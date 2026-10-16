"""PostgreSQL owns attempt-outcome evidence, decision times and update stamps."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.tasks.post_submit_routing.test_source_preparation import routing_source


async def _refused(h, statement, match, **values):
    with pytest.raises(DBAPIError, match=match):
        async with h.factory.begin() as session:
            await session.execute(text(statement), values)


async def test_attempt_outcome_needs_owner_evidence_and_is_final(tmp_path, isolated_database_env):
    async with routing_source(tmp_path, isolated_database_env) as h:
        submission = {"id": h.request.submission_id}
        update = "UPDATE public.submissions SET attempt_status=:status WHERE id=:id"
        # Rejection straight from evaluation needs an exhaustion receipt.
        for status in ("accepted", "needs_revision", "review_pending", "rejected"):
            await _refused(h, update, "requires owner evidence", status=status, **submission)
        await _refused(h, update, "not allowed|ck_submissions_attempt_status",
                       status="evaluation_pending_typo", **submission)
        await _refused(
            h, "UPDATE public.submissions SET decided_at=clock_timestamp() WHERE id=:id",
            "decision is immutable", **submission,
        )
        await _refused(
            h, "UPDATE public.submissions SET status_reason='revision_deadline_expired' WHERE id=:id",
            "decision is immutable", **submission,
        )
        async with h.factory() as session:
            assert (await session.execute(text(
                "SELECT attempt_status,status_reason,decided_at FROM public.submissions WHERE id=:id"
            ), submission)).one() == ("evaluation_pending", None, None)


async def test_new_attempts_start_pending_and_stamps_are_database_owned(
    tmp_path, isolated_database_env,
):
    async with routing_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            before = (await session.execute(text("""
                SELECT s.updated_at, t.updated_at, a.updated_at
                FROM public.submissions s JOIN public.workstream_tasks t ON t.id=s.task_id
                JOIN public.task_assignments a ON a.id=s.task_assignment_id WHERE s.id=:id
            """), {"id": h.request.submission_id})).one()
        async with h.factory.begin() as session:
            # Raw SQL that does not mention updated_at still moves it.
            await session.execute(text(
                "UPDATE public.workstream_tasks SET title=title WHERE id=:id"
            ), {"id": h.request.task_id})
            await session.execute(text(
                "UPDATE public.task_assignments SET accepted_at=accepted_at WHERE id=:id"
            ), {"id": h.request.assignment_id})
            await session.execute(text(
                "UPDATE public.submissions SET status=status WHERE id=:id"
            ), {"id": h.request.submission_id})
        async with h.factory() as session:
            after = (await session.execute(text("""
                SELECT s.updated_at, t.updated_at, a.updated_at
                FROM public.submissions s JOIN public.workstream_tasks t ON t.id=s.task_id
                JOIN public.task_assignments a ON a.id=s.task_assignment_id WHERE s.id=:id
            """), {"id": h.request.submission_id})).one()
        assert all(later > earlier for earlier, later in zip(before, after))


async def test_assignment_start_requires_the_started_task(tmp_path, isolated_database_env):
    async with routing_source(tmp_path, isolated_database_env) as h:
        assignment = {"id": h.request.assignment_id}
        # The task is past in_progress, so the assignment cannot gain a start now.
        await _refused(
            h, "UPDATE public.task_assignments SET started_at=clock_timestamp() WHERE id=:id",
            "assignment start requires the started task", **assignment,
        )


async def test_a_recorded_decision_cannot_be_rewritten(tmp_path, isolated_database_env):
    from app.adapters.tasks import task_post_submit_outcome
    from tests.tasks.post_submit_routing.remediation_support import remediation_source

    async with remediation_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            await task_post_submit_outcome(session, h.factory).apply(
                h.envelope, current_generation=None,
            )
        submission = {"id": h.request.submission_id}
        async with h.factory() as session:
            decided = (await session.execute(text(
                "SELECT attempt_status,decided_at FROM public.submissions WHERE id=:id"
            ), submission)).one()
        assert decided[0] == "needs_revision" and decided[1] is not None
        for status in ("evaluation_pending", "review_pending", "accepted"):
            await _refused(
                h, "UPDATE public.submissions SET attempt_status=:status WHERE id=:id",
                "not allowed", status=status, **submission,
            )
        # Rejection needs a revision expiration receipt for this exact source.
        await _refused(
            h, "UPDATE public.submissions SET attempt_status='rejected' WHERE id=:id",
            "requires owner evidence", **submission,
        )
        await _refused(
            h, "UPDATE public.submissions SET decided_at=decided_at - interval '1 day' WHERE id=:id",
            "decision is immutable", **submission,
        )
        async with h.factory() as session:
            assert (await session.execute(text(
                "SELECT attempt_status,decided_at FROM public.submissions WHERE id=:id"
            ), submission)).one() == decided
