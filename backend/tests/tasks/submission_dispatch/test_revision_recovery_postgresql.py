"""Retained checker failures gain exact expiry coverage through service discovery."""

import asyncio
import json
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.adapters.tasks import scan_task_revision_sources, task_revision_recovery
from app.core.identifiers import new_record_id
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.revision.models import TaskRevisionPreparation
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import activate_successor_guide
from tests.tasks.submission_dispatch.test_revision_capacity import _retain_pre_revision_source
from tests.tasks.submission_dispatch.test_revision_expiry import _provision_expirer
from tests.test_submission_predecessor_custody import _fixture_revision_context


@pytest.mark.parametrize("new_active_guide", [False, True])
async def test_discovery_freezes_original_retained_window_without_pm_or_rebase(
    tmp_path, isolated_database_env, new_active_guide,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        await _retain_pre_revision_source(h, source_id)
        if new_active_guide:
            await activate_successor_guide(h)
        service_actor = await _provision_expirer(h.factory)
        async with h.factory() as session:
            before = await session.scalar(text(
                "SELECT public.revision_task_lineage(to_jsonb(t)) "
                "FROM public.workstream_tasks t WHERE t.id=:task"
            ), {"task": h.request.task_id})
            source_window = (await session.execute(text("""
                SELECT m.created_at,
                       m.created_at+make_interval(hours=>p.revision_deadline_hours)
                FROM public.task_post_submit_routing_manifests m
                JOIN public.submissions s ON s.id=m.submission_id
                JOIN public.revision_policies p ON p.id=s.locked_revision_policy_id
                WHERE m.id=:source
            """), {"source": source_id})).one()

        recovered, _ = await scan_task_revision_sources(h.factory, None)
        if recovered != 1:
            # The scheduler deliberately isolates one bad source. Re-run the
            # same locked operation in a rolled-back test transaction to show
            # only bounded validation locations and types in a failure.
            try:
                async with h.factory() as session, session.begin():
                    await task_revision_recovery(session).recover(source_id)
                    raise AssertionError("recovery source was skipped without an error")
            except ValidationError as exc:
                pytest.fail(str([(item["loc"], item["type"]) for item in exc.errors()]))
        assert recovered == 1
        repeated, _ = await scan_task_revision_sources(h.factory, None)
        assert repeated == 0
        async with h.factory() as session:
            rows = (await session.scalars(select(TaskRevisionPreparation).where(
                TaskRevisionPreparation.routing_manifest_id == source_id,
            ))).all()
            assert len(rows) == 1
            root = rows[0]
            assert root.predecessor_id is None and root.sequence == 1
            assert root.repair_actor_id == service_actor
            assert root.repair_idempotency_key == source_id
            assert root.requested_at == source_window[0]
            assert root.deadline_at == source_window[1]
            assert root.outcome == ("blocked" if new_active_guide else "kept")
            assert root.blocked_reason == ("context_blocked" if new_active_guide else None)
            if new_active_guide:
                assert root.packet["candidate"]["target"] is None
            else:
                assert root.packet["candidate"]["target"] == root.packet["candidate"]["prior"]
            assert await session.scalar(text(
                "SELECT public.revision_task_lineage(to_jsonb(t)) "
                "FROM public.workstream_tasks t WHERE t.id=:task"
            ), {"task": h.request.task_id}) == before
            action = await session.scalar(text(
                "SELECT action_id FROM public.audit_events WHERE id=:decision"
            ), {"decision": root.authorization_decision_id})
            assert action == "task.revision.recover"
            event = await session.scalar(select(OutboxEvent).where(
                OutboxEvent.idempotency_key == f"task.revision.expire:{source_id}",
            ))
            assert event is not None
            assert event.not_before_at == root.deadline_at
            assert event.payload["root_preparation_id"] == str(root.id)
            assert event.payload["root_preparation_sha256"] == root.preparation_sha256
        if not new_active_guide:
            # The same root, packet, digest and service decision cannot be
            # replayed with a different AUTH request/correlation receipt.
            with pytest.raises(IntegrityError, match="revision repair authorization unavailable"):
                async with h.factory() as session, session.begin():
                    row = await session.scalar(text(
                        "SELECT to_jsonb(p) FROM public.task_revision_preparations p WHERE p.id=:id"
                    ), {"id": root.id})
                    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                    await session.execute(text(
                        "ALTER TABLE public.task_revision_preparations "
                        "DISABLE TRIGGER revision_preparation_immutable"
                    ))
                    await session.execute(text(
                        "DELETE FROM public.task_revision_preparations WHERE id=:id"
                    ), {"id": root.id})
                    await session.execute(text(
                        "ALTER TABLE public.task_revision_preparations "
                        "ENABLE TRIGGER revision_preparation_immutable"
                    ))
                    await session.execute(text(
                        "ALTER TABLE public.audit_events "
                        "DISABLE TRIGGER audit_events_reject_update_delete"
                    ))
                    await session.execute(text(
                        "UPDATE public.audit_events SET request_id=:other,correlation_id=:other "
                        "WHERE id=:decision"
                    ), {"other": new_record_id(), "decision": root.authorization_decision_id})
                    await session.execute(text(
                        "ALTER TABLE public.audit_events "
                        "ENABLE TRIGGER audit_events_reject_update_delete"
                    ))
                    row["creation_xid"] = await session.scalar(text("SELECT pg_current_xact_id()::text"))
                    await session.execute(text(
                        "INSERT INTO public.task_revision_preparations SELECT * FROM "
                        "jsonb_populate_record(NULL::public.task_revision_preparations, CAST(:row AS jsonb))"
                    ), {"row": json.dumps(row)})


async def test_discovery_registers_missing_root_event_once_under_race(
    tmp_path, isolated_database_env,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        original_root_id = h.revision_preparation_id
        await _provision_expirer(h.factory)
        async with h.factory() as session, session.begin():
            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            await session.execute(text(
                "ALTER TABLE public.outbox_events DISABLE TRIGGER outbox_events_custody"
            ))
            removed = await session.execute(text("""
                DELETE FROM public.outbox_events
                WHERE event_type='TaskRevisionExpiryRequested'
                  AND idempotency_key=:key AND attempt_count=0
                  AND claimed_at IS NULL AND delivery_state='pending'
                RETURNING event_id
            """), {"key": f"task.revision.expire:{source_id}"})
            assert len(removed.all()) == 1
            await session.execute(text(
                "ALTER TABLE public.outbox_events ENABLE TRIGGER outbox_events_custody"
            ))
        counts = await asyncio.gather(*(
            scan_task_revision_sources(h.factory, None)
            for _ in range(2)
        ))
        assert sum(count for count, _ in counts) == 1
        async with h.factory() as session:
            roots = (await session.scalars(select(TaskRevisionPreparation).where(
                TaskRevisionPreparation.routing_manifest_id == source_id,
            ))).all()
            assert len(roots) == 1
            assert UUID(str(roots[0].id)) == original_root_id
            assert roots[0].repair_actor_id is None
            events = (await session.scalars(select(OutboxEvent).where(
                OutboxEvent.idempotency_key == f"task.revision.expire:{source_id}",
            ))).all()
            assert len(events) == 1
            assert events[0].not_before_at == roots[0].deadline_at
            repairs = await session.scalar(text("""
                SELECT count(*) FROM public.audit_events
                WHERE event_type='TaskRevisionContextRepaired'
                  AND event_payload->'references'->>'routing_manifest_id'=:source
            """), {"source": str(source_id)})
            assert repairs == 1
