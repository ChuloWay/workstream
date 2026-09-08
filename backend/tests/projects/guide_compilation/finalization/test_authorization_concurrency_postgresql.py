"""Independent-session finalization versus production actor/link revocation ordering."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api import ProjectGuideSetupFinalizationError
from app.modules.projects.guide_compilation.finalization import GuideCompilationFinalizationService
from tests.auth_concurrency_support import wait_for_named_database_lock
from .pg_authorization import ObservedAuthorization, concrete_finalize, revoke, seed_lifecycle_admin
from .pg_support import database_case, stored_state


@pytest.mark.parametrize("kind", ["actor", "link"])
@pytest.mark.parametrize("first", ["finalization", "revocation"])
async def test_finalization_and_revocation_serialize(clean_postgres_database, kind, first):
    async with database_case(clean_postgres_database) as (values, factory, command):
        # Both actor/link cases retain an actual non-revoked successful control.
        async with factory() as session:
            async with session.begin():
                await GuideCompilationFinalizationService(
                    session, ObservedAuthorization(session)
                ).finalize(command)
                await session.rollback()
        admin = await seed_lifecycle_admin(factory)
        held, release, second_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
        pids = {}
        waiter_name = "auth12b2-waiter-" + uuid4().hex
        second = "revocation" if first == "finalization" else "finalization"

        async def hold():
            held.set()
            await release.wait()

        async def run(name):
            if name != first:
                await held.wait()
            try:
                async with factory() as session, session.begin():
                    pids[name] = await session.scalar(text("select pg_backend_pid()"))
                    if name != first:
                        await session.execute(
                            text("select set_config('application_name', :name, true)"),
                            {"name": waiter_name},
                        )
                        second_started.set()
                    if name == "finalization":
                        authority = ObservedAuthorization(
                            session, after_prepare=hold if name == first else None
                        )
                        await GuideCompilationFinalizationService(session, authority).finalize(
                            command
                        )
                    else:
                        await revoke(session, admin, values, kind)
                        if name == first:
                            await hold()
                return "committed"
            except ProjectGuideSetupFinalizationError as exc:
                assert name == "finalization"
                assert exc.code == "service_authority_denied"
                return "denied"

        tasks = {
            name: asyncio.create_task(run(name), name="auth12b2-" + name)
            for name in (first, second)
        }
        try:
            await asyncio.wait_for(second_started.wait(), timeout=15)
            assert pids[first] != pids[second]
            await asyncio.wait_for(
                wait_for_named_database_lock(
                    clean_postgres_database,
                    waiter_name,
                    expected_waiter_pid=pids[second],
                    expected_blocker_pid=pids[first],
                ),
                timeout=15,
            )
            assert not tasks[second].done()
            release.set()
            results = await asyncio.wait_for(
                asyncio.gather(tasks[first], tasks[second]), timeout=30
            )
            assert results == (
                ["committed", "committed"] if first == "finalization" else ["committed", "denied"]
            )
        finally:
            release.set()
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        setup, receipt, count = await stored_state(factory, command)
        assert count == int(first == "finalization")
        assert (receipt is not None) == (first == "finalization")
        assert setup["status"] == ("policy_draft_ready" if first == "finalization" else "queued")
        with pytest.raises(ProjectGuideSetupFinalizationError, match="service_authority_denied"):
            await concrete_finalize(factory, command)
