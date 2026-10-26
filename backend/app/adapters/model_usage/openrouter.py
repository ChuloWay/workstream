"""Shared concrete OpenRouter transport and profile-validation primitives."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
import json

from app.modules.model_usage.api import ModelCallUnavailable, ProjectModelProfile


OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODEL_URL = "https://openrouter.ai/api/v1/model/{author}/{slug}"
_OPENROUTER_REQUIRED_PARAMETERS = frozenset(
    {"max_tokens", "reasoning_effort", "tool_choice", "tools", "verbosity"}
)
_MAX_METADATA_BYTES = 1_048_576
_MAX_TOKEN_COUNT = 2**63 - 1


@dataclass(frozen=True, slots=True)
class OpenRouterUsage:
    """Complete normalized Chat Completions token counters."""

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int | None

    def __post_init__(self) -> None:
        values = (
            self.input_tokens,
            self.cached_input_tokens,
            self.output_tokens,
            self.reasoning_tokens,
        )
        if any(
            type(value) is not int or not 0 <= value <= _MAX_TOKEN_COUNT
            for value in values
        ):
            raise ValueError("OpenRouter usage is invalid")
        if self.total_tokens is not None and (
            type(self.total_tokens) is not int
            or not 0 <= self.total_tokens <= _MAX_TOKEN_COUNT
            or self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("OpenRouter usage is invalid")
        if (
            self.cached_input_tokens > self.input_tokens
            or self.reasoning_tokens > self.output_tokens
        ):
            raise ValueError("OpenRouter usage is invalid")


def require_direct_openrouter_model(model: str) -> str:
    """Reject provider-selected routing variants while preserving the exact model."""
    if not isinstance(model, str):
        raise ValueError("OpenRouter model routing is unsupported")
    normalized = model.lower()
    parts = model.split("/")
    if (
        ":" in normalized
        or normalized.startswith("openrouter/")
        or len(parts) != 2
        or not all(parts)
    ):
        raise ValueError("OpenRouter model routing is unsupported")
    return model


def openrouter_model_metadata_url(model: str) -> str:
    """Return the exact metadata endpoint for one direct author/model identity."""
    direct = require_direct_openrouter_model(model)
    model_parts = direct.split("/")
    return _OPENROUTER_MODEL_URL.format(author=model_parts[0], slug=model_parts[1])


def openrouter_request_options() -> dict[str, object]:
    """Return fixed routing and plugin controls for a direct OpenRouter request.

    Alignment currently rejects an ``enabled`` key, even when false. All account
    plugins must therefore be disabled operationally before private model use;
    enforced account settings can also override these per-request controls.
    ``data_collection=deny`` is not a zero-data-retention guarantee.
    """
    return {
        "provider": {"allow_fallbacks": False, "data_collection": "deny"},
        "plugins": [
            {"id": plugin, "enabled": False}
            for plugin in (
                "web",
                "file-parser",
                "response-healing",
                "armor",
                "pareto-router",
                "context-compression",
            )
        ],
    }


async def preflight_openrouter_profile(client, profile: ProjectModelProfile) -> int:
    """Refresh bounded metadata and reserve the profile's full input context."""
    try:
        url = openrouter_model_metadata_url(profile.spec.model_snapshot)
        async with client.stream("GET", url) as response:
            raw = await bounded_response_bytes(response, _MAX_METADATA_BYTES)
        if not 200 <= response.status_code < 300 or not raw:
            raise ValueError("provider metadata unavailable")
        value = json.loads(raw, parse_constant=_reject_constant)
        validate_openrouter_metadata(profile, value)
    except ModelCallUnavailable:
        raise
    except BaseException as exc:
        raise ModelCallUnavailable("model_profile_provider_unavailable") from exc
    return profile.spec.maximum_input_tokens


def validate_openrouter_metadata(profile: ProjectModelProfile, value: object) -> None:
    """Fail before spend unless current metadata fits the pinned profile."""
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


def openrouter_usage(value: object) -> OpenRouterUsage:
    """Decode nested Chat Completions token counters without owner-specific DTOs."""
    if not isinstance(value, dict):
        raise ValueError("OpenRouter usage is unavailable")
    input_details = value.get("prompt_tokens_details") or {}
    output_details = value.get("completion_tokens_details") or {}
    if not isinstance(input_details, dict) or not isinstance(output_details, dict):
        raise ValueError("OpenRouter usage is invalid")
    return OpenRouterUsage(
        input_tokens=value.get("prompt_tokens"),
        cached_input_tokens=input_details.get("cached_tokens", 0),
        output_tokens=value.get("completion_tokens"),
        reasoning_tokens=output_details.get("reasoning_tokens", 0),
        total_tokens=value.get("total_tokens"),
    )


def openrouter_generated_output_bytes(root: object) -> int:
    """Count bounded content, refusal and tool-argument strings recursively."""
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


async def bounded_response_bytes(response, maximum_bytes: int) -> bytes:
    """Read a provider body without accumulating beyond its locked cap."""
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if not chunk:
            continue
        if len(chunk) > maximum_bytes - len(body):
            raise ValueError("provider response exceeds profile")
        body.extend(chunk)
    return bytes(body)


def _validate_openrouter_pricing(profile: ProjectModelProfile, value: object) -> None:
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
    converted = (amount * Decimal(1_000_000_000)).to_integral_value(rounding=ROUND_CEILING)
    if converted > 9_000_000_000_000_000_000:
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    return int(converted)


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite provider number")


__all__ = (
    "OPENROUTER_CHAT_COMPLETIONS_URL",
    "OpenRouterUsage",
    "bounded_response_bytes",
    "openrouter_generated_output_bytes",
    "openrouter_model_metadata_url",
    "openrouter_request_options",
    "openrouter_usage",
    "preflight_openrouter_profile",
    "require_direct_openrouter_model",
    "validate_openrouter_metadata",
)
