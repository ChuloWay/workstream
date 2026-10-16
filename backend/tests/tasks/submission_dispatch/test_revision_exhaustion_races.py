"""Competing real terminal-failure transactions retain exactly one closed assignment."""

import asyncio

import pytest
from sqlalchemy import select, text

from app.adapters.tasks import task_post_submit_outcome
from app.core.identifiers import new_record_id
from app.modules.tasks.revision.models import TaskRevisionExhaustion
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.tasks.post_submit_routing.outcome_support import outcome_snapshot
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.submission_dispatch.test_revision_exhaustion import terminal_facts


async def _snapshot(session):
    """Include immutable evidence and request rows as well as every routing participant.

    Submission packets are compared without their attempt outcome, which the
    terminal writer records; the last element holds that outcome.
    """
    routing = tuple(await outcome_snapshot(session))
    retained = (await session.execute(text("""
        SELECT (SELECT jsonb_agg(to_jsonb(r)-ARRAY['attempt_status','status_reason','decided_at','updated_at']
                  ORDER BY r.id) FROM public.submissions r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.task_revision_exhaustions r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.task_revision_preparations r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.task_revision_expirations r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.route_operation_id)
             FROM public.task_post_submit_routing_requests r),
          (SELECT jsonb_agg(jsonb_build_array(r.attempt_status,r.status_reason) ORDER BY r.id)
             FROM public.submissions r)
    """))).one()
    return routing, tuple(retained)


async def _apply(session, h):
    return await task_post_submit_outcome(session, h.factory).apply(
        h.envelope, current_generation=None,
    )


def _new_ids(snapshot, baseline, index, field):
    return {row[field] for row in snapshot[0][index] or []} - {
        row[field] for row in baseline[0][index] or []
    }


@pytest.mark.parametrize("first_worker", [0, 1], ids=["worker-a-first", "worker-b-first"])
@pytest.mark.parametrize("roll_back_first", [False, True], ids=["commit", "rollback"])
async def test_duplicate_terminal_failure_serializes_and_rolled_back_evidence_stays_absent(
    tmp_path, isolated_database_env, first_worker, roll_back_first,
):
    """The real waiter replays a committed winner or replaces a fully rolled-back holder."""
    async with remediation_source(tmp_path, isolated_database_env, max_revision_rounds=0) as h:
        async with h.factory() as reader:
            before = await _snapshot(reader)
        name = "terminal-failure-wait-" + new_record_id().hex
        async with h.factory() as worker_a, h.factory() as worker_b:
            workers = (worker_a, worker_b)
            holder, waiter = workers[first_worker], workers[1 - first_worker]
            await holder.begin()
            holder_pid = await holder.scalar(text("SELECT pg_backend_pid()"))
            staged = await _apply(holder, h)
            staged_receipt = await holder.scalar(select(TaskRevisionExhaustion))
            assert staged_receipt is not None and not staged.replayed
            staged_id = staged_receipt.id
            staged_snapshot = await _snapshot(holder)

            async def compete():
                async with waiter.begin():
                    await waiter.execute(text(
                        "SELECT set_config('application_name',:name,true)"
                    ), {"name": name})
                    return await _apply(waiter, h)

            pending = asyncio.create_task(compete(), name=name)
            try:
                await asyncio.wait_for(wait_for_named_database_lock(
                    isolated_database_env, name, expected_blocker_pid=holder_pid,
                ), 20)
                assert not pending.done()
                async with h.factory() as reader:
                    assert await _snapshot(reader) == before
                if roll_back_first:
                    await holder.rollback()
                else:
                    await holder.commit()
                committed = await asyncio.wait_for(pending, 30)
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
                if holder.in_transaction():
                    await holder.rollback()
        receipt = await terminal_facts(h, committed, expected_round=0)
        async with h.factory() as reader:
            after = await _snapshot(reader)
        assert len(after[1][1]) == 1
        assert after[1][0] == before[1][0]
        assert after[1][5] == [["rejected", "revision_limit_reached"]]
        if roll_back_first:
            assert not committed.replayed and receipt.id != staged_id
            assert committed.authorization_decision_id != staged.authorization_decision_id
            assert committed.outcome_event_id != staged.outcome_event_id
            for index, field in ((4, "id"), (5, "event_id")):
                staged_ids = _new_ids(staged_snapshot, before, index, field)
                committed_ids = _new_ids(after, before, index, field)
                assert staged_ids and len(staged_ids) == len(committed_ids)
                assert staged_ids.isdisjoint(committed_ids)
        else:
            assert committed == staged.model_copy(update={"replayed": True})
            assert receipt.id == staged_id and after == staged_snapshot
