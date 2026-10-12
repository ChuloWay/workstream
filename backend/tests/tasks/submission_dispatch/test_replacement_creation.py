"""Real checker-remediation creation races, replay, and rollback."""

import asyncio

import pytest
from sqlalchemy import func, select, text

from app.adapters.checkers import evaluation_coordinator
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.core.identifiers import new_record_id
from app.modules.artifacts.models import SubmissionBundleAdmission
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.api import OutboxPersistenceError
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.api import (
    SubmissionCreationRequest,
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.models import Submission, SubmissionDispatch
from app.modules.tasks.repository import TaskRepository
from tests.checkers.post_submit.support import change_request
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import revision_archive
from tests.tasks.submission_lineage_support import _verified_admission
from tests.test_submission_predecessor_custody import (
    _fixture_revision_context,
    _prepare,
    _replacement_request,
)


async def _ready_replacement(h, data: bytes):
    """Prepare once, then replay through the independent verifier to ready."""
    idempotency_key = new_record_id()
    request = _replacement_request(
        h,
        data,
        predecessor_id=h.created.submission_id,
        idempotency_key=idempotency_key,
    )
    prepared = await _prepare(h, request)
    assert prepared.replayed is False
    assert prepared.put_attempt_id is not None
    assert prepared.admission_id is None
    replay = _replacement_request(
        h,
        data,
        predecessor_id=h.created.submission_id,
        idempotency_key=idempotency_key,
    )
    admission_id = await _verified_admission(
        h.factory,
        h.store,
        h.namespace,
        h.settings,
        h.actor_context,
        replay,
    )
    return request, admission_id


def _creation_request(h, prepared, admission_id):
    return SubmissionCreationRequest(
        task_id=h.request.task_id,
        assignment_id=h.request.assignment_id,
        contributor_id=h.actor_context.actor_profile_id,
        predecessor_submission_id=h.created.submission_id,
        admission_id=admission_id,
        summary=prepared.summary,
        contributor_attestation=prepared.contributor_attestation,
    )


async def _create(h, request, *, context=None, label=None):
    async with h.factory() as session:
        if label is not None:
            session.info["replacement_creation_contender"] = label
        return await compose_hidden_submission_creation_command(
            session,
            context or h.actor_context,
            request_id=new_record_id(),
            correlation_id=new_record_id(),
        ).create(request)


async def _creation_snapshot(h):
    """Capture every mutable owner participating in canonical creation."""
    async with h.factory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT
                      (SELECT jsonb_agg(to_jsonb(s) ORDER BY s.id)
                         FROM public.submissions s),
                      (SELECT jsonb_agg(to_jsonb(d) ORDER BY d.submission_id)
                         FROM public.submission_dispatches d),
                      (SELECT jsonb_agg(to_jsonb(b) ORDER BY b.id)
                         FROM public.artifact_bindings b),
                      (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.admission_id)
                         FROM public.submission_binding_receipts r),
                      (SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id)
                         FROM public.submission_bundle_admissions a),
                      (SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id)
                         FROM public.audit_events e
                        WHERE e.action_id IN (
                          'submission.create',
                          'artifact.submission.binding.create'
                        )),
                      (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id)
                         FROM public.checker_runs r),
                      (SELECT jsonb_agg(to_jsonb(f) ORDER BY f.submission_id)
                         FROM public.checker_submission_fences f),
                      (SELECT jsonb_agg(to_jsonb(e) ORDER BY e.event_id)
                         FROM public.outbox_events e),
                      (SELECT jsonb_agg(to_jsonb(t) ORDER BY t.id)
                         FROM public.workstream_tasks t)
                    """
                )
            )
        ).one()
    return tuple(row)


async def _admission_status(h, admission_id):
    async with h.factory() as session:
        admission = await session.get(SubmissionBundleAdmission, str(admission_id))
        assert admission is not None
        return admission.status


async def test_stale_routed_cause_denies_before_ready_admission_consumption(
    tmp_path,
    isolated_database_env,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        prepared, admission_id = await _ready_replacement(h, revision_archive(h.data))
        creation = _creation_request(h, prepared, admission_id)

        successor = change_request(
            h.request,
            evaluation_request_id=new_record_id(),
            evaluation_generation=h.request.evaluation_generation + 1,
        )
        async with h.factory() as session, session.begin():
            reserved = await evaluation_coordinator(session).reserve_current_evaluation(successor)
        assert reserved.request_id == successor.evaluation_request_id
        assert await _admission_status(h, admission_id) == "ready"
        before = await _creation_snapshot(h)

        with pytest.raises(TaskSubmissionContextUnavailable):
            await _create(h, creation)

        assert await _creation_snapshot(h) == before
        assert await _admission_status(h, admission_id) == "ready"
        async with h.factory() as session:
            assert await session.scalar(
                select(func.count()).select_from(Submission).where(
                    Submission.task_id == str(h.request.task_id),
                    Submission.version == 2,
                )
            ) == 0


async def test_competing_ready_admissions_commit_one_and_winner_replays_exactly(
    tmp_path,
    isolated_database_env,
    monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        first_prepared, first_admission = await _ready_replacement(
            h, revision_archive(h.data)
        )
        second_prepared, second_admission = await _ready_replacement(
            h, revision_archive(revision_archive(h.data))
        )
        assert first_admission != second_admission
        first_request = _creation_request(h, first_prepared, first_admission)
        second_request = _creation_request(h, second_prepared, second_admission)
        assert await _admission_status(h, first_admission) == "ready"
        assert await _admission_status(h, second_admission) == "ready"

        held = asyncio.Event()
        release = asyncio.Event()
        contender_entered = asyncio.Event()
        contender_pid = []
        original_get_task = TaskRepository.get_task

        async def pause_with_task_lock(repository, *args, **kwargs):
            label = repository._session.info.pop(
                "replacement_creation_contender", None
            )
            if label == "second":
                contender_pid.append(
                    await repository._session.scalar(
                        text("SELECT pg_catalog.pg_backend_pid()")
                    )
                )
                contender_entered.set()
            task = await original_get_task(repository, *args, **kwargs)
            if label == "first":
                held.set()
                await asyncio.wait_for(release.wait(), 15)
            return task

        first = second = None
        with monkeypatch.context() as patch:
            patch.setattr(TaskRepository, "get_task", pause_with_task_lock)
            try:
                first = asyncio.create_task(
                    _create(h, first_request, label="first")
                )
                await asyncio.wait_for(held.wait(), 15)
                second = asyncio.create_task(
                    _create(h, second_request, label="second")
                )
                await asyncio.wait_for(contender_entered.wait(), 15)
                async with h.factory() as observer:
                    async with asyncio.timeout(10):
                        while not await observer.scalar(
                            text(
                                "SELECT cardinality(pg_catalog.pg_blocking_pids(:pid)) > 0"
                            ),
                            {"pid": contender_pid[0]},
                        ):
                            await asyncio.sleep(0.02)
                assert not second.done()
                release.set()
                results = await asyncio.wait_for(
                    asyncio.gather(first, second, return_exceptions=True), 30
                )
            finally:
                release.set()
                for pending in (first, second):
                    if pending is not None and not pending.done():
                        pending.cancel()
                await asyncio.gather(
                    *(pending for pending in (first, second) if pending is not None),
                    return_exceptions=True,
                )

        winner, loser = results
        assert not isinstance(winner, BaseException), winner
        assert isinstance(loser, TaskSubmissionContextUnavailable), loser
        assert winner.admission_id == first_admission
        assert await _admission_status(h, first_admission) == "consumed"
        assert await _admission_status(h, second_admission) == "ready"

        async with h.factory() as session:
            dispatch = await session.get(SubmissionDispatch, str(winner.submission_id))
            run = await session.get(CheckerRun, str(winner.evaluation_attempt_id))
            event = await session.get(OutboxEvent, winner.evaluation_event_id)
            assert dispatch is not None
            assert dispatch.checker_remediation_manifest_id == source_id
            assert dispatch.creation_kind == "checker_remediation"
            assert run is not None and run.evaluation_generation == 1
            assert event is not None
            assert await session.scalar(
                select(func.count()).select_from(Submission).where(
                    Submission.task_id == str(h.request.task_id),
                    Submission.version == 2,
                )
            ) == 1

        committed = await _creation_snapshot(h)
        fresh_context = h.actor_context.model_copy(
            update={
                "request_id": new_record_id(),
                "correlation_id": new_record_id(),
            }
        )
        replay = await _create(h, first_request, context=fresh_context)
        assert replay == winner
        assert await _creation_snapshot(h) == committed


async def test_late_outbox_insert_failure_rolls_back_and_ready_retry_succeeds(
    tmp_path,
    isolated_database_env,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        prepared, admission_id = await _ready_replacement(h, revision_archive(h.data))
        creation = _creation_request(h, prepared, admission_id)
        before = await _creation_snapshot(h)

        async with h.factory() as session, session.begin():
            await session.execute(
                text("CREATE SEQUENCE public.test_replacement_outbox_attempt")
            )
            await session.execute(
                text(
                    """
                    CREATE FUNCTION public.test_replacement_outbox_failure()
                    RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN
                      PERFORM nextval('public.test_replacement_outbox_attempt');
                      RAISE EXCEPTION 'controlled replacement outbox insert failure'
                        USING ERRCODE='23514';
                    END $$
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TRIGGER test_replacement_outbox_failure
                    BEFORE INSERT ON public.outbox_events
                    FOR EACH ROW
                    WHEN (NEW.event_type='PostSubmissionEvaluationRequested')
                    EXECUTE FUNCTION public.test_replacement_outbox_failure()
                    """
                )
            )

        try:
            with pytest.raises(
                OutboxPersistenceError, match="outbox_persistence_failed"
            ):
                await _create(h, creation)
            async with h.factory() as session:
                assert (
                    await session.execute(
                        text(
                            "SELECT last_value,is_called "
                            "FROM public.test_replacement_outbox_attempt"
                        )
                    )
                ).one() == (1, True)
            assert await _creation_snapshot(h) == before
            assert await _admission_status(h, admission_id) == "ready"
        finally:
            async with h.factory() as session, session.begin():
                await session.execute(
                    text(
                        "DROP TRIGGER IF EXISTS test_replacement_outbox_failure "
                        "ON public.outbox_events"
                    )
                )
                await session.execute(
                    text(
                        "DROP FUNCTION IF EXISTS "
                        "public.test_replacement_outbox_failure()"
                    )
                )
                await session.execute(
                    text(
                        "DROP SEQUENCE IF EXISTS "
                        "public.test_replacement_outbox_attempt"
                    )
                )

        created = await _create(h, creation)
        assert created.submission_version == 2
        assert created.admission_id == admission_id
        assert await _admission_status(h, admission_id) == "consumed"
        async with h.factory() as session:
            dispatch = await session.get(SubmissionDispatch, str(created.submission_id))
            assert dispatch is not None
            assert dispatch.checker_remediation_manifest_id == source_id
            assert await session.scalar(
                text(
                    "SELECT public.submission_dispatch_valid(d) "
                    "FROM public.submission_dispatches d "
                    "WHERE d.submission_id=:submission_id"
                ),
                {"submission_id": created.submission_id},
            ) is True
