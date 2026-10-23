"""Actual OmniCoreAgent loop qualification over the closed synthetic transport."""

from __future__ import annotations

import asyncio
import copy
import json
import os
from contextlib import suppress
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from app.adapters.project_agents.omnicore_agent import (
    OmniCoreAgentProjectGuideRuntime,
    _GuardRejection,
    _LoopbackOpenRouterGuard,
    _MODEL_TOOLS,
    _OPENROUTER_PLUGINS,
    _TEST_UPSTREAM_AUTHORITY,
    _unique_object,
    _validated_test_upstream,
    _validate_request_body,
)
from app.adapters.project_agents.omnicore_profile import (
    OMNICORE_MODEL,
    build_omnicore_agent_adapter_profile,
    require_omnicore_agent_adapter_profile,
)
from app.interfaces.guide_document_tools import GuideDocumentToolResult
from app.interfaces.project_agents import (
    ProjectAgentRuntimeConfigurationError,
    ProjectAgentRuntimeError,
    ProjectGuideCompilationInvalidOutputError,
)
from app.interfaces.project_guide_runtime import canonical_adapter_profile
from tests.projects.guide_compilation.helpers import (
    context,
    generated_result,
    ids,
)


class _SyntheticOpenRouter:
    """Bounded loopback provider capturing only generated test material."""

    def __init__(
        self,
        *,
        handle: str,
        final_output: str,
        retry_statuses: tuple[int, ...] = (),
        hang: bool = False,
    ) -> None:
        self.handle = handle
        self.final_output = final_output
        self.retry_statuses = retry_statuses
        self.hang = hang
        self.requests: list[tuple[dict[str, str], dict[str, object]]] = []
        self.received = asyncio.Event()
        self.disconnected = asyncio.Event()
        self._server: asyncio.AbstractServer | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def url(self) -> str:
        assert self._server is not None and self._server.sockets
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}/chat/completions"

    async def __aenter__(self) -> _SyntheticOpenRouter:
        self._server = await asyncio.start_server(self._accepted, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _accepted(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(self._handle(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            lines = head[:-4].decode("ascii").split("\r\n")
            headers = {}
            for line in lines[1:]:
                name, value = line.split(":", 1)
                headers[name.lower()] = value.strip()
            body = json.loads(await reader.readexactly(int(headers["content-length"])))
            self.requests.append((headers, body))
            self.received.set()
            if self.hang:
                await reader.read()
                self.disconnected.set()
                return
            if len(self.requests) <= len(self.retry_statuses):
                status = self.retry_statuses[len(self.requests) - 1]
                await self._respond(
                    writer,
                    status,
                    {"error": {"message": "synthetic retryable provider failure"}},
                    extra_headers={"Retry-After": "0"},
                )
                return
            successful_index = len(self.requests) - len(self.retry_statuses)
            if successful_index % 2 == 1:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{successful_index}",
                            "type": "function",
                            "function": {
                                "name": "read_document",
                                "arguments": json.dumps({"handle": self.handle}),
                            },
                        }
                    ],
                }
                finish_reason = "tool_calls"
            else:
                message = {"role": "assistant", "content": self.final_output}
                finish_reason = "stop"
            await self._respond(
                writer,
                200,
                {
                    "id": f"chatcmpl-{len(self.requests)}",
                    "object": "chat.completion",
                    "created": 1,
                    "model": OMNICORE_MODEL,
                    "choices": [
                        {
                            "index": 0,
                            "message": message,
                            "finish_reason": finish_reason,
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            )
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    @staticmethod
    async def _respond(
        writer: asyncio.StreamWriter,
        status: int,
        body: dict[str, object],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = [
            f"HTTP/1.1 {status} Synthetic",
            "Content-Type: application/json",
            f"Content-Length: {len(payload)}",
            "Connection: close",
        ]
        headers.extend(f"{name}: {value}" for name, value in (extra_headers or {}).items())
        writer.write(("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + payload)
        await writer.drain()


def _runtime_context():
    compilation_context = context(ids())
    configuration = compilation_context.runtime_configuration.model_copy(
        update={
            "runtime_key": "omnicore_agent",
            "model_provider": "openrouter",
            "model_api": "chat_completions",
            "model": OMNICORE_MODEL,
            "adapter_profile": canonical_adapter_profile(build_omnicore_agent_adapter_profile({})),
            "timeout_seconds": 300,
            "maximum_turns": 6,
        }
    )
    return compilation_context.model_copy(update={"runtime_configuration": configuration})


def _provider_output() -> str:
    return generated_result().model_dump_json()


def _capabilities(compilation_context):
    opened: set[str] = set()
    reads: list[str] = []
    document = compilation_context.material.documents[0]
    handle = compilation_context.material.handle_for(document)

    async def read_document(
        supplied_handle: str, *, offset: int = 0, limit: int = 16000
    ) -> GuideDocumentToolResult:
        assert supplied_handle == handle
        assert offset == 0 and limit == 16000
        opened.add(supplied_handle)
        reads.append(supplied_handle)
        return GuideDocumentToolResult(
            handle=handle,
            source_item_id=document.source_item_id,
            document_version_id=document.ingest_id,
            sha256=document.sha256,
            operation="read",
            text="Generated synthetic guide text.",
            locators=(),
            next_offset=None,
            total_characters=31,
        )

    async def search_document(
        supplied_handle: str,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> GuideDocumentToolResult:
        value = await read_document(supplied_handle, offset=offset, limit=16000)
        assert query and limit == 20
        return value.model_copy(update={"operation": "search"})

    async def opened_handles() -> frozenset[str]:
        return frozenset(opened)

    return (
        SimpleNamespace(
            tools=SimpleNamespace(
                read_document=read_document,
                search_document=search_document,
                opened_handles=opened_handles,
            )
        ),
        reads,
        handle,
    )


@pytest.fixture(autouse=True)
def synthetic_credential(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-omnicore-test-key")


async def _send_guard_request(
    base_url: str,
    *,
    header_override: tuple[str, str] | None = None,
) -> bytes:
    parsed = urlparse(base_url)
    request_body = json.dumps(
        {
            "model": OMNICORE_MODEL,
            "messages": [
                {"role": "system", "content": "Synthetic."},
                {"role": "user", "content": "Synthetic."},
            ],
            "temperature": 0,
            "max_tokens": 16_384,
            "tools": _MODEL_TOOLS,
            "usage": {"include": True},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    headers = {
        "Host": f"127.0.0.1:{parsed.port}",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "User-Agent": "litellm/1.106.2",
        "HTTP-Referer": "https://litellm.ai",
        "X-Title": "liteLLM",
        "Authorization": "Bearer synthetic-omnicore-test-key",
        "Content-Type": "application/json",
        "Content-Length": str(len(request_body)),
    }
    if header_override is not None:
        headers[header_override[0]] = header_override[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", parsed.port)
    request_path = parsed.path + "/chat/completions"
    wire = [f"POST {request_path} HTTP/1.1"]
    wire.extend(f"{name}: {item}" for name, item in headers.items())
    writer.write(("\r\n".join(wire) + "\r\n\r\n").encode("ascii") + request_body)
    await writer.drain()
    status_line = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return status_line


def test_profile_provider_and_test_transport_are_closed(monkeypatch):
    profile = build_omnicore_agent_adapter_profile({})
    assert profile["provider_retries"] == 3
    assert profile["provider_attempts"] == 4
    assert profile["provider_fallbacks_allowed"] is False
    assert profile["data_collection"] == "deny"
    assert profile["provider_plugin_disable_requests"] is True
    assert profile["sdk_environment"] == "omnicore"
    assert profile["process_sdk_exclusive"] is True
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="no runtime options"):
        build_omnicore_agent_adapter_profile({"base_url": "https://example.invalid"})

    compilation_context = _runtime_context()
    monkeypatch.delenv("OPENROUTER_API_KEY")
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="credentials"):
        OmniCoreAgentProjectGuideRuntime(compilation_context.runtime_configuration)
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-omnicore-test-key")
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="loopback"):
        OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url="https://example.invalid/chat/completions",
        )
    for model in ("openai/gpt-5.6-terra:online", "openrouter/auto"):
        with pytest.raises(ProjectAgentRuntimeConfigurationError, match="unsupported"):
            OmniCoreAgentProjectGuideRuntime(
                compilation_context.runtime_configuration.model_copy(update={"model": model})
            )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda body: body.update(models=[OMNICORE_MODEL]),
        lambda body: body.update(route="alternate"),
        lambda body: body.update(plugins=[]),
        lambda body: body.update(model="openrouter/auto"),
        lambda body: body.update(usage={"include": False}),
        lambda body: body.update(temperature=1),
        lambda body: body.update(max_tokens=1),
        lambda body: body.update(tools=[{"type": "web_search", "web_search": {}}]),
    ],
)
def test_transport_rejects_each_routing_and_tool_mutation_before_forward(mutation):
    body = {
        "model": OMNICORE_MODEL,
        "messages": [
            {"role": "system", "content": "Generated synthetic instruction."},
            {"role": "user", "content": "Generated synthetic request."},
        ],
        "temperature": 0,
        "max_tokens": 16_384,
        "tools": copy.deepcopy(_MODEL_TOOLS),
        "usage": {"include": True},
    }
    mutation(body)
    with pytest.raises(_GuardRejection):
        _validate_request_body(body)


def test_transport_rejects_duplicate_json_members():
    with pytest.raises(ValueError, match="duplicate"):
        _unique_object([("model", OMNICORE_MODEL), ("model", "openrouter/auto")])


@pytest.mark.parametrize(
    ("header", "value"),
    [
        ("Authorization", "Bearer hostile-key"),
        ("HTTP-Referer", "https://example.invalid"),
        ("User-Agent", "litellm/0.0.0"),
        ("Cookie", "session=hostile"),
    ],
)
async def test_transport_header_mutations_never_reach_upstream(header, value):
    handle = "00000000-0000-0000-0000-000000000001"
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output='{"synthetic":true}',
    ) as provider:
        profile = require_omnicore_agent_adapter_profile(build_omnicore_agent_adapter_profile({}))
        guard = _LoopbackOpenRouterGuard(
            credential="synthetic-omnicore-test-key",
            profile=profile,
            maximum_requests=1,
            io_timeout_seconds=5,
            upstream=_validated_test_upstream(provider.url, _TEST_UPSTREAM_AUTHORITY),
        )
        await guard.start()
        try:
            status_line = await _send_guard_request(guard.base_url, header_override=(header, value))
            assert status_line.startswith((b"HTTP/1.1 400", b"HTTP/1.1 401"))
        finally:
            await guard.close(5)
    assert provider.requests == []


async def test_transport_stops_oversized_provider_response():
    async with _SyntheticOpenRouter(
        handle="00000000-0000-0000-0000-000000000001",
        final_output='{"synthetic":true}',
    ) as provider:
        profile = require_omnicore_agent_adapter_profile(build_omnicore_agent_adapter_profile({}))
        guard = _LoopbackOpenRouterGuard(
            credential="synthetic-omnicore-test-key",
            profile=replace(profile, maximum_response_bytes=64),
            maximum_requests=1,
            io_timeout_seconds=5,
            upstream=_validated_test_upstream(provider.url, _TEST_UPSTREAM_AUTHORITY),
        )
        await guard.start()
        try:
            status_line = await _send_guard_request(guard.base_url)
            assert status_line.startswith(b"HTTP/1.1 502")
        finally:
            await guard.close(5)
    assert len(provider.requests) == 1


async def test_actual_sdk_tool_loop_retries_and_rebuilds_private_provider_controls(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    compilation_context = _runtime_context()
    capabilities, reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        retry_statuses=(408, 429, 500),
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            outcome = await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()

    assert outcome == generated_result()
    assert reads == [handle, handle]
    assert len(provider.requests) == 7
    assert all(
        body["provider"] == {"allow_fallbacks": False, "data_collection": "deny"}
        for _, body in provider.requests
    )
    expected_plugins = [{"id": plugin, "enabled": False} for plugin in _OPENROUTER_PLUGINS]
    assert all(body["plugins"] == expected_plugins for _, body in provider.requests)
    assert all(body["model"] == OMNICORE_MODEL for _, body in provider.requests)
    assert all(body["tools"] == _MODEL_TOOLS for _, body in provider.requests)
    for headers, _body in provider.requests:
        assert headers["authorization"] == "Bearer synthetic-omnicore-test-key"
        assert "http-referer" not in headers
        assert "x-title" not in headers
        assert "cookie" not in headers
    assert not (tmp_path / "workspace").exists()
    assert not (tmp_path / "telemetry").exists()
    assert os.environ["OPENROUTER_API_KEY"] == "synthetic-omnicore-test-key"


async def test_actual_sdk_malformed_output_is_terminal_invalid_output():
    compilation_context = _runtime_context()
    capabilities, _reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output="not-json",
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        runtime.admit_execution()
        try:
            with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
                await runtime.compile_project_guide(compilation_context, capabilities)
        finally:
            await runtime.aclose()
    assert caught.value.failure_code == "schema_invalid"
    assert len(provider.requests) == 2


async def test_actual_sdk_cancellation_closes_forward_and_runtime_lifecycle():
    compilation_context = _runtime_context()
    capabilities, _reads, handle = _capabilities(compilation_context)
    async with _SyntheticOpenRouter(
        handle=handle,
        final_output=_provider_output(),
        hang=True,
    ) as provider:
        runtime = OmniCoreAgentProjectGuideRuntime._for_test(
            compilation_context.runtime_configuration,
            upstream_url=provider.url,
        )
        assert runtime.identity == compilation_context.runtime_configuration.adapter_identity
        different_context = compilation_context.model_copy(
            update={
                "runtime_configuration": compilation_context.runtime_configuration.model_copy(
                    update={"timeout_seconds": 299}
                )
            }
        )
        with pytest.raises(ProjectAgentRuntimeConfigurationError, match="mismatch"):
            await runtime.compile_project_guide(different_context, capabilities)
        with pytest.raises(ProjectAgentRuntimeError, match="not admitted"):
            await runtime.compile_project_guide(compilation_context, capabilities)
        runtime.admit_execution()
        task = asyncio.create_task(runtime.compile_project_guide(compilation_context, capabilities))
        await asyncio.wait_for(provider.received.wait(), timeout=180)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(provider.disconnected.wait(), timeout=30)
        await runtime.aclose()
        await runtime.aclose()
        with pytest.raises(ProjectAgentRuntimeError, match="closed"):
            await runtime.compile_project_guide(compilation_context, capabilities)
