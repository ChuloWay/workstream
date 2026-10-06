"""Exact owner-composed routing proposals without publication or authority."""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.adapters.tasks import routing_source_preparer
from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.tasks.post_submit_routing.models import TaskRoutingRequest
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
from tests.checkers.execution.support import reserve
from .support import (
    completed_source, completed_sibling_source, completion_for, next_request,
    joined_source_facts, source_count, activate_successor_guide,
)
from .test_requests import effect_snapshot


@asynccontextmanager
async def routing_source(tmp_path, database_url):
    """Real completed evaluation with future dispatch state explicitly seeded.

    This proves mechanical preparation, not live dispatch or routing authority.
    """
    async with completed_source(tmp_path, database_url) as h:
        async with h.factory() as session, session.begin():
            before = await effect_snapshot(session)
            with pytest.raises(TaskRoutingRequestUnavailable, match="routing_source_unavailable"):
                await prepare(session, h)
            assert await effect_snapshot(session) == before
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 0
            changed = await session.execute(text(
                "UPDATE public.workstream_tasks SET status='evaluation_pending' "
                "WHERE id=:id AND status='in_progress'"
            ), {"id": h.request.task_id})
            assert changed.rowcount == 1
            # The ART fixture arranges an assignment directly, not through claim.
            # Retain the real claim precondition without claiming AUTH proof here.
            with pytest.raises(TaskRoutingRequestUnavailable, match="routing_source_unavailable"):
                await prepare(session, h)
            started = await session.execute(text(
                "UPDATE public.task_assignments SET accepted_at=clock_timestamp() "
                "WHERE id=:id AND accepted_at IS NULL"
            ), {"id": h.request.assignment_id})
            assert started.rowcount == 1
        yield h


async def prepare(session, h, completion=None):
    return await routing_source_preparer(session).prepare(
        h.source["completion_event_id"], completion or completion_for(h),
    )


async def test_exact_proposal_replay_and_rollback(tmp_path, isolated_database_env):
    from datetime import UTC, datetime
    async with routing_source(tmp_path, isolated_database_env) as h:
        expected = await joined_source_facts(h, h.source | {"created_at": datetime.now(UTC)})
        async with h.factory() as session:
            await session.begin()
            before = await effect_snapshot(session)
            result = await prepare(session, h)
            assert result.source.model_dump() == expected.model_dump(exclude={"created_at"}) | {
                "id": result.request.routing_manifest_id,
            }
            assert "created_at" not in result.source.model_dump()
            assert await source_count(session) == 0
            assert await effect_snapshot(session) == before
            await session.rollback()
        async with h.factory() as session, session.begin():
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 0
            committed = await prepare(session, h)
        async with h.factory() as session, session.begin():
            assert await prepare(session, h) == committed
            assert await effect_snapshot(session) == before
            assert await source_count(session) == 0
            assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 1


async def test_historical_policy_survives_new_guide(tmp_path, isolated_database_env):
    async with routing_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            before = await prepare(session, h)
        await activate_successor_guide(h)
        async with h.factory() as session, session.begin():
            assert await prepare(session, h) == before


async def test_mixed_stored_sources_reject_without_effects(tmp_path, isolated_database_env):
    async with routing_source(tmp_path, isolated_database_env) as h:
        sibling = await completed_sibling_source(h)
        original, other = completion_for(h), completion_for(sibling)
        for field in ("task_id", "submission_id", "reference", "execute_evidence_id", "finalize_evidence_id"):
            async with h.factory() as session, session.begin():
                before = await effect_snapshot(session)
                with pytest.raises((TaskRoutingRequestUnavailable, CheckerExecutionUnavailable)):
                    await prepare(session, h, original.model_copy(update={field: getattr(other, field)}))
                assert await effect_snapshot(session) == before
                assert await source_count(session) == 0
                assert await session.scalar(select(func.count()).select_from(TaskRoutingRequest)) == 0


async def test_preparation_retains_parent_custody_and_successor_wins_next(tmp_path, isolated_database_env):
    async with routing_source(tmp_path, isolated_database_env) as h:
        old = completion_for(h)
        async with h.factory() as first, first.begin():
            await prepare(first, h)
            for table, key, value in (
                ("workstream_tasks", "id", h.request.task_id),
                ("projects", "id", h.request.project_id),
                ("task_assignments", "id", h.request.assignment_id),
                ("submissions", "id", h.request.submission_id),
                ("checker_submission_fences", "submission_id", h.request.submission_id),
            ):
                async with h.factory() as other:
                    with pytest.raises(DBAPIError) as failure:
                        await other.execute(text(f"SELECT 1 FROM public.{table} WHERE {key}=:id FOR UPDATE NOWAIT"), {"id": value})
                    assert failure.value.orig.sqlstate == "55P03"
        await next_request(h)
        await reserve(h)
        async with h.factory() as session, session.begin():
            with pytest.raises(CheckerExecutionUnavailable, match="current_request_unavailable"):
                await prepare(session, h, old)
            assert await source_count(session) == 0
