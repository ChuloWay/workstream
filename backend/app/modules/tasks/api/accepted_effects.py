"""Source-neutral TASK participant contract for future final acceptance."""

from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

_Sha256 = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
_PositiveVersion = Annotated[StrictInt, Field(ge=1, le=2_147_483_647)]


class TaskAcceptedEffectsUnavailable(RuntimeError):
    """Conceal absent, foreign, stale, or invalid TASK acceptance state."""


class TaskAcceptedEffectsRequest(BaseModel):
    """Exact TASK identity and lineage selected by the acceptance owner."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    submission_id: UUID
    submission_version: _PositiveVersion
    contributor_id: UUID
    contribution_policy_version_id: UUID
    content_id: UUID
    content_sha256: _Sha256
    final_acceptance_id: UUID
    expected_task_status: Literal["evaluation_pending", "review_pending"]


class TaskAcceptedEffectsResult(BaseModel):
    """Exact accepted request identity and the two TASK-owned terminal states."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    request: TaskAcceptedEffectsRequest
    task_status: Literal["accepted"]
    assignment_status: Literal["completed"]


class TaskAcceptedEffectsPort(Protocol):
    """Apply flush-only TASK effects inside the caller's one root transaction.

    The participant never commits, authorizes, creates REV or CON facts, or calls
    back into routing.
    """

    async def apply_accepted_effects(
        self, request: TaskAcceptedEffectsRequest
    ) -> TaskAcceptedEffectsResult:
        """Validate exact TASK state and lineage, then flush accepted effects."""
        ...


__all__ = (
    "TaskAcceptedEffectsPort",
    "TaskAcceptedEffectsRequest",
    "TaskAcceptedEffectsResult",
    "TaskAcceptedEffectsUnavailable",
)
