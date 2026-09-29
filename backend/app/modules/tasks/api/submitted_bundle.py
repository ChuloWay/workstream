"""TASK-owned immutable Submission facts for internal materialization."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class SubmittedBundleUnavailable(RuntimeError):
    """Conceal absent, foreign or ineligible Submission material."""


@dataclass(frozen=True, slots=True)
class SubmittedBundleRequest:
    """Select one Submission within its exact project and task."""
    project_id: UUID
    task_id: UUID
    submission_id: UUID


@dataclass(frozen=True, slots=True)
class SubmittedPolicyContext:
    """Frozen Submission references, independent of current project selectors."""

    guide_version: str
    source_id: UUID
    source_hash: str
    effective_policy_id: UUID
    effective_policy_hash: str
    pre_policy_id: UUID
    pre_policy_hash: str
    post_policy_id: UUID
    post_policy_version: str
    post_policy_hash: str
    review_policy_id: UUID
    review_generation: int
    review_hash: str
    revision_policy_id: UUID
    revision_generation: int
    revision_hash: str


@dataclass(frozen=True, slots=True)
class SubmittedBundleFacts:
    """Detached exact ownership; no packet, policy body or storage coordinates."""

    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    submission_id: UUID
    submission_version: int
    status: str
    predecessor_id: UUID | None
    predecessor_version: int | None
    contribution_policy_version_id: UUID
    admission_id: UUID
    binding_id: UUID
    content_id: UUID
    context: SubmittedPolicyContext


class SubmittedBundlePort(Protocol):
    """Read immutable TASK facts without acquiring mutation authority."""
    async def read(self, request: SubmittedBundleRequest) -> SubmittedBundleFacts:
        """Read exact submitted ownership inside the caller's short transaction."""
