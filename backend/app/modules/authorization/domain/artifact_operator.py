"""Exact system Operator contexts for ART diagnostics and recovery."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.authorization.catalogue import ActionId


ARTIFACT_OPERATOR_READ_RESOURCES = {
    ActionId.ARTIFACT_BINDING_READ: "artifact_binding_scope",
    ActionId.ARTIFACT_REPLICA_READ: "artifact_content",
    ActionId.ARTIFACT_RECEIPT_READ: "artifact_replica",
    ActionId.ARTIFACT_VERIFICATION_JOB_READ: "artifact_verification_job",
    ActionId.ARTIFACT_RECOVERY_ATTEMPT_READ: "artifact_recovery_attempt",
    ActionId.ARTIFACT_AUDIT_READ: "artifact_audit_resource",
    ActionId.OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ: "artifact_admission_scope",
}
ARTIFACT_OPERATOR_READ_ACTIONS = frozenset(ARTIFACT_OPERATOR_READ_RESOURCES)
ARTIFACT_OPERATOR_ACTIONS = ARTIFACT_OPERATOR_READ_ACTIONS | {
    ActionId.ARTIFACT_VERIFICATION_JOB_RETRY,
}


class ArtifactOperatorReadResourceContext(BaseModel):
    """ART-composed canonical selector; never a client-supplied project scope."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal[
        "artifact_binding_scope",
        "artifact_content",
        "artifact_replica",
        "artifact_verification_job",
        "artifact_recovery_attempt",
        "artifact_audit_resource",
        "artifact_admission_scope",
    ]
    resource_id: UUID | Literal["workstream:artifact_storage_readiness"]
    selector: str = Field(min_length=1)
    project_ids: tuple[UUID, ...]
    action_id: ActionId
    identity_link_id: UUID

    @model_validator(mode="after")
    def exact_shape(self):
        if ARTIFACT_OPERATOR_READ_RESOURCES.get(self.action_id) != self.resource_type:
            raise ValueError("artifact Operator action/resource mismatch")
        if self.project_ids != tuple(sorted(set(self.project_ids))):
            raise ValueError("artifact Operator projects are not canonical")
        readiness = self.resource_id == "workstream:artifact_storage_readiness"
        if readiness != (self.selector == "artifact-storage-readiness"):
            raise ValueError("artifact Operator readiness selector mismatch")
        if readiness and (
            self.action_id is not ActionId.OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ
            or self.project_ids
        ):
            raise ValueError("artifact Operator readiness shape mismatch")
        if not readiness and not self.project_ids:
            raise ValueError("artifact Operator resource has no project lineage")
        return self


class ArtifactOperatorRetryResourceContext(BaseModel):
    """ART-locked source and request facts for independently guarded retry."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["artifact_verification_job"] = "artifact_verification_job"
    resource_id: UUID
    project_id: UUID
    task_id: UUID
    submission_id: UUID | None
    expected_source_job_cas_version: int = Field(ge=0)
    identity_link_id: UUID
