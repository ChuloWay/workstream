"""PostgreSQL proofs for checker-retry authority ordering and revocation."""

import asyncio

import pytest
from sqlalchemy import func, select, text

from app.adapters.audit import task_transition_audit
from app.adapters.checkers import checker_retry_service
from app.adapters.tasks import task_commands
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.admin_service import AdminRoleGrantService
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.checker_retry_authorization import (
    PreparedCheckerRetryAuthorization,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.models import AdminRoleGrant, AuthorityControl
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import AdminRoleGrantResourceContext
from app.modules.authorization.schemas import (
    AdminRoleGrantRevokeRequest,
    AuthorityOperation,
    derive_reason_digest,
)
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.checkers.models import CheckerRetryReceipt, CheckerRun, CheckerSubmissionFence
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import AuditEvent, TaskCommandReceipt
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.service import TaskTransitionBlocked
from auth_concurrency_support import wait_for_named_database_lock
from tests.checkers.execution.test_checker_retry import _command, _failed_source, _operator_for
from tests.test_artifact_admission import _context


async def _named_retry(h, operator, name):
    async with h.factory.begin() as session:
        await session.execute(
            text("select set_config('application_name', :name, true)"), {"name": name}
        )
        return await checker_retry_service(session, operator).retry(_command(h, operator))


async def _named_override(h, operator, name):
    key = operator.request_id
    async with h.factory() as session:
        await session.execute(
            text("select set_config('application_name', :name, false)"), {"name": name}
        )
        await session.commit()
        try:
            return await task_commands(
                session,
                authorization=PreparedTaskAuthorization(session, operator),
                audit=task_transition_audit(session),
                actor_profile_id=operator.actor_profile_id,
                settings=get_settings(),
            ).start(
                h.request.task_id,
                "Operator recovery start while evaluation is pending",
                idempotency_key=key,
                operator_override=True,
            )
        finally:
            await session.rollback()
            await session.execute(
                text("select set_config('application_name', '', false)")
            )
            await session.commit()


async def _retry_facts(h):
    async with h.factory() as session:
        fence = await session.get(CheckerSubmissionFence, str(h.request.submission_id))
        return (
            await session.scalar(select(func.count()).select_from(CheckerRun)),
            await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)),
            await session.scalar(select(func.count()).select_from(OutboxEvent)),
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action_id == ActionId.OPERATIONS_CHECKER_RETRY.value)
            ),
            str(fence.current_run_id),
        )


async def _revocation_setup(h, operator):
    async with h.factory() as session:
        grant = await session.scalar(
            select(AdminRoleGrant).where(
                AdminRoleGrant.target_actor_profile_id == str(operator.actor_profile_id),
                AdminRoleGrant.role == "operator",
                AdminRoleGrant.status == "active",
            )
        )
        assert grant is not None
        revoker_link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.actor_profile_id == grant.granted_by_actor_profile_id,
                ActorIdentityLink.status == "active",
            )
        )
        assert revoker_link is not None
        grant_id = grant.id
        revoker_actor_id = grant.granted_by_actor_profile_id
        revoker_link_id = revoker_link.id
    key = new_record_id()
    revoker = _context(
        actor_profile_id=revoker_actor_id,
        identity_link_id=revoker_link_id,
    ).model_copy(update={"request_id": key, "correlation_id": key})
    return grant_id, revoker


async def _named_revoke(h, grant_id, revoker, name):
    reason = "Revoke Operator authority during checker recovery"
    request = AdminRoleGrantRevokeRequest(
        operation=AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE,
        grant_id=grant_id,
        reason_digest=derive_reason_digest(reason),
    )
    async with h.factory.begin() as session:
        await session.execute(
            text("select set_config('application_name', :name, true)"), {"name": name}
        )
        service = AdminRoleGrantService(session)
        reservation = await service.reserve(
            idempotency_key=revoker.request_id,
            actor_profile_id=revoker.actor_profile_id,
            request=request,
        )
        assert reservation.outcome == "claimed"
        decision = await AuthorizationService(session, revoker).require(
            ActionId.ADMIN_ROLE_GRANT_REVOKE,
            AdminRoleGrantResourceContext(
                resource_type="admin_role_grant", resource_id=grant_id
            ),
        )
        return await service.complete_revoke(
            claim=reservation.claim,
            request=request,
            decision=decision,
            actor_profile_id=revoker.actor_profile_id,
            reason=reason,
        )


async def test_task_wait_holds_no_retry_authority_custody(
    tmp_path, isolated_database_env, monkeypatch
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _):
        operator = await _operator_for(h)
        name = f"checker-retry-task-wait-{new_record_id().hex}"
        async with h.factory.begin() as holder:
            assert await TaskRepository(holder).lock_project_task(
                h.request.project_id, h.request.task_id
            ) is not None
            call = asyncio.create_task(_named_retry(h, operator, name))
            try:
                await asyncio.wait_for(
                    wait_for_named_database_lock(isolated_database_env, name), 30
                )
                async with h.factory.begin() as probe:
                    assert await probe.scalar(
                        select(AuthorityControl)
                        .where(AuthorityControl.id == 1)
                        .with_for_update(nowait=True)
                    ) is not None
                    assert await probe.scalar(
                        select(ActorProfile)
                        .where(ActorProfile.id == str(operator.actor_profile_id))
                        .with_for_update(nowait=True)
                    ) is not None
                    assert await probe.scalar(
                        select(ActorIdentityLink)
                        .where(ActorIdentityLink.id == str(operator.identity_link_id))
                        .with_for_update(nowait=True)
                    ) is not None
                    grant = await probe.scalar(
                        select(AdminRoleGrant)
                        .where(
                            AdminRoleGrant.target_actor_profile_id
                            == str(operator.actor_profile_id),
                            AdminRoleGrant.status == "active",
                        )
                        .with_for_update(nowait=True)
                    )
                    assert grant is not None
                assert await _retry_facts(h) == (
                    1,
                    0,
                    1,
                    0,
                    str(h.created.evaluation_attempt_id),
                )
            except BaseException:
                call.cancel()
                await asyncio.gather(call, return_exceptions=True)
                raise
        created = await asyncio.wait_for(call, 60)
        assert created.successor.generation == 2
        assert (await _retry_facts(h))[:4] == (2, 1, 2, 1)


