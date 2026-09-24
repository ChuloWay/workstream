"""Actual worker startup selection and synchronous entry guard, before SQL."""

import os
from types import SimpleNamespace

import pytest
from celery.concurrency.prefork import TaskPool
from celery.concurrency.solo import TaskPool as SoloPool
from celery.exceptions import WorkerShutdown

from app.workers import outbox_topology as topology


def worker(*, queues=(topology.OUTBOX_QUEUE,), pool=TaskPool, eager=False):
    return SimpleNamespace(pool_cls=pool, app=SimpleNamespace(
        conf=SimpleNamespace(task_always_eager=eager),
        amqp=SimpleNamespace(queues=SimpleNamespace(consume_from=queues)),
    ))


@pytest.fixture(autouse=True)
def reset_marker(monkeypatch):
    monkeypatch.setattr(topology, "_validated_parent", None)


@pytest.mark.parametrize("pool", ["solo", SoloPool, "threads"])
def test_delivery_queue_requires_prefork(pool):
    with pytest.raises(WorkerShutdown):
        topology.validate_outbox_worker(worker(pool=pool))
    assert topology._validated_parent is None


def test_delivery_queue_rejects_eager():
    with pytest.raises(WorkerShutdown):
        topology.validate_outbox_worker(worker(eager=True))
    assert topology._validated_parent is None


def test_other_queue_allows_solo():
    topology.validate_outbox_worker(worker(queues=("celery",), pool=SoloPool))
    assert topology._validated_parent is None


@pytest.mark.parametrize("mode", ["direct", "eager", "unvalidated", "parent", "dynamic_queue"])
def test_delivery_entry_rejects_unvalidated_execution(monkeypatch, mode):
    configured = worker()
    if mode == "dynamic_queue":
        configured = worker(queues=("celery",), pool=TaskPool)
    topology.validate_outbox_worker(configured)
    monkeypatch.setattr(topology.os, "getppid", lambda: os.getpid() if mode != "parent" else 1)
    if mode == "unvalidated":
        topology._validated_parent = None
    request = SimpleNamespace(is_eager=mode == "eager", called_directly=mode == "direct")
    with pytest.raises(RuntimeError, match="validated prefork"):
        topology.require_outbox_worker(SimpleNamespace(app=configured.app, request=request))


def test_validated_prefork_child_enters(monkeypatch):
    configured = worker(pool="prefork")
    topology.validate_outbox_worker(configured)
    monkeypatch.setattr(topology.os, "getppid", os.getpid)
    topology.require_outbox_worker(SimpleNamespace(app=configured.app,
        time_limit=300, request=SimpleNamespace(is_eager=False, called_directly=False, timelimit=None)))


def test_synchronous_task_rejects_before_sql(monkeypatch):
    from uuid import uuid4
    from app.core.config import get_settings
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import outbox
    def forbidden(*_args, **_kwargs):
        pytest.fail("unvalidated delivery reached SQL/async execution")
    monkeypatch.setattr(outbox, "run_async_task", forbidden)
    try:
        with pytest.raises(RuntimeError, match="validated prefork"):
            outbox.deliver_event.apply(args=(str(uuid4()), str(uuid4())), task_id=str(uuid4()), throw=True)
        with pytest.raises(RuntimeError, match="validated prefork"):
            outbox.deliver_event(str(uuid4()), str(uuid4()))
    finally:
        get_settings.cache_clear()


def test_delivery_routes_to_dedicated_queue(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers.celery_app import create_celery_app
    app = create_celery_app()
    try:
        route = app.amqp.router.route({}, topology.OUTBOX_DELIVERY_TASK)
        assert route["queue"].name == topology.OUTBOX_QUEUE
        assert app.amqp.router.route({}, "workstream.project_setup.compile")["queue"].name == "celery"
    finally:
        app.close()
        get_settings.cache_clear()


@pytest.mark.parametrize("task_limit,message_limit", [(None, None), (301, None), (300, 301)])
def test_delivery_cannot_disable_or_extend_process_bound(monkeypatch, task_limit, message_limit):
    configured = worker()
    topology.validate_outbox_worker(configured)
    monkeypatch.setattr(topology.os, "getppid", os.getpid)
    with pytest.raises(RuntimeError, match="bounded hard time limit"):
        topology.require_outbox_worker(SimpleNamespace(app=configured.app, time_limit=task_limit,
            request=SimpleNamespace(is_eager=False, called_directly=False, timelimit=(message_limit, None))))
