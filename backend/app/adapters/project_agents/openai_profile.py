"""Closed effective profile for the pinned OpenAI Agents SDK adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from app.interfaces.project_agents import ProjectAgentRuntimeConfigurationError
from app.interfaces.project_guide_runtime import AdapterProfileValue


OPENAI_AGENTS_PROFILE_KEY = "openai_agents_sdk.v1"
OPENAI_AGENTS_SDK_VERSION = "0.24.0"
OPENAI_SDK_VERSION = "3.37.0"

_DEFAULTS: dict[str, AdapterProfileValue] = {
    "profile_key": OPENAI_AGENTS_PROFILE_KEY,
    "agents_sdk_version": OPENAI_AGENTS_SDK_VERSION,
    "openai_sdk_version": OPENAI_SDK_VERSION,
    "request_timeout_seconds": 300,
    "maximum_retries": 2,
    "retry_backoff_multiplier": 2,
    "retry_jitter": True,
    "retry_initial_delay_seconds": 1,
    "retry_max_delay_seconds": 30,
    "circuit_failure_threshold": 3,
    "circuit_cooldown_seconds": 60,
    "store": False,
    "tracing_disabled": True,
    "provider_fallbacks_allowed": False,
    "data_collection": "deny",
}
_CONFIGURABLE = frozenset(
    {
        "request_timeout_seconds",
        "maximum_retries",
        "retry_backoff_multiplier",
        "retry_jitter",
        "retry_initial_delay_seconds",
        "retry_max_delay_seconds",
        "circuit_failure_threshold",
        "circuit_cooldown_seconds",
    }
)


@dataclass(frozen=True, slots=True)
class OpenAIAgentsSdkProfile:
    """Validated adapter-native controls recorded in the attempt snapshot."""

    request_timeout_seconds: int
    maximum_retries: int
    retry_backoff_multiplier: int
    retry_jitter: bool
    retry_initial_delay_seconds: int
    retry_max_delay_seconds: int
    circuit_failure_threshold: int
    circuit_cooldown_seconds: int


def build_openai_agents_sdk_adapter_profile(
    options: Mapping[str, object],
) -> dict[str, AdapterProfileValue]:
    """Fill pinned defaults and reject every unsupported native option."""
    if not isinstance(options, Mapping) or any(key not in _CONFIGURABLE for key in options):
        raise ProjectAgentRuntimeConfigurationError(
            "project guide runtime options are unsupported"
        )
    values = dict(_DEFAULTS)
    values.update(options)
    _validated_profile(values)
    return values


def require_openai_agents_sdk_adapter_profile(
    values: Mapping[str, object],
) -> OpenAIAgentsSdkProfile:
    """Validate the complete frozen profile and the installed SDK pair."""
    profile = _validated_profile(values)
    try:
        installed_agents = version("openai-agents")
        installed_openai = version("openai")
    except PackageNotFoundError:
        raise ProjectAgentRuntimeConfigurationError(
            "project guide runtime is unavailable"
        ) from None
    if (installed_agents, installed_openai) != (
        OPENAI_AGENTS_SDK_VERSION,
        OPENAI_SDK_VERSION,
    ):
        raise ProjectAgentRuntimeConfigurationError(
            "project guide runtime SDK installation does not match its profile"
        )
    return profile


def _validated_profile(values: Mapping[str, object]) -> OpenAIAgentsSdkProfile:
    if set(values) != set(_DEFAULTS):
        raise ProjectAgentRuntimeConfigurationError(
            "project guide runtime adapter profile is unsupported"
        )
    fixed = set(_DEFAULTS) - _CONFIGURABLE
    if any(values[name] != _DEFAULTS[name] for name in fixed):
        raise ProjectAgentRuntimeConfigurationError(
            "project guide runtime adapter profile is unsupported"
        )
    integer_bounds = {
        "request_timeout_seconds": (1, 1800),
        "maximum_retries": (0, 5),
        "retry_backoff_multiplier": (1, 4),
        "retry_initial_delay_seconds": (1, 30),
        "retry_max_delay_seconds": (1, 120),
        "circuit_failure_threshold": (1, 20),
        "circuit_cooldown_seconds": (1, 600),
    }
    for name, (minimum, maximum) in integer_bounds.items():
        value = values[name]
        if type(value) is not int or not minimum <= value <= maximum:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime adapter profile is invalid"
            )
    if type(values["retry_jitter"]) is not bool:
        raise ProjectAgentRuntimeConfigurationError(
            "project guide runtime adapter profile is invalid"
        )
    if values["retry_initial_delay_seconds"] > values["retry_max_delay_seconds"]:
        raise ProjectAgentRuntimeConfigurationError(
            "project guide runtime adapter profile is invalid"
        )
    return OpenAIAgentsSdkProfile(
        request_timeout_seconds=values["request_timeout_seconds"],
        maximum_retries=values["maximum_retries"],
        retry_backoff_multiplier=values["retry_backoff_multiplier"],
        retry_jitter=values["retry_jitter"],
        retry_initial_delay_seconds=values["retry_initial_delay_seconds"],
        retry_max_delay_seconds=values["retry_max_delay_seconds"],
        circuit_failure_threshold=values["circuit_failure_threshold"],
        circuit_cooldown_seconds=values["circuit_cooldown_seconds"],
    )
