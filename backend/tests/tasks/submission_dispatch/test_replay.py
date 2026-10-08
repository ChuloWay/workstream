"""Retained creation cannot reset generations or borrow another owner's admission."""

from dataclasses import replace

import pytest
from sqlalchemy import func, select, text

from app.adapters.checkers import evaluation_coordinator
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.core.identifiers import new_record_id
from app.modules.actors.models import ActorProfile
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.api import SubmissionAdmissionConsumptionError
from app.modules.checkers.models import CheckerRun, CheckerSubmissionFence
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.api import SubmissionCreationUnavailable, TaskSubmissionContextUnavailable
from app.modules.tasks.models import SubmissionDispatch
from tests.checkers.post_submit.support import change_request
from tests.post_submit_materialization_helpers import material_fixture


async def replay(h, request=None):
    async with h.factory() as session:
        return await compose_hidden_submission_creation_command(
            session, h.actor_context, request_id=new_record_id(), correlation_id=new_record_id(),
        ).create(request or h.creation_request)


async def test_later_generation_does_not_change_original_creation_replay(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        successor = change_request(h.request, evaluation_request_id=new_record_id(), evaluation_generation=2)
        async with h.factory.begin() as session:
            newer = await evaluation_coordinator(session).reserve_current_evaluation(successor)
        assert await replay(h) == h.created
        async with h.factory() as session:
            fence = await session.get(CheckerSubmissionFence, str(h.created.submission_id))
            assert fence.current_run_id == str(newer.attempt_id)
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 2
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1


async def test_valid_foreign_ownership_cannot_be_mixed_into_creation_replay(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path / "first", isolated_database_env) as h:
        async with material_fixture(tmp_path / "foreign", isolated_database_env,
                                    provision_services=False, storage_settings=h.settings) as foreign:
            for field in ("task_id", "assignment_id", "contributor_id", "admission_id"):
                with pytest.raises((SubmissionCreationUnavailable, TaskSubmissionContextUnavailable)):
                    await replay(h, replace(h.creation_request, **{field: getattr(foreign.creation_request, field)}))
            assert await replay(h) == h.created
            assert await replay(foreign) == foreign.created
            async with h.factory() as session:
                assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 2
                assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 2
                assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 2


async def test_live_revocation_and_service_suspension_deny_retained_replay(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        async with h.factory.begin() as session:
            binding_actor = await session.scalar(select(ActorProfile.id).where(
                ActorProfile.service_identity == ServiceIdentity.ARTIFACT_BINDING.value,
            ))
        for actor_id in (str(h.actor_context.actor_profile_id), binding_actor):
            async with h.factory.begin() as session:
                await session.execute(text("UPDATE public.actor_profiles SET status='suspended', suspended_by='dispatch-test', suspended_at=clock_timestamp(), suspension_reason='Recheck live authority' WHERE id=:id"), {"id": actor_id})
            try:
                with pytest.raises((SubmissionCreationUnavailable, SubmissionAdmissionConsumptionError)):
                    await replay(h)
            finally:
                async with h.factory.begin() as session:
                    await session.execute(text("UPDATE public.actor_profiles SET status='active', suspended_by=NULL, suspended_at=NULL, suspension_reason=NULL, reactivated_by='dispatch-test', reactivated_at=clock_timestamp(), reactivation_reason='Restore valid control' WHERE id=:id"), {"id": actor_id})
        assert await replay(h) == h.created
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1


async def test_missing_retained_owners_never_trigger_repair(tmp_path, isolated_database_env, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.modules.audit.service import AuditService
    from app.modules.artifacts.models import SubmissionBindingReceipt
    from app.modules.checkers.execution_coordination import EvaluationCoordinator
    from app.modules.checkers.api.execution import CheckerExecutionUnavailable
    from app.modules.outbox.repository import OutboxRepository
    from app.modules.outbox.service import OutboxService
    from app.modules.outbox.api import OutboxIdempotencyConflict

    async with material_fixture(tmp_path, isolated_database_env) as h:
        async def forbidden(*args, **kwargs):
            pytest.fail("retained replay tried to create missing custody")
        original_scalar, original_get = AsyncSession.scalar, AsyncSession.get
        original_audit = AuditService.get_authority_event
        for missing in ("dispatch", "creation_allow", "binding_receipt", "binding_allow", "reservation", "event"):
            seen = []
            async def read_scalar(session, statement, *args, **kwargs):
                model = SubmissionDispatch if missing == "dispatch" else CheckerRun if missing == "reservation" else None
                if model is not None and any(value.get("entity") is model for value in getattr(statement, "column_descriptions", ())):
                    seen.append(missing)
                    return None
                return await original_scalar(session, statement, *args, **kwargs)
            async def read_get(session, entity, ident, **kwargs):
                if missing == "binding_receipt" and entity is SubmissionBindingReceipt:
                    assert ident == h.created.admission_id
                    seen.append(missing)
                    return None
                return await original_get(session, entity, ident, **kwargs)
            async def read_audit(service, identifier):
                selected = h.created.creation_decision_id if missing == "creation_allow" else h.created.binding_decision_id if missing == "binding_allow" else None
                if identifier == selected:
                    seen.append(missing)
                    return None
                return await original_audit(service, identifier)
            async def read_event(repository, identifier, value):
                assert identifier == h.created.evaluation_event_id
                seen.append(missing)
                return None
            with monkeypatch.context() as patch:
                patch.setattr(EvaluationCoordinator, "reserve_current_evaluation", forbidden)
                patch.setattr(OutboxService, "append", forbidden)
                patch.setattr(AsyncSession, "scalar", read_scalar)
                patch.setattr(AsyncSession, "get", read_get)
                patch.setattr(AuditService, "get_authority_event", read_audit)
                if missing == "event":
                    patch.setattr(OutboxRepository, "read_exact", read_event)
                with pytest.raises((SubmissionCreationUnavailable, TaskSubmissionContextUnavailable,
                                    SubmissionAdmissionConsumptionError, CheckerExecutionUnavailable,
                                    OutboxIdempotencyConflict)):
                    await replay(h)
            assert seen == [missing]
        assert await replay(h) == h.created
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
