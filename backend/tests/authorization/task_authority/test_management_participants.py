"""Native canonical transitions compose and roll back in one caller-owned root."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.adapters.audit import task_transition_audit
from app.adapters.tasks import task_commands
from app.core.config import get_settings
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.tasks.api.authorization import TaskAuthorityOperation
from app.modules.tasks.models import AuditEvent, TaskCommandReceipt, WorkstreamTask
from app.modules.tasks.service import TaskValidationError
from tests.authorization.task_authority.test_concurrency import actor_context
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    create_active_project,
    create_draft_task,
)


async def manager_context():
    async with db_session.get_session_factory()() as session:
        actor_id = await session.scalar(select(ActorIdentityLink.actor_profile_id).where(
            ActorIdentityLink.subject == "project-manager-subject",
        ))
    return await actor_context(actor_id)


def commands(session, context):
    return task_commands(
        session, authorization=PreparedTaskAuthorization(session, context),
        audit=task_transition_audit(session), actor_profile_id=context.actor_profile_id,
        settings=get_settings(),
    )


@pytest.mark.parametrize("phase", ["authorize", "stage"])
async def test_transition_preparation_cannot_cross_roots(task_client, phase):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    context = await manager_context()
    async with db_session.get_session_factory()() as session:
        owner = commands(session, context)
        async with session.begin():
            prepared = await owner.prepare_transition(
                UUID(task["id"]), TaskAuthorityOperation.SCREEN, "Canonical screening",
                idempotency_key=uuid4(), project_id=UUID(project["id"]),
            )
            decision = await owner.authorize_transition(prepared)
            receipt_id = prepared.receipt.id
            await session.rollback()
        async with session.begin():
            with pytest.raises(RuntimeError, match="original caller transaction"):
                if phase == "authorize":
                    await owner.authorize_transition(prepared)
                else:
                    await owner.stage_transition(prepared, decision)
        async with session.begin():
            assert await session.get(TaskCommandReceipt, receipt_id) is None
            assert await session.get(AuditEvent, str(decision.decision_id)) is None
            current = await session.get(WorkstreamTask, task["id"])
            assert current.status == "draft" and current.locked_guide_version is None


async def test_transition_context_cannot_cross_roots(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    context = await manager_context()
    async with db_session.get_session_factory()() as session:
        owner = commands(session, context)
        async with session.begin():
            original = await owner.prepare_transition(
                UUID(task["id"]), TaskAuthorityOperation.SCREEN, "Canonical screening",
                idempotency_key=uuid4(), project_id=UUID(project["id"]),
            )
            await owner.authorize_transition(original)
            transition_context = await owner.prepare_transition_context(original)
            await session.rollback()
        async with session.begin():
            prepared = await owner.prepare_transition(
                UUID(task["id"]), TaskAuthorityOperation.SCREEN, "Canonical screening",
                idempotency_key=uuid4(), project_id=UUID(project["id"]),
            )
            decision = await owner.authorize_transition(prepared)
            with pytest.raises(RuntimeError, match="original caller transaction"):
                await owner.stage_transition(
                    prepared, decision, transition_context=transition_context,
                )
            await session.rollback()
        async with session.begin():
            current = await session.get(WorkstreamTask, task["id"])
            assert current.status == "draft" and current.locked_guide_version is None


async def test_transition_context_cannot_cross_projects(task_client):
    task_project = await create_active_project(task_client)
    other_project = await create_active_project(task_client)
    task = await create_draft_task(task_client, task_project["id"])
    other_task = await create_draft_task(task_client, other_project["id"])
    context = await manager_context()
    async with db_session.get_session_factory()() as session:
        owner = commands(session, context)
        async with session.begin():
            prepared = await owner.prepare_transition(
                UUID(task["id"]), TaskAuthorityOperation.SCREEN, "Canonical screening",
                idempotency_key=uuid4(), project_id=UUID(task_project["id"]),
            )
            decision = await owner.authorize_transition(prepared)
            other = await owner.prepare_transition(
                UUID(other_task["id"]), TaskAuthorityOperation.SCREEN, "Other screening",
                idempotency_key=uuid4(), project_id=UUID(other_project["id"]),
            )
            await owner.authorize_transition(other)
            transition_context = await owner.prepare_transition_context(other)
            with pytest.raises(TaskValidationError, match="transition context changed"):
                await owner.stage_transition(
                    prepared, decision, transition_context=transition_context,
                )
            await session.rollback()
        async with session.begin():
            current = await session.get(WorkstreamTask, task["id"])
            assert current.status == "draft" and current.locked_guide_version is None


async def test_release_context_refuses_changed_task_stamps(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    context = await manager_context()
    async with db_session.get_session_factory()() as session:
        owner = commands(session, context)
        async with session.begin():
            screened = await owner.prepare_transition(
                UUID(task["id"]), TaskAuthorityOperation.SCREEN, "Canonical screening",
                idempotency_key=uuid4(), project_id=UUID(project["id"]),
            )
            await owner.stage_transition(screened, await owner.authorize_transition(screened))
        async with session.begin():
            prepared = await owner.prepare_transition(
                UUID(task["id"]), TaskAuthorityOperation.RELEASE, "Canonical release",
                idempotency_key=uuid4(), project_id=UUID(project["id"]),
            )
            decision = await owner.authorize_transition(prepared)
            transition_context = await owner.prepare_transition_context(prepared)
            prepared.task.locked_post_submit_checker_policy_body = {"schema_version": "changed"}
            with pytest.raises(TaskValidationError, match="transition preparation changed"):
                await owner.stage_transition(
                    prepared, decision, transition_context=transition_context,
                )
            await session.rollback()
        async with session.begin():
            current = await session.get(WorkstreamTask, task["id"])
            assert current.status == "screening"


async def test_two_task_transition_late_failure_rolls_back_complete_root(task_client, monkeypatch):
    project = await create_active_project(task_client)
    tasks = [await create_draft_task(task_client, project["id"]) for _ in range(2)]
    context = await manager_context()
    async with db_session.get_session_factory()() as session:
        owner = commands(session, context)
        original = owner._record_management
        observed = []

        async def fail_after_second_audit(*args, **kwargs):
            await original(*args, **kwargs)
            observed.append(args[0].id)
            if len(observed) == 2:
                raise RuntimeError("second canonical transition staged")

        monkeypatch.setattr(owner, "_record_management", fail_after_second_audit)
        with pytest.raises(RuntimeError, match="second canonical transition staged"):
            async with session.begin():
                prepared = [await owner.prepare_transition(
                    UUID(task["id"]), TaskAuthorityOperation.SCREEN, "Complete batch",
                    idempotency_key=uuid4(), project_id=UUID(project["id"]),
                ) for task in sorted(tasks, key=lambda value: UUID(value["id"]).int)]
                decisions = [await owner.authorize_transition(value) for value in prepared]
                receipt_ids = [value.receipt.id for value in prepared]
                for value, decision in zip(prepared, decisions, strict=True):
                    await owner.stage_transition(value, decision)
        assert observed == [task["id"] for task in sorted(tasks, key=lambda value: UUID(value["id"]).int)]
        async with session.begin():
            for value in tasks:
                current = await session.get(WorkstreamTask, value["id"], populate_existing=True)
                assert current.status == "draft" and current.locked_guide_version is None
            assert not list(await session.scalars(select(TaskCommandReceipt.id).where(
                TaskCommandReceipt.id.in_(receipt_ids),
            )))
            assert not list(await session.scalars(select(AuditEvent.id).where(
                AuditEvent.id.in_([str(value.decision_id) for value in decisions]),
            )))
            assert not list(await session.scalars(select(AuditEvent.id).where(
                AuditEvent.entity_id.in_([value["id"] for value in tasks]),
                AuditEvent.event_type == "TaskScreened",
            )))
