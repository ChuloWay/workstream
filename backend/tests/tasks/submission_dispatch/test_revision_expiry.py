"""Durable revision expiry keeps the old Submission and releases its assignment."""

from datetime import UTC, datetime, timedelta
import asyncio
import json
import traceback
from types import SimpleNamespace

from sqlalchemy import func, select, text
from uuid import UUID

from app.adapters.auth import outbox_dispatch_authorization, revision_expiry_authorization
from app.adapters.outbox import outbox_delivery
from app.adapters.tasks import (
    TransactionalTaskRevisionExpiredNoticeHandler, TransactionalTaskRevisionExpiryHandler,
)
from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.outbox.api import DeliveryOptions
from app.modules.outbox.api import HandlerOutcome
from app.modules.outbox.delivery import CommittedInvocationReader
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.registry import HandlerRegistry
from app.modules.tasks.api.revision_expiry import REVISION_EXPIRED_EVENT, REVISION_EXPIRY_EVENT
from app.modules.tasks.api.revision_expiry import (
    TaskRevisionExpiryAuthorityFacts, revision_expiry_resource_digest,
)
from app.modules.tasks.revision.expiry_event import revision_expiry_event
from app.modules.tasks.revision.models import TaskRevisionExpiration
from tests.tasks.post_submit_routing.remediation_support import remediation_source, no_economic_effects
from tests.tasks.submission_dispatch.test_revision_capacity import _retain_pre_revision_source
from tests.tasks.test_public_submission_intake import _client
from tests.test_submission_predecessor_custody import _fixture_revision_context


def test_expiry_request_keeps_the_original_window_when_the_head_changes():
    """The scheduled event binds the original failure, not a later repair head."""
    manifest_id = new_record_id()
    manifest = SimpleNamespace(id=manifest_id, outcome_event_id=new_record_id())
    root = SimpleNamespace(
        id=new_record_id(), project_id=str(new_record_id()), task_id=str(new_record_id()),
        assignment_id=str(new_record_id()), contributor_id=str(new_record_id()),
        submission_id=str(new_record_id()), routing_manifest_id=manifest_id,
        sequence=1, predecessor_id=None,
        preparation_sha256="sha256:" + "a" * 64,
        deadline_at=datetime(2026, 10, 14, tzinfo=UTC) + timedelta(hours=24),
    )
    event = revision_expiry_event(manifest, root)
    assert event.event_type == REVISION_EXPIRY_EVENT
    assert event.idempotency_key == f"task.revision.expire:{manifest_id}"
    assert event.not_before_at == root.deadline_at
    assert event.payload["root_preparation_id"] == str(root.id)
    assert event.payload["root_preparation_sha256"] == root.preparation_sha256
    assert "head_preparation_id" not in event.payload

    from app.modules.authorization.catalogue import ActionId
    from app.modules.authorization.domain.audit_targets import project_authority_audit_target
    from app.modules.authorization.domain.resource_digest import authorization_resource_digest
    from app.modules.authorization.domain.revision_expiry import revision_expiry_resource

    from app.modules.tasks.api.revision_expiry import TaskRevisionExpiryTarget
    facts = TaskRevisionExpiryAuthorityFacts(
        target=TaskRevisionExpiryTarget.model_validate_json(json.dumps(event.payload)),
        head_preparation_id=new_record_id(),
        head_preparation_sha256="sha256:" + "b" * 64,
        delivery_event_id=new_record_id(), delivery_generation=1,
        invocation_digest="sha256:" + "c" * 64,
        task_status="needs_revision", assignment_status="active",
    )
    resource = revision_expiry_resource(facts)
    assert authorization_resource_digest(resource) == revision_expiry_resource_digest(facts)
    assert project_authority_audit_target(resource, ActionId.TASK_REVISION_EXPIRE) == (
        str(facts.target.project_id), "task", str(facts.target.task_id),
        "project", str(facts.target.project_id),
    )


