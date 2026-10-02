"""Real independent-session locks, tested independently of one another."""

import asyncio
from contextlib import suppress

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import get_session_factory
from app.modules.reviews.api.lifecycle import JointLifecycleUnavailable
from app.modules.reviews.lifecycle.fence import (
    JOINT_LIFECYCLE_LOCK_KEY,
    PostgresJointLifecycleMutationFence,
)


async def test_fence_requires_root_transaction(clean_postgres_database):
    async with get_session_factory()() as session:
        fence = PostgresJointLifecycleMutationFence(session)
        with pytest.raises(JointLifecycleUnavailable, match="root transaction"):
            await fence.acquire(0)
        assert not session.in_transaction()
        async with session.begin():
            async with session.begin_nested():
                with pytest.raises(JointLifecycleUnavailable, match="root transaction"):
                    await fence.acquire(0)
            for invalid in (True, "0", -1, 2**63):
                with pytest.raises(JointLifecycleUnavailable, match="exact generation"):
                    await fence.acquire(invalid)
            facts = await fence.acquire(0)
            assert facts.generation == 0 and facts.phase == "disabled"
            assert session.in_transaction()
        assert not session.in_transaction()


async def test_fence_rejects_stale_generation(clean_postgres_database):
    async with get_session_factory()() as session:
        async with session.begin():
            with pytest.raises(JointLifecycleUnavailable, match="generation changed"):
                await PostgresJointLifecycleMutationFence(session).acquire(1)
            facts = await PostgresJointLifecycleMutationFence(session).acquire(0)
            assert facts.generation == 0


async def observe_advisory_wait(factory, pid, pending):
    async with factory() as observer:
        async with asyncio.timeout(5):
            while True:
                if pending.done():
                    await pending  # A setup exception is not the expected mutant failure.
                    raise AssertionError("advisory lock did not block")
                if await observer.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_locks "
                        "WHERE pid=:pid AND locktype='advisory' AND NOT granted)"
                    ),
                    {"pid": pid},
                ):
                    return
                await asyncio.sleep(0.01)


@pytest.mark.parametrize("remove_advisory", [False, True])
async def test_advisory_precedes_row_lock(clean_postgres_database, monkeypatch, remove_advisory):
    factory = get_session_factory()
    async with factory() as owner, factory() as contender:
        await owner.execute(
            text("SELECT pg_catalog.pg_advisory_xact_lock(:key)"), {"key": JOINT_LIFECYCLE_LOCK_KEY}
        )
        pid = await contender.scalar(text("SELECT pg_catalog.pg_backend_pid()"))
        real_execute = contender.execute
        removed = []
        if remove_advisory:

            async def without_advisory(statement, *args, **kwargs):
                if str(statement) == "SELECT pg_catalog.pg_advisory_xact_lock(:key)":
                    removed.append(True)
                    return None
                return await real_execute(statement, *args, **kwargs)

            monkeypatch.setattr(contender, "execute", without_advisory)
        pending = asyncio.create_task(PostgresJointLifecycleMutationFence(contender).acquire(0))
        try:
            if remove_advisory:
                with pytest.raises(AssertionError, match="advisory lock did not block"):
                    await observe_advisory_wait(factory, pid, pending)
                assert removed == [True]
            else:
                await observe_advisory_wait(factory, pid, pending)
                # The contender is waiting on advisory, not holding the row already.
                async with factory() as row_probe:
                    await row_probe.execute(
                        text(
                            "SELECT id FROM public.joint_lifecycle_release_control FOR UPDATE NOWAIT"
                        )
                    )
                    await row_probe.rollback()
            await owner.rollback()
            facts = await asyncio.wait_for(pending, 5)
            assert facts.generation == 0
            await contender.rollback()
        finally:
            await owner.rollback()
            if not pending.done():
                pending.cancel()
            with suppress(asyncio.CancelledError):
                await pending


@pytest.mark.parametrize("finish", ["commit", "rollback"])
async def test_caller_transaction_holds_and_releases_locks(clean_postgres_database, finish):
    factory = get_session_factory()
    async with factory() as owner:
        await owner.begin()
        facts = await PostgresJointLifecycleMutationFence(owner).acquire(0)
        # A detached return neither commits nor releases either lock.
        async with factory() as probe:
            assert not await probe.scalar(
                text("SELECT pg_catalog.pg_try_advisory_xact_lock(:key)"),
                {"key": JOINT_LIFECYCLE_LOCK_KEY},
            )
            with pytest.raises(DBAPIError, match="could not obtain lock"):
                await probe.execute(
                    text("SELECT id FROM public.joint_lifecycle_release_control FOR UPDATE NOWAIT")
                )
            await probe.rollback()
        await getattr(owner, finish)()
        async with factory() as probe:
            assert await probe.scalar(
                text("SELECT pg_catalog.pg_try_advisory_xact_lock(:key)"),
                {"key": JOINT_LIFECYCLE_LOCK_KEY},
            )
            assert (
                await probe.scalar(
                    text("SELECT id FROM public.joint_lifecycle_release_control FOR UPDATE NOWAIT")
                )
                == facts.singleton_id
            )
            assert (await PostgresJointLifecycleMutationFence(probe).acquire(0)) == facts


async def test_missing_controller_denies_and_stale_identity_map_is_not_used(
    clean_postgres_database,
):
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import set_committed_value

    from app.modules.reviews.lifecycle.models import JointLifecycleReleaseControl

    factory = get_session_factory()
    async with factory() as session:
        cached = await session.scalar(select(JointLifecycleReleaseControl))
        set_committed_value(cached, "generation", 3)
        set_committed_value(cached, "phase", "live")
        facts = await PostgresJointLifecycleMutationFence(session).acquire(0)
        assert facts.phase == "disabled" and facts.generation == 0
        # Isolated corruption fixture is transactional and never committed.
        await session.execute(
            text(
                "ALTER TABLE public.joint_lifecycle_release_control DISABLE TRIGGER joint_lifecycle_genesis_immutable"
            )
        )
        await session.execute(text("DELETE FROM public.joint_lifecycle_release_control"))
        with pytest.raises(JointLifecycleUnavailable, match="controller missing"):
            await PostgresJointLifecycleMutationFence(session).acquire(0)
        await session.rollback()
    async with factory() as session:
        await session.begin()
        assert await PostgresJointLifecycleMutationFence(session).acquire(0) == facts
