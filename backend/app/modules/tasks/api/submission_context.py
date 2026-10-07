"""Public TASK contracts for locked Submission lifecycle context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, get_args
from uuid import UUID

from app.modules.tasks.api.transition_audit import TaskPolicyLineage

TaskSubmissionContextKind = Literal["initial", "revision"]
TaskSubmissionContextStatus = Literal["in_progress", "needs_revision"]
TaskSubmissionContextFailure = Literal[
    "task_submission_context_invalid",
    "task_submission_predecessor_changed",
]


class TaskSubmissionContextUnavailable(RuntimeError):
    """Report one stable failure without exposing TASK persistence."""

    def __init__(self, code: TaskSubmissionContextFailure) -> None:
        """Validate and retain one failure from the public closed set."""
        if code not in get_args(TaskSubmissionContextFailure):
            raise ValueError("task submission context failure code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TaskSubmissionContextRequest:
    """Exact TASK-owned selectors supplied to a transaction-bound port."""

    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    predecessor_submission_id: UUID | None


@dataclass(frozen=True, slots=True)
class TaskLockedProjectContextReferences:
    """Immutable project-policy references locked onto one TASK row."""

    project_id: UUID
    locked_contribution_policy_version_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    effective_policy_id: UUID
    effective_policy_hash: str
    pre_submit_policy_id: UUID
    pre_submit_policy_bundle_hash: str

    def __post_init__(self) -> None:
        """Reject incomplete locked string references."""
        if not isinstance(self.locked_contribution_policy_version_id, UUID):
            raise ValueError("task contribution policy identity is invalid")
        values = (
            self.guide_version,
            self.source_snapshot_hash,
            self.effective_policy_hash,
            self.pre_submit_policy_bundle_hash,
        )
        if any(not value.strip() for value in values):
            raise ValueError("task locked project context reference is empty")


@dataclass(frozen=True, slots=True)
class SubmissionPredecessorFacts:
    """TASK-owned identity of the immediate immutable Submission predecessor."""

    submission_id: UUID
    version: int

    def __post_init__(self) -> None:
        """Reject non-positive or non-integer Submission versions."""
        if type(self.version) is not int or self.version < 1:
            raise ValueError("submission predecessor version is invalid")


@dataclass(frozen=True, slots=True)
class TaskSubmissionContextFacts:
    """Locked TASK, assignment, predecessor, and project-reference facts."""

    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    status: TaskSubmissionContextStatus
    kind: TaskSubmissionContextKind
    predecessor: SubmissionPredecessorFacts | None
    submitter_contribution_policy_version_id: UUID
    locked_project_context: TaskLockedProjectContextReferences
    locked_policy: TaskPolicyLineage
    acceptance_criteria: str | None

    def __post_init__(self) -> None:
        """Enforce the exact initial-or-revision lifecycle shape."""
        if (
            not isinstance(self.submitter_contribution_policy_version_id, UUID)
            or self.submitter_contribution_policy_version_id
            != self.locked_project_context.locked_contribution_policy_version_id
        ):
            raise ValueError("assignment contribution policy differs from task")
        if self.acceptance_criteria is not None and type(self.acceptance_criteria) is not str:
            raise ValueError("task acceptance criteria is invalid")
        reference_fields = {
            "guide_version": "locked_guide_version",
            "source_snapshot_id": "locked_guide_source_snapshot_id",
            "source_snapshot_hash": "locked_guide_source_snapshot_hash",
            "effective_policy_id": "locked_effective_project_submission_artifact_policy_id",
            "effective_policy_hash": "locked_effective_project_submission_artifact_policy_hash",
            "pre_submit_policy_id": "locked_pre_submit_checker_policy_id",
            "pre_submit_policy_bundle_hash": "locked_pre_submit_checker_bundle_hash",
            "locked_contribution_policy_version_id": "locked_contribution_policy_version_id",
        }
        if any(getattr(self.locked_project_context, ref) != getattr(self.locked_policy, stamp)
               for ref, stamp in reference_fields.items()):
            raise ValueError("task submission context policy references differ")
        is_initial = (
            self.status == "in_progress"
            and self.kind == "initial"
            and self.predecessor is None
        )
        is_revision = (
            self.status == "needs_revision"
            and self.kind == "revision"
            and self.predecessor is not None
        )
        if not (is_initial or is_revision):
            raise ValueError("task submission context predecessor is inconsistent")


class TaskSubmissionContextPort(Protocol):
    """Transaction-bound TASK capability implemented inside the TASK module."""

    async def lock_submission_context(
        self,
        request: TaskSubmissionContextRequest,
    ) -> TaskSubmissionContextFacts:
        """Lock and return exact TASK-owned lifecycle facts."""
