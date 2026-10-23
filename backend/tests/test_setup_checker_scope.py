"""Setup proposes only checks and repairs strict output without granting new authority."""

import copy
import json
from types import SimpleNamespace

import pytest

from app.adapters.project_agents.compilation_draft import (
    CompilationDraftParser,
    generated_compilation_schema,
)
from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.core.project_guide_instructions import PROJECT_GUIDE_INSTRUCTIONS
from app.interfaces.project_agents import (
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    require_complete_generated_specifications,
    validate_project_guide_compilation_result,
)
from app.interfaces.project_guide_example import PROJECT_GUIDE_OUTPUT_EXAMPLE
from app.modules.projects.guide_compilation.contracts import accepted_compilation_result
from tests.projects.guide_compilation.helpers import (
    context,
    generated_result,
    ids,
    runtime_configuration,
)
from tests.test_agent_runtime import (
    _compile,
    _open_prompt_documents,
    _provider_payload,
    _sdk_result,
    model_credentials,  # noqa: F401
    scripted_workspace,  # noqa: F401
)


def _schema():
    from agents import AgentOutputSchema

    return generated_compilation_schema(
        AgentOutputSchema(ProjectGuideCompilationResult).json_schema()
    )


def test_example_is_complete_valid_and_bound_to_instructions():
    example = PROJECT_GUIDE_OUTPUT_EXAMPLE
    raw = json.dumps(example["result"])
    assert CompilationDraftParser(_schema(), 100_000).parse(raw) == example["result"]
    result = ProjectGuideCompilationResult.model_validate_json(raw)
    assert {r.check_specification.execution_mode for r in result.requirements} == {
        "bounded_pre_submit",
        "background",
    }
    compilation = context(ids())
    # Replace only synthetic source identities for context-dependent validation.
    payload = copy.deepcopy(example["result"])
    actual_ref = generated_result().requirements[0].evidence_refs[0].model_dump(mode="json")
    for requirement in payload["requirements"]:
        requirement["evidence_refs"] = [actual_ref]
    for suggestion in payload["capability_suggestions"]:
        suggestion["evidence_refs"] = [actual_ref]
    payload["agent_version"] = compilation.agent_version
    actual = ProjectGuideCompilationResult.model_validate(payload)
    require_complete_generated_specifications(compilation, actual)
    validate_project_guide_compilation_result(compilation, actual)
    assert (
        json.dumps(example, ensure_ascii=False, separators=(",", ":")) in PROJECT_GUIDE_INSTRUCTIONS
    )
    assert len(PROJECT_GUIDE_INSTRUCTIONS) <= 16_000
    assert "setup_notes" not in PROJECT_GUIDE_INSTRUCTIONS
    assert "setup_notes" not in _schema()["properties"]


@pytest.mark.parametrize(
    "disposition", ["human_review", "project_lifecycle_policy", "informational"]
)
def test_inference_cannot_return_management_classifications_but_retained_reads_survive(disposition):
    payload = _provider_payload()
    requirement = payload["requirements"][0]
    requirement.update(disposition=disposition, platform_coverage=None)
    assert CompilationDraftParser(_schema(), 100_000).parse(json.dumps(payload)) is None
    retained = ProjectGuideCompilationResult.model_validate(payload)
    original = accepted_compilation_result(retained)
    assert (
        accepted_compilation_result(
            ProjectGuideCompilationResult.model_validate(
                original.canonical_result,
            )
        )
        == original
    )
    with pytest.raises(ValueError, match="outside PRE and POST"):
        require_complete_generated_specifications(context(ids()), retained)
    manager = context(ids()).model_copy(
        update={
            "runtime_configuration": runtime_configuration().model_copy(
                update={
                    "runtime_key": "manager_authored",
                    "model_provider": "none",
                    "model_api": "none",
                    "model": "none",
                }
            ),
        }
    )
    require_complete_generated_specifications(manager, retained)


