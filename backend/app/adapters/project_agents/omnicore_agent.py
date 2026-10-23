"""OmniCoreAgent guide runtime over a closed OpenRouter transport guard."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import math
import os
import secrets
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.adapters.project_agents.compilation_draft import CompilationDraftParser
from app.adapters.project_agents.omnicore_profile import (
    LITELLM_VERSION,
    OMNICORE_MAX_TOKENS,
    OMNICORE_MODEL,
    OMNICORE_PROVIDER_ATTEMPTS,
    OMNICORE_RUNTIME_KEY,
    OmniCoreAgentProfile,
    require_omnicore_agent_adapter_profile,
)
from app.adapters.project_agents.result_validation import (
    require_result_sources_opened,
    validate_project_guide_runtime_result,
)
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.interfaces.project_agents import (
    ProjectAgentRuntimeConfigurationError,
    ProjectAgentRuntimeError,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    invalid_compilation_failure_code,
    project_guide_compilation_prompt_bytes,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.projects.api.guide_documents import GuideRuntimeCapabilities


_INVALID_SCHEMA_OUTPUT = object()
_OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_PLUGINS = (
    "web",
    "file-parser",
    "response-healing",
    "alignment",
    "armor",
    "pareto",
)
_READ_DESCRIPTION = "Read bounded text from an assigned original using its exact opaque handle."
_SEARCH_DESCRIPTION = "Search bounded text in an assigned original using its exact opaque handle."
_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "handle": {
            "type": "string",
            "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        },
        "offset": {
            "type": "integer",
            "default": 0,
            "minimum": 0,
            "maximum": 2_147_483_647,
        },
        "limit": {
            "type": "integer",
            "default": 16000,
            "minimum": 1,
            "maximum": 16000,
        },
    },
    "required": ["handle"],
    "additionalProperties": False,
}
_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "handle": {
            "type": "string",
            "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        },
        "query": {"type": "string", "minLength": 1, "maxLength": 1000},
        "offset": {
            "type": "integer",
            "default": 0,
            "minimum": 0,
            "maximum": 2_147_483_647,
        },
        "limit": {
            "type": "integer",
            "default": 20,
            "minimum": 1,
            "maximum": 20,
        },
    },
    "required": ["handle", "query"],
    "additionalProperties": False,
}
_MODEL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": _READ_DESCRIPTION,
            "parameters": _READ_SCHEMA,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_document",
            "description": _SEARCH_DESCRIPTION,
            "parameters": _SEARCH_SCHEMA,
        },
    },
]
_ALLOWED_HEADERS = frozenset(
    {
        "host",
        "authorization",
        "content-type",
        "content-length",
        "accept",
        "accept-encoding",
        "user-agent",
        "connection",
        "http-referer",
        "x-title",
    }
)
_ALLOWED_BODY_FIELDS = frozenset(
    {
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "top_p",
        "stream",
        "tools",
        "tool_choice",
        "usage",
    }
)
_RETRY_RESPONSE_HEADERS = frozenset(
    {
        "retry-after",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
    }
)


@dataclass(frozen=True, slots=True)
class _UpstreamTarget:
    url: str


_PRODUCTION_UPSTREAM = _UpstreamTarget(_OPENROUTER_CHAT_COMPLETIONS_URL)


class OmniCoreAgentProjectGuideRuntime:
    """Run OmniCoreAgent with only the two trusted guide-document tools."""

    def __init__(
        self,
        configuration: ProjectGuideRuntimeConfiguration,
        *,
        _test_upstream: str | None = None,
        _test_authority: object | None = None,
    ) -> None:
        """Validate the pinned runtime, profile, provider, model and credential."""
        if (
            configuration.runtime_key != OMNICORE_RUNTIME_KEY
            or configuration.model_provider != "openrouter"
            or configuration.model_api != "chat_completions"
            or configuration.model != OMNICORE_MODEL
            or not configuration.uses_inference
        ):
            raise ProjectAgentRuntimeConfigurationError("project guide runtime is unsupported")
        if configuration.maximum_turns < 2:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime requires draft and review turns"
            )
        credential = os.environ.get("OPENROUTER_API_KEY")
        if not credential:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide model credentials are unavailable"
            )
        self._profile = require_omnicore_agent_adapter_profile(
            configuration.adapter_profile_values()
        )
        self._configuration = configuration
        self._credential = credential
        self._test_upstream = _validated_test_upstream(_test_upstream, _test_authority)
        self._admitted = False
        self._closed = False
        self._running_task: asyncio.Task[Any] | None = None

    @classmethod
    def _for_test(
        cls,
        configuration: ProjectGuideRuntimeConfiguration,
        *,
        upstream_url: str,
    ) -> OmniCoreAgentProjectGuideRuntime:
        """Inject a loopback-only fake upstream outside product composition."""
        return cls(
            configuration,
            _test_upstream=upstream_url,
            _test_authority=_TEST_UPSTREAM_AUTHORITY,
        )

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Expose the immutable identity checked by the shared factory."""
        return self._configuration.adapter_identity

    def admit_execution(self) -> None:
        """Admit one attempt before the durable execution fence."""
        if self._closed:
            raise ProjectAgentRuntimeError("project guide runtime is closed")
        if self._admitted:
            raise ProjectAgentRuntimeError("project guide runtime admission already acquired")
        self._admitted = True

    async def aclose(self) -> None:
        """Close idempotently and await any concurrently running compilation."""
        if self._closed:
            return
        self._closed = True
        self._admitted = False
        task = self._running_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def compile_project_guide(
        self,
        context: ProjectGuideCompilationContext,
        capabilities: GuideRuntimeCapabilities,
    ) -> ProjectGuideCompilationResult:
        """Run one bounded draft-and-review attempt through the native SDK loop."""
        if context.runtime_configuration != self._configuration:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime configuration mismatch"
            )
        if self._closed:
            raise ProjectAgentRuntimeError("project guide runtime is closed")
        if not self._admitted:
            raise ProjectAgentRuntimeError("project guide runtime was not admitted")
        if self._running_task is not None:
            raise ProjectAgentRuntimeError("project guide runtime is already running")
        prompt = project_guide_compilation_prompt_bytes(context)
        if len(prompt) > self._configuration.maximum_manifest_bytes:
            raise ProjectAgentRuntimeError("project guide prompt exceeds configured size limit")
        self._require_credential_unchanged()
        task = asyncio.current_task()
        if task is None:
            raise ProjectAgentRuntimeError("project guide runtime task is unavailable")
        self._running_task = task
        runtime_failure: str | None = None
        invalid_failure: str | None = None
        output: object = None
        try:
            output = await asyncio.wait_for(
                self._run(context, prompt.decode("utf-8"), capabilities),
                timeout=self._configuration.timeout_seconds,
            )
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            runtime_failure = "project guide run cancelled"
        except TimeoutError:
            runtime_failure = "project guide run timed out"
        except ProjectGuideCompilationInvalidOutputError as error:
            invalid_failure = error.failure_code
        except Exception:
            runtime_failure = "project guide run failed"
        finally:
            self._running_task = None
            try:
                self._require_credential_unchanged()
            except ProjectAgentRuntimeError:
                runtime_failure = "project guide run failed"
        if runtime_failure is not None:
            raise ProjectAgentRuntimeError(runtime_failure) from None
        if invalid_failure is not None:
            raise ProjectGuideCompilationInvalidOutputError(invalid_failure) from None
        if output is _INVALID_SCHEMA_OUTPUT:
            raise ProjectGuideCompilationInvalidOutputError("schema_invalid") from None
        try:
            opened = await capabilities.tools.opened_handles()
            return validate_project_guide_runtime_result(context, output, opened)
        except (TypeError, ValueError) as error:
            invalid_failure = invalid_compilation_failure_code(error)
        output = None
        raise ProjectGuideCompilationInvalidOutputError(invalid_failure) from None

    async def _run(
        self,
        context: ProjectGuideCompilationContext,
        prompt: str,
        capabilities: GuideRuntimeCapabilities,
    ) -> object:
        """Keep SDK construction, tools, requests and cleanup inside one deadline."""
        from omnicoreagent import MemoryRouter, OmniCoreAgent, ToolRegistry

        configuration = self._configuration
        profile = self._profile
        maximum_requests = configuration.maximum_turns * OMNICORE_PROVIDER_ATTEMPTS
        guard = _LoopbackOpenRouterGuard(
            credential=self._credential,
            profile=profile,
            maximum_requests=maximum_requests,
            io_timeout_seconds=max(1, min(300, configuration.timeout_seconds)),
            upstream=self._test_upstream,
        )
        agents: list[Any] = []
        await guard.start()
        try:
            draft_steps = max(1, configuration.maximum_turns // 2)
            review_steps = configuration.maximum_turns - draft_steps
            review_opened: set[str] = set()
            phase = "draft"
            registry = ToolRegistry()

            @registry.register_tool(
                name="read_document",
                inputSchema=_READ_SCHEMA,
                description=_READ_DESCRIPTION,
                idempotent=True,
            )
            async def read_document(handle: str, offset: int = 0, limit: int = 16000) -> str:
                value = await capabilities.tools.read_document(handle, offset=offset, limit=limit)
                if phase == "review":
                    review_opened.add(handle)
                return value.model_dump_json()

            @registry.register_tool(
                name="search_document",
                inputSchema=_SEARCH_SCHEMA,
                description=_SEARCH_DESCRIPTION,
                idempotent=True,
            )
            async def search_document(
                handle: str,
                query: str,
                offset: int = 0,
                limit: int = 20,
            ) -> str:
                value = await capabilities.tools.search_document(
                    handle,
                    query,
                    offset=offset,
                    limit=limit,
                )
                if phase == "review":
                    review_opened.add(handle)
                return value.model_dump_json()

            schema = ProjectGuideCompilationResult.model_json_schema()
            draft_parser = CompilationDraftParser(schema, configuration.maximum_manifest_bytes)
            draft_agent = _build_agent(
                OmniCoreAgent=OmniCoreAgent,
                MemoryRouter=MemoryRouter,
                configuration=configuration,
                credential=self._credential,
                base_url=guard.base_url,
                registry=registry,
                maximum_steps=draft_steps,
                phase_instruction=(
                    "Produce a private draft. Return only one JSON object matching "
                    "this exact schema: "
                    + json.dumps(schema, separators=(",", ":"), ensure_ascii=True)
                ),
            )
            agents.append(draft_agent)
            await _require_exact_tool_inventory(draft_agent)
            draft_output = await _run_native_agent(
                draft_agent,
                prompt,
                guard=guard,
                cleanup_timeout_seconds=profile.cleanup_timeout_seconds,
            )
            candidate = draft_parser.parse(draft_output)
            draft_output = None
            if candidate is None:
                return _INVALID_SCHEMA_OUTPUT
            review_input = json.dumps(
                {
                    "phase": "coverage_review",
                    "guide_setup_context": json.loads(prompt),
                    "candidate_proposal": candidate,
                    "candidate_validation_issues": draft_parser.canonical_issues(candidate),
                },
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            candidate = None
            if len(review_input.encode("utf-8")) > configuration.maximum_manifest_bytes:
                raise ProjectGuideCompilationInvalidOutputError("schema_invalid")
            await _cleanup_agent(draft_agent, profile.cleanup_timeout_seconds)
            agents.remove(draft_agent)
            phase = "review"
            review_agent = _build_agent(
                OmniCoreAgent=OmniCoreAgent,
                MemoryRouter=MemoryRouter,
                configuration=configuration,
                credential=self._credential,
                base_url=guard.base_url,
                registry=registry,
                maximum_steps=review_steps,
                phase_instruction=(
                    "Independently review source coverage, reopen every source cited "
                    "by the final proposal, repair the candidate, and return only one "
                    "complete JSON object matching this exact schema: "
                    + json.dumps(schema, separators=(",", ":"), ensure_ascii=True)
                ),
            )
            agents.append(review_agent)
            await _require_exact_tool_inventory(review_agent)
            final_output = await _run_native_agent(
                review_agent,
                review_input,
                guard=guard,
                cleanup_timeout_seconds=profile.cleanup_timeout_seconds,
            )
            if len(final_output.encode("utf-8")) > configuration.maximum_manifest_bytes:
                return _INVALID_SCHEMA_OUTPUT
            try:
                provisional = ProjectGuideCompilationResult.model_validate_json(final_output)
                require_result_sources_opened(context, provisional, review_opened)
            except (TypeError, ValueError):
                return _INVALID_SCHEMA_OUTPUT
            return final_output
        finally:
            cleanup_error: BaseException | None = None
            try:
                await guard.close(profile.cleanup_timeout_seconds)
            except BaseException as error:
                cleanup_error = cleanup_error or error
            for agent in reversed(agents):
                try:
                    await _cleanup_agent(agent, profile.cleanup_timeout_seconds)
                except BaseException as error:
                    cleanup_error = cleanup_error or error
            try:
                self._require_credential_unchanged()
            except BaseException as error:
                cleanup_error = cleanup_error or error
            if cleanup_error is not None:
                raise cleanup_error

    def _require_credential_unchanged(self) -> None:
        """Reject SDK lifecycle drift without rewriting process-global state."""
        current = os.environ.get("OPENROUTER_API_KEY")
        if current is None or not hmac.compare_digest(current, self._credential):
            raise ProjectAgentRuntimeError("project guide model credential changed")


def _build_agent(
    *,
    OmniCoreAgent: Any,
    MemoryRouter: Any,
    configuration: ProjectGuideRuntimeConfiguration,
    credential: str,
    base_url: str,
    registry: Any,
    maximum_steps: int,
    phase_instruction: str,
) -> Any:
    """Construct one phase with a fresh private in-memory session and no extras."""
    telemetry_config = {
        "storage": "memory",
        "memory_max_traces": 1,
        "capture": "default",
        "record_inputs": False,
        "record_outputs": False,
        "record_model_prompts": False,
        "record_model_responses": False,
        "record_tool_results": False,
        "record_token_details": False,
        "offload_large_payloads": False,
        "strict": True,
    }
    agent_config = {
        "request_limit": maximum_steps,
        "max_steps": maximum_steps,
        "tool_call_timeout": max(2, min(1000, configuration.timeout_seconds)),
        "enable_advanced_tool_use": False,
        "enable_subagents": False,
        "worker_profiles": [],
        "enable_agent_skills": False,
        "completion_review": 0,
        "code_mode": {},
        "agents_md": {},
        "enable_workspace_files": False,
        "tool_offload": {"enabled": False},
        "governance_config": {"enabled": False},
    }
    return OmniCoreAgent(
        name="ProjectGuideCompilationAgent",
        system_instruction=configuration.instructions + "\n\n" + phase_instruction,
        model_config={
            "provider": "openrouter",
            "model": configuration.model,
            "api_key": credential,
            "base_url": base_url,
            "temperature": 0,
            "max_tokens": OMNICORE_MAX_TOKENS,
        },
        mcp_tools=[],
        local_tools=registry,
        sub_agents=[],
        agent_config=agent_config,
        memory_router=MemoryRouter("in_memory"),
        telemetry_exporters=[],
        telemetry_config=telemetry_config,
        debug=False,
    )


async def _require_exact_tool_inventory(agent: Any) -> None:
    inventory = await agent.list_all_available_tools()
    if [item.get("name") for item in inventory] != [
        "read_document",
        "search_document",
    ]:
        raise ProjectAgentRuntimeError("project guide runtime tool inventory changed")


async def _run_native_agent(
    agent: Any,
    query: str,
    *,
    guard: _LoopbackOpenRouterGuard,
    cleanup_timeout_seconds: int,
) -> str:
    native_task = asyncio.create_task(
        agent.run(
            query,
            session_id="workstream-" + secrets.token_hex(16),
        )
    )
    try:
        response = await asyncio.shield(native_task)
    except asyncio.CancelledError:
        close_error: BaseException | None = None
        try:
            await guard.close(cleanup_timeout_seconds)
        except BaseException as error:
            close_error = error
        native_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(native_task), timeout=cleanup_timeout_seconds)
        except asyncio.CancelledError:
            pass
        except TimeoutError:
            native_task.cancel()
            raise ProjectAgentRuntimeError(
                "project guide native cancellation did not finish"
            ) from None
        if close_error is not None:
            raise close_error
        raise
    if (
        not isinstance(response, dict)
        or response.get("status") != "success"
        or response.get("termination_reason") != "stop"
        or not isinstance(response.get("response"), str)
    ):
        raise ProjectAgentRuntimeError("project guide native run failed")
    return response["response"]


async def _cleanup_agent(agent: Any, timeout_seconds: int) -> None:
    cleanup = asyncio.create_task(agent.cleanup())
    try:
        await asyncio.wait_for(asyncio.shield(cleanup), timeout=timeout_seconds)
    except BaseException:
        cleanup.cancel()
        with suppress(BaseException):
            await cleanup
        raise


@dataclass(frozen=True, slots=True)
class _ParsedRequest:
    body: dict[str, Any]


class _LoopbackOpenRouterGuard:
    """Validate one pinned SDK envelope and rebuild a fixed OpenRouter request."""

    def __init__(
        self,
        *,
        credential: str,
        profile: OmniCoreAgentProfile,
        maximum_requests: int,
        io_timeout_seconds: int,
        upstream: _UpstreamTarget | None,
    ) -> None:
        self._credential = credential
        self._profile = profile
        self._maximum_requests = maximum_requests
        self._io_timeout_seconds = io_timeout_seconds
        self._upstream_url = (upstream or _PRODUCTION_UPSTREAM).url
        self._path_token = secrets.token_urlsafe(32)
        self._server: asyncio.AbstractServer | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._writers: set[asyncio.StreamWriter] = set()
        self._client: Any = None
        self._port: int | None = None
        self._requests = 0
        self._active = False
        self._closing = False

    @property
    def base_url(self) -> str:
        if self._port is None:
            raise RuntimeError("OpenRouter guard is not started")
        return f"http://127.0.0.1:{self._port}/{self._path_token}/v1"

    async def start(self) -> None:
        import httpx

        self._client = httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            timeout=self._io_timeout_seconds,
        )
        self._client.headers.clear()
        try:
            self._server = await asyncio.start_server(
                self._accepted,
                host="127.0.0.1",
                port=0,
                limit=self._profile.maximum_header_bytes + 1,
                start_serving=True,
            )
        except BaseException:
            await self._client.aclose()
            raise
        sockets = self._server.sockets or []
        if len(sockets) != 1:
            self._server.close()
            await self._server.wait_closed()
            await self._client.aclose()
            raise RuntimeError("OpenRouter guard listener is invalid")
        self._port = int(sockets[0].getsockname()[1])

    def _accepted(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._closing or self._tasks:
            writer.close()
            return
        task = asyncio.create_task(self._handle(reader, writer))
        self._tasks.add(task)
        self._writers.add(writer)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(lambda _task: self._writers.discard(writer))

    async def close(self, timeout_seconds: int) -> None:
        if self._closing:
            return
        self._closing = True
        if self._server is not None:
            self._server.close()
        for writer in list(self._writers):
            writer.close()
        if self._server is not None:
            await self._server.wait_closed()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        cleanup_error: BaseException | None = None
        try:
            if tasks:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout_seconds,
                )
        except BaseException as error:
            cleanup_error = error
        try:
            if self._client is not None:
                await asyncio.wait_for(self._client.aclose(), timeout=timeout_seconds)
        except BaseException as error:
            cleanup_error = cleanup_error or error
        finally:
            self._tasks.clear()
            self._writers.clear()
        if cleanup_error is not None:
            raise cleanup_error

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        status = 400
        response_headers: Mapping[str, str] = {}
        response_body = b'{"error":{"message":"request rejected"}}'
        write_response = True
        try:
            if self._closing or self._active:
                status = 503
            elif self._requests >= self._maximum_requests:
                status = 429
            else:
                self._active = True
                self._requests += 1
                try:
                    request = await self._read_request(reader)
                    status, response_headers, response_body = await self._forward(request)
                finally:
                    self._active = False
        except _GuardRejection as error:
            status = error.status
        except asyncio.CancelledError:
            write_response = False
            raise
        except Exception:
            status = 502
        finally:
            if write_response and not writer.is_closing():
                with suppress(Exception):
                    await self._write_response(writer, status, response_headers, response_body)
            if not writer.is_closing():
                writer.close()
            with suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), timeout=1)

    async def _read_request(self, reader: asyncio.StreamReader) -> _ParsedRequest:
        timeout = self._io_timeout_seconds
        try:
            header_block = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=timeout)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
            raise _GuardRejection(400) from None
        if len(header_block) > self._profile.maximum_header_bytes:
            raise _GuardRejection(431)
        try:
            lines = header_block[:-4].decode("ascii").split("\r\n")
        except UnicodeDecodeError:
            raise _GuardRejection(400) from None
        expected_path = f"/{self._path_token}/v1/chat/completions"
        if not lines or lines[0] != f"POST {expected_path} HTTP/1.1":
            raise _GuardRejection(404)
        if len(lines) - 1 > self._profile.maximum_headers:
            raise _GuardRejection(431)
        headers: dict[str, str] = {}
        for line in lines[1:]:
            name, separator, value = line.partition(":")
            normalized = name.lower()
            value = value.strip()
            if (
                not separator
                or normalized in headers
                or normalized not in _ALLOWED_HEADERS
                or len(name) > 64
                or len(value.encode("ascii", errors="ignore")) > 1024
                or any(ord(character) < 32 or ord(character) > 126 for character in value)
            ):
                raise _GuardRejection(400)
            headers[normalized] = value
        if set(headers) != _ALLOWED_HEADERS:
            raise _GuardRejection(400)
        if headers["host"] != f"127.0.0.1:{self._port}":
            raise _GuardRejection(400)
        expected_auth = "Bearer " + self._credential
        if not hmac.compare_digest(headers["authorization"], expected_auth):
            raise _GuardRejection(401)
        if (
            headers["content-type"] != "application/json"
            or headers["connection"].lower() != "keep-alive"
            or headers["user-agent"] != f"litellm/{LITELLM_VERSION}"
            or headers["http-referer"] != "https://litellm.ai"
            or headers["x-title"] != "liteLLM"
        ):
            raise _GuardRejection(400)
        try:
            content_length = int(headers["content-length"])
        except ValueError:
            raise _GuardRejection(400) from None
        if not 1 <= content_length <= self._profile.maximum_request_bytes:
            raise _GuardRejection(413)
        try:
            body_bytes = await asyncio.wait_for(reader.readexactly(content_length), timeout=timeout)
            body = json.loads(
                body_bytes,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (
            asyncio.IncompleteReadError,
            TimeoutError,
            UnicodeDecodeError,
            ValueError,
            RecursionError,
        ):
            raise _GuardRejection(400) from None
        if not isinstance(body, dict):
            raise _GuardRejection(400)
        _validate_request_body(body)
        return _ParsedRequest(body=body)

    async def _forward(self, request: _ParsedRequest) -> tuple[int, Mapping[str, str], bytes]:
        outbound = _rebuild_openrouter_body(request.body)
        request_body = json.dumps(
            outbound,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self._client.cookies.clear()
        try:
            async with self._client.stream(
                "POST",
                self._upstream_url,
                headers={
                    "Authorization": "Bearer " + self._credential,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                content=request_body,
            ) as response:
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self._profile.maximum_response_bytes:
                        raise _GuardRejection(502)
                    chunks.append(chunk)
                content_type = response.headers.get("content-type", "")
                if not content_type.lower().startswith("application/json"):
                    raise _GuardRejection(502)
                returned_headers = {
                    key: value
                    for key, value in response.headers.items()
                    if key.lower() in _RETRY_RESPONSE_HEADERS
                    and len(value.encode("ascii", errors="ignore")) <= 256
                }
                return response.status_code, returned_headers, b"".join(chunks)
        finally:
            self._client.cookies.clear()

    async def _write_response(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        headers: Mapping[str, str],
        body: bytes,
    ) -> None:
        reason = {
            200: "OK",
            400: "Bad Request",
            401: "Unauthorized",
            404: "Not Found",
            413: "Payload Too Large",
            429: "Too Many Requests",
            431: "Request Header Fields Too Large",
            500: "Internal Server Error",
            502: "Bad Gateway",
            503: "Service Unavailable",
        }.get(status, "Provider Response")
        lines = [
            f"HTTP/1.1 {status} {reason}",
            "Content-Type: application/json",
            f"Content-Length: {len(body)}",
            "Connection: close",
        ]
        for name, value in headers.items():
            lines.append(f"{name}: {value}")
        writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + body)
        await asyncio.wait_for(writer.drain(), timeout=self._io_timeout_seconds)


class _GuardRejection(Exception):
    def __init__(self, status: int) -> None:
        self.status = status


def _validate_request_body(body: dict[str, Any]) -> None:
    if set(body) - _ALLOWED_BODY_FIELDS:
        raise _GuardRejection(400)
    if body.get("model") != OMNICORE_MODEL:
        raise _GuardRejection(400)
    if body.get("tools") != _MODEL_TOOLS:
        raise _GuardRejection(400)
    if body.get("usage") != {"include": True}:
        raise _GuardRejection(400)
    if body.get("stream", False) is not False:
        raise _GuardRejection(400)
    if "tool_choice" in body and body["tool_choice"] != "auto":
        raise _GuardRejection(400)
    temperature = body.get("temperature")
    if isinstance(temperature, bool) or temperature != 0:
        raise _GuardRejection(400)
    top_p = body.get("top_p")
    if top_p is not None and (
        isinstance(top_p, bool)
        or not isinstance(top_p, (int, float))
        or not math.isfinite(top_p)
        or top_p != 1
    ):
        raise _GuardRejection(400)
    max_tokens = body.get("max_tokens")
    if max_tokens != OMNICORE_MAX_TOKENS:
        raise _GuardRejection(400)
    messages = body.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 512:
        raise _GuardRejection(400)
    for message in messages:
        _validate_message(message)


def _validate_message(message: object) -> None:
    if not isinstance(message, dict):
        raise _GuardRejection(400)
    role = message.get("role")
    if role in {"system", "user"}:
        if set(message) != {"role", "content"} or not isinstance(message.get("content"), str):
            raise _GuardRejection(400)
        return
    if role == "tool":
        if set(message) != {"role", "tool_call_id", "content"} or not all(
            isinstance(message.get(name), str) for name in ("tool_call_id", "content")
        ):
            raise _GuardRejection(400)
        return
    if role != "assistant" or set(message) - {"role", "content", "tool_calls"}:
        raise _GuardRejection(400)
    if message.get("content") is not None and not isinstance(message.get("content"), str):
        raise _GuardRejection(400)
    calls = message.get("tool_calls")
    if calls is not None:
        if not isinstance(calls, list) or not 1 <= len(calls) <= 64:
            raise _GuardRejection(400)
        for call in calls:
            _validate_tool_call(call)


def _validate_tool_call(call: object) -> None:
    if (
        not isinstance(call, dict)
        or set(call) != {"id", "type", "function"}
        or call.get("type") != "function"
        or not isinstance(call.get("id"), str)
        or not 1 <= len(call["id"]) <= 256
    ):
        raise _GuardRejection(400)
    function = call.get("function")
    if (
        not isinstance(function, dict)
        or set(function) != {"name", "arguments"}
        or function.get("name") not in {"read_document", "search_document"}
        or not isinstance(function.get("arguments"), str)
        or len(function["arguments"].encode("utf-8")) > 65_536
    ):
        raise _GuardRejection(400)
    try:
        arguments = json.loads(
            function["arguments"],
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (ValueError, RecursionError):
        raise _GuardRejection(400) from None
    if not isinstance(arguments, dict):
        raise _GuardRejection(400)


def _rebuild_openrouter_body(body: dict[str, Any]) -> dict[str, Any]:
    rebuilt = {
        key: body[key]
        for key in (
            "messages",
            "temperature",
            "max_tokens",
            "top_p",
            "stream",
            "tool_choice",
        )
        if key in body
    }
    rebuilt.update(
        {
            "model": OMNICORE_MODEL,
            "tools": _MODEL_TOOLS,
            "usage": {"include": True},
            "provider": {
                "allow_fallbacks": False,
                "data_collection": "deny",
            },
            "plugins": [{"id": plugin, "enabled": False} for plugin in _OPENROUTER_PLUGINS],
        }
    )
    return rebuilt


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("nonstandard JSON constant")


_TEST_UPSTREAM_AUTHORITY = object()


def _validated_test_upstream(value: str | None, authority: object | None) -> _UpstreamTarget | None:
    if value is None and authority is None:
        return None
    if authority is not _TEST_UPSTREAM_AUTHORITY or not isinstance(value, str):
        raise ProjectAgentRuntimeConfigurationError("project guide test transport is unavailable")
    parsed = urlparse(value)
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        raise ProjectAgentRuntimeConfigurationError(
            "project guide test transport must be loopback"
        ) from None
    if (
        parsed.scheme != "http"
        or not address.is_loopback
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.port is None
    ):
        raise ProjectAgentRuntimeConfigurationError("project guide test transport must be loopback")
    return _UpstreamTarget(value)
