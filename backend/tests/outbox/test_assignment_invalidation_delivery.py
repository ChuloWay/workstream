"""Production immutable registry and real dispatcher/feature authority composition."""

from uuid import UUID

from sqlalchemy import select

from app.adapters.outbox import production_outbox_delivery
from app.modules.outbox.models import OutboxEvent, OutboxDeliveryAttempt
from tests.test_tasks import task_client as task_client, task_database_env as task_database_env
from tests.tasks.invalidation_support import setup_assignment, revoke, snapshot


async def test_production_delivery_releases_exact_assignment(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    async with s.sessions() as session:
        event = (await session.scalars(select(OutboxEvent))).one()
        event_id = event.event_id
    delivery = production_outbox_delivery(s.sessions)
    page = await delivery.candidates()
    assert [item.event_id for item in page.items] == [event_id]
    result = await delivery.deliver(event_id, UUID(s.project["id"]), "production-proof")
    assert result is not None
    task, assignments, events = await snapshot(s)
    assert task["status"] == "ready" and task["assigned_to"] is None
    assert assignments[0]["status"] == "authority_revoked"
    assert assignments[0]["released_at"] is not None
    assert len([e for e in events if e["event_type"] == "TaskAssignmentAuthorityRevoked"]) == 1
    assert await delivery.deliver(event_id, UUID(s.project["id"]), "duplicate") is None
    assert await snapshot(s) == (task, assignments, events)
    async with s.sessions() as session:
        attempts = (await session.scalars(select(OutboxDeliveryAttempt))).all()
        assert len(attempts) == 1 and attempts[0].stage == "completed"


def _broker_worker(app, hostname):
    """Isolate a real worker process tree; the production startup guard runs here."""
    import os
    os.setsid()
    app.Worker(pool="prefork", concurrency=1, queues=["workstream.outbox"],
               hostname=hostname, loglevel="ERROR", without_gossip=True,
               without_mingle=True, without_heartbeat=True).start()


async def test_real_broker_prefork_delivers_committed_invalidation(task_client, monkeypatch):
    """Real Redis routing, startup, child execution, feature transaction and finalization."""
    import asyncio
    import multiprocessing
    import os
    import signal
    import time
    from uuid import uuid4
    import redis
    from app.core.config import get_settings

    broker = os.environ["WORKSTREAM_TEST_BROKER_URL"]
    connection = redis.Redis.from_url(broker)
    assert connection.ping()
    prefix = f"workstream-proof-{uuid4()}:"
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    async with s.sessions() as session:
        event_id = (await session.scalars(select(OutboxEvent.event_id))).one()
    monkeypatch.setenv("WORKSTREAM_ARTIFACT_STORE_BACKEND", "disabled")
    get_settings.cache_clear()
    from app.workers import outbox as worker

    app = worker.celery_app
    monkeypatch.setitem(app.conf, "broker_url", broker)
    monkeypatch.setitem(app.conf, "broker_transport_options", {"global_keyprefix": prefix})
    monkeypatch.setitem(app.conf, "task_always_eager", False)
    monkeypatch.setattr(worker, "get_database_url", lambda: s.sessions.kw["bind"].url)
    hostname = f"outbox-proof-{uuid4()}@localhost"
    process = multiprocessing.get_context("fork").Process(target=_broker_worker, args=(app, hostname))
    process.start()
    try:
        deadline = time.monotonic() + 45
        ready = False
        while time.monotonic() < deadline:
            assert process.is_alive(), f"worker startup failed: {process.exitcode}"
            if app.control.ping(destination=[hostname], timeout=0.2):
                ready = True
                break
            await asyncio.sleep(0.1)
        assert ready, "real broker worker did not become ready"
        worker.deliver_event.apply_async(args=(str(event_id), s.project["id"]))
        finished = False
        while time.monotonic() < deadline:
            async with s.sessions() as session:
                event = await session.get(OutboxEvent, event_id)
                if event.delivery_state == "acknowledged":
                    finished = True
                    break
            await asyncio.sleep(0.1)
        assert finished, "production delivery did not finalize"
        task, assignments, events = await snapshot(s)
        assert task["status"] == "ready" and assignments[0]["status"] == "authority_revoked"
        assert len([e for e in events if e["event_type"] == "TaskAssignmentAuthorityRevoked"]) == 1
    finally:
        if process.is_alive():
            os.killpg(process.pid, signal.SIGTERM)
        process.join(timeout=10)
        if process.is_alive():
            os.killpg(process.pid, signal.SIGKILL)
            process.join(timeout=5)
        assert not process.is_alive(), "test worker cleanup failed"
        keys = list(connection.scan_iter(match=prefix + "*"))
        if keys:
            connection.delete(*keys)
        assert list(connection.scan_iter(match=prefix + "*")) == []
        connection.close()
        get_settings.cache_clear()


async def test_missing_feature_authority_preserves_assignment(task_client, monkeypatch):
    import json
    s = await setup_assignment(task_client, monkeypatch, reconciler=False)
    await revoke(s)
    before = await snapshot(s)
    async with s.sessions() as session:
        event_id = (await session.scalars(select(OutboxEvent.event_id))).one()
    result = await production_outbox_delivery(s.sessions).deliver(
        event_id, UUID(s.project["id"]), "missing-feature-authority",
    )
    assert result is not None
    assert json.loads(result.outcome_json)["error_code"] == "HANDLER_REJECTED"
    assert await snapshot(s) == before
