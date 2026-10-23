"""Invalid drafts are rejected; bounded corrections must pass source review."""

import json
from types import SimpleNamespace

import pytest

from app.adapters.project_agents.compilation_draft import (
    CompilationDraftParser,
    generated_compilation_schema,
)
from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.interfaces.project_agents import (
    ProjectAgentRuntimeError,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
)
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
    _provider_specification,
    model_credentials,  # noqa: F401
)


@pytest.fixture
def parser():
    """Use the exact strict schema the SDK exposes to both provider phases."""
    from agents import AgentOutputSchema

    return CompilationDraftParser(
        generated_compilation_schema(
            AgentOutputSchema(ProjectGuideCompilationResult).json_schema()
        ),
        100_000,
    )


@pytest.mark.parametrize(
    "fault",
    [
        "malformed",
        "duplicate",
        "nan",
        "infinity",
        "deep",
        "surrogate",
        "oversized",
        "missing",
        "extra",
        "wrong_type",
        "wrong_enum",
        "overlong",
    ],
)
def test_draft_structure_rejection_is_bounded_and_private(parser, fault):
    payload = _provider_payload()
    if fault == "missing":
        del payload["status"]
    elif fault == "extra":
        payload["untrusted-private-field"] = "private-value"
    elif fault == "wrong_type":
        payload["requirements"] = "not a list"
    elif fault == "wrong_enum":
        payload["status"] = "not a status"
    elif fault == "overlong":
        payload["findings"][0]["message"] = "x" * 1001
    elif fault == "surrogate":
        payload["findings"][0]["message"] = "\ud800"
    elif fault in {"nan", "infinity"}:
        payload["submission_artifact_policy"]["maximum_file_size_bytes"] = float(fault)
    raw = json.dumps(payload)
    if fault == "malformed":
        raw = '{"private-marker":'
    elif fault == "duplicate":
        raw = '{"status":"draft_ready",' + raw[1:]
    elif fault == "deep":
        raw = "[" * 1100 + "0" + "]" * 1100
    elif fault == "oversized":
        raw = " " * 100_001 + raw
    assert parser.parse(raw) is None
    if fault == "overlong":
        assert parser.issues == [
            {"path": ["findings", 0, "message"], "code": "schema_maxLength"}
        ]
    elif fault == "surrogate":
        assert parser.issues == [{"path": [], "code": "invalid_json"}]


@pytest.mark.parametrize(
    "patch",
    [
        {"$ref": "https://example.invalid/schema"},
        {"$dynamicRef": "file:///private/schema"},
        {"$id": "https://example.invalid/base"},
    ],
)
def test_draft_schema_never_resolves_external_resources(patch):
    with pytest.raises(ValueError, match="only local references"):
        CompilationDraftParser({"type": "object", "properties": {"field": patch}}, 1000)


def _invalid_canonical_payload(fault):
    """Reproduce live path/pairing defects and unsafe prose without invalid JSON shape."""
    payload = _provider_payload()
    if fault == "path":
        payload["submission_artifact_policy"]["required_artifacts"] = ["environment/"]
    elif fault == "material":
        specification = _provider_specification()
        specification["runtime_dependencies"] = [
            {
                "dependency_id": "prior_material",
                "kind": "task_context",
                "provisioning": "runtime_gap",
                "purpose": "Compare the prior task context.",
                "unavailable_code": "material_unavailable",
            }
        ]
        specification["infrastructure_failures"] = [
            {
                "code": "material_unavailable",
                "condition": "The prior context is unavailable.",
            }
        ]
        payload["requirements"][0]["check_specification"] = specification
    else:
        payload["findings"][0]["message"] = "token=private-draft-marker-7391"
    return payload


@pytest.mark.usefixtures("model_credentials")
@pytest.mark.parametrize("fault", ["path", "material", "unsafe"])
@pytest.mark.parametrize("review", ["corrected", "unchanged", "provider_error"])
async def test_review_can_correct_private_draft_without_relaxing_acceptance(
    monkeypatch,
    caplog,
    parser,
    fault,
    review,
):
    """Only the canonical second result survives; private failures expose no draft values."""
    from agents import Runner

    payload = _invalid_canonical_payload(fault)
    if fault == "unsafe":
        assert parser.parse(json.dumps(payload)) == payload
        assert parser.canonical_issues(payload) == [
            {"path": ["findings", 0, "message"], "code": "canonical_constraint"}
        ]
    parsers = []
    models = []

    async def run(agent, prompt, **kwargs):
        parsers.append(agent.output_type)
        models.append(agent.model)
        await _open_prompt_documents(agent, prompt)
        if len(parsers) == 1:
            return SimpleNamespace(
                final_output=agent.output_type.validate_json(json.dumps(payload))
            )
        supplied = json.loads(prompt)
        if len(parsers) == 2 or review == "unchanged":
            issues = supplied["validation_errors"]
            assert issues and len(issues) <= 20
            assert all(set(issue) == {"path", "code"} for issue in issues)
            assert "private-draft-marker" not in prompt
            assert "candidate_proposal" not in supplied
        assert models[0] is models[-1]
        if review == "provider_error":
            raise RuntimeError("private-draft-marker-7391")
        value = _provider_payload() if review == "corrected" else payload
        return SimpleNamespace(final_output=agent.output_type.validate_json(json.dumps(value)))

    monkeypatch.setattr(Runner, "run", run)
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    if review == "corrected":
        assert await _compile(runtime, context(ids())) == generated_result()
    else:
        expected = (
            ProjectAgentRuntimeError
            if review == "provider_error"
            else ProjectGuideCompilationInvalidOutputError
        )
        with pytest.raises(expected) as caught:
            await _compile(runtime, context(ids()))
        assert "private-draft-marker" not in str(caught.value)
        assert caught.value.__suppress_context__
    assert len(parsers) == (2 if review == "provider_error" else 3)
    assert "private-draft-marker" not in caplog.text
