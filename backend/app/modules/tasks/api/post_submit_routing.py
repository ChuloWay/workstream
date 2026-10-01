"""Detached TASK source facts for future post-submit routing."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from app.modules.tasks.api.transition_audit import TaskPolicyLineage

_Sha256 = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
_PositiveVersion = Annotated[StrictInt, Field(ge=1, le=2_147_483_647)]
_ByteCount = Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]


class TaskPostSubmitManifestFacts(BaseModel):
    """Immutable persisted and owner-joined source facts without routing authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: UUID
    created_at: AwareDatetime
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    submission_version: _PositiveVersion
    assignment_id: UUID
    contributor_id: UUID
    contribution_policy_version_id: UUID
    checker_run_id: UUID
    evaluation_request_id: UUID
    request_digest: _Sha256
    evaluation_generation: _PositiveVersion
    result_id: UUID
    result_digest: _Sha256
    completion_event_id: UUID
    execute_evidence_id: UUID
    finalize_evidence_id: UUID
    human_review_required: StrictBool
    replica_id: UUID
    content_sha256: _Sha256
    byte_count: _ByteCount
    semantic_manifest_sha256: _Sha256

    predecessor_submission_id: UUID | None
    predecessor_submission_version: _PositiveVersion | None
    admission_id: UUID
    binding_id: UUID
    content_id: UUID
    locked_policy: TaskPolicyLineage
    routing_recommendation: Literal["allow_review"]

    @model_validator(mode="after")
    def validate_detached_lineage(self) -> Self:
        """Keep nested policy and immediate predecessor facts internally exact."""
        if (
            self.locked_policy.locked_contribution_policy_version_id
            != self.contribution_policy_version_id
        ):
            raise ValueError("routing source contribution policy lineage differs")
        if self.execute_evidence_id == self.finalize_evidence_id:
            raise ValueError("routing source phase receipts are not distinct")

        has_predecessor_id = self.predecessor_submission_id is not None
        has_predecessor_version = self.predecessor_submission_version is not None
        if has_predecessor_id != has_predecessor_version:
            raise ValueError("routing source predecessor identity is incomplete")
        if self.submission_version == 1:
            if has_predecessor_id:
                raise ValueError("initial routing source has a predecessor")
            return self
        if not has_predecessor_id:
            raise ValueError("successor routing source lacks a predecessor")
        if self.predecessor_submission_id == self.submission_id:
            raise ValueError("routing source predecessor equals submission")
        if self.predecessor_submission_version != self.submission_version - 1:
            raise ValueError("routing source predecessor version is inconsistent")
        return self


__all__ = ("TaskPostSubmitManifestFacts",)
