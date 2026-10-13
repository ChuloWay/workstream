"""Exact external-checker contract fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.identifiers import new_record_id
from app.modules.checkers.api.external import (
    POST_SUBMIT_INPUT_SCHEMA_ID,
    PRE_SUBMIT_INPUT_SCHEMA_ID,
    RESULT_SCHEMA_ID,
    ExternalCheckerCapabilityDefinition,
    ExternalCheckerCapabilityProjection,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistrySpec,
    ExternalCheckerResourceLimits,
    ExternalCheckerSchema,
    PostSubmitExternalCheckerMaterial,
    PostSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerMaterial,
    PreSubmitExternalCheckerIdentity,
    external_checker_json_hash,
    make_external_checker_registration_request,
)
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_CHECKER_ID,
    WORKSTREAM_DEFAULT_CHECKER_VERSION,
)

SHA = "sha256:" + "a" * 64


def schema(schema_id: str, *, required: tuple[str, ...] = ()) -> ExternalCheckerSchema:
    document = {"type": "object"}
    if schema_id != RESULT_SCHEMA_ID:
        document.update(
            properties={name: {"type": "string"} for name in required},
            required=list(required),
            additionalProperties=False,
        )
    return ExternalCheckerSchema(
        schema_id=schema_id,
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )


def registry_spec(
    phase: str = "pre_submit", *, maximum_output_bytes: int = 32_768
) -> ExternalCheckerRegistrySpec:
    return ExternalCheckerRegistrySpec(
        capability_id="acme.safe_archive",
        capability_version="v1.2.3",
        phase=phase,
        image_digest=SHA,
        configuration_schema=schema("acme.safe_archive.configuration"),
        input_schema=schema(
            PRE_SUBMIT_INPUT_SCHEMA_ID if phase == "pre_submit" else POST_SUBMIT_INPUT_SCHEMA_ID,
            required=("task_version",),
        ),
        output_schema=schema(RESULT_SCHEMA_ID),
        resources=ExternalCheckerResourceLimits(
            cpu_millis=500,
            memory_bytes=128 * 1024 * 1024,
            deadline_ms=30_000,
            maximum_output_bytes=maximum_output_bytes,
        ),
    )


def post_registry_spec() -> ExternalCheckerRegistrySpec:
    """Return the exact selected POST schema used by native execution fixtures."""
    values = registry_spec("post_submit").model_dump(mode="json")
    document = {"type": "object"}
    values["input_schema"] = ExternalCheckerSchema(
        schema_id=POST_SUBMIT_INPUT_SCHEMA_ID,
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    ).model_dump(mode="json")
    return ExternalCheckerRegistrySpec.model_validate(values)


def registry_entry(
    phase: str = "pre_submit", *, maximum_output_bytes: int = 32_768
) -> ExternalCheckerRegistryEntry:
    spec = registry_spec(phase, maximum_output_bytes=maximum_output_bytes)
    return ExternalCheckerRegistryEntry(
        **spec.model_dump(),
        registry_entry_id=new_record_id(),
        entry_digest=spec.spec_digest,
        registration_operation_id=uuid4(),
        registered_by_actor_profile_id=uuid4(),
        authorization_decision_event_id=uuid4(),
        created_at=datetime.now(timezone.utc),
    )


def capability_projection(
    *entries: ExternalCheckerRegistryEntry,
) -> ExternalCheckerCapabilityProjection:
    """Build the one code-owned default plus exact immutable registry entries."""
    definitions = tuple(
        sorted(
            (
                ExternalCheckerCapabilityDefinition(
                    capability_id=WORKSTREAM_DEFAULT_CHECKER_ID,
                    capability_version=WORKSTREAM_DEFAULT_CHECKER_VERSION,
                    phase="pre_submit",
                    selectable=False,
                ),
                *(
                    ExternalCheckerCapabilityDefinition(
                        capability_id=entry.capability_id,
                        capability_version=entry.capability_version,
                        phase=entry.phase,
                        selectable=True,
                        registry_entry=entry,
                    )
                    for entry in entries
                ),
            ),
            key=lambda item: (item.phase, item.capability_id, item.capability_version),
        )
    )
    body = {
        "schema_version": "external_checker_capabilities.v1",
        "definitions": [item.model_dump(mode="json") for item in definitions],
    }
    return ExternalCheckerCapabilityProjection(
        definitions=definitions,
        manifest_sha256=external_checker_json_hash(body),
    )


def registration_request(phase: str = "pre_submit", *, actor_profile_id=None):
    return make_external_checker_registration_request(
        actor_profile_id=actor_profile_id or uuid4(),
        operation_id=uuid4(),
        registry_entry_id=new_record_id(),
        spec=registry_spec(phase),
    )


def execution_identity(phase: str = "pre_submit"):
    common = dict(project_id=uuid4(), task_id=uuid4(), assignment_id=uuid4())
    if phase == "pre_submit":
        return PreSubmitExternalCheckerIdentity(
            **common,
            prepared_generation_id=uuid4(),
            attempt_id=uuid4(),
            attempt_request_digest=SHA,
            effective_plan_sha256=SHA,
        )
    return PostSubmitExternalCheckerIdentity(
        **common,
        submission_id=uuid4(),
        submission_version=2,
        evaluation_request_id=uuid4(),
        evaluation_request_digest=SHA,
        evaluation_generation=3,
        attempt_id=uuid4(),
        result_id=uuid4(),
        lease_id=uuid4(),
        lease_generation=4,
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )


def execution_material(identity):
    """Build one genuine phase-specific custody value for a test identity."""
    if identity.phase == "pre_submit":
        return PreSubmitExternalCheckerMaterial(
            role="submission_archive",
            prepared_generation_id=identity.prepared_generation_id,
            attempt_id=identity.attempt_id,
            attempt_request_digest=identity.attempt_request_digest,
            archive_sha256=SHA,
            archive_byte_count=4,
            semantic_manifest_sha256=SHA,
            media_type="application/zip",
        )
    return PostSubmitExternalCheckerMaterial(
        role="submission_archive",
        submission_id=identity.submission_id,
        submission_version=identity.submission_version,
        binding_id=uuid4(),
        content_id=uuid4(),
        replica_id=uuid4(),
        content_sha256=SHA,
        byte_count=4,
        media_type="application/zip",
        evidence_id=uuid4(),
        verification_receipt_id=uuid4(),
        verification_job_id=uuid4(),
        verification_generation=1,
        namespace_fingerprint=SHA,
        semantic_manifest_sha256=SHA,
    )
