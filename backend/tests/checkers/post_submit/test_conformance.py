"""Real registered handlers, reachable counterexamples, and explicit legacy dispatch."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.checkers.api import ExpectedPostSubmitContext
from app.modules.checkers.api.post_submit_catalogue import LEGACY_IMPLEMENTATION_VERSION
from app.modules.checkers.post_submit_implementations import (
    bounded_structural_result,
    check_modern_policy_context,
    detached_checker_context,
    evaluate_registered_structural_member,
)
from app.modules.checkers.runner import CheckerContext, CheckerOutcome, default_checker_registry
from tests.checkers.post_submit.support import change_request, request

CASES = (
    ("check_submission_packet", "packet_fields_missing", "failed"),
    ("check_policy_context_present", "policy_context_invalid", "failed"),
    ("check_evidence_present", "evidence_missing", "failed"),
    ("check_evidence_integrity", "evidence_structure_invalid", "failed"),
    ("check_required_files", "required_files_missing", "failed"),
    ("check_forbidden_files", "forbidden_path_present", "failed"),
    ("check_confidentiality_attestation", "attestation_missing", "failed"),
    ("check_low_quality_generated_artifacts", "placeholder_signal", "warning"),
    ("check_acceptance_criteria_present", "acceptance_criteria_missing", "failed"),
)


def damaged_input(source, name):
    data = source.structural_input.model_dump()
    if name == "check_submission_packet":
        data["summary"] = ""
    elif name == "check_policy_context_present":
        data["observed_context"]["post_policy_id"] = None
    elif name == "check_evidence_present":
        data["evidence"] = ()
    elif name == "check_evidence_integrity":
        data["manifest"][0]["hash"] = "invalid"
    elif name == "check_required_files":
        data["manifest"][0]["artifact"] = "another.txt"
    elif name == "check_forbidden_files":
        data["manifest"][0]["artifact"] = "forbidden/data.txt"
    elif name == "check_confidentiality_attestation":
        data["worker_attestation"] = data["worker_attestation"].replace("Rights confirmed.", "")
    elif name == "check_low_quality_generated_artifacts":
        data["summary"] = "TODO: add actual content"
    elif name == "check_acceptance_criteria_present":
        data["criteria"] = " "
    return change_request(source, structural_input=data)


@pytest.mark.parametrize("name,code,status", CASES)
async def test_structural_conformance(name, code, status):
    registry = default_checker_registry()
    source = request()
    definition = source.catalogue.definition(name, "v0.2")
    control = await evaluate_registered_structural_member(registry, definition, source)
    assert (control.status, control.code, control.severity, control.failure_category) == (
        "passed",
        "passed",
        "info",
        "none",
    )
    result = await evaluate_registered_structural_member(
        registry, definition, damaged_input(source, name)
    )
    assert (result.status, result.code) == (status, code)
    assert result.severity == ("medium" if status == "warning" else "high")
    assert result.failure_category == (
        "task_configuration"
        if name in {"check_policy_context_present", "check_acceptance_criteria_present"}
        else "submission_structure"
    )
    assert "message" not in result.model_dump()


@pytest.mark.parametrize("field", tuple(ExpectedPostSubmitContext.model_fields))
@pytest.mark.parametrize("kind", ("missing", "crossed"))
async def test_modern_policy_context_without_payment(field, kind):
    source = request()
    data = source.structural_input.model_dump()
    old = data["observed_context"][field]
    replacement = None
    if kind == "crossed":
        replacement = (
            uuid4()
            if field.endswith("_id")
            else 2
            if type(old) is int
            else ("sha256:" + "b" * 64 if str(old).startswith("sha256:") else "other")
        )
    data["observed_context"][field] = replacement
    changed = change_request(source, structural_input=data)
    definition = source.catalogue.definition("check_policy_context_present", "v0.2")
    registry = default_checker_registry()
    assert (
        await evaluate_registered_structural_member(registry, definition, source)
    ).status == "passed"
    result = await evaluate_registered_structural_member(registry, definition, changed)
    assert result.code == "policy_context_invalid"
    assert result.status == "failed"


async def test_legacy_name_only_execution_stays_on_exact_old_handler():
    fields = (
        "locked_guide_version",
        "locked_post_submit_checker_policy_id",
        "locked_post_submit_checker_policy_version",
        "locked_post_submit_checker_policy_hash",
        "locked_review_policy_id",
        "locked_review_policy_generation",
        "locked_review_policy_hash",
        "locked_revision_policy_id",
        "locked_revision_policy_generation",
        "locked_revision_policy_hash",
        "locked_payment_policy_version",
        "locked_guide_source_snapshot_id",
        "locked_guide_source_snapshot_hash",
        "locked_effective_project_submission_artifact_policy_id",
        "locked_effective_project_submission_artifact_policy_hash",
        "locked_pre_submit_checker_policy_id",
        "locked_pre_submit_checker_bundle_hash",
    )
    submission = SimpleNamespace(**dict.fromkeys(fields, "v1"))
    context = CheckerContext(
        task=None,
        submission=submission,
        required_checker_names=frozenset(),
        warning_checker_names=frozenset(),
        blocking_severities=frozenset(),
    )
    registry = default_checker_registry()
    assert (await registry.run(context, ["check_policy_context_present"]))[0].status == "passed"
    submission.locked_payment_policy_version = None
    result = (await registry.run(context, ["check_policy_context_present"]))[0]
    assert result.status == "failed"
    assert result.metadata["missing_context"] == ["locked_payment_policy_version"]
    assert (
        registry.resolve("check_policy_context_present", LEGACY_IMPLEMENTATION_VERSION).definition
        is None
    )


async def test_presence_check_does_not_claim_substantive_quality():
    source = request()
    changed = change_request(
        source,
        structural_input={
            **source.structural_input.model_dump(),
            "summary": "An incorrect analysis with unsupported conclusions.",
        },
    )
    definition = source.catalogue.definition("check_acceptance_criteria_present", "v0.2")
    result = await evaluate_registered_structural_member(
        default_checker_registry(), definition, changed
    )
    assert result.status == "passed"
    assert definition.supported_claim == "criteria_presence"


@pytest.mark.parametrize("mutation", ("identity", "severity", "status"))
def test_bounded_result_rejects_malformed_handler_output(mutation):
    definition = request().catalogue.definitions[0]
    values = dict(
        checker_name=definition.capability_id, status="failed", severity="high", message="secret"
    )
    values[{"identity": "checker_name", "severity": "severity", "status": "status"}[mutation]] = {
        "identity": "other",
        "severity": "low",
        "status": "accept",
    }[mutation]
    with pytest.raises(ValueError):
        bounded_structural_result(definition, CheckerOutcome(**values))


async def test_modern_handler_requires_detached_input_and_definitions_are_exact():
    source = request()
    context = detached_checker_context(source)
    context = replace(context, detached_input=None)
    with pytest.raises(ValueError, match="requires detached"):
        await check_modern_policy_context(context)
    definition = source.catalogue.definitions[0].model_copy(update={"state": "disabled"})
    with pytest.raises(ValueError, match="definition mismatch"):
        await evaluate_registered_structural_member(default_checker_registry(), definition, source)
    registry = default_checker_registry()
    key = (source.catalogue.definitions[0].capability_id, LEGACY_IMPLEMENTATION_VERSION)
    registry._checkers[key] = registry._checkers[
        ("check_required_files", LEGACY_IMPLEMENTATION_VERSION)
    ]
    with pytest.raises(ValueError, match="installed definition mismatch"):
        await evaluate_registered_structural_member(
            registry, source.catalogue.definitions[0], source
        )


@pytest.mark.parametrize(
    "damage", ("duplicate", "empty_package", "empty_manifest", "missing_evidence_hash")
)
async def test_additional_claim_specific_failures_reach_handlers(damage):
    source = request()
    data = source.structural_input.model_dump()
    name, code = "check_evidence_integrity", "evidence_structure_invalid"
    if damage == "duplicate":
        data["manifest"] = data["manifest"] * 2
    elif damage == "missing_evidence_hash":
        data["evidence"][0]["hash"] = None
    else:
        name, code = "check_submission_packet", "packet_fields_missing"
        if damage == "empty_package":
            data["package_hash"] = ""
        else:
            data["manifest"] = ()
    changed = change_request(source, structural_input=data)
    result = await evaluate_registered_structural_member(
        default_checker_registry(), source.catalogue.definition(name, "v0.2"), changed
    )
    assert result.code == code
