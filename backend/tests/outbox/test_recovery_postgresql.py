"""Crash boundaries, retry exhaustion and exact retained outcome replay."""

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


async def test_old_generation_cannot_invoke_or_finalize_successor(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    await expire(h)
    await h.delivery.recover(claim.event_id, h.project)
    async with h.factory() as session:
        await session.execute(text("select pg_sleep(1.05)"))
    second = await h.delivery.claim(claim.event_id, h.project, "second")
    assert second.claim_generation == 2
    consumed = len(h.consumed)
    assert await h.delivery.invoke(claim) is None
    with pytest.raises(DeliveryUnavailable):
        await h.delivery.finalize(claim, FinalizationCause.EXPIRED)
    assert len(h.consumed) == consumed
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
