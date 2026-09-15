"""Real PostgreSQL ordering across policy, role, binding and intake owners."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.auth import (
    compensation_adapter_binding_authorization, contribution_policy_authorization,
)
from app.adapters.contributions import contribution_policy_service, contribution_policy_validation_port
from app.db import session as db_session
from app.modules.artifacts.models import PreSubmitEvidenceSet
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus,
)
from app.modules.compensation.api import AdapterBindingSuspendRequest
from app.modules.compensation.service import AdapterBindingService
from app.modules.contributions.api import (
    ContributionPolicyCreateDraftRequest, ContributionPolicyValidationPurpose,
    ContributionPolicyValidationRequest,
)
from app.modules.projects.contribution_policy import ProjectContributionPolicyEligibility
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.authorization.contribution_policies.postgresql_support import world
from tests.authorization.contribution_policies.test_selected_validation_postgresql import (
    published_world,
)
from tests.authorization.test_pre_submit_attempt_authority import _seed_materializer
from tests.test_pre_submit_attempt_authority_integration import _reserve_with_real_materializer
from tests.test_pre_submit_attempt_recovery import _harness
from tests.test_pre_submit_related_lock_order import (
    _PauseBeforeProject, _assert_row_locked, _ready_workflow,
)
from project_create_fixtures import grant_fixture_admin_role


def _role_body(target_id: UUID) -> dict:
    return {
        "target_actor_profile_id": str(target_id), "role": "submitter",
        "reason": "Concurrent policy authority lock proof",
        "qualification": {
            "skills_snapshot": {
                "availability": "unavailable", "reference_ids": [],
                "unavailable_reason": "no_record",
            },
            "reputation_snapshot": {
                "availability": "unavailable", "reference_ids": [],
                "unavailable_reason": "no_record",
            },
            "prior_project_work_refs": [], "external_expertise_refs": [],
        },
    }


async def _manager(access, project_id):
    manager = await access.signed.actor("cp07a-manager")
    await access.signed.grant(
        access.admin, manager, role="project_manager", project_id=project_id,
    )
    return manager


async def _issue_role(access, manager, project_id, target_id):
    return await access.signed.client.post(
        f"/api/v1/projects/{project_id}/role-grants",
        headers=manager.headers | {"Idempotency-Key": str(uuid4())},
        json=_role_body(target_id),
    )


def _observed_lock_hooks(monkeypatch, *, names):
    """Tag actual second/third backends at Control before they can block."""
    original = AdminAuthorizationRepository.lock_control
    pids: dict[str, int] = {}
    entered = {name: asyncio.Event() for name in names}

    async def hook(repository):
        name = asyncio.current_task().get_name()
        if name in names:
            pids[name] = int(await repository._session.scalar(text("select pg_backend_pid()")))
            await repository._session.execute(text(
                "select set_config('application_name', :name, true)"
            ), {"name": names[name]})
            entered[name].set()
        return await original(repository)

    monkeypatch.setattr(AdminAuthorizationRepository, "lock_control", hook)
    return pids, entered


async def _wait_edge(database_url, label, waiter_pid, blocker_pid):
    await asyncio.wait_for(wait_for_named_database_lock(
        database_url, label, expected_waiter_pid=waiter_pid,
        expected_blocker_pid=blocker_pid,
    ), timeout=20)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["publish", "retire"])
async def test_role_issue_waits_for_policy_publication_or_retirement(
    admin_access, auth_database_env, monkeypatch, operation,
) -> None:
    target = await world(admin_access)
    manager = await _manager(admin_access, target.project)
    prior = await target.execute("create_draft", target.request("create_draft"))
    prior = await target.execute("update_draft", target.request("update_draft", prior))
    if operation == "retire":
        prior = await target.execute("publish", target.request("publish", prior))
    request = target.request(operation, prior)
    owner = ProjectContributionPolicyEligibility
    original_project = owner.lock_contribution_policy_project
    original_role_project = AdminAuthorizationRepository.lock_project
    held, release = asyncio.Event(), asyncio.Event()
    first_name = f"cp07a-policy-{uuid4().hex[:10]}"
    issue_name = f"cp07a-issue-{uuid4().hex[:10]}"
    pids: dict[str, int] = {}
    role_sqlstates: list[str | None] = []

    async def pause_policy(projects, project_id):
        result = await original_project(projects, project_id)
        if asyncio.current_task().get_name() == first_name:
            pids[first_name] = int(await projects._session.scalar(text("select pg_backend_pid()")))
            held.set()
            await release.wait()
        return result

    async def mutate():
        return await target.execute(operation, request)

    async def issue():
        return await _issue_role(admin_access, manager, target.project, target.context.actor_profile_id)

    async def lock_role_project(repository, project_id):
        try:
            return await original_role_project(repository, project_id)
        except DBAPIError as exc:
            role_sqlstates.append(getattr(exc.orig, "sqlstate", None))
            raise

    monkeypatch.setattr(owner, "lock_contribution_policy_project", pause_policy)
    monkeypatch.setattr(AdminAuthorizationRepository, "lock_project", lock_role_project)
    control_pids, control_entered = _observed_lock_hooks(
        monkeypatch, names={issue_name: issue_name},
    )
    first_task = second_task = None
    try:
        first_task = asyncio.create_task(mutate(), name=first_name)
        await asyncio.wait_for(held.wait(), timeout=30)
        second_task = asyncio.create_task(issue(), name=issue_name)
        await asyncio.wait_for(control_entered[issue_name].wait(), timeout=30)
        await _wait_edge(auth_database_env, issue_name, control_pids[issue_name], pids[first_name])
        release.set()
        policy_result, role_response = await asyncio.wait_for(
            asyncio.gather(first_task, second_task), timeout=60,
        )
        assert policy_result.operation_id == request.operation_id
        assert role_response.status_code == 201, (role_response.status_code, role_sqlstates)
        assert role_sqlstates == []
        assert role_response.json()["actor_profile_id"] == str(target.context.actor_profile_id)
    finally:
        release.set()
        await asyncio.gather(
            *(task for task in (first_task, second_task) if task is not None),
            return_exceptions=True,
        )


@pytest.mark.asyncio
async def test_validation_role_issue_and_binding_suspension_complete_in_lock_order(
    admin_access, auth_database_env, monkeypatch,
) -> None:
    target, published, _ = await published_world(admin_access)
    manager = await _manager(admin_access, target.project)
    validation = ContributionPolicyValidationRequest(
        project_id=target.project,
        contribution_policy_id=published.contribution_policy_id,
        contribution_policy_version_id=published.contribution_policy_version_id,
        purpose=ContributionPolicyValidationPurpose.GUIDE_ACTIVATION,
    )
    suspend = AdapterBindingSuspendRequest(
        operation_id=uuid4(), actor_profile_id=target.context.actor_profile_id,
        project_id=target.project, adapter_binding_id=target.binding,
        expected_lifecycle_version=1,
    )
    owner = ProjectContributionPolicyEligibility
    original_project = owner.lock_contribution_policy_project
    held, release = asyncio.Event(), asyncio.Event()
    validate_name, issue_name, suspend_name = (
        f"cp07a-validate-{uuid4().hex[:8]}",
        f"cp07a-issue-{uuid4().hex[:8]}",
        f"cp07a-suspend-{uuid4().hex[:8]}",
    )
    validator_pid: int | None = None

    async def pause_validation(projects, project_id):
        nonlocal validator_pid
        result = await original_project(projects, project_id)
        if asyncio.current_task().get_name() == validate_name:
            validator_pid = int(await projects._session.scalar(text("select pg_backend_pid()")))
            held.set()
            await release.wait()
        return result

    async def validate():
        async with db_session.get_session_factory()() as session, session.begin():
            return await contribution_policy_validation_port(session).validate_contribution_policy(
                validation,
            )

    async def suspend_binding():
        async with db_session.get_session_factory()() as session, session.begin():
            authority = compensation_adapter_binding_authorization(session, target.context)
            return await AdapterBindingService(session, mutation_authorization=authority).suspend(
                suspend,
            )

    monkeypatch.setattr(owner, "lock_contribution_policy_project", pause_validation)
    control_pids, control_entered = _observed_lock_hooks(
        monkeypatch,
        names={issue_name: issue_name, suspend_name: suspend_name},
    )
    tasks = []
    try:
        tasks.append(asyncio.create_task(validate(), name=validate_name))
        await asyncio.wait_for(held.wait(), timeout=30)
        tasks.append(asyncio.create_task(
            _issue_role(admin_access, manager, target.project, target.context.actor_profile_id),
            name=issue_name,
        ))
        await asyncio.wait_for(control_entered[issue_name].wait(), timeout=30)
        await _wait_edge(auth_database_env, issue_name, control_pids[issue_name], validator_pid)
        tasks.append(asyncio.create_task(suspend_binding(), name=suspend_name))
        await asyncio.wait_for(control_entered[suspend_name].wait(), timeout=30)
        await _wait_edge(
            auth_database_env, suspend_name, control_pids[suspend_name],
            control_pids[issue_name],
        )
        release.set()
        validated, issued, suspended = await asyncio.wait_for(asyncio.gather(*tasks), timeout=60)
        assert validated.adapter_binding_ids == (target.binding,)
        assert issued.status_code == 201, issued.text
        assert suspended.operation_id == suspend.operation_id
        assert suspended.to_status == "suspended"
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


class _ObservedBeforeProject(_PauseBeforeProject):
    def __init__(self, repository, session, entered, release):
        super().__init__(repository, entered, release)
        self.session = session
        self.backend_pid: int | None = None

    async def lock_locked_policy_context(self, request):
        self.backend_pid = int(await self.session.scalar(text("select pg_backend_pid()")))
        return await super().lock_locked_policy_context(request)


@pytest.mark.asyncio
async def test_dual_finance_submitter_profile_precedes_policy_project_lock(
    tmp_path: Path, isolated_database_env: str, monkeypatch,
) -> None:
    import tests.test_default_pre_submit_execution as default_tests

    original_limits = default_tests._limits
    monkeypatch.setattr(default_tests, "_limits", lambda: replace(
        original_limits(), total_deadline_seconds=90, reservation_ttl_seconds=120,
        aggregate_reserved_bytes=4 * default_tests.HARD_MAXIMUM_ARTIFACT_BYTES,
    ))
    harness = await _harness(tmp_path, isolated_database_env)
    con_engine = None
    art_task = con_task = None
    release_art = asyncio.Event()
    try:
        await _seed_materializer(harness.factory)
        project_id = harness.request.effective_plan.lineage.project_id
        async with harness.factory.begin() as setup:
            await grant_fixture_admin_role(
                setup, harness.actor_id, role="finance_authority",
                scope="project", project_id=project_id,
            )
        con_name = f"cp07a-dual-finance-{uuid4().hex[:10]}"
        con_engine = create_async_engine(
            isolated_database_env,
            connect_args={"server_settings": {"application_name": con_name}},
        )
        con_factory = async_sessionmaker(con_engine, expire_on_commit=False)
        draft = ContributionPolicyCreateDraftRequest(
            actor_profile_id=harness.actor_id, project_id=project_id,
            operation_id=uuid4(), name="Dual role lock order",
        )
        async with harness.factory() as art_session, con_factory() as con_session:
            calls: list[int] = []
            workflow, materializer = await _ready_workflow(harness, art_session, calls)
            reservation = await _reserve_with_real_materializer(
                workflow, harness.request, harness.preparation_request,
            )
            art_before_project = asyncio.Event()
            paused = _ObservedBeforeProject(
                workflow._project_contexts, art_session,
                art_before_project, release_art,
            )
            workflow._project_contexts = paused
            context = HumanAuthorizationContext(
                actor_profile_id=harness.actor_id, actor_kind=ActorKind.HUMAN,
                actor_status=ActorStatus.ACTIVE, identity_link_id=harness.identity_link_id,
                identity_link_status=IdentityLinkStatus.ACTIVE,
                request_id=uuid4(), correlation_id=uuid4(),
            )

            async def create_draft():
                async with con_session.begin():
                    authority = contribution_policy_authorization(con_session, context)
                    return await contribution_policy_service(
                        con_session, read_authorization=authority,
                        mutation_authorization=authority,
                    ).create_draft(draft)

            try:
                art_task = asyncio.create_task(workflow.execute_reserved(
                    harness.request, reservation,
                    preparation_request=harness.preparation_request,
                ))
                await asyncio.wait_for(art_before_project.wait(), timeout=30)
                assert paused.backend_pid is not None
                await _assert_row_locked(harness.engine, "actor_profiles", harness.actor_id)
                await _assert_row_locked(
                    harness.engine, "actor_identity_links", harness.identity_link_id,
                )
                con_task = asyncio.create_task(create_draft())
                await _wait_edge(
                    isolated_database_env, con_name, None, paused.backend_pid,
                )
                release_art.set()
                art_result, policy_result = await asyncio.wait_for(
                    asyncio.gather(art_task, con_task), timeout=60,
                )
                assert art_result.pass_capability is not None
                assert policy_result.operation_id == draft.operation_id
                assert calls == [1]
            finally:
                release_art.set()
                await asyncio.gather(
                    *(task for task in (art_task, con_task) if task is not None),
                    return_exceptions=True,
                )
                materializer.close()
        async with harness.factory() as check:
            assert await check.scalar(select(PreSubmitEvidenceSet.id).limit(1)) is not None
    finally:
        release_art.set()
        if con_engine is not None:
            await con_engine.dispose()
        await harness.close()
