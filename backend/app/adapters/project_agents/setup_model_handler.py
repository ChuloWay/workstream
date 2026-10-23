"""Trusted setup-agent model handler with durable budget and ART custody."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Protocol

from app.adapters.project_agents.openrouter_policy import openrouter_request_options
from app.core.hashing import canonical_json_hash
from app.interfaces.setup_model_proxy import (
    SetupModelProxyReply,
    SetupModelProxyRequest,
)
from app.modules.model_usage.api import (
    CompletedSetupModelUsageEffect,
    ModelCallBudgetUnavailable,
    ModelCallEvidence,
    ModelCallUnavailable,
    ModelCallUsage,
    ModelProfileSelector,
    ObservedSetupModelUsageEffect,
    PreparedSetupModelUsageEffect,
    ProjectModelProfile,
    SetupModelOutputArtifactRequest,
    SetupModelOutputBindingRequest,
    SetupModelOutputSelector,
    SetupModelUsageSlotKey,
)

_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
_OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODEL_URL = "https://openrouter.ai/api/v1/model/{author}/{slug}"
_OPENROUTER_REQUIRED_PARAMETERS = frozenset(
    {"max_tokens", "reasoning_effort", "tool_choice", "tools", "verbosity"}
)
_OPENAI_RESPONSE_FIELDS = frozenset(
    {
        "background",
        "include",
        "input",
        "instructions",
        "max_output_tokens",
        "model",
        "parallel_tool_calls",
        "previous_response_id",
        "reasoning",
        "store",
        "stream",
        "text",
        "tool_choice",
        "tools",
        "truncation",
    }
)
_COUNT_FIELDS = frozenset(
    {
        "input",
        "instructions",
        "model",
        "parallel_tool_calls",
        "reasoning",
        "text",
        "tool_choice",
        "tools",
        "truncation",
    }
)
_OPENROUTER_CHAT_FIELDS = frozenset(
    {
        "max_tokens",
        "messages",
        "model",
        "parallel_tool_calls",
        "plugins",
        "provider",
        "reasoning_effort",
        "response_format",
        "store",
        "stream",
        "temperature",
        "tool_choice",
        "tools",
        "top_p",
        "usage",
        "verbosity",
    }
)


@dataclass(frozen=True, slots=True)
class SetupProviderResponse:
    """One fully observed provider response with exact raw JSON and usage."""

    status_code: int
    response_json: str
    provider_response_id: str
    provider_model: str
    usage: ModelCallUsage
    usable: bool = True


class SetupProviderUncertain(RuntimeError):
    """A provider dispatch may have created a paid effect."""

    def __init__(self, digest: str, provider_response_id: str | None = None) -> None:
        super().__init__("setup provider outcome is uncertain")
        self.digest = digest
        self.provider_response_id = provider_response_id


class SetupProvider(Protocol):
    """Closed provider boundary used by the trusted setup model handler."""

    async def count_input(self, body: dict[str, object]) -> int: ...

    async def dispatch(self, body_json: str) -> SetupProviderResponse: ...


class OpenAISetupProvider:
    """No-retry OpenAI Responses adapter owned only by the trusted model process."""

    def __init__(self, *, api_key: str, profile: ProjectModelProfile) -> None:
        import httpx
        from openai import AsyncOpenAI

        self._profile = profile
        self._counter = AsyncOpenAI(
            api_key=api_key,
            max_retries=0,
            timeout=profile.spec.deadline_ms / 1000.0,
        )
        self._client = httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            timeout=profile.spec.deadline_ms / 1000.0,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def count_input(self, body: dict[str, object]) -> int:
        """Use the provider's non-creating endpoint on the exact semantic input."""
        arguments = {key: value for key, value in body.items() if key in _COUNT_FIELDS}
        counted = await self._counter.responses.input_tokens.count(**arguments)
        value = getattr(counted, "input_tokens", None)
        if type(value) is not int or value < 0:
            raise ModelCallUnavailable("setup_model_input_count_unavailable")
        return value

    async def dispatch(self, body_json: str) -> SetupProviderResponse:
        """Send exactly once; every exception or non-success remains uncertain."""
        raw = b""
        try:
            async with self._client.stream(
                "POST", _OPENAI_RESPONSES_URL, content=body_json
            ) as response:
                raw = await _bounded_response_bytes(
                    response, self._profile.spec.maximum_response_bytes
                )
        except BaseException as exc:
            raise SetupProviderUncertain(
                canonical_json_hash({"outcome": "transport_error"})
            ) from exc
        try:
            if not raw:
                raise ValueError("provider response exceeds profile")
            value = json.loads(raw, parse_constant=_reject_constant)
            if not isinstance(value, dict):
                raise TypeError("provider response is invalid")
            provider_id = value.get("id")
            if not 200 <= response.status_code < 300:
                raise SetupProviderUncertain(
                    canonical_json_hash(
                        {"outcome": "provider_status", "status_code": response.status_code}
                    ),
                    provider_id if isinstance(provider_id, str) else None,
                )
            return _openai_response(self._profile, response.status_code, value)
        except SetupProviderUncertain:
            raise
        except BaseException as exc:
            provider_id = None
            try:
                candidate = json.loads(raw).get("id")
                if isinstance(candidate, str):
                    provider_id = candidate
            except (AttributeError, TypeError, ValueError, UnicodeError):
                provider_id = None
            raise SetupProviderUncertain(
                canonical_json_hash(
                    {"outcome": "invalid_response", "status_code": response.status_code}
                ),
                provider_id,
            ) from exc

    async def aclose(self) -> None:
        await self._counter.close()
        await self._client.aclose()


