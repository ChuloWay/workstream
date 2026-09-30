"""Retained evidence constraints survive removal of the alternate checker writer."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.tasks.models import Submission
from app.modules.checkers.models import CheckerRun
from tests.test_tasks import create_started_task, complete_submission_payload
from tests.submission_fixtures import seed_retained_submission, seed_retained_checker_run
from .test_reads import history_case


@pytest.mark.parametrize("damage", ["missing", "mismatched"])
async def test_submission_policy_custody_rejects_changes(task_client, monkeypatch, damage):
    case = await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, case[2])
        original = submission.locked_post_submit_checker_policy_hash
        if damage == "missing":
            submission.locked_post_submit_checker_policy_id = None
            submission.locked_post_submit_checker_policy_version = None
            submission.locked_post_submit_checker_policy_hash = None
        else:
            submission.locked_post_submit_checker_policy_hash = "sha256:" + "0" * 64
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, case[2])
        assert submission.locked_post_submit_checker_policy_hash == original
        assert submission.locked_at is not None
        assert await session.get(CheckerRun, case[3]) is not None


async def retained_pair(client, monkeypatch):
    case = await history_case(client, monkeypatch)
    other = await create_started_task(client, case[0], monkeypatch, subject="other-checker-owner")
    submission = await seed_retained_submission(other["id"], complete_submission_payload())
    run = await seed_retained_checker_run(submission)
    return case, (other["id"], submission, run)


async def test_coherent_run_rebinding_is_rejected(task_client, monkeypatch):
    case, other = await retained_pair(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        before = await session.scalar(text("select to_jsonb(r) from checker_runs r where id=:id"), {"id":case[3]})
        with pytest.raises(IntegrityError, match="checker run custody is immutable"):
            await session.execute(text("update checker_runs set task_id=:task, submission_id=:submission where id=:id"),
                                  {"task":other[0], "submission":other[1], "id":case[3]})
        await session.rollback()
        assert await session.scalar(text("select to_jsonb(r) from checker_runs r where id=:id"), {"id":case[3]}) == before


@pytest.mark.parametrize("table,operation", [(table, operation) for table in ("checker_runs", "checker_results", "checker_submission_fences") for operation in ("delete", "truncate")])
async def test_retained_rows_cannot_be_removed(task_client, monkeypatch, table, operation):
    await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        before = list((await session.execute(text(f"select to_jsonb(r) from {table} r"))).scalars())
        assert before
        with pytest.raises(IntegrityError, match="custody is immutable"):
            await session.execute(text(f"delete from {table}" if operation == "delete" else f"truncate {table} cascade"))
        await session.rollback()
        assert list((await session.execute(text(f"select to_jsonb(r) from {table} r"))).scalars()) == before


@pytest.mark.parametrize("state", ["completed", "infrastructure_failed"])
async def test_terminal_outcome_fields_cannot_change(task_client, monkeypatch, state):
    from datetime import timedelta
    case = await history_case(task_client, monkeypatch, run_status=state)
    async with db_session.get_session_factory()() as session:
        before = await session.scalar(text("select to_jsonb(r) from checker_runs r where id=:id"), {"id":case[3]})
        original = await session.get(CheckerRun, case[3])
        changes = dict(status="running", routing_recommendation="task_setup_blocked", outcome_source="none",
                       passed_count=original.passed_count+1, warning_count=1, failed_count=original.failed_count+1,
                       blocking_count=original.blocking_count+1, started_at=original.started_at+timedelta(seconds=1),
                       completed_at=None, failure_code="invalid_output", finalize_evidence_id=str(new_record_id()),
                       worker_lease_id=str(new_record_id()), worker_lease_generation=42,
                       worker_lease_expires_at=original.worker_lease_expires_at+timedelta(seconds=1))
        for field, value in changes.items():
            run = await session.get(CheckerRun, case[3])
            assert getattr(run, field) != value
            setattr(run, field, value)
            with pytest.raises(IntegrityError, match="checker run outcome is immutable") as rejected:
                await session.flush()
            assert rejected.value.orig.sqlstate == "23514"
            await session.rollback()
            assert await session.scalar(text("select to_jsonb(r) from checker_runs r where id=:id"), {"id":case[3]}) == before


async def test_result_and_predecessor_custody(task_client, monkeypatch):
    case, other = await retained_pair(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        original = list((await session.execute(text("select to_jsonb(r) from checker_results r where checker_run_id=:id"), {"id":case[3]})).scalars())
        assert original
        with pytest.raises(IntegrityError, match="checker result custody is immutable"):
            await session.execute(text("update checker_results set checker_run_id=:run,task_id=:task,submission_id=:submission where checker_run_id=:id"),
                                  {"run":other[2], "task":other[0], "submission":other[1], "id":case[3]})
        await session.rollback()
        assert list((await session.execute(text("select to_jsonb(r) from checker_results r where checker_run_id=:id"), {"id":case[3]})).scalars()) == original
        with pytest.raises(IntegrityError, match="checker run custody is immutable"):
            await session.execute(text("update checker_runs set supersedes_checker_run_id=:foreign where id=:id"), {"foreign":other[2], "id":case[3]})
        await session.rollback()


async def test_finished_run_cannot_receive_late_result(task_client, monkeypatch):
    from app.modules.checkers.models import CheckerResult
    case = await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        source = await session.scalar(select(CheckerResult).where(CheckerResult.checker_run_id==case[3]).limit(1))
        values = {column.name:getattr(source,column.name) for column in CheckerResult.__table__.columns}
        values["id"] = str(new_record_id())
        session.add(CheckerResult(**values))
        with pytest.raises(IntegrityError, match="finished or unclaimed checker run cannot receive results"):
            await session.flush()
        await session.rollback()
