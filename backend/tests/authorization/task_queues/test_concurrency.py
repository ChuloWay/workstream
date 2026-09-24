"""Real AUTH queue transactions serialize with revocation and guide activation."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import select, text

from app.db import session as db_session
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.task_queues import QueueReadResourceContext
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.models import AdminRoleGrant, AuthorityControl
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.authorization.runtime import AuthorizationDenied
from app.modules.tasks.api import TaskQueueRequest
from app.modules.tasks.repository import TaskRepository
from tests.authorization.guide_activation.pg_support import revoke_manager_grant, activate
from tests.authorization.task_authority.test_concurrency import actor_context
from tests.authorization.task_authority.test_management_concurrency import prepare_successor_activation
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.test_tasks import (
    task_database_env as task_database_env, task_client as task_client,
    create_active_project, create_draft_task,
)


def resource(project):
    return QueueReadResourceContext(resource_id=UUID(project), scope_project_id=UUID(project), request_digest="sha256:" + "a" * 64)


async def read(session, context, project):
    await AuthorizationService(session, context).require(ActionId.PROJECT_TASK_QUEUE_READ, resource(project))
    return await TaskRepository(session).read_management_tasks(TaskQueueRequest(UUID(project)))


@pytest.mark.parametrize("first", ["read", "revoke"])
async def test_queue_serializes_with_authority_revocation(task_client, task_database_env, first):
    project = await create_active_project(task_client)
    await create_draft_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor
    actor, grant_id = await seed_review_actor(factory, UUID(project["id"]))
    manager = await actor_context(str(actor.actor_profile_id))
    async with factory() as session:
        grants = list(await session.scalars(select(AdminRoleGrant).where(
            AdminRoleGrant.target_actor_profile_id == str(actor.actor_profile_id),
            AdminRoleGrant.status == "active",
        )))
        assert [row.id for row in grants] == [grant_id]
        bootstrap = await session.get(AuthorityControl, 1)
        admin_grant = await session.get(AdminRoleGrant, bootstrap.bootstrap_grant_id)
        admin_id = admin_grant.target_actor_profile_id
    administrator = await actor_context(admin_id)

    async def operation(name, session):
        if name == "read":
            return await read(session, manager, project["id"])
        return await revoke_manager_grant(session, administrator, grant_id)

    second = "revoke" if first == "read" else "read"
    async with factory() as owner:
        await operation(first, owner)
        async def waiter():
            async with factory() as session, session.begin():
                await session.execute(text("select set_config('application_name','queue-revocation-waiter',true)"))
                return await operation(second, session)
        waiting = asyncio.create_task(waiter())
        try:
            await asyncio.wait_for(wait_for_named_database_lock(task_database_env, "queue-revocation-waiter"), 10)
            assert not waiting.done()
        finally:
            await owner.commit()
        if second == "read":
            with pytest.raises(AuthorizationDenied):
                await asyncio.wait_for(waiting, 15)
        else:
            await asyncio.wait_for(waiting, 15)
    async with factory() as session:
        with pytest.raises(AuthorizationDenied):
            await read(session, manager, project["id"])


async def test_queue_serializes_with_guide_activation(task_client, task_database_env, monkeypatch):
    from app.modules.authorization.repository import AdminAuthorizationRepository

    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    manager = await actor_context(task["created_by"])
    factory = db_session.get_session_factory()
    _, command = await prepare_successor_activation(task_client, factory, project)
    actor = ActorIdentityFacts(manager.actor_profile_id, manager.identity_link_id, ActorKind.HUMAN)
    original = AdminAuthorizationRepository.lock_request_actor

    async def named(repository, *args, **kwargs):
        await repository._session.execute(text("select set_config('application_name','queue-activation-waiter',true)"))
        return await original(repository, *args, **kwargs)

    async with factory() as session:
        page = await read(session, manager, project["id"])
        assert [str(item.task_id) for item in page.items] == [task["id"]]
        monkeypatch.setattr(AdminAuthorizationRepository, "lock_request_actor", named)
        waiting = asyncio.create_task(activate(factory, actor, command))
        try:
            await asyncio.wait_for(wait_for_named_database_lock(task_database_env, "queue-activation-waiter"), 10)
            assert not waiting.done()
        finally:
            await session.commit()
        receipt = await asyncio.wait_for(waiting, 30)
        assert receipt.command == command
    async with factory() as session:
        assert [str(item.task_id) for item in (await read(session, manager, project["id"])).items] == [task["id"]]
