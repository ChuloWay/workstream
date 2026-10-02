"""Closed source metadata, without authority, effects or a creation operation."""

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class FinalAcceptanceInput(BaseModel):
    """One exclusive source; owner validation and future AUTH custody remain required."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: UUID
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    acceptance_source: Literal["human_review", "task_post_submit_route"]
    source_review_id: UUID | None
    source_routing_manifest_id: UUID | None
    accepted_submitter_id: UUID
    recorded_by: UUID
    policy_context_ref: UUID

    @model_validator(mode="after")
    def exclusive_source(self) -> Self:
        human = self.acceptance_source == "human_review"
        if (self.source_review_id is not None) != human or (
            self.source_routing_manifest_id is not None
        ) == human:
            raise ValueError("acceptance source identity is not exclusive")
        return self
