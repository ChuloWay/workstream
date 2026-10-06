"""Review admission retains TASK before CHECKERS, including between owner calls."""

import asyncio
from contextlib import asynccontextmanager, nullcontext

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.adapters.checkers import evaluation_coordinator
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.checkers.models import CheckerSubmissionFence
from app.modules.reviews.models import ReviewAdmissionIdempotencyRecord, ReviewQueueEntry
from app.modules.reviews.repository import ReviewQueueRepository
from app.modules.reviews.schemas import ReviewAdmissionReservationInput, ReviewQueueEntryInput
from app.modules.tasks.post_submit_routing.evaluation_guard import TaskEvaluationGuard
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.checkers.post_submit.support import change_request
from tests.post_submit_materialization_helpers import material_fixture
from .support import completed_source, completion_for


def _inputs(h):
    owners = dict(project_id=str(h.request.project_id), task_id=str(h.request.task_id),
                  submission_id=str(h.request.submission_id), submission_version=h.request.submission_version,
                  admitting_checker_run_id=str(h.result.attempt_id))
    return (
        ReviewQueueEntryInput(id=new_record_id(), **owners, routing_mode="open",
                              routing_reason="first_submission"),
        ReviewAdmissionReservationInput(id=new_record_id(), **owners,
                                        idempotency_key=new_record_id(), operation_id=new_record_id(),
                                        request_digest="sha256:" + "a" * 64),
    )


async def _read(session, h, reader):
    coordinator = evaluation_coordinator(session)
    if reader == "result":
        result = await coordinator.read_current_result(h.request)
        assert result.result == h.result
    else:
        verified = await coordinator.require_current_completion(
            h.source["completion_event_id"], completion_for(h),
        )
        assert verified.submission_version == h.request.submission_version
        assert verified.completion == completion_for(h)
        assert verified.material.model_dump(mode="json") == h.material


async def _admit(session, queue, admission):
    repository = ReviewQueueRepository(session)
    await repository.reserve_admission(admission)
    await repository.add_queue_entry(queue)
    await repository.commit_admission(reservation_id=admission.id, queue_entry_id=queue.id)


async def _race(h, database_url, reader, successor_first):
    queue, admission = _inputs(h)
    successor = change_request(h.request, evaluation_request_id=new_record_id(), evaluation_generation=2)
    name = "review-intermediate-" + new_record_id().hex

    async def compete():
        async with h.factory() as session, session.begin():
            await session.execute(text("select set_config('application_name',:name,true)"), {"name": name})
            if successor_first:
                await _read(session, h, reader)
                await _admit(session, queue, admission)
            else:
                return await evaluation_coordinator(session).reserve_current_evaluation(successor)

    pending = None
    errors = []
    try:
        try:
            async with h.factory() as winner, winner.begin():
                blocker = await winner.scalar(text("select pg_backend_pid()"))
                if successor_first:
                    reserved = await evaluation_coordinator(winner).reserve_current_evaluation(successor)
                else:
                    await _read(winner, h, reader)
                pending = asyncio.create_task(compete())
                await asyncio.wait_for(wait_for_named_database_lock(
                    database_url, name, expected_blocker_pid=blocker,
                ), 10)
                assert not pending.done()
                if not successor_first:
                    # Crucially, insert only AFTER the successor has reached its wait.
                    await _admit(winner, queue, admission)
        except DBAPIError as error:
            errors.append(error)
        if successor_first:
            with pytest.raises(CheckerExecutionUnavailable, match="checker_current_request_unavailable"):
                await asyncio.wait_for(pending, 10)
        else:
            try:
                reserved = await asyncio.wait_for(pending, 10)
            except DBAPIError as error:
                errors.append(error)
        if errors:
            assert all(getattr(error.orig, "sqlstate", None) == "40P01" for error in errors)
            raise AssertionError("admission and successor deadlocked at the intermediate wait")
    finally:
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
    async with h.factory() as session:
        fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
        assert fence.current_run_id == str(reserved.attempt_id)
        stored_queue = await session.get(ReviewQueueEntry, queue.id)
        stored_admission = await session.get(ReviewAdmissionIdempotencyRecord, admission.id)
        if successor_first:
            assert stored_queue is None and stored_admission is None
        else:
            assert stored_queue.admitting_checker_run_id == str(h.result.attempt_id)
            assert stored_queue.submission_id == str(h.request.submission_id)
            assert stored_admission.status == "committed"
            assert stored_admission.review_queue_entry_id == queue.id


@pytest.mark.parametrize("reader", ["result", "completion"])
@pytest.mark.parametrize("successor_first", [False, True])
async def test_read_then_admission_serializes_at_intermediate_wait(
    tmp_path, isolated_database_env, reader, successor_first,
):
    async with completed_source(tmp_path, isolated_database_env) as h:
        await _race(h, isolated_database_env, reader, successor_first)


async def test_read_guard_removal_reproduces_deadlock(tmp_path, isolated_database_env, monkeypatch):
    async with completed_source(tmp_path, isolated_database_env) as h:
        original = TaskEvaluationGuard.lock_evaluation_scope

        async def omit_read_lock(self, request):
            if request.evaluation_generation == 1:
                return True
            return await original(self, request)

        monkeypatch.setattr(TaskEvaluationGuard, "lock_evaluation_scope", omit_read_lock)
        with pytest.raises(AssertionError, match="deadlocked at the intermediate wait"):
            await _race(h, isolated_database_env, "result", False)


