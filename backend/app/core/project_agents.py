"""Explicit composition of independently configured guide-agent runtimes."""

from __future__ import annotations

import hashlib

from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.core.config import Settings
from app.core.project_guide_instructions import PROJECT_GUIDE_INSTRUCTIONS
from app.interfaces.external_services import ExternalServiceAdapterFactory
from app.interfaces.project_agents import ProjectGuideAgentRuntime
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration


def project_guide_runtime_configuration(settings: Settings) -> ProjectGuideRuntimeConfiguration:
    """Snapshot trusted settings without constructing a provider or copying secrets."""
    instructions = (
        PROJECT_GUIDE_INSTRUCTIONS
        if settings.project_agent_instructions is None
        else settings.project_agent_instructions
    )
    return ProjectGuideRuntimeConfiguration(
        runtime_key=settings.project_agent_runtime,
        model_provider=settings.project_agent_model_provider,
        model=settings.project_agent_model,
        model_api=settings.project_agent_model_api,
        model_endpoint=settings.project_agent_model_endpoint,
        instruction_version=settings.project_agent_instruction_version,
        instructions=instructions,
        instructions_sha256="sha256:" + hashlib.sha256(instructions.encode("utf-8")).hexdigest(),
        timeout_seconds=settings.project_agent_run_timeout_seconds,
        maximum_prompt_bytes=settings.project_agent_max_prompt_bytes,
    )


def create_project_guide_runtime(
    configuration: ProjectGuideRuntimeConfiguration,
) -> ProjectGuideAgentRuntime:
    """Construct only the explicitly registered runtime chosen by this attempt."""
    factory = ExternalServiceAdapterFactory[ProjectGuideAgentRuntime]("project_guide_compilation")
    factory.register("openai_agents_sdk", lambda: OpenAIAgentSdkProjectGuideRuntime(configuration))
    return factory.create(configuration.runtime_key)
