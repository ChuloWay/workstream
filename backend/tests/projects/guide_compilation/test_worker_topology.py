"""Project-guide inference worker topology and timeout boundaries."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from celery.concurrency.prefork import TaskPool
from celery.concurrency.solo import TaskPool as SoloPool
from celery.exceptions import WorkerShutdown

from app.core.config import get_settings
from app.workers import project_setup_topology as topology


def worker(
    *,
    queues=(topology.PROJECT_GUIDE_QUEUE,),
    pool=TaskPool,
    eager=False,
    broker="redis://localhost:6379/0",
    disable_prefetch=True,
    visibility=topology.CELERY_VISIBILITY_TIMEOUT_SECONDS,
):
    conf = SimpleNamespace(
        broker_url=broker,
        task_always_eager=eager,
        worker_disable_prefetch=disable_prefetch,
        visibility_timeout=visibility,
        broker_transport_options={"visibility_timeout": visibility},
        result_backend_transport_options={"visibility_timeout": visibility},
    )
    return SimpleNamespace(
        pool_cls=pool,
        app=SimpleNamespace(
            conf=conf,
            amqp=SimpleNamespace(queues=SimpleNamespace(consume_from=queues)),
        ),
    )


@pytest.fixture(autouse=True)
def restore_state(monkeypatch):
    monkeypatch.setenv("WORKSTREAM_PROJECT_AGENT_RUNTIME", "openai_agents_sdk")
    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()
    monkeypatch.setattr(topology, "_validated_parent", None)
    try:
        yield
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "configured",
    (
        worker(pool=SoloPool),
        worker(eager=True),
        worker(broker="amqp://localhost"),
        worker(disable_prefetch=False),
        worker(visibility=60),
    ),
)
def test_inference_worker_rejects_unsafe_delivery(configured):
    with pytest.raises(WorkerShutdown, match="bounded Redis prefork"):
        topology.validate_project_setup_worker(configured)
    assert topology._validated_parent is None


def test_inference_worker_ignores_processes_without_default_queue():
    topology.validate_project_setup_worker(worker(queues=("workstream.outbox",)))
    assert topology._validated_parent is None


def test_manager_authored_runtime_does_not_require_provider_worker_topology(monkeypatch):
    monkeypatch.setenv("WORKSTREAM_PROJECT_AGENT_RUNTIME", "manager_authored")
    get_settings.cache_clear()
    topology.validate_project_setup_worker(worker(pool=SoloPool, broker="memory://"))
    topology.require_project_setup_worker(SimpleNamespace())


def test_validated_prefork_child_requires_exact_hard_limit(monkeypatch):
    configured = worker(pool="prefork")
    topology.validate_project_setup_worker(configured)
    monkeypatch.setattr(topology.os, "getppid", os.getpid)
    task = SimpleNamespace(
        app=configured.app,
        time_limit=topology.PROJECT_GUIDE_HARD_LIMIT_SECONDS,
        request=SimpleNamespace(
            is_eager=False,
            called_directly=False,
            timelimit=(topology.PROJECT_GUIDE_HARD_LIMIT_SECONDS, None),
        ),
    )
    topology.require_project_setup_worker(task)
    task.time_limit -= 1
    with pytest.raises(RuntimeError, match="bounded hard time limit"):
        topology.require_project_setup_worker(task)


def test_direct_inference_rejects_before_task_body(monkeypatch):
    from app.workers import project_setup

    monkeypatch.setattr(
        project_setup,
        "run_async_task",
        lambda _factory: pytest.fail("unsafe delivery reached model construction"),
    )
    project_setup.run_project_guide_compilation.push_request(id="delivery")
    try:
        with pytest.raises(RuntimeError, match="validated Redis prefork"):
            project_setup.run_project_guide_compilation.run("bad", "bad", "bad", "bad", 1)
    finally:
        project_setup.run_project_guide_compilation.pop_request()


def test_task_and_shared_app_pin_timeout_hierarchy():
    from app.workers.celery_app import celery_app
    from app.workers.project_setup import run_project_guide_compilation

    assert run_project_guide_compilation.time_limit == 7_260
    assert run_project_guide_compilation.soft_time_limit is None
    assert run_project_guide_compilation.acks_late is True
    assert run_project_guide_compilation.acks_on_failure_or_timeout is True
    assert run_project_guide_compilation.reject_on_worker_lost is True
    assert celery_app.conf.worker_disable_prefetch is True
    assert celery_app.conf.visibility_timeout == 7_380
    assert celery_app.conf.broker_transport_options == {"visibility_timeout": 7_380}
    assert celery_app.conf.result_backend_transport_options == {
        "visibility_timeout": 7_380
    }


@pytest.mark.parametrize("pool", ("solo", "threads"))
def test_actual_inference_worker_startup_rejects_unsafe_pool(pool):
    from app.workers.celery_app import create_celery_app

    app = create_celery_app()
    try:
        with pytest.raises(WorkerShutdown, match="bounded Redis prefork"):
            app.Worker(pool=pool, queues=[topology.PROJECT_GUIDE_QUEUE])
        assert topology._validated_parent is None
    finally:
        app.close()


def test_prefork_hard_timeout_acknowledges_without_reinvocation(
    monkeypatch, tmp_path
):
    """A cancellation-resistant guide run is killed once and acknowledged."""
    import asyncio
    from threading import Event
    from uuid import uuid4

    from billiard.connection import wait
    from billiard.einfo import ExceptionWithTraceback
    from celery.concurrency.prefork import TaskPool
    from celery.exceptions import TimeLimitExceeded
    from celery.worker.request import Request
    from kombu.message import Message

    from app.workers import project_setup

    marker = tmp_path / "provider-invocations.txt"

    async def stubborn(_delivery):
        with marker.open("a", encoding="utf-8") as stream:
            stream.write("invoked\n")
        while True:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                continue

    monkeypatch.setattr(project_setup, "_run_project_guide_compilation", stubborn)
    monkeypatch.setattr(project_setup.run_project_guide_compilation, "time_limit", 5)
    monkeypatch.setattr(topology, "PROJECT_GUIDE_HARD_LIMIT_SECONDS", 5)
    monkeypatch.setattr(topology, "_validated_parent", os.getpid())
    acked = Event()
    rejected = []
    pool = TaskPool(
        1,
        app=project_setup.celery_app,
        initargs=(project_setup.celery_app, "guide-timeout-proof"),
    )
    pool.start()
    child = pool._pool._pool[0]
    try:
        task_id = str(uuid4())
        message = Message(
            headers={
                "id": task_id,
                "task": project_setup.run_project_guide_compilation.name,
            },
            properties={"correlation_id": task_id},
            body=(tuple(str(uuid4()) for _ in range(4)) + (1,), {}, {}),
        )
        request = Request(
            message,
            app=project_setup.celery_app,
            task=project_setup.run_project_guide_compilation,
            decoded=True,
            on_ack=lambda *_args: acked.set(),
            on_reject=lambda *args: rejected.append(args),
        )
        with pytest.raises(ExceptionWithTraceback) as timed_out:
            request.execute_using_pool(pool).get(timeout=15)
        assert isinstance(timed_out.value.exc, TimeLimitExceeded)
        assert acked.wait(3)
        assert rejected == []
        assert wait([child.sentinel], timeout=5)
    finally:
        processes = pool._pool
        pool.terminate()
        processes.join()
    assert marker.read_text(encoding="utf-8").splitlines() == ["invoked"]
