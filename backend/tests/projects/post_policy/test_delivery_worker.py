"""Transport failures, bounded scan progression and exact delivery admission."""

from uuid import UUID, uuid4

import pytest

from app.modules.projects.api.post_policy import PostPolicyDelivery, post_policy_task_id


def test_worker_rejects_wrong_task_identity_before_database(post_policy_worker, monkeypatch):
    def forbidden(*args):
        pytest.fail("invalid delivery reached async SQL work")
    monkeypatch.setattr(post_policy_worker, "run_async_task", forbidden)
    result = post_policy_worker.derive_post_policy.apply(args=(str(uuid4()),), task_id=str(uuid4()), throw=True).get()
    assert result == {"status":"delivery_rejected"}


@pytest.mark.parametrize("status", ["derivation_unavailable", "delivery_rejected", "policy_draft_ready"])
def test_only_transient_derivation_outcome_retries(post_policy_worker, monkeypatch, status):
    from celery.exceptions import Retry

    monkeypatch.setattr(post_policy_worker, "run_async_task", lambda fn: {"status":status})
    retries = []
    def retry(**kwargs):
        retries.append(kwargs)
        return Retry()
    monkeypatch.setattr(post_policy_worker.derive_post_policy, "retry", retry)
    operation = uuid4()
    if status == "derivation_unavailable":
        with pytest.raises(Retry):
            post_policy_worker.derive_post_policy.apply(args=(str(operation),), task_id=str(post_policy_task_id(operation)), throw=True).get()
        assert retries[0]["countdown"] == 30 and retries[0]["max_retries"] == 3
    else:
        assert post_policy_worker.derive_post_policy.apply(args=(str(operation),), task_id=str(post_policy_task_id(operation)), throw=True).get() == {"status":status}
        assert retries == []


async def test_queue_publishes_canonical_task_and_keeps_failure_recoverable(post_policy_worker, monkeypatch):
    from app.modules.projects.post_policy import queue

    captured = []
    monkeypatch.setattr(post_policy_worker.derive_post_policy, "apply_async", lambda **kwargs: captured.append(kwargs))
    operation = uuid4()
    assert await queue.dispatch_after_commit(operation) is True
    assert captured == [{"args":(str(operation),), "task_id":str(post_policy_task_id(operation))}]
    def unavailable(*args, **kwargs):
        raise OSError("isolated broker unavailable")
    monkeypatch.setattr(post_policy_worker.derive_post_policy, "apply_async", unavailable)
    assert await queue.dispatch_after_commit(operation) is False


async def test_scan_pages_advance_past_failed_candidate(post_policy_worker, monkeypatch):
    """Use the actual scheduler loop; only metadata selection and delivery are controlled."""
    monkeypatch.setattr(post_policy_worker, "get_database_url", lambda: "postgresql+asyncpg://unused/unused")
    first, second = UUID(int=1), UUID(int=2)
    selected, published, continuation = [], [], []
    async def candidates(factory, *, after, limit):
        selected.append((after, limit))
        return [first] if after is None else [second] if after == first else []
    async def publish(candidate):
        published.append(candidate)
        return candidate != first
    monkeypatch.setattr(post_policy_worker, "POST_POLICY_SCAN_PAGE_SIZE", 1)
    monkeypatch.setattr(post_policy_worker, "pending_post_policy_approvals", candidates)
    monkeypatch.setattr(post_policy_worker, "dispatch_post_policy_derivation_after_commit", publish)
    monkeypatch.setattr(post_policy_worker.scan_post_policy_approvals, "apply_async", lambda **kw: continuation.append(kw["args"][0]))
    initial = post_policy_worker.scan_post_policy_approvals.apply(throw=True).get()
    assert initial == {"selected":1, "published":0, "next_after":str(first)}
    assert continuation == [str(first)]
    later = post_policy_worker.scan_post_policy_approvals.apply(args=(continuation.pop(0),), throw=True).get()
    assert later == {"selected":1, "published":1, "next_after":str(second)}
    assert post_policy_worker.scan_post_policy_approvals.apply(args=(continuation.pop(0),), throw=True).get()["selected"] == 0
    assert selected == [(None, 1), (first, 1), (second, 1)]
    assert published == [first, second]
    # A scheduled sweep restarts at the beginning, allowing recovered candidates.
    post_policy_worker.scan_post_policy_approvals.apply(throw=True).get()
    assert published[-1] == first


def test_scan_rejects_invalid_cursor_before_database(post_policy_worker, monkeypatch):
    def forbidden(*args):
        pytest.fail("malformed scan reached SQL")
    monkeypatch.setattr(post_policy_worker, "run_async_task", forbidden)
    assert post_policy_worker.scan_post_policy_approvals.apply(args=("invalid",), throw=True).get() == {"status":"scan_rejected"}


def test_scan_continuation_publication_failure_retries(post_policy_worker, monkeypatch):
    from celery.exceptions import Retry

    monkeypatch.setattr(post_policy_worker, "run_async_task", lambda fn: {"selected":100, "published":100, "next_after":str(uuid4())})
    def unavailable(**kwargs):
        raise OSError("broker unavailable")
    retries = []
    def retry(**kwargs):
        retries.append(kwargs)
        return Retry()
    monkeypatch.setattr(post_policy_worker.scan_post_policy_approvals, "apply_async", unavailable)
    monkeypatch.setattr(post_policy_worker.scan_post_policy_approvals, "retry", retry)
    with pytest.raises(Retry):
        post_policy_worker.scan_post_policy_approvals.apply(throw=True).get()
    assert retries[0]["countdown"] == 30 and retries[0]["max_retries"] == 3


async def test_worker_disposes_engine_on_storage_failure(post_policy_worker, monkeypatch):
    monkeypatch.setattr(post_policy_worker, "get_database_url", lambda: "postgresql+asyncpg://unused/unused")
    events = []
    class Engine:
        async def dispose(self):
            events.append("disposed")
    class Port:
        async def run(self, delivery):
            raise OSError("private storage detail")
    monkeypatch.setattr(post_policy_worker, "create_async_engine", lambda *a, **kw: Engine())
    monkeypatch.setattr(post_policy_worker, "async_sessionmaker", lambda *a, **kw: object())
    monkeypatch.setattr(post_policy_worker, "project_post_policy_delivery_port", lambda *a, **kw: Port())
    operation = uuid4()
    result = await post_policy_worker._derive(PostPolicyDelivery(approval_operation_id=operation, task_id=post_policy_task_id(operation)))
    assert result == {"status":"derivation_unavailable"}
    assert events == ["disposed"]


def test_celery_registers_periodic_policy_recovery(post_policy_worker):
    conf = post_policy_worker.celery_app.conf
    assert "app.workers.post_policy" in conf.include
    assert conf.beat_schedule["post-policy-approval-recovery"] == {
        "task":"workstream.project_setup.scan_post_policy_approvals", "schedule":60.0,
    }
