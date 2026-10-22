"""Typed implementation handoff and generation-admission boundaries."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CheckInput,
    CheckRuntimeDependency,
    CheckSpecification,
    GuideEvidenceRef,
    PostSubmissionBindingProposal,
    PreSubmissionBindingProposal,
    ProjectGuideCompilationResult,
    require_complete_generated_specifications,
    validate_project_guide_compilation_result,
)
from app.modules.checkers.api.external import (
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistrySpec,
)
from app.modules.projects.guide_compilation.contracts import accepted_compilation_result
from tests.checkers.external.support import capability_projection, registry_entry
from tests.projects.guide_compilation.helpers import (
    DOCUMENT_VERSION_ID,
    SOURCE_ITEM_ID,
    SOURCE_SHA256,
    context,
    generated_result,
    ids,
    result,
    valid_specification,
)


def _specification(**updates: object) -> CheckSpecification:
    body = valid_specification().model_dump(mode="json")
    body.update(updates)
    return CheckSpecification.model_validate(body)


def _requirement(**updates: object) -> AtomicGuideRequirement:
    body: dict[str, object] = {
        "requirement_id": "required_item",
        "statement": "The submitted work must include the required item.",
        "disposition": "supported_pre_submit",
        "classification_rationale": "Static inspection can enforce this at intake.",
        "check_specification": valid_specification().model_dump(mode="json"),
        "evidence_refs": [
            GuideEvidenceRef(
                source_item_id=SOURCE_ITEM_ID,
                document_version_id=DOCUMENT_VERSION_ID,
                sha256=SOURCE_SHA256,
            ).model_dump(mode="json")
        ],
    }
    body.update(updates)
    return AtomicGuideRequirement.model_validate(body)


def _with_requirement(
    requirement: AtomicGuideRequirement,
) -> ProjectGuideCompilationResult:
    return generated_result().model_copy(update={"requirements": (requirement,)})


def _entry_with_deadline(
    deadline_ms: int, phase: str = "pre_submit"
) -> ExternalCheckerRegistryEntry:
    original = registry_entry(phase)
    body = original.model_dump()
    body["resources"]["deadline_ms"] = deadline_ms
    spec_fields = ExternalCheckerRegistrySpec.model_fields
    spec = ExternalCheckerRegistrySpec.model_validate(
        {name: body[name] for name in spec_fields}
    )
    body["entry_digest"] = spec.spec_digest
    return ExternalCheckerRegistryEntry.model_validate(body)


def test_valid_generated_result_and_static_specification_are_admitted() -> None:
    compilation_context = context(ids())

    require_complete_generated_specifications(
        compilation_context, generated_result()
    )
    require_complete_generated_specifications(
        compilation_context, _with_requirement(_requirement())
    )


def test_generation_admission_does_not_change_retained_result_hashes() -> None:
    legacy_requirement = AtomicGuideRequirement(
        requirement_id="review_scope",
        statement="The guide provides background for claim review.",
        disposition="informational",
        evidence_refs=(
            GuideEvidenceRef(
                source_item_id=SOURCE_ITEM_ID,
                document_version_id=DOCUMENT_VERSION_ID,
                sha256=SOURCE_SHA256,
            ),
        ),
    )
    legacy = result().model_copy(update={"requirements": (legacy_requirement,)})
    accepted = accepted_compilation_result(legacy)
    reparsed = ProjectGuideCompilationResult.model_validate(accepted.canonical_result)

    assert "classification_rationale" not in accepted.canonical_result["requirements"][0]
    assert "check_specification" not in accepted.canonical_result["requirements"][0]
    assert accepted_compilation_result(reparsed) == accepted
    validate_project_guide_compilation_result(context(ids()), legacy)
    with pytest.raises(ValueError, match="classification rationale"):
        require_complete_generated_specifications(context(ids()), legacy)


def test_ready_generation_requires_a_requirement_inventory() -> None:
    with pytest.raises(ValueError, match="requirement inventory"):
        require_complete_generated_specifications(context(ids()), result())


def test_every_generated_requirement_requires_source_evidence() -> None:
    requirement = _requirement(evidence_refs=[])

    with pytest.raises(ValueError, match="source evidence"):
        require_complete_generated_specifications(
            context(ids()), _with_requirement(requirement)
        )


@pytest.mark.parametrize(
    ("disposition", "specification", "message"),
    [
        ("supported_pre_submit", None, "lacks a check specification"),
        ("pre_submit_capability_gap", None, "lacks a check specification"),
        (
            "human_review",
            valid_specification(),
            "non-check requirement cannot include",
        ),
        (
            "project_lifecycle_policy",
            valid_specification(),
            "non-check requirement cannot include",
        ),
    ],
)
def test_generation_admission_requires_specifications_only_for_check_dispositions(
    disposition: str,
    specification: CheckSpecification | None,
    message: str,
) -> None:
    requirement = _requirement(
        disposition=disposition,
        check_specification=(
            specification.model_dump(mode="json")
            if specification is not None
            else None
        ),
    )

    with pytest.raises(ValueError, match=message):
        require_complete_generated_specifications(
            context(ids()), _with_requirement(requirement)
        )


@pytest.mark.parametrize(
    ("disposition", "execution_mode", "duration", "message"),
    [
        ("supported_pre_submit", "bounded_pre_submit", 61, "not bounded"),
        ("pre_submit_capability_gap", "background", 60, "not bounded"),
        ("supported_post_submit", "bounded_pre_submit", 60, "not background"),
        ("post_submit_capability_gap", "bounded_pre_submit", 60, "not background"),
    ],
)
def test_generation_admission_enforces_stage_from_bounded_work(
    disposition: str,
    execution_mode: str,
    duration: int,
    message: str,
) -> None:
    specification = _specification(
        execution_mode=execution_mode,
        maximum_duration_seconds=duration,
    )

    with pytest.raises(ValueError, match=message):
        require_complete_generated_specifications(
            context(ids()),
            _with_requirement(
                _requirement(
                    disposition=disposition,
                    check_specification=specification.model_dump(mode="json"),
                )
            ),
        )


def test_supported_check_cannot_claim_runtime_support_the_runner_lacks() -> None:
    dependency = CheckRuntimeDependency(
        dependency_id="task_material",
        kind="task_context",
        provisioning="runtime_gap",
        purpose="Task instructions needed for evaluation.",
        unavailable_code="material_unavailable",
    )
    specification = _specification(
        inputs=[
            {
                "input_id": "task_material",
                "kind": "task_context",
                "purpose": "Task instructions needed for evaluation.",
            }
        ],
        runtime_dependencies=[dependency.model_dump(mode="json")],
        infrastructure_failures=[
            {
                "code": "material_unavailable",
                "condition": "Task instructions are unavailable.",
            }
        ],
    )

    with pytest.raises(ValueError, match="unavailable runtime support"):
        require_complete_generated_specifications(
            context(ids()),
            _with_requirement(
                _requirement(
                    check_specification=specification.model_dump(mode="json")
                )
            ),
        )


def test_pre_submit_binding_must_fit_the_stage_budget() -> None:
    entry = _entry_with_deadline(60_001)
    compilation_context = context(
        ids(), checker_capabilities=capability_projection(entry)
    )
    proposal = _with_requirement(_requirement()).model_copy(
        update={
            "pre_submit_bindings": (
                PreSubmissionBindingProposal(
                    requirement_id="required_item",
                    capability_id=entry.capability_id,
                    capability_version=entry.capability_version,
                    stage="pre_submit",
                ),
            )
        }
    )

    with pytest.raises(ValueError, match="deadline exceeds"):
        require_complete_generated_specifications(compilation_context, proposal)


@pytest.mark.parametrize("phase", ["pre_submit", "post_submit"])
def test_supported_specification_must_fit_the_selected_checker_deadline(
    phase: str,
) -> None:
    entry = _entry_with_deadline(30_000, phase)
    compilation_context = context(
        ids(), checker_capabilities=capability_projection(entry)
    )
    specification = _specification(
        execution_mode=("bounded_pre_submit" if phase == "pre_submit" else "background"),
        maximum_duration_seconds=31,
    )
    requirement = _requirement(
        disposition=(
            "supported_pre_submit"
            if phase == "pre_submit"
            else "supported_post_submit"
        ),
        check_specification=specification.model_dump(mode="json"),
    )
    binding_type = (
        PreSubmissionBindingProposal
        if phase == "pre_submit"
        else PostSubmissionBindingProposal
    )
    binding = binding_type(
        requirement_id="required_item",
        capability_id=entry.capability_id,
        capability_version=entry.capability_version,
        stage=phase,
    )
    proposal = _with_requirement(requirement).model_copy(
        update={
            (
                "pre_submit_bindings"
                if phase == "pre_submit"
                else "post_submit_bindings"
            ): (binding,)
        }
    )

    with pytest.raises(ValueError, match="exceeds the checker deadline"):
        require_complete_generated_specifications(compilation_context, proposal)


@pytest.mark.parametrize(
    "input_body",
    [
        {
            "input_id": "report",
            "kind": "relative_file",
            "purpose": "Report to inspect.",
        },
        {
            "input_id": "report",
            "kind": "package",
            "relative_path": "report.txt",
            "purpose": "Report to inspect.",
        },
        {
            "input_id": "report",
            "kind": "relative_file",
            "relative_path": "../report.txt",
            "purpose": "Report to inspect.",
        },
    ],
)
def test_check_input_requires_a_canonical_path_only_for_relative_material(
    input_body: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="relative path"):
        CheckInput.model_validate(input_body)


def test_negative_test_verdict_must_match_referenced_finding_levels() -> None:
    negative = valid_specification().negative_tests[0].model_dump(mode="json")
    negative["expected_verdict"] = "passed"

    with pytest.raises(ValidationError, match="verdict disagrees"):
        _specification(negative_tests=[negative])


def test_work_findings_cannot_use_reserved_infrastructure_codes() -> None:
    finding = valid_specification().failure_findings[0].model_dump(mode="json")
    finding["code"] = "deadline_exceeded"
    negative = valid_specification().negative_tests[0].model_dump(mode="json")
    negative["expected_finding_codes"] = ["deadline_exceeded"]

    with pytest.raises(ValidationError, match="must be distinct"):
        _specification(failure_findings=[finding], negative_tests=[negative])


def test_every_prose_collection_member_is_validated() -> None:
    with pytest.raises(ValidationError, match="model-produced text is unsafe"):
        _specification(check_steps=["Run bash to inspect the package."])


def test_check_specification_is_a_closed_object() -> None:
    body = valid_specification().model_dump(mode="json")
    body["evaluation_method_description"] = "Extra prose is not admitted."

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CheckSpecification.model_validate(body)
