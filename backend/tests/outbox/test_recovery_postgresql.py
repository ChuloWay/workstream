"""Crash boundaries, retry exhaustion and exact retained outcome replay."""

import asyncio
import json

import pytest
from sqlalchemy import select, text

from app.core.hashing import canonical_json_hash
from app.modules.outbox.api import DeliveryUnavailable, FinalizationCause, HandlerOutcome
from app.modules.outbox.delivery_repository import DeliveryRepository
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent


async def expire(h):
    async with h.factory() as session:
        await session.execute(text("select pg_sleep(3.05)"))


async def test_crash_before_invoke_recovers(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    assert await h.delivery.recover(claim.event_id, h.project) is None
    await expire(h)
    result = await h.delivery.recover(claim.event_id, h.project)
    body = json.loads(result.outcome_json)
    assert body["delivery_state"] == "retryable"
    assert body["error_code"] == "LEASE_EXPIRED_BEFORE_INVOKE"
    assert body["invoked_at"] is None and body["invocation_unknown"] is False
    assert h.handled == []


async def test_crash_after_invoke_commit_before_handler_entry_is_unknown(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    assert await h.delivery._begin_invocation(claim)
    assert h.handled == []
    await expire(h)
    assert await h.delivery.observe_invocation(claim) is None
    receipt = await h.delivery.recover(claim.event_id, h.project)
    body = json.loads(receipt.outcome_json)
    assert (body["delivery_state"], body["error_code"], body["invocation_unknown"]) == (
        "dead_letter",
        "INVOKE_OUTCOME_UNKNOWN",
        True,
    )
    assert await h.delivery.claim(claim.event_id, h.project, "other") is None
    assert await h.delivery.invoke(claim) is None
    assert (await h.delivery.drain(h.project)).unresolved == 1
    assert h.handled == []


async def test_crash_after_handler_before_finalize_is_unknown(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    envelope = await h.delivery._begin_invocation(claim)
    assert await h.handle(envelope) is HandlerOutcome.ACKNOWLEDGE
    await expire(h)
    receipt = await h.delivery.recover(claim.event_id, h.project)
    assert json.loads(receipt.outcome_json)["invocation_unknown"] is True
    assert len(h.handled) == 1


async def test_finalize_commit_and_exact_replay(delivery_harness, monkeypatch):
    h = delivery_harness
    claim = await h.claim()
    await h.delivery._begin_invocation(claim)
    from sqlalchemy.ext.asyncio import AsyncSession

    original = AsyncSession.flush

    async def fail_after_flush(session, *args, **kwargs):
        await original(session, *args, **kwargs)
        raise RuntimeError("simulated_loss_before_commit")

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "flush", fail_after_flush)
        with pytest.raises(RuntimeError, match="simulated_loss_before_commit"):
            await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    async with h.factory() as session:
        assert (await DeliveryRepository(session).attempt(claim)).stage == "invoked"
        assert (await session.get(OutboxEvent, claim.event_id)).delivery_state == "claimed"
    receipt = await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    assert await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE) == receipt
    body = json.loads(receipt.outcome_json)
    assert canonical_json_hash(body) == receipt.outcome_digest
    assert body["receipt_completed_at"] == body["finalized_at"]
    with pytest.raises(DeliveryUnavailable):
        await h.delivery.finalize(claim, FinalizationCause.RETRY)
    for key, replacement in {
        "delivery_state": "dead_letter",
        "error_code": "HANDLER_REJECTED",
        "next_attempt_at": body["receipt_completed_at"],
        "finalized_at": None,
        "receipt_completed_at": claim.claimed_at.isoformat(),
        "invocation_unknown": True,
        "invoked_at": None,
    }.items():
        mutated = {**body, key: replacement}
        forged = receipt.model_copy(
            update={
                "outcome_json": json.dumps(mutated, sort_keys=True, separators=(",", ":")),
                "outcome_digest": canonical_json_hash(mutated),
            }
        )
        with pytest.raises(DeliveryUnavailable):
            await h.delivery._finalize(forged, FinalizationCause.ACKNOWLEDGE)
    async with h.factory() as session:
        rows = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(rows) == 1
        assert rows[0].outcome_json == receipt.outcome_json
        assert rows[0].outcome_digest == receipt.outcome_digest
        assert rows[0].claimed_at == claim.claimed_at
        assert rows[0].claim_expires_at == claim.claim_expires_at


async def test_retry_backoff_and_exhaustion(delivery_harness):
    from datetime import datetime

    h = delivery_harness
    h.options = h.options.model_copy(update={"max_attempts": 2})
    h.delivery = h.build()
    claim = await h.claim()
    h.result = HandlerOutcome.RETRY
    first = await h.delivery.invoke(claim)
    body = json.loads(first.outcome_json)
    assert (
        datetime.fromisoformat(body["next_attempt_at"])
        - datetime.fromisoformat(body["receipt_completed_at"])
    ).total_seconds() == 1
    assert await h.delivery.claim(claim.event_id, h.project, "early") is None
    async with h.factory() as session:
        await session.execute(text("select pg_sleep(1.05)"))
    second = await h.delivery.claim(claim.event_id, h.project, "second")
    assert second.claim_generation == 2
    last = json.loads((await h.delivery.invoke(second)).outcome_json)
    assert last["delivery_state"] == "dead_letter" and last["error_code"] == "ATTEMPTS_EXHAUSTED"
    assert last["invocation_unknown"] is False and last["next_attempt_at"] is None
    assert await h.delivery.claim(claim.event_id, h.project, "third") is None
    control = await h.claim()
    h.result = HandlerOutcome.ACKNOWLEDGE
    assert (
        json.loads((await h.delivery.invoke(control)).outcome_json)["delivery_state"]
        == "acknowledged"
    )


async def test_completed_generation_replays_without_mutating_successor(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    await expire(h)
    original = await h.delivery.recover(claim.event_id, h.project)
    async with h.factory() as session:
        await session.execute(text("select pg_sleep(1.05)"))
    second = await h.delivery.claim(claim.event_id, h.project, "second")
    assert second.claim_generation == 2
    consumed = len(h.consumed)
    assert await h.delivery.invoke(claim) is None
    assert len(h.consumed) == consumed
    assert await h.delivery.finalize(claim, FinalizationCause.EXPIRED) == original
    assert len(h.consumed) == consumed + 1
    forged = original.model_copy(update={"outcome_digest": "sha256:" + "0" * 64})
    with pytest.raises(DeliveryUnavailable):
        await h.delivery._finalize(forged, FinalizationCause.EXPIRED)
    assert len(h.consumed) == consumed + 1
    async with h.factory() as session:
        event = await session.get(OutboxEvent, claim.event_id)
        assert event.claim_generation == 2 and event.claim_owner == "second"


@pytest.mark.parametrize("fault", ["exception", "invalid", "timeout"])
async def test_handler_failure_is_unknown_not_retryable(delivery_harness, fault):
    import asyncio

    h = delivery_harness

    async def fail(envelope):
        if fault == "exception":
            raise RuntimeError("private provider content")
        if fault == "timeout":
            await asyncio.sleep(2.1)

    h.handler_hook = fail
    if fault == "invalid":
        h.result = "acknowledge"
    receipt = await h.delivery.invoke(await h.claim())
    assert "private" not in receipt.outcome_json
    assert json.loads(receipt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"


async def test_concurrent_same_outcome_finalizers_replay_winner(delivery_harness):
    from app.modules.authorization.api.outbox_dispatch import OutboxDispatchPhase

    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 30})
    h.delivery = h.build()
    claim = await h.claim()
    await h.delivery._begin_invocation(claim)
    entered, ready = 0, asyncio.Event()

    async def barrier(facts):
        nonlocal entered
        if facts.phase is OutboxDispatchPhase.FINALIZE:
            entered += 1
            if entered == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), 5)

    h.prepare_hook = barrier
    first = asyncio.create_task(h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE))
    await asyncio.sleep(0.02)
    receipts = await asyncio.gather(
        first, h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    )
    assert receipts[0] == receipts[1]
    finalized = [f for f in h.consumed if f.phase is OutboxDispatchPhase.FINALIZE]
    assert len(finalized) == 2
    assert {f.outcome_digest for f in finalized} == {receipts[0].outcome_digest}
    assert entered == 3  # Losing proposal prepares once more for the stored digest.
    async with h.factory() as session:
        attempts = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(attempts) == 1 and attempts[0].outcome_json == receipts[0].outcome_json
        from app.modules.tasks.models import AuditEvent
        original_ids = {attempts[0].claim_decision_event_id, attempts[0].invoke_decision_event_id,
                        attempts[0].finalize_decision_event_id}
        assert len(original_ids) == 3 and None not in original_ids
        audits = (await session.scalars(select(AuditEvent).where(AuditEvent.action_id == "outbox.dispatch"))).all()
        assert len(audits) == 4 and original_ids < {audit.id for audit in audits}


