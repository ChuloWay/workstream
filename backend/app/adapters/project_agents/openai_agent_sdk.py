"""OpenAI Agents SDK implementation of the single guide-compilation port."""

from __future__ import annotations

import asyncio
import os
from typing import Literal

from pydantic import ValidationError

from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.interfaces.project_agents import (
    ProjectAgentRuntimeConfigurationError,
    ProjectAgentRuntimeError,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    project_guide_compilation_prompt_bytes,
    require_complete_project_guide_compilation_result,
    validate_project_guide_compilation_result,
)


class OpenAIAgentSdkProjectGuideRuntime:
    """Execute a configured, tool-free structured run without SDK leakage."""

    def __init__(self, configuration: ProjectGuideRuntimeConfiguration) -> None:
        """Validate the installed adapter and credentials before the dispatch fence."""
        if configuration.runtime_key != "openai_agents_sdk":
            raise ProjectAgentRuntimeConfigurationError("project guide runtime is unsupported")
        try:
            import agents  # noqa: F401
            import openai  # noqa: F401
        except ImportError:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime is unavailable"
            ) from None
        if not os.environ.get("OPENAI_API_KEY"):
            raise ProjectAgentRuntimeConfigurationError(
                "project guide model credentials are unavailable"
            )
        self._configuration = configuration

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Expose the immutable identity checked by the shared factory."""
        return self._configuration.adapter_identity

    async def compile_project_guide(
        self,
        context: ProjectGuideCompilationContext,
    ) -> ProjectGuideCompilationResult:
        """Run one exact attempt with its recorded model and instruction configuration."""
        if context.runtime_configuration != self._configuration:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime configuration mismatch"
            )
        prompt = project_guide_compilation_prompt_bytes(context)
        if len(prompt) > self._configuration.maximum_prompt_bytes:
            raise ProjectAgentRuntimeError("project guide prompt exceeds configured size limit")
        try:
            output = await asyncio.wait_for(
                self._run(context, prompt.decode("utf-8")),
                timeout=self._configuration.timeout_seconds,
            )
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise
            raise ProjectAgentRuntimeError("project guide run cancelled") from None
        except TimeoutError:
            raise ProjectAgentRuntimeError("project guide run timed out") from None
        except ProjectGuideCompilationInvalidOutputError:
            raise
        except Exception:
            raise ProjectAgentRuntimeError("project guide run failed") from None
        try:
            if isinstance(output, ProjectGuideCompilationResult):
                result = output
            elif isinstance(output, str):
                result = ProjectGuideCompilationResult.model_validate_json(output)
            else:
                result = ProjectGuideCompilationResult.model_validate(output)
            require_complete_project_guide_compilation_result(result)
            validate_project_guide_compilation_result(context, result)
            if result.agent_version != context.agent_version:
                raise ValueError("compilation result agent version is invalid")
            return result
        except (TypeError, ValueError) as exc:
            raise ProjectGuideCompilationInvalidOutputError(
                _invalid_compilation_failure_code(exc)
            ) from None

    async def _run(self, context: ProjectGuideCompilationContext, prompt: str):
        """Keep client creation, provider protocol and SDK execution inside the adapter."""
        from agents import (
            Agent,
            AgentOutputSchema,
            OpenAIChatCompletionsModel,
            OpenAIResponsesModel,
            RunConfig,
            Runner,
        )
        from agents.exceptions import ModelBehaviorError
        from openai import AsyncOpenAI

        class CompilationOutputSchema(AgentOutputSchema):
            """Translate rejection at the SDK parser boundary, even with redacted errors."""

            def validate_json(self, json_str: str):
                """Use the SDK parser; never infer failure type from provider error text."""
                try:
                    return super().validate_json(json_str)
                except ModelBehaviorError:
                    raise ProjectGuideCompilationInvalidOutputError("schema_invalid") from None

        configuration = self._configuration
        async with AsyncOpenAI(
            base_url=configuration.model_endpoint or "https://api.openai.com/v1",
            max_retries=0,
        ) as client:
            model_type = (
                OpenAIResponsesModel
                if configuration.model_api == "responses"
                else OpenAIChatCompletionsModel
            )
            agent = Agent(
                name="ProjectGuideCompilationAgent",
                instructions=configuration.instructions,
                model=model_type(model=configuration.model, openai_client=client),
                output_type=CompilationOutputSchema(
                    ProjectGuideCompilationResult, strict_json_schema=True
                ),
                tools=[],
                handoffs=[],
            )
            result = await Runner.run(
                agent,
                prompt,
                max_turns=1,
                run_config=RunConfig(tracing_disabled=True, trace_include_sensitive_data=False),
            )
            return result.final_output


def _invalid_compilation_failure_code(
    error: TypeError | ValueError,
) -> Literal["schema_invalid", "unsafe_text"]:
    """Classify only a proven unsafe-text validation without exposing output."""
    if isinstance(error, ValidationError):
        for item in error.errors(include_url=False, include_input=False):
            context = item.get("ctx") or {}
            cause = context.get("error")
            if isinstance(cause, ValueError) and str(cause) == "model-produced text is unsafe":
                return "unsafe_text"
    if str(error) == "model-produced text is unsafe":
        return "unsafe_text"
    return "schema_invalid"
