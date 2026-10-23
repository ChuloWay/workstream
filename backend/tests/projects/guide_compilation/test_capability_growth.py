"""Catalogue growth reports retain exact matches without inventing executable checks."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CapabilitySuggestion,
    CompilationFinding,
    PostSubmissionBindingProposal,
    PreSubmissionBindingProposal,
    ProjectGuideCompilationResult,
    validate_project_guide_compilation_result,
)
from .helpers import context, ids, result, valid_specification
from tests.checkers.external.support import capability_projection, registry_entry


def _context():
    """Expose one exact selectable image in each phase for growth validation."""
    return context(
        ids(),
        checker_capabilities=capability_projection(
            registry_entry("pre_submit"), registry_entry("post_submit")
        ),
    )


def growth_report(*, gaps=True):
    """Use current selectable definitions and distinct missing checks in both stages."""
    source = _context()
    refs = result().findings[0].evidence_refs
    requirements, suggestions, pre, post = [], [], [], []
    for stage in ("pre_submit", "post_submit"):
        specification = valid_specification().model_copy(
            update={
                "execution_mode": (
                    "bounded_pre_submit" if stage == "pre_submit" else "background"
                )
            }
        )
        key = f"supported_{stage}"
        requirements.append(
            AtomicGuideRequirement(
                requirement_id=key,
                statement="Require the registered structural check.",
                disposition=f"supported_{stage}",
                classification_rationale=(
                    "The selected check fits the bounded intake stage."
                    if stage == "pre_submit"
                    else "The selected check runs as background evaluation."
                ),
                check_specification=specification,
                evidence_refs=refs,
            )
        )
        definition = next(
            d for d in source.checker_capabilities.definitions if d.selectable and d.phase == stage
        )
        if stage == "pre_submit":
            pre.append(
                PreSubmissionBindingProposal(
                    requirement_id=key,
                    capability_id=definition.capability_id,
                    capability_version=definition.capability_version,
                    stage=stage,
                )
            )
        else:
            post.append(
                PostSubmissionBindingProposal(
                    requirement_id=key,
                    capability_id=definition.capability_id,
                    capability_version=definition.capability_version,
                    stage=stage,
                )
            )
        if gaps:
            key = f"gap_{stage}"
            requirements.append(
                AtomicGuideRequirement(
                    requirement_id=key,
                    statement="Require an unavailable automated semantic check.",
                    disposition=f"{stage}_capability_gap",
                    classification_rationale=(
                        "The missing check belongs in the bounded intake stage."
                        if stage == "pre_submit"
                        else "The missing check belongs in background evaluation."
                    ),
                    check_specification=specification,
                    evidence_refs=refs,
                )
            )
            suggestions.append(
                CapabilitySuggestion(
                    requirement_id=key,
                    stage=stage,
                    title="Automated semantic verification",
                    rationale="Engineering must implement and register the required semantic check.",
                    evidence_refs=refs,
                )
            )
    return result().model_copy(
        update={
            "status": "draft_ready_with_warnings" if gaps else "draft_ready",
            "submission_artifact_policy": result().submission_artifact_policy,
            "findings": (
                CompilationFinding(
                    severity="warning" if gaps else "info",
                    code="external_checker.coverage",
                    message="Required automation is unavailable."
                    if gaps
                    else "All checks are supported.",
                    evidence_refs=refs,
                ),
            ),
            "requirements": tuple(requirements),
            "capability_suggestions": tuple(suggestions),
            "pre_submit_bindings": tuple(pre),
            "post_submit_bindings": tuple(post),
        }
    )


@pytest.mark.parametrize("gaps", [True, False])
def test_exact_matches_and_gap_handoff(gaps):
    report = growth_report(gaps=gaps)
    parsed = ProjectGuideCompilationResult.model_validate_json(report.model_dump_json())
    validate_project_guide_compilation_result(_context(), parsed)
    assert len(parsed.capability_suggestions) == (2 if gaps else 0)
    assert len(parsed.pre_submit_bindings) == len(parsed.post_submit_bindings) == 1


@pytest.mark.parametrize(
    "fault", ["missing", "duplicate", "orphan", "wrong_stage", "non_gap", "foreign_evidence"]
)
def test_gap_handoff_rejects_invalid_linkage(fault):
    report = growth_report()
    validate_project_guide_compilation_result(_context(), report)
    suggestions = list(report.capability_suggestions)
    if fault == "missing":
        suggestions.pop()
    elif fault == "duplicate":
        suggestions.append(suggestions[0])
    else:
        update = {
            "orphan": {"requirement_id": "absent"},
            "wrong_stage": {"stage": "post_submit"},
            "non_gap": {"requirement_id": "supported_pre_submit"},
            "foreign_evidence": {
                "evidence_refs": (
                    suggestions[0]
                    .evidence_refs[0]
                    .model_copy(update={"document_version_id": uuid4()}),
                )
            },
        }[fault]
        suggestions[0] = CapabilitySuggestion.model_validate(
            suggestions[0].model_dump(mode="python") | update
        )
    report = ProjectGuideCompilationResult.model_validate(
        report.model_copy(
            update={
                "capability_suggestions": tuple(suggestions),
            }
        ).model_dump(mode="json")
    )
    with pytest.raises(
        ValueError, match="source lineage" if fault == "foreign_evidence" else "suggestion"
    ):
        validate_project_guide_compilation_result(_context(), report)


@pytest.mark.parametrize("field", ["requirement_id", "stage", "evidence_refs"])
def test_suggestion_requires_explicit_linkage(field):
    payload = growth_report().capability_suggestions[0].model_dump(mode="json")
    payload.pop(field)
    with pytest.raises(ValidationError, match=field):
        CapabilitySuggestion.model_validate(payload)


def test_suggestion_rejects_empty_evidence():
    payload = growth_report().capability_suggestions[0].model_dump(mode="json")
    payload["evidence_refs"] = []
    with pytest.raises(ValidationError, match="evidence_refs"):
        CapabilitySuggestion.model_validate(payload)


@pytest.mark.parametrize("disposition", ["human_review", "informational"])
def test_non_automated_requirements_need_no_suggestion(disposition):
    report = growth_report(gaps=False)
    extra = AtomicGuideRequirement(
        requirement_id="human",
        statement="A reviewer assesses quality.",
        disposition=disposition,
        evidence_refs=report.findings[0].evidence_refs,
    )
    report = report.model_copy(
        update={
            "requirements": (*report.requirements, extra),
            "setup_notes": ("Consider an optional future reporting improvement.",),
        }
    )
    validate_project_guide_compilation_result(_context(), report)
    assert report.capability_suggestions == ()


@pytest.mark.parametrize("stage", ["pre_submit", "post_submit"])
@pytest.mark.parametrize(
    "fault", ["missing", "duplicate", "unknown", "stale", "stage", "configuration"]
)
def test_blocked_matches_still_require_exact_external_capability_validation(stage, fault):
    report = growth_report()
    field = f"{stage}_bindings"
    binding = getattr(report, field)[0]
    updates = {
        "unknown": {"capability_id": "invented"},
        "stale": {"capability_version": "absent"},
        "stage": {"stage": "post_submit" if stage == "pre_submit" else "pre_submit"},
        "configuration": {"parameters": [{"name": "invented", "value": 1}]},
    }
    if fault in updates:
        binding = type(binding).model_validate(binding.model_dump(mode="json") | updates[fault])
    bindings = (
        () if fault == "missing" else ((binding, binding) if fault == "duplicate" else (binding,))
    )
    with pytest.raises(ValueError):
        validate_project_guide_compilation_result(
            _context(), report.model_copy(update={field: bindings})
        )


@pytest.mark.parametrize("count", [50, 51, 100, 101, 200, 201])
@pytest.mark.parametrize("kind", ["gap", "pre_submit", "post_submit"])
def test_requirement_and_handoff_limits_align(count, kind):
    base = growth_report(gaps=kind == "gap")
    requirement = next(
        r
        for r in base.requirements
        if r.requirement_id == ("gap_pre_submit" if kind == "gap" else f"supported_{kind}")
    )
    field = "capability_suggestions" if kind == "gap" else f"{kind}_bindings"
    item = getattr(base, field)[0]
    payload = base.model_dump(mode="json") | {
        "requirements": [
            requirement.model_dump(mode="json") | {"requirement_id": f"r{i}"} for i in range(count)
        ],
        "capability_suggestions": [],
        "pre_submit_bindings": [],
        "post_submit_bindings": [],
    }
    payload[field] = [
        item.model_dump(mode="json") | {"requirement_id": f"r{i}"} for i in range(count)
    ]
    if count > 200:
        with pytest.raises(ValidationError, match="at most 200"):
            ProjectGuideCompilationResult.model_validate(payload)
    else:
        parsed = ProjectGuideCompilationResult.model_validate(payload)
        validate_project_guide_compilation_result(_context(), parsed)


@pytest.mark.parametrize("stage", ["pre_submit", "post_submit"])
def test_blocked_report_rejects_platform_defaults_as_project_bindings(stage):
    source = _context()
    report = growth_report()
    definitions = (
        source.checker_capabilities.definitions
        if stage == "pre_submit"
        else source.checker_capabilities.definitions
    )
    definition = next(d for d in definitions if not d.selectable)
    binding = getattr(report, f"{stage}_bindings")[0]
    binding = binding.model_copy(
        update={
            "capability_id": definition.capability_id
            if stage == "pre_submit"
            else definition.capability_id,
            "capability_version": definition.capability_version
            if stage == "pre_submit"
            else definition.capability_version,
        }
    )
    with pytest.raises(ValueError, match="compilation capability binding is invalid"):
        validate_project_guide_compilation_result(
            source, report.model_copy(update={f"{stage}_bindings": (binding,)})
        )


def test_blocked_handoff_cannot_include_artifact_policy():
    report = result().model_copy(
        update={
            "status": "guide_blocked",
            "submission_artifact_policy": None,
            "findings": (
                CompilationFinding(
                    severity="blocking_gap",
                    code="guide.invalid",
                    message="The guide cannot define a valid task policy.",
                    evidence_refs=result().findings[0].evidence_refs,
                ),
            ),
            "requirements": (
                AtomicGuideRequirement(
                    requirement_id="guide_invalid",
                    statement="The guide must define a valid task policy.",
                    disposition="guide_blocker",
                    evidence_refs=result().findings[0].evidence_refs,
                ),
            ),
        }
    )
    validate_project_guide_compilation_result(_context(), report)
    with pytest.raises(ValueError, match="blocked guide cannot publish policy proposals"):
        validate_project_guide_compilation_result(
            _context(),
            report.model_copy(
                update={
                    "submission_artifact_policy": result().submission_artifact_policy,
                }
            ),
        )


@pytest.mark.parametrize(
    "field",
    ["requirements", "capability_suggestions", "pre_submit_bindings", "post_submit_bindings"],
)
def test_each_collection_ceiling_rejects_independently(field):
    """Schema proof keeps every other collection within bounds, before semantic checks."""
    payload = growth_report().model_dump(mode="json")
    item = payload[field][0]
    payload[field] = [item] * 200
    ProjectGuideCompilationResult.model_validate(payload)
    payload[field] = [item] * 201
    with pytest.raises(ValidationError) as error:
        ProjectGuideCompilationResult.model_validate(payload)
    assert [(entry["loc"], entry["type"]) for entry in error.value.errors()] == [
        ((field,), "too_long"),
    ]
