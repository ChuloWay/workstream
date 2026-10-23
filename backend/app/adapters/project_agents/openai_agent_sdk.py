"""OpenAI Agents SDK guide runtime using trusted local document tools only."""

from __future__ import annotations

import asyncio
import json
import os

from app.adapters.project_agents.compilation_draft import (
    CompilationDraftParser,
    generated_compilation_schema,
    contextual_output_issue,
)
from app.adapters.project_agents.openai_profile import (
    require_openai_agents_sdk_adapter_profile,
)
from app.adapters.project_agents.provider_resilience import (
    ModelCircuitAdmission,
    model_retry_settings,
    transient_provider_failure,
)
from app.adapters.project_agents.result_validation import (
    require_result_sources_opened,
    validate_project_guide_runtime_result,
)
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.interfaces.project_agents import (
    ProjectAgentRuntimeConfigurationError,
    ProjectAgentRuntimeError,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    invalid_compilation_failure_code,
    project_guide_compilation_prompt_bytes,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from .openrouter_policy import openrouter_request_options, require_direct_openrouter_model
from app.modules.projects.api.guide_documents import GuideRuntimeCapabilities


_INVALID_SCHEMA_OUTPUT = object()
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_OPENAI_BASE_URL = "https://api.openai.com/v1"



class OpenAIAgentSdkProjectGuideRuntime:
    """Run the pinned SDK with no provider custody, remote tools or persistent session."""

    def __init__(self, configuration: ProjectGuideRuntimeConfiguration) -> None:
        """Validate the installed adapter, effective profile and trusted credential."""
        if configuration.runtime_key != "openai_agents_sdk" or not configuration.uses_inference:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime is unsupported"
            )
        if configuration.maximum_turns < 2:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime requires draft and review turns"
            )
        self._provider = _provider_configuration(configuration)
        self._profile = require_openai_agents_sdk_adapter_profile(
            configuration.adapter_profile_values()
        )
        try:
            import agents  # noqa: F401
            import openai  # noqa: F401
        except ImportError:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime is unavailable"
            ) from None
        self._configuration = configuration
        self._admission: ModelCircuitAdmission | None = None

    def admit_execution(self) -> None:
        """Acquire one process-local provider lease before the product dispatch fence."""
        if self._admission is not None:
            raise ProjectAgentRuntimeError(
                "project guide runtime admission already acquired"
            )
        self._admission = ModelCircuitAdmission(self._configuration, self._profile)

    async def aclose(self) -> None:
        """Release pre-fence admission after completion, cancellation, or a lost fence."""
        if self._admission is not None:
            self._admission.close()

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Expose the immutable identity checked by the shared factory."""
        return self._configuration.adapter_identity

    async def compile_project_guide(
        self,
        context: ProjectGuideCompilationContext,
        capabilities: GuideRuntimeCapabilities,
    ) -> ProjectGuideCompilationResult:
        """Run one exact attempt with its recorded model and instruction configuration."""
        if context.runtime_configuration != self._configuration:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime configuration mismatch"
            )
        if self._admission is None:
            raise ProjectAgentRuntimeError("project guide runtime was not admitted")
        prompt = project_guide_compilation_prompt_bytes(context)
        if len(prompt) > self._configuration.maximum_manifest_bytes:
            raise ProjectAgentRuntimeError(
                "project guide prompt exceeds configured size limit"
            )
        runtime_failure = None
        invalid_failure = None
        output = None
        try:
            output = await asyncio.wait_for(
                self._run(context, prompt.decode("utf-8"), capabilities),
                timeout=self._configuration.timeout_seconds,
            )
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise
            runtime_failure = "project guide run cancelled"
        except TimeoutError:
            runtime_failure = "project guide run timed out"
        except ProjectGuideCompilationInvalidOutputError as error:
            invalid_failure = error.failure_code
        except Exception:
            runtime_failure = "project guide run failed"
        if runtime_failure is not None:
            raise ProjectAgentRuntimeError(runtime_failure) from None
        if invalid_failure is not None:
            raise ProjectGuideCompilationInvalidOutputError(invalid_failure) from None
        if output is _INVALID_SCHEMA_OUTPUT:
            raise ProjectGuideCompilationInvalidOutputError("schema_invalid") from None
        try:
            opened = await capabilities.tools.opened_handles()
            return validate_project_guide_runtime_result(context, output, opened)
        except (TypeError, ValueError) as error:
            invalid_failure = invalid_compilation_failure_code(error)
        output = None
        raise ProjectGuideCompilationInvalidOutputError(invalid_failure) from None

    async def _run(
        self,
        context: ProjectGuideCompilationContext,
        prompt: str,
        capabilities: GuideRuntimeCapabilities,
    ):
        """Keep SDK parsing, local tool execution and model requests inside the adapter."""
        from agents import (
            Agent,
            AgentOutputSchema,
            ModelSettings,
            OpenAIChatCompletionsModel,
            OpenAIResponsesModel,
            RunConfig,
            Runner,
            function_tool,
        )
        from agents.exceptions import ModelBehaviorError
        from openai import AsyncOpenAI, DefaultAsyncHttpx2Client

        configuration = self._configuration
        profile = self._profile
        admission = self._admission
        assert admission is not None

        phase_opened: set[str] = set()

        class RejectedOutput(ModelBehaviorError):
            """A completed response failed trusted checks; only safe diagnostics survive."""

            def __init__(self, issues):
                super().__init__("Guide output rejected by validation")
                self.issues = issues

        class CompilationOutputSchema(AgentOutputSchema):
            """Expose and enforce the same restricted schema in both inference phases."""

            def __init__(self, *, draft=False):
                super().__init__(ProjectGuideCompilationResult, strict_json_schema=True)
                self.draft = draft
                self.schema = generated_compilation_schema(super().json_schema())
                self.parser = CompilationDraftParser(
                    self.schema,
                    configuration.maximum_manifest_bytes,
                )

            def json_schema(self):
                return self.schema

            def validate_json(self, json_str: str):
                candidate = self.parser.parse(json_str)
                json_str = None
                if candidate is None:
                    raise RejectedOutput(self.parser.issues) from None
                issues = self.parser.canonical_issues(candidate)
                if not issues:
                    try:
                        result = ProjectGuideCompilationResult.model_validate(candidate)
                        validate_project_guide_runtime_result(context, result, phase_opened)
                    except (TypeError, ValueError) as error:
                        issues = [contextual_output_issue(error)]
                if issues:
                    candidate = None
                    raise RejectedOutput(issues) from None
                return candidate if self.draft else result

        canonical_schema = CompilationOutputSchema()
        draft_schema = CompilationOutputSchema(draft=True)

        base_model_class = (
            OpenAIChatCompletionsModel
            if configuration.model_api == "chat_completions"
            else OpenAIResponsesModel
        )

        class BoundedModel(base_model_class):
            """Count logical model turns and bind circuit state around native retries."""

            model_turns = 0

            async def get_response(
                self,
                system_instructions,
                input,
                model_settings,
                tools,
                output_schema,
                handoffs,
                tracing,
                previous_response_id=None,
                conversation_id=None,
                prompt=None,
            ):
                if (
                    self.model_turns >= configuration.maximum_turns
                    or previous_response_id is not None
                    or conversation_id is not None
                ):
                    raise RuntimeError("guide runtime work boundary exceeded")
                admission.before_request()
                self.model_turns += 1
                try:
                    response = await super().get_response(
                        system_instructions,
                        input,
                        model_settings,
                        tools,
                        output_schema,
                        handoffs,
                        tracing,
                        previous_response_id=None,
                        conversation_id=None,
                        prompt=prompt,
                    )
                except Exception as error:
                    admission.request_failed(transient_provider_failure(error))
                    raise
                admission.request_succeeded()
                return response

        http_client = DefaultAsyncHttpx2Client(
            trust_env=False,
            follow_redirects=False,
        )
        client = AsyncOpenAI(
            api_key=self._provider.api_key,
            base_url=self._provider.base_url,
            http_client=http_client,
            max_retries=0,
            timeout=profile.request_timeout_seconds,
        )
        try:
            if configuration.model_api == "chat_completions":
                model = BoundedModel(
                    model=configuration.model,
                    openai_client=client,
                    strict_feature_validation=True,
                )
            else:
                model = BoundedModel(model=configuration.model, openai_client=client)

            @function_tool(failure_error_function=None)
            async def read_document(
                handle: str, offset: int = 0, limit: int = 16000
            ) -> str:
                """Read bounded text from an assigned original using its exact opaque handle."""
                value = await capabilities.tools.read_document(
                    handle,
                    offset=offset,
                    limit=limit,
                )
                # Audit access alone is not proof that this phase observed an original.
                if offset == 0 and (value.text or value.total_characters == 0):
                    phase_opened.add(handle)
                return value.model_dump_json()

            @function_tool(failure_error_function=None)
            async def search_document(
                handle: str, query: str, offset: int = 0, limit: int = 20
            ) -> str:
                """Search bounded text in an assigned original using its exact opaque handle."""
                value = await capabilities.tools.search_document(
                    handle,
                    query,
                    offset=offset,
                    limit=limit,
                )
                return value.model_dump_json()

            extra_body = None
            if configuration.model_provider == "openrouter":
                extra_body = openrouter_request_options()
            model_settings = ModelSettings(
                parallel_tool_calls=False,
                store=False,
                timeout=profile.request_timeout_seconds,
                retry=model_retry_settings(profile),
                extra_body=extra_body,
            )
            agent = Agent(
                name="ProjectGuideCompilationAgent",
                instructions=configuration.instructions,
                model=model,
                model_settings=model_settings,
                output_type=draft_schema,
                tools=[read_document, search_document],
                handoffs=[],
            )
            run_config = RunConfig(
                tracing_disabled=True,
                trace_include_sensitive_data=False,
            )
            corrections = 0

            async def run_phase(phase, phase_prompt, turn_limit):
                """Correct known invalid responses without replaying uncertain requests."""
                nonlocal corrections
                while True:
                    remaining = turn_limit - agent.model.model_turns
                    if remaining <= 0:
                        raise ProjectGuideCompilationInvalidOutputError("schema_invalid")
                    phase_opened.clear()
                    issues = None
                    try:
                        response = await Runner.run(
                            agent,
                            phase_prompt,
                            max_turns=remaining,
                            run_config=run_config,
                        )
                    except RejectedOutput as error:
                        issues = error.issues
                    else:
                        return response.final_output
                    if corrections >= 2:
                        raise ProjectGuideCompilationInvalidOutputError("schema_invalid")
                    corrections += 1
                    phase_prompt = json.dumps(
                        {
                            "phase": phase,
                            "guide_setup_context": json.loads(prompt),
                            "validation_errors": issues,
                            "correction_instruction": (
                                "The previous completed output was rejected. Reopen the assigned "
                                "originals and return a complete corrected JSON proposal matching "
                                "the schema, source identities, enabled capabilities and PRE/POST scope."
                            ),
                        },
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    )
                    if len(phase_prompt.encode("utf-8")) > configuration.maximum_manifest_bytes:
                        raise ProjectGuideCompilationInvalidOutputError("schema_invalid")

            candidate = await run_phase(
                "checker_specification",
                prompt,
                configuration.maximum_turns // 2,
            )
            if not isinstance(candidate, dict):
                return _INVALID_SCHEMA_OUTPUT
            review_input = json.dumps(
                {
                    "phase": "coverage_review",
                    "guide_setup_context": json.loads(prompt),
                    "candidate_proposal": candidate,
                    "candidate_validation_issues": [],
                },
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            candidate = None
            if len(review_input.encode("utf-8")) > configuration.maximum_manifest_bytes:
                raise ProjectGuideCompilationInvalidOutputError("schema_invalid")
            agent.output_type = canonical_schema
            result = await run_phase(
                "coverage_review",
                review_input,
                configuration.maximum_turns,
            )
            try:
                require_result_sources_opened(context, result, phase_opened)
            except ValueError:
                raise ProjectGuideCompilationInvalidOutputError("schema_invalid") from None
            return result
        finally:
            await client.close()


class _ProviderConfiguration:
    __slots__ = ("api_key", "base_url")

    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url


def _provider_configuration(
    configuration: ProjectGuideRuntimeConfiguration,
) -> _ProviderConfiguration:
    if (
        configuration.model_provider == "openrouter"
        and configuration.model_api == "chat_completions"
    ):
        require_direct_openrouter_model(configuration.model)
        credential_name = "OPENROUTER_API_KEY"
        base_url = _OPENROUTER_BASE_URL
    elif configuration.model_provider == "openai" and configuration.model_api in {
        "responses",
        "chat_completions",
    }:
        credential_name = "OPENAI_API_KEY"
        base_url = _OPENAI_BASE_URL
    else:
        raise ProjectAgentRuntimeConfigurationError(
            "project guide model provider or protocol is unsupported"
        )
    api_key = os.environ.get(credential_name)
    if not api_key:
        raise ProjectAgentRuntimeConfigurationError(
            "project guide model credentials are unavailable"
        )
    return _ProviderConfiguration(api_key, base_url)
