"""Frozen pre-cutover metadata used only by retained-record migration fixtures."""

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.historical_post_submit import (
    POST_SUBMIT_CATALOGUE_ID, POST_SUBMIT_CATALOGUE_SCHEMA, POST_SUBMIT_IMPLEMENTATION_ID,
    PostSubmitCatalogue, PostSubmitDefinition,
)

_STRUCTURAL_DEFINITIONS = (
    ("check_submission_packet", "packet_presence", "packet_fields_missing", "submission_structure"),
    (
        "check_policy_context_present",
        "policy_context_consistency",
        "policy_context_invalid",
        "task_configuration",
    ),
    ("check_evidence_present", "evidence_presence", "evidence_missing", "submission_structure"),
    (
        "check_evidence_integrity",
        "evidence_structure",
        "evidence_structure_invalid",
        "submission_structure",
    ),
    (
        "check_required_files",
        "required_path_presence",
        "required_files_missing",
        "submission_structure",
    ),
    (
        "check_forbidden_files",
        "forbidden_path_detection",
        "forbidden_path_present",
        "submission_structure",
    ),
    (
        "check_confidentiality_attestation",
        "attestation_presence",
        "attestation_missing",
        "submission_structure",
    ),
    (
        "check_low_quality_generated_artifacts",
        "placeholder_signal_detection",
        "placeholder_signal",
        "submission_structure",
    ),
    (
        "check_acceptance_criteria_present",
        "criteria_presence",
        "acceptance_criteria_missing",
        "task_configuration",
    ),
)


def structural_definition(name: str) -> PostSubmitDefinition:
    """Mint the code-owned metadata attached to an explicit registration entry."""
    for order, (checker_id, claim, failure, category) in enumerate(_STRUCTURAL_DEFINITIONS, 1):
        if checker_id == name:
            warning = name == "check_low_quality_generated_artifacts"
            return PostSubmitDefinition(
                capability_id=name,
                implementation_version=POST_SUBMIT_IMPLEMENTATION_ID,
                platform_default=order <= 8,
                selectable=order == 9,
                order=order,
                supported_claim=claim,
                failure_code=failure,
                failure_category=category,
                failure_status="warning" if warning else "failed",
                failure_severity="medium" if warning else "high",
            )
    raise ValueError("unknown structural post-submit definition")


def historical_post_submit_catalogue() -> PostSubmitCatalogue:
    """Return code-owned immutable metadata, without execution authority."""
    definitions = tuple(structural_definition(row[0]) for row in _STRUCTURAL_DEFINITIONS)
    body = {
        "catalogue_id": POST_SUBMIT_CATALOGUE_ID,
        "source_version": "v0.1",
        "schema_version": POST_SUBMIT_CATALOGUE_SCHEMA,
        "definitions": [item.model_dump(mode="json") for item in definitions],
    }
    return PostSubmitCatalogue(**body, manifest_sha256=canonical_json_hash(body))


