"""Actual 0047 blocked clocks upgrade without history rewrites or renewed time."""

import asyncio
import json
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import DateTime, select, text

from app.adapters.tasks import task_post_submit_outcome, task_revision_recovery
from app.modules.tasks.post_submit_routing import outcome as routing_outcome
from app.modules.tasks.revision.models import TaskRevisionPreparation
from tests.migration_revision_fixtures import insert_0047_preparation, retained_revision_rows
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.submission_dispatch.test_revision_expiry import _provision_expirer
from tests.test_alembic import HEAD_REVISION, _alembic_config, _execute

pytestmark = pytest.mark.postgres_schema_contract


async def _old_blocked_preparation(
    session, *, manifest, candidate, audit_event_id,
):
    """Use the original guarded writer with its database-selected historical time."""
    await session.refresh(manifest, attribute_names=["created_at"])
    # Historical system discovery could retain a blocked target without PM rebase.
    blocked = candidate.model_copy(update={
        "target": None, "target_post_policy_json": None, "target_max_revision_rounds": None,
    })
    return await insert_0047_preparation(
        session, manifest=manifest, candidate=blocked, audit_event_id=audit_event_id,
    )


async def _wait_old_window_due(h, deadline):
    async with h.factory() as session:
        remaining = await session.scalar(text(
            "SELECT greatest(0,extract(epoch FROM (CAST(:deadline AS timestamptz)-clock_timestamp())))"
        ), {"deadline": deadline})
        assert 0 <= remaining <= 60
        await session.execute(text("SELECT pg_sleep(:seconds)"), {"seconds": float(remaining)})
        assert await session.scalar(text("SELECT clock_timestamp()>=:deadline"), {"deadline": deadline})


@pytest.mark.parametrize("already_due", [False, True])
async def test_retained_blocked_clock_pauses_once_or_stays_due(
    tmp_path, isolated_database_env, migration_lock, monkeypatch, already_due,
):
    """Recovery appends fresh authority and remaining time; a due head gains nothing."""
    with migration_lock():
        await _execute(isolated_database_env, "drop schema public cascade; create schema public")
        await asyncio.to_thread(command.upgrade, _alembic_config(), "0047_revision_recovery")
        async with remediation_source(tmp_path, isolated_database_env) as h:
            window_seconds = 60 if already_due else 600
            original_manifest = routing_outcome._manifest

            def old_manifest(*args, **kwargs):
                manifest = original_manifest(*args, **kwargs)
                manifest.created_at = text("""
                    SELECT clock_timestamp()-make_interval(hours=>p.revision_deadline_hours)
                        +make_interval(secs=>:historical_window_seconds) AS created_at
                    FROM public.submissions s
                    JOIN public.revision_policies p ON p.id=s.locked_revision_policy_id
                    WHERE s.id=:historical_submission_id
                """).bindparams(
                    historical_window_seconds=window_seconds,
                    historical_submission_id=manifest.submission_id,
                ).columns(created_at=DateTime(timezone=True)).scalar_subquery()
                return manifest

            with monkeypatch.context() as patch:
                patch.setattr(routing_outcome, "_manifest", old_manifest)
                patch.setattr(routing_outcome, "prepare_revision", _old_blocked_preparation)
                async with h.factory() as session, session.begin():
                    outcome = await task_post_submit_outcome(session, h.factory).apply(
                        h.envelope, current_generation=None,
                    )
            source_id = outcome.routing_manifest_id
            async with h.factory() as session:
                before = await retained_revision_rows(session, source_id, root_only=True)
                original = json.loads(before["task_revision_preparations"][0][0])
                assert original["blocked_reason"] == "context_blocked"
                assert await session.scalar(text(
                    "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgenabled='D'"
                )) == 0
            await asyncio.to_thread(command.upgrade, _alembic_config(), HEAD_REVISION)
            await _provision_expirer(h.factory)
            async with h.factory() as session:
                root = await session.scalar(select(TaskRevisionPreparation))
                assert root.clock_observed_at is None and root.deadline_at is not None
                assert await retained_revision_rows(session, source_id, root_only=True) == before
            if already_due:
                await _wait_old_window_due(h, root.deadline_at)
            async with h.factory() as session, session.begin():
                assert await task_revision_recovery(session).recover(source_id) is (not already_due)
            async with h.factory() as session:
                rows = (await session.scalars(select(TaskRevisionPreparation).order_by(
                    TaskRevisionPreparation.sequence,
                ))).all()
                assert len(rows) == (1 if already_due else 2)
                assert await retained_revision_rows(session, source_id, root_only=True) == before
                if not already_due:
                    child = rows[-1]
                    assert child.predecessor_id == root.id and child.deadline_at is None
                    assert child.repair_idempotency_key == root.id
                    assert child.remaining_microseconds == (
                        root.deadline_at - child.clock_observed_at
                    ) // timedelta(microseconds=1)
                    assert 0 < child.remaining_microseconds < window_seconds * 1_000_000
                    assert child.outcome == "blocked" and child.blocked_reason == "context_blocked"
                    assert child.authorization_decision_id != root.authorization_decision_id
                    assert await session.scalar(text(
                        "SELECT action_id FROM public.audit_events WHERE id=:id"
                    ), {"id": child.authorization_decision_id}) == "task.revision.recover"
                    notice = (await session.execute(text(
                        "SELECT event_type,payload FROM public.outbox_events WHERE idempotency_key=:key"
                    ), {"key": f"task.revision.context-blocked:{source_id}:{child.id}"})).one()
                    assert notice[0] == "TaskRevisionContextBlocked"
                    assert notice[1]["preparation_sha256"] == child.preparation_sha256
                    assert notice[1]["remaining_microseconds"] == child.remaining_microseconds
                count = await session.scalar(text("SELECT count(*) FROM public.audit_events"))
            async with h.factory() as session, session.begin():
                assert await task_revision_recovery(session).recover(source_id) is False
            async with h.factory() as session:
                assert await session.scalar(text("SELECT count(*) FROM public.audit_events")) == count
                assert await retained_revision_rows(session, source_id, root_only=True) == before