async def test_running_handler_expiry_preserves_unknown_and_late_replay(delivery_harness):
    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 5, "handler_timeout_seconds": 4})
    h.delivery = h.build()
    claim = await h.claim()
    await asyncio.sleep(2)
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(envelope):
        entered.set()
        await release.wait()

    h.handler_hook = blocked
    invocation = asyncio.create_task(h.delivery.invoke(claim))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert (await h.delivery.drain(h.project)).invoked == 1
        await asyncio.sleep(3.05)
        receipt = await h.delivery.recover(claim.event_id, h.project)
        assert not invocation.done()
        assert json.loads(receipt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
        observation = await h.delivery.drain(h.project)
        assert observation.invoked == 0 and observation.unresolved == 1
        assert await h.delivery.claim(claim.event_id, h.project, "retry") is None
        release.set()
        assert await asyncio.wait_for(invocation, 2) == receipt
        assert len(h.handled) == 1
        assert await h.delivery.invoke(claim) is None
    finally:
        release.set()
        await asyncio.gather(invocation, return_exceptions=True)


async def test_cancelled_invocation_leaves_custody_for_unknown_recovery(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    entered = asyncio.Event()

    async def blocked(envelope):
        entered.set()
        await asyncio.Event().wait()

    h.handler_hook = blocked
    invocation = asyncio.create_task(h.delivery.invoke(claim))
    await asyncio.wait_for(entered.wait(), 2)
    invocation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await invocation
    async with h.factory() as session:
        assert (await DeliveryRepository(session).attempt(claim)).stage == "invoked"
    await expire(h)
    receipt = await h.delivery.recover(claim.event_id, h.project)
    assert json.loads(receipt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
    observation = await h.delivery.drain(h.project)
    assert observation.invoked == 0 and observation.unresolved == 1
    assert await h.delivery.invoke(claim) is None and len(h.handled) == 1


async def test_handler_suppressing_cancellation_cannot_ack_after_deadline(delivery_harness):
    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 30, "handler_timeout_seconds": 1})
    h.delivery = h.build()
    claim = await h.claim()
    cancelled, release = asyncio.Event(), asyncio.Event()

    async def suppress_cancellation(envelope):
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            await release.wait()

    h.handler_hook = suppress_cancellation
    invocation = asyncio.create_task(h.delivery.invoke(claim))
    try:
        await asyncio.wait_for(cancelled.wait(), 3)
        # The dispatcher returns while the uncooperative handler remains running.
        receipt = await asyncio.wait_for(asyncio.shield(invocation), 2)
        assert h.delivery._running_handlers
        assert json.loads(receipt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
        assert (await h.delivery.drain(h.project)).unresolved == 1
        release.set()
        await asyncio.gather(*tuple(h.delivery._running_handlers))
        assert await h.delivery.finalize(claim, FinalizationCause.UNKNOWN) == receipt
        assert await h.delivery.invoke(claim) is None and len(h.handled) == 1
    finally:
        release.set()
        await asyncio.gather(invocation, return_exceptions=True)
        await asyncio.gather(*tuple(h.delivery._running_handlers), return_exceptions=True)


async def test_completed_handler_after_deadline_is_unknown(delivery_harness):
    """A completed task must not turn event-loop delay into a timely success."""
    import time

    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 30, "handler_timeout_seconds": 1})
    h.delivery = h.build()

    async def blocking_handler(envelope):
        time.sleep(1.1)

    h.handler_hook = blocking_handler
    receipt = await h.delivery.invoke(await h.claim())
    assert json.loads(receipt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
    assert len(h.handled) == 1
    assert (await h.delivery.drain(h.project)).unresolved == 1
