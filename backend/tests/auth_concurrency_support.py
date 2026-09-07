"""AUTH test ordering and fresh PostgreSQL activity observation, not authority."""

import asyncio
from uuid import uuid4

from httpx import AsyncClient, Response
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.modules.authorization.repository import AdminAuthorizationRepository

OrderedRequest = tuple[str, str, dict[str, str], dict[str, str], str]


async def wait_for_named_database_lock(database_url: str, application_name: str) -> None:
    """Observe a late-named waiter without retaining a transaction activity snapshot."""
    engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            for _ in range(5000):
                waiting = await connection.scalar(
                    text(
                        "select exists(select 1 from pg_stat_activity where "
                        "application_name=:name and wait_event_type='Lock')"
                    ),
                    {"name": application_name},
                )
                if waiting:
                    return
                await asyncio.sleep(0)
    finally:
        await engine.dispose()
    raise AssertionError("ordered lifecycle request never reached the database lock")


async def ordered_control_requests(
    first_name: str,
    requests: tuple[OrderedRequest, OrderedRequest],
    *,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> tuple[tuple[str, Response], tuple[str, Response]]:
    """Order two real requests; preserve hook failures and finish owned tasks."""
    original_lock_control = AdminAuthorizationRepository.lock_control
    first_locked = asyncio.Event()
    waiter_name = f"auth-ordered-{uuid4().hex}"
    hook_failures: list[Exception] = []
    tasks: list[asyncio.Task] = []

    async def ordered_lock_control(repository):
        try:
            task = asyncio.current_task()
            assert task is not None, "an asyncio task is required"
            if task.get_name() == first_name:
                control = await original_lock_control(repository)
                first_locked.set()
                await asyncio.wait_for(
                    wait_for_named_database_lock(database_url, waiter_name), timeout=5
                )
                return control
            await first_locked.wait()
            await repository._session.execute(
                text("select set_config('application_name', :name, true)"),
                {"name": waiter_name},
            )
            return await original_lock_control(repository)
        except Exception as exc:
            hook_failures.append(exc)
            raise

    monkeypatch.setattr(AdminAuthorizationRepository, "lock_control", ordered_lock_control)
    try:
        tasks = [
            asyncio.create_task(
                client.post(path, headers={**headers, "Idempotency-Key": key}, json=body),
                name=name,
            )
            for name, path, headers, body, key in requests
        ]
        responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=60)
        return (requests[0][4], responses[0]), (requests[1][4], responses[1])
    finally:
        try:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            monkeypatch.setattr(AdminAuthorizationRepository, "lock_control", original_lock_control)
        if hook_failures:
            raise AssertionError("ordered AUTH lock hook failed") from hook_failures[0]
