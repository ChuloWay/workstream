"""Real owner/AUTH operations meet at an observed PostgreSQL TASK row wait."""

import asyncio

import pytest

from sqlalchemy import select, func, text

from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.core.identifiers import new_record_id
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import Submission, SubmissionDispatch
from app.modules.tasks.repository import TaskRepository
from tests.post_submit_materialization_helpers import _material_fixture, _read_current_request


@pytest.mark.parametrize("different_admissions", [False, True])
async def test_concurrent_initial_creation_has_one_committed_dispatch(tmp_path, isolated_database_env, monkeypatch, different_admissions):
    held, release, contender_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    contender_pid = []
    original = TaskRepository.get_task

    async def pause_at_task(repository, *args, **kwargs):
        label = repository._session.info.pop("dispatch_contender", None)
        if label == "second":
            contender_pid.append(await repository._session.scalar(text("SELECT pg_catalog.pg_backend_pid()")))
            contender_entered.set()
        result = await original(repository, *args, **kwargs)
        if label == "first":
            held.set()
            await asyncio.wait_for(release.wait(), 15)
        return result

    async def competing_writer(factory, context, request):
        second_request = request
        if different_admissions:
            from dataclasses import replace
            from types import SimpleNamespace
            from uuid import UUID
            from app.modules.tasks.models import WorkstreamTask, TaskAssignment
            from app.modules.actors.models import ActorIdentityLink
            from tests.retained_material_fixtures import retained_admission
            async with factory() as session:
                task = await session.get(WorkstreamTask, str(request.task_id))
                assignment = await session.get(TaskAssignment, str(request.assignment_id))
                link = await session.get(ActorIdentityLink, str(context.identity_link_id))
                session.expunge_all()
            other = await retained_admission(factory, task, assignment, link,
                SimpleNamespace(summary=request.summary, worker_attestation=request.contributor_attestation), None)
            assert UUID(other) != request.admission_id
            second_request = replace(request, admission_id=UUID(other))
        async def create(label):
            async with factory() as session:
                session.info["dispatch_contender"] = label
                return await compose_hidden_submission_creation_command(
                    session, context, request_id=new_record_id(), correlation_id=new_record_id(),
                ).create(second_request if label == "second" else request)

        with monkeypatch.context() as patch:
            patch.setattr(TaskRepository, "get_task", pause_at_task)
            first = asyncio.create_task(create("first"))
            second = None
            try:
                await asyncio.wait_for(held.wait(), 15)
                second = asyncio.create_task(create("second"))
                await asyncio.wait_for(contender_entered.wait(), 15)
                async with factory() as observer:
                    async with asyncio.timeout(10):
                        while not await observer.scalar(text("SELECT cardinality(pg_catalog.pg_blocking_pids(:pid))>0"), {"pid": contender_pid[0]}):
                            await asyncio.sleep(.02)
                assert not second.done()
                release.set()
                results = await asyncio.wait_for(asyncio.gather(first, second, return_exceptions=True), 30)
                if different_admissions:
                    from app.modules.tasks.api import TaskSubmissionContextUnavailable
                    assert isinstance(results[1], TaskSubmissionContextUnavailable), results[1]
                else:
                    assert results[0] == results[1]
                assert not isinstance(results[0], BaseException), results[0]
                return results[0]
            finally:
                release.set()
                for task in (first, second):
                    if task is not None and not task.done():
                        task.cancel()
                await asyncio.gather(*(task for task in (first, second) if task is not None), return_exceptions=True)

    async with _material_fixture(tmp_path, isolated_database_env,
                                 write_submission=competing_writer, read_request=_read_current_request) as h:
        async with h.factory() as session:
            for owner in (Submission, SubmissionDispatch, CheckerRun, OutboxEvent):
                assert await session.scalar(select(func.count()).select_from(owner)) == 1


