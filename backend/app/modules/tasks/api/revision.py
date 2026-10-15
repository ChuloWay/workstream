"""Frozen revision context and bounded contributor change-summary contracts."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.modules.tasks.api.transition_audit import TaskPolicyLineage


class RevisionContextSnapshot(BaseModel):
    """One complete activated context, independent of the task's mutable locks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    guide_id: UUID
    activation_operation_id: UUID
    activation_generation: int = Field(gt=0)
    activated_at: AwareDatetime
    lineage: TaskPolicyLineage


class RevisionCandidate(BaseModel):
    """Server-selected context under PROJECT custody; not mutation authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prior: RevisionContextSnapshot
    target: RevisionContextSnapshot | None
    target_post_policy_json: str | None = Field(default=None, max_length=262144)
    max_revision_rounds: int = Field(gt=0)
    revision_deadline_hours: int = Field(gt=0)
    target_max_revision_rounds: int | None = Field(default=None, gt=0)


class RevisionContextChange(BaseModel):
    """One bounded policy identity change, without provider or finance internals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component: Literal["guide", "source", "artifact", "pre_submit", "post_submit", "review", "revision", "contribution"]
    before: str = Field(min_length=1, max_length=200)
    after: str = Field(min_length=1, max_length=200)


class ContributorRevisionContext(BaseModel):
    """Frozen preparation plus an eligibility projection evaluated at database time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    preparation_id: UUID
    preparation_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    predecessor_preparation_id: UUID | None
    source_submission_id: UUID
    source_routing_manifest_id: UUID
    sequence: int = Field(gt=0)
    next_revision_round: int = Field(gt=0)
    max_revision_rounds: int = Field(gt=0)
    requested_at: AwareDatetime
    deadline_at: AwareDatetime
    outcome: Literal["kept", "rebased", "blocked"]
    disposition: Literal["ready", "context_blocked", "revision_limit_reached", "revision_deadline_expired"]
    direction: Literal["kept", "forward", "backward"] | None
    prior: RevisionContextSnapshot
    target: RevisionContextSnapshot | None
    changes: tuple[RevisionContextChange, ...] = Field(max_length=8)
