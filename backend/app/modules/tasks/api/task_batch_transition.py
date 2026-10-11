"""Closed batch transition requests and compact canonical receipt projections."""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskBatchTransitionRequest(BaseModel):
    """One normal transition reason; membership comes only from the native batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: str | None = Field(default=None, max_length=4000)


class TaskBatchTransitionResult(BaseModel):
    """Ordered canonical success facts without repeating Task instructions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: UUID
    row_index: int = Field(ge=0, le=499)
    status: Literal["screening", "ready"]
    locked_guide_version: str = Field(min_length=1, max_length=100)
    locked_contribution_policy_version_id: UUID
    locked_context_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class TaskBatchTransitionResponse(BaseModel):
    """The complete original ordered result, recoverable only while all Tasks match."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    batch_id: UUID
    operation: Literal["screen", "release"]
    row_count: int = Field(ge=1, le=500)
    tasks: tuple[TaskBatchTransitionResult, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def complete_order(self):
        """Refuse partial, duplicated or incorrectly ordered public membership."""
        status = "screening" if self.operation == "screen" else "ready"
        if (len(self.tasks) != self.row_count
                or len({task.task_id for task in self.tasks}) != self.row_count
                or any(task.row_index != index or task.status != status
                       for index, task in enumerate(self.tasks))):
            raise ValueError("task batch transition membership is invalid")
        return self


class TaskBatchTransitionPort(Protocol):
    """Own one complete transition root; no caller may supply individual members."""

    async def screen(
        self, project_id: UUID, batch_id: UUID, reason: str | None, *, idempotency_key: UUID,
    ) -> TaskBatchTransitionResponse: ...

    async def release(
        self, project_id: UUID, batch_id: UUID, reason: str | None, *, idempotency_key: UUID,
    ) -> TaskBatchTransitionResponse: ...
