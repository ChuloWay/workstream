"""Actual Celery task functions with real OUTBOX custody and fixed-service AUTH."""

import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from app.adapters.auth import outbox_dispatch_authorization
from app.adapters.outbox import outbox_delivery
from app.core.config import get_settings
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent
from app.modules.outbox.registry import HandlerRegistry


@pytest.fixture
def worker(delivery_harness, monkeypatch):
    h = delivery_harness
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import outbox as worker

    monkeypatch.setattr(worker, "get_database_url", lambda: h.factory.kw["bind"].url)
    monkeypatch.setattr(
        worker,
        "production_outbox_delivery",
        lambda factory: outbox_delivery(
            factory,
            authorization_factory=outbox_dispatch_authorization,
            registry=HandlerRegistry([("ContributionRecorded", 1, h.handle)]),
            options=h.options,
        ),
    )
    yield worker
    get_settings.cache_clear()


def deliver(worker, event, project):
    return worker.deliver_event.apply(
        args=(str(event), str(project)),
        task_id=str(uuid4()),
        throw=True,
    ).get()


async def test_worker_duplicate_delivery(delivery_harness, worker):
    h = delivery_harness
    event = await h.append()
    assert deliver(worker, event.event_id, h.project) == {"status": "delivery_recorded"}
    assert deliver(worker, event.event_id, h.project) == {"status": "delivery_unavailable"}
    assert len(h.handled) == 1
    async with h.factory() as session:
        attempts = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(attempts) == 1 and attempts[0].stage == "completed"
        assert all(
            (
                attempts[0].claim_decision_event_id,
                attempts[0].invoke_decision_event_id,
                attempts[0].finalize_decision_event_id,
            )
        )


@pytest.mark.parametrize("invoked", [False, True])
async def test_worker_expired_recovery(delivery_harness, worker, invoked):
    h = delivery_harness
    claim = await h.claim()
    if invoked:
        await h.delivery._begin_invocation(claim)
    async with h.factory() as session:
        await session.execute(text("select pg_sleep(3.05)"))
    assert deliver(worker, claim.event_id, h.project) == {"status": "delivery_recorded"}
    async with h.factory() as session:
        attempt = (await session.scalars(select(OutboxDeliveryAttempt))).one()
        body = json.loads(attempt.outcome_json)
        assert body["error_code"] == (
            "INVOKE_OUTCOME_UNKNOWN" if invoked else "LEASE_EXPIRED_BEFORE_INVOKE"
        )
        assert (attempt.invoke_decision_event_id is not None) is invoked
        assert attempt.finalize_decision_event_id
    assert h.handled == []


async def test_worker_scan_closes_sql_before_publication_and_retries_missing_hints(
    delivery_harness, worker, monkeypatch
):
    h = delivery_harness
    events = [await h.append() for _ in range(3)]
    published = []
    # Actual candidate query and engine disposal execute before this broker seam.
    real_candidates = worker._candidates
    read_closed = False

    async def candidates(after):
        nonlocal read_closed
        page = await real_candidates(after)
        read_closed = True
        return page

    def publish(*, args):
        assert read_closed
        published.append(args)
        if len(published) == 1:
            raise ConnectionError("broker unavailable")

    monkeypatch.setattr(worker, "_candidates", candidates)
    monkeypatch.setattr(worker.deliver_event, "apply_async", publish)
    result = worker.scan_pending.apply(task_id=str(uuid4()), throw=True).get()
    assert result == {"selected": 3, "published": 2}
    assert {e.event_id for e in events} == {UUID(args[0]) for args in published}
    assert worker.scan_pending.apply(task_id=str(uuid4()), throw=True).get() == {
        "selected": 3,
        "published": 3,
    }
    async with h.factory() as session:
        assert {e.delivery_state for e in (await session.scalars(select(OutboxEvent))).all()} == {
            "pending"
        }
        assert (await session.scalars(select(OutboxDeliveryAttempt))).all() == []


@pytest.mark.parametrize(
    "args,task_id",
    [
        (("bad", "bad"), str(uuid4())),
        ((str(uuid4()), str(uuid4())), "not-a-task-uuid"),
        ((None, str(uuid4())), str(uuid4())),
    ],
)
async def test_worker_rejects_transport_before_sql(worker, monkeypatch, args, task_id):
    def forbidden():
        pytest.fail("malformed broker input reached SQL")

    monkeypatch.setattr(worker, "get_database_url", forbidden)
    assert worker.deliver_event.apply(args=args, task_id=task_id, throw=True).get() == {
        "status": "delivery_rejected"
    }
    assert worker.scan_pending.apply(args=("bad",), throw=True).get() == {"status": "scan_rejected"}


@pytest.mark.parametrize("failure", ["delivery", "scan"])
async def test_worker_infrastructure_failure_has_bounded_sanitized_retry(
    worker, monkeypatch, failure
):
    from celery.exceptions import Retry

    async def failed(*args):
        raise RuntimeError("private database detail")

    monkeypatch.setattr(worker, "_deliver" if failure == "delivery" else "_candidates", failed)
    task = worker.deliver_event if failure == "delivery" else worker.scan_pending
    args = (str(uuid4()), str(uuid4())) if failure == "delivery" else ()
    with pytest.raises(Retry) as raised:
        task.apply(args=args, task_id=str(uuid4()), throw=True)
    assert raised.value.when == 30
    assert "private" not in str(raised.value)
    with pytest.raises(RuntimeError, match="outbox .* unavailable") as exhausted:
        task.apply(args=args, task_id=str(uuid4()), retries=3, throw=True)
    assert "private" not in str(exhausted.value)


async def test_worker_scan_continues_after_failed_publication(worker, monkeypatch):
    from app.modules.outbox.api import DeliveryCandidate, DeliveryCandidatePage

    selectors = (DeliveryCandidate(event_id=uuid4(), project_id=uuid4()),)
    cursor = selectors[-1].event_id

    async def page(after):
        return DeliveryCandidatePage(items=selectors, next_after=cursor)

    attempts = []

    def publish(*, args):
        attempts.append(args)
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(worker, "_candidates", page)
    monkeypatch.setattr(worker.deliver_event, "apply_async", publish)
    monkeypatch.setattr(worker.scan_pending, "apply_async", publish)
    assert worker.scan_pending.apply(task_id=str(uuid4()), throw=True).get() == {
        "selected": 1,
        "published": 0,
    }
    assert attempts == [(str(cursor), str(selectors[0].project_id)), (str(cursor),)]


async def test_empty_production_registry_does_not_claim_feature_work(delivery_harness):
    from app.adapters.outbox import production_outbox_delivery

    h = delivery_harness
    event = await h.append()
    production = production_outbox_delivery(h.factory)
    assert (await production.candidates()).items == ()
    assert await production.deliver(event.event_id, h.project, "worker") is None
    async with h.factory() as session:
        assert (await session.scalars(select(OutboxDeliveryAttempt))).all() == []
        assert (await session.get(OutboxEvent, event.event_id)).delivery_state == "pending"