async def _require_task_lock(h):
    async with h.factory() as probe, probe.begin():
        try:
            await probe.execute(text(
                "SELECT id FROM public.workstream_tasks WHERE id=:id FOR NO KEY UPDATE NOWAIT"
            ), {"id": h.request.task_id})
        except DBAPIError as error:
            assert getattr(error.orig, "sqlstate", None) == "55P03"
        else:
            raise AssertionError("review INSERT did not retain TASK before CHECKERS/FK custody")


async def _insert(session, value, table):
    values = value.model_dump()
    if table == "review_queue_entries":
        values.update(queue_state="pending", routing_generation=1, lifecycle_generation=1)
    else:
        values.update(status="pending")
    columns = tuple(values)
    await session.execute(text(
        "INSERT INTO public." + table + " (" + ",".join(columns) + ") VALUES ("
        + ",".join(":" + key for key in columns) + ")"
    ), values)


@pytest.mark.parametrize("remove_lock", [False, True])
@pytest.mark.parametrize("boundary", ["queue", "admission"])
async def test_direct_insert_takes_task_before_checker_or_foreign_keys(
    tmp_path, isolated_database_env, boundary, remove_lock,
):
    async with completed_source(tmp_path, isolated_database_env) as h, _trigger_scope(h, boundary, remove_lock):
        queue, admission = _inputs(h)
        proof = pytest.raises(AssertionError, match="review INSERT did not retain TASK") if remove_lock else nullcontext()
        if boundary == "admission":
            async with h.factory() as session, session.begin():
                await _insert(session, admission, "review_admission_idempotency_records")
                with proof:
                    await _require_task_lock(h)
            return
        name = "direct-queue-fence-" + new_record_id().hex

        async def insert():
            async with h.factory() as session, session.begin():
                await session.execute(text("select set_config('application_name',:name,true)"), {"name": name})
                await _insert(session, queue, "review_queue_entries")

        pending = None
        try:
            async with h.factory() as blocker, blocker.begin():
                pid = await blocker.scalar(text("select pg_backend_pid()"))
                await blocker.execute(text(
                    "SELECT submission_id FROM public.checker_submission_fences WHERE submission_id=:id FOR UPDATE"
                ), {"id": h.request.submission_id})
                pending = asyncio.create_task(insert())
                await asyncio.wait_for(wait_for_named_database_lock(
                    isolated_database_env, name, expected_blocker_pid=pid,
                ), 10)
                with proof:
                    await _require_task_lock(h)
            await asyncio.wait_for(pending, 10)
        finally:
            if pending is not None:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        async with h.factory() as session:
            assert await session.scalar(select(ReviewQueueEntry.id).where(ReviewQueueEntry.id == queue.id)) == queue.id


@asynccontextmanager
async def _trigger_scope(h, boundary, remove_lock):
    name = "guard_review_queue_entry" if boundary == "queue" else "guard_review_admission_record"
    async with h.factory() as session:
        definition = await session.scalar(text(
            "SELECT pg_catalog.pg_get_functiondef(pg_catalog.to_regprocedure(:name))"
        ), {"name": "public." + name + "()"})
        # Inspect the resulting migration, including the UPDATE branch that must
        # never acquire TASK after PostgreSQL has already locked an admission row.
        insert_branch = "and task.project_id=new.project_id for update;"
        assert definition.count(insert_branch) == 1
        settings = await session.scalar(text(
            "SELECT proconfig FROM pg_catalog.pg_proc WHERE oid=pg_catalog.to_regprocedure(:name)"
        ), {"name": "public." + name + "()"})
        assert settings == ["search_path=pg_catalog, public, pg_temp"]
        assert "from public.checker_submission_fences" in definition
        unlocked_update = "where task.id=new.task_id and task.project_id=new.project_id;"
        assert unlocked_update in definition
        if remove_lock:
            await session.execute(text(definition.replace(insert_branch, "and task.project_id=new.project_id;")))
            await session.commit()
    try:
        yield
    finally:
        if remove_lock:
            async with h.factory() as session, session.begin():
                await session.execute(text(definition))


async def test_direct_insert_wrong_project_does_not_wait_on_foreign_task(tmp_path, isolated_database_env):
    async with completed_source(tmp_path / "owned", isolated_database_env) as h:
        async with material_fixture(tmp_path / "foreign", isolated_database_env,
                                    provision_services=False, storage_settings=h.settings) as foreign:
            queue, admission = _inputs(h)
            async with h.factory() as blocker, blocker.begin():
                await blocker.execute(text("SELECT id FROM public.workstream_tasks WHERE id=:id FOR UPDATE"),
                                      {"id": h.request.task_id})
                for boundary, value, table in (
                    ("queue", queue, "review_queue_entries"),
                    ("admission", admission, "review_admission_idempotency_records"),
                ):
                    async with h.factory() as session:
                        await session.execute(text("SET LOCAL lock_timeout='250ms'"))
                        with pytest.raises(DBAPIError, match=f"review {boundary} task project mismatch") as caught:
                            await _insert(session, value.model_copy(update={"project_id": str(foreign.request.project_id)}), table)
                        assert getattr(caught.value.orig, "sqlstate", None) == "23514"
                        await session.rollback()
            async with h.factory() as session:
                assert list(await session.scalars(select(ReviewQueueEntry.id))) == []
                assert list(await session.scalars(select(ReviewAdmissionIdempotencyRecord.id))) == []
