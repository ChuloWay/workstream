"""Executor deadlines must not bypass post-I/O material authority and selection."""

import asyncio

import pytest
from sqlalchemy import text

from app.modules.actors.api import ServiceIdentity
from app.modules.checkers.api.materialization import PostSubmissionMaterializationUnavailable
from tests.checkers.execution.support import live_executor, reserve, service_link_state
from tests.post_submit_materialization_helpers import material_fixture
from .test_receipt_custody import snapshot


@pytest.mark.parametrize("change", ["revoked", "replica_unavailable", "unchanged"])
async def test_outer_deadline_revalidates_material_after_cleanup(tmp_path, isolated_database_env, monkeypatch, change):
    import app.modules.checkers.execution as execution
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        entered = asyncio.Event()
        async def paused(consumer, request, material):
            entered.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(execution._StructuralConsumer, "evaluate", paused)
        # Arm the actual asyncio deadline after the consumer enters, avoiding a
        # machine-speed race between setup queries and the short test deadline.
        original_timeout, deadlines = asyncio.timeout, []
        def controlled_timeout(seconds):
            timer = original_timeout(None if seconds == 12345 else seconds)
            if seconds == 12345:
                deadlines.append(timer)
            return timer
        monkeypatch.setattr(execution, "EXECUTION_TIMEOUT_SECONDS", 12345)
        monkeypatch.setattr(asyncio, "timeout", controlled_timeout)
        task = asyncio.create_task(live_executor(h).evaluate_post_submission(h.request))
        try:
            await asyncio.wait_for(entered.wait(), 10)
            before = await snapshot(h)
            if change == "revoked":
                await service_link_state(h.factory, ServiceIdentity.ARTIFACT_MATERIALIZER, active=False)
            elif change == "replica_unavailable":
                async with h.factory() as session, session.begin():
                    await session.execute(text("UPDATE artifact_replicas SET availability_state='unavailable' WHERE id=:id"), {"id": h.replica_id})
            assert len(deadlines) == 1
            deadlines[0].reschedule(asyncio.get_running_loop().time())
            if change == "unchanged":
                result = await asyncio.wait_for(task, 10)
                assert result.outcome == "infrastructure_failed"
                assert result.infrastructure_failure_code == "deadline_exceeded"
                after = await snapshot(h)
                assert after[0][0]["status"] == "infrastructure_failed"
                assert after[0][0]["material_custody"] is None
                assert after[1] == before[1] + 1  # finalization only; no second read allow
                assert after[2:] == before[2:]
            else:
                with pytest.raises(PostSubmissionMaterializationUnavailable):
                    await asyncio.wait_for(task, 10)
                assert await snapshot(h) == before
            assert len(h.store.opens) == 1 and not h.preparation._active
            assert list((h.scratch / "workspaces").iterdir()) == []
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
