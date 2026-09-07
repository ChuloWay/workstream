"""Real activity-snapshot regression and bounded AUTH harness diagnostics."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from httpx import Response
import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

import auth_concurrency_support as support


def requests():
    return (
        ("first", "/first", {}, {}, str(uuid4())),
        ("second", "/second", {}, {}, str(uuid4())),
    )


async def test_ordered_requests_preserves_observer_exception(monkeypatch):
    failure = AssertionError("observer exhausted its polls")
    original = AsyncMock(return_value=object())
    monkeypatch.setattr(support.AdminAuthorizationRepository, "lock_control", original)
    monkeypatch.setattr(support, "wait_for_named_database_lock", AsyncMock(side_effect=failure))

    async def post(*_, **__):
        repository = SimpleNamespace(_session=SimpleNamespace(execute=AsyncMock()))
        try:
            await support.AdminAuthorizationRepository.lock_control(repository)
            return Response(200)
        except Exception:
            # Model middleware's response conversion, not an authorization decision.
            return Response(500)

    with pytest.raises(AssertionError, match="ordered AUTH lock hook failed") as observed:
        await support.ordered_control_requests(
            "first",
            requests(),
            client=SimpleNamespace(post=post),
            monkeypatch=monkeypatch,
            database_url="unused-by-controlled-observer",
        )
    assert observed.value.__cause__ is failure
    assert support.AdminAuthorizationRepository.lock_control is original


async def test_ordered_requests_cleans_up_pending_task(monkeypatch):
    original = support.AdminAuthorizationRepository.lock_control
    second_entered = asyncio.Event()
    observations = []
    failure = RuntimeError("first request failed")

    async def post(path, **_):
        if path == "/first":
            await second_entered.wait()
            raise failure
        second_entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            observations.append(support.AdminAuthorizationRepository.lock_control is original)

    with pytest.raises(RuntimeError) as observed:
        await asyncio.wait_for(
            support.ordered_control_requests(
                "first",
                requests(),
                client=SimpleNamespace(post=post),
                monkeypatch=monkeypatch,
                database_url="unused-by-controlled-client",
            ),
            timeout=5,
        )
    assert observed.value is failure
    assert observations == [False]  # Waiter finished before the monkeypatch was restored.
    assert support.AdminAuthorizationRepository.lock_control is original


async def require_exact_blocker(connection, waiter_pid, blocker_pid):
    for _ in range(5000):
        blockers = await connection.scalar(
            text("select pg_blocking_pids(:pid)"), {"pid": waiter_pid}
        )
        if blockers == [blocker_pid]:
            return
        await asyncio.sleep(0)
    raise AssertionError("exact waiter never blocked on the expected holder")


@pytest.mark.parametrize("transaction_cached", [False, True], ids=["fresh", "cached-baseline"])
async def test_observer_detects_waiter_after_initial_miss(
    postgres_database_url, monkeypatch, transaction_cached
):
    first_probe = asyncio.Event()
    observer_engines = []

    def observed_engine(url, **options):
        assert options == {"isolation_level": "AUTOCOMMIT"}
        if transaction_cached:
            options = {}  # Reproduce the original helper's actual transaction mode.
        engine = create_async_engine(url, **options)
        observer_engines.append(engine)

        def after_query(_conn, _cursor, statement, *_):
            if "pg_stat_activity" in statement:
                first_probe.set()

        event.listen(engine.sync_engine, "after_cursor_execute", after_query)
        return engine

    monkeypatch.setattr(support, "create_async_engine", observed_engine)
    engine = create_async_engine(postgres_database_url)
    tasks = []
    name = f"auth-late-waiter-{uuid4().hex}"
    key = uuid4().int % (2**63)
    try:
        async with engine.connect() as blocker, engine.connect() as waiter:
            blocker_pid = await blocker.scalar(text("select pg_backend_pid()"))
            waiter_pid = await waiter.scalar(text("select pg_backend_pid()"))
            assert blocker_pid != waiter_pid
            await blocker.execute(text("select pg_advisory_xact_lock(:key)"), {"key": key})
            observer = asyncio.create_task(
                support.wait_for_named_database_lock(postgres_database_url, name)
            )
            tasks.append(observer)
            try:
                await asyncio.wait_for(first_probe.wait(), timeout=5)

                async def wait_on_lock():
                    await waiter.execute(
                        text("select set_config('application_name', :name, true)"), {"name": name}
                    )
                    await waiter.execute(text("select pg_advisory_xact_lock(:key)"), {"key": key})

                contender = asyncio.create_task(wait_on_lock())
                tasks.append(contender)
                await asyncio.wait_for(
                    require_exact_blocker(blocker, waiter_pid, blocker_pid), timeout=5
                )
                if transaction_cached:
                    with pytest.raises((AssertionError, TimeoutError)) as observed:
                        await asyncio.wait_for(observer, timeout=5)
                    if isinstance(observed.value, AssertionError):
                        assert (
                            str(observed.value)
                            == "ordered lifecycle request never reached the database lock"
                        )
                else:
                    await asyncio.wait_for(observer, timeout=5)
                assert not contender.done()  # Observation did not release the protected lock.
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await engine.dispose()
        for observer_engine in observer_engines:
            await observer_engine.dispose()
