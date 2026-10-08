"""Real ART admission and AUTH through the canonical hidden transaction."""

from sqlalchemy import select, func, text

from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.core.identifiers import new_record_id
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import AuditEvent, SubmissionDispatch, WorkstreamTask
from tests.post_submit_materialization_helpers import material_fixture


async def test_creation_commits_exact_dispatch_and_fresh_transport_replay(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        result = h.created
        async with h.factory() as session:
            receipt = await session.get(SubmissionDispatch, result.submission_id)
            assert receipt is not None and receipt.result() == result
            assert (await session.get(WorkstreamTask, str(h.request.task_id))).status == "evaluation_pending"
            run = await session.get(CheckerRun, str(result.evaluation_attempt_id))
            assert run.evaluation_request_id == str(result.evaluation_request_id)
            assert run.request_digest == result.evaluation_request_digest == h.request.request_sha256
            assert run.result_id == str(result.evaluation_result_id)
            assert run.evaluation_generation == 1 and run.status == "queued"
            event = await session.get(OutboxEvent, result.evaluation_event_id)
            assert event.payload["request_id"] == str(result.evaluation_request_id)
            assert event.payload["creation_decision_id"] == str(result.creation_decision_id)
            assert event.payload["binding_decision_id"] == str(result.binding_decision_id)
            assert await session.scalar(text("SELECT public.submission_dispatch_valid(d) FROM public.submission_dispatches d WHERE submission_id=:id"), {"id": result.submission_id}) is True
            allows = await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id.in_(["submission.create", "artifact.submission.binding.create"]),
            ))
            assert allows == 2
        async with h.factory() as session:
            replay = await compose_hidden_submission_creation_command(
                session, h.actor_context.model_copy(update={"request_id": new_record_id(), "correlation_id": new_record_id()}),
                request_id=new_record_id(), correlation_id=new_record_id(),
            ).create(h.creation_request)
        assert replay == result
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
            assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id.in_(["submission.create", "artifact.submission.binding.create"]),
            )) == allows


async def test_changed_request_cannot_create_or_repair_dispatch(tmp_path, isolated_database_env, monkeypatch):
    from dataclasses import replace
    import pytest
    from app.modules.tasks.api import SubmissionCreationUnavailable, TaskSubmissionContextUnavailable
    from app.modules.checkers.execution_coordination import EvaluationCoordinator
    from app.modules.outbox.service import OutboxService

    async with material_fixture(tmp_path, isolated_database_env) as h:
        async def forbidden(*args, **kwargs):
            pytest.fail("retry entered a creation participant")
        monkeypatch.setattr(EvaluationCoordinator, "reserve_current_evaluation", forbidden)
        monkeypatch.setattr(OutboxService, "append", forbidden)
        for field, value in {
            "task_id": new_record_id(), "assignment_id": new_record_id(),
            "contributor_id": new_record_id(), "admission_id": new_record_id(),
            "predecessor_submission_id": new_record_id(),
            "summary": "Different complete packet summary", "contributor_attestation": "Different valid attestation",
        }.items():
            async with h.factory() as session:
                with pytest.raises((SubmissionCreationUnavailable, TaskSubmissionContextUnavailable)):
                    await compose_hidden_submission_creation_command(
                        session, h.actor_context, request_id=new_record_id(), correlation_id=new_record_id(),
                    ).create(replace(h.creation_request, **{field: value}))
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
        async with h.factory() as session:
            assert await compose_hidden_submission_creation_command(
                session, h.actor_context, request_id=new_record_id(), correlation_id=new_record_id(),
            ).create(h.creation_request) == h.created


async def test_missing_dispatch_receipt_rejects_real_commit_and_rolls_back(tmp_path, isolated_database_env, monkeypatch):
    import pytest
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.exc import IntegrityError
    from app.modules.artifacts.models import SubmissionBundleAdmission, SubmissionBindingReceipt
    from app.modules.tasks.models import Submission
    from app.modules.tasks.submission_composition import TaskSubmissionCreationService

    add = AsyncSession.add
    create = TaskSubmissionCreationService.create
    staged = []

    def omit_only_dispatch(session, instance, **kwargs):
        if isinstance(instance, SubmissionDispatch):
            staged.append(instance)
            return
        return add(session, instance, **kwargs)

    async def observe_before_commit(service, request):
        result = await create(service, request)
        for model in (Submission, SubmissionBindingReceipt, CheckerRun, OutboxEvent):
            assert await service._session.scalar(select(func.count()).select_from(model)) == 1
        assert await service._session.scalar(select(SubmissionBundleAdmission.status)) == "consumed"
        return result

    monkeypatch.setattr(AsyncSession, "add", omit_only_dispatch)
    monkeypatch.setattr(TaskSubmissionCreationService, "create", observe_before_commit)
    with pytest.raises(IntegrityError, match="submission dispatch required"):
        async with material_fixture(tmp_path, isolated_database_env):
            pytest.fail("incomplete creation committed")
    assert len(staged) == 1 and staged[0].evaluation_event_id is not None
    engine = create_async_engine(isolated_database_env)
    try:
        async with async_sessionmaker(engine)() as session:
            for model in (Submission, SubmissionDispatch, SubmissionBindingReceipt, CheckerRun, OutboxEvent):
                assert await session.scalar(select(func.count()).select_from(model)) == 0
            assert await session.scalar(select(SubmissionBundleAdmission.status)) == "ready"
            assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id.in_(["submission.create", "artifact.submission.binding.create"]),
            )) == 0
    finally:
        await engine.dispose()
