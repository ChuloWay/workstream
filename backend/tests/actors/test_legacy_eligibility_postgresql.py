# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalOperand=false
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.db import session as db_session
from app.modules.actors.models import (
    LegacyActorIdentity,
    LegacyWorkflowEligibility,
)
from app.modules.actors.repository import ActorRepository
from app.modules.actors.schemas import (
    LegacyWorkflowEligibilityActivationRequest,
)
from app.modules.actors.service import (
    ActorProfileDisabled,
    ActorService,
    LegacyWorkflowEligibilityCompatibility,
)
from app.modules.tasks.models import AuditEvent

from tests.actors.support import verified_token, legacy_actor
from auth_concurrency_support import wait_for_named_database_lock


async def test_legacy_activation_writes_only_compatibility_metadata(
    actor_database_env: str,
) -> None:
    actor = legacy_actor("legacy-intake")
    async with db_session.get_session_factory()() as session:
        await ActorService(session).resolve_verified_actor(
            verified_token("legacy-intake"),
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        response = await ActorService(session).activate_legacy_workflow_eligibility(
            actor,
            LegacyWorkflowEligibilityActivationRequest(skill_tags=["STEM", "stem"]),
        )
    assert response.status == "active"
    assert response.skill_tags == ["stem"]
    async with db_session.get_session_factory()() as session:
        assert await session.get(LegacyActorIdentity, actor.actor_id) is not None
        eligibility = await session.scalar(
            select(LegacyWorkflowEligibility).where(
                LegacyWorkflowEligibility.actor_id == actor.actor_id
            )
        )
        assert eligibility is not None
        assert eligibility.profile_metadata == {"source": "legacy_worker_profile_api"}
        table_names = set(
            await session.scalars(
                text("select tablename from pg_tables where schemaname=current_schema()")
            )
        )
        assert "admin_role_grants" in table_names
        assert await session.scalar(text("select count(*) from admin_role_grants")) == 0
        assert "project_role_grants" in table_names
        assert "project_role_qualification_snapshots" in table_names
        assert await session.scalar(text("select count(*) from project_role_grants")) == 0
        assert (
            await session.scalar(text("select count(*) from project_role_qualification_snapshots"))
            == 0
        )


async def test_repeated_legacy_activation_updates_one_row_and_audits_only_changes(
    actor_database_env: str,
) -> None:
    actor = legacy_actor("legacy-repeat")
    async with db_session.get_session_factory()() as session:
        await ActorService(session).resolve_verified_actor(
            verified_token("legacy-repeat"),
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        service = ActorService(session)
        first = await service.activate_legacy_workflow_eligibility(
            actor,
            LegacyWorkflowEligibilityActivationRequest(skill_tags=["stem"]),
        )
        changed = await service.activate_legacy_workflow_eligibility(
            actor,
            LegacyWorkflowEligibilityActivationRequest(skill_tags=["data"]),
        )
        unchanged = await service.activate_legacy_workflow_eligibility(
            actor,
            LegacyWorkflowEligibilityActivationRequest(skill_tags=["data"]),
        )

    assert first.id == changed.id == unchanged.id
    assert first.skill_tags == ["stem"]
    assert changed.skill_tags == unchanged.skill_tags == ["data"]
    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(LegacyWorkflowEligibility)
                .where(LegacyWorkflowEligibility.actor_id == actor.actor_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.entity_type == "legacy_workflow_eligibility",
                    AuditEvent.actor_id == actor.actor_id,
                )
            )
            == 2
        )


async def test_concurrent_legacy_activation_serializes_payloads_and_actual_audits(
    actor_database_env: str,
) -> None:
    actor = legacy_actor("legacy-concurrent-activation")
    async with db_session.get_session_factory()() as session:
        await ActorService(session).resolve_verified_actor(
            verified_token("legacy-concurrent-activation"),
            request_id=uuid4(),
            correlation_id=uuid4(),
        )

    async with (
        db_session.get_session_factory()() as first_session,
        db_session.get_session_factory()() as second_session,
    ):
        await ActorRepository(first_session).lock_external_identity(
            actor.external_issuer,
            actor.external_subject,
        )
        blocker_pid = await first_session.scalar(text("select pg_backend_pid()"))
        waiter_pid = await second_session.scalar(text("select pg_backend_pid()"))
        assert blocker_pid != waiter_pid
        waiter_name = f"actor-legacy-{uuid4().hex}"
        await second_session.execute(
            text("select set_config('application_name', :name, true)"), {"name": waiter_name}
        )
        second_activation = asyncio.create_task(
            ActorService(second_session).activate_legacy_workflow_eligibility(
                actor,
                LegacyWorkflowEligibilityActivationRequest(skill_tags=["second"]),
            )
        )
        try:
            await asyncio.wait_for(
                wait_for_named_database_lock(
                    actor_database_env,
                    waiter_name,
                    expected_waiter_pid=waiter_pid,
                    expected_blocker_pid=blocker_pid,
                ),
                timeout=5,
            )
            assert not second_activation.done()
            first = await ActorService(first_session).activate_legacy_workflow_eligibility(
                actor,
                LegacyWorkflowEligibilityActivationRequest(skill_tags=["first"]),
            )
            second = await asyncio.wait_for(second_activation, timeout=5)
        except Exception:
            if second_activation.done():
                await (
                    second_activation
                )  # Surface a worker failure instead of masking it as a wait failure.
            raise
        finally:
            if not second_activation.done():
                second_activation.cancel()
            await asyncio.gather(second_activation, return_exceptions=True)

    assert first.skill_tags == ["first"]
    assert second.skill_tags == ["second"]
    assert first.id == second.id
    async with db_session.get_session_factory()() as session:
        eligibility = await session.scalar(
            select(LegacyWorkflowEligibility).where(
                LegacyWorkflowEligibility.actor_id == actor.actor_id
            )
        )
        assert eligibility is not None
        assert eligibility.skill_tags == ["second"]
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.entity_type == "legacy_workflow_eligibility",
                    AuditEvent.actor_id == actor.actor_id,
                )
            )
            == 2
        )


async def test_disabled_legacy_eligibility_is_not_reactivated(actor_database_env: str) -> None:
    legacy = legacy_actor("disabled-legacy")
    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                LegacyActorIdentity(
                    actor_id=legacy.actor_id,
                    external_subject=legacy.external_subject,
                    external_issuer=legacy.external_issuer,
                    last_seen_roles=["worker"],
                    last_claim_snapshot={},
                    auth_source="dev_mock",
                    is_dev_auth=True,
                ),
                LegacyWorkflowEligibility(
                    id=str(uuid4()),
                    actor_id=legacy.actor_id,
                    profile_type="worker",
                    status="disabled",
                    skill_tags=[],
                    scope_type="global",
                    scope_id="global",
                    profile_metadata={},
                ),
            ]
        )
        await session.commit()
        with pytest.raises(ActorProfileDisabled):
            await ActorService(session).activate_legacy_workflow_eligibility(
                legacy,
                LegacyWorkflowEligibilityActivationRequest(skill_tags=[]),
            )
        compatibility = LegacyWorkflowEligibilityCompatibility(session)
        assert await compatibility.get_active_submitter_eligibility(legacy.actor_id) is None
        assert await compatibility.get_active_submitter_eligibility(str(uuid4())) is None
