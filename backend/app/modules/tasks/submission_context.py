"""TASK's exact contributor Submission context through the existing owner port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable,
    EvaluationCoordinationPort,
)
from app.modules.tasks.api.submission_context import (
    TaskSubmissionContextFacts,
    TaskSubmissionContextRequest,
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.repository import TaskRepository


class TaskSubmissionContextService:
    """Join TASK's locked source to CHECKERS currentness without a second port."""

    def __init__(self, session: AsyncSession, evaluations: EvaluationCoordinationPort) -> None:
        self._session = session
        self._tasks = TaskRepository(session)
        self._evaluations = evaluations

    async def lock_submission_context(
        self, request: TaskSubmissionContextRequest,
    ) -> TaskSubmissionContextFacts:
        """Return initial or exact current checker-remediation facts under one transaction."""
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
        facts, source = await self._tasks.select_submission_context(request)
        if source is None:
            return facts
        if facts.predecessor is None:
            raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
        try:
            retained = await self._evaluations.read_reserved_evaluation(
                project_id=facts.locked_project_context.project_id,
                task_id=facts.task_id,
                submission_id=facts.predecessor.submission_id,
                request_id=source.evaluation_request_id,
            )
            stored_request, reservation = retained.request, retained.reservation
            current = await self._evaluations.read_current_result(stored_request)
            reference = current.reference
            if not (
                stored_request.project_id == facts.locked_project_context.project_id
                and stored_request.task_id == facts.task_id
                and stored_request.assignment_id == facts.assignment_id
                and stored_request.submission_id == facts.predecessor.submission_id
                and stored_request.submission_version == facts.predecessor.version
                and stored_request.evaluation_request_id == source.evaluation_request_id
                and stored_request.request_sha256 == source.request_digest
                and stored_request.evaluation_generation == source.evaluation_generation
                and reservation.attempt_id == reference.attempt_id
                and reservation.result_id == reference.result_id
                and reference.request_id == source.evaluation_request_id
                and reference.request_digest == source.request_digest
                and reference.attempt_id == UUID(source.checker_run_id)
                and reference.evaluation_generation == source.evaluation_generation
                and reference.result_id == source.result_id
                and reference.result_digest == source.result_digest
                and current.routing_recommendation == "needs_revision"
            ):
                raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
            complete = await self._session.scalar(text(
                "SELECT public.task_routing_outcome_complete(m) "
                "FROM public.task_post_submit_routing_manifests m WHERE m.id=:id"
            ), {"id": source.id})
            if complete is not True:
                raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
        except (CheckerExecutionUnavailable, ValueError, TypeError) as exc:
            raise TaskSubmissionContextUnavailable("task_submission_context_invalid") from exc
        return facts
