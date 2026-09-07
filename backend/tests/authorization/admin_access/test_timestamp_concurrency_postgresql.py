"""A delayed real observation cannot overwrite a newer committed observation."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.repository import ActorRepository
from tests.authorization.admin_access.support import (
    ActorObservation,
    AdminAccess,
    actor_observation,
    authority_events,
    seed_old_observation,
)


async def test_older_read_cannot_regress_committed_observation(
    admin_access: AdminAccess,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    before = await seed_old_observation(access.admin.id)
    older_entered, newer_committed = asyncio.Event(), asyncio.Event()
    identity = f"observations-{uuid4().hex}"
    newer_values: ActorObservation | None = None
    touch = ActorRepository.touch_verified_actor
    commit = AsyncSession.commit
    failures: list[Exception] = []
    tasks: list[asyncio.Task] = []

    async def delayed_touch(repository, profile, link):
        task = asyncio.current_task()
        if task is not None and task.get_name() == identity + "-older":
            older_entered.set()
            await newer_committed.wait()
        return await touch(repository, profile, link)

    async def observed_commit(session):
        nonlocal newer_values
        await commit(session)
        task = asyncio.current_task()
        if task is not None and task.get_name() == identity + "-newer":
            try:
                newer_values = await actor_observation(access.admin.id)
                newer_committed.set()
            except Exception as exc:
                failures.append(exc)
                raise

    async def request_after_older_enters():
        await older_entered.wait()
        return await access.signed.client.get(
            "/api/v1/authorization/permissions",
            headers=access.admin.headers,
        )

    with monkeypatch.context() as patch:
        patch.setattr(ActorRepository, "touch_verified_actor", delayed_touch)
        patch.setattr(AsyncSession, "commit", observed_commit)
        try:
            tasks = [
                asyncio.create_task(
                    access.signed.client.get(
                        "/api/v1/authorization/permissions",
                        headers=access.admin.headers,
                    ),
                    name=identity + "-older",
                ),
                asyncio.create_task(request_after_older_enters(), name=identity + "-newer"),
            ]
            responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=60)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if failures:
                raise AssertionError(
                    "newer committed observation could not be captured"
                ) from failures[0]
    assert [r.status_code for r in responses] == [200, 200]
    assert newer_values is not None
    after = await actor_observation(access.admin.id)
    assert after.last_seen_at > before.last_seen_at
    assert after.last_verified_at > before.last_verified_at
    assert after.last_seen_at >= newer_values.last_seen_at
    assert after.last_verified_at >= newer_values.last_verified_at
    events = await authority_events(
        action="authorization.permission_catalogue.read",
        event_type="SensitiveAuthorizationAllowed",
    )
    assert len(events) == 2
