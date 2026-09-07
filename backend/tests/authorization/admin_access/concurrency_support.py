"""Hold the actual owner lock until an independent observer sees the exact waiter."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db import session as db_session
from app.modules.actors.service import ActorService

from app.modules.authorization.repository import (
    AdminAuthorizationRepository,
    AuthorityIdempotencyRepository,
)
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.authorization.admin_access.read_support import read_path
from tests.authorization.admin_access.support import AdminAccess, SignedActor


@dataclass
class LockObservation:
    holder_pid: int | None = None
    waiter_pid: int | None = None
    observed: bool = False


async def ordered_owner_calls(
    first: Callable[[], Awaitable[Any]],
    second: Callable[[], Awaitable[Any]],
    *,
    boundary: str,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, Any, LockObservation]:
    """Run two named operations and propagate hook failures outside HTTP concealment."""
    assert boundary in {"control", "reservation"}
    owner, method = (
        (AdminAuthorizationRepository, "lock_control")
        if boundary == "control"
        else (AuthorityIdempotencyRepository, "reserve")
    )
    original = getattr(owner, method)
    held, waiter_ready = asyncio.Event(), asyncio.Event()
    identity = f"admin-race-{uuid4().hex}"
    observation = LockObservation()
    entered: set[str] = set()
    failures: list[Exception] = []
    tasks: list[asyncio.Task] = []

    async def hook(repository, *args, **kwargs):
        task = asyncio.current_task()
        assert task is not None
        name = task.get_name()
        if name not in {identity + "-holder", identity + "-waiter"} or name in entered:
            return await original(repository, *args, **kwargs)
        entered.add(name)
        try:
            if name.endswith("-holder"):
                observation.holder_pid = await repository._session.scalar(
                    text("select pg_backend_pid()")
                )
                result = await original(repository, *args, **kwargs)
                held.set()
                await waiter_ready.wait()
                assert observation.holder_pid != observation.waiter_pid
                await wait_for_named_database_lock(
                    database_url,
                    identity,
                    expected_waiter_pid=observation.waiter_pid,
                    expected_blocker_pid=observation.holder_pid,
                )
                observation.observed = True
                return result
            await held.wait()
            await repository._session.execute(
                text("select set_config('application_name', :name, true)"),
                {"name": identity},
            )
            observation.waiter_pid = await repository._session.scalar(
                text("select pg_backend_pid()")
            )
            waiter_ready.set()
            return await original(repository, *args, **kwargs)
        except Exception as exc:
            failures.append(exc)
            raise

    with monkeypatch.context() as patch:
        patch.setattr(owner, method, hook)
        try:
            tasks = [
                asyncio.create_task(first(), name=identity + "-holder"),
                asyncio.create_task(second(), name=identity + "-waiter"),
            ]
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=60)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if failures:
                raise AssertionError("actual owner lock observation failed") from failures[0]
    assert observation.observed, "both operations must reach the intended lock"
    assert observation.holder_pid is not None and observation.waiter_pid is not None
    return results[0], results[1], observation


async def apply_disabling_transition(
    access: AdminAccess,
    reader: SignedActor,
    grant_id: str,
    transition: str,
    capture: Callable[..., Awaitable[None]],
):
    """Grant uses HTTP; profile/link SQL proves row custody with triggers enabled."""
    if transition == "grant_revoked":
        return await access.signed.revoke(access.admin, grant_id)
    statements = {
        "suspended": "update actor_profiles set status='suspended',suspended_by=:by,"
        "suspended_at=clock_timestamp(),suspension_reason='race proof' where id=:actor",
        "deactivated": "update actor_profiles set status='deactivated',deactivated_by=:by,"
        "deactivated_at=clock_timestamp(),deactivation_reason='race proof' where id=:actor",
        "link_revoked": "update actor_identity_links set status='revoked',revoked_by=:by,"
        "revoked_at=clock_timestamp(),revoked_reason='race proof' where actor_profile_id=:actor",
    }
    async with db_session.get_session_factory()() as session:
        await capture(session)
        await session.execute(
            text(statements[transition]),
            {
                "actor": str(reader.id),
                "by": str(access.admin.id),
            },
        )
        await session.commit()


async def read_against_transition(
    access: AdminAccess,
    reader: SignedActor,
    grant_id: str,
    surface: str,
    transition: str,
    *,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, Any, LockObservation]:
    """Release disclosure only after its exact transaction blocks the transition."""
    identity = f"read-race-{uuid4().hex}"
    entered, release, waiter_ready = asyncio.Event(), asyncio.Event(), asyncio.Event()
    observation = LockObservation()
    tasks: list[asyncio.Task] = []
    failures: list[Exception] = []
    method = "read_admin_profile" if surface == "profile" else "read_admin_identity_link"
    original_read = getattr(ActorService, method)
    original_get_grant = AdminAuthorizationRepository.get_grant

    async def capture(session):
        if observation.waiter_pid is None:
            await session.execute(
                text("select set_config('application_name', :name, true)"), {"name": identity}
            )
            observation.waiter_pid = await session.scalar(text("select pg_backend_pid()"))
            waiter_ready.set()

    async def paused_read(service, target):
        observation.holder_pid = await service._session.scalar(text("select pg_backend_pid()"))
        entered.set()
        await release.wait()
        return await original_read(service, target)

    async def captured_grant(repository, *args, **kwargs):
        task = asyncio.current_task()
        if task is not None and task.get_name() == identity + "-transition":
            try:
                await capture(repository._session)
            except Exception as exc:
                failures.append(exc)
                raise
        return await original_get_grant(repository, *args, **kwargs)

    async def transition_after_read():
        await entered.wait()
        return await apply_disabling_transition(access, reader, grant_id, transition, capture)

    async def observe_then_release():
        await waiter_ready.wait()
        assert observation.holder_pid is not None and observation.waiter_pid is not None
        assert observation.holder_pid != observation.waiter_pid
        await wait_for_named_database_lock(
            database_url,
            identity,
            expected_waiter_pid=observation.waiter_pid,
            expected_blocker_pid=observation.holder_pid,
        )
        observation.observed = True
        release.set()

    with monkeypatch.context() as patch:
        patch.setattr(ActorService, method, paused_read)
        patch.setattr(AdminAuthorizationRepository, "get_grant", captured_grant)
        try:
            tasks = [
                asyncio.create_task(
                    access.signed.client.get(
                        read_path(access.target.id, surface),
                        headers=reader.headers,
                    ),
                    name=identity + "-reader",
                ),
                asyncio.create_task(transition_after_read(), name=identity + "-transition"),
                asyncio.create_task(observe_then_release(), name=identity + "-observer"),
            ]
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=60)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if failures:
                raise AssertionError("transition session capture failed") from failures[0]
    assert observation.observed
    return results[0], results[1], observation
