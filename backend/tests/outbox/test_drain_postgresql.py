"""Nonlocking, project-exact single-snapshot observations with no false-zero recovery."""

from uuid import uuid4

import pytest
from sqlalchemy import text, event as sqlalchemy_event
from sqlalchemy.exc import SQLAlchemyError

from app.modules.outbox.api import DeliveryPersistenceError, DeliveryUnavailable, FinalizationCause, HandlerOutcome
from app.modules.outbox.delivery_repository import DeliveryRepository
from project_create_fixtures import seed_historical_project


async def test_drain_uses_one_snapshot_and_exact_project(delivery_harness):
    h = delivery_harness
    foreign = uuid4()
    async with h.factory() as session, session.begin():
        await seed_historical_project(
            session,
            project_id=str(foreign),
            name="Foreign outbox",
            slug=f"foreign-{foreign}",
            status="active",
        )
    await h.append(project_id=foreign, event_type="ForeignOnly")
    pending = await h.append()
    await h.append(event_type="Unregistered")
    retry = await h.claim()
    h.result = HandlerOutcome.RETRY
    await h.delivery.invoke(retry)
    invoked = await h.claim()
    await h.delivery._begin_invocation(invoked)
    unknown = await h.claim()
    await h.delivery._begin_invocation(unknown)
    await h.delivery.finalize(unknown, FinalizationCause.UNKNOWN)
    statements = []
    async with h.factory() as blocker, blocker.begin():
        await DeliveryRepository(blocker).event(pending.event_id, h.project, lock=True)
        bind = h.factory.kw["bind"].sync_engine

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        sqlalchemy_event.listen(bind, "before_cursor_execute", capture)
        try:
            observation = await h.delivery.drain(h.project)
        finally:
            sqlalchemy_event.remove(bind, "before_cursor_execute", capture)
    assert len(statements) == 1
    assert "FOR UPDATE" not in statements[0].upper()
    assert (observation.pending, observation.claimed, observation.retryable) == (2, 1, 1)
    assert (
        observation.invoked,
        observation.unresolved,
        observation.unsupported,
        observation.dead_letter,
    ) == (1, 1, 1, 1)
    assert observation.project_id == h.project
    other = await h.delivery.drain(foreign)
    assert other.pending == other.unsupported == 1
    assert other.invoked == other.unresolved == other.retryable == other.dead_letter == 0


async def test_drain_failure_never_returns_zero(delivery_harness, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    h = delivery_harness
    await h.append()

    async def failed(*args, **kwargs):
        raise SQLAlchemyError("private connection data")

    monkeypatch.setattr(AsyncSession, "execute", failed)
    with pytest.raises(DeliveryPersistenceError, match="^outbox_observation_failed$"):
        await h.delivery.drain(h.project)


async def test_candidates_are_bounded_nonlocking_selectors_with_expired_recovery(delivery_harness):
    from app.modules.outbox.registry import HandlerRegistry
    h = delivery_harness
    pending = [await h.append() for _ in range(3)]
    await h.append(event_type="Unsupported")
    expired = await h.claim()
    async with h.factory() as session:
        await session.execute(text("select pg_sleep(3.05)"))
    statements = []
    bind = h.factory.kw["bind"].sync_engine

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sqlalchemy_event.listen(bind, "before_cursor_execute", capture)
    try:
        first = await h.delivery.candidates(limit=2)
        second = await h.delivery.candidates(limit=2, after=first.next_after)
    finally:
        sqlalchemy_event.remove(bind, "before_cursor_execute", capture)
    expected = sorted([event.event_id for event in pending] + [expired.event_id])
    assert [item.event_id for item in first.items + second.items] == expected
    assert first.next_after == expected[1] and second.next_after is None
    assert {item.project_id for item in first.items + second.items} == {h.project}
    assert len(statements) == 2
    for statement in statements:
        selected = statement.split("FROM")[0].lower()
        assert "payload" not in selected and "claim_owner" not in selected
        assert "FOR UPDATE" not in statement
    # Removing a handler does not strand a committed claim needing recovery.
    empty = h.build(HandlerRegistry([]))
    page = await empty.candidates()
    assert [item.event_id for item in page.items] == [expired.event_id]
    assert await empty.deliver(expired.event_id, h.project, "recovery")
    assert (await empty.candidates()).items == ()
    assert h.handled == []


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 501}, {"limit": True}, {"after": "bad"}])
async def test_candidate_bounds_reject_before_database(delivery_harness, monkeypatch, kwargs):
    h = delivery_harness
    def forbidden():
        pytest.fail("invalid selector opened a session")
    monkeypatch.setattr(h.delivery, "_sessions", forbidden)
    with pytest.raises(DeliveryUnavailable):
        await h.delivery.candidates(**kwargs)
