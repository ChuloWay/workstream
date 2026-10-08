"""TASK-owned retained creation reads, independent of today's task lifecycle state."""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api import (
    SubmissionCreationRequest, SubmissionCreationUnavailable, SubmissionPredecessorFacts,
    TaskLockedProjectContextReferences, TaskPolicyLineage, TaskSubmissionContextFacts,
)
from app.modules.tasks.models import Submission, TaskAssignment, WorkstreamTask
from app.modules.tasks.submission_dispatch import SubmissionDispatch, creation_request_digest


async def read_creation_replay(
    session: AsyncSession, task: WorkstreamTask, request: SubmissionCreationRequest,
) -> tuple[SubmissionDispatch, TaskSubmissionContextFacts] | None:
    """Caller holds TASK; scope all replay selectors before taking child locks."""
    receipt = await session.scalar(select(SubmissionDispatch).where(
        SubmissionDispatch.project_id == task.project_id,
        SubmissionDispatch.task_id == str(request.task_id),
        SubmissionDispatch.assignment_id == str(request.assignment_id),
        SubmissionDispatch.contributor_id == str(request.contributor_id),
        SubmissionDispatch.admission_id == str(request.admission_id),
    ).execution_options(populate_existing=True))
    if receipt is None:
        return None
    invalid = SubmissionCreationUnavailable("submission creation is unavailable")
    if receipt.request_digest != creation_request_digest(request):
        raise invalid
    assignment = await session.scalar(select(TaskAssignment).where(
        TaskAssignment.project_id == task.project_id,
        TaskAssignment.task_id == task.id,
        TaskAssignment.id == str(request.assignment_id),
        TaskAssignment.contributor_id == str(request.contributor_id),
    ).with_for_update().execution_options(populate_existing=True))
    submission = await session.scalar(select(Submission).where(
        Submission.id == str(receipt.submission_id), Submission.task_id == task.id,
        Submission.task_assignment_id == str(request.assignment_id),
        Submission.contributor_id == str(request.contributor_id),
        Submission.submission_bundle_admission_id == str(request.admission_id),
    ).with_for_update().execution_options(populate_existing=True))
    if assignment is None or submission is None:
        raise invalid
    predecessor_id = str(request.predecessor_submission_id) if request.predecessor_submission_id else None
    if (
        submission.version != receipt.submission_version
        or submission.supersedes_submission_id != predecessor_id
        or submission.summary != request.summary
        or submission.worker_attestation != request.contributor_attestation
        or submission.artifact_binding_id != str(receipt.artifact_binding_id)
        or submission.artifact_content_id != str(receipt.artifact_content_id)
        or submission.contribution_policy_version_id != assignment.submitter_contribution_policy_version_id
        or receipt.creation_kind != ("revision" if predecessor_id else "initial")
        or receipt.creation_status != ("needs_revision" if predecessor_id else "in_progress")
    ):
        raise invalid
    predecessor = None
    if predecessor_id:
        version = await session.scalar(select(Submission.version).where(
            Submission.id == predecessor_id, Submission.task_id == task.id,
            Submission.contributor_id == submission.contributor_id,
        ))
        if version is None or version + 1 != submission.version:
            raise invalid
        predecessor = SubmissionPredecessorFacts(request.predecessor_submission_id, version)
    elif submission.version != 1:
        raise invalid
    try:
        policy = TaskPolicyLineage.model_validate_json(json.dumps({
            name: str(value) if isinstance(value, UUID) else value
            for name in TaskPolicyLineage.model_fields
            for value in (getattr(submission, name if name != "locked_contribution_policy_version_id"
                                 else "contribution_policy_version_id"),)
        }))
        refs = TaskLockedProjectContextReferences(
            project_id=UUID(task.project_id),
            locked_contribution_policy_version_id=submission.contribution_policy_version_id,
            guide_version=policy.locked_guide_version,
            source_snapshot_id=policy.locked_guide_source_snapshot_id,
            source_snapshot_hash=policy.locked_guide_source_snapshot_hash,
            effective_policy_id=policy.locked_effective_project_submission_artifact_policy_id,
            effective_policy_hash=policy.locked_effective_project_submission_artifact_policy_hash,
            pre_submit_policy_id=policy.locked_pre_submit_checker_policy_id,
            pre_submit_policy_bundle_hash=policy.locked_pre_submit_checker_bundle_hash,
        )
        # These are the original creation facts recorded by this receipt, not a
        # claim that the task still has its pre-submission lifecycle status.
        context = TaskSubmissionContextFacts(
            task_id=request.task_id, assignment_id=request.assignment_id,
            contributor_id=request.contributor_id, status=receipt.creation_status,
            kind=receipt.creation_kind, predecessor=predecessor,
            submitter_contribution_policy_version_id=submission.contribution_policy_version_id,
            locked_project_context=refs, locked_policy=policy,
            acceptance_criteria=task.acceptance_criteria,
        )
    except (ValueError, TypeError, AttributeError) as exc:
        raise invalid from exc
    return receipt, context
