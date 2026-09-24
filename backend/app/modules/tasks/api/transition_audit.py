"""TASK transition facts passed to the shared audit owner."""

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

from app.modules.tasks.api.authorization import TaskAuthorityDecision, TaskAuthorityOperation


class TaskPolicyLineage(BaseModel):
    """Complete bounded policy identities; no policy body or arbitrary metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    locked_guide_version: str = Field(pattern=r"\S")
    locked_guide_source_snapshot_id: UUID
    locked_guide_source_snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    locked_effective_project_submission_artifact_policy_id: UUID
    locked_effective_project_submission_artifact_policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    locked_pre_submit_checker_policy_id: UUID
    locked_pre_submit_checker_bundle_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    locked_post_submit_checker_policy_id: UUID
    locked_post_submit_checker_policy_version: str = Field(pattern=r"\S")
    locked_post_submit_checker_policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    locked_review_policy_id: UUID
    locked_review_policy_generation: int = Field(gt=0)
    locked_review_policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    locked_revision_policy_id: UUID
    locked_revision_policy_generation: int = Field(gt=0)
    locked_revision_policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    locked_contribution_policy_version_id: UUID


@dataclass(frozen=True, slots=True)
class TaskTransitionFacts:
    operation: TaskAuthorityOperation
    project_id: UUID
    task_id: UUID
    assignment_id: UUID | None
    actor_profile_id: UUID
    authorization_decision_id: UUID
    from_status: str | None
    to_status: str
    reason: str | None
    source_type: Literal["manual", "markdown_import", "csv_import"] | None = None
    locked_lineage: TaskPolicyLineage | None = None
    authority: TaskAuthorityDecision | None = None


class TaskTransitionAuditPort(Protocol):
    async def record(self, facts: TaskTransitionFacts) -> None: ...
