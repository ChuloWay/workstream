"""Direct SQL and commit-boundary denials for database-owned revision clocks."""

import asyncio
import json
from uuid import UUID

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.adapters.audit import _TaskTransitionAudit
from app.core.identifiers import new_record_id
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.revision.models import TaskRevisionPreparation
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import activate_successor_guide
from tests.tasks.submission_dispatch.test_revision_expiry import expire_retained_revision
from tests.tasks.test_public_submission_intake import _client
from tests.test_submission_predecessor_custody import _fixture_revision_context

REAL_DEADLINE_WINDOW_SECONDS = 45


async def test_large_revision_allowance_preserves_every_microsecond(isolated_database_env):
    """Resuming a valid large allowance cannot round through floating point."""
    allowances = [2**53 + 1, (2**31 - 1) * 3_600_000_000 - 1]
    connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
    try:
        rows = await connection.fetch(
            """
            SELECT remaining,
              extract(epoch FROM public.revision_clock_interval(remaining))*1000000 AS interval_us,
              extract(epoch FROM ((timestamptz '2000-01-01 00:00:00+00'
                +public.revision_clock_interval(remaining))
                -timestamptz '2000-01-01 00:00:00+00'))*1000000 AS deadline_us
            FROM unnest($1::bigint[]) AS remaining ORDER BY remaining
        """,
            allowances,
        )
    finally:
        await connection.close()
    assert [row["remaining"] for row in rows] == allowances
    for row in rows:
        assert row["interval_us"] == row["remaining"]
        assert row["deadline_us"] == row["remaining"]


async def _clock_custody(h):
    """Snapshot all durable participants before the attempted pause transaction."""
    owners = (
        "task_revision_preparations",
        "task_assignments",
        "workstream_tasks",
        "submissions",
        "task_command_receipts",
        "audit_events",
        "outbox_events",
    )
    async with h.factory() as session:
        return {
            table: await session.scalar(
                text(
                    f"SELECT jsonb_agg(to_jsonb(row) ORDER BY to_jsonb(row)::text) FROM public.{table} row"
                )
            )
            for table in owners
        }


async def test_direct_sql_cannot_supply_authoritative_clock_values(
    tmp_path,
    isolated_database_env,
):
    """Raw INSERTs cannot backdate observations or manufacture paused allowance."""
    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        async with h.factory() as session:
            original = await session.scalar(
                text("SELECT to_jsonb(p) FROM public.task_revision_preparations p WHERE id=:id"),
                {"id": h.revision_preparation_id},
            )
        before = await _clock_custody(h)
        attempts = [
            (location, field, value)
            for field, value in (
                ("clock_observed_at", "2000-01-01T00:00:00+00:00"),
                ("remaining_microseconds", 10**15),
                ("deadline_at", "2100-01-01T00:00:00+00:00"),
            )
            for location in ("column", "packet")
        ]
        for location, field, value in attempts:
            forged = dict(original)
            next_id = new_record_id()
            forged.update(
                id=str(next_id),
                predecessor_id=original["id"],
                sequence=2,
                deadline_at=None,
                remaining_microseconds=None,
                clock_observed_at=None,
            )
            forged["packet"] = dict(
                original["packet"],
                id=str(next_id),
                predecessor_id=original["id"],
                sequence=2,
                deadline_at=None,
                remaining_microseconds=None,
                clock_observed_at=None,
            )
            (forged if location == "column" else forged["packet"])[field] = value
            with pytest.raises(IntegrityError, match="revision clock is database owned") as error:
                async with h.factory() as session, session.begin():
                    await session.execute(
                        text(
                            "INSERT INTO public.task_revision_preparations "
                            "SELECT * FROM jsonb_populate_record(NULL::public.task_revision_preparations,"
                            "CAST(:row AS jsonb))"
                        ),
                        {"row": json.dumps(forged)},
                    )
            assert error.value.orig.sqlstate == "23514"
            assert await _clock_custody(h) == before


