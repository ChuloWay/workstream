"""Execution-fence control flow and cleanup through passive connection ports."""

import asyncio
from types import SimpleNamespace

import pytest

from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.execution_fence_fixtures import fence_case as fence_case, open_fence


@pytest.mark.parametrize("acquired", [False, None, 1], ids=["busy", "null", "truthy-integer"])
async def test_unacquired_fence_never_enters_work(
    fence_case: SimpleNamespace, acquired: object,
) -> None:
    """Only literal True permits work; a non-owner never attempts unlock."""
    fence_case.connection.scalar.side_effect = None
    fence_case.connection.scalar.return_value = acquired

    with pytest.raises(fence_case.conflict, match="idempotency_pending"):
        async with open_fence(fence_case):
            pytest.fail("unacquired fence entered protected work")

    fence_case.connection.scalar.assert_awaited_once()
    fence_case.connection.execute.assert_not_awaited()
    assert fence_case.events == ["enter", "exit"]


async def test_acquisition_failure_propagates(fence_case: SimpleNamespace) -> None:
    """Acquisition exceptions cannot be converted to successful work or cleanup."""
    failure = RuntimeError("acquisition failed")
    fence_case.connection.scalar.side_effect = failure

    with pytest.raises(RuntimeError) as observed:
        async with open_fence(fence_case):
            pytest.fail("failed acquisition entered protected work")

    assert observed.value is failure
    fence_case.connection.execute.assert_not_awaited()
    assert fence_case.events == ["enter", "exit"]
    assert fence_case.connection.__aexit__.await_args.args[1] is failure


async def test_fence_releases_after_success(fence_case: SimpleNamespace) -> None:
    """Protected work is bracketed by acquisition and unlock on one connection."""
    async with open_fence(fence_case):
        fence_case.events.append("body")

    assert fence_case.events == ["enter", "acquire", "body", "unlock", "exit"]
    fence_case.engine.connect.assert_called_once_with()
    fence_case.connection.__aexit__.assert_awaited_once_with(None, None, None)


async def test_fence_releases_after_body_failure(fence_case: SimpleNamespace) -> None:
    """A body failure escapes unchanged only after the unlock attempt."""
    failure = RuntimeError("body failed")

    with pytest.raises(RuntimeError) as observed:
        async with open_fence(fence_case):
            fence_case.events.append("body")
            raise failure

    assert observed.value is failure
    assert fence_case.events == ["enter", "acquire", "body", "unlock", "exit"]
    assert fence_case.connection.__aexit__.await_args.args[1] is failure


async def test_fence_releases_after_body_cancellation(fence_case: SimpleNamespace) -> None:
    """Cancel an actual task inside work; cleanup precedes cancellation escape."""
    entered = asyncio.Event()
    blocked = asyncio.Event()
    cancellation = []

    async def work():
        async with open_fence(fence_case):
            fence_case.events.append("body")
            entered.set()
            try:
                await blocked.wait()
            except asyncio.CancelledError as exc:
                cancellation.append(exc)
                raise

    task = asyncio.create_task(work())
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError) as observed:
            await asyncio.wait_for(task, timeout=5)
        assert observed.value is cancellation[0]
        assert fence_case.events == ["enter", "acquire", "body", "unlock", "exit"]
        assert fence_case.connection.__aexit__.await_args.args[1] is observed.value
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_unlock_failure_propagates(fence_case: SimpleNamespace) -> None:
    """Unlock failure escapes, while the connection context still attempts exit."""
    failure = RuntimeError("unlock failed")
    fence_case.connection.execute.side_effect = failure

    with pytest.raises(RuntimeError) as observed:
        async with open_fence(fence_case):
            fence_case.events.append("body")

    assert observed.value is failure
    fence_case.connection.execute.assert_awaited_once()
    assert fence_case.events == ["enter", "acquire", "body", "exit"]
    assert fence_case.connection.__aexit__.await_args.args[1] is failure
