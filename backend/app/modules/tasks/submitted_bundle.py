"""Owner-qualified, nonlocking immutable Submission material projection."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.tasks.api.submitted_bundle import (
    SubmittedBundleFacts, SubmittedBundleRequest, SubmittedBundleUnavailable,
    SubmittedPolicyContext,
)
from app.modules.tasks.models import Submission, WorkstreamTask


class SubmittedBundleReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(self, request: SubmittedBundleRequest) -> SubmittedBundleFacts:
        """Select all scalar facts afresh, scoped before any row is returned."""
        predecessor = aliased(Submission)
        columns = (
            Submission.id,
            Submission.task_id,
            Submission.task_assignment_id,
            Submission.contributor_id,
            Submission.version,
            Submission.status,
            Submission.supersedes_submission_id,
            Submission.contribution_policy_version_id,
            Submission.submission_bundle_admission_id,
            Submission.artifact_binding_id,
            Submission.artifact_content_id,
            Submission.locked_guide_version,
            Submission.locked_guide_source_snapshot_id,
            Submission.locked_guide_source_snapshot_hash,
            Submission.locked_effective_project_submission_artifact_policy_id,
            Submission.locked_effective_project_submission_artifact_policy_hash,
            Submission.locked_pre_submit_checker_policy_id,
            Submission.locked_pre_submit_checker_bundle_hash,
            Submission.locked_post_submit_checker_policy_id,
            Submission.locked_post_submit_checker_policy_version,
            Submission.locked_post_submit_checker_policy_hash,
            Submission.locked_review_policy_id,
            Submission.locked_review_policy_generation,
            Submission.locked_review_policy_hash,
            Submission.locked_revision_policy_id,
            Submission.locked_revision_policy_generation,
            Submission.locked_revision_policy_hash,
        )
        row = (await self._session.execute(
            select(*columns, WorkstreamTask.project_id,
                   predecessor.version.label("predecessor_version"))
            .join(WorkstreamTask, WorkstreamTask.id == Submission.task_id)
            .outerjoin(predecessor, (predecessor.id == Submission.supersedes_submission_id)
                       & (predecessor.task_id == Submission.task_id))
            .where(WorkstreamTask.project_id == str(request.project_id),
                   Submission.task_id == str(request.task_id),
                   Submission.id == str(request.submission_id), Submission.status == "submitted")
        )).mappings().one_or_none()
        if row is None:
            raise SubmittedBundleUnavailable("submitted_bundle_unavailable")
        try:
            context = SubmittedPolicyContext(
                guide_version=row["locked_guide_version"],
                source_id=UUID(row["locked_guide_source_snapshot_id"]),
                source_hash=row["locked_guide_source_snapshot_hash"],
                effective_policy_id=UUID(row["locked_effective_project_submission_artifact_policy_id"]),
                effective_policy_hash=row["locked_effective_project_submission_artifact_policy_hash"],
                pre_policy_id=UUID(row["locked_pre_submit_checker_policy_id"]),
                pre_policy_hash=row["locked_pre_submit_checker_bundle_hash"],
                post_policy_id=UUID(row["locked_post_submit_checker_policy_id"]),
                post_policy_version=row["locked_post_submit_checker_policy_version"],
                post_policy_hash=row["locked_post_submit_checker_policy_hash"],
                review_policy_id=UUID(row["locked_review_policy_id"]),
                review_generation=row["locked_review_policy_generation"],
                review_hash=row["locked_review_policy_hash"],
                revision_policy_id=UUID(row["locked_revision_policy_id"]),
                revision_generation=row["locked_revision_policy_generation"],
                revision_hash=row["locked_revision_policy_hash"],
            )
            predecessor_id = row["supersedes_submission_id"]
            if (predecessor_id is None) != (row["predecessor_version"] is None):
                raise ValueError("predecessor unavailable")
            return SubmittedBundleFacts(
                project_id=UUID(row["project_id"]), task_id=UUID(row["task_id"]),
                assignment_id=UUID(row["task_assignment_id"]),
                contributor_id=UUID(row["contributor_id"]), submission_id=UUID(row["id"]),
                submission_version=row["version"], status=row["status"],
                predecessor_id=UUID(predecessor_id) if predecessor_id else None,
                predecessor_version=row["predecessor_version"],
                contribution_policy_version_id=row["contribution_policy_version_id"],
                admission_id=UUID(row["submission_bundle_admission_id"]),
                binding_id=UUID(row["artifact_binding_id"]),
                content_id=UUID(row["artifact_content_id"]), context=context,
            )
        except (ValueError, TypeError, AttributeError):
            raise SubmittedBundleUnavailable("submitted_bundle_unavailable") from None
