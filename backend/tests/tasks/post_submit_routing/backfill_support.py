"""Prove migration 0048's backfill reproduces what the live deciding owners wrote."""

import importlib.util
from pathlib import Path

from sqlalchemy import text

_PATH = Path(__file__).resolve().parents[3] / "alembic/versions/0048_attempt_outcome_findings.py"
_SPEC = importlib.util.spec_from_file_location("migration_0048", _PATH)
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