async def _provision_expirer(factory):
    actor_id = new_record_id()
    async with factory() as session, session.begin():
        session.add(ActorProfile(
            id=str(actor_id), actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.TASK_REVISION_EXPIRER.value,
            created_by=str(actor_id),
        ))
        await session.flush()
        session.add(ActorIdentityLink(
            id=str(new_record_id()), actor_profile_id=str(actor_id),
            issuer="workstream.internal", subject=ServiceIdentity.TASK_REVISION_EXPIRER.value,
            subject_kind="service", status="active", linked_by="workstream:system:bootstrap",
        ))
    return actor_id


async def expire_retained_revision(
    h, *, monkeypatch, isolated_database_env, ack_lost=False, deliver=True,
):
    """Exercise a pre-preparation retained failure through PM recovery and durable delivery."""
    source_id = await _fixture_revision_context(h)
    await _retain_pre_revision_source(h, source_id)
    async with h.factory() as session, session.begin():
        await session.execute(text(
            "ALTER TABLE public.task_post_submit_routing_manifests "
            "DISABLE TRIGGER task_routing_manifest_immutable"
        ))
        deadline = await session.scalar(text("""
            UPDATE public.task_post_submit_routing_manifests m
            SET created_at=clock_timestamp()-make_interval(hours => p.revision_deadline_hours+1)
            FROM public.submissions s JOIN public.revision_policies p
              ON p.id=s.locked_revision_policy_id
            WHERE m.id=:id AND s.id=m.submission_id
            RETURNING m.created_at+make_interval(hours => p.revision_deadline_hours)
        """), {"id": source_id})
        await session.execute(text(
            "ALTER TABLE public.task_post_submit_routing_manifests "
            "ENABLE TRIGGER task_routing_manifest_immutable"
        ))
    async with _client(h, monkeypatch, isolated_database_env) as client:
        recovered = await client.post(
            f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair",
            json={"routing_manifest_id": str(source_id), "reason": "Recover overdue retained failure"},
            headers={"Idempotency-Key": str(new_record_id())},
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["disposition"] == "revision_deadline_expired"
    async with h.factory() as session:
        event = await session.scalar(select(OutboxEvent).where(
            OutboxEvent.event_type == REVISION_EXPIRY_EVENT,
            OutboxEvent.idempotency_key == f"task.revision.expire:{source_id}",
        ))
        assert event is not None and event.not_before_at == deadline
        event_id = event.event_id
    await _provision_expirer(h.factory)
    handler = TransactionalTaskRevisionExpiryHandler(
        h.factory, observer=CommittedInvocationReader(h.factory),
        authorization_factory=revision_expiry_authorization,
    )

    async def observed_expiry(envelope):
        try:
            outcome = await handler(envelope)
            h.expiry_handler_outcome = outcome.value
            return outcome
        except Exception as exc:
            original = exc
            for _ in range(6):
                nested = getattr(original, "orig", None) or original.__cause__
                if nested is None or nested is original:
                    break
                original = nested
            frames = traceback.extract_tb(exc.__traceback__)
            owner = next((
                f"{frame.filename.rsplit('/backend/', 1)[-1]}:{frame.lineno}:{frame.name}"
                for frame in reversed(frames) if "/backend/app/" in frame.filename
            ), None)
            h.expiry_handler_error = (
                type(original).__name__, getattr(original, "sqlstate", None),
                getattr(original, "constraint_name", None),
                str(original).splitlines()[0][:160], owner,
            )
            raise

    delivery = outbox_delivery(
        h.factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry(
            [
                (REVISION_EXPIRY_EVENT, 1, observed_expiry),
                (REVISION_EXPIRED_EVENT, 1, TransactionalTaskRevisionExpiredNoticeHandler(
                    h.factory, observer=CommittedInvocationReader(h.factory),
                )),
            ],
            replay_safe=frozenset({(REVISION_EXPIRY_EVENT, 1)}),
        ),
        options=(DeliveryOptions(lease_seconds=30, handler_timeout_seconds=25,
                                 retry_base_seconds=1, retry_cap_seconds=1)
                 if ack_lost else DeliveryOptions()),
    )
    h.expiry_delivery = delivery
    if ack_lost:
        claim = await delivery.claim(event_id, h.request.project_id, "revision-expiry-proof")
        assert claim is not None
        h.expiry_claim_expires_at = claim.claim_expires_at
        envelope = await delivery._begin_invocation(claim)
        assert envelope is not None
        assert await observed_expiry(envelope) is HandlerOutcome.ACKNOWLEDGE
    elif deliver:
        delivered = await delivery.deliver(event_id, h.request.project_id, "revision-expiry-proof")
        assert delivered is not None
        assert json.loads(delivered.outcome_json)["delivery_state"] == "acknowledged", (
            delivered.outcome_json,
            getattr(h, "expiry_handler_outcome", None),
            getattr(h, "expiry_handler_error", None),
        )
    return source_id, recovered.json(), event_id


async def test_due_failure_auto_rejects_and_releases_with_immutable_receipt(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            source_before = await session.scalar(text(
                "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
            ), {"id": h.created.submission_id})
        source_id, recovered, event_id = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
        )
        async with h.factory() as session:
            receipt = await session.scalar(select(TaskRevisionExpiration).where(
                TaskRevisionExpiration.routing_manifest_id == source_id,
            ))
            assert receipt is not None
            assert receipt.root_preparation_id == receipt.head_preparation_id
            assert receipt.root_preparation_id == UUID(recovered["preparation_id"])
            repair_target = (await session.execute(text("""
                SELECT a.resource_type,a.resource_id FROM public.task_revision_preparations p
                JOIN public.audit_events a ON a.id=p.authorization_decision_id
                WHERE p.id=:preparation
            """), {"preparation": receipt.root_preparation_id})).one()
            assert repair_target == ("project", str(h.request.project_id))
            assert receipt.delivery_event_id == event_id
            outcome = await session.get(OutboxEvent, receipt.outcome_event_id)
            assert outcome is not None
            assert outcome.event_type == REVISION_EXPIRED_EVENT
            assert outcome.causation_event_id == event_id
            assert outcome.payload["expiration_receipt_id"] == str(receipt.id)
            assert outcome.payload["authorization_decision_id"] == str(receipt.authorization_decision_id)
            assert outcome.payload["audit_event_id"] == str(receipt.audit_event_id)
            assert await session.scalar(text(
                "SELECT count(*) FROM public.outbox_events "
                "WHERE event_type='TaskRevisionExpired' AND idempotency_key=:key"
            ), {"key": f"task.revision.expired:{source_id}"}) == 1
            assert receipt.deadline_at <= receipt.expired_at
            assert await session.scalar(text(
                "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
            ), {"id": h.created.submission_id}) == source_before
            task = (await session.execute(text(
                "SELECT status,assigned_to FROM public.workstream_tasks WHERE id=:id"
            ), {"id": h.request.task_id})).one()
            assignment = (await session.execute(text(
                "SELECT status,released_at FROM public.task_assignments WHERE id=:id"
            ), {"id": h.request.assignment_id})).one()
            assert task == ("ready", None)
            assert assignment == ("revision_expired", receipt.expired_at)
            assert await session.scalar(text(
                "SELECT public.task_revision_expired_assignment_current(:assignment,:submission)"
            ), {"assignment": h.request.assignment_id, "submission": h.created.submission_id}) is True
            await no_economic_effects(session)
        acknowledged = await h.expiry_delivery.deliver(
            receipt.outcome_event_id, h.request.project_id, "revision-expired-notice-proof",
        )
        assert acknowledged is not None
        assert json.loads(acknowledged.outcome_json)["delivery_state"] == "acknowledged"
        async with _client(h, monkeypatch, isolated_database_env) as client:
            history = await client.get(f"/api/v1/tasks/{h.request.task_id}/submissions")
            assert history.status_code == 200, history.text
            row = next(item for item in history.json()["items"]
                       if item["id"] == str(h.created.submission_id))
            assert row["status"] == "rejected"
            assert row["status_reason"] == "revision_deadline_expired"


async def test_expiry_replays_one_receipt_when_effect_commits_before_ack(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id, _, event_id = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
            ack_lost=True,
        )
        async with h.factory() as session:
            db_now = await session.scalar(select(func.clock_timestamp()))
        remaining = (h.expiry_claim_expires_at - db_now).total_seconds()
        await asyncio.sleep(max(0, remaining) + 0.2)
        recovered = await h.expiry_delivery.recover(event_id, h.request.project_id)
        assert recovered is not None
        assert json.loads(recovered.outcome_json)["delivery_state"] == "retryable"
        assert json.loads(recovered.outcome_json)["invocation_unknown"] is True
        await asyncio.sleep(1.1)
        redelivered = await h.expiry_delivery.deliver(
            event_id, h.request.project_id, "revision-expiry-replay-proof")
        assert redelivered is not None
        assert json.loads(redelivered.outcome_json)["delivery_state"] == "acknowledged"
        async with h.factory() as session:
            assert await session.scalar(text(
                "SELECT count(*) FROM public.task_revision_expirations WHERE routing_manifest_id=:source"
            ), {"source": source_id}) == 1
            assert await session.scalar(text(
                "SELECT count(*) FROM public.audit_events "
                "WHERE event_type='TaskRevisionExpired' "
                "AND event_payload->'references'->>'outbox_event_id'=:event"
            ), {"event": str(event_id)}) == 1


async def test_due_expiry_and_old_assignment_intake_wait_for_task_lock(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Both contenders wait on TASK; expiry wins and the old assignment cannot intake."""
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id, recovered, event_id = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
            deliver=False,
        )
        async with _client(h, monkeypatch, isolated_database_env) as client:
            async with h.factory() as holder:
                async with holder.begin():
                    holder_pid = await holder.scalar(text("SELECT pg_catalog.pg_backend_pid()"))
                    await holder.execute(text(
                        "SELECT id FROM public.workstream_tasks WHERE id=:task FOR UPDATE"
                    ), {"task": h.request.task_id})
                    delivery_task = asyncio.create_task(h.expiry_delivery.deliver(
                        event_id, h.request.project_id, "revision-expiry-lock-proof",
                    ))
                    intake_task = None
                    try:
                        async def wait_for_blockers(count):
                            async with asyncio.timeout(30):
                                while True:
                                    async with h.factory() as probe:
                                        blockers = await probe.scalar(text("""
                                            SELECT count(*) FROM pg_catalog.pg_stat_activity a
                                            WHERE a.datname=pg_catalog.current_database()
                                              AND a.pid<>:holder
                                              AND (
                                                :holder=ANY(pg_catalog.pg_blocking_pids(a.pid))
                                                OR EXISTS (
                                                  SELECT 1 FROM pg_catalog.pg_stat_activity b
                                                  WHERE b.pid=ANY(pg_catalog.pg_blocking_pids(a.pid))
                                                    AND :holder=ANY(pg_catalog.pg_blocking_pids(b.pid))
                                                )
                                              )
                                        """), {"holder": holder_pid})
                                    if blockers >= count:
                                        return
                                    if intake_task is not None and intake_task.done():
                                        response = await intake_task
                                        raise AssertionError(
                                            f"intake finished before TASK lock wait: "
                                            f"{response.status_code} {response.text}"
                                        )
                                    await asyncio.sleep(0.05)

                        await wait_for_blockers(1)
                        intake_task = asyncio.create_task(client.post(
                            f"/api/v1/tasks/{h.request.task_id}/submission-bundle-preparations",
                            headers={
                                "Content-Type": "application/zip",
                                "X-Task-Assignment-Id": str(h.request.assignment_id),
                                "X-Predecessor-Submission-Id": str(h.created.submission_id),
                                "Idempotency-Key": str(new_record_id()),
                                "X-Revision-Preparation-Id": recovered["preparation_id"],
                                "X-Revision-Preparation-Sha256": recovered["preparation_sha256"],
                            }, content=b"not a zip",
                        ))
                        await wait_for_blockers(2)
                    except BaseException:
                        delivery_task.cancel()
                        if intake_task is not None:
                            intake_task.cancel()
                        await asyncio.gather(
                            delivery_task, *(item for item in (intake_task,) if item is not None),
                            return_exceptions=True,
                        )
                        raise
                delivered, intake = await asyncio.wait_for(
                    asyncio.gather(delivery_task, intake_task), timeout=30,
                )
            assert json.loads(delivered.outcome_json)["delivery_state"] == "acknowledged"
            assert intake.status_code in {404, 409}, intake.text
            async with h.factory() as session:
                assert await session.scalar(text(
                    "SELECT count(*) FROM public.submissions "
                    "WHERE task_id=:task AND version>1"
                ), {"task": h.request.task_id}) == 0
                assert await session.scalar(text(
                    "SELECT count(*) FROM public.task_revision_expirations "
                    "WHERE routing_manifest_id=:source"
                ), {"source": source_id}) == 1


async def test_expired_notice_retries_after_unknown_ack_without_new_effect(
    tmp_path, isolated_database_env, monkeypatch,
):
    """The outcome notice revalidates one committed receipt after a lost ACK."""
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id, _, _ = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
        )
        async with h.factory() as session:
            receipt = await session.scalar(select(TaskRevisionExpiration).where(
                TaskRevisionExpiration.routing_manifest_id == source_id,
            ))
            assert receipt is not None
            notice_id = receipt.outcome_event_id
        notice_handler = TransactionalTaskRevisionExpiredNoticeHandler(
            h.factory, observer=CommittedInvocationReader(h.factory),
        )
        delivery = outbox_delivery(
            h.factory, authorization_factory=outbox_dispatch_authorization,
            registry=HandlerRegistry(
                [(REVISION_EXPIRED_EVENT, 1, notice_handler)],
                replay_safe=frozenset({(REVISION_EXPIRED_EVENT, 1)}),
            ),
            options=DeliveryOptions(lease_seconds=30, handler_timeout_seconds=25,
                                    retry_base_seconds=1, retry_cap_seconds=1),
        )
        claim = await delivery.claim(notice_id, h.request.project_id, "revision-notice-ack-loss")
        assert claim is not None
        envelope = await delivery._begin_invocation(claim)
        assert envelope is not None
        assert await notice_handler(envelope) is HandlerOutcome.ACKNOWLEDGE
        async with h.factory() as session:
            db_now = await session.scalar(select(func.clock_timestamp()))
        await asyncio.sleep(max(0, (claim.claim_expires_at - db_now).total_seconds()) + 0.2)
        recovered = await delivery.recover(notice_id, h.request.project_id)
        assert recovered is not None
        assert json.loads(recovered.outcome_json)["invocation_unknown"] is True
        assert json.loads(recovered.outcome_json)["delivery_state"] == "retryable"
        await asyncio.sleep(1.1)
        acknowledged = await delivery.deliver(
            notice_id, h.request.project_id, "revision-notice-replay",
        )
        assert acknowledged is not None
        assert json.loads(acknowledged.outcome_json)["delivery_state"] == "acknowledged"
        async with h.factory() as session:
            assert await session.scalar(text(
                "SELECT count(*) FROM public.task_revision_expirations "
                "WHERE routing_manifest_id=:source"
            ), {"source": source_id}) == 1
            assert await session.scalar(text(
                "SELECT count(*) FROM public.audit_events "
                "WHERE event_type='TaskRevisionExpired' "
                "AND event_payload->'references'->>'routing_manifest_id'=:source"
            ), {"source": str(source_id)}) == 1
