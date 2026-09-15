"""Observe real AUTH locks throughout the complete activation transaction."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_proposals import GuideProposalError
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor
from tests.projects.guide_activation.pg_support import activation_case
from .pg_support import service, activate


@pytest.mark.parametrize("first", ["activate", "revoke"])
async def test_activation_and_revocation_serialize(clean_postgres_database, first):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        administrator, admin_grant = await seed_review_actor(
            factory, None, role="access_administrator", scope="system"
        )
        second = "revoke" if first == "activate" else "activate"
        held, started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        pids = {}
        waiter = "activation-revoke-" + uuid4().hex

        async def run(name):
            if name == second:
                await held.wait()
            try:
                async with service(factory, actor) as (session, owner, request, _):
                    pids[name] = await session.scalar(text("select pg_backend_pid()"))
                    if name == second:
                        await session.execute(
                            text("select set_config('application_name',:name,true)"),
                            {"name": waiter},
                        )
                        started.set()
                    if name == "activate":
                        await owner.activate(
                            command,
                            actor=actor,
                            request_id=request,
                        )
                    else:
                        await session.execute(
                            text(
                                "UPDATE admin_role_grants SET status='revoked',version=2,revoked_by_actor_profile_id=:actor,"
                                "revoked_by_admin_role_grant_id=:authorizer,revoked_at=now(),revoked_reason='Manager turnover' WHERE id=:id"
                            ),
                            {
                                "actor": str(administrator.actor_profile_id),
                                "authorizer": admin_grant,
                                "id": grant,
                            },
                        )
                    if name == first:
                        held.set()
                        await release.wait()
                return "committed"
            except GuideProposalError as exc:
                assert name == "activate" and exc.code == "authority_unavailable"
                return "denied"

        tasks = {name: asyncio.create_task(run(name)) for name in (first, second)}
        try:
            await asyncio.wait_for(started.wait(), timeout=15)
            assert pids[first] != pids[second]
            await asyncio.wait_for(
                wait_for_named_database_lock(
                    clean_postgres_database,
                    waiter,
                    expected_waiter_pid=pids[second],
                    expected_blocker_pid=pids[first],
                ),
                timeout=15,
            )
            assert not tasks[second].done()
            release.set()
            assert await asyncio.wait_for(
                asyncio.gather(tasks[first], tasks[second]), timeout=30
            ) == (["committed", "committed"] if first == "activate" else ["committed", "denied"])
        finally:
            release.set()
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        with pytest.raises(GuideProposalError, match="authority_unavailable"):
            await activate(factory, actor, command)


async def test_concurrent_activation_replays_once(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, _, _, _):
        held, started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        pids = {}
        waiter = "activation-replay-" + uuid4().hex

        async def run(index):
            if index:
                await held.wait()
            async with service(factory, actor) as (session, owner, request, _):
                pids[index] = await session.scalar(text("select pg_backend_pid()"))
                if index:
                    await session.execute(text("select set_config('application_name',:name,true)"), dict(name=waiter))
                    started.set()
                receipt = await owner.activate(command, actor=actor, request_id=request)
                if not index:
                    held.set()
                    await release.wait()
                return receipt

        tasks = [asyncio.create_task(run(i)) for i in range(2)]
        try:
            await asyncio.wait_for(started.wait(), timeout=15)
            assert pids[0] != pids[1]
            await asyncio.wait_for(wait_for_named_database_lock(
                clean_postgres_database, waiter,
                expected_waiter_pid=pids[1], expected_blocker_pid=pids[0],
            ), timeout=15)
            assert not tasks[1].done()
            release.set()
            first, second = await asyncio.wait_for(asyncio.gather(*tasks), timeout=30)
            assert first == second
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'")) == 1
            assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE action_id='project.guide.activate'")) == 1
