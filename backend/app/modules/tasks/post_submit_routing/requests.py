"""Caller-owned routing request reservation, without routing authority or effects."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import EvaluationCompletion, EvaluationCoordinationPort
from app.modules.tasks.api.post_submit_routing import (
    TaskRoutingRequestFacts,
    TaskRoutingSelection,
    task_routing_request_digest,
)
from app.modules.tasks.models import Submission
from app.modules.tasks.post_submit_routing.models import TaskRoutingRequest
from app.modules.tasks.repository import TaskRepository


_OWNER_STRING_IDS = frozenset({"project_id", "task_id", "submission_id", "checker_run_id"})


class TaskRoutingRequestUnavailable(RuntimeError):
    """Conceal unavailable or inconsistent request preparation."""


class TaskRoutingRequests:
    """Reserve/recover one request inside a caller-owned transaction; never commit."""

    def __init__(self, session: AsyncSession, evaluations: EvaluationCoordinationPort):
        self._session = session
        self._evaluations = evaluations

    async def stage(
        self, event_id: UUID, completion: EvaluationCompletion
    ) -> TaskRoutingRequestFacts:
        """Revalidate latest Submission and current completion before reservation or replay."""
        transaction = self._session.get_transaction()
        if transaction is None or not transaction.is_active or self._session.in_nested_transaction():
            raise TaskRoutingRequestUnavailable("routing_request_caller_transaction_required")
        connection = await self._session.connection()
        if connection.in_nested_transaction():
            raise TaskRoutingRequestUnavailable("routing_request_caller_transaction_required")
        # PostgreSQL observes native savepoints which SQLAlchemy cannot see.
        # Discard the snapshot token; caller transaction completion owns cleanup.
        try:
            await self._session.execute(text("SELECT pg_catalog.pg_export_snapshot()"))
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) != "25001":
                raise
            raise TaskRoutingRequestUnavailable("routing_request_caller_transaction_required") from exc
        completion = EvaluationCompletion.model_validate(completion)
        if not isinstance(event_id, UUID) or completion.routing_recommendation != "allow_review":
            raise TaskRoutingRequestUnavailable("routing_request_unavailable")
        task = await TaskRepository(self._session).lock_project_task(
            completion.project_id, completion.task_id
        )
        if task is None:
            raise TaskRoutingRequestUnavailable("routing_request_unavailable")
        submission = await self._session.scalar(select(Submission).where(
            Submission.task_id == str(completion.task_id),
            Submission.id == str(completion.submission_id),
        ).with_for_update().execution_options(populate_existing=True))
        if submission is None or submission.status != "submitted":
            raise TaskRoutingRequestUnavailable("routing_request_unavailable")
        later = await self._session.scalar(select(Submission.id).where(
            Submission.task_id == submission.task_id,
            Submission.version > submission.version,
        ).limit(1))
        if later is not None:
            raise TaskRoutingRequestUnavailable("routing_request_unavailable")
        version = await self._evaluations.require_current_completion(event_id, completion)
        if version != submission.version:
            raise TaskRoutingRequestUnavailable("routing_request_unavailable")
        ref = completion.reference
        selection = TaskRoutingSelection(
            project_id=completion.project_id, task_id=completion.task_id,
            submission_id=completion.submission_id, submission_version=submission.version,
            checker_run_id=ref.attempt_id, evaluation_request_id=ref.request_id,
            evaluation_request_digest=ref.request_digest,
            evaluation_generation=ref.evaluation_generation, result_id=ref.result_id,
            result_digest=ref.result_digest, completion_event_id=event_id,
            routing_recommendation=completion.routing_recommendation,
        )
        digest = task_routing_request_digest(selection)
        prior = await self._session.scalar(select(TaskRoutingRequest).where(
            TaskRoutingRequest.submission_id == str(selection.submission_id),
            TaskRoutingRequest.checker_run_id == str(selection.checker_run_id),
            TaskRoutingRequest.result_digest == selection.result_digest,
        ).execution_options(populate_existing=True))
        if prior is None:
            prior = TaskRoutingRequest(
                **{key: str(value) if key in _OWNER_STRING_IDS else value
                   for key, value in selection.model_dump().items()},
                route_operation_id=new_record_id(),
                routing_manifest_id=new_record_id(), route_request_digest=digest,
            )
            self._session.add(prior)
            await self._session.flush()
        facts = TaskRoutingRequestFacts(**{
            key: UUID(getattr(prior, key)) if key in _OWNER_STRING_IDS else getattr(prior, key)
            for key in TaskRoutingRequestFacts.model_fields
        })
        if (
            facts.route_request_digest != digest
            or facts.model_dump(include=set(TaskRoutingSelection.model_fields)) != selection.model_dump()
        ):
            raise TaskRoutingRequestUnavailable("routing_request_conflict")
        return facts
