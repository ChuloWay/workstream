"""One attempt budget must cover candidate generation and coverage review together."""

from types import SimpleNamespace
import json

import pytest

from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.interfaces.project_agents import ProjectAgentRuntimeError
from tests.projects.guide_compilation.helpers import (
    generated_result,
    runtime_configuration,
)
from tests.test_agent_runtime import _compile, _open_prompt_documents, _sdk_result
from tests.projects.guide_compilation.test_correction_context import correction_context


@pytest.mark.parametrize("boundary", ["model_turns", "tool_calls", "within_budget"])
async def test_coverage_review_cannot_reset_the_attempt_work_budget(monkeypatch, boundary):
    """Even a runner overrunning its phase allowance cannot make an extra provider call."""
    from agents import OpenAIResponsesModel, Runner

    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    responses = []
    phases = []
    config = runtime_configuration().model_copy(
        update={
            "maximum_turns": 6 if boundary == "model_turns" else 10,
            "maximum_tool_calls": 1 if boundary == "tool_calls" else 8,
        }
    )

    async def response(self, *args, **kwargs):
        responses.append(self)
        return SimpleNamespace(output=[SimpleNamespace(type="message")])

    monkeypatch.setattr(OpenAIResponsesModel, "get_response", response)

    async def run(agent, prompt, **kwargs):
        inputs = json.loads(prompt)
        guide_context = inputs.get("guide_setup_context", inputs)
        assert guide_context[
            "correction_predecessor"
        ] == compilation.correction_predecessor.model_dump(mode="json")
        await _open_prompt_documents(agent, prompt)
        phases.append(kwargs["max_turns"])
        # Candidate uses three turns. The review tries four more, irrespective of
        # the SDK phase limit, to exercise the adapter's independent shared fence.
        for _ in range(3 if len(phases) == 1 else 4):
            await agent.model.get_response(
                agent.instructions,
                [],
                agent.model_settings,
                agent.tools,
                agent.output_type,
                [],
                None,
            )
        return _sdk_result(agent, generated_result())

    monkeypatch.setattr(Runner, "run", run)
    runtime = OpenAIAgentSdkProjectGuideRuntime(config)
    compilation = correction_context().model_copy(update={"runtime_configuration": config})
    if boundary == "within_budget":
        assert await _compile(runtime, compilation) == generated_result()
    else:
        with pytest.raises(ProjectAgentRuntimeError, match="project guide run failed"):
            await _compile(runtime, compilation)
    assert phases == (
        [config.maximum_turns // 2]
        if boundary == "tool_calls"
        else [config.maximum_turns // 2, config.maximum_turns - 3]
    )
    assert len(responses) == {"model_turns": 6, "tool_calls": 3, "within_budget": 7}[boundary]
    assert all(model is responses[0] for model in responses)


async def test_oversize_predecessor_is_rejected_before_provider_execution(monkeypatch):
    """The authenticated body counts towards the actual provider prompt bound."""
    from app.interfaces.project_agents import project_guide_compilation_prompt_bytes

    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    compilation = correction_context()
    prompt = json.loads(project_guide_compilation_prompt_bytes(compilation))
    del prompt["correction_predecessor"]
    previous_size = len(
        json.dumps(prompt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )
    config = compilation.runtime_configuration.model_copy(
        update={"maximum_manifest_bytes": previous_size}
    )
    compilation = compilation.model_copy(update={"runtime_configuration": config})
    runtime = OpenAIAgentSdkProjectGuideRuntime(config)

    async def forbidden(*args):
        pytest.fail("oversize correction reached provider execution")

    monkeypatch.setattr(runtime, "_run", forbidden)
    with pytest.raises(ProjectAgentRuntimeError, match="prompt exceeds"):
        await _compile(runtime, compilation)
