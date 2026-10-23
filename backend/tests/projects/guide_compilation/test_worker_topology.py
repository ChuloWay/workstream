"""Project-guide inference worker topology and timeout boundaries."""

from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import signal
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from celery.concurrency.prefork import TaskPool
from celery.concurrency.solo import TaskPool as SoloPool
from celery.exceptions import WorkerShutdown

from app.core.config import get_settings
from app.workers import project_setup_topology as topology


_REDIS_PROBE_TASK = "tests.project_guide_delivery_probe"


def _append_probe_event(marker: str, event: str, task_id: str) -> None:
    payload = (
        json.dumps(
            {
                "event": event,
                "task_id": task_id,
                "pid": os.getpid(),
                "time": time.monotonic(),
            },
            sort_keys=True,
        )
        + "\n"
    )
    descriptor = os.open(marker, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, payload.encode("utf-8"))
    finally:
        os.close(descriptor)


def _delivery_probe(marker: str, release: str, mode: str) -> None:
    from celery import current_task

    task_id = current_task.request.id
    _append_probe_event(marker, "started", task_id)
    if mode == "hold":
        deadline = time.monotonic() + 30
        while not Path(release).exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("delivery proof release was not observed")
            time.sleep(0.02)
    elif mode == "timeout":
        while True:
            time.sleep(60)
    _append_probe_event(marker, "finished", task_id)


def _redis_prefork_worker(app, hostname: str, marker: str, runtime: str) -> None:
    from celery.signals import task_received, worker_process_init

    os.setsid()
    os.environ["WORKSTREAM_PROJECT_AGENT_RUNTIME"] = runtime
    get_settings.cache_clear()
    topology._validated_parent = None

    @task_received.connect(weak=False)
    def received(request=None, **_kwargs):
        if request is not None and request.name == _REDIS_PROBE_TASK:
            _append_probe_event(marker, "received", request.id)

    @worker_process_init.connect(weak=False)
    def initialized(**_kwargs):
        _append_probe_event(marker, "child_ready", "")

    app.Worker(
        pool="prefork",
        concurrency=2,
        queues=[topology.PROJECT_GUIDE_QUEUE],
        hostname=hostname,
        loglevel="WARNING",
        without_gossip=True,
        without_mingle=True,
        without_heartbeat=True,
    ).start()


def _probe_events(marker: Path) -> list[dict[str, object]]:
    if not marker.exists():
        return []
    return [json.loads(line) for line in marker.read_text(encoding="utf-8").splitlines() if line]


