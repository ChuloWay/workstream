"""Real PostgreSQL proof of role issuance versus pre-submit execution lock order."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service import ResolvedActor
from app.modules.artifacts.authorization import PreparedPreSubmitMaterializationAuthorization
from app.modules.artifacts.models import PreSubmitEvidenceSet, PreSubmitExecutionAttempt
from app.core.api_controls import StructuredHTTPException
from app.modules.authorization import router as authorization_router
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.models import ProjectRoleGrant
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.project_role_schemas import ProjectRoleGrantIssueBody
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus,
)
from app.modules.authorization.schemas import AdminRole, ProjectRole
from project_create_fixtures import grant_fixture_admin_role
from tests.authorization.test_pre_submit_attempt_authority import _seed_materializer
from tests.test_pre_submit_attempt_authority_integration import _reserve_with_real_materializer
from tests.test_pre_submit_attempt_lock_order import (
    _PauseAfterProjectLock, _wait_for_project_block,
)
from tests.test_pre_submit_attempt_recovery import _harness


async def _seed_manager(harness) -> tuple[UUID, UUID]:
    actor_id, link_id = uuid4(), uuid4()
    project_id = harness.request.effective_plan.lineage.project_id
    async with harness.factory() as session:
        session.add_all([
            ActorProfile(
                id=str(actor_id), actor_kind="human", status="active",
                provisioning_method="automatic_first_access", created_by="test",
            ),
            ActorIdentityLink(
                id=str(link_id), actor_profile_id=str(actor_id), issuer="flow-test",
                subject=f"role-issue-{actor_id}", subject_kind="human",
                status="active", linked_by="test", last_verified_at=datetime.now(UTC),
            ),
        ])
        await session.flush()
        await grant_fixture_admin_role(
            session, actor_id, role=AdminRole.PROJECT_MANAGER.value,
            scope="project", project_id=project_id,
        )
        await session.commit()
    return actor_id, link_id


def _issue_body(target_actor_id: UUID) -> ProjectRoleGrantIssueBody:
    return ProjectRoleGrantIssueBody.model_validate({
        "target_actor_profile_id": target_actor_id,
        "role": "reviewer",
        "reason": "Concurrent project-role issue lock-order proof",
        "qualification": {
            "skills_snapshot": {
                "availability": "available", "reference_ids": ["skill:reviewer"],
                "unavailable_reason": None,
            },
            "reputation_snapshot": {
                "availability": "unavailable", "reference_ids": [],
                "unavailable_reason": "no_record",
            },
            "prior_project_work_refs": [], "external_expertise_refs": [],
        },
    })


async def _issue_runtime(session, actor_id: UUID, link_id: UUID):
    context = HumanAuthorizationContext(
        actor_profile_id=actor_id, actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE, identity_link_id=link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(), correlation_id=uuid4(),
    )
    repository = AdminAuthorizationRepository(session)
    authority = AuthorizationService(session, context, admin_repository=repository)
    prepared = PreparedAuthorizationService(session, context, authority, repository)
    profile = await session.get(ActorProfile, str(actor_id))
    link = await session.get(ActorIdentityLink, str(link_id))
    assert profile is not None and link is not None
    await session.commit()
    return prepared, ResolvedActor(profile, link)


async def _issue_role(session, project_id, body, issue_key, resolved, prepared):
    try:
        return await authorization_router.issue_project_role_grant(
            project_id=project_id, payload=body, idempotency_key=issue_key,
            resolved=resolved, prepared=prepared, session=session,
        )
    except BaseException:
        await session.rollback()
        raise


async def _assert_persisted_outcomes(harness, project_id, target_id, target_kind, issue_result):
    async with harness.factory() as session:
        assert await session.scalar(select(func.count()).select_from(PreSubmitEvidenceSet)) == 1
        attempts = (await session.scalars(select(PreSubmitExecutionAttempt))).all()
        assert len(attempts) == 1 and attempts[0].status == "completed"
        grants = (await session.scalars(select(ProjectRoleGrant).where(
            ProjectRoleGrant.project_id == str(project_id),
            ProjectRoleGrant.actor_profile_id == str(target_id),
            ProjectRoleGrant.role == "reviewer", ProjectRoleGrant.status == "active",
        ))).all()
        if target_kind == "contributor":
            assert len(grants) == 1 and grants[0].id == issue_result.id
        else:
            assert grants == []


def _sqlstate_cause(error: BaseException) -> str | None:
    cause: BaseException | None = error
    while cause is not None:
        original = getattr(cause, "orig", None)
        sqlstate = getattr(original, "sqlstate", None)
        if sqlstate is not None:
            return sqlstate
        cause = cause.__cause__
    return None


@pytest.mark.parametrize("target_kind", ["contributor", "materializer_service"])
@pytest.mark.asyncio
async def test_role_issue_and_pre_submit_execution_complete_without_project_contributor_deadlock(
    tmp_path: Path, isolated_database_env: str, monkeypatch, target_kind: str,
) -> None:
    import tests.test_default_pre_submit_execution as default_tests

    original_limits = default_tests._limits
    monkeypatch.setattr(default_tests, "_limits", lambda: replace(
        original_limits(), total_deadline_seconds=90, reservation_ttl_seconds=120,
        aggregate_reserved_bytes=4 * default_tests.HARD_MAXIMUM_ARTIFACT_BYTES,
    ))
    harness = await _harness(tmp_path, isolated_database_env)
    issue_engine = None
    execution_task = issue_task = None
    resume_project = asyncio.Event()
    try:
        manager_id, manager_link_id = await _seed_manager(harness)
        materializer_link_id = await _seed_materializer(harness.factory)
        target_id = harness.actor_id
        if target_kind == "materializer_service":
            async with harness.factory() as session:
                target_id = UUID(await session.scalar(select(
                    ActorIdentityLink.actor_profile_id,
                ).where(ActorIdentityLink.id == materializer_link_id)))
        application_name = f"pol07a_role_issue_{uuid4().hex[:12]}"
        issue_engine = create_async_engine(
            isolated_database_env,
            connect_args={"server_settings": {"application_name": application_name}},
        )
        issue_factory = async_sessionmaker(issue_engine, expire_on_commit=False)
        project_id = harness.request.effective_plan.lineage.project_id
        async with harness.factory() as execution_session, issue_factory() as issue_session:
            contributor_authority = harness.contributor_authority(execution_session)
            await contributor_authority.preflight(request=harness.preparation_request)
            async with execution_session.begin():
                await contributor_authority.revalidate(
                    request=harness.preparation_request, project_id=project_id,
                )
            materializer = PreparedPreSubmitMaterializationAuthorization(
                execution_session,
                request_id=harness.preparation_request.request_id,
                correlation_id=harness.preparation_request.correlation_id,
            )
            calls: list[int] = []
            workflow = harness.workflow(
                execution_session, calls, preparation_authorization=contributor_authority,
            )
            workflow._materialization._authorization = materializer
            prepared_issue, resolved_manager = await _issue_runtime(
                issue_session, manager_id, manager_link_id,
            )
            project_locked = asyncio.Event()
            try:
                reservation = await _reserve_with_real_materializer(
                    workflow, harness.request, harness.preparation_request,
                )
                paused_project = _PauseAfterProjectLock(
                    workflow._project_contexts, execution_session,
                    project_locked, resume_project,
                )
                workflow._project_contexts = paused_project
                execution_task = asyncio.create_task(workflow.execute_reserved(
                    harness.request, reservation,
                    preparation_request=harness.preparation_request,
                ))
                await asyncio.wait_for(project_locked.wait(), timeout=30)
                assert paused_project.backend_pid is not None
                issue_key = uuid4()
                body = _issue_body(target_id)
                issue_task = asyncio.create_task(_issue_role(
                    issue_session, project_id, body, issue_key,
                    resolved_manager, prepared_issue,
                ))
                await _wait_for_project_block(
                    harness.engine, application_name=application_name,
                    blocker_pid=paused_project.backend_pid,
                )
                resume_project.set()
                execution_result, issue_result = await asyncio.wait_for(
                    asyncio.gather(execution_task, issue_task, return_exceptions=True),
                    timeout=30,
                )
                assert not isinstance(execution_result, BaseException), execution_result
                assert execution_result.pass_capability is not None
                if target_kind == "contributor":
                    assert not isinstance(issue_result, BaseException), (
                        issue_result, _sqlstate_cause(issue_result)
                    )
                    assert issue_result.status == "active"
                    assert issue_result.role is ProjectRole.REVIEWER
                    assert issue_result.actor_profile_id == harness.actor_id
                    replay = await authorization_router.issue_project_role_grant(
                        project_id=project_id, payload=body, idempotency_key=issue_key,
                        resolved=resolved_manager, prepared=prepared_issue,
                        session=issue_session,
                    )
                    assert replay == issue_result
                else:
                    assert isinstance(issue_result, StructuredHTTPException), issue_result
                    assert issue_result.status_code == 404, _sqlstate_cause(issue_result)
                assert calls == [1]
            finally:
                resume_project.set()
                await asyncio.gather(
                    *(task for task in (execution_task, issue_task) if task is not None),
                    return_exceptions=True,
                )
                materializer.close()
                prepared_issue.close()
        await _assert_persisted_outcomes(
            harness, project_id, target_id, target_kind, issue_result,
        )
    finally:
        resume_project.set()
        await asyncio.gather(
            *(task for task in (execution_task, issue_task) if task is not None),
            return_exceptions=True,
        )
        if issue_engine is not None:
            await issue_engine.dispose()
        await harness.close()


async def _assert_target_rows_locked(harness, target_id, link_id):
    for model, row_id in ((ActorProfile, target_id), (ActorIdentityLink, link_id)):
        async with harness.factory() as observer:
            with pytest.raises(DBAPIError) as blocked:
                await observer.scalar(select(model).where(
                    model.id == str(row_id),
                ).with_for_update(nowait=True))
            assert blocked.value.orig.sqlstate == "55P03"
            await observer.rollback()


@pytest.mark.asyncio
async def test_target_created_after_prepare_is_locked_before_project(
    tmp_path: Path, isolated_database_env: str, monkeypatch,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    try:
        manager_id, manager_link_id = await _seed_manager(harness)
        project_id = harness.request.effective_plan.lineage.project_id
        target_id, target_link_id = uuid4(), uuid4()
        async with harness.factory() as session:
            prepared, resolved = await _issue_runtime(session, manager_id, manager_link_id)
            original_prepare = prepared.prepare
            original_lock_project = AdminAuthorizationRepository.lock_project
            project_probes = []

            async def prepare_then_create(*args, **kwargs):
                handle = await original_prepare(*args, **kwargs)
                async with harness.factory.begin() as creator:
                    creator.add_all([
                        ActorProfile(
                            id=str(target_id), actor_kind="human", status="active",
                            provisioning_method="automatic_first_access", created_by="test",
                        ),
                        ActorIdentityLink(
                            id=str(target_link_id), actor_profile_id=str(target_id),
                            issuer="flow-test", subject=f"late-target-{target_id}",
                            subject_kind="human", status="active", linked_by="test",
                            last_verified_at=datetime.now(UTC),
                        ),
                    ])
                return handle

            async def observe_project_lock(repository, requested_project_id):
                await _assert_target_rows_locked(harness, target_id, target_link_id)
                project_probes.append(requested_project_id)
                return await original_lock_project(repository, requested_project_id)

            monkeypatch.setattr(prepared, "prepare", prepare_then_create)
            monkeypatch.setattr(
                AdminAuthorizationRepository, "lock_project", observe_project_lock,
            )
            try:
                issued = await _issue_role(
                    session, project_id, _issue_body(target_id), uuid4(),
                    resolved, prepared,
                )
                assert issued.status == "active"
                assert issued.actor_profile_id == target_id
                assert project_probes == [project_id]
            finally:
                prepared.close()
        async with harness.factory() as session:
            assert await session.scalar(select(func.count()).select_from(
                ProjectRoleGrant,
            ).where(ProjectRoleGrant.actor_profile_id == str(target_id))) == 1
    finally:
        await harness.close()
