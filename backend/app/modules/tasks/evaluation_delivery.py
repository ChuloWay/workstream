"""Recover a committed initial or Operator-retry evaluation request."""

from collections.abc import Callable
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable, EvaluationCoordinationPort, REQUEST_EVENT,
)
from app.modules.checkers.api.evaluation_contract import (
    PostSubmissionExecutionRequest,
)
from app.modules.outbox.api import (
    CommittedInvocationPort, HandlerOutcome, OutboxEventEnvelope,
)
from app.modules.tasks.models import SubmissionDispatch
from app.modules.tasks.submission_dispatch import evaluation_request_event


class EvaluationDeliveryUnavailable(RuntimeError):
    """The event and its retained request do not have exact custody."""


class EvaluationDeliveryRequestReader:
    """TASK owns initial dispatch; CHECKERS owns retry and stored request facts."""

    def __init__(self, session: AsyncSession, evaluations: EvaluationCoordinationPort):
        self._session, self._evaluations = session, evaluations

    async def read(self, envelope: OutboxEventEnvelope) -> PostSubmissionExecutionRequest:
        """Select all owner identifiers together, without creating or repairing rows."""
        retry = await self._evaluations.read_retry_delivery(
            project_id=envelope.claim.project_id,
            submission_id=envelope.aggregate_id,
            event_id=envelope.claim.event_id,
        )
        receipt = await self._session.scalar(select(SubmissionDispatch).where(
            SubmissionDispatch.project_id == str(envelope.claim.project_id),
            SubmissionDispatch.submission_id == str(envelope.aggregate_id),
            SubmissionDispatch.evaluation_event_id == envelope.claim.event_id,
        ).execution_options(populate_existing=True))
        if (receipt is None) == (retry is None):
            raise EvaluationDeliveryUnavailable("evaluation_delivery_unavailable")
        if receipt is not None:
            expected = evaluation_request_event(receipt)
            expected_payload = json.dumps(
                expected.payload, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            )
            expected_digest = canonical_json_hash(expected.payload)
        else:
            expected = retry.expected_event
            expected_payload = expected.payload_json
            expected_digest = expected.payload_digest
        if (
            any(getattr(envelope, name) != getattr(expected, name) for name in (
                "event_type", "event_version", "aggregate_type", "aggregate_id",
                "correlation_id", "causation_event_id", "idempotency_key",
            ))
            or envelope.payload_json != expected_payload
            or envelope.claim.payload_digest != expected_digest
        ):
            raise EvaluationDeliveryUnavailable("evaluation_delivery_unavailable")
        if retry is not None:
            return retry.request
        stored = await self._evaluations.read_reserved_evaluation(
            project_id=UUID(receipt.project_id), task_id=UUID(receipt.task_id),
            submission_id=UUID(receipt.submission_id),
            request_id=UUID(receipt.evaluation_request_id),
        )
        request, reservation = stored.request, stored.reservation
        if (
            (reservation.request_id, reservation.request_digest,
             reservation.attempt_id, reservation.result_id, reservation.evaluation_generation)
            != (UUID(receipt.evaluation_request_id), receipt.evaluation_request_digest,
                UUID(receipt.evaluation_attempt_id), UUID(receipt.evaluation_result_id), 1)
            or (request.project_id, request.task_id, request.submission_id,
                request.submission_version, request.assignment_id, request.binding_id,
                request.content_id, request.evaluation_request_id, request.request_sha256,
                request.evaluation_generation)
            != (UUID(receipt.project_id), UUID(receipt.task_id), UUID(receipt.submission_id),
                receipt.submission_version, UUID(receipt.assignment_id),
                UUID(receipt.artifact_binding_id), UUID(receipt.artifact_content_id),
                UUID(receipt.evaluation_request_id), receipt.evaluation_request_digest, 1)
        ):
            raise EvaluationDeliveryUnavailable("evaluation_delivery_unavailable")
        return request


class EvaluationRequestHandler:
    """Hidden typed handler; only shared outbox decides delivery/retry state."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], *,
        observer: CommittedInvocationPort,
        evaluations: Callable[[AsyncSession], EvaluationCoordinationPort],
        executor: Callable[[OutboxEventEnvelope, PostSubmissionExecutionRequest], object],
    ):
        self._sessions, self._observer = sessions, observer
        self._evaluations, self._executor = evaluations, executor

    async def __call__(self, envelope: OutboxEventEnvelope) -> HandlerOutcome:
        """Reject before execution; uncertain executor effects remain UNKNOWN."""
        try:
            envelope = OutboxEventEnvelope.model_validate(envelope.model_dump())
        except (AttributeError, TypeError, ValueError):
            return HandlerOutcome.REJECT
        if envelope.event_type != REQUEST_EVENT or envelope.event_version != 1:
            return HandlerOutcome.REJECT
        observed = await self._observer.observe_invocation(envelope)
        if observed is None or observed.claim != envelope.claim:
            return HandlerOutcome.REJECT
        try:
            async with self._sessions() as session, session.begin():
                request = await EvaluationDeliveryRequestReader(
                    session, self._evaluations(session),
                ).read(envelope)
        except (EvaluationDeliveryUnavailable, CheckerExecutionUnavailable):
            return HandlerOutcome.REJECT
        # The composed executor rechecks TASK, AUTH, CHECKERS and this invocation
        # inside each phase transaction. Exceptions/cancellation must propagate.
        result = await self._executor(envelope, request).evaluate_post_submission(request)
        result.validate_request(request)
        return HandlerOutcome.ACKNOWLEDGE
