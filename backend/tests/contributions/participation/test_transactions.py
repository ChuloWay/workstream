"""Caller transaction, rollback, fence, and PostgreSQL winner proof."""

import asyncio
from contextlib import suppress

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.modules.reviews.api.lifecycle import JointLifecycleUnavailable
from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
from tests.contributions.records.support import contribution_source, rows
from tests.reviews.acceptance.support import insert_acceptance
from tests.reviews.packet.test_repository import wait_for_blocker

from .support import participant, request_for

async def test_later_sql_failure_rolls_back_acceptance_contribution_and_awards(
    tmp_path, isolated_database_env
):
    async with contribution_source(
        tmp_path, isolated_database_env, paid=True, persist_acceptance=False
    ) as h:
        request = request_for(h, correlation_id=new_record_id())
        async with h.factory() as session:
            with pytest.raises(DBAPIError, match="division by zero"):
                async with session.begin():
                    await PostgresJointLifecycleMutationFence(session).acquire(0)
                    await insert_acceptance(session, h.acceptance)
                    result = await participant(session).participate_submitter(request)
                    assert len(result.awards) == 2
                    await session.execute(text("SELECT 1 / 0"))
            await session.rollback()
        async with h.factory() as session:
            assert await rows(session, "final_acceptances") == []
            assert await rows(session, "contribution_records") == []
            assert await rows(session, "compensation_awards") == []


@pytest.mark.parametrize("commit_first", [True, False], ids=("commit-wins", "rollback-loses"))
async def test_concurrent_participants_converge_on_committed_winner_ids(
    tmp_path, isolated_database_env, commit_first
):
    async with contribution_source(tmp_path, isolated_database_env, paid=True) as h:
        request = request_for(h, correlation_id=new_record_id())
        ready = asyncio.Future()

        async def competitor():
            async with h.factory() as session:
                await session.begin()
                ready.set_result(await session.scalar(text("SELECT pg_backend_pid()")))
                try:
                    result = await participant(session).participate_submitter(request)
                    await session.commit()
                    return result
                except BaseException:
                    await session.rollback()
                    raise

        async with h.factory() as first_session:
            await first_session.begin()
            first = await participant(first_session).participate_submitter(request)
            pending = asyncio.create_task(competitor())
            try:
                await wait_for_blocker(h.factory, await ready)
                await (
                    first_session.commit() if commit_first else first_session.rollback()
                )
                winner = await asyncio.wait_for(pending, 10)
            finally:
                if not pending.done():
                    pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending

        if commit_first:
            assert winner == first
        else:
            assert winner.contribution.id != first.contribution.id
            assert {award.id for award in winner.awards}.isdisjoint(
                {award.id for award in first.awards}
            )
        async with h.factory() as session:
            stored_records = await rows(session, "contribution_records")
            stored_awards = await rows(session, "compensation_awards")
            assert [row["id"] for row in stored_records] == [
                str(winner.contribution.id)
            ]
            assert {row["id"] for row in stored_awards} == {
                str(award.id) for award in winner.awards
            }


async def test_canonical_fence_rejects_missing_and_savepoint_transactions(
    tmp_path, isolated_database_env
):
    async with contribution_source(tmp_path, isolated_database_env) as h:
        request = request_for(h, correlation_id=new_record_id())
        async with h.factory() as session:
            with pytest.raises(JointLifecycleUnavailable, match="root transaction"):
                await participant(session).participate_submitter(request)
            assert not session.in_transaction()

        async with h.factory() as session, session.begin():
            async with session.begin_nested():
                with pytest.raises(JointLifecycleUnavailable, match="root transaction"):
                    await participant(session).participate_submitter(request)

        async with h.factory() as session:
            await session.begin()
            await session.execute(text("SAVEPOINT caller_raw_savepoint"))
            with pytest.raises(
                JointLifecycleUnavailable, match="root database transaction"
            ):
                await participant(session).participate_submitter(request)
            await session.rollback()

        async with h.factory() as session, session.begin():
            result = await participant(session).participate_submitter(request)
            assert result.awards == ()
