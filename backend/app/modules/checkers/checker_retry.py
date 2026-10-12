"""One hidden Operator retry of a terminal checker infrastructure failure."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable, CheckerRequestConflict, CheckerRetryAuditPort,
    CheckerRetryAuthorizationPort, CheckerRetryCommand, CheckerRetryDelivery,
    CheckerRetryEventExpectation,
    CheckerRetryPreparation, CheckerRetryResult, CheckerRetrySource,
    CheckerRetrySuccessor, EvaluationTaskGuard,
)
from app.modules.checkers.api.evaluation_contract import PostSubmissionExecutionRequest
from app.modules.checkers.api.post_submit import make_post_submit_request
from app.modules.checkers.api.selected_post_submit import (
    SelectedPostSubmissionEvaluationRequest,
    make_selected_post_submit_request,
)
from app.modules.checkers.execution_coordination import EvaluationCoordinator
from app.modules.checkers.execution_repository import (
    require_transaction, stored_request, stored_result,
)
from app.modules.checkers.models import CheckerRetryReceipt, CheckerRun
from app.modules.outbox.api import OutboxAppendInput, OutboxAppendPort


def _source_from_run(run: CheckerRun) -> tuple[PostSubmissionExecutionRequest, CheckerRetrySource]:
    """Require a real terminal result/finalization before any new Operator effect."""
    if (
        run.status != "infrastructure_failed" or run.finalize_evidence_id is None
        or run.result_json is None or run.result_digest is None
        or run.completion_event_id is not None or run.failure_code is None
    ):
        raise CheckerExecutionUnavailable("checker_retry_source_unavailable")
    request = stored_request(run)
    result = stored_result(run)
    if (
        result.outcome != "infrastructure_failed"
        or result.infrastructure_failure_code != run.failure_code
        or request.evaluation_generation != run.evaluation_generation
    ):
        raise CheckerExecutionUnavailable("checker_retry_source_unavailable")
    return request, CheckerRetrySource(
        project_id=request.project_id, task_id=request.task_id,
        assignment_id=request.assignment_id, submission_id=request.submission_id,
        submission_version=request.submission_version,
        source_run_id=UUID(run.id), source_request_id=request.evaluation_request_id,
        source_request_digest=request.request_sha256,
        source_result_id=UUID(run.result_id), source_result_digest=run.result_digest,
        source_finalize_evidence_id=UUID(run.finalize_evidence_id),
        source_generation=run.evaluation_generation, failure_code=run.failure_code,
    )


def _source_from_receipt(receipt: CheckerRetryReceipt) -> CheckerRetrySource:
    return CheckerRetrySource(
        project_id=UUID(receipt.project_id), task_id=UUID(receipt.task_id),
        assignment_id=UUID(receipt.assignment_id), submission_id=UUID(receipt.submission_id),
        submission_version=receipt.submission_version,
        source_run_id=UUID(receipt.source_run_id),
        source_request_id=UUID(receipt.source_request_id),
        source_request_digest=receipt.source_request_digest,
        source_result_id=UUID(receipt.source_result_id),
        source_result_digest=receipt.source_result_digest,
        source_finalize_evidence_id=UUID(receipt.source_finalize_evidence_id),
        source_generation=receipt.source_generation, failure_code=receipt.failure_code,
    )


def _successor_from_receipt(receipt: CheckerRetryReceipt) -> CheckerRetrySuccessor:
    return CheckerRetrySuccessor(
        request_id=UUID(receipt.successor_request_id),
        request_digest=receipt.successor_request_digest,
        run_id=UUID(receipt.successor_run_id),
        result_id=UUID(receipt.successor_result_id),
        generation=receipt.successor_generation,
        event_id=receipt.event_id,
        audit_event_id=UUID(receipt.audit_event_id),
    )


def retry_request_event(
    source: CheckerRetrySource, *, receipt_id: UUID, request_id: UUID,
    request_digest: str, run_id: UUID, result_id: UUID,
) -> OutboxAppendInput:
    """One v1 request event schema for creation and later exact delivery."""
    return OutboxAppendInput(
        event_type="PostSubmissionEvaluationRequested", event_version=1,
        aggregate_type="submission", aggregate_id=source.submission_id,
        project_id=source.project_id,
        correlation_id=str(source.source_run_id),
        idempotency_key="checker-retry:" + str(source.source_run_id),
        payload={
            "project_id": str(source.project_id), "task_id": str(source.task_id),
            "submission_id": str(source.submission_id),
            "submission_version": source.submission_version,
            "request_id": str(request_id), "request_digest": request_digest,
            "evaluation_generation": source.source_generation + 1,
            "attempt_id": str(run_id), "result_id": str(result_id),
            "source_run_id": str(source.source_run_id),
            "source_result_digest": source.source_result_digest,
            "retry_receipt_id": str(receipt_id),
        },
    )


class CheckerRetryService:
    """Compose existing TASK, AUTH, CHECKERS, OUTBOX and AUDIT owner operations."""

    def __init__(
        self, session: AsyncSession, *, actor_profile_id: UUID,
        tasks: EvaluationTaskGuard, evaluations: EvaluationCoordinator,
        authorization: CheckerRetryAuthorizationPort,
        events: OutboxAppendPort, audit: CheckerRetryAuditPort,
    ) -> None:
        self._session, self._actor_profile_id = session, actor_profile_id
        self._tasks, self._evaluations = tasks, evaluations
        self._authorization, self._events, self._audit = authorization, events, audit

    async def retry(self, command: CheckerRetryCommand) -> CheckerRetryResult:
        """Return one new authorized successor or the exact retained replay."""
        require_transaction(self._session)
        command = CheckerRetryCommand.model_validate(command)
        # Detached selectors only: no CHECKERS lock, AUTH custody or decision yet.
        existing = await self._session.scalar(select(CheckerRetryReceipt).where(
            CheckerRetryReceipt.actor_profile_id == str(self._actor_profile_id),
            CheckerRetryReceipt.request_key == str(command.request_key),
        ).execution_options(populate_existing=True))
        source_id = UUID(existing.source_run_id) if existing is not None else command.source_run_id
        source_run = await self._session.scalar(select(CheckerRun).where(
            CheckerRun.id == str(source_id), CheckerRun.phase == "post_submission",
        ).execution_options(populate_existing=True))
        if source_run is None:
            raise CheckerExecutionUnavailable("checker_retry_source_unavailable")
        source_request = stored_request(source_run)
        # Both branches first hold the same historical TASK owner rows. A
        # contender that saw no detached receipt must reread it after this
        # lock: the first transaction may have committed while it waited.
        await self._tasks.lock_retry_replay_scope(source_request)
        existing = await self._session.scalar(select(CheckerRetryReceipt).where(
            CheckerRetryReceipt.actor_profile_id == str(self._actor_profile_id),
            CheckerRetryReceipt.request_key == str(command.request_key),
        ).execution_options(populate_existing=True))
        if existing is not None and (
            existing.source_run_id != str(command.source_run_id)
            or existing.reason != command.reason
        ):
            raise CheckerRequestConflict("checker_retry_request_conflict")
        if existing is None:
            await self._tasks.lock_terminal_retry_scope(source_request)
        source_run = await self._session.scalar(select(CheckerRun).where(
            CheckerRun.id == str(source_id), CheckerRun.phase == "post_submission",
        ).execution_options(populate_existing=True))
        if source_run is None:
            raise CheckerExecutionUnavailable("checker_retry_source_unavailable")
        locked_request, source = _source_from_run(source_run)
        if locked_request != source_request:
            raise CheckerExecutionUnavailable("checker_retry_source_unavailable")
        if existing is not None:
            return await self._replay(command, existing, source)
        preparation = CheckerRetryPreparation(
            actor_profile_id=self._actor_profile_id,
            request_key=command.request_key, reason=command.reason, source=source,
        )
        handle = await self._authorization.prepare(preparation)
        try:
            request_fields = {
                **source_request.model_dump(exclude={
                    "evaluation_request_id", "evaluation_generation", "request_sha256",
                }),
                "evaluation_request_id": new_record_id(),
                "evaluation_generation": source.source_generation + 1,
            }
            next_request = (
                make_selected_post_submit_request(**request_fields)
                if isinstance(source_request, SelectedPostSubmissionEvaluationRequest)
                else make_post_submit_request(**request_fields)
            )
            reserved = await self._evaluations._reserve_after_task_lock(
                next_request, terminal_source_id=source.source_run_id,
            )
            if (
                reserved.request_id != next_request.evaluation_request_id
                or reserved.request_digest != next_request.request_sha256
                or reserved.evaluation_generation != source.source_generation + 1
            ):
                raise CheckerExecutionUnavailable("checker_retry_reservation_unavailable")
            receipt_id = new_record_id()
            event = await self._events.append(retry_request_event(
                source, receipt_id=receipt_id, request_id=reserved.request_id,
                request_digest=reserved.request_digest,
                run_id=reserved.attempt_id, result_id=reserved.result_id,
            ))
            successor = CheckerRetrySuccessor(
                request_id=reserved.request_id, request_digest=reserved.request_digest,
                run_id=reserved.attempt_id, result_id=reserved.result_id,
                generation=reserved.evaluation_generation,
                event_id=event.event_id, audit_event_id=new_record_id(),
            )
            authority = await self._authorization.consume(handle, preparation, successor)
            await self._audit.record(preparation, successor, authority)
            receipt = CheckerRetryReceipt(
                id=str(receipt_id), actor_profile_id=str(self._actor_profile_id),
                identity_link_id=str(authority.identity_link_id),
                request_key=str(command.request_key), reason=command.reason,
                project_id=str(source.project_id), task_id=str(source.task_id),
                assignment_id=str(source.assignment_id),
                submission_id=str(source.submission_id),
                submission_version=source.submission_version,
                source_run_id=str(source.source_run_id),
                source_request_id=str(source.source_request_id),
                source_request_digest=source.source_request_digest,
                source_result_id=str(source.source_result_id),
                source_result_digest=source.source_result_digest,
                source_finalize_evidence_id=str(source.source_finalize_evidence_id),
                source_generation=source.source_generation, failure_code=source.failure_code,
                successor_run_id=str(successor.run_id),
                successor_request_id=str(successor.request_id),
                successor_request_digest=successor.request_digest,
                successor_result_id=str(successor.result_id),
                successor_generation=successor.generation,
                event_id=successor.event_id,
                audit_event_id=str(successor.audit_event_id),
                authorization_decision_id=str(authority.decision_id),
                resource_digest=authority.resource_digest,
                resource_json=authority.resource_json,
            )
            self._session.add(receipt)
            await self._session.flush()
            return CheckerRetryResult(
                receipt_id=receipt_id, source=source, successor=successor,
                authorization_decision_id=authority.decision_id,
            )
        finally:
            self._authorization.close(handle)

    async def _replay(
        self, command: CheckerRetryCommand, detached: CheckerRetryReceipt,
        source: CheckerRetrySource,
    ) -> CheckerRetryResult:
        preparation = CheckerRetryPreparation(
            actor_profile_id=self._actor_profile_id, request_key=command.request_key,
            reason=command.reason, source=source,
        )
        handle = await self._authorization.prepare(preparation)
        try:
            receipt = await self._session.scalar(select(CheckerRetryReceipt).where(
                CheckerRetryReceipt.id == detached.id,
                CheckerRetryReceipt.actor_profile_id == str(self._actor_profile_id),
                CheckerRetryReceipt.request_key == str(command.request_key),
            ).with_for_update().execution_options(populate_existing=True))
            if receipt is None or _source_from_receipt(receipt) != source or receipt.reason != command.reason:
                raise CheckerExecutionUnavailable("checker_retry_replay_unavailable")
            successor = _successor_from_receipt(receipt)
            delivery = await read_retry_delivery(
                self._session, self._evaluations,
                project_id=source.project_id, submission_id=source.submission_id,
                event_id=successor.event_id,
            )
            # The reader already binds the retained run/result/generation to this receipt.
            if delivery is None or delivery.request.evaluation_request_id != successor.request_id:
                raise CheckerExecutionUnavailable("checker_retry_replay_unavailable")
            await self._authorization.validate_replay(
                handle, preparation, successor, UUID(receipt.identity_link_id),
                UUID(receipt.authorization_decision_id),
            )
            return CheckerRetryResult(
                receipt_id=UUID(receipt.id), source=source, successor=successor,
                authorization_decision_id=UUID(receipt.authorization_decision_id),
            )
        finally:
            self._authorization.close(handle)


async def read_retry_delivery(
    session: AsyncSession, evaluations: EvaluationCoordinator, *,
    project_id: UUID, submission_id: UUID, event_id: UUID,
) -> CheckerRetryDelivery | None:
    """Expose only a committed exact receipt through CHECKERS's existing port."""
    receipt = await session.scalar(select(CheckerRetryReceipt).where(
        CheckerRetryReceipt.project_id == str(project_id),
        CheckerRetryReceipt.submission_id == str(submission_id),
        CheckerRetryReceipt.event_id == event_id,
    ).execution_options(populate_existing=True))
    if receipt is None:
        return None
    source, successor = _source_from_receipt(receipt), _successor_from_receipt(receipt)
    stored = await evaluations.read_reserved_evaluation(
        project_id=source.project_id, task_id=source.task_id,
        submission_id=source.submission_id, request_id=successor.request_id,
    )
    if (
        stored.reservation.request_digest != successor.request_digest
        or stored.reservation.attempt_id != successor.run_id
        or stored.reservation.result_id != successor.result_id
        or stored.reservation.evaluation_generation != successor.generation
        or stored.request.assignment_id != source.assignment_id
        or stored.request.submission_version != source.submission_version
    ):
        raise CheckerExecutionUnavailable("checker_retry_delivery_unavailable")
    expected = retry_request_event(
        source, receipt_id=UUID(receipt.id), request_id=successor.request_id,
        request_digest=successor.request_digest,
        run_id=successor.run_id, result_id=successor.result_id,
    )
    return CheckerRetryDelivery(
        request=stored.request,
        expected_event=CheckerRetryEventExpectation(
            event_type=expected.event_type, event_version=expected.event_version,
            aggregate_type=expected.aggregate_type, aggregate_id=expected.aggregate_id,
            correlation_id=expected.correlation_id,
            causation_event_id=expected.causation_event_id,
            idempotency_key=expected.idempotency_key,
            payload_json=json.dumps(
                expected.payload, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ),
            payload_digest=canonical_json_hash(expected.payload),
        ),
    )
