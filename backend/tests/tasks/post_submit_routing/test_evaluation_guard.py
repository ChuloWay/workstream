"""Exact owner selection and root-lock lifetime for evaluation reservations."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.adapters.checkers import evaluation_coordinator
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.checkers.models import CheckerRun
from app.modules.tasks.models import WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from tests.checkers.post_submit.support import change_request
from tests.post_submit_materialization_helpers import material_fixture


async def _require_task_lock(h):
    async with h.factory() as holder, holder.begin():
        await evaluation_coordinator(holder).reserve_current_evaluation(h.request)
        async with h.factory() as other, other.begin():
            locked = False
            try:
                # FK KEY SHARE alone must not satisfy this stronger custody proof.
                await other.execute(text(
                    "SELECT id FROM public.workstream_tasks WHERE id=:id FOR NO KEY UPDATE NOWAIT"
                ), {"id": h.request.task_id})
            except DBAPIError as error:
                assert getattr(error.orig, "sqlstate", None) == "55P03"
                locked = True
            assert locked, "task row was not locked before checker reservation"


async def test_reservation_retains_task_lock(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await _require_task_lock(h)


async def test_task_lock_removal_is_detected(tmp_path, isolated_database_env, monkeypatch):
    async def unlocked(self, project_id, task_id):
        task = await self.get_task(str(task_id))
        return task if task is not None and task.project_id == str(project_id) else None

    async with material_fixture(tmp_path, isolated_database_env) as h:
        monkeypatch.setattr(TaskRepository, "lock_project_task", unlocked)
        with pytest.raises(AssertionError, match="task row was not locked"):
            await _require_task_lock(h)


@pytest.mark.parametrize("operation", ["reserve_current_evaluation", "read_current_result"])
async def test_savepoints_cannot_release_reservation_locks(tmp_path, isolated_database_env, operation):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            async with session.begin_nested():
                with pytest.raises(CheckerExecutionUnavailable, match="caller_transaction_required"):
                    await getattr(evaluation_coordinator(session), operation)(h.request)
        async with h.factory() as session:
            await session.begin()
            await session.execute(text("SAVEPOINT caller_scope"))
            with pytest.raises(CheckerExecutionUnavailable, match="caller_transaction_required"):
                await getattr(evaluation_coordinator(session), operation)(h.request)
            await session.rollback()
        async with h.factory() as session, session.begin():
            assert list(await session.scalars(select(CheckerRun.id))) == [str(h.created.evaluation_attempt_id)]
            created = await evaluation_coordinator(session).reserve_current_evaluation(h.request)
            assert created.evaluation_generation == 1


async def test_stale_identity_map_cannot_hide_ineligible_task(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        async with h.factory() as stale:
            loaded = await stale.get(WorkstreamTask, str(h.request.task_id))
            assert loaded.status == "evaluation_pending"
            async with h.factory() as writer, writer.begin():
                await writer.execute(text("UPDATE public.workstream_tasks SET status='draft' WHERE id=:id"),
                                     {"id": h.request.task_id})
            with pytest.raises(CheckerExecutionUnavailable, match="checker_reservation_scope_unavailable"):
                await evaluation_coordinator(stale).reserve_current_evaluation(h.request)
            assert loaded.status == "draft"
            assert list(await stale.scalars(select(CheckerRun.id))) == [str(h.created.evaluation_attempt_id)]
            await stale.rollback()


async def test_valid_foreign_selectors_fail_before_foreign_task_lock(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path / "one", isolated_database_env) as first:
        async with material_fixture(tmp_path / "two", isolated_database_env,
                                    provision_services=False, storage_settings=first.settings) as foreign:
            expected_runs = {str(first.created.evaluation_attempt_id), str(foreign.created.evaluation_attempt_id)}
            mixed_project = change_request(foreign.request, task_id=first.request.task_id,
                                           submission_id=first.request.submission_id)
            async with first.factory() as blocker, blocker.begin():
                await blocker.execute(text("SELECT id FROM public.workstream_tasks WHERE id=:id FOR UPDATE"),
                                      {"id": first.request.task_id})
                async with first.factory() as session, session.begin():
                    await session.execute(text("SET LOCAL lock_timeout='250ms'"))
                    with pytest.raises(CheckerExecutionUnavailable, match="checker_reservation_scope_unavailable"):
                        await evaluation_coordinator(session).reserve_current_evaluation(mixed_project)
                    assert set(await session.scalars(select(CheckerRun.id))) == expected_runs
            for field in ("task_id", "submission_id", "assignment_id", "binding_id", "content_id"):
                changed = change_request(first.request, **{field: getattr(foreign.request, field)})
                async with first.factory() as session, session.begin():
                    with pytest.raises(CheckerExecutionUnavailable, match="checker_reservation_scope_unavailable"):
                        await evaluation_coordinator(session).reserve_current_evaluation(changed)
                    assert set(await session.scalars(select(CheckerRun.id))) == expected_runs
            async with first.factory() as session, session.begin():
                control = await evaluation_coordinator(session).reserve_current_evaluation(first.request)
                assert control.request_id == first.request.evaluation_request_id


async def test_changed_locked_context_cannot_advance_generation(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            first = await evaluation_coordinator(session).reserve_current_evaluation(h.request)
        for field in ("source_id", "effective_policy_id", "pre_policy_id", "review_policy_id", "revision_policy_id"):
            context = h.request.expected_context.model_copy(update={field: new_record_id()})
            changed = change_request(h.request, expected_context=context,
                                     structural_input=h.request.structural_input.model_copy(update={
                                         "observed_context": h.request.structural_input.observed_context.model_copy(
                                             update={field: getattr(context, field)}),
                                     }), evaluation_request_id=new_record_id(), evaluation_generation=2)
            async with h.factory() as session, session.begin():
                with pytest.raises(CheckerExecutionUnavailable, match="checker_reservation_scope_unavailable"):
                    await evaluation_coordinator(session).reserve_current_evaluation(changed)
                assert list(await session.scalars(select(CheckerRun.id))) == [str(first.attempt_id)]


async def test_superseded_submission_cannot_reserve_or_replay(tmp_path, isolated_database_env):
    from tests.checkers.execution.storage_fixture import storage_request
    from .support import completed_source, successor_submission

    async with completed_source(tmp_path, isolated_database_env) as h:
        successor = await successor_submission(h)
        async with h.factory() as session, session.begin():
            before = list(await session.scalars(select(CheckerRun.id)))
            with pytest.raises(CheckerExecutionUnavailable, match="checker_reservation_scope_unavailable"):
                await evaluation_coordinator(session).reserve_current_evaluation(h.request)
            assert list(await session.scalars(select(CheckerRun.id))) == before
            valid = await storage_request(session, successor.submission_id)
            result = await evaluation_coordinator(session).reserve_current_evaluation(valid)
            assert result.request_id == valid.evaluation_request_id
            assert set(await session.scalars(select(CheckerRun.id))) == set(before)
            assert result.attempt_id == successor.evaluation_attempt_id
