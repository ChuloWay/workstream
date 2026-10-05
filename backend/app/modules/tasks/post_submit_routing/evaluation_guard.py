"""TASK custody required before evaluation reservations and current-result reads."""

from dataclasses import asdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.checkers.api.post_submit import PostSubmissionEvaluationRequest
from app.modules.tasks.api.submitted_bundle import SubmittedBundleRequest, SubmittedBundleUnavailable
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.submitted_bundle import SubmittedBundleReader


class TaskEvaluationGuard:
    """Lock current TASK scope without granting execution or changing product state."""

    def __init__(self, session: AsyncSession):
        self._repository = TaskRepository(session)
        self._submitted = SubmittedBundleReader(session)

    async def lock_evaluation_scope(self, request: PostSubmissionEvaluationRequest) -> bool:
        """Return new-generation eligibility after exact Task/Assignment/Submission locks."""
        task = await self._repository.lock_project_task(request.project_id, request.task_id)
        if task is None:
            raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable")
        assignment = await self._repository.lock_accepted_assignment(
            project_id=request.project_id, task_id=request.task_id,
            assignment_id=request.assignment_id,
        )
        latest = await self._repository.get_latest_submission_for_task(
            str(request.task_id), for_update=True, populate_existing=True,
        )
        if assignment is None or latest is None or not (
            latest.id == str(request.submission_id)
            and latest.version == request.submission_version
            and latest.status == "submitted"
            and latest.task_assignment_id == assignment.id
            and latest.contributor_id == assignment.contributor_id
            and task.assigned_to == latest.contributor_id
        ):
            raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable")
        try:
            facts = await self._submitted.read(SubmittedBundleRequest(
                request.project_id, request.task_id, request.submission_id,
            ))
        except SubmittedBundleUnavailable:
            raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable") from None
        if not (
            facts.assignment_id == request.assignment_id
            and facts.submission_version == request.submission_version
            and facts.contributor_id == UUID(assignment.contributor_id)
            and facts.binding_id == request.binding_id
            and facts.content_id == request.content_id
            and asdict(facts.context) == request.expected_context.model_dump()
        ):
            raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable")
        if task.status in {"accepted", "rejected"}:
            return False
        if task.status not in {
            "in_progress", "submitted", "evaluation_pending", "review_pending", "needs_revision",
        } or assignment.status != "active" or assignment.released_at is not None:
            raise CheckerExecutionUnavailable("checker_reservation_scope_unavailable")
        return True
