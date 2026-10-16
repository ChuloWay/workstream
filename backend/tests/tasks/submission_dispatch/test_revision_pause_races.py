"""Real delivery and TASK-lock races against immutable paused revision heads."""

import asyncio
import json
from uuid import UUID

import pytest
from sqlalchemy import select, text

from app.adapters.outbox import production_outbox_delivery
from app.core.identifiers import new_record_id
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.revision.models import TaskRevisionPreparation
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import activate_successor_guide
from tests.tasks.submission_dispatch.test_revision_clock_sql import (
    REAL_DEADLINE_WINDOW_SECONDS,
    _wait_for_parent_deadline,
)
from tests.tasks.submission_dispatch.test_revision_expiry import expire_retained_revision
from tests.tasks.submission_dispatch.test_revision_pause import _read_prep, _repair
from tests.tasks.test_public_submission_intake import _client


async def _revision_state(h):
    """Observe business effects independently of OUTBOX's delivery audit writes."""
    async with h.factory() as session:
        return (
            await session.execute(
                text("""
            SELECT (SELECT jsonb_agg(to_jsonb(p) ORDER BY p.sequence)
                    FROM public.task_revision_preparations p WHERE p.task_id=:task),
                   (SELECT to_jsonb(t) FROM public.workstream_tasks t WHERE t.id=:task),
                   (SELECT to_jsonb(a) FROM public.task_assignments a WHERE a.id=:assignment),
                   (SELECT count(*) FROM public.task_revision_expirations WHERE task_id=:task),
                   (SELECT count(*) FROM public.submissions WHERE task_id=:task)
        """),
                {"task": h.request.task_id, "assignment": h.request.assignment_id},
            )
        ).one()


@pytest.mark.parametrize("resume", [False, True])
async def test_due_old_timer_cannot_expire_paused_or_resumed_head(
    tmp_path,
    isolated_database_env,
    monkeypatch,
    resume,
):
    """An actual claimed old timer ACKs without closing either kind of later head."""
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id, _, timer_id = await expire_retained_revision(
            h,
            monkeypatch=monkeypatch,
            isolated_database_env=isolated_database_env,
            deliver=False,
            window_seconds=REAL_DEADLINE_WINDOW_SECONDS,
        )
        root = await _read_prep(h)
        await activate_successor_guide(h, max_revision_rounds=0)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            paused_view = await _repair(client, h, root)
            paused = await _read_prep(h, UUID(paused_view["preparation_id"]))
            assert paused.deadline_at is None
            async with h.factory() as session:
                notice_id = await session.scalar(
                    select(OutboxEvent.event_id).where(
                        OutboxEvent.idempotency_key
                        == f"task.revision.context-blocked:{source_id}:{paused.id}",
                    )
                )
            assert notice_id is not None
            notice = await production_outbox_delivery(h.factory).deliver(
                notice_id,
                h.request.project_id,
                "paused-context-pm-attention-proof",
            )
            assert notice is not None
            assert json.loads(notice.outcome_json)["delivery_state"] == "acknowledged"
            if resume:
                await activate_successor_guide(h, version="v3")
                resumed_view = await _repair(client, h, paused)
                current = await _read_prep(h, UUID(resumed_view["preparation_id"]))
                assert current.deadline_at > root.deadline_at
        before = await _revision_state(h)
        await _wait_for_parent_deadline(h, timer_id)
        delivered = await h.expiry_delivery.deliver(
            timer_id,
            h.request.project_id,
            "stale-timer-after-pause-proof",
        )
        assert delivered is not None
        assert json.loads(delivered.outcome_json)["delivery_state"] == "acknowledged", (
            delivered.outcome_json,
            getattr(h, "expiry_handler_error", None),
        )
        assert await _revision_state(h) == before
        assert before[1]["status"] == "needs_revision" and before[2]["status"] == "active"
        assert before[3] == 0 and before[4] == 1


