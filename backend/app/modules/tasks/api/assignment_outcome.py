"""Contributor-safe terminal assignment facts, independent of a task's new claim."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator


class TaskAssignmentOutcome(BaseModel):
    """An immutable rejected attempt with no remaining action on its assignment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assignment_id: UUID
    submission_id: UUID
    status: Literal["revision_exhausted", "revision_expired"]
    status_reason: Literal["revision_limit_reached", "revision_deadline_expired"]
    closed_at: AwareDatetime
    next_action: Literal["none"] = "none"

    @model_validator(mode="after")
    def exact_reason(self):
        """Keep exhaustion distinct from elapsed revision time."""
        expected = "revision_limit_reached" if self.status == "revision_exhausted" else "revision_deadline_expired"
        if self.status_reason != expected:
            raise ValueError("assignment outcome reason differs")
        return self
