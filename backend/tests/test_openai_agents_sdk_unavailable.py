"""Failure boundary for selecting OpenAI Agents outside its SDK image."""

import pytest

from app.adapters.project_agents.openai_profile import (
    build_openai_agents_sdk_adapter_profile,
    require_openai_agents_sdk_adapter_profile,
)
from app.interfaces.project_agents import ProjectAgentRuntimeConfigurationError


def test_openai_agents_profile_rejects_omnicore_sdk_environment() -> None:
    with pytest.raises(
        ProjectAgentRuntimeConfigurationError,
        match="^project guide runtime is unavailable$",
    ):
        require_openai_agents_sdk_adapter_profile(
            build_openai_agents_sdk_adapter_profile({})
        )
