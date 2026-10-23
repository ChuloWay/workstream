"""Closed effective profile for the pinned OmniCoreAgent adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.interfaces.project_agents import ProjectAgentRuntimeConfigurationError
from app.interfaces.project_guide_runtime import AdapterProfileValue


OMNICORE_RUNTIME_KEY = "omnicore_agent"
OMNICORE_PROFILE_KEY = "omnicore_agent.v1"
OMNICOREAGENT_VERSION = "0.6.0"
LITELLM_VERSION = "1.106.2"
OMNICORE_OPENAI_VERSION = "2.54.0"
OMNICORE_MODEL = "openai/gpt-5.6-terra"
OMNICORE_PROVIDER_RETRIES = 3
OMNICORE_PROVIDER_ATTEMPTS = OMNICORE_PROVIDER_RETRIES + 1
OMNICORE_MAX_TOKENS = 16_384
OMNICORE_TEMPERATURE = 0
OMNICORE_MAXIMUM_REQUEST_BYTES = 32_000_000
OMNICORE_MAXIMUM_RESPONSE_BYTES = 8_000_000
OMNICORE_MAXIMUM_HEADER_BYTES = 16_384
OMNICORE_MAXIMUM_HEADERS = 16
OMNICORE_CLEANUP_TIMEOUT_SECONDS = 10

_DEFAULTS: dict[str, AdapterProfileValue] = {
    "profile_key": OMNICORE_PROFILE_KEY,
    "omnicoreagent_version": OMNICOREAGENT_VERSION,
    "litellm_version": LITELLM_VERSION,
    "openai_sdk_version": OMNICORE_OPENAI_VERSION,
    "provider_retries": OMNICORE_PROVIDER_RETRIES,
    "provider_attempts": OMNICORE_PROVIDER_ATTEMPTS,
    "provider_fallbacks_allowed": False,
    "data_collection": "deny",
    "provider_plugin_disable_requests": True,
    "provider_plugin_profile": "openrouter_known_2026_10_23",
    "transport_profile": "closed_loopback.v1",
    "model_max_tokens": OMNICORE_MAX_TOKENS,
    "model_temperature": OMNICORE_TEMPERATURE,
    "maximum_request_bytes": OMNICORE_MAXIMUM_REQUEST_BYTES,
    "maximum_response_bytes": OMNICORE_MAXIMUM_RESPONSE_BYTES,
    "maximum_header_bytes": OMNICORE_MAXIMUM_HEADER_BYTES,
    "maximum_headers": OMNICORE_MAXIMUM_HEADERS,
    "cleanup_timeout_seconds": OMNICORE_CLEANUP_TIMEOUT_SECONDS,
    "memory_store": "in_memory",
    "workspace_files": False,
    "tool_offload": False,
    "skills": False,
    "subagents": False,
    "code_mode": False,
    "advanced_tools": False,
    "agents_md": False,
    "content_telemetry": False,
    "telemetry_export": False,
    "sdk_environment": "omnicore",
    "process_sdk_exclusive": True,
}


@dataclass(frozen=True, slots=True)
class OmniCoreAgentProfile:
    """Validated adapter-native controls recorded in the attempt snapshot."""

    maximum_request_bytes: int
    maximum_response_bytes: int
    maximum_header_bytes: int
    maximum_headers: int
    cleanup_timeout_seconds: int
    provider_retries: int
    provider_attempts: int


def build_omnicore_agent_adapter_profile(
    options: Mapping[str, object],
) -> dict[str, AdapterProfileValue]:
    """Return the one supported pinned profile and reject native option drift."""
    if not isinstance(options, Mapping) or options:
        raise ProjectAgentRuntimeConfigurationError(
            "OmniCoreAgent guide runtime accepts no runtime options"
        )
    return dict(_DEFAULTS)


def require_omnicore_agent_adapter_profile(
    values: Mapping[str, object],
) -> OmniCoreAgentProfile:
    """Validate the complete frozen profile and lightweight SDK identities."""
    if dict(values) != _DEFAULTS:
        raise ProjectAgentRuntimeConfigurationError(
            "project guide runtime adapter profile is unsupported"
        )
    try:
        import omnicoreagent
        import openai
    except ImportError:
        raise ProjectAgentRuntimeConfigurationError(
            "project guide runtime is unavailable"
        ) from None
    if (
        omnicoreagent.__version__ != OMNICOREAGENT_VERSION
        or openai.__version__ != OMNICORE_OPENAI_VERSION
    ):
        raise ProjectAgentRuntimeConfigurationError(
            "project guide runtime SDK installation does not match its profile"
        )
    return OmniCoreAgentProfile(
        maximum_request_bytes=OMNICORE_MAXIMUM_REQUEST_BYTES,
        maximum_response_bytes=OMNICORE_MAXIMUM_RESPONSE_BYTES,
        maximum_header_bytes=OMNICORE_MAXIMUM_HEADER_BYTES,
        maximum_headers=OMNICORE_MAXIMUM_HEADERS,
        cleanup_timeout_seconds=OMNICORE_CLEANUP_TIMEOUT_SECONDS,
        provider_retries=OMNICORE_PROVIDER_RETRIES,
        provider_attempts=OMNICORE_PROVIDER_ATTEMPTS,
    )
