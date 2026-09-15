"""Observe real AUTH and product serialization before committing guide activation."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.auth_concurrency_support import wait_for_named_database_lock
from .pg_support import activation_case, activation_service


@pytest.mark.parametrize("operation", ["retire", "publish", "suspend_binding"])
async def test_activation_and_con_changes_serialize_with_exact_authority_blocker(
    clean_postgres_database,
    operation,
):
    async with activation_case(
        clean_postgres_database, compensated=operation == "suspend_binding"
    ) as (
        factory,
        command,
        actor,
        grant,
        world,
        policy,
    ):
        pending = policy
        if operation == "publish":
            for prepare in ("create_draft", "update_draft"):
                async with factory() as session, session.begin():
                    pending = await getattr(world.service(session), prepare)(
                        world.request(prepare, pending)
                    )
        entered, release = asyncio.Event(), asyncio.Event()
        pids = {}
        label = "cp07-" + operation + "-" + uuid4().hex
        tasks = []

        async def activate():
            async with factory() as session, session.begin():
                pids["activation"] = await session.scalar(text("select pg_backend_pid()"))
                service = activation_service(session, actor, command, grant)
                real = service.contribution

                class PausedValidation:
                    async def validate_for_activation(self, *args):
                        facts = await real.validate_for_activation(*args)
                        entered.set()
                        await asyncio.wait_for(release.wait(), 20)
                        return facts

                service.contribution = PausedValidation()
                return await service.activate(command, actor=actor, request_id=uuid4())

        async def contend():
            async with factory() as session, session.begin():
                await session.execute(
                    text("select set_config('application_name',:name,true)"), dict(name=label)
                )
                pids["contender"] = await session.scalar(text("select pg_backend_pid()"))
                if operation == "suspend_binding":
                    from app.adapters.auth import compensation_adapter_binding_authorization
                    from app.modules.compensation.api import AdapterBindingSuspendRequest
                    from app.modules.compensation.service import AdapterBindingService

                    authority = compensation_adapter_binding_authorization(session, world.context)
                    return await AdapterBindingService(
                        session, mutation_authorization=authority
                    ).suspend(
                        AdapterBindingSuspendRequest(
                            operation_id=uuid4(),
                            actor_profile_id=world.context.actor_profile_id,
                            project_id=world.project,
                            adapter_binding_id=world.binding,
                            expected_lifecycle_version=1,
                        )
                    )
                return await getattr(world.service(session), operation)(
                    world.request(operation, pending)
                )

        try:
            tasks.append(asyncio.create_task(activate()))
            await asyncio.wait_for(entered.wait(), 20)
            tasks.append(asyncio.create_task(contend()))
            while "contender" not in pids:
                await asyncio.sleep(0)
            await asyncio.wait_for(
                wait_for_named_database_lock(
                    clean_postgres_database,
                    label,
                    expected_waiter_pid=pids["contender"],
                    expected_blocker_pid=pids["activation"],
                ),
                10,
            )
            assert not tasks[1].done()
            release.set()
            receipt, _ = await asyncio.wait_for(asyncio.gather(*tasks), 30)
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        async with factory() as session, session.begin():
            assert (
                await activation_service(session, actor, command, grant).activate(
                    command, actor=actor, request_id=uuid4()
                )
                == receipt
            )


async def test_concurrent_exact_activation_deliveries_return_one_receipt(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):

        async def activate():
            async with factory() as session, session.begin():
                return await activation_service(session, actor, command, grant).activate(
                    command, actor=actor, request_id=uuid4()
                )

        receipts = await asyncio.wait_for(asyncio.gather(activate(), activate()), 30)
        assert receipts[0] == receipts[1]
        async with factory() as session:
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                    )
                )
                == 1
            )
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM project_guides WHERE status='active'")
                )
                == 1
            )
