"""Real AUTH queue transactions serialize with revocation and guide activation."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app.db import session as db_session
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.task_queues import QueueReadResourceContext
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.models import AdminRoleGrant, AuthorityControl
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


@pytest.mark.parametrize("remove_project_lock", [False, True])
async def test_queue_serializes_with_guide_activation(task_client, task_database_env, monkeypatch, remove_project_lock):
    from app.modules.authorization.repository import AdminAuthorizationRepository

    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    manager = await actor_context(task["created_by"])
    factory = db_session.get_session_factory()
    _, command = await prepare_successor_activation(task_client, factory, project)
    from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor
    actor, _ = await seed_review_actor(factory, UUID(project["id"]))
    assert actor.actor_profile_id != manager.actor_profile_id
    original = AdminAuthorizationRepository.lock_request_actor

    async def named(repository, *args, **kwargs):
        await repository._session.execute(text("select set_config('application_name','queue-activation-waiter',true)"))
        return await original(repository, *args, **kwargs)

    original_project = AdminAuthorizationRepository.lock_project

    async with factory() as session:
        async def unlocked_queue_project(repository, project_id):
            if repository._session is session:
                from app.modules.projects.models import Project
                return await session.scalar(select(Project).where(Project.id == str(project_id)))
            return await original_project(repository, project_id)

        if remove_project_lock:
            monkeypatch.setattr(AdminAuthorizationRepository, "lock_project", unlocked_queue_project)
        page = await read(session, manager, project["id"])
        assert [str(item.task_id) for item in page.items] == [task["id"]]
        monkeypatch.setattr(AdminAuthorizationRepository, "lock_request_actor", named)
        waiting = asyncio.create_task(activate(factory, actor, command))
        try:
            if remove_project_lock:
                # Removing only this reader's Project lock lets activation commit
                # while the queue transaction still holds its own actor/grant locks.
                await asyncio.wait_for(asyncio.shield(waiting), 30)
                with pytest.raises(AssertionError):
                    assert not waiting.done(), "activation must wait for the queue Project lock"
            else:
                await asyncio.wait_for(wait_for_named_database_lock(task_database_env, "queue-activation-waiter"), 10)
                assert not waiting.done(), "activation must wait for the queue Project lock"
        finally:
            await session.commit()
        receipt = await asyncio.wait_for(waiting, 30)
        assert receipt.command == command
    async with factory() as session:
        assert [str(item.task_id) for item in (await read(session, manager, project["id"])).items] == [task["id"]]


@pytest.mark.parametrize("first", ["read", "transition"])
@pytest.mark.parametrize("transition", ["project_grant", "profile"])
async def test_ready_queue_serializes_with_live_authority_change(
    admin_access, auth_database_env, monkeypatch, first, transition,
):
    """Two real HTTP operations retain locks until their root transaction commits."""
    from app.modules.authorization.project_role_service import ProjectRoleGrantMutationService
    from app.modules.authorization.lifecycle_service import ActorLifecycleService
    from tests.authorization.task_authority.test_postgresql import project_manager, grant
    from tests.authorization.task_queues.support import project_fixture, PATHS

    access = admin_access
    project = await project_fixture()
    manager = await project_manager(access, project)
    grant_id = await grant(access, manager, project)
    path = PATHS["ready"].format(project=project)
    client = access.signed.client
    assert (await client.get(path, headers=access.target.headers)).status_code == 200
    mutation_path, caller = (
        (f"/api/v1/projects/{project}/role-grants/{grant_id}/revoke", manager)
        if transition == "project_grant"
        else (f"/api/v1/actors/{access.target.id}/suspend", access.admin)
    )
    identity = "queue-live-" + uuid4().hex
    held, release = asyncio.Event(), asyncio.Event()
    pids = {}
    original_read = TaskRepository.read_ready_tasks
    owner, method = (
        (ProjectRoleGrantMutationService, "complete_revoke")
        if transition == "project_grant" else (ActorLifecycleService, "complete")
    )
    original_transition = getattr(owner, method)

    def named_transaction(session, transaction, connection):
        name = asyncio.current_task().get_name()
        if name in {identity + "-read", identity + "-transition"}:
            connection.execute(
                text("select set_config('application_name', :name, true)"), {"name": name},
            )
            pids[name] = connection.scalar(text("select pg_backend_pid()"))

    async def hold_first(name, result):
        if first == name:
            held.set()
            await release.wait()
        return result

    async def paused_read(repository, *args, **kwargs):
        return await hold_first("read", await original_read(repository, *args, **kwargs))

    async def paused_transition(service, *args, **kwargs):
        return await hold_first("transition", await original_transition(service, *args, **kwargs))

    async def invoke(name):
        if name == "read":
            return await client.get(path, headers=access.target.headers)
        return await client.post(
            mutation_path, headers=caller.headers | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Withdraw queue authority concurrently"},
        )

    second = "transition" if first == "read" else "read"
    tasks = []
    with monkeypatch.context() as patch:
        patch.setattr(TaskRepository, "read_ready_tasks", paused_read)
        patch.setattr(owner, method, paused_transition)
        event.listen(Session, "after_begin", named_transaction)
        try:
            tasks.append(asyncio.create_task(invoke(first), name=identity + "-" + first))
            await asyncio.wait_for(held.wait(), 30)
            tasks.append(asyncio.create_task(invoke(second), name=identity + "-" + second))
            await asyncio.wait_for(wait_for_named_database_lock(
                auth_database_env, identity + "-" + second,
                expected_blocker_pid=pids[identity + "-" + first],
            ), 15)
            assert not tasks[1].done()
            release.set()
            responses = await asyncio.wait_for(asyncio.gather(*tasks), 30)
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            event.remove(Session, "after_begin", named_transaction)
    results = dict(zip((first, second), responses, strict=True))
    assert results["transition"].status_code == 200, results["transition"].text
    assert results["read"].status_code == (200 if first == "read" else 404), results["read"].text
    assert (await client.get(path, headers=access.target.headers)).status_code == 404
    async with db_session.get_session_factory()() as session:
        from app.modules.actors.models import ActorProfile
        from app.modules.authorization.models import ProjectRoleGrant
        row = await session.get(ProjectRoleGrant if transition == "project_grant" else ActorProfile,
                                grant_id if transition == "project_grant" else str(access.target.id))
        assert row.status == ("revoked" if transition == "project_grant" else "suspended")
