"""Real PostgreSQL races with explicitly synthetic phase authorization."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.modules.authorization.api.decisions import DecisionOutcome
from app.modules.authorization.api.outbox_dispatch import OutboxDispatchPhase
from app.modules.outbox.api import DeliveryUnavailable, FinalizationCause
from app.modules.outbox.delivery_repository import DeliveryRepository, database_time
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent
from app.modules.outbox.registry import HandlerRegistry


async def test_claim_race_commits_one_generation(delivery_harness):
    h = delivery_harness
    event = await h.append()
    entered = 0
    ready = asyncio.Event()

    async def barrier(facts):
        nonlocal entered
        entered += 1
        if entered == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), 5)

    h.prepare_hook = barrier
    outcomes = await asyncio.gather(
        *(h.delivery.claim(event.event_id, h.project, owner) for owner in ("one", "two"))
    )
    assert sum(result is not None for result in outcomes) == 1
    assert len(h.consumed) == 1
    async with h.factory() as session:
        attempts = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(attempts) == 1 and attempts[0].claim_generation == 1


async def test_claim_lease_expiring_behind_lock_consumes_no_authority(delivery_harness):
    h = delivery_harness
    event = await h.append()
    proposed = asyncio.Event()

    async def prepared(facts):
        proposed.set()

    h.prepare_hook = prepared
    async with h.factory() as blocker, blocker.begin():
        await DeliveryRepository(blocker).event(event.event_id, h.project, lock=True)
        task = asyncio.create_task(h.delivery.claim(event.event_id, h.project, "waiting"))
        await asyncio.wait_for(proposed.wait(), 3)
        await blocker.execute(text("select pg_sleep(3.1)"))
    assert await asyncio.wait_for(task, 5) is None
    assert h.consumed == []
    async with h.factory() as session:
        assert (await session.get(OutboxEvent, event.event_id)).delivery_state == "pending"
        assert (await session.scalars(select(OutboxDeliveryAttempt))).all() == []


async def test_claim_validator_requires_committed_invocation(delivery_harness):
    h = delivery_harness
    claim = await h.claim()
    assert await h.delivery.observe_invocation(claim) is None
    async with h.factory() as writer, writer.begin():
        attempt = await DeliveryRepository(writer).attempt(claim, lock=True)
        attempt.stage, attempt.invoked_at = "invoked", await database_time(writer)
        await writer.flush()
        assert await h.delivery.observe_invocation(claim) is None
    observed = await h.delivery.observe_invocation(claim)
    assert observed.claim == claim and observed.observed_at >= claim.claimed_at
    for changes in (
        {"project_id": uuid4()},
        {"event_id": uuid4()},
        {"payload_digest": "sha256:" + "0" * 64},
        {"claim_owner": "different"},
        {"claim_generation": 2},
        {"claimed_at": claim.claimed_at + timedelta(microseconds=1)},
        {"claim_expires_at": claim.claim_expires_at + timedelta(seconds=1)},
    ):
        assert await h.delivery.observe_invocation(claim.model_copy(update=changes)) is None
    await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    assert await h.delivery.observe_invocation(claim) is None


@pytest.mark.parametrize("phase", list(OutboxDispatchPhase))
@pytest.mark.parametrize("fault", ["deny", "action", "permission", "phase", "facts"])
async def test_each_phase_denies_mismatch_and_reused_authority(delivery_harness, phase, fault):
    h = delivery_harness
    event = await h.append()
    claim = None
    if phase is not OutboxDispatchPhase.CLAIM:
        claim = await h.delivery.claim(event.event_id, h.project, "worker")
    if phase is OutboxDispatchPhase.FINALIZE:
        assert await h.delivery._begin_invocation(claim)
    consumed = len(h.consumed)
    if fault == "deny":
        h.outcome = DecisionOutcome.DENY
    elif fault == "action":
        h.action = "task.claim"
    elif fault == "permission":
        h.permission = "task.claim"
    elif fault == "facts":
        h.substitute = lambda facts: replace(facts, claim_owner="substituted")
    else:
        h.substitute = lambda facts: replace(
            facts,
            phase=OutboxDispatchPhase.INVOKE
            if phase is OutboxDispatchPhase.CLAIM
            else OutboxDispatchPhase.CLAIM,
            outcome_digest=None,
        )
    with pytest.raises(DeliveryUnavailable):
        if phase is OutboxDispatchPhase.CLAIM:
            await h.delivery.claim(event.event_id, h.project, "worker")
        elif phase is OutboxDispatchPhase.INVOKE:
            await h.delivery._begin_invocation(claim)
        else:
            await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    if fault in ("phase", "facts"):
        assert len(h.consumed) == consumed
    async with h.factory() as session:
        row = await session.get(OutboxEvent, event.event_id)
        assert row.delivery_state == (
            "pending" if phase is OutboxDispatchPhase.CLAIM else "claimed"
        )
        attempts = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(attempts) == (0 if phase is OutboxDispatchPhase.CLAIM else 1)
        if attempts:
            assert attempts[0].stage == (
                "claimed" if phase is OutboxDispatchPhase.INVOKE else "invoked"
            )


async def test_unknown_registration_stays_unclaimed_and_counted(delivery_harness):
    h = delivery_harness
    event = await h.append(event_version=2)
    assert await h.delivery.claim(event.event_id, h.project, "worker") is None
    observation = await h.delivery.drain(h.project)
    assert observation.pending == observation.unsupported == 1
    assert h.prepared == h.consumed == h.handled == []
    assert await h.build(HandlerRegistry([])).claim(event.event_id, h.project, "worker") is None


async def test_invoke_releases_locks_and_runs_generation_once(delivery_harness):
    h = delivery_harness
    claim = await h.claim()

    async def independent_lock(envelope):
        async with h.factory() as session, session.begin():
            await session.execute(text("set local lock_timeout='500ms'"))
            row = await DeliveryRepository(session).event(claim.event_id, h.project, lock=True)
            assert row.delivery_state == "claimed"

    h.handler_hook = independent_lock
    results = await asyncio.gather(h.delivery.invoke(claim), h.delivery.invoke(claim))
    assert sum(result is not None for result in results) == 1
    assert len(h.handled) == 1
    assert [f.phase for f in h.consumed] == list(OutboxDispatchPhase)


@pytest.mark.parametrize("phase", list(OutboxDispatchPhase))
async def test_authority_wait_cannot_commit_an_expired_live_phase(delivery_harness, phase):
    """A delay inside consume must roll back instead of committing stale live facts."""
    h = delivery_harness
    event = await h.append()
    claim = None
    if phase is not OutboxDispatchPhase.CLAIM:
        claim = await h.delivery.claim(event.event_id, h.project, "worker")
    if phase is OutboxDispatchPhase.FINALIZE:
        await h.delivery._begin_invocation(claim)

    async def delay(facts):
        await asyncio.sleep(3.1)

    h.consume_hook = delay
    with pytest.raises(DeliveryUnavailable):
        if phase is OutboxDispatchPhase.CLAIM:
            await h.delivery.claim(event.event_id, h.project, "worker")
        elif phase is OutboxDispatchPhase.INVOKE:
            await h.delivery._begin_invocation(claim)
        else:
            await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    async with h.factory() as session:
        row = await session.get(OutboxEvent, event.event_id)
        assert row.delivery_state == (
            "pending" if phase is OutboxDispatchPhase.CLAIM else "claimed"
        )
        if claim:
            attempt = await DeliveryRepository(session).attempt(claim)
            assert attempt.stage == (
                "claimed" if phase is OutboxDispatchPhase.INVOKE else "invoked"
            )
    assert h.handled == []