class OpenRouterSetupProvider:
    """No-retry OpenRouter adapter reserving its full pinned model context."""

    def __init__(self, *, api_key: str, profile: ProjectModelProfile) -> None:
        import httpx

        model_parts = profile.spec.model_snapshot.split("/")
        if len(model_parts) != 2 or not all(model_parts):
            raise ModelCallUnavailable("model_profile_provider_unavailable")
        self._profile = profile
        self._model_url = _OPENROUTER_MODEL_URL.format(
            author=model_parts[0], slug=model_parts[1]
        )
        self._client = httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            timeout=profile.spec.deadline_ms / 1000.0,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def count_input(self, _body: dict[str, object]) -> int:
        """Refresh exact model metadata, then reserve the full approved context."""
        try:
            async with self._client.stream("GET", self._model_url) as response:
                raw = await _bounded_response_bytes(response, 1_048_576)
            if not 200 <= response.status_code < 300 or not raw:
                raise ValueError("provider metadata unavailable")
            value = json.loads(raw, parse_constant=_reject_constant)
            _validate_openrouter_metadata(self._profile, value)
        except ModelCallUnavailable:
            raise
        except BaseException as exc:
            raise ModelCallUnavailable("model_profile_provider_unavailable") from exc
        return self._profile.spec.maximum_input_tokens

    async def dispatch(self, body_json: str) -> SetupProviderResponse:
        raw = b""
        try:
            async with self._client.stream(
                "POST", _OPENROUTER_CHAT_URL, content=body_json
            ) as response:
                raw = await _bounded_response_bytes(
                    response, self._profile.spec.maximum_response_bytes
                )
        except BaseException as exc:
            raise SetupProviderUncertain(
                canonical_json_hash({"outcome": "transport_error"})
            ) from exc
        try:
            if not raw:
                raise ValueError("provider response exceeds profile")
            value = json.loads(raw, parse_constant=_reject_constant)
            if not isinstance(value, dict):
                raise TypeError("provider response is invalid")
            provider_id = value.get("id")
            if not 200 <= response.status_code < 300:
                raise SetupProviderUncertain(
                    canonical_json_hash(
                        {"outcome": "provider_status", "status_code": response.status_code}
                    ),
                    provider_id if isinstance(provider_id, str) else None,
                )
            return _openrouter_response(self._profile, response.status_code, value)
        except SetupProviderUncertain:
            raise
        except BaseException as exc:
            provider_id = None
            try:
                candidate = json.loads(raw).get("id")
                if isinstance(candidate, str):
                    provider_id = candidate
            except (AttributeError, TypeError, ValueError, UnicodeError):
                provider_id = None
            raise SetupProviderUncertain(
                canonical_json_hash(
                    {"outcome": "invalid_response", "status_code": response.status_code}
                ),
                provider_id,
            ) from exc

    async def aclose(self) -> None:
        await self._client.aclose()


