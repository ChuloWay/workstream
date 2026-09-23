"""Database guards reject independently valid but inconsistent delivery facts."""

from datetime import datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.hashing import canonical_json_hash
from app.modules.outbox.api import FinalizationCause
from app.modules.outbox.delivery import _encode, _outcome
from app.modules.outbox.delivery_repository import DeliveryRepository, database_time
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent


@pytest.mark.parametrize("side", ["event", "attempt"])
async def test_projection_and_receipt_commit_together(delivery_harness, side):
    h = delivery_harness
    claim = await h.claim()
    await h.delivery._begin_invocation(claim)
    async with h.factory() as session:
        attempt = await DeliveryRepository(session).attempt(claim)
        value = _outcome(
            claim,
            attempt.invoked_at,
            FinalizationCause.ACKNOWLEDGE,
            await database_time(session),
            h.options,
        )
        await session.rollback()
        with pytest.raises(DBAPIError, match="outbox (claim|outcome) custody mismatch"):
            async with session.begin():
                if side == "event":
                    await session.execute(
                        text(
                            "update outbox_events set delivery_state='acknowledged',claim_owner=null,"
                            "claimed_at=null,claim_expires_at=null,finalized_at=cast(:now as timestamptz) where event_id=:id"
                        ),
                        {
                            "id": claim.event_id,
                            "now": datetime.fromisoformat(value["finalized_at"]),
                        },
                    )
                else:
                    await session.execute(
                        text(
                            "update outbox_delivery_attempts set stage='completed',outcome_json=:body,"
                            "outcome_digest=:digest where event_id=:id"
                        ),
                        {
                            "id": claim.event_id,
                            "body": _encode(value),
                            "digest": canonical_json_hash(value),
                        },
                    )
        attempt = await DeliveryRepository(session).attempt(claim)
        assert attempt.stage == "invoked" and attempt.outcome_json is None
        assert (await session.get(OutboxEvent, claim.event_id)).delivery_state == "claimed"
    receipt = await h.delivery.finalize(claim, FinalizationCause.ACKNOWLEDGE)
    async with h.factory() as session:
        assert (
            await DeliveryRepository(session).attempt(claim)
        ).outcome_digest == receipt.outcome_digest
        assert (await session.get(OutboxEvent, claim.event_id)).delivery_state == "acknowledged"


@pytest.mark.parametrize(
    "change",
    [
        "claim_owner='other'",
        "claim_generation=2",
        "project_id=project_id",
        "invoked_at=null",
        "payload_digest='sha256:'||repeat('0',64)",
        "claimed_at=claimed_at+interval '1 microsecond'",
        "claim_expires_at=claim_expires_at+interval '1 second'",
        "outcome_digest='sha256:'||repeat('0',64)",
        "outcome_json='{}'",
        "stage='invoked'",
        "DELETE",
        "TRUNCATE",
    ],
)
async def test_completed_custody_is_immutable(delivery_harness, change):
    h = delivery_harness
    claim = await h.claim()
    receipt = await h.delivery.invoke(claim)
    async with h.factory() as session:
        with pytest.raises(
            DBAPIError, match="outbox delivery custody (is immutable|cannot be removed)"
        ):
            async with session.begin():
                if change == "TRUNCATE":
                    statement = "truncate outbox_delivery_attempts"
                elif change == "DELETE":
                    statement = "delete from outbox_delivery_attempts where event_id=:id"
                else:
                    statement = f"update outbox_delivery_attempts set {change} where event_id=:id"
                await session.execute(text(statement), {"id": claim.event_id})
        rows = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(rows) == 1 and rows[0].outcome_json == receipt.outcome_json
        assert rows[0].outcome_digest == receipt.outcome_digest


async def test_claim_requires_matching_custody_at_commit(delivery_harness):
    h = delivery_harness
    event = await h.append()
    async with h.factory() as session:
        with pytest.raises(DBAPIError, match="outbox delivery custody does not match event"):
            async with session.begin():
                await session.execute(
                    text(
                        "update outbox_events set delivery_state='claimed',attempt_count=1,claim_generation=1,"
                        "next_attempt_at=null,claim_owner='worker',claimed_at=statement_timestamp(),"
                        "last_attempt_at=statement_timestamp(),claim_expires_at=statement_timestamp()+interval '5 seconds' "
                        "where event_id=:id"
                    ),
                    {"id": event.event_id},
                )
        assert (await session.get(OutboxEvent, event.event_id)).delivery_state == "pending"
    assert await h.delivery.claim(event.event_id, h.project, "worker")


async def test_invocation_requires_timestamp_not_sql_null(delivery_harness):
    """A CHECK evaluating NULL must not admit invoked custody without its time."""
    h = delivery_harness
    claim = await h.claim()
    async with h.factory() as session:
        with pytest.raises(DBAPIError, match="ck_outbox_delivery_attempts_stage_shape"):
            async with session.begin():
                await session.execute(
                    text("update outbox_delivery_attempts set stage='invoked' where event_id=:id"),
                    {"id": claim.event_id},
                )
        assert (await DeliveryRepository(session).attempt(claim)).stage == "claimed"
    assert await h.delivery._begin_invocation(claim)


