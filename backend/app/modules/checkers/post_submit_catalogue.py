"""Construct the public snapshot from the single versioned checker registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.checkers.runner import CheckerRegistry

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.post_submit_catalogue import (
    MODERN_CONTEXT_IMPLEMENTATION_VERSION,
    LEGACY_IMPLEMENTATION_VERSION,
    PostSubmitCatalogue,
    PostSubmitDefinition,
)

# Definition data belongs to explicit registration, not a second dispatch registry.
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
                implementation_version=(
                    MODERN_CONTEXT_IMPLEMENTATION_VERSION
                    if name == "check_policy_context_present"
                    else LEGACY_IMPLEMENTATION_VERSION
                ),
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


def build_post_submit_catalogue(registry: CheckerRegistry) -> PostSubmitCatalogue:
    """Validate installed metadata/callable parity and hash the exact snapshot."""
    definitions = tuple(sorted(registry.definitions(), key=lambda item: item.order))
    if {item.capability_id for item in definitions} != {row[0] for row in _STRUCTURAL_DEFINITIONS}:
        raise ValueError("post-submit registered catalogue is incomplete")
    for definition in definitions:
        entry = registry.resolve(definition.capability_id, definition.implementation_version)
        if entry.definition != definition or entry.checker.name != definition.capability_id:
            raise ValueError("post-submit registered implementation mismatch")
    body = {
        "catalogue_id": "workstream.post_submission_checkers",
        "source_version": "v0.2",
        "schema_version": "post_submission_checker_capability_projection.v2",
        "definitions": [item.model_dump(mode="json") for item in definitions],
    }
    return PostSubmitCatalogue(**body, manifest_sha256=canonical_json_hash(body))