@pytest.mark.usefixtures("model_credentials", "scripted_workspace")
@pytest.mark.parametrize("phase", ["draft", "review"])
@pytest.mark.parametrize(
    "fault",
    [
        "prose",
        "duplicate",
        "extra",
        "notes",
        "lifecycle",
        "canonical",
        "source",
        "version",
    ],
)
async def test_rejected_output_gets_error_feedback_then_complete_revalidation(
    monkeypatch, phase, fault
):
    from agents import Runner

    calls = []
    marker = "private-rejected-output-781"
    bad = _provider_payload()
    if fault in {"extra", "notes"}:
        bad["setup_notes" if fault == "notes" else marker] = [marker]
    elif fault == "lifecycle":
        bad["requirements"][0].update(
            disposition="project_lifecycle_policy", platform_coverage=None
        )
    elif fault == "canonical":
        bad["submission_artifact_policy"]["required_artifacts"] = ["../private"]
    elif fault == "source":
        bad["requirements"][0]["evidence_refs"][0]["sha256"] = "sha256:" + "f" * 64
    elif fault == "version":
        bad["agent_version"] = "wrong_version"
    raw = json.dumps(bad)
    if fault == "prose":
        raw = marker + raw
    elif fault == "duplicate":
        raw = '{"status":"draft_ready",' + raw[1:]
    rejected_call = 1 if phase == "draft" else 2

    async def run(agent, prompt, **kwargs):
        calls.append(json.loads(prompt))
        await _open_prompt_documents(agent, prompt)
        if len(calls) == rejected_call:
            return SimpleNamespace(final_output=agent.output_type.validate_json(raw))
        if len(calls) == rejected_call + 1:
            errors = calls[-1]["validation_errors"]
            assert errors and len(errors) <= 20
            assert marker not in prompt and "../private" not in prompt
            assert "candidate_proposal" not in calls[-1]
        return _sdk_result(agent)

    monkeypatch.setattr(Runner, "run", run)
    assert (
        await _compile(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()), context(ids()))
        == generated_result()
    )
    assert len(calls) == 3


@pytest.mark.usefixtures("model_credentials", "scripted_workspace")
@pytest.mark.parametrize("phase", ["draft", "review"])
async def test_output_correction_exhaustion_never_returns_a_proposal(monkeypatch, phase):
    from agents import Runner

    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append(json.loads(prompt))
        await _open_prompt_documents(agent, prompt)
        if phase == "review" and len(calls) == 1:
            return _sdk_result(agent)
        return SimpleNamespace(final_output=agent.output_type.validate_json("not-json"))

    monkeypatch.setattr(Runner, "run", run)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError):
        await _compile(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()), context(ids()))
    assert len(calls) == (3 if phase == "draft" else 4)


@pytest.mark.usefixtures("model_credentials", "scripted_workspace")
async def test_draft_and_review_share_two_corrections(monkeypatch):
    """A draft repair cannot grant the review a new correction allowance."""
    from agents import Runner

    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append(json.loads(prompt))
        await _open_prompt_documents(agent, prompt)
        if len(calls) == 2:
            return _sdk_result(agent)
        return SimpleNamespace(final_output=agent.output_type.validate_json("not-json"))

    monkeypatch.setattr(Runner, "run", run)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError):
        await _compile(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()), context(ids()))
    assert len(calls) == 4
    assert calls[1]["phase"] == "checker_specification"
    assert calls[2]["phase"] == calls[3]["phase"] == "coverage_review"


@pytest.mark.usefixtures("model_credentials", "scripted_workspace")
async def test_corrections_cannot_reset_model_turn_budget(monkeypatch):
    """Count actual model-boundary calls, including a rejected completed output."""
    from agents import OpenAIResponsesModel, Runner

    turns = []
    phases = []

    async def response(self, *args, **kwargs):
        turns.append(1)
        return SimpleNamespace(output=[])

    async def run(agent, prompt, **kwargs):
        phases.append(kwargs["max_turns"])
        await _open_prompt_documents(agent, prompt)
        for _ in range(2):
            await agent.model.get_response(
                agent.instructions,
                [],
                agent.model_settings,
                agent.tools,
                agent.output_type,
                [],
                None,
            )
        return SimpleNamespace(final_output=agent.output_type.validate_json("not-json"))

    monkeypatch.setattr(OpenAIResponsesModel, "get_response", response)
    monkeypatch.setattr(Runner, "run", run)
    config = runtime_configuration().model_copy(update={"maximum_turns": 4})
    compilation = context(ids()).model_copy(update={"runtime_configuration": config})
    with pytest.raises(ProjectGuideCompilationInvalidOutputError):
        await _compile(OpenAIAgentSdkProjectGuideRuntime(config), compilation)
    assert len(turns) == 2
    assert phases == [2]
