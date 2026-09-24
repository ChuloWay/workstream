"""Manager readiness races using independent transactions and canonical AUTH."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db import session as db_session
from app.adapters.tasks import task_commands
from app.adapters.audit import task_transition_audit
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.tasks.api import TaskAuthorityDenied
from app.modules.tasks.models import AuditEvent, TaskCommandReceipt
from app.modules.tasks.schemas import TaskCreate, TaskResponse
from tests.authorization.task_authority.test_concurrency import actor_context
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    create_active_project,
    create_draft_task,
    complete_task_payload,
)


async def invoke(context, operation, target, key):
    async with db_session.get_session_factory()() as session:
        commands = task_commands(
            session,
            authorization=PreparedTaskAuthorization(session, context),
            audit=task_transition_audit(session),
            actor_profile_id=context.actor_profile_id,
            settings=get_settings(),
        )
        if operation == "create":
            return await commands.create_task(
                UUID(target), TaskCreate(**complete_task_payload()), idempotency_key=key
            )
        return await getattr(commands, operation)(
            UUID(target), "Manager decision", idempotency_key=key
        )


@pytest.mark.parametrize(
    "operation,same_key",
    [("create", True), ("screen", True), ("screen", False), ("release", True), ("release", False)],
)
async def test_competing_manager_commands_preserve_one_transition(task_client, operation, same_key):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    context = await actor_context(task["created_by"])
    if operation == "release":
        await invoke(context, "screen", task["id"], uuid4())
    target = project["id"] if operation == "create" else task["id"]
    key = uuid4()
    barrier = asyncio.Barrier(2)

    async def run(command_key):
        await barrier.wait()
        return await invoke(context, operation, target, command_key)

    outcomes = await asyncio.wait_for(
        asyncio.gather(run(key), run(key if same_key else uuid4()), return_exceptions=True), 30
    )
    successes = [item for item in outcomes if isinstance(item, TaskResponse)]
    assert len(successes) == (2 if same_key else 1), outcomes
    if same_key:
        assert successes[0] == successes[1]
    else:
        assert sum(isinstance(item, TaskAuthorityDenied) for item in outcomes) == 1
    task_id = successes[0].id
    async with db_session.get_session_factory()() as session:
        events = list(
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.entity_id == task_id,
                    AuditEvent.event_type
                    == {
                        "create": "TaskCreated",
                        "screen": "TaskScreened",
                        "release": "TaskReleased",
                    }[operation],
                )
            )
        )
        receipts = list(
            await session.scalars(
                select(TaskCommandReceipt).where(
                    TaskCommandReceipt.task_id == task_id,
                    TaskCommandReceipt.action_id == f"project.task.{operation}",
                )
            )
        )
        assert len(events) == len(receipts) == 1


@pytest.mark.parametrize("first", ["screen", "release"])
async def test_screen_and_release_follow_the_actual_lock_order(
    task_client, task_database_env, monkeypatch, first
):
    from contextvars import ContextVar
    from sqlalchemy import text
    from auth_concurrency_support import wait_for_named_database_lock
    from app.modules.tasks.repository import TaskRepository
    from app.modules.tasks.models import WorkstreamTask

    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    context = await actor_context(task["created_by"])
    owner = ContextVar("manager_operation")
    acquired, proceed = asyncio.Event(), asyncio.Event()
    original = TaskRepository.get_task

    async def lock(repo, task_id, *, for_update=False):
        result = await original(repo, task_id, for_update=for_update)
        if for_update and owner.get(None) == first and task_id == task["id"]:
            acquired.set()
            await proceed.wait()
        return result

    monkeypatch.setattr(TaskRepository, "get_task", lock)

    async def run(operation):
        owner.set(operation)
        async with db_session.get_session_factory()() as session:
            await session.execute(
                text("select set_config('application_name',:name,false)"),
                {"name": f"manager-{operation}"},
            )
            await session.commit()
            commands = task_commands(
                session,
                authorization=PreparedTaskAuthorization(session, context),
                audit=task_transition_audit(session),
                actor_profile_id=context.actor_profile_id,
                settings=get_settings(),
            )
            return await getattr(commands, operation)(
                UUID(task["id"]), "Manager decision", idempotency_key=uuid4()
            )

    first_run = asyncio.create_task(run(first))
    other = "release" if first == "screen" else "screen"
    other_run = None
    try:
        await asyncio.wait_for(acquired.wait(), 20)
        other_run = asyncio.create_task(run(other))
        await wait_for_named_database_lock(task_database_env, f"manager-{other}")
    finally:
        proceed.set()
        outcomes = await asyncio.wait_for(
            asyncio.gather(
                *(job for job in (first_run, other_run) if job is not None), return_exceptions=True
            ),
            30,
        )
    assert isinstance(outcomes[1], TaskResponse), outcomes
    assert isinstance(outcomes[0], TaskResponse if first == "screen" else TaskAuthorityDenied), (
        outcomes
    )
    async with db_session.get_session_factory()() as session:
        stored = await session.get(WorkstreamTask, task["id"])
        assert stored.status == ("ready" if first == "screen" else "screening")
        events = list(
            await session.scalars(
                select(AuditEvent.event_type)
                .where(AuditEvent.entity_id == task["id"])
                .order_by(AuditEvent.created_at)
            )
        )
        assert events == (
            ["TaskCreated", "TaskScreened", "TaskReleased"]
            if first == "screen"
            else ["TaskCreated", "TaskScreened"]
        )


@pytest.mark.parametrize("first", ["screen", "revoke"])
async def test_screening_serializes_with_real_manager_revocation(
    task_client, task_database_env, monkeypatch, first
):
    from sqlalchemy import text
    from auth_concurrency_support import wait_for_named_database_lock
    from app.modules.authorization.models import AdminRoleGrant, AuthorityControl
    from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
    from app.modules.tasks.models import WorkstreamTask
    from tests.authorization.guide_activation.pg_support import revoke_manager_grant

    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    manager = await actor_context(task["created_by"])
    async with db_session.get_session_factory()() as session:
        control = await session.get(AuthorityControl, 1)
        bootstrap = await session.get(AdminRoleGrant, control.bootstrap_grant_id)
        admin_id = bootstrap.target_actor_profile_id
        grants = list(
            await session.scalars(
                select(AdminRoleGrant.id).where(
                    AdminRoleGrant.target_actor_profile_id == task["created_by"],
                    AdminRoleGrant.role == "project_manager",
                    AdminRoleGrant.status == "active",
                )
            )
        )
    admin = await actor_context(admin_id)
    acquired, proceed = asyncio.Event(), asyncio.Event()
    original = AuthorizedTaskCommands._record_management

    async def hold_screen(owner, *args, **kwargs):
        await original(owner, *args, **kwargs)
        if first == "screen":
            acquired.set()
            await proceed.wait()

    monkeypatch.setattr(AuthorizedTaskCommands, "_record_management", hold_screen)

    async def run(operation):
        async with db_session.get_session_factory()() as session:
            await session.execute(
                text("select set_config('application_name',:name,false)"),
                {"name": f"manager-race-{operation}"},
            )
            await session.commit()
            if operation == "revoke":
                async with session.begin():
                    for grant_id in grants:
                        await revoke_manager_grant(session, admin, grant_id)
                    if first == "revoke":
                        acquired.set()
                        await proceed.wait()
                return "revoked"
            commands = task_commands(
                session,
                authorization=PreparedTaskAuthorization(session, manager),
                audit=task_transition_audit(session),
                actor_profile_id=manager.actor_profile_id,
                settings=get_settings(),
            )
            return await commands.screen(
                UUID(task["id"]), "Manager decision", idempotency_key=uuid4()
            )

    first_run = asyncio.create_task(run(first))
    second = "revoke" if first == "screen" else "screen"
    second_run = None
    try:
        await asyncio.wait_for(acquired.wait(), 25)
        second_run = asyncio.create_task(run(second))
        await wait_for_named_database_lock(task_database_env, f"manager-race-{second}")
    finally:
        proceed.set()
        outcomes = await asyncio.wait_for(
            asyncio.gather(
                *(job for job in (first_run, second_run) if job is not None), return_exceptions=True
            ),
            30,
        )
    assert outcomes[1 if first == "screen" else 0] == "revoked", outcomes
    result = outcomes[0 if first == "screen" else 1]
    assert isinstance(result, TaskResponse if first == "screen" else TaskAuthorityDenied), outcomes
    async with db_session.get_session_factory()() as session:
        stored = await session.get(WorkstreamTask, task["id"])
        assert stored.status == ("screening" if first == "screen" else "draft")
        receipts = list(
            await session.scalars(
                select(TaskCommandReceipt).where(
                    TaskCommandReceipt.task_id == task["id"],
                    TaskCommandReceipt.action_id == "project.task.screen",
                )
            )
        )
        assert len(receipts) == (1 if first == "screen" else 0)


async def prepare_successor_activation(task_client, factory, project):
    from app.modules.projects.api.post_policy import PostPolicyReceipt
    from app.modules.projects.models import ProjectGuide, PostSubmitCheckerPolicy
    from app.modules.projects.post_policy.models import PostPolicyOperation
    from tests.projects.guide_activation.pg_support import activation_command, publish_policy
    from tests.test_tasks import (
        auth_headers,
        complete_guide_payload,
        create_policy_bundle_for_guide,
    )

    successor = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload("v2"),
    )
    assert successor.status_code == 201, successor.text
    await create_policy_bundle_for_guide(task_client, project["id"], successor.json()["id"])
    async with factory() as session:
        operation = (
            await session.scalars(
                select(PostPolicyOperation)
                .join(
                    PostSubmitCheckerPolicy,
                    PostSubmitCheckerPolicy.approval_operation_id
                    == PostPolicyOperation.operation_id,
                )
                .where(
                    PostSubmitCheckerPolicy.guide_id == successor.json()["id"],
                    PostSubmitCheckerPolicy.lifecycle_status == "approved",
                )
            )
        ).one()
        approved = PostPolicyReceipt.model_validate(operation.receipt_json)
        previous = await session.scalar(
            select(ProjectGuide).where(
                ProjectGuide.project_id == project["id"], ProjectGuide.status == "active"
            )
        )
        predecessor = dict(
            expected_previous_active_guide_id=UUID(previous.id),
            expected_previous_active_guide_generation=previous.mutation_generation,
        )
    _, policy = await publish_policy(factory, UUID(project["id"]))
    command = (await activation_command(factory, approved, policy)).model_copy(update=predecessor)
    return successor.json()["id"], command


@pytest.mark.parametrize("first", ["screen", "activate"])
async def test_screening_serializes_with_real_guide_activation(
    task_client, task_database_env, monkeypatch, first
):
    from contextlib import asynccontextmanager
    from contextvars import ContextVar
    from sqlalchemy import text
    from auth_concurrency_support import wait_for_named_database_lock
    from app.modules.authorization.api import ActorIdentityFacts, ActorKind
    from app.modules.authorization.repository import AdminAuthorizationRepository
    from app.modules.projects.models import ProjectGuide
    from app.modules.tasks.models import WorkstreamTask
    from tests.authorization.guide_activation.pg_support import activate

    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    manager = await actor_context(task["created_by"])
    factory = db_session.get_session_factory()
    successor_id, command = await prepare_successor_activation(task_client, factory, project)
    actor = ActorIdentityFacts(manager.actor_profile_id, manager.identity_link_id, ActorKind.HUMAN)
    owner = ContextVar("manager_activation_operation")
    acquired, proceed = asyncio.Event(), asyncio.Event()
    original = AdminAuthorizationRepository.find_effective_grant

    async def hold_grant(repo, *args, **kwargs):
        result = await original(repo, *args, **kwargs)
        if owner.get(None) == first:
            acquired.set()
            await proceed.wait()
        return result

    monkeypatch.setattr(AdminAuthorizationRepository, "find_effective_grant", hold_grant)

    async def run(operation):
        owner.set(operation)

        @asynccontextmanager
        async def named_factory():
            async with factory() as session:
                await session.execute(
                    text("select set_config('application_name',:name,false)"),
                    {"name": f"guide-race-{operation}"},
                )
                await session.commit()
                yield session

        if operation == "activate":
            return await activate(named_factory, actor, command)
        async with named_factory() as session:
            commands = task_commands(
                session,
                authorization=PreparedTaskAuthorization(session, manager),
                audit=task_transition_audit(session),
                actor_profile_id=manager.actor_profile_id,
                settings=get_settings(),
            )
            return await commands.screen(
                UUID(task["id"]), "Manager screening", idempotency_key=uuid4()
            )

    first_run = asyncio.create_task(run(first))
    second = "activate" if first == "screen" else "screen"
    second_run = None
    try:
        await asyncio.wait_for(acquired.wait(), 25)
        second_run = asyncio.create_task(run(second))
        await wait_for_named_database_lock(task_database_env, f"guide-race-{second}")
    finally:
        proceed.set()
        outcomes = await asyncio.wait_for(
            asyncio.gather(
                *(job for job in (first_run, second_run) if job is not None), return_exceptions=True
            ),
            30,
        )
    assert len(outcomes) == 2 and not any(isinstance(item, BaseException) for item in outcomes), (
        outcomes
    )
    async with factory() as session:
        stored = await session.get(WorkstreamTask, task["id"])
        assert stored.status == "screening"
        assert stored.locked_guide_version == ("v1" if first == "screen" else "v2")
        assert (await session.get(ProjectGuide, successor_id)).status == "active"