async def test_expiry_beats_real_pm_repair_waiting_for_task_past_deadline(
    tmp_path,
    isolated_database_env,
    monkeypatch,
):
    """A repair admitted before the deadline cannot pause after TASK custody arrives."""
    async with remediation_source(tmp_path, isolated_database_env) as h:
        _, _, timer_id = await expire_retained_revision(
            h,
            monkeypatch=monkeypatch,
            isolated_database_env=isolated_database_env,
            deliver=False,
            window_seconds=REAL_DEADLINE_WINDOW_SECONDS,
        )
        await activate_successor_guide(h, max_revision_rounds=0)
        original = TaskRepository.lock_project_task
        waiter = "revision-pause-wait-" + new_record_id().hex
        expiry_waiter = "revision-expiry-wait-" + new_record_id().hex
        task_id, project_id = h.request.task_id, h.request.project_id
        lock_name = waiter

        async def named_lock(repository, project_id, task_id):
            await repository._session.execute(
                text("SELECT set_config('application_name',:name,true)"), {"name": lock_name}
            )
            return await original(repository, project_id, task_id)

        async with _client(h, monkeypatch, isolated_database_env) as client:
            async with h.factory() as blocker, blocker.begin():
                await original(TaskRepository(blocker), project_id, task_id)
                blocker_pid = await blocker.scalar(text("SELECT pg_backend_pid()"))
                with monkeypatch.context() as patch:
                    patch.setattr(TaskRepository, "lock_project_task", named_lock)
                    pending = asyncio.create_task(
                        client.post(
                            f"/api/v1/projects/{project_id}/tasks/{task_id}/revision-context/repair",
                            json={
                                "parent_preparation_id": str(h.revision_preparation_id),
                                "parent_preparation_sha256": h.revision_preparation_sha256,
                                "reason": "Pause only if the running window still permits it",
                            },
                            headers={"Idempotency-Key": str(new_record_id())},
                        ),
                        name=waiter,
                    )
                    expiry_pending = None
                    try:
                        await asyncio.wait_for(
                            wait_for_named_database_lock(
                                isolated_database_env,
                                waiter,
                                expected_blocker_pid=blocker_pid,
                            ),
                            20,
                        )
                        await _wait_for_parent_deadline(h, timer_id)
                        # PM is already inside its named row wait. Name the
                        # later handler connection independently of its child task.
                        lock_name = expiry_waiter
                        expiry_pending = asyncio.create_task(
                            h.expiry_delivery.deliver(
                                timer_id,
                                project_id,
                                "expiry-after-waiting-pause-proof",
                            ),
                            name=expiry_waiter,
                        )
                        await asyncio.wait_for(
                            wait_for_named_database_lock(
                                isolated_database_env,
                                expiry_waiter,
                            ),
                            20,
                        )
                        await blocker.commit()
                        response = await asyncio.wait_for(pending, 25)
                        delivered = await asyncio.wait_for(expiry_pending, 25)
                    finally:
                        if not pending.done():
                            pending.cancel()
                        if expiry_pending is not None and not expiry_pending.done():
                            expiry_pending.cancel()
                        await asyncio.gather(
                            *[item for item in (pending, expiry_pending) if item is not None],
                            return_exceptions=True,
                        )
            assert response.status_code == 409, response.text
            assert response.json()["error"]["code"] == "revision_deadline_expired"
        assert delivered is not None
        assert json.loads(delivered.outcome_json)["delivery_state"] == "acknowledged", (
            delivered.outcome_json,
            getattr(h, "expiry_handler_outcome", None),
            getattr(h, "expiry_handler_error", None),
        )
        state = await _revision_state(h)
        assert len(state[0]) == 1 and state[1]["status"] == "ready"
        assert state[2]["status"] == "revision_expired" and state[3] == 1 and state[4] == 1
        async with h.factory() as session:
            root = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
            assert root.deadline_at is not None
