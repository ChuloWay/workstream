"""Closed contribution metadata without a recognition command or authority."""

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContributionRecordInput(BaseModel):
    """Exclusive source facts; SQL verifies the actual persisted owners."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: UUID
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    contribution_type: Literal["completed_review", "accepted_submission"]
    contributor_id: UUID
    source_review_id: UUID | None
    source_review_lease_id: UUID | None
    source_final_acceptance_id: UUID | None
    source_task_assignment_id: UUID | None
    artifact_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    contribution_policy_version_id: UUID

    @model_validator(mode="after")
    def exclusive_source(self) -> Self:
        reviewer = self.contribution_type == "completed_review"
        present = (
            self.source_review_id is not None,
            self.source_review_lease_id is not None,
            self.source_final_acceptance_id is not None,
            self.source_task_assignment_id is not None,
        )
        if present != (reviewer, reviewer, not reviewer, not reviewer):
            raise ValueError("contribution source identity is not exclusive and complete")
        return self
