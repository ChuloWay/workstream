"""Direct PostgreSQL guard proofs, independent of TASK's request writer."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text, func
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.adapters.checkers import evaluation_coordinator
from app.modules.tasks.post_submit_routing.models import TaskRoutingRequest
from .support import (
    completed_source, completed_sibling_source, request_values, rehash_request,
    insert_request, next_request, other_hash,
)



async def reject(h, values, message):
    async with h.factory() as session:
        with pytest.raises(DBAPIError, match=message):
            async with session.begin():
                await insert_request(session, values)


async def test_request_storage_rejects_substituted_owner(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        sibling = await completed_sibling_source(h)
        original, foreign = request_values(h), request_values(sibling)
        for key, message in (
            ("task_id", "submission mismatch"),
            ("submission_id", "submission mismatch"),
            ("checker_run_id", "currentness mismatch"),
            ("evaluation_request_id", "checker mismatch"),
            ("evaluation_request_digest", "checker mismatch"),
            ("result_id", "checker mismatch"),
            ("result_digest", "checker mismatch"),
            ("completion_event_id", "checker mismatch"),
        ):
            assert original[key] != foreign[key], key
            await reject(h, rehash_request(original | {key: foreign[key]}), message)
        for key in ("submission_version", "evaluation_generation"):
            await reject(h, rehash_request(original | {key: original[key] + 1}),
                         "submission mismatch" if key == "submission_version" else "checker mismatch")
        async with h.factory() as session, session.begin():
            await insert_request(session, original)


async def test_request_storage_rejects_wrong_digest(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        values = request_values(h)
        await reject(h, values | {"route_request_digest": other_hash(values["route_request_digest"])}, "digest mismatch")
        async with h.factory() as session, session.begin():
            await insert_request(session, values)


@pytest.mark.parametrize("supplied", [None, datetime(2000, 1, 1, tzinfo=UTC), datetime(2099, 1, 1, tzinfo=UTC)])
async def test_database_owns_request_timestamp(tmp_path, isolated_database_env, supplied):
    async with completed_source(tmp_path, isolated_database_env) as h:
        values = request_values(h) | {"created_at": supplied}
        async with h.factory() as session, session.begin():
            before = await session.scalar(select(func.clock_timestamp()))
            await insert_request(session, values)
            after = await session.scalar(select(func.clock_timestamp()))
            stored = await session.get(TaskRoutingRequest, values["route_operation_id"])
            assert before <= stored.created_at <= after
            assert stored.created_at != supplied


async def test_request_is_immutable(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        values = request_values(h)
        async with h.factory() as session, session.begin():
            await insert_request(session, values)
        for statement in (
            "UPDATE public.task_post_submit_routing_requests SET result_digest=result_digest",
            "DELETE FROM public.task_post_submit_routing_requests",
            "TRUNCATE public.task_post_submit_routing_requests",
        ):
            async with h.factory() as session:
                with pytest.raises(DBAPIError, match="task routing request is immutable"):
                    async with session.begin():
                        await session.execute(text(statement))
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 1


async def test_sql_insert_blocks_fence_advancement(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        values = request_values(h)
        successor = await next_request(h)
        async with h.factory() as first:
            await first.begin()
            await insert_request(first, values)
            async with h.factory() as second:
                await second.begin()
                await second.execute(text("SET LOCAL lock_timeout = '250ms'"))
                with pytest.raises(DBAPIError, match="lock timeout"):
                    await evaluation_coordinator(second).reserve_current_evaluation(successor)
                await second.rollback()
            await first.commit()
        async with h.factory() as second, second.begin():
            result = await evaluation_coordinator(second).reserve_current_evaluation(successor)
            assert result.evaluation_generation == 2


async def test_sql_advance_first_rejects_old_completion(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        values = request_values(h)
        successor = await next_request(h)
        async with h.factory() as first:
            await first.begin()
            await evaluation_coordinator(first).reserve_current_evaluation(successor)
            started = asyncio.Event()
            async def old_insert():
                async with h.factory() as second, second.begin():
                    await second.execute(text("SET LOCAL lock_timeout = '5s'"))
                    started.set()
                    await insert_request(second, values)
            pending = asyncio.create_task(old_insert())
            await started.wait()
            try:
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(pending), .2)
                await first.commit()
                with pytest.raises(DBAPIError, match="currentness mismatch"):
                    await pending
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 0


@pytest.mark.parametrize("generated_id", ["route_operation_id", "routing_manifest_id"])
async def test_request_ids_are_distinct_uuid7(tmp_path, isolated_database_env, generated_id):
    async with completed_source(tmp_path, isolated_database_env) as h:
        values = request_values(h)
        for target in ("route_operation_id", "routing_manifest_id"):
            for source in ("evaluation_request_id", "result_id", "completion_event_id"):
                await reject(h, values | {target: values[source]}, "distinct_request_ids")
        await reject(h, values | {"routing_manifest_id": values["route_operation_id"]}, "distinct_request_ids")
        from uuid import UUID
        await reject(h, values | {generated_id: UUID("00000000-0000-4000-8000-000000000001")}, f"{generated_id}_uuid7")
        async with h.factory() as session, session.begin():
            await insert_request(session, values)
        await reject(h, values | {"routing_manifest_id": new_record_id()}, "pk_task_post_submit_routing_requests")


@pytest.mark.parametrize("field", ["payload", "aggregate_id", "correlation_id", "idempotency_key"])
async def test_sql_rejects_crossed_completion_event(tmp_path, isolated_database_env, field):
    """Prove the request guard independently, using a transaction-local faulty event."""
    import json
    async with completed_source(tmp_path, isolated_database_env) as h:
        values = request_values(h)
        async with h.factory() as session:
            with pytest.raises(DBAPIError, match="task routing request event mismatch"):
                async with session.begin():
                    await session.execute(text("ALTER TABLE public.outbox_events DISABLE TRIGGER USER"))
                    if field == "payload":
                        payload = await session.scalar(text("SELECT payload FROM public.outbox_events WHERE event_id=:event"), {"event": values["completion_event_id"]})
                        payload = payload | {"task_id": str(new_record_id())}
                        statement = "UPDATE public.outbox_events SET payload=CAST(:value AS jsonb) WHERE event_id=:event"
                        value = json.dumps(payload)
                    else:
                        statement = f"UPDATE public.outbox_events SET {field}=:value WHERE event_id=:event"
                        value = new_record_id() if field == "aggregate_id" else "different-custody"
                    await session.execute(text(statement), {"value": value, "event": values["completion_event_id"]})
                    await session.execute(text("ALTER TABLE public.outbox_events ENABLE TRIGGER USER"))
                    await insert_request(session, values)
        # The failed transaction restores the real event and its immutable guards.
        async with h.factory() as session, session.begin():
            await insert_request(session, values)
