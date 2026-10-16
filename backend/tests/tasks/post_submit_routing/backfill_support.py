"""Prove migration 0049's backfill reproduces what the live deciding owners wrote."""

import importlib.util
from pathlib import Path

from sqlalchemy import text

_PATH = Path(__file__).resolve().parents[3] / "alembic/versions/0049_attempt_outcome_findings.py"
_SPEC = importlib.util.spec_from_file_location("migration_0049", _PATH)
_MIGRATION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATION)
_SUBMISSION_FACTS = (
    "SELECT id::text, attempt_status, status_reason, decided_at "
    "FROM public.submissions ORDER BY id"
)
_ASSIGNMENT_FACTS = "SELECT id::text, started_at FROM public.task_assignments ORDER BY id"


async def _replay(session, script):
    for statement in filter(str.strip, script.split(";")):
        await session.execute(text(statement))


async def assert_backfill_matches_live(factory, *, assignments=False):
    """Erase the live facts, rerun the backfill, and require identical results.

    Everything runs in one transaction that is rolled back, so the caller's
    committed evidence is untouched.
    """
    async with factory() as session:
        await session.begin()
        try:
            live = (await session.execute(text(_SUBMISSION_FACTS))).all()
            assert live or assignments, "backfill proof needs live evidence"
            live_starts = (await session.execute(text(_ASSIGNMENT_FACTS))).all()
            for table in ("submissions", "task_assignments"):
                await session.execute(text(f"ALTER TABLE public.{table} DISABLE TRIGGER USER"))
            await session.execute(text(
                "UPDATE public.submissions SET attempt_status='evaluation_pending', "
                "status_reason=NULL, decided_at=NULL"
            ))
            await _replay(session, _MIGRATION.BACKFILL_SUBMISSION_ATTEMPTS)
            assert (await session.execute(text(_SUBMISSION_FACTS))).all() == live
            if assignments:
                await session.execute(text("UPDATE public.task_assignments SET started_at=NULL"))
                await _replay(session, _MIGRATION.BACKFILL_ASSIGNMENT_STARTS)
                backfilled = dict((await session.execute(text(_ASSIGNMENT_FACTS))).all())
                for assignment_id, started_at in live_starts:
                    # Audit time is the transaction start; the live stamp is taken later
                    # in that same transaction.
                    restored = backfilled[assignment_id]
                    assert (restored is None) == (started_at is None), assignment_id
                    if started_at is not None:
                        assert 0 <= (started_at - restored).total_seconds() < 5
        finally:
            await session.rollback()


_STALE_FINDING = {
    "checker_runs": (
        "UPDATE public.checker_runs SET result_json=v.body, result_digest='sha256:'||"
        "encode(sha256(convert_to(v.body,'UTF8')),'hex') FROM (SELECT (result_json::jsonb #- "
        "CAST(:path AS text[]))::text AS body FROM public.checker_runs WHERE id=:id) v WHERE id=:id"
    ),
    "selected_pre_submit_runs": (
        "UPDATE public.selected_pre_submit_runs SET terminal_json=terminal_json #- "
        "CAST(:path AS text[]) WHERE id=:id"
    ),
}


async def assert_upgrade_refuses_stale_findings(factory, *, store, row_id):
    """0049 accepts the live finding shape and refuses a retained pre-0049 one.

    Removing ``check_id`` from one retained finding reproduces evidence written
    before the contract required it. The rollback leaves custody untouched.
    """
    path = ["execution", "external_members", "0", "result", "findings", "0", "check_id"]
    async with factory() as session:
        await session.begin()
        try:
            connection = await session.connection()
            await connection.run_sync(_MIGRATION.refuse_incompatible_retained_findings)
            await session.execute(text(f"ALTER TABLE public.{store} DISABLE TRIGGER USER"))
            changed = await session.execute(text(_STALE_FINDING[store]), {"id": str(row_id), "path": path})
            assert changed.rowcount == 1
            try:
                await connection.run_sync(_MIGRATION.refuse_incompatible_retained_findings)
            except RuntimeError as refused:
                assert f"{store}: 1 rows (e.g. {row_id})" in str(refused)
                assert "recreate this database" in str(refused)
            else:
                raise AssertionError("upgrade accepted a finding without check_id")
        finally:
            await session.rollback()
