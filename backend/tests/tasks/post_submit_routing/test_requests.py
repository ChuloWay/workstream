"""Real owner preparation, rollback and concurrent routing-request replay."""

import asyncio

import pytest
from sqlalchemy import func, select, text

from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.adapters.checkers import evaluation_coordinator
from app.modules.tasks.post_submit_routing.models import TaskRoutingRequest
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequests, TaskRoutingRequestUnavailable
from tests.checkers.execution.support import reserve
from .support import completed_source, completed_sibling_source, completion_for, next_request, source_count, successor_submission



async def stage(session, h, completion=None):
    return await TaskRoutingRequests(session, evaluation_coordinator(session)).stage(
        h.source["completion_event_id"], completion or completion_for(h)
    )


async def effect_snapshot(session):
    return (await session.execute(text("""
        SELECT (SELECT count(*) FROM public.audit_events),
               (SELECT count(*) FROM public.outbox_events),
               (SELECT count(*) FROM public.review_queue_entries),
               (SELECT count(*) FROM public.final_acceptances),
               (SELECT count(*) FROM public.contribution_records),
               (SELECT count(*) FROM public.compensation_awards),
               (SELECT jsonb_agg(to_jsonb(t) ORDER BY t.id) FROM public.workstream_tasks t),
               (SELECT jsonb_agg(to_jsonb(s) ORDER BY s.id) FROM public.submissions s)
    """))).one()


