# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalOperand=false
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db import session as db_session
from app.modules.actors.models import (
    ActorIdentityLink,
    ActorProfile,
)
from app.modules.actors.service import (
    ActorService,
)
from app.modules.audit.service import AuditService
from app.modules.tasks.models import AuditEvent
from app.schemas.auth import (
    actor_id_from_external_identity,
)

from tests.actors.support import ISSUER, verified_token
from tests.actors.first_access_support import (
    FirstAccessRace,
    event_views,
    expected_first_access_events,
)


async def test_first_human_access_atomically_creates_profile_link_and_events(
    actor_database_env: str,
) -> None:
    token = verified_token("first-human")
    request_id, correlation_id = uuid4(), uuid4()
    async with db_session.get_session_factory()() as session:
        resolved = await ActorService(session).resolve_verified_actor(
            token,
            request_id=request_id,
            correlation_id=correlation_id,
        )

    assert resolved.profile.id == actor_id_from_external_identity(ISSUER, token.subject)
    assert resolved.profile.actor_kind == "human"
    assert resolved.profile.status == "active"
    assert resolved.profile.provisioning_method == "automatic_first_access"
    assert resolved.identity_link.actor_profile_id == resolved.profile.id
    assert resolved.identity_link.subject_kind == "human"
    async with db_session.get_session_factory()() as session:
        events = (
            await session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_id.in_([resolved.profile.id, resolved.identity_link.id]))
                .order_by(AuditEvent.created_at, AuditEvent.id)
            )
        ).all()
        assert {event.event_type for event in events} == {
            "ActorProfileProvisioned",
            "ActorIdentityLinked",
        }
        assert len(events) == 2
        assert all(event.idempotency_reference is None for event in events)
        assert all(event.invalidation_cause_event_id is None for event in events)
        assert event_views(events) == expected_first_access_events(
            resolved.profile.id, resolved.identity_link.id, request_id, correlation_id
        )


async def test_concurrent_first_access_leaves_one_profile_link_and_event_pair(
    actor_database_env: str,
    monkeypatch,
) -> None:
    token = verified_token("concurrent-human")
    race = FirstAccessRace(monkeypatch, actor_database_env)
    provenance = {name: (uuid4(), uuid4()) for name in (race.holder, race.contender)}

    async def resolve(name):
        async with db_session.get_session_factory()() as session:
            return await ActorService(session).resolve_verified_actor(
                token,
                request_id=provenance[name][0],
                correlation_id=provenance[name][1],
            )

    tasks = [asyncio.create_task(resolve(name), name=name) for name in provenance]
    try:
        first, second = await asyncio.wait_for(asyncio.gather(*tasks), timeout=15)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert race.observed_exact_wait
    assert race.pids[race.holder] != race.pids[race.contender]
    assert race.lookups[race.holder] == [None, None]
    assert len(race.lookups[race.contender]) == 2
    assert race.lookups[race.contender][0] is None
    assert race.lookups[race.contender][1].profile.id == first.profile.id
    assert race.lookups[race.contender][1].identity_link.id == first.identity_link.id
    assert race.touches == [(race.contender, first.profile.id, first.identity_link.id)]
    assert first.profile.id == second.profile.id
    assert first.identity_link.id == second.identity_link.id
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 1
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type.in_(["ActorProfileProvisioned", "ActorIdentityLinked"])
                )
            )
            == 2
        )
        events = (await session.scalars(select(AuditEvent))).all()
        assert event_views(events) == expected_first_access_events(
            first.profile.id, first.identity_link.id, *provenance[race.holder]
        )


@pytest.fixture
async def repeated_actor(actor_database_env):
    token = verified_token("repeat-human")
    past = datetime(2000, 1, 1, tzinfo=UTC)
    async with db_session.get_session_factory()() as session:
        first = await ActorService(session).resolve_verified_actor(
            token,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        first.profile.last_seen_at = past
        first.identity_link.last_verified_at = past
        await session.commit()
    return token, first, past


async def test_repeated_verified_access_reuses_actor(repeated_actor):
    token, first, _past = repeated_actor
    async with db_session.get_session_factory()() as session:
        second = await ActorService(session).resolve_verified_actor(
            token,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )

    assert second.profile.id == first.profile.id
    assert second.identity_link.id == first.identity_link.id
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 1
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 1


async def test_repeated_verified_access_advances_persisted_timestamps(repeated_actor):
    token, first, past = repeated_actor
    assert first.profile.last_seen_at is not None
    assert first.identity_link.last_verified_at is not None
    async with db_session.get_session_factory()() as session:
        await ActorService(session).resolve_verified_actor(
            token,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, first.profile.id)
        link = await session.get(ActorIdentityLink, first.identity_link.id)
        assert profile.last_seen_at > past
        assert link.last_verified_at > past


async def test_first_access_rolls_back_profile_link_and_first_audit_on_second_audit_failure(
    actor_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = verified_token("audit-rollback-human")
    original = AuditService.add_authority_event
    calls = 0

    async def fail_second_event(self, value):
        nonlocal calls
        calls += 1
        if calls == 2:
            staged = self._repository._session
            assert await staged.scalar(select(func.count()).select_from(ActorProfile)) == 1
            assert await staged.scalar(select(func.count()).select_from(ActorIdentityLink)) == 1
            assert await staged.scalar(select(func.count()).select_from(AuditEvent)) == 1
            raise RuntimeError("injected audit failure")
        return await original(self, value)

    monkeypatch.setattr(AuditService, "add_authority_event", fail_second_event)
    async with db_session.get_session_factory()() as session:
        with pytest.raises(RuntimeError, match="injected audit failure"):
            await ActorService(session).resolve_verified_actor(
                token,
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
        await session.rollback()

    actor_id = actor_id_from_external_identity(ISSUER, token.subject)
    async with db_session.get_session_factory()() as session:
        assert await session.get(ActorProfile, actor_id) is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ActorIdentityLink)
                .where(ActorIdentityLink.actor_profile_id == actor_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.actor_id == actor_id)
            )
            == 0
        )