class SetupModelProxyHandler:
    """Persist request and reservation before exactly one trusted provider send."""

    def __init__(
        self,
        *,
        sessions,
        authorization,
        calls,
        profiles,
        outputs,
        bindings,
        provider: Callable[
            [ProjectModelProfile], AbstractAsyncContextManager[SetupProvider]
        ],
    ) -> None:
        self._sessions = sessions
        self._authorization = authorization
        self._calls = calls
        self._profiles = profiles
        self._outputs = outputs
        self._bindings = bindings
        self._provider = provider

    async def handle(self, request: SetupModelProxyRequest) -> SetupModelProxyReply:
        try:
            return await self._handle(request)
        except ModelCallBudgetUnavailable:
            return _unavailable(request, "model_budget_unavailable")
        except (ModelCallUnavailable, ValueError, TypeError):
            return _unavailable(request, "model_call_unavailable")

    async def _handle(self, request: SetupModelProxyRequest) -> SetupModelProxyReply:
        subject = request.subject
        key = SetupModelUsageSlotKey(
            compilation_attempt_id=subject.compilation_attempt_id,
            project_id=subject.project_id,
            guide_id=subject.guide_id,
            source_snapshot_id=subject.source_snapshot_id,
            setup_run_id=subject.setup_run_id,
            setup_generation=subject.setup_generation,
            runtime_configuration_hash=subject.runtime_configuration_hash,
            profile_id=subject.profile_id,
            profile_version=subject.profile_version,
            profile_digest=subject.profile_digest,
            phase=request.phase,
            call_index=request.call_index,
        )
        body = json.loads(request.provider_request_json)
        async with self._sessions() as session, session.begin():
            profile = await self._profiles(session).read_exact(
                ModelProfileSelector(
                    profile_id=subject.profile_id,
                    profile_version=subject.profile_version,
                    profile_digest=subject.profile_digest,
                ),
                project_id=subject.project_id,
            )
        _validate_request(profile, request, body)
        data = request.provider_request_json.encode("utf-8")
        request_sha = _sha(data)

        async with self._sessions() as session, session.begin():
            authority = await self._authorization(session, subject.compilation_attempt_id)
            calls = self._calls(session, authority)
            existing = await calls.recover_existing(key, request_sha)
        if isinstance(existing, ObservedSetupModelUsageEffect):
            return await self._recover_observed(request, existing, profile)
        if existing is not None:
            if existing.state != "completed":
                return _unavailable(request, "model_call_unavailable")
            return await self._cached(request, existing, profile)

        async with self._provider(profile) as provider:
            input_tokens = await provider.count_input(body)
            if input_tokens > profile.spec.maximum_input_tokens:
                raise ModelCallUnavailable("setup_model_input_limit_exceeded")
            async with self._sessions() as session, session.begin():
                authority = await self._authorization(session, subject.compilation_attempt_id)
                prepared = await self._calls(session, authority).prepare(key, request_sha)
            request_evidence = await self._store(prepared, "model_request", data)
            async with self._sessions() as session, session.begin():
                authority = await self._authorization(session, prepared.internal_call_request_id)
                dispatch = await self._calls(session, authority).reserve_dispatch(
                    prepared, request_evidence
                )
            if dispatch.replayed:
                return _unavailable(request, "model_provider_delivery_uncertain")
            try:
                response = await provider.dispatch(request.provider_request_json)
            except SetupProviderUncertain as uncertain:
                async with self._sessions() as session, session.begin():
                    authority = await self._authorization(
                        session, dispatch.internal_call_request_id
                    )
                    await self._calls(session, authority).mark_uncertain(
                        dispatch.effect,
                        uncertain.digest,
                        provider_response_id=uncertain.provider_response_id,
                    )
                return _unavailable(request, "model_provider_delivery_uncertain")
        response_data = response.response_json.encode("utf-8")
        async with self._sessions() as session, session.begin():
            authority = await self._authorization(session, dispatch.internal_call_request_id)
            await self._calls(session, authority).mark_uncertain(
                dispatch.effect,
                _sha(response_data),
                provider_response_id=response.provider_response_id,
            )
        response_evidence = await self._store(prepared, "model_response", response_data)
        async with self._sessions() as session, session.begin():
            authority = await self._authorization(session, dispatch.internal_call_request_id)
            await self._calls(session, authority).complete(
                dispatch.effect,
                provider_response_id=response.provider_response_id,
                provider_model_snapshot=response.provider_model,
                response_evidence=response_evidence,
                usage=response.usage,
                usable=response.usable,
            )
        if not response.usable:
            return _unavailable(request, "model_response_too_large")
        return _completed_reply(
            request,
            profile,
            status_code=response.status_code,
            response_json=response.response_json,
        )

    async def _recover_observed(
        self,
        request: SetupModelProxyRequest,
        observed: ObservedSetupModelUsageEffect,
        profile: ProjectModelProfile,
    ) -> SetupModelProxyReply:
        """Complete only exact response bytes already verified by ART."""
        if observed.provider_response_id is None:
            return _unavailable(request, "model_provider_delivery_uncertain")
        effect = observed.effect
        selector = SetupModelOutputSelector(
            slot_key=effect.slot_key,
            model_call_slot_id=effect.slot_id,
            model_call_attempt_id=effect.effect_id,
            role="model_response",
            content_sha256=observed.uncertainty_digest,
        )
        recovered = await self._outputs.recover_setup_output(selector)
        if (
            recovered is None
            or recovered.status != "verified"
            or recovered.content_id is None
            or recovered.verification_receipt_id is None
            or recovered.content_sha256 != selector.content_sha256
        ):
            return _unavailable(request, "model_provider_delivery_uncertain")
        async with self._sessions() as session, session.begin():
            binding = await self._bindings(session).bind_setup_output(
                SetupModelOutputBindingRequest(
                    selector,
                    recovered.put_attempt_id,
                    recovered.verification_receipt_id,
                )
            )
        evidence = ModelCallEvidence(
            binding_id=binding.binding_id,
            content_id=binding.content_id,
            put_attempt_id=binding.put_attempt_id,
            verification_receipt_id=binding.verification_receipt_id,
            content_sha256=recovered.content_sha256,
            byte_count=recovered.byte_count,
        )
        data = await self._outputs.read_setup_response(selector, evidence)
        response = _retained_provider_response(profile, data)
        if response.provider_response_id != observed.provider_response_id:
            raise ModelCallUnavailable("setup_model_recovery_identity_mismatch")
        async with self._sessions() as session, session.begin():
            authority = await self._authorization(session, effect.internal_call_request_id)
            completed = await self._calls(session, authority).complete(
                effect,
                provider_response_id=response.provider_response_id,
                provider_model_snapshot=response.provider_model,
                response_evidence=evidence,
                usage=response.usage,
                usable=response.usable,
            )
        if completed.state != "completed" or not response.usable:
            return _unavailable(request, "model_response_too_large")
        return _completed_reply(
            request,
            profile,
            status_code=response.status_code,
            response_json=response.response_json,
        )

    async def _store(
        self, prepared: PreparedSetupModelUsageEffect, role: str, data: bytes
    ) -> ModelCallEvidence:
        selector = SetupModelOutputSelector(
            slot_key=prepared.slot_key,
            model_call_slot_id=prepared.slot_id,
            model_call_attempt_id=prepared.effect_id,
            role=role,
            content_sha256=_sha(data),
        )

        async def source():
            yield data

        stored = await self._outputs.store_setup_output(
            SetupModelOutputArtifactRequest(selector, source())
        )
        if stored.status != "verified" or stored.verification_receipt_id is None:
            raise ModelCallUnavailable("setup_model_evidence_unavailable")
        async with self._sessions() as session, session.begin():
            binding = await self._bindings(session).bind_setup_output(
                SetupModelOutputBindingRequest(
                    selector,
                    stored.put_attempt_id,
                    stored.verification_receipt_id,
                )
            )
        return ModelCallEvidence(
            binding_id=binding.binding_id,
            content_id=binding.content_id,
            put_attempt_id=binding.put_attempt_id,
            verification_receipt_id=binding.verification_receipt_id,
            content_sha256=selector.content_sha256,
            byte_count=len(data),
        )

    async def _cached(
        self,
        request: SetupModelProxyRequest,
        completed: CompletedSetupModelUsageEffect,
        profile: ProjectModelProfile,
    ) -> SetupModelProxyReply:
        selector = SetupModelOutputSelector(
            slot_key=completed.effect.slot_key,
            model_call_slot_id=completed.effect.slot_id,
            model_call_attempt_id=completed.effect.effect_id,
            role="model_response",
            content_sha256=completed.response_evidence.content_sha256,
        )
        data = await self._outputs.read_setup_response(selector, completed.response_evidence)
        body = json.loads(data)
        response_json = _canonical_bytes(body).decode("utf-8")
        return _completed_reply(
            request,
            profile,
            status_code=200,
            response_json=response_json,
        )


