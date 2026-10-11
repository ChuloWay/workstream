"""Foreign and superseding sources cannot borrow remediation custody."""

import asyncio

import pytest
from sqlalchemy import text

from app.adapters.checkers import evaluation_coordinator
from app.adapters.tasks import routing_source_preparer
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
from tests.auth_concurrency_support import wait_for_named_database_lock
from .outcome_support import apply_outcome, outcome_snapshot
from .remediation_support import remediation_source
from .support import next_request


async def test_remediation_rejects_crossed_source(tmp_path, isolated_database_env):
    async with remediation_source(tmp_path, isolated_database_env) as own:
        async with remediation_source(
            tmp_path / "foreign", isolated_database_env, provision_services=False, storage_settings=own.settings,
        ) as foreign:
            assert own.request.project_id != foreign.request.project_id
            # Both complete stored lineages independently resolve before mixing.
            for h in (own, foreign):
                async with h.factory() as session:
                    await session.begin()
                    control = await routing_source_preparer(session).prepare(
                        h.source["completion_event_id"], h.completion,
                    )
                    assert control.source.routing_recommendation == "needs_revision"
                    await session.rollback()
            async with own.factory() as session:
                before = await outcome_snapshot(session)
            for field in ("project_id", "task_id", "submission_id", "reference"):
                completion = own.completion.model_copy(update={field: getattr(foreign.completion, field)})
                async with own.factory() as session:
                    with pytest.raises((TaskRoutingRequestUnavailable, CheckerExecutionUnavailable)):
                        async with session.begin():
                            await routing_source_preparer(session).prepare(
                                own.source["completion_event_id"], completion,
                            )
                async with own.factory() as session:
                    assert await outcome_snapshot(session) == before


async def test_remediation_holds_currentness_against_successor(tmp_path, isolated_database_env):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        successor = await next_request(h)
        name = "remediation-successor-" + new_record_id().hex
        pending = None

        async def reserve():
            async with h.factory() as session, session.begin():
                await session.execute(text("SELECT set_config('application_name',:name,true)"), {"name": name})
                return await evaluation_coordinator(session).reserve_current_evaluation(successor)

        try:
            async with h.factory() as session, session.begin():
                blocker = await session.scalar(text("SELECT pg_backend_pid()"))
                routed = await apply_outcome(session, h, None)
                pending = asyncio.create_task(reserve())
                await asyncio.wait_for(wait_for_named_database_lock(
                    isolated_database_env, name, expected_blocker_pid=blocker,
                ), 10)
                assert not pending.done()
            reserved = await asyncio.wait_for(pending, 10)
            assert reserved.request_id == successor.evaluation_request_id
            async with h.factory() as session:
                before = await outcome_snapshot(session)
            async with h.factory() as session:
                with pytest.raises(CheckerExecutionUnavailable):
                    async with session.begin():
                        await apply_outcome(session, h, None)
            async with h.factory() as session:
                assert await outcome_snapshot(session) == before
                assert await session.scalar(text(
                    "SELECT id FROM public.task_post_submit_routing_manifests"
                )) == routed.routing_manifest_id
        finally:
            if pending is not None:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
