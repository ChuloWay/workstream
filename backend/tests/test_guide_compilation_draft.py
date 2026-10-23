"""Private drafts can be corrected; only canonical reviewed output can be accepted."""

import json
import weakref
from types import SimpleNamespace

import pytest

from app.adapters.project_agents.compilation_draft import CompilationDraftParser
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
        AgentOutputSchema(ProjectGuideCompilationResult).json_schema(), 100_000
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
        payload["setup_notes"] = ["x" * 1001]
    elif fault == "surrogate":
        payload["setup_notes"] = ["\ud800"]
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
        payload["setup_notes"] = ["token=private-draft-marker-7391"]
    return payload


@pytest.mark.usefixtures("model_credentials")
@pytest.mark.parametrize("fault", ["path", "material", "unsafe"])
@pytest.mark.parametrize("review", ["corrected", "unchanged", "provider_error"])
async def test_review_can_correct_private_draft_without_relaxing_acceptance(
    monkeypatch,
    caplog,
    fault,
    review,
):
    """Only the canonical second result survives; private failures expose no draft values."""
    from agents import Runner

    payload = _invalid_canonical_payload(fault)
    parsers = []
    models = []
    receipt_reference = None

    class Receipt:
        pass

    async def run(agent, prompt, **kwargs):
        nonlocal receipt_reference
        parsers.append(agent.output_type)
        models.append(agent.model)
        await _open_prompt_documents(agent, prompt)
        if len(parsers) == 1:
            receipt = Receipt()
            receipt.final_output = agent.output_type.validate_json(json.dumps(payload))
            assert isinstance(receipt.final_output, dict)
            receipt_reference = weakref.ref(receipt)
            return receipt
        assert len(parsers) == 2
        assert receipt_reference() is None
        supplied = json.loads(prompt)
        assert supplied["candidate_proposal"] == payload
        issues = supplied["candidate_validation_issues"]
        assert issues and len(issues) <= 20
        assert all(set(issue) == {"path", "code"} for issue in issues)
        assert "private-draft-marker" not in json.dumps(issues)
        assert parsers[0] is not parsers[1]
        assert parsers[0].json_schema() == parsers[1].json_schema()
        assert models[0] is models[1]
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
    assert len(parsers) == 2
    assert "private-draft-marker" not in caplog.text
