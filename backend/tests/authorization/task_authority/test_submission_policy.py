"""Real locked-policy rejection before hidden Submission persistence or ART access."""

from app.core.config import get_settings

from app.adapters.tasks import task_service, task_submission_context_port

from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from app.db import models as db_models
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.modules.projects.models import (
    PostSubmitCheckerPolicy,
)
from app.modules.authorization.prepared import PreparedSubmissionCreationAuthorization
from app.modules.tasks.api import SubmissionCreationRequest, TaskSubmissionContextUnavailable
from app.modules.tasks.models import AuditEvent, Submission, TaskAssignment, WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.service import TaskLockedContextInvalid
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from tests.authorization.task_authority.test_concurrency import actor_context
from tests.projects.policy_read_faults import corrupt_locked_policy_reads
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    create_active_project,
    create_started_task,
)


async def _create_hidden_submission(task_id: str):
    """Exercise real TASK/AUTH composition; invalid policy must precede ART lookup.

    The deliberately nonexistent admission cannot produce successful creation.
    If policy validation regresses, admission denial is a different failure and
    does not satisfy these tests' precise locked-policy error assertions.
    """
    async with db_session.get_session_factory()() as session:
        assignment = await session.scalar(select(TaskAssignment).where(
            TaskAssignment.task_id == task_id, TaskAssignment.status == "active",
        ))
        assert assignment is not None
        assignment_id = UUID(assignment.id)
        contributor_id = UUID(assignment.contributor_id)
    context = await actor_context(str(contributor_id))
    async with db_session.get_session_factory()() as session:
        command = compose_hidden_submission_creation_command(
            session, context, request_id=context.request_id, correlation_id=context.correlation_id,
        )
        return await command.create(SubmissionCreationRequest(
            task_id=UUID(task_id), assignment_id=assignment_id,
            contributor_id=contributor_id, admission_id=uuid4(),
            predecessor_submission_id=None, summary="Completed work",
            contributor_attestation="This submission is my work.",
        ))


@pytest.mark.parametrize("field", [
    "locked_post_submit_checker_policy_body",
    "locked_review_policy_hash",
    "locked_revision_policy_hash",
])
async def test_invalid_locked_policy_never_reaches_art_or_submission(
    task_client, monkeypatch, field,
):
    project = await create_active_project(task_client)
    task_response = await create_started_task(task_client, project["id"], monkeypatch)
    async with db_session.get_session_factory()() as session:
        assignment = await session.scalar(select(TaskAssignment).where(
            TaskAssignment.task_id == task_response["id"],
            TaskAssignment.status == "active",
        ))
        assignment_id = UUID(assignment.id)
        contributor_id = UUID(assignment.contributor_id)
    context = await actor_context(str(contributor_id))
    admissions = AsyncMock()
    admissions.consume.side_effect = AssertionError("invalid policy reached ART")

    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="task revision context lacks current preparation"):
            async with session.begin():
                task = await session.get(WorkstreamTask, task_response["id"])
                original = getattr(task, field)
                # A released TASK can change these locks only through its
                # authorized current revision preparation. This BEFORE UPDATE
                # guard precedes policy FK checks and any ART participation.
                setattr(task, field, {} if field.endswith("body") else "sha256:" + "f" * 64)
                await session.flush()
                await TaskSubmissionCreationService(
                    session,
                    authorization=PreparedSubmissionCreationAuthorization(session, context),
                    admissions=admissions, evaluations=AsyncMock(), events=AsyncMock(),
                    contexts=task_service(session, settings=get_settings()),
                    submission_contexts=task_submission_context_port(session),
                ).create(
                    SubmissionCreationRequest(
                        task_id=UUID(task.id),
                        assignment_id=assignment_id,
                        contributor_id=contributor_id,
                        admission_id=uuid4(),
                        predecessor_submission_id=None,
                        summary="Completed work",
                        contributor_attestation="This submission is my work.",
                    )
                )
        admissions.consume.assert_not_awaited()
        assert await session.scalar(select(Submission).where(
            Submission.task_id == task_response["id"],
        )) is None
        restored = await session.get(WorkstreamTask, task_response["id"])
        assert getattr(restored, field) == original
        assert restored.status == "in_progress"