async def _role_race(tmp_path, database_url, monkeypatch, operation):
    from uuid import UUID
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from auth_concurrency_support import wait_for_named_database_lock
    from project_create_fixtures import grant_fixture_admin_role
    from app.modules.authorization import router
    from app.modules.authorization.models import ProjectRoleGrant
    from app.modules.authorization.project_role_schemas import ProjectRoleGrantRevokeBody
    from app.modules.authorization.submission_creation_authorization import PreparedSubmissionCreationAuthorization
    from app.modules.tasks.models import WorkstreamTask
    from tests.test_artifact_admission import _context, _seed_human_actor
    from tests.test_pre_submit_role_issue_lock_order import _issue_body, _issue_runtime

    async def writer(factory, context, request):
        manager = _context()
        async with factory.begin() as session:
            project_id = UUID((await session.get(WorkstreamTask, str(request.task_id))).project_id)
            grant_id = await session.scalar(select(ProjectRoleGrant.id).where(
                ProjectRoleGrant.project_id == str(project_id),
                ProjectRoleGrant.actor_profile_id == str(context.actor_profile_id),
                ProjectRoleGrant.role == "submitter", ProjectRoleGrant.status == "active",
            ))
            await _seed_human_actor(session, manager)
            await grant_fixture_admin_role(session, manager.actor_profile_id, role="project_manager",
                                           scope="project", project_id=project_id)
        held, release = asyncio.Event(), asyncio.Event()
        original = PreparedSubmissionCreationAuthorization.prepare
        async def pause_after_authority(self, facts):
            handle = await original(self, facts)
            held.set()
            await asyncio.wait_for(release.wait(), 30)
            return handle
        name = "dispatch-role-" + new_record_id().hex
        engine = create_async_engine(database_url, connect_args={"server_settings": {"application_name": name}})
        role_factory = async_sessionmaker(engine, expire_on_commit=False)
        async def create():
            async with factory() as session:
                return await compose_hidden_submission_creation_command(
                    session, context, request_id=new_record_id(), correlation_id=new_record_id(),
                ).create(request)
        async def mutate():
            async with role_factory() as session:
                prepared, resolved = await _issue_runtime(session, manager.actor_profile_id, manager.identity_link_id)
                if operation == "issue":
                    return await router.issue_project_role_grant(
                        project_id=project_id, payload=_issue_body(context.actor_profile_id),
                        idempotency_key=new_record_id(), resolved=resolved, prepared=prepared, session=session,
                    )
                return await router.revoke_project_role_grant(
                    project_id=project_id, grant_id=grant_id,
                    payload=ProjectRoleGrantRevokeBody(reason="Concurrent contribution authority revocation"),
                    idempotency_key=new_record_id(), resolved=resolved, prepared=prepared, session=session,
                )
        pending = []
        try:
            with monkeypatch.context() as patch:
                patch.setattr(PreparedSubmissionCreationAuthorization, "prepare", pause_after_authority)
                pending.append(asyncio.create_task(create()))
                await asyncio.wait_for(held.wait(), 30)
                pending.append(asyncio.create_task(mutate()))
                await asyncio.wait_for(wait_for_named_database_lock(database_url, name), 30)
                release.set()
                created, changed = await asyncio.wait_for(asyncio.gather(*pending), 45)
                assert changed.status == ("active" if operation == "issue" else "revoked")
                return created
        finally:
            release.set()
            for task in pending:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await engine.dispose()

    async with _material_fixture(tmp_path, database_url, write_submission=writer,
                                 read_request=_read_current_request) as h:
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1


async def test_role_issuance_serializes_with_submission_authority(tmp_path, isolated_database_env, monkeypatch):
    await _role_race(tmp_path, isolated_database_env, monkeypatch, "issue")


async def test_role_revocation_serializes_with_submission_authority(tmp_path, isolated_database_env, monkeypatch):
    await _role_race(tmp_path, isolated_database_env, monkeypatch, "revoke")