@asynccontextmanager
async def configured_setup_provider(profile: ProjectModelProfile):
    """Construct only the closed provider/API pair supported with exact pre-counting."""
    identity = profile.spec.provider, profile.spec.api
    if identity == ("openai", "responses"):
        key_name = "OPENAI_API_KEY"
        provider_type = OpenAISetupProvider
    elif identity == ("openrouter", "chat_completions"):
        key_name = "OPENROUTER_API_KEY"
        provider_type = OpenRouterSetupProvider
    else:
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    key = os.environ.get(key_name, "")
    if not key:
        raise ModelCallUnavailable("model_provider_credentials_unavailable")
    provider = provider_type(api_key=key, profile=profile)
    try:
        yield provider
    finally:
        await provider.aclose()


def _validate_request(
    profile: ProjectModelProfile,
    request: SetupModelProxyRequest,
    body: object,
) -> None:
    subject = request.subject
    if (
        not isinstance(body, dict)
        or (profile.spec.provider, profile.spec.api, profile.spec.model_snapshot)
        != (subject.provider, subject.api, subject.model)
        or profile.spec.allowed_tools != ("read_document", "search_document")
        or body.get("model") != subject.model
        or body.get("stream", False) is not False
        or len(request.provider_request_json.encode("utf-8"))
        > profile.spec.maximum_request_bytes
        or not _safe_tools(body.get("tools"))
    ):
        raise ModelCallUnavailable("setup_model_request_invalid")
    identity = subject.provider, subject.api
    if identity == ("openai", "responses"):
        if (
            set(body) - _OPENAI_RESPONSE_FIELDS
            or body.get("background", False) is not False
            or body.get("store", False) is not False
            or body.get("previous_response_id") not in {None, ""}
            or body.get("parallel_tool_calls") is not False
            or body.get("truncation") not in {None, "disabled"}
            or body.get("include", []) != []
            or body.get("reasoning")
            != {"effort": profile.spec.settings.reasoning_effort}
            or not _safe_response_text(
                body.get("text"), profile.spec.settings.text_verbosity
            )
            or type(body.get("max_output_tokens")) is not int
            or not 1
            <= body["max_output_tokens"]
            <= profile.spec.maximum_output_tokens
        ):
            raise ModelCallUnavailable("setup_model_request_invalid")
    elif identity == ("openrouter", "chat_completions"):
        if (
            set(body) - _OPENROUTER_CHAT_FIELDS
            or type(body.get("max_tokens")) is not int
            or not 1 <= body["max_tokens"] <= profile.spec.maximum_output_tokens
            or body.get("usage") != {"include": True}
            or body.get("provider") != openrouter_request_options()["provider"]
            or body.get("plugins") != openrouter_request_options()["plugins"]
            or body.get("reasoning_effort") != profile.spec.settings.reasoning_effort
            or body.get("verbosity") != profile.spec.settings.text_verbosity
            or body.get("temperature", 0) != 0
            or body.get("top_p", 1) != 1
            or body.get("store", False) is not False
            or body.get("parallel_tool_calls", False) is not False
            or not _safe_chat_response_format(body.get("response_format"))
        ):
            raise ModelCallUnavailable("setup_model_request_invalid")
    else:
        raise ModelCallUnavailable("setup_model_request_invalid")


