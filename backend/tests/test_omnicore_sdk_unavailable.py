"""Failure boundary for selecting OmniCoreAgent outside its isolated SDK environment."""

from __future__ import annotations

import pytest

from app.adapters.project_agents import build_project_guide_adapter_profile
from app.adapters.project_agents.omnicore_profile import (
    build_omnicore_agent_adapter_profile,
    require_omnicore_agent_adapter_profile,
)
from app.interfaces.project_agents import ProjectAgentRuntimeConfigurationError


def test_omnicore_profile_rejects_agents_sdk_environment() -> None:
    """Fail before dispatch when the mutually exclusive Omni SDK is unavailable."""
    with pytest.raises(
        ProjectAgentRuntimeConfigurationError,
        match="^project guide runtime is unavailable$",
    ):
        require_omnicore_agent_adapter_profile(build_omnicore_agent_adapter_profile({}))


def test_omnicore_profile_is_statically_registered_without_importing_its_sdk() -> None:
    profile = build_project_guide_adapter_profile("omnicore_agent", {})
    assert profile["sdk_environment"] == "omnicore"
    assert profile["process_sdk_exclusive"] is True
