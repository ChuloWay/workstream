"""Unified proposals preserve separate human review and unsupported-automation gaps."""

import pytest

from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CapabilitySuggestion,
    PostSubmissionBindingProposal,
    ProjectGuideCompilationResult,
    validate_project_guide_compilation_result,
)
from tests.test_project_guide_compilation_contracts import _artifact_policy, _context, _evidence


def proposal(disposition, *, binding=False):
    gap = disposition == "post_submit_capability_gap"
    return ProjectGuideCompilationResult(
        status="draft_ready_with_warnings" if gap else "draft_ready",
        agent_version="v1",
        submission_artifact_policy=_artifact_policy(),
        findings=({
            "severity": "warning",
            "code": "capability.unavailable",
            "message": "Required automation is awaiting a registered checker.",
            "evidence_refs": (_evidence(),),
        },) if gap else (),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="quality",
                statement="Evaluate the submitted analysis.",
                disposition=disposition,
                evidence_refs=(_evidence(),),
            ),
        ),
        capability_suggestions=(CapabilitySuggestion(
            requirement_id="quality", stage="post_submit", title="Required automated analysis check",
            rationale="Engineering must provide the unavailable automated analysis evaluator.",
            evidence_refs=(_evidence(),),
        ),) if gap else (),
        post_submit_bindings=(
            PostSubmissionBindingProposal(
                requirement_id="quality",
                capability_id="acme.post",
                capability_version="v1.2.3",
                stage="post_submit",
            ),
        )
        if binding
        else (),
    )


def test_requirement_disposition_is_preserved():
    source = _context()
    human = proposal("human_review")
    validate_project_guide_compilation_result(source, human)
    assert human.requirements[0].disposition.value == "human_review"
    assert human.post_submit_bindings == ()
    gap = proposal("post_submit_capability_gap")
    validate_project_guide_compilation_result(source, gap)
    assert gap.requirements[0].disposition.value == "post_submit_capability_gap"
    assert gap.post_submit_bindings == ()
    blocked_gap = gap.model_copy(
        update={"status": "guide_blocked", "submission_artifact_policy": None}
    )
    with pytest.raises(ValueError, match="blocked compilation requires blocking"):
        validate_project_guide_compilation_result(source, blocked_gap)


@pytest.mark.parametrize("disposition", ("human_review", "post_submit_capability_gap"))
def test_unbound_dispositions_cannot_acquire_a_binding(disposition):
    source = _context()
    validate_project_guide_compilation_result(source, proposal(disposition))
    with pytest.raises(ValueError, match="compilation capability binding is invalid"):
        validate_project_guide_compilation_result(source, proposal(disposition, binding=True))