def _safe_tools(value: object) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return False
    names: list[str] = []
    for item in value:
        if not isinstance(item, dict) or item.get("type") != "function":
            return False
        name = item.get("name")
        if name is None and isinstance(item.get("function"), dict):
            name = item["function"].get("name")
        if not isinstance(name, str):
            return False
        names.append(name)
    return sorted(names) == ["read_document", "search_document"]


def _safe_response_text(value: object, verbosity: str) -> bool:
    if not isinstance(value, dict) or set(value) - {"format", "verbosity"}:
        return False
    output_format = value.get("format")
    return (
        value.get("verbosity") == verbosity
        and isinstance(output_format, dict)
        and output_format.get("type") == "json_schema"
        and output_format.get("strict") is True
        and isinstance(output_format.get("name"), str)
        and isinstance(output_format.get("schema"), dict)
    )


def _safe_chat_response_format(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != {"type", "json_schema"}:
        return False
    schema = value.get("json_schema")
    return (
        value.get("type") == "json_schema"
        and isinstance(schema, dict)
        and schema.get("strict") is True
        and isinstance(schema.get("name"), str)
        and isinstance(schema.get("schema"), dict)
        and not set(schema) - {"name", "strict", "schema", "description"}
    )


def _validate_openrouter_metadata(
    profile: ProjectModelProfile, value: object
) -> None:
    """Fail before spend unless current provider metadata fits the pinned profile."""
    if not isinstance(value, dict) or set(value) != {"data"}:
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    data = value["data"]
    if not isinstance(data, dict):
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    top_provider = data.get("top_provider")
    supported = data.get("supported_parameters")
    context_length = data.get("context_length")
    if (
        data.get("id") != profile.spec.model_snapshot
        or not isinstance(data.get("canonical_slug"), str)
        or not data["canonical_slug"]
        or type(context_length) is not int
        or context_length < 1
        or context_length > profile.spec.maximum_input_tokens
        or not isinstance(top_provider, dict)
        or type(top_provider.get("context_length")) is not int
        or top_provider["context_length"] != context_length
        or type(top_provider.get("max_completion_tokens")) is not int
        or not 1
        <= profile.spec.maximum_output_tokens
        <= top_provider["max_completion_tokens"]
        or not isinstance(supported, list)
        or any(type(item) is not str for item in supported)
        or not _OPENROUTER_REQUIRED_PARAMETERS.issubset(supported)
    ):
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    _validate_openrouter_pricing(profile, data.get("pricing"))


def _validate_openrouter_pricing(
    profile: ProjectModelProfile, value: object
) -> None:
    """Require pinned rates to cover every advertised tier and cache class."""
    if not isinstance(value, dict):
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    pricing_rows = [value]
    overrides = value.get("overrides", [])
    if not isinstance(overrides, list) or any(not isinstance(row, dict) for row in overrides):
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    pricing_rows.extend(overrides)
    input_ceiling = 0
    cached_ceiling = 0
    output_ceiling = 0
    for row in pricing_rows:
        _require_zero_unsupported_fees(row)
        input_ceiling = max(
            input_ceiling,
            _nanodollars(row.get("prompt")),
            _nanodollars(row.get("input_cache_write", row.get("prompt"))),
        )
        cached_ceiling = max(
            cached_ceiling,
            _nanodollars(row.get("input_cache_read", row.get("prompt"))),
        )
        output_ceiling = max(output_ceiling, _nanodollars(row.get("completion")))
    pinned = profile.spec.pricing
    if (
        input_ceiling > pinned.uncached_input_nanodollars_per_token
        or cached_ceiling > pinned.cached_input_nanodollars_per_token
        or output_ceiling > pinned.output_nanodollars_per_token
    ):
        raise ModelCallUnavailable("model_profile_provider_unavailable")


def _require_zero_unsupported_fees(row: dict) -> None:
    """Reject advertised charges the token-only ledger cannot reserve."""
    supported = {
        "prompt",
        "completion",
        "input_cache_read",
        "input_cache_write",
        "overrides",
        "min_prompt_tokens",
    }
    for key, value in row.items():
        if key not in supported and _nanodollars(value) != 0:
            raise ModelCallUnavailable("model_profile_provider_unavailable")


def _nanodollars(value: object) -> int:
    if type(value) is not str:
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise ModelCallUnavailable("model_profile_provider_unavailable") from None
    if not amount.is_finite() or amount < 0:
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    converted = (amount * Decimal(1_000_000_000)).to_integral_value(
        rounding=ROUND_CEILING
    )
    if converted > 9_000_000_000_000_000_000:
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    return int(converted)


def _openai_response(
    profile: ProjectModelProfile, status_code: int, value: dict[str, object]
) -> SetupProviderResponse:
    provider_id = value.get("id")
    provider_model = value.get("model")
    if (
        not isinstance(provider_id, str)
        or not provider_id
        or provider_model != profile.spec.model_snapshot
    ):
        raise ValueError("provider response identity is invalid")
    return SetupProviderResponse(
        status_code=status_code,
        response_json=_canonical_bytes(value).decode("utf-8"),
        provider_response_id=provider_id,
        provider_model=provider_model,
        usage=_usage(value.get("usage")),
        usable=_model_output_bytes(value) <= profile.spec.maximum_output_bytes,
    )


def _openrouter_response(
    profile: ProjectModelProfile, status_code: int, value: dict[str, object]
) -> SetupProviderResponse:
    provider_id = value.get("id")
    provider_model = value.get("model")
    if (
        not isinstance(provider_id, str)
        or not provider_id
        or provider_model != profile.spec.model_snapshot
    ):
        raise ValueError("provider response identity is invalid")
    return SetupProviderResponse(
        status_code=status_code,
        response_json=_canonical_bytes(value).decode("utf-8"),
        provider_response_id=provider_id,
        provider_model=provider_model,
        usage=_chat_usage(value.get("usage")),
        usable=_chat_output_bytes(value) <= profile.spec.maximum_output_bytes,
    )


def _retained_provider_response(
    profile: ProjectModelProfile, data: bytes
) -> SetupProviderResponse:
    """Re-validate exact retained ART bytes without another provider request."""
    try:
        value = json.loads(data, parse_constant=_reject_constant)
        if not isinstance(value, dict) or _canonical_bytes(value) != data:
            raise ValueError("retained response is not canonical")
        identity = profile.spec.provider, profile.spec.api
        if identity == ("openai", "responses"):
            return _openai_response(profile, 200, value)
        if identity == ("openrouter", "chat_completions"):
            return _openrouter_response(profile, 200, value)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ModelCallUnavailable("setup_model_recovery_response_invalid") from exc
    raise ModelCallUnavailable("model_profile_provider_unavailable")


def _usage(value: object) -> ModelCallUsage:
    if not isinstance(value, dict):
        raise TypeError("provider usage is unavailable")
    input_details = value.get("input_tokens_details") or {}
    output_details = value.get("output_tokens_details") or {}
    return ModelCallUsage(
        input_tokens=value.get("input_tokens"),
        cached_input_tokens=input_details.get("cached_tokens", 0),
        output_tokens=value.get("output_tokens"),
        reasoning_tokens=output_details.get("reasoning_tokens", 0),
    )


def _chat_usage(value: object) -> ModelCallUsage:
    if not isinstance(value, dict):
        raise TypeError("provider usage is unavailable")
    input_details = value.get("prompt_tokens_details") or {}
    output_details = value.get("completion_tokens_details") or {}
    return ModelCallUsage(
        input_tokens=value.get("prompt_tokens"),
        cached_input_tokens=input_details.get("cached_tokens", 0),
        output_tokens=value.get("completion_tokens"),
        reasoning_tokens=output_details.get("reasoning_tokens", 0),
    )


def _model_output_bytes(value: dict[str, object]) -> int:
    """Count UTF-8 model-authored text and tool arguments without response metadata."""
    output = value.get("output")
    if not isinstance(output, list):
        raise TypeError("provider output is invalid")
    total = 0
    stack: list[object] = list(output)
    while stack:
        current = stack.pop()
        if isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, dict):
            for key, item in current.items():
                if key in {"text", "refusal", "arguments"} and isinstance(item, str):
                    total += len(item.encode("utf-8"))
                elif isinstance(item, (dict, list)):
                    stack.append(item)
    return total