@pytest.mark.parametrize("first", ["retry", "override"])
async def test_retry_and_start_override_keep_task_before_authority(
    tmp_path, isolated_database_env, monkeypatch, first
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _):
        operator = await _operator_for(h)
        override_key = new_record_id()
        override = operator.model_copy(
            update={"request_id": override_key, "correlation_id": override_key}
        )
        held, release = asyncio.Event(), asyncio.Event()
        holder_name = f"checker-{first}-authority-holder"
        waiter_name = f"checker-{first}-task-wait-{new_record_id().hex}"
        reached_authority: list[str] = []
        original = AdminAuthorizationRepository.lock_request_actor

        async def pause_holder(repository, *args, **kwargs):
            locked = await original(repository, *args, **kwargs)
            task = asyncio.current_task()
            assert task is not None
            reached_authority.append(task.get_name())
            if task.get_name() == holder_name:
                held.set()
                await release.wait()
            return locked

        invoke = {
            "retry": lambda name: _named_retry(h, operator, name),
            "override": lambda name: _named_override(h, override, name),
        }
        second = "override" if first == "retry" else "retry"
        tasks = []
        with monkeypatch.context() as patch:
            patch.setattr(AdminAuthorizationRepository, "lock_request_actor", pause_holder)
            try:
                tasks.append(asyncio.create_task(invoke[first](holder_name), name=holder_name))
                await asyncio.wait_for(held.wait(), 30)
                tasks.append(asyncio.create_task(invoke[second](waiter_name), name=waiter_name))
                await asyncio.wait_for(
                    wait_for_named_database_lock(isolated_database_env, waiter_name), 30
                )
                assert waiter_name not in reached_authority
                release.set()
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), 90
                )
            finally:
                release.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        assert sum(not isinstance(result, BaseException) for result in results) == 1
        assert sum(isinstance(result, TaskTransitionBlocked) for result in results) == 1
        assert (await _retry_facts(h))[:4] == (2, 1, 2, 1)
        async with h.factory() as session:
            assert await session.scalar(
                select(func.count())
                .select_from(TaskCommandReceipt)
                .where(TaskCommandReceipt.idempotency_key == override_key)
            ) == 0


@pytest.mark.parametrize("first", ["retry", "revoke"])
async def test_retry_and_operator_revocation_commit_one_authorized_order(
    tmp_path, isolated_database_env, monkeypatch, first
):
    async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _):
        operator = await _operator_for(h)
        grant_id, revoker = await _revocation_setup(h, operator)
        held, release = asyncio.Event(), asyncio.Event()
        retry_name = f"checker-retry-revocation-{first}-{new_record_id().hex}"
        revoke_name = f"checker-grant-revocation-{first}-{new_record_id().hex}"
        original_consume = PreparedCheckerRetryAuthorization.consume
        original_revoke = AdminRoleGrantService.complete_revoke

        async def pause_retry(authority, handle, facts, successor):
            receipt = await original_consume(authority, handle, facts, successor)
            if first == "retry":
                held.set()
                await release.wait()
            return receipt

        async def pause_revoke(service, **kwargs):
            response = await original_revoke(service, **kwargs)
            if first == "revoke":
                held.set()
                await release.wait()
            return response

        calls = []
        with monkeypatch.context() as patch:
            patch.setattr(PreparedCheckerRetryAuthorization, "consume", pause_retry)
            patch.setattr(AdminRoleGrantService, "complete_revoke", pause_revoke)
            try:
                if first == "retry":
                    calls.append(asyncio.create_task(_named_retry(h, operator, retry_name)))
                else:
                    calls.append(
                        asyncio.create_task(
                            _named_revoke(h, grant_id, revoker, revoke_name)
                        )
                    )
                await asyncio.wait_for(held.wait(), 30)
                if first == "retry":
                    calls.append(
                        asyncio.create_task(
                            _named_revoke(h, grant_id, revoker, revoke_name)
                        )
                    )
                    waiter_name = revoke_name
                else:
                    calls.append(asyncio.create_task(_named_retry(h, operator, retry_name)))
                    waiter_name = retry_name
                await asyncio.wait_for(
                    wait_for_named_database_lock(isolated_database_env, waiter_name), 30
                )
                release.set()
                results = await asyncio.wait_for(
                    asyncio.gather(*calls, return_exceptions=True), 90
                )
            finally:
                release.set()
                for call in calls:
                    if not call.done():
                        call.cancel()
                await asyncio.gather(*calls, return_exceptions=True)
        async with h.factory() as session:
            grant = await session.get(AdminRoleGrant, grant_id)
            assert grant.status == "revoked" and grant.version == 2
        if first == "retry":
            assert all(not isinstance(result, BaseException) for result in results)
            assert (await _retry_facts(h))[:4] == (2, 1, 2, 1)
        else:
            assert sum(isinstance(result, CheckerExecutionUnavailable) for result in results) == 1
            assert (await _retry_facts(h)) == (
                1,
                0,
                1,
                0,
                str(h.created.evaluation_attempt_id),
            )
