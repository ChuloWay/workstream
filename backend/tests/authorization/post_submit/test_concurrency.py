"""Independent transactions serialize finalization against live service revocation."""

import asyncio

import pytest
from sqlalchemy import text

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.post_submit_authorization import _PreparedFinalize
from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from tests.checkers.execution.support import live_executor, reserve, service_link_state
from tests.checkers.execution.test_concurrency import final_facts
from tests.post_submit_materialization_helpers import material_fixture
from .test_receipt_custody import snapshot


@pytest.mark.parametrize("finalization_first", [True, False])
async def test_revocation_and_finalization_serialize(tmp_path, isolated_database_env, monkeypatch, finalization_first):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = live_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = final_facts(h, lease)
        before = await snapshot(h)
        held, release = asyncio.Event(), asyncio.Event()
        original = _PreparedFinalize.consume

        async def paused_consume(prepared, value):
            receipt = await original(prepared, value)
            held.set()
            await asyncio.wait_for(release.wait(), 10)
            return receipt

        async def revoke_while_held():
            async with h.factory() as session, session.begin():
                await session.execute(text("""UPDATE actor_identity_links SET status='revoked',
                    revoked_by='test', revoked_at=clock_timestamp(), revoked_reason='test'
                    WHERE actor_profile_id=(SELECT id FROM actor_profiles WHERE service_identity=:identity)"""),
                    {"identity": ServiceIdentity.CHECKER_POST_SUBMIT.value})
                held.set()
                await asyncio.wait_for(release.wait(), 10)

        if finalization_first:
            monkeypatch.setattr(_PreparedFinalize, "consume", paused_consume)
            first = asyncio.create_task(executor.finalize(facts))
        else:
            first = asyncio.create_task(revoke_while_held())
        second = None
        try:
            await asyncio.wait_for(held.wait(), 10)
            second = asyncio.create_task(
                service_link_state(h.factory, ServiceIdentity.CHECKER_POST_SUBMIT, active=False)
                if finalization_first else executor.finalize(facts)
            )
            blocked = False
            async with h.factory() as observer:
                for _ in range(100):
                    blocked = bool(await observer.scalar(text("""SELECT EXISTS (
                        SELECT 1 FROM pg_stat_activity WHERE datname=current_database()
                          AND pid<>pg_backend_pid() AND cardinality(pg_blocking_pids(pid))>0
                          AND query ILIKE '%actor_identity_links%')""")))
                    if blocked or second.done():
                        break
                    await asyncio.sleep(0.02)
            assert blocked and not second.done(), "competing authority operation did not wait on live principal custody"
            release.set()
            await asyncio.wait_for(first, 10)
            if finalization_first:
                await asyncio.wait_for(second, 10)
                after = await snapshot(h)
                assert after[0][0]["status"] == "completed"
                assert after[1] == before[1] + 1
                assert after[2] == len(h.request.policy.entries)
                assert after[3] == before[3] + 1
            else:
                with pytest.raises(CheckerExecutionUnavailable):
                    await asyncio.wait_for(second, 10)
                assert await snapshot(h) == before
            await service_link_state(h.factory, ServiceIdentity.CHECKER_POST_SUBMIT, active=True)
            assert await executor.finalize(facts) == facts.result
        finally:
            release.set()
            await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