def _chat_output_bytes(value: dict[str, object]) -> int:
    choices = value.get("choices")
    if not isinstance(choices, list):
        raise TypeError("provider output is invalid")
    return _generated_string_bytes(choices)


def _generated_string_bytes(root: object) -> int:
    total = 0
    stack = [root]
    while stack:
        current = stack.pop()
        if isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, dict):
            for key, item in current.items():
                if key in {"content", "refusal", "arguments"} and isinstance(item, str):
                    total += len(item.encode("utf-8"))
                elif isinstance(item, (dict, list)):
                    stack.append(item)
    return total


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


async def _bounded_response_bytes(response, maximum_bytes: int) -> bytes:
    """Read a provider body without ever accumulating beyond its locked cap."""
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if not chunk:
            continue
        if len(chunk) > maximum_bytes - len(body):
            raise ValueError("provider response exceeds profile")
        body.extend(chunk)
    return bytes(body)


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite provider number")


def _unavailable(request: SetupModelProxyRequest, code: str) -> SetupModelProxyReply:
    return SetupModelProxyReply(
        outcome="unavailable",
        call_index=request.call_index,
        status_code=None,
        response_json=None,
        response_headers=(),
        failure_code=code,
        session_exhausted=True,
    )


def _completed_reply(
    request: SetupModelProxyRequest,
    profile: ProjectModelProfile,
    *,
    status_code: int,
    response_json: str,
) -> SetupModelProxyReply:
    """Return a bounded SDK reply after the caller has retained and settled it."""
    try:
        return SetupModelProxyReply(
            outcome="completed",
            call_index=request.call_index,
            status_code=status_code,
            response_json=response_json,
            response_headers=(),
            failure_code=None,
            session_exhausted=request.call_index + 1 >= profile.spec.maximum_calls,
        )
    except ValueError:
        return _unavailable(request, "model_response_too_large")


__all__ = (
    "OpenAISetupProvider",
    "SetupModelProxyHandler",
    "SetupProviderResponse",
    "SetupProviderUncertain",
    "configured_setup_provider",
)
