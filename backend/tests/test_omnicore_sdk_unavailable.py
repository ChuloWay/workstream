"""Failure boundary for selecting OmniCoreAgent outside its isolated SDK environment."""

from __future__ import annotations

import pytest

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
        require_omnicore_agent_adapter_profile(
            build_omnicore_agent_adapter_profile({})
        )