async def _wait_for_parent_deadline(h, timer_id):
    """Observe the actual PostgreSQL deadline without changing the production clock."""
    async with h.factory() as session:
        remaining = await session.scalar(
            text(
                "SELECT greatest(0,extract(epoch FROM (not_before_at-clock_timestamp()))) "
                "FROM public.outbox_events WHERE event_id=:id"
            ),
            {"id": timer_id},
        )
        assert remaining is not None and 0 < remaining <= REAL_DEADLINE_WINDOW_SECONDS
        await session.execute(text("SELECT pg_sleep(:seconds)"), {"seconds": float(remaining)})
        assert (
            await session.scalar(
                text(
                    "SELECT clock_timestamp()>=not_before_at FROM public.outbox_events WHERE event_id=:id"
                ),
                {"id": timer_id},
            )
            is True
        )


async def test_pause_cannot_commit_after_running_parent_deadline(
    tmp_path,
    isolated_database_env,
    monkeypatch,
):
    """A genuine PM pause staged before the deadline rolls back after it passes."""
    async with remediation_source(tmp_path, isolated_database_env) as h:
        _, _, timer_id = await expire_retained_revision(
            h,
            monkeypatch=monkeypatch,
            isolated_database_env=isolated_database_env,
            deliver=False,
            window_seconds=REAL_DEADLINE_WINDOW_SECONDS,
        )
        await activate_successor_guide(h, max_revision_rounds=0)
        before = await _clock_custody(h)
        staged, release = asyncio.Event(), asyncio.Event()
        original = _TaskTransitionAudit.record_revision_repair
        repair_root = AuthorizedTaskCommands._repair_revision_context_root
        database_errors = []

        async def observe_database_error(commands, *args, **kwargs):
            try:
                return await repair_root(commands, *args, **kwargs)
            except SQLAlchemyError as error:
                origin = getattr(error, "orig", None)
                cause = getattr(origin, "__cause__", None) or origin
                database_errors.append(
                    (
                        getattr(cause, "constraint_name", None),
                        getattr(cause, "sqlstate", None),
                        str(cause).splitlines()[0],
                    )
                )
                raise

        async def wait_after_all_participants(audit, facts):
            await original(audit, facts)
            staged.set()
            await asyncio.wait_for(release.wait(), 180)

        async with _client(h, monkeypatch, isolated_database_env) as client:
            with monkeypatch.context() as patch:
                patch.setattr(
                    _TaskTransitionAudit, "record_revision_repair", wait_after_all_participants
                )
                patch.setattr(
                    AuthorizedTaskCommands, "_repair_revision_context_root", observe_database_error
                )
                pending = asyncio.create_task(
                    client.post(
                        f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair",
                        json={
                            "parent_preparation_id": str(h.revision_preparation_id),
                            "parent_preparation_sha256": h.revision_preparation_sha256,
                            "reason": "Pause against the current approved zero-revision context",
                        },
                        headers={"Idempotency-Key": str(new_record_id())},
                    )
                )
                stage_waiter = asyncio.create_task(staged.wait())
                try:
                    done, _ = await asyncio.wait(
                        (pending, stage_waiter),
                        timeout=20,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if pending in done:
                        response = await pending
                        pytest.fail(
                            f"repair finished before staging: {response.status_code} "
                            f"{response.text}; database_errors={database_errors}"
                        )
                    assert stage_waiter in done
                    assert await _clock_custody(h) == before
                    await _wait_for_parent_deadline(h, timer_id)
                    release.set()
                    response = await asyncio.wait_for(pending, 20)
                    assert response.status_code == 409, response.text
                    assert response.json()["error"]["code"] == "revision_deadline_expired"
                    assert len(database_errors) == 1
                    assert database_errors[0][:2] == (
                        "ck_revision_preparation_deadline_expired",
                        "23514",
                    )
                finally:
                    release.set()
                    stage_waiter.cancel()
                    if not pending.done():
                        pending.cancel()
                    await asyncio.gather(pending, stage_waiter, return_exceptions=True)
        assert await _clock_custody(h) == before
        async with h.factory() as session:
            root = await session.get(TaskRevisionPreparation, UUID(str(h.revision_preparation_id)))
            assert root.deadline_at is not None and root.remaining_microseconds is None