async def test_submission_pre_submit_rejects_mutated_effective_policy_body(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await corrupt_locked_policy_reads(monkeypatch, started_task["id"], "stale_effective")

    with pytest.raises(TaskLockedContextInvalid) as rejected:
        await _create_hidden_submission(started_task["id"])
    assert rejected.value.status_code == 422
    assert rejected.value.code == "task_locked_context_invalid"
    assert str(rejected.value) == "task locked policy custody is invalid"

    async with db_session.get_session_factory()() as session:
        submissions = (
            (
                await session.execute(
                    select(Submission).where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_submission_rejects_malformed_locked_post_submit_policy_body_without_side_effects(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        corrupted_body = dict(task.locked_post_submit_checker_policy_body or {})
        corrupted_body["required_checkers"] = [
            "check_policy_context_present",
            "check_evidence_present",
        ]
        original_body = dict(task.locked_post_submit_checker_policy_body)

    original_get = TaskRepository.get_task

    async def corrupt_task_read(repository, task_id, **kwargs):
        task = await original_get(repository, task_id, **kwargs)
        if task is not None and task.id == started_task["id"]:
            # A detached storage fault exercises the read guard without editing
            # the locked row or disabling its current preparation guard.
            repository._session.expunge(task)
            task.locked_post_submit_checker_policy_body = dict(corrupted_body)
        return task

    monkeypatch.setattr(TaskRepository, "get_task", corrupt_task_read)

    with pytest.raises(TaskSubmissionContextUnavailable) as rejected:
        await _create_hidden_submission(started_task["id"])
    assert rejected.value.code == "task_submission_context_invalid"
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submissions = (
            (
                await session.execute(
                    select(Submission).where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        runs = (
            (
                await session.execute(
                    select(db_models.CheckerRun)
                    .join(Submission, db_models.CheckerRun.submission_id == Submission.id)
                    .where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        results = (
            (
                await session.execute(
                    select(db_models.CheckerResult)
                    .join(Submission, db_models.CheckerResult.submission_id == Submission.id)
                    .where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        audit_events = (
            (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.entity_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )

    assert task is not None
    assert task.status == "in_progress"
    assert task.locked_post_submit_checker_policy_body == original_body
    assert submissions == []
    assert runs == []
    assert results == []
    assert "submission_created" not in {event.event_type for event in audit_events}
    assert "submission_finalized" not in {event.event_type for event in audit_events}
    assert "checker_run_triggered" not in {event.event_type for event in audit_events}


async def test_submission_pre_submit_rejects_mutated_compiled_checker_bundle(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await corrupt_locked_policy_reads(monkeypatch, started_task["id"], "stale_bundle")

    with pytest.raises(TaskLockedContextInvalid) as rejected:
        await _create_hidden_submission(started_task["id"])
    assert rejected.value.status_code == 422
    assert rejected.value.code == "task_locked_context_invalid"
    assert str(rejected.value) == "task locked policy custody is invalid"

    async with db_session.get_session_factory()() as session:
        submissions = (
            (
                await session.execute(
                    select(Submission).where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_submission_rejects_crossed_post_submit_policy_sidecar(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        locked_body = dict(task.locked_post_submit_checker_policy_body or {})
        post_submit_policy = await session.get(
            PostSubmitCheckerPolicy,
            task.locked_post_submit_checker_policy_id,
        )
        assert post_submit_policy is not None
        policy_id = post_submit_policy.id
        audit_ids = sorted(await session.scalars(select(AuditEvent.id)))
        await session.commit()

    from tests.projects.post_submit_fixtures import crossed_post_policy_read

    with crossed_post_policy_read(policy_id) as seen:
        with pytest.raises(TaskLockedContextInvalid) as rejected:
            await _create_hidden_submission(started_task["id"])
    assert seen

    assert rejected.value.status_code == 422
    assert rejected.value.code == "task_locked_context_invalid"
    assert str(rejected.value) == "task locked policy custody is invalid"

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submissions = (
            (
                await session.execute(
                    select(Submission).where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
        assert sorted(await session.scalars(select(AuditEvent.id))) == audit_ids
    assert task is not None
    assert task.status == "in_progress"
    assert submissions == []
    assert task.locked_post_submit_checker_policy_body == locked_body

    assert checker_runs == []
