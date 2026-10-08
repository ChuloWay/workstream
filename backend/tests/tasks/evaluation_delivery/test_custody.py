"""Real phase boundaries: committed execution cannot outlive revoked delivery custody."""

import asyncio

import pytest
from sqlalchemy import text

from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.outbox.api import DeliveryOptions, FinalizationCause, HandlerOutcome
from tests.post_submit_materialization_helpers import material_fixture
from .support import delivery_fixture, invoked, state, outcome


async def test_expired_invocation_cannot_start_execution(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h, options=DeliveryOptions(lease_seconds=2, handler_timeout_seconds=1))
        envelope = await invoked(h, d)
        before = await state(h)
        async with h.factory() as session:
            await session.execute(text("select pg_sleep(greatest(0, extract(epoch from "
                                       "(:deadline - clock_timestamp()))) + 0.02)"),
                                  {"deadline": envelope.claim.claim_expires_at})
        assert await d.handler(envelope) is HandlerOutcome.REJECT
        assert await state(h) == before and not h.store.opens


async def test_expired_execution_is_not_renewed(tmp_path, isolated_database_env, monkeypatch):
    import app.modules.checkers.execution as execution

    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h)
        envelope = await invoked(h, d)
        with monkeypatch.context() as patch:
            patch.setattr(execution, "LEASE_SECONDS", 1)
            lease, replay = await d.handler._executor(envelope, h.request)._claim(h.request)
        assert replay is None and lease.lease_generation == 1
        before = await state(h)
        async with h.factory() as session:
            await session.execute(text("select pg_sleep(greatest(0, extract(epoch from "
                                       "(:deadline - clock_timestamp()))) + 0.02)"),
                                  {"deadline": lease.expires_at})
        with pytest.raises(CheckerExecutionUnavailable, match="checker_delivery_execution_unavailable"):
            await d.handler(envelope)
        assert await state(h) == before and not h.store.opens and not h.preparation._active
        receipt = await d.delivery.finalize(envelope.claim, FinalizationCause.UNKNOWN)
        assert outcome(receipt)["invocation_unknown"] is True
        assert await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "retry") is None


async def test_delivery_closed_during_io_cannot_publish_terminal(tmp_path, isolated_database_env, monkeypatch):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h)
        envelope = await invoked(h, d)
        entered, release = asyncio.Event(), asyncio.Event()
        original = h.store.open

        async def paused(reference):
            source = original(reference)
            entered.set()
            await release.wait()
            async for chunk in source:
                yield chunk

        monkeypatch.setattr(h.store, "open", paused)
        operation = asyncio.create_task(d.handler(envelope))
        try:
            await asyncio.wait_for(entered.wait(), 20)
            running = await state(h)
            assert running["run"]["status"] == "running"
            assert running["run"]["worker_lease_generation"] == 1
            assert running["run"]["execute_evidence_id"] is not None
            assert running["run"]["finalize_evidence_id"] is None
            # Real dispatcher transaction must complete while I/O is paused.
            receipt = await asyncio.wait_for(
                d.delivery.finalize(envelope.claim, FinalizationCause.UNKNOWN), 10,
            )
            assert outcome(receipt)["invocation_unknown"] is True
            release.set()
            with pytest.raises(CheckerExecutionUnavailable, match="checker_delivery_invocation_unavailable"):
                await asyncio.wait_for(operation, 20)
            assert await state(h) == running
            assert running["members"] == running["events"] == 0
            assert not h.preparation._active and not list((h.scratch / "workspaces").iterdir())
            assert len(h.store.opens) == 1
            assert await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "again") is None
            assert len(h.store.opens) == 1
        finally:
            release.set()
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)


async def test_cancellation_after_execute_preserves_unknown(tmp_path, isolated_database_env, monkeypatch):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h)
        envelope = await invoked(h, d)
        entered = asyncio.Event()
        original = h.store.open

        async def paused(reference):
            source = original(reference)
            entered.set()
            await asyncio.Event().wait()
            async for chunk in source:
                yield chunk

        monkeypatch.setattr(h.store, "open", paused)
        operation = asyncio.create_task(d.handler(envelope))
        try:
            await asyncio.wait_for(entered.wait(), 20)
            running = await state(h)
            operation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await operation
            receipt = await d.delivery.finalize(envelope.claim, FinalizationCause.UNKNOWN)
            assert outcome(receipt)["invocation_unknown"] is True
            assert await state(h) == running
            assert not h.preparation._active and not list((h.scratch / "workspaces").iterdir())
            assert await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "again") is None
            assert len(h.store.opens) == 1
        finally:
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
