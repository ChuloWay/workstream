"""Every real participant is staged inside the same rollback boundary."""

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.artifacts.models import SubmissionBundleAdmission, SubmissionBindingReceipt, ArtifactBinding
from app.modules.artifacts.submission_bindings import SubmissionAdmissionConsumptionService
from app.modules.authorization.submission_creation_authorization import PreparedSubmissionCreationAuthorization
from app.modules.checkers.execution_coordination import EvaluationCoordinator
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.service import OutboxService
from app.modules.tasks.models import Submission, SubmissionDispatch, AuditEvent, WorkstreamTask
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from tests.post_submit_materialization_helpers import material_fixture


class ParticipantFailure(RuntimeError):
    pass


@pytest.mark.parametrize("owner,method,stored", [
    (SubmissionAdmissionConsumptionService, "consume", SubmissionBindingReceipt),
    (PreparedSubmissionCreationAuthorization, "consume", AuditEvent),
    (EvaluationCoordinator, "reserve_current_evaluation", CheckerRun),
    (OutboxService, "append", OutboxEvent),
    (TaskSubmissionCreationService, "create", SubmissionDispatch),
])
async def test_participant_failure_rolls_back_actual_staged_rows(
    tmp_path, isolated_database_env, monkeypatch, owner, method, stored,
):
    original = getattr(owner, method)
    observed = []

    async def fail_after_write(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        session = self._repository._session if owner is OutboxService else self._session
        query = select(func.count()).select_from(stored)
        if stored is AuditEvent:
            query = query.where(AuditEvent.action_id == "submission.create")
        assert await session.scalar(query) == 1
        observed.append(result)
        raise ParticipantFailure("after real participant write")

    monkeypatch.setattr(owner, method, fail_after_write)
    with pytest.raises(ParticipantFailure, match="after real participant write"):
        async with material_fixture(tmp_path, isolated_database_env):
            pytest.fail("partial creation committed")
    assert len(observed) == 1
    engine = create_async_engine(isolated_database_env)
    try:
        async with async_sessionmaker(engine)() as session:
            for model in (Submission, SubmissionDispatch, SubmissionBindingReceipt, ArtifactBinding, CheckerRun, OutboxEvent):
                assert await session.scalar(select(func.count()).select_from(model)) == 0
            assert await session.scalar(select(SubmissionBundleAdmission.status)) == "ready"
            assert await session.scalar(select(WorkstreamTask.status)) == "in_progress"
            assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id.in_(["submission.create", "artifact.submission.binding.create"]),
            )) == 0
    finally:
        await engine.dispose()


async def test_raw_savepoint_cannot_release_creation_custody(tmp_path, isolated_database_env, monkeypatch):
    from sqlalchemy import text
    original = TaskSubmissionCreationService.create
    observed = []

    async def inside_raw_savepoint(self, request):
        await self._session.execute(text("SAVEPOINT caller_savepoint"))
        assert self._session.in_nested_transaction() is False
        observed.append(True)
        return await original(self, request)

    monkeypatch.setattr(TaskSubmissionCreationService, "create", inside_raw_savepoint)
    with pytest.raises(RuntimeError, match="requires one root transaction"):
        async with material_fixture(tmp_path, isolated_database_env):
            pytest.fail("creation accepted an unmanaged savepoint")
    assert observed == [True]


async def test_revoked_binding_identity_rolls_back_initial_creation(tmp_path, isolated_database_env):
    from sqlalchemy import text
    from app.modules.artifacts.api import SubmissionAdmissionConsumptionError
    from tests.post_submit_materialization_helpers import _material_fixture, _write_current_submission, _read_current_request

    async def revoke_before_create(factory, context, request):
        async with factory.begin() as session:
            await session.execute(text("""UPDATE public.actor_identity_links SET status='revoked',
                revoked_by='dispatch-test', revoked_at=clock_timestamp(), revoked_reason='Withdraw binding authority'
                WHERE actor_profile_id IN (SELECT id FROM public.actor_profiles
                    WHERE service_identity='workstream.artifact.binding')"""))
        return await _write_current_submission(factory, context, request)

    with pytest.raises(SubmissionAdmissionConsumptionError, match="submission_bundle_admission_unavailable"):
        async with _material_fixture(tmp_path, isolated_database_env,
                                     write_submission=revoke_before_create, read_request=_read_current_request):
            pytest.fail("revoked binding service created a Submission")
    engine = create_async_engine(isolated_database_env)
    try:
        async with async_sessionmaker(engine)() as session:
            for model in (Submission, SubmissionDispatch, SubmissionBindingReceipt, ArtifactBinding, CheckerRun, OutboxEvent):
                assert await session.scalar(select(func.count()).select_from(model)) == 0
            assert await session.scalar(select(SubmissionBundleAdmission.status)) == "ready"
            assert await session.scalar(select(WorkstreamTask.status)) == "in_progress"
            assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id.in_(["submission.create", "artifact.submission.binding.create"]),
            )) == 0
    finally:
        await engine.dispose()
