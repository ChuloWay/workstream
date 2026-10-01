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
        deadlines = controlled_deadline(monkeypatch, execution)
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


def controlled_deadline(monkeypatch, execution):
    """Use the real timeout, armed only after the boundary under test is reached."""
    original_timeout, deadlines = asyncio.timeout, []
    def timeout(seconds):
        timer = original_timeout(None if seconds == 12345 else seconds)
        if seconds == 12345:
            deadlines.append(timer)
        return timer
    monkeypatch.setattr(execution, "EXECUTION_TIMEOUT_SECONDS", 12345)
    monkeypatch.setattr(asyncio, "timeout", timeout)
    return deadlines


@pytest.mark.parametrize("failure", ["release", "workspace"])
async def test_outer_deadline_cannot_hide_failed_scratch_cleanup(tmp_path, isolated_database_env, monkeypatch, failure):
    import app.modules.checkers.execution as execution
    from app.modules.artifacts.preparation import ArtifactScratchIntegrityError

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        entered, finish = asyncio.Event(), asyncio.Event()
        original_release = h.manager.release
        original_workspace = h.manager._cleanup_workspace_sync
        async def failed_release(reservation):
            entered.set()
            await finish.wait()
            raise ArtifactScratchIntegrityError("controlled release failure")
        async def paused_consumer(consumer, request, material):
            entered.set()
            await asyncio.Event().wait()
        def failed_workspace(name):
            raise ArtifactScratchIntegrityError("controlled workspace failure")
        if failure == "release":
            monkeypatch.setattr(h.manager, "release", failed_release)
        else:
            monkeypatch.setattr(execution._StructuralConsumer, "evaluate", paused_consumer)
            monkeypatch.setattr(h.manager, "_cleanup_workspace_sync", failed_workspace)
        deadlines = controlled_deadline(monkeypatch, execution)
        task = asyncio.create_task(live_executor(h).evaluate_post_submission(h.request))
        try:
            await asyncio.wait_for(entered.wait(), 10)
            before = await snapshot(h)
            deadlines[0].reschedule(asyncio.get_running_loop().time())
            for _ in range(10):
                await asyncio.sleep(0)
                if task.cancelling():
                    break
            assert task.cancelling(), "executor deadline did not cancel the protected operation"
            finish.set()
            with pytest.raises(ArtifactScratchIntegrityError, match=f"controlled {failure} failure"):
                await asyncio.wait_for(task, 10)
            assert await snapshot(h) == before  # running, no final receipt/result/event
            assert len(h.store.opens) == 1
            if failure == "release":
                assert len(h.preparation._active) == 1
                assert (await h.manager.usage()).reservation_count == 1
            else:
                assert not h.preparation._active and h.manager._pending_workspaces
        finally:
            finish.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            monkeypatch.setattr(h.manager, "release", original_release)
            monkeypatch.setattr(h.manager, "_cleanup_workspace_sync", original_workspace)
            for binding in list(h.preparation._active):
                await h.preparation.release_prepared_artifact(binding)
            await h.preparation.retry_pending_cleanup()
        assert not h.preparation._active and not h.manager._pending_workspaces
        assert (await h.manager.usage()).reservation_count == 0
        assert list((h.scratch / "workspaces").iterdir()) == []