def _wait_for_probe(marker: Path, predicate, *, timeout: float = 15) -> list[dict[str, object]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = _probe_events(marker)
        if predicate(events):
            return events
        time.sleep(0.05)
    events = _probe_events(marker)
    raise AssertionError(f"delivery proof timed out with events: {events}")


def _stop_prefork_worker(process: multiprocessing.Process) -> None:
    if process.is_alive():
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        process.join(5)
    if process.is_alive():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.join(5)


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
    assert celery_app.conf.result_backend_transport_options == {"visibility_timeout": 7_380}


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


def test_prefork_hard_timeout_acknowledges_without_reinvocation(monkeypatch, tmp_path):
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


@pytest.mark.skipif(
    "WORKSTREAM_TEST_BROKER_URL" not in os.environ,
    reason="real delivery proof requires the repository Redis test service",
)
def test_real_redis_prefork_bounds_reservation_and_timeout_redelivery(monkeypatch, tmp_path):
    """Prove the hosted Redis/prefork settings prevent stale reserved guides."""
    from celery import Celery
    import redis
    from urllib.parse import urlsplit, urlunsplit

    broker_parts = urlsplit(os.environ["WORKSTREAM_TEST_BROKER_URL"])
    broker = urlunsplit(broker_parts._replace(path="/15"))
    redis_client = redis.Redis.from_url(broker)
    assert redis_client.ping()
    redis_client.flushdb()
    context = multiprocessing.get_context("fork")

    def build_app(*, prefix: str | None, disable_prefetch: bool, visibility: int):
        app = Celery(f"guide-delivery-proof-{prefix}", broker=broker, backend=broker)
        broker_options = {"visibility_timeout": visibility}
        backend_options = {"visibility_timeout": visibility}
        if prefix is not None:
            broker_options["global_keyprefix"] = prefix
            backend_options["global_keyprefix"] = prefix
        app.conf.update(
            task_default_queue=topology.PROJECT_GUIDE_QUEUE,
            task_always_eager=False,
            task_acks_late=True,
            task_acks_on_failure_or_timeout=True,
            task_reject_on_worker_lost=True,
            worker_disable_prefetch=disable_prefetch,
            worker_prefetch_multiplier=4,
            broker_transport_options=broker_options,
            result_backend_transport_options=backend_options,
            visibility_timeout=visibility,
        )
        task = app.task(
            _delivery_probe,
            name=_REDIS_PROBE_TASK,
            acks_late=True,
            acks_on_failure_or_timeout=True,
            reject_on_worker_lost=True,
        )
        return app, task

    def start(app, marker: Path, runtime: str):
        hostname = f"guide-proof-{uuid4().hex}@localhost"
        process = context.Process(
            target=_redis_prefork_worker,
            args=(app, hostname, str(marker), runtime),
        )
        process.start()
        _wait_for_probe(
            marker,
            lambda events: sum(e["event"] == "child_ready" for e in events) >= 2,
        )
        return process

    # The deliberately unsafe control reserves a third task while both children
    # are busy. Once its one-second visibility expires, Kombu's real Redis
    # restore operation makes at least one still-running delivery available
    # again, discriminating the failure that the supported profile prevents.
    bad_prefix = f"guide-bad-{uuid4().hex}:"
    bad_marker = tmp_path / "bad.jsonl"
    bad_release = tmp_path / "bad.release"
    bad_app, bad_task = build_app(prefix=bad_prefix, disable_prefetch=False, visibility=1)
    bad_worker = start(bad_app, bad_marker, "manager_authored")
    bad_ids = [uuid4().hex for _ in range(3)]
    try:
        for task_id in bad_ids:
            bad_task.apply_async(
                (str(bad_marker), str(bad_release), "hold"),
                task_id=task_id,
                time_limit=20,
            )
        _wait_for_probe(
            bad_marker,
            lambda events: (
                sum(e["event"] == "started" for e in events) == 2
                and any(e["event"] == "received" and e["task_id"] == bad_ids[2] for e in events)
            ),
        )
        time.sleep(1.2)
        with bad_app.connection_for_read() as connection:
            connection.channel().qos.restore_visible(start=0, num=100, interval=1)
        _wait_for_probe(
            bad_marker,
            lambda events: any(
                sum(e["event"] == "received" and e["task_id"] == task_id for e in events) >= 2
                for task_id in bad_ids
            ),
        )
    finally:
        bad_release.touch()
        _stop_prefork_worker(bad_worker)
        bad_app.close()
        keys = redis_client.keys(f"{bad_prefix}*")
        if keys:
            redis_client.delete(*keys)

    # The supported profile uses the exact production ordering, scaled down to
    # seconds: visibility > graceful drain > hard task limit.
    hard_limit, drain, visibility = 3, 4, 5
    assert topology.CELERY_VISIBILITY_TIMEOUT_SECONDS > topology.PROJECT_GUIDE_DRAIN_SECONDS
    assert topology.PROJECT_GUIDE_DRAIN_SECONDS > topology.PROJECT_GUIDE_HARD_LIMIT_SECONDS
    assert visibility > drain > hard_limit
    monkeypatch.setattr(topology, "PROJECT_GUIDE_HARD_LIMIT_SECONDS", hard_limit)
    monkeypatch.setattr(topology, "CELERY_VISIBILITY_TIMEOUT_SECONDS", visibility)
    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", broker)
    get_settings.cache_clear()

    safe_marker = tmp_path / "safe.jsonl"
    safe_release = tmp_path / "safe.release"
    safe_app, safe_task = build_app(prefix=None, disable_prefetch=True, visibility=visibility)
    safe_worker = start(safe_app, safe_marker, "openai_agents_sdk")
    initial_children = {e["pid"] for e in _probe_events(safe_marker) if e["event"] == "child_ready"}
    held_ids = [uuid4().hex for _ in range(2)]
    timeout_id = uuid4().hex
    quick_id = uuid4().hex
    try:
        for task_id in held_ids:
            safe_task.apply_async(
                (str(safe_marker), str(safe_release), "hold"),
                task_id=task_id,
                time_limit=hard_limit,
            )
        safe_task.apply_async(
            (str(safe_marker), str(safe_release), "timeout"),
            task_id=timeout_id,
            time_limit=hard_limit,
        )
        _wait_for_probe(
            safe_marker,
            lambda events: all(
                any(e["event"] == "started" and e["task_id"] == task_id for e in events)
                for task_id in held_ids
            ),
        )
        time.sleep(0.75)
        assert not any(
            e["event"] == "received" and e["task_id"] == timeout_id
            for e in _probe_events(safe_marker)
        )

        safe_release.touch()
        timeout_events = _wait_for_probe(
            safe_marker,
            lambda events: any(
                e["event"] == "started" and e["task_id"] == timeout_id for e in events
            ),
        )
        timeout_pid = next(
            e["pid"]
            for e in timeout_events
            if e["event"] == "started" and e["task_id"] == timeout_id
        )
        _wait_for_probe(
            safe_marker,
            lambda events: any(
                e["event"] == "child_ready"
                and e["pid"] not in initial_children
                and e["pid"] != timeout_pid
                for e in events
            ),
            timeout=hard_limit + 10,
        )
        # Redis checks stale unacknowledged deliveries periodically. Waiting
        # beyond both the visibility window and its ten-poll restore cadence
        # proves the timeout acknowledgement prevents automatic reexecution.
        time.sleep(visibility + 6)
        before_quick = _probe_events(safe_marker)
        assert (
            sum(e["event"] == "received" and e["task_id"] == timeout_id for e in before_quick) == 1
        )
        assert (
            sum(e["event"] == "started" and e["task_id"] == timeout_id for e in before_quick) == 1
        )

        safe_task.apply_async(
            (str(safe_marker), str(safe_release), "quick"),
            task_id=quick_id,
            time_limit=hard_limit,
        )
        final_events = _wait_for_probe(
            safe_marker,
            lambda events: any(
                e["event"] == "finished" and e["task_id"] == quick_id for e in events
            ),
        )
        assert (
            sum(
                e["event"] == "started" and e["task_id"] == task_id
                for e in final_events
                for task_id in (*held_ids, timeout_id, quick_id)
            )
            == 4
        )
    finally:
        _stop_prefork_worker(safe_worker)
        safe_app.close()
        redis_client.flushdb()
