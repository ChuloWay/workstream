"""Independent PostgreSQL sessions prove convergence after an observed lock wait."""

import asyncio

from sqlalchemy import text

from app.modules.projects.guide_compilation.finalization import GuideCompilationFinalizationService
from .pg_support import DatabaseAuthorization, database_case, finalize, stored_state


async def test_concurrent_identical_finalization_has_one_effect(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        first, second = await asyncio.gather(
            finalize(factory, values, command), finalize(factory, values, command)
        )
        assert first == second
        _, receipt, evidence = await stored_state(factory, command)
        assert receipt["id"] == first.finalization_id
        assert evidence == 1


async def test_concurrent_identical_finalization_rechecks_receipt_after_setup_lock(
    clean_postgres_database,
):
    async with database_case(clean_postgres_database) as (values, factory, command):
        winner_locked = asyncio.Event()
        release_winner = asyncio.Event()
        loser_started = asyncio.Event()
        pids = {}
        events = {"winner": [], "loser": []}

        async def before_consume():
            winner_locked.set()
            await asyncio.wait_for(release_winner.wait(), 20)

        async def call(name):
            async with factory() as session, session.begin():
                pids[name] = await session.scalar(text("select pg_backend_pid()"))
                if name == "loser":
                    loser_started.set()
                auth = DatabaseAuthorization(
                    session,
                    values,
                    events=events[name],
                    on_consume=before_consume if name == "winner" else None,
                )
                return await GuideCompilationFinalizationService(session, auth).finalize(command)

        winner = asyncio.create_task(call("winner"))
        loser = None
        try:
            await asyncio.wait_for(winner_locked.wait(), 20)
            loser = asyncio.create_task(call("loser"))
            await asyncio.wait_for(loser_started.wait(), 20)

            async def observe_wait():
                async with factory() as observer:
                    while True:
                        blockers = await observer.scalar(
                            text("select pg_blocking_pids(:pid)"), {"pid": pids["loser"]}
                        )
                        if pids["winner"] in blockers:
                            return blockers
                        await asyncio.sleep(0.02)

            blockers = await asyncio.wait_for(observe_wait(), 20)
            assert pids["winner"] in blockers
            assert not loser.done()
            assert events["loser"] == ["prepare"]
            release_winner.set()
            first, second = await asyncio.wait_for(asyncio.gather(winner, loser), 20)
            assert first == second
            assert events["winner"] == ["prepare", "consume", "close"]
            assert events["loser"] == ["prepare", "replay", "close"]
            assert (await stored_state(factory, command))[2] == 1
        finally:
            release_winner.set()
            for task in (winner, loser):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(
                *(task for task in (winner, loser) if task is not None), return_exceptions=True
            )
