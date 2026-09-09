"""Bounded Celery delivery and retry behavior without provider or broker I/O."""

import asyncio
from uuid import uuid4

import pytest

from app.core.config import get_settings


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup

    monkeypatch.setattr(project_setup, "run_async_task", lambda factory: asyncio.run(factory()))
    yield project_setup
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "status",
    [
        "compilation_invalid_terminal",
        "provider_outcome_unresolved",
        "compilation_provider_uncertain",
        "policy_draft_ready",
        "delivery_rejected",
    ],
)
def test_terminal_delivery_never_requests_transport_retry(worker, monkeypatch, status):
    received = []

    async def run(delivery):
        received.append(delivery)
        return {"status": status}

    monkeypatch.setattr(worker, "_run_project_guide_compilation", run)

    def forbidden(**kwargs):
        pytest.fail("terminal delivery requested a retry")

    monkeypatch.setattr(worker.run_project_guide_compilation, "retry", forbidden)
    task_id = str(uuid4())
    arguments = [str(uuid4()) for _ in range(4)] + [1]
    worker.run_project_guide_compilation.push_request(id=task_id, retries=0)
    try:
        assert worker.run_project_guide_compilation.run(*arguments) == {"status": status}
    finally:
        worker.run_project_guide_compilation.pop_request()
    assert str(received[0].task_id) == task_id
    assert str(received[0].setup_run_id) == arguments[3]


def test_transient_delivery_uses_bounded_same_task_retry(worker, monkeypatch):
    async def run(delivery):
        return {"status": "compilation_unavailable"}

    monkeypatch.setattr(worker, "_run_project_guide_compilation", run)
    retries = []

    class Retried(Exception):
        pass

    def retry(**kwargs):
        retries.append(kwargs)
        return Retried()

    monkeypatch.setattr(worker.run_project_guide_compilation, "retry", retry)
    worker.run_project_guide_compilation.push_request(id=str(uuid4()), retries=1)
    try:
        with pytest.raises(Retried):
            worker.run_project_guide_compilation.run(*[str(uuid4()) for _ in range(4)], 1)
    finally:
        worker.run_project_guide_compilation.pop_request()
    assert retries[0]["max_retries"] == 3
    assert retries[0]["countdown"] == 60
    assert str(retries[0]["exc"]) == "project guide compilation unavailable"
    assert "task_id" not in retries[0] and "args" not in retries[0] and "kwargs" not in retries[0]


def test_missing_broker_task_id_rejects_before_execution(worker, monkeypatch):
    def forbidden(factory):
        pytest.fail("unbound task reached execution")

    monkeypatch.setattr(worker, "run_async_task", forbidden)
    worker.run_project_guide_compilation.push_request(id=None)
    try:
        assert worker.run_project_guide_compilation.run(*[str(uuid4()) for _ in range(4)], 1) == {
            "status": "delivery_rejected",
            "error_code": "invalid_compilation_delivery",
        }
    finally:
        worker.run_project_guide_compilation.pop_request()