async def test_reserve_replay_and_rollback(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            await session.begin()
            before = await effect_snapshot(session)
            facts = await stage(session, h)
            assert facts.route_operation_id != h.request.evaluation_request_id
            assert facts.routing_manifest_id != facts.route_operation_id
            assert facts.evaluation_request_id == h.request.evaluation_request_id
            assert facts.result_id == h.result.result_id
            assert facts.result_digest == h.result.result_digest
            assert await source_count(session) == 0
            assert await effect_snapshot(session) == before
            await session.rollback()
        async with h.factory() as session, session.begin():
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 0
            committed = await stage(session, h)
        async with h.factory() as session, session.begin():
            replay = await stage(session, h)
            assert replay == committed
            assert await effect_snapshot(session) == before
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 1
            assert await source_count(session) == 0


async def test_concurrent_reservations_recover_winner(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        async def caller():
            async with h.factory() as session, session.begin():
                return await stage(session, h)
        results = await asyncio.wait_for(asyncio.gather(caller(), caller()), 20)
        assert results[0] == results[1]
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 1


async def test_stale_completion_cannot_reserve(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        old = completion_for(h)
        await next_request(h)
        await reserve(h)
        async with h.factory() as session, session.begin():
            with pytest.raises(CheckerExecutionUnavailable, match="current_request_unavailable"):
                await stage(session, h, old)
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 0


@pytest.mark.parametrize("recommendation", ["needs_revision", "task_setup_blocked"])
async def test_non_allow_completion_cannot_reserve(tmp_path, isolated_database_env, recommendation):
    async with completed_source(tmp_path, isolated_database_env) as h:
        incoming = completion_for(h).model_copy(update={"routing_recommendation": recommendation})
        async with h.factory() as session, session.begin():
            with pytest.raises(TaskRoutingRequestUnavailable, match="routing_request_unavailable"):
                await stage(session, h, incoming)
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 0


async def test_mixed_valid_lineage_is_denied(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        sibling = await completed_sibling_source(h)
        completion = completion_for(h)
        other = completion_for(sibling)
        for fields in ({"task_id": other.task_id}, {"submission_id": other.submission_id},
                       {"reference": other.reference}, {"execute_evidence_id": other.execute_evidence_id},
                       {"finalize_evidence_id": other.finalize_evidence_id}):
            async with h.factory() as session, session.begin():
                with pytest.raises((TaskRoutingRequestUnavailable, CheckerExecutionUnavailable)):
                    await stage(session, h, completion.model_copy(update=fields))
                assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 0


async def test_reservation_blocks_successor_parent_lock(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as first, first.begin():
            await stage(first, h)
            from sqlalchemy.exc import DBAPIError
            for table, row_id in (("workstream_tasks", h.request.task_id), ("submissions", h.request.submission_id)):
                async with h.factory() as other, other.begin():
                    with pytest.raises(DBAPIError, match="could not obtain lock"):
                        await other.execute(text(f"SELECT id FROM public.{table} WHERE id=:id FOR UPDATE NOWAIT"), {"id": row_id})


async def test_replay_requires_latest_submitted_submission(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            original = await stage(session, h)
        async with h.factory() as session:
            await session.begin()
            await session.execute(text("UPDATE public.submissions SET status='needs_revision' WHERE id=:id"), {"id": h.request.submission_id})
            with pytest.raises(TaskRoutingRequestUnavailable, match="routing_request_unavailable"):
                await stage(session, h)
            await session.rollback()
        async with h.factory() as session, session.begin():
            assert await stage(session, h) == original


async def test_reservation_holds_currentness_lock(tmp_path, isolated_database_env):
    from sqlalchemy.exc import DBAPIError
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            await stage(session, h)
            for table, key, value in (
                ("checker_submission_fences", "submission_id", h.request.submission_id),
                ("checker_runs", "id", h.result.attempt_id),
            ):
                async with h.factory() as other:
                    with pytest.raises(DBAPIError, match="could not obtain lock"):
                        await other.execute(text(f"SELECT 1 FROM public.{table} WHERE {key}=:id FOR UPDATE NOWAIT"), {"id": value})


@pytest.mark.parametrize("entry", ["request", "source"])
async def test_cross_project_cannot_lock_foreign_task(tmp_path, isolated_database_env, entry):
    async with completed_source(tmp_path / "one", isolated_database_env) as first:
        async with completed_source(tmp_path / "two", isolated_database_env, provision_services=False, storage_settings=first.settings) as second:
            assert first.request.project_id != second.request.project_id
            mixed = completion_for(first).model_copy(update={"project_id": second.request.project_id})
            async with first.factory() as owner, owner.begin():
                await owner.execute(text("SELECT id FROM public.workstream_tasks WHERE id=:id FOR UPDATE"), {"id": first.request.task_id})
                async with first.factory() as intruder, intruder.begin():
                    await intruder.execute(text("SET LOCAL lock_timeout = '250ms'"))
                    # A SQL timeout is deliberately not accepted as concealed denial.
                    message = "routing_request_unavailable" if entry == "request" else "routing_source_unavailable"
                    with pytest.raises(TaskRoutingRequestUnavailable, match=message):
                        if entry == "request":
                            await stage(intruder, first, mixed)
                        else:
                            from app.adapters.tasks import routing_source_preparer
                            await routing_source_preparer(intruder).prepare(first.source["completion_event_id"], mixed)


async def test_replay_rejects_older_still_submitted_version(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            original = await stage(session, h)
        successor = await successor_submission(h)
        assert successor.submission_version == 2
        async with h.factory() as session, session.begin():
            assert await session.scalar(text("SELECT status FROM public.submissions WHERE id=:id"), {"id": h.request.submission_id}) == "submitted"
            with pytest.raises(TaskRoutingRequestUnavailable, match="routing_request_unavailable"):
                await stage(session, h)
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 1
            assert (await session.get(TaskRoutingRequest, original.route_operation_id)).routing_manifest_id == original.routing_manifest_id


def untrusted_completion():
    """Valid value shape only; empty database ensures root denial precedes owner reads."""
    from app.core.identifiers import new_record_id
    from app.modules.checkers.api.execution import EvaluationCompletion
    from app.modules.checkers.api.post_submit import PostSubmitCurrentResultReference
    return new_record_id(), EvaluationCompletion(
        project_id=new_record_id(), task_id=new_record_id(), submission_id=new_record_id(),
        reference=PostSubmitCurrentResultReference(
            request_id=new_record_id(), request_digest="sha256:" + "a" * 64,
            attempt_id=new_record_id(), evaluation_generation=1,
            result_id=new_record_id(), result_digest="sha256:" + "b" * 64,
        ), routing_recommendation="allow_review", output_binding_ids=(),
        execute_evidence_id=new_record_id(), finalize_evidence_id=new_record_id(),
    )


@pytest.mark.parametrize("entry", ["request", "source"])
@pytest.mark.parametrize("kind", [
    "missing", "session_nested", "raw_session", "raw_connection", "raw_driver",
    "external_connection_nested", "external_create_savepoint",
])
async def test_request_requires_database_root_transaction(isolated_database_env, kind, entry):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    engine = create_async_engine(isolated_database_env)
    event, completion = untrusted_completion()
    async def rejected(session):
        with pytest.raises(TaskRoutingRequestUnavailable, match="routing_request_caller_transaction_required"):
            if entry == "request":
                await TaskRoutingRequests(session, evaluation_coordinator(session)).stage(event, completion)
            else:
                from app.adapters.tasks import routing_source_preparer
                await routing_source_preparer(session).prepare(event, completion)
    try:
        if kind.startswith("external_"):
            async with engine.connect() as connection:
                root = await connection.begin()
                if kind == "external_connection_nested":
                    await connection.begin_nested()
                mode = "create_savepoint" if kind == "external_create_savepoint" else "rollback_only"
                async with AsyncSession(bind=connection, join_transaction_mode=mode) as session:
                    await session.begin()
                    assert not session.in_nested_transaction()
                    await rejected(session)
                await root.rollback()
        else:
            async with AsyncSession(engine) as session:
                if kind != "missing":
                    await session.begin()
                if kind == "session_nested":
                    await session.begin_nested()
                elif kind.startswith("raw_"):
                    await session.execute(text("SELECT 1"))
                    if kind == "raw_session":
                        await session.execute(text("SAVEPOINT hidden_request_scope"))
                    elif kind == "raw_connection":
                        await (await session.connection()).execute(text("SAVEPOINT hidden_request_scope"))
                    else:
                        raw = await (await session.connection()).get_raw_connection()
                        await raw.driver_connection.execute("SAVEPOINT hidden_request_scope")
                    assert not session.in_nested_transaction()
                    assert not (await session.connection()).in_nested_transaction()
                await rejected(session)
                await session.rollback()
    finally:
        await engine.dispose()


async def test_external_root_and_prior_queries_preserve_reservation_locks(tmp_path, isolated_database_env):
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.exc import DBAPIError
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.engine.connect() as connection:
            root = await connection.begin()
            await connection.execute(text("SELECT 1"))
            async with AsyncSession(bind=connection, join_transaction_mode="rollback_only") as session:
                await session.begin()
                facts = await stage(session, h)
                await session.execute(text("SAVEPOINT after_request"))
                await session.execute(text("ROLLBACK TO SAVEPOINT after_request"))
                await session.execute(text("RELEASE SAVEPOINT after_request"))
                for table, key, value in (
                    ("workstream_tasks", "id", h.request.task_id),
                    ("submissions", "id", h.request.submission_id),
                    ("checker_submission_fences", "submission_id", h.request.submission_id),
                    ("checker_runs", "id", h.result.attempt_id),
                ):
                    async with h.factory() as other:
                        with pytest.raises(DBAPIError, match="could not obtain lock"):
                            await other.execute(text(f"SELECT 1 FROM public.{table} WHERE {key}=:id FOR UPDATE NOWAIT"), {"id": value})
                assert await session.get(TaskRoutingRequest, facts.route_operation_id) is not None
                assert root.is_active
                await root.rollback()
        async with h.factory() as session:
            assert await session.get(TaskRoutingRequest, facts.route_operation_id) is None