async def _write_paired_outcome(session, claim, value):
    """Write both valid projections so rejection must come from outcome custody."""
    await session.execute(
        text(
            "update outbox_delivery_attempts set stage='completed',outcome_json=:body,"
            "outcome_digest=:digest where event_id=:id and claim_generation=:generation"
        ),
        {
            "id": claim.event_id,
            "generation": claim.claim_generation,
            "body": _encode(value),
            "digest": canonical_json_hash(value),
        },
    )
    await session.execute(
        text(
            "update outbox_events set delivery_state=:state,last_error_code=:code,"
            "next_attempt_at=:retry,finalized_at=:final,claim_owner=null,claimed_at=null,"
            "claim_expires_at=null where event_id=:id"
        ),
        {
            "id": claim.event_id,
            "state": value["delivery_state"],
            "code": value["error_code"],
            "retry": datetime.fromisoformat(value["next_attempt_at"])
            if value["next_attempt_at"]
            else None,
            "final": datetime.fromisoformat(value["finalized_at"])
            if value["finalized_at"]
            else None,
        },
    )


@pytest.mark.parametrize(
    "cause", [FinalizationCause.ACKNOWLEDGE, FinalizationCause.RETRY, FinalizationCause.REJECT]
)
async def test_expired_invoked_sql_outcome_rejected(delivery_harness, cause):
    """Paired expired outcomes cannot assert success, safe retry, or rejection."""
    from datetime import timedelta
    import json

    h = delivery_harness
    claim = await h.claim()
    await h.delivery._begin_invocation(claim)
    async with h.factory() as session:
        attempt = await DeliveryRepository(session).attempt(claim)
        value = _outcome(claim, attempt.invoked_at, cause, await database_time(session), h.options)
        await session.execute(text("select pg_sleep(3.05)"))
        completed = await database_time(session)
        value["receipt_completed_at"] = completed.isoformat()
        if value["next_attempt_at"]:
            value["next_attempt_at"] = (completed + timedelta(seconds=1)).isoformat()
        if value["finalized_at"]:
            value["finalized_at"] = completed.isoformat()
        await session.rollback()
        with pytest.raises(DBAPIError, match="ck_outbox_delivery_attempts_outcome"):
            async with session.begin():
                await _write_paired_outcome(session, claim, value)
        assert (await DeliveryRepository(session).attempt(claim)).stage == "invoked"
        assert (await session.get(OutboxEvent, claim.event_id)).delivery_state == "claimed"
    receipt = await h.delivery.recover(claim.event_id, h.project)
    assert json.loads(receipt.outcome_json)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"


@pytest.mark.parametrize("fault", ["future_completion", "overlong_retry"])
async def test_sql_completion_time_and_retry_bounds(delivery_harness, fault):
    from datetime import timedelta

    h = delivery_harness
    h.options = h.options.model_copy(update={"lease_seconds": 30})
    h.delivery = h.build()
    claim = await h.claim()
    await h.delivery._begin_invocation(claim)
    cause = (
        FinalizationCause.ACKNOWLEDGE if fault == "future_completion" else FinalizationCause.RETRY
    )
    async with h.factory() as session:
        attempt = await DeliveryRepository(session).attempt(claim)
        now = await database_time(session)
        completed = now + timedelta(seconds=10) if fault == "future_completion" else now
        value = _outcome(claim, attempt.invoked_at, cause, completed, h.options)
        if fault == "overlong_retry":
            value["next_attempt_at"] = (completed + timedelta(days=1, microseconds=1)).isoformat()
        await session.rollback()
        error = (
            "outbox completion cannot be in the future"
            if fault == "future_completion"
            else "ck_outbox_delivery_attempts_outcome"
        )
        with pytest.raises(DBAPIError, match=error):
            async with session.begin():
                await _write_paired_outcome(session, claim, value)
        assert (await DeliveryRepository(session).attempt(claim)).stage == "invoked"
        assert (await session.get(OutboxEvent, claim.event_id)).delivery_state == "claimed"
    assert await h.delivery.finalize(claim, cause)


async def test_sql_claim_lease_is_bounded(delivery_harness):
    from datetime import timedelta

    h = delivery_harness
    event = await h.append()
    async with h.factory() as session:
        now = await database_time(session)
        await session.rollback()
        with pytest.raises(DBAPIError, match="ck_outbox_delivery_attempts_lease"):
            async with session.begin():
                await session.execute(
                    text(
                        "update outbox_events set delivery_state='claimed',attempt_count=1,claim_generation=1,"
                        "next_attempt_at=null,claim_owner='bounded',claimed_at=:now,"
                        "last_attempt_at=:now,claim_expires_at=:expires where event_id=:id"
                    ),
                    {"id": event.event_id, "now": now, "expires": now + timedelta(seconds=3601)},
                )
                session.add(
                    OutboxDeliveryAttempt(
                        event_id=event.event_id,
                        project_id=str(h.project),
                        payload_digest=canonical_json_hash(event.payload),
                        claim_generation=1,
                        claim_owner="bounded",
                        claimed_at=now,
                        claim_expires_at=now + timedelta(seconds=3601),
                        stage="claimed",
                    )
                )
                await session.flush()
        assert (await session.get(OutboxEvent, event.event_id)).delivery_state == "pending"
    h.options = h.options.model_copy(update={"lease_seconds": 3600})
    h.delivery = h.build()
    claim = await h.delivery.claim(event.event_id, h.project, "bounded")
    assert (claim.claim_expires_at - claim.claimed_at).total_seconds() == 3600
