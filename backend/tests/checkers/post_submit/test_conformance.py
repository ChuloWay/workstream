"""Real registered handlers and reachable counterexamples."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.checkers.api import ExpectedPostSubmitContext
from app.modules.checkers.post_submit_implementations import (
    bounded_structural_result,
    detached_checker_context,
    evaluate_registered_structural_member,
)
from app.modules.checkers.runner import (
    check_policy_context_present,
    CheckerOutcome,
    default_checker_registry,
)
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
    definition = source.catalogue.definition(name, "v0.1")
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
async def test_current_policy_context_without_payment(field, kind):
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
    definition = source.catalogue.definition("check_policy_context_present", "v0.1")
    registry = default_checker_registry()
    assert (
        await evaluate_registered_structural_member(registry, definition, source)
    ).status == "passed"
    result = await evaluate_registered_structural_member(registry, definition, changed)
    assert result.code == "policy_context_invalid"
    assert result.status == "failed"


async def test_registry_executes_canonical_entries_with_current_context():
    source = request()
    outcomes = await default_checker_registry().run(
        detached_checker_context(source), source.policy.entries
    )
    assert [item.checker_name for item in outcomes] == source.policy.execution_checkers
    assert all(item.status == "passed" for item in outcomes)


async def test_presence_check_does_not_claim_substantive_quality():
    source = request()
    changed = change_request(
        source,
        structural_input={
            **source.structural_input.model_dump(),
            "summary": "An incorrect analysis with unsupported conclusions.",
        },
    )
    definition = source.catalogue.definition("check_acceptance_criteria_present", "v0.1")
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


async def test_context_handler_requires_observed_input_and_definitions_are_exact():
    source = request()
    context = detached_checker_context(source)
    context = replace(context, observed_context=None)
    with pytest.raises(ValueError, match="requires expected and observed"):
        await check_policy_context_present(context)
    definition = source.catalogue.definitions[0].model_copy(update={"state": "disabled"})
    with pytest.raises(ValueError, match="definition mismatch"):
        await evaluate_registered_structural_member(default_checker_registry(), definition, source)
    registry = default_checker_registry()
    key = source.catalogue.definitions[0].capability_id
    registry._checkers[key] = registry._checkers["check_required_files"]
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
        default_checker_registry(), source.catalogue.definition(name, "v0.1"), changed
    )
    assert result.code == code


@pytest.mark.parametrize("alias", ("./report.txt", ".\\report.txt", " report.txt "))
async def test_normalized_duplicates_preserve_immutable_source(alias):
    source = request()
    data = source.structural_input.model_dump()
    entry = data["manifest"][0]
    data["manifest"] = (entry, {**entry, "artifact": alias})
    changed = change_request(source, structural_input=data)
    original = changed.model_dump_json()
    registry = default_checker_registry()
    definition = changed.catalogue.definition("check_evidence_integrity", "v0.1")
    outcome = await evaluate_registered_structural_member(registry, definition, changed)
    assert (outcome.status, outcome.code) == ("failed", "evidence_structure_invalid")
    assert changed.model_dump_json() == original


@pytest.mark.parametrize("path", ("../report.txt", "/report.txt", "./"))
async def test_invalid_copied_paths_reach_registered_failure(path):
    source = request()
    data = source.structural_input.model_dump()
    data["manifest"][0]["artifact"] = path
    changed = change_request(source, structural_input=data)
    original = changed.model_dump_json()
    outcome = await evaluate_registered_structural_member(
        default_checker_registry(),
        changed.catalogue.definition("check_evidence_integrity", "v0.1"),
        changed,
    )
    assert (outcome.status, outcome.code) == ("failed", "evidence_structure_invalid")
    assert changed.model_dump_json() == original


@pytest.mark.parametrize(
    "uri,expected",
    (
        ("./report.txt", "report.txt"),
        ("https://example.com/proof", "https://example.com/proof"),
    ),
)
def test_copied_evidence_paths_preserve_external_uri_identity(uri, expected):
    source = request()
    data = source.structural_input.model_dump()
    data["evidence"][0]["uri"] = uri
    changed = change_request(source, structural_input=data)
    assert detached_checker_context(changed).submission.evidence_items[0].uri == expected
    assert changed.structural_input.evidence[0].uri == uri


@pytest.mark.parametrize(
    "field",
    (
        "payment_policy_version",
        "compilation_id",
        "compilation_result_hash",
        "contribution_policy_version_id",
        "guide_id",
        "project_id",
    ),
)
def test_context_rejects_unsupported_or_fabricated_observations(field):
    from app.modules.checkers.api import ObservedPostSubmitContext

    values = request().structural_input.observed_context.model_dump()
    with pytest.raises(ValueError, match="Extra inputs"):
        ObservedPostSubmitContext.model_validate({**values, field: uuid4()})
