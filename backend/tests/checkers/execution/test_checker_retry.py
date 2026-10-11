"""A real missing-artifact infrastructure result can be superseded once by an Operator."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import hashlib
import json
import os

import pytest
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.checkers import checker_retry_service, evaluation_coordinator
from app.adapters.outbox import outbox_append
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import ArtifactObjectMissingError
from app.modules.authorization.catalogue import ActionId
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable, CheckerRequestConflict, CheckerRetryCommand,
)
from app.modules.checkers.models import CheckerRetryReceipt, CheckerRun, CheckerSubmissionFence
from app.modules.outbox.api import (
    HandlerOutcome, OutboxAppendDisposition, OutboxAppendInput,
    OutboxAppendResult, OutboxIdempotencyConflict,
)
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import AuditEvent
from app.modules.tasks.evaluation_delivery import EvaluationDeliveryRequestReader, EvaluationDeliveryUnavailable
from app.modules.tasks.post_submit_routing.evaluation_guard import TaskEvaluationGuard
from app.modules.tasks.repository import TaskRepository
from tests.post_submit_materialization_helpers import material_fixture
from tests.checkers.post_submit.support import change_request
from tests.checkers.execution.completion_fixture import completed_evidence
from tests.checkers.execution.support import live_executor, reserve
from tests.project_create_fixtures import grant_fixture_admin_role
from tests.tasks.evaluation_delivery.support import delivery_fixture, outcome, state
from tests.tasks.evaluation_delivery.test_worker_materialization import _worker_port
from tests.test_artifact_admission import _context, _seed_human_actor


@asynccontextmanager
async def _failed_source(tmp_path, isolated_database_env, monkeypatch, provider="local"):
    """Build one real terminal missing-object result through the durable worker."""
    from app.adapters.artifacts.local import LocalStorageAdapter
    from app.adapters.artifacts.s3_compatible import S3CompatibleArtifactStore
    from app.adapters.artifacts import internal_workers

    if provider == "minio":
        from tests import test_s3_artifact_store

        monkeypatch.setattr(
            test_s3_artifact_store, "MINIO_BUCKET", os.environ["WORKSTREAM_TEST_MINIO_BUCKET"]
        )
    async with material_fixture(tmp_path, isolated_database_env, provider=provider) as h:
        port = _worker_port(h, monkeypatch)

        def missing(_store, _reference):
            raise ArtifactObjectMissingError("controlled verified object loss")

        try:
            delivery = await delivery_fixture(h, materialization=port)
            with monkeypatch.context() as patch:
                patch.setattr(
                    LocalStorageAdapter if provider == "local" else S3CompatibleArtifactStore,
                    "open", missing,
                )
                initial = await delivery.delivery.deliver(
                    h.created.evaluation_event_id, h.request.project_id, "retry-source",
                )
            assert outcome(initial)["delivery_state"] == "acknowledged"
            saved = await state(h)
            assert saved["run"]["status"] == "infrastructure_failed"
            assert json.loads(saved["run"]["result_json"])["infrastructure_failure_code"] == "material_unavailable"
            yield h, delivery
        finally:
            internal_workers.shutdown_artifact_internal_runtime()


async def _operator_for(h, *, grant=True):
    operator = _context()
    async with h.factory.begin() as session:
        await _seed_human_actor(session, operator)
        if grant:
            await grant_fixture_admin_role(
                session, operator.actor_profile_id, role="operator", scope="system",
            )
    key = new_record_id()
    return operator.model_copy(update={"request_id": key, "correlation_id": key})


def _command(h, operator):
    return CheckerRetryCommand(
        source_run_id=h.created.evaluation_attempt_id,
        request_key=operator.request_id,
        reason="Verified artifact storage has been restored",
    )


def _copied_audit_event(event, **changes):
    values = {
        column.name: getattr(event, column.name)
        for column in AuditEvent.__table__.columns
    }
    return AuditEvent(**(values | changes))


async def test_retry_sql_rejects_unreceipted_terminal_supersession(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        direct_successor = change_request(
            h.request, evaluation_request_id=new_record_id(), evaluation_generation=2,
        )
        with pytest.raises(IntegrityError, match="terminal checker infrastructure retry requires Operator receipt"):
            async with h.factory.begin() as session:
                await evaluation_coordinator(session).reserve_current_evaluation(direct_successor)
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1


async def test_retry_sql_rejects_crossed_receipt_with_real_authority_participants(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        captured = []
        original_add = AsyncSession.add

        def omit_only_receipt(session, value):
            if isinstance(value, CheckerRetryReceipt):
                captured.append(value)
                return
            return original_add(session, value)

        substitutions = (
            ("reason", "crossed Operator reason"),
            ("request_key", str(new_record_id())),
            ("source_result_id", str(new_record_id())),
            ("successor_run_id", str(command.source_run_id)),
            ("event_id", h.created.evaluation_event_id),
            ("authorization_decision_id", None),
        )
        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "add", omit_only_receipt)
            for field, crossed in substitutions:
                captured.clear()
                with pytest.raises(IntegrityError, match="checker retry receipt closure invalid|terminal checker infrastructure retry requires Operator receipt"):
                    async with h.factory.begin() as session:
                        created = await checker_retry_service(session, operator).retry(command)
                        assert len(captured) == 1
                        receipt = captured[0]
                        values = {
                            column.name: getattr(receipt, column.name)
                            for column in CheckerRetryReceipt.__table__.columns
                            if column.name != "created_at"
                        }
                        values[field] = (
                            str(created.source.source_finalize_evidence_id)
                            if field == "authorization_decision_id" else crossed
                        )
                        await session.execute(insert(CheckerRetryReceipt).values(**values))
        async with h.factory() as session:
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert fence.current_run_id == str(command.source_run_id)
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
        async with h.factory.begin() as session:
            valid = await checker_retry_service(session, operator).retry(command)
        assert valid.successor.generation == 2


async def test_retry_sql_rejects_noncanonical_authority_resource_even_with_matching_raw_hash(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        captured = []
        original_add = AsyncSession.add

        def omit_only_receipt(session, value):
            if isinstance(value, CheckerRetryReceipt):
                captured.append(value)
                return
            return original_add(session, value)

        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "add", omit_only_receipt)
            with pytest.raises(IntegrityError, match="resource_json_digest"):
                async with h.factory.begin() as session:
                    await checker_retry_service(session, operator).retry(_command(h, operator))
                    assert len(captured) == 1
                    receipt = captured[0]
                    values = {
                        column.name: getattr(receipt, column.name)
                        for column in CheckerRetryReceipt.__table__.columns
                        if column.name != "created_at"
                    }
                    authority_id = str(new_record_id())
                    initiation_id = str(new_record_id())
                    resource = json.loads(receipt.resource_json)
                    resource["resource_context"]["successor"]["audit_event_id"] = initiation_id
                    values["resource_json"] = " " + json.dumps(
                        resource, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                    )
                    values["resource_digest"] = "sha256:" + hashlib.sha256(
                        values["resource_json"].encode("utf-8")
                    ).hexdigest()
                    authority = await session.get(AuditEvent, receipt.authorization_decision_id)
                    initiation = await session.get(AuditEvent, receipt.audit_event_id)
                    assert authority is not None and initiation is not None
                    references = dict(initiation.event_payload["references"])
                    references["authorization_decision_id"] = authority_id
                    session.add(_copied_audit_event(
                        authority, id=authority_id, entity_id=authority_id,
                        after_facts={"allowed": True, "resource_context_digest": values["resource_digest"]},
                    ))
                    session.add(_copied_audit_event(
                        initiation, id=initiation_id,
                        event_payload={**initiation.event_payload, "references": references},
                    ))
                    await session.flush()
                    values["authorization_decision_id"] = authority_id
                    values["audit_event_id"] = initiation_id
                    await session.execute(insert(CheckerRetryReceipt).values(**values))
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
        async with h.factory.begin() as session:
            valid = await checker_retry_service(session, operator).retry(_command(h, operator))
        assert valid.successor.generation == 2


async def test_retry_sql_actor_status_validation_preserves_fresh_historical_replay(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(command)
        async with h.factory() as session:
            await session.begin()
            valid = text("select public.checker_retry_receipt_valid(:receipt_id)")
            assert await session.scalar(valid, {"receipt_id": created.receipt_id}) is True
            await session.execute(text("""
                update actor_profiles set status='suspended', suspended_by='test',
                  suspended_at=clock_timestamp(), suspension_reason='test'
                where id=:actor_id
            """), {"actor_id": operator.actor_profile_id})
            assert await session.scalar(valid, {"receipt_id": created.receipt_id}) is False
            await session.rollback()
        async with h.factory.begin() as session:
            assert await checker_retry_service(session, operator).retry(command) == created


async def test_retry_sql_rejects_outbox_payload_with_false_digest(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.modules.outbox.service import OutboxService

    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        false_digest = "sha256:" + "0" * 64

        async def false_digest_append(service, event):
            event_id = new_record_id()
            await service._repository._session.execute(insert(OutboxEvent).values(
                event_id=event_id, event_type=event.event_type,
                event_version=event.event_version, aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id, project_id=str(event.project_id),
                correlation_id=event.correlation_id,
                causation_event_id=event.causation_event_id,
                idempotency_key=event.idempotency_key,
                payload=event.payload, payload_digest=false_digest,
            ))
            return OutboxAppendResult(
                event_id=event_id, disposition=OutboxAppendDisposition.CREATED,
                payload_digest=false_digest, occurred_at=datetime.now(UTC),
            )

        with monkeypatch.context() as patch:
            patch.setattr(OutboxService, "append", false_digest_append)
            with pytest.raises(IntegrityError, match="checker retry receipt closure invalid|terminal checker infrastructure retry requires Operator receipt"):
                async with h.factory.begin() as session:
                    await checker_retry_service(session, operator).retry(command)
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
        async with h.factory.begin() as session:
            valid = await checker_retry_service(session, operator).retry(command)
        assert valid.successor.generation == 2


async def test_retry_without_operator_grant_denies_without_effects(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h, grant=False)
        with pytest.raises(CheckerExecutionUnavailable, match="checker_retry_authority_unavailable"):
            async with h.factory.begin() as session:
                await checker_retry_service(session, operator).retry(_command(h, operator))
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
            assert await session.scalar(select(func.count()).select_from(
                AuditEvent
            ).where(AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value)) == 0


async def test_retry_caller_rollback_removes_whole_successor(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        with pytest.raises(RuntimeError, match="planned caller rollback"):
            async with h.factory.begin() as session:
                staged = await checker_retry_service(session, operator).retry(_command(h, operator))
                assert staged.successor.generation == 2
                raise RuntimeError("planned caller rollback")
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
            assert await session.get(CheckerRun, str(staged.successor.run_id)) is None
            assert await session.get(AuditEvent, str(staged.authorization_decision_id)) is None


async def test_retry_audit_failure_removes_whole_successor(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.adapters.audit import _CheckerRetryAudit

    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)

        async def audit_unavailable(_participant, _preparation, _successor, _authority):
            raise RuntimeError("controlled initiation audit outage")

        with monkeypatch.context() as patch:
            patch.setattr(_CheckerRetryAudit, "record", audit_unavailable)
            with pytest.raises(RuntimeError, match="controlled initiation audit outage"):
                async with h.factory.begin() as session:
                    await checker_retry_service(session, operator).retry(_command(h, operator))
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
            assert await session.scalar(select(func.count()).select_from(
                AuditEvent
            ).where(AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value)) == 0


async def test_retry_real_outbox_conflict_rolls_back_successor(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        async with h.factory.begin() as session:
            await outbox_append(session).append(OutboxAppendInput(
                event_type="RetryCollision", event_version=1,
                aggregate_type="submission", aggregate_id=h.request.submission_id,
                project_id=h.request.project_id,
                correlation_id=str(command.source_run_id),
                idempotency_key="checker-retry:" + str(command.source_run_id),
                payload={"collision": "reserved by another producer"},
            ))
        with pytest.raises(OutboxIdempotencyConflict):
            async with h.factory.begin() as session:
                await checker_retry_service(session, operator).retry(command)
        async with h.factory() as session:
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert fence.current_run_id == str(command.source_run_id)
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 2
            assert await session.scalar(select(func.count()).select_from(
                AuditEvent
            ).where(AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value)) == 0


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_retry_known_missing_object_dispatches_new_generation(
    tmp_path, isolated_database_env, monkeypatch, provider,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch, provider) as (h, delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(command)
        assert created.source.source_run_id == command.source_run_id
        assert created.successor.generation == h.request.evaluation_generation + 1
        assert created.successor.run_id != created.source.source_run_id
        async with h.factory() as session:
            source = await session.get(CheckerRun, str(command.source_run_id))
            successor = await session.get(CheckerRun, str(created.successor.run_id))
            receipt = await session.get(CheckerRetryReceipt, str(created.receipt_id))
            assert source.status == "infrastructure_failed"
            assert successor.status == "queued"
            assert receipt.source_result_digest == source.result_digest
            assert receipt.successor_request_digest == successor.request_digest
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 2
            authorization = await session.get(AuditEvent, str(created.authorization_decision_id))
            assert authorization.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value
            assert authorization.project_id == str(h.request.project_id)
            assert authorization.resource_id == str(command.source_run_id)
            assert authorization.after_facts["resource_context_digest"] == receipt.resource_digest
            audit = await session.get(AuditEvent, str(created.successor.audit_event_id))
            assert audit.project_id is None
            assert audit.event_payload["references"]["project_id"] == str(h.request.project_id)
            assert audit.event_payload["references"]["source_checker_run_id"] == str(command.source_run_id)
            assert audit.event_payload["authorization_resource_digest"] == receipt.resource_digest
        delivered = await delivery.delivery.deliver(
            created.successor.event_id, h.request.project_id, "retry-successor",
        )
        assert outcome(delivered)["delivery_state"] == "acknowledged"
        async with h.factory() as session:
            successor = await session.get(CheckerRun, str(created.successor.run_id))
            assert successor.status == "completed"


async def test_retry_response_loss_and_later_generation_replay(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, delivery):
        operator = await _operator_for(h)
        command = _command(h, operator)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(command)
        async with h.factory.begin() as session:
            replay = await checker_retry_service(session, operator).retry(command)
        assert replay == created
        with pytest.raises(CheckerRequestConflict, match="checker_retry_request_conflict"):
            async with h.factory.begin() as session:
                await checker_retry_service(session, operator).retry(command.model_copy(update={
                    "reason": "Different reason under the same request key",
                }))
        second_key = new_record_id()
        second_context = operator.model_copy(update={
            "request_id": second_key, "correlation_id": second_key,
        })
        with pytest.raises(CheckerExecutionUnavailable):
            async with h.factory.begin() as session:
                await checker_retry_service(session, second_context).retry(
                    command.model_copy(update={"request_key": second_key})
                )
        delivered = await delivery.delivery.deliver(
            created.successor.event_id, h.request.project_id, "retry-successor",
        )
        assert outcome(delivered)["delivery_state"] == "acknowledged"
        later_request = change_request(
            h.request, evaluation_request_id=new_record_id(), evaluation_generation=3,
        )
        async with h.factory.begin() as session:
            later = await evaluation_coordinator(session).reserve_current_evaluation(later_request)
        assert later.evaluation_generation == 3
        assert later.attempt_id != created.successor.run_id
        async with h.factory.begin() as session:
            historical_replay = await checker_retry_service(session, operator).retry(command)
        assert historical_replay == created
        async with h.factory() as session:
            source = await session.get(CheckerRun, str(command.source_run_id))
            successor = await session.get(CheckerRun, str(created.successor.run_id))
            assert source.status == "infrastructure_failed"
            assert successor.status == "completed"
            assert await session.get(CheckerRun, str(later.attempt_id)) is not None
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 3


async def test_retry_handler_rejects_crossed_event_and_payload_before_execution(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, delivery):
        operator = await _operator_for(h)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(_command(h, operator))
        claim = await delivery.delivery.claim(
            created.successor.event_id, h.request.project_id, "retry-crossed-envelope",
        )
        assert claim is not None
        envelope = await delivery.delivery._begin_invocation(claim)
        assert envelope is not None
        before, opens = await state(h), len(h.store.opens)
        async with h.factory() as session, session.begin():
            reader = EvaluationDeliveryRequestReader(session, evaluation_coordinator(session))
            exact = await reader.read(envelope)
            assert exact.evaluation_request_id == created.successor.request_id
            crossed = []
            for field, value in (
                ("request_id", str(new_record_id())),
                ("retry_receipt_id", str(new_record_id())),
            ):
                payload = json.loads(envelope.payload_json)
                payload[field] = value
                crossed.append(envelope.model_copy(update={
                    "payload_json": json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    "claim": envelope.claim.model_copy(update={
                        "payload_digest": canonical_json_hash(payload),
                    }),
                }))
            crossed.append(envelope.model_copy(update={
                "claim": envelope.claim.model_copy(update={
                    "event_id": h.created.evaluation_event_id,
                }),
            }))
            for mixed in crossed:
                with pytest.raises(EvaluationDeliveryUnavailable, match="evaluation_delivery_unavailable"):
                    await reader.read(mixed)
                assert await delivery.handler(mixed) is HandlerOutcome.REJECT
        assert await state(h) == before and len(h.store.opens) == opens


async def test_same_key_independent_sessions_wait_for_task_then_replay_one_retry(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.adapters.artifacts.local import LocalStorageAdapter
    from app.adapters.artifacts import internal_workers

    async with material_fixture(tmp_path, isolated_database_env) as h:
        port = _worker_port(h, monkeypatch)

        def missing(_store, _reference):
            raise ArtifactObjectMissingError("controlled verified object loss")

        try:
            delivery = await delivery_fixture(h, materialization=port)
            with monkeypatch.context() as patch:
                patch.setattr(LocalStorageAdapter, "open", missing)
                initial = await delivery.delivery.deliver(
                    h.created.evaluation_event_id, h.request.project_id, "concurrent-source",
                )
            assert outcome(initial)["delivery_state"] == "acknowledged"
            assert (await state(h))["run"]["status"] == "infrastructure_failed"

            operator = _context()
            async with h.factory.begin() as session:
                await _seed_human_actor(session, operator)
                await grant_fixture_admin_role(
                    session, operator.actor_profile_id, role="operator", scope="system",
                )
            key = new_record_id()
            operator = operator.model_copy(update={"request_id": key, "correlation_id": key})
            command = CheckerRetryCommand(
                source_run_id=h.created.evaluation_attempt_id,
                request_key=key, reason="Restore verified checker infrastructure",
            )

            arrivals: set[int] = set()
            both_arrived = asyncio.Event()
            original_replay = TaskEvaluationGuard.lock_retry_replay_scope
            original_new = TaskEvaluationGuard.lock_terminal_retry_scope

            async def mark_then(method, guard, request):
                arrivals.add(id(guard))
                if len(arrivals) >= 2:
                    both_arrived.set()
                return await method(guard, request)

            async def replay_gate(guard, request):
                return await mark_then(original_replay, guard, request)

            async def new_gate(guard, request):
                return await mark_then(original_new, guard, request)

            async def invoke():
                async with h.factory.begin() as session:
                    return await checker_retry_service(session, operator).retry(command)

            with monkeypatch.context() as patch:
                patch.setattr(TaskEvaluationGuard, "lock_retry_replay_scope", replay_gate)
                patch.setattr(TaskEvaluationGuard, "lock_terminal_retry_scope", new_gate)
                async with h.factory.begin() as holder:
                    assert await TaskRepository(holder).lock_project_task(
                        h.request.project_id, h.request.task_id,
                    ) is not None
                    calls = [asyncio.create_task(invoke()) for _ in range(2)]
                    try:
                        await asyncio.wait_for(both_arrived.wait(), 30)
                        assert all(not call.done() for call in calls)
                        async with h.factory() as observer:
                            assert await observer.scalar(
                                select(func.count()).select_from(CheckerRetryReceipt)
                            ) == 0
                            assert await observer.scalar(select(func.count()).select_from(
                                AuditEvent
                            ).where(AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value)) == 0
                    except BaseException:
                        for call in calls:
                            call.cancel()
                        await asyncio.gather(*calls, return_exceptions=True)
                        raise
                first, second = await asyncio.gather(*calls)
            assert first == second
            async with h.factory() as session:
                assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 1
                assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 2
        finally:
            internal_workers.shutdown_artifact_internal_runtime()


async def _assert_nonterminal_source_reaches_guard(h, monkeypatch, expected_status):
    operator = await _operator_for(h)
    command = _command(h, operator)
    before_opens = len(h.store.opens)
    async with h.factory() as session:
        before_events = await session.scalar(select(func.count()).select_from(OutboxEvent))
        assert (await session.get(CheckerRun, str(command.source_run_id))).status == expected_status
    reached = False
    original = TaskEvaluationGuard.lock_terminal_retry_scope

    async def observed(guard, request):
        nonlocal reached
        await original(guard, request)
        reached = True

    with monkeypatch.context() as patch:
        patch.setattr(TaskEvaluationGuard, "lock_terminal_retry_scope", observed)
        with pytest.raises(CheckerExecutionUnavailable, match="checker_retry_source_unavailable"):
            async with h.factory.begin() as session:
                await checker_retry_service(session, operator).retry(command)
    assert reached and len(h.store.opens) == before_opens
    async with h.factory() as session:
        assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == before_events


async def test_queued_source_reaches_valid_task_guard_then_refuses_terminal_retry(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await _assert_nonterminal_source_reaches_guard(h, monkeypatch, "queued")


async def test_running_source_reaches_valid_task_guard_then_refuses_terminal_retry(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        lease, replay = await live_executor(h)._claim(h.request)
        assert replay is None and lease.reservation.attempt_id == h.created.evaluation_attempt_id
        await _assert_nonterminal_source_reaches_guard(h, monkeypatch, "running")


@pytest.mark.parametrize("recommendation", ["allow_review", "task_setup_blocked"])
async def test_completed_source_reaches_valid_task_guard_then_refuses_terminal_retry(
    tmp_path, isolated_database_env, monkeypatch, recommendation,
):
    async with completed_evidence(tmp_path, isolated_database_env, recommendation) as h:
        assert h.result.outcome == "completed" and h.run.routing_recommendation == recommendation
        await _assert_nonterminal_source_reaches_guard(h, monkeypatch, "completed")


async def test_expired_unfinished_transport_reclaims_same_run_without_retry_receipt(
    tmp_path, isolated_database_env, monkeypatch,
):
    import app.modules.checkers.execution as execution

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        monkeypatch.setattr(execution, "LEASE_SECONDS", 1)
        first, replay = await executor._claim(h.request)
        assert replay is None
        async with h.factory() as session:
            await session.execute(text("select pg_sleep(1.05)"))
        monkeypatch.setattr(execution, "LEASE_SECONDS", 300)
        second, replay = await executor._claim(h.request)
        assert replay is None
        assert second.reservation == first.reservation
        assert second.lease_generation == first.lease_generation + 1
        async with h.factory() as session:
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert fence.current_run_id == str(first.reservation.attempt_id)
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0


async def test_retry_fences_failed_source_from_stale_worker_and_current_result(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _delivery):
        executor = live_executor(h)
        lease, replay = await executor._claim(h.request)
        assert lease is None and replay is not None
        operator = await _operator_for(h)
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(_command(h, operator))
        with pytest.raises(CheckerExecutionUnavailable, match="checker_current_request_unavailable"):
            await executor._claim(h.request)
        async with h.factory.begin() as session:
            with pytest.raises(CheckerExecutionUnavailable, match="checker_current_request_unavailable"):
                await evaluation_coordinator(session).read_current_result(h.request)
        async with h.factory() as session:
            source = await session.get(CheckerRun, str(h.created.evaluation_attempt_id))
            fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
            assert source.status == "infrastructure_failed" and source.completion_event_id is None
            assert fence.current_run_id == str(created.successor.run_id)
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 1
