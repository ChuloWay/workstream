"""Execution through real verified input, immutable results and shared outbox."""

import pytest
from sqlalchemy import select, func

from app.modules.checkers.api.execution import CheckerExecutionUnavailable, COMPLETION_EVENT
from app.modules.checkers.execution_coordination import EvaluationCoordinator
from app.modules.checkers.models import CheckerRun, CheckerResult
from app.modules.outbox.models import OutboxEvent
from tests.checkers.post_submit.support import request
from tests.post_submit_materialization_helpers import material_fixture
from .support import controlled_executor, denied_executor, reserve


@pytest.fixture
def autoflush_clock(monkeypatch):
    """Exercise a real ORM query flush at the database-clock boundary."""
    from app.modules.checkers.execution_repository import ExecutionRepository

    original = ExecutionRepository.now

    async def read_clock(repo):
        assert repo.session.autoflush
        # ORM SELECTs trigger autoflush even when the installed SQLAlchemy version
        # does not autoflush a scalar SQL-function SELECT. Keep real DB guards on.
        await repo.session.scalar(select(CheckerRun.id).limit(1))
        return await original(repo)

    monkeypatch.setattr(ExecutionRepository, "now", read_clock)


async def test_production_denies_before_access():
    with pytest.raises(CheckerExecutionUnavailable, match="post_submit_execution_unavailable"):
        await denied_executor().evaluate_post_submission(request())


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_verified_material_execution_and_replay(
    tmp_path, isolated_database_env, provider, autoflush_clock
):
    if provider == "minio":
        from tests.test_s3_artifact_store import provision_minio_bucket

        await provision_minio_bucket.__wrapped__()
    async with material_fixture(tmp_path, isolated_database_env, provider=provider) as h:
        reservation = await reserve(h)
        executor = controlled_executor(h)
        result = await executor.evaluate_post_submission(h.request)
        assert result.outcome == "completed"
        assert (
            result.attempt_id == reservation.attempt_id
            and result.result_id == reservation.result_id
        )
        result.validate_request(h.request)
        opened = len(h.store.opens)
        assert opened == 1
        assert await executor.evaluate_post_submission(h.request) == result
        assert len(h.store.opens) == opened
        async with h.factory() as session, session.begin():
            current = await EvaluationCoordinator(session).read_current_result(h.request)
            assert current.result == result
            assert current.routing_recommendation in {"allow_review", "needs_revision"}
            rows = list(
                await session.scalars(
                    select(CheckerResult)
                    .where(CheckerResult.checker_run_id == str(result.attempt_id))
                    .order_by(CheckerResult.member_order)
                )
            )
            assert tuple(row.checker_name for row in rows) == tuple(
                m.checker_id for m in result.member_results
            )
            assert len(rows) == len(h.request.policy.entries)
            event = await session.scalar(
                select(OutboxEvent).where(OutboxEvent.event_type == COMPLETION_EVENT)
            )
            assert event.payload["reference"]["result_digest"] == result.result_digest
            assert event.payload["output_binding_ids"] == []
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
        assert not h.preparation._active
        assert list((h.scratch / "workspaces").iterdir()) == []


async def test_infrastructure_failure_is_terminal(tmp_path, isolated_database_env, autoflush_clock):
    from app.modules.checkers.runner import CheckerRegistry

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = controlled_executor(h, registry=CheckerRegistry())
        failed = await executor.evaluate_post_submission(h.request)
        assert failed.outcome == "infrastructure_failed"
        assert failed.infrastructure_failure_code == "implementation_unavailable"
        assert failed.member_results == ()
        opens = len(h.store.opens)
        assert await executor.evaluate_post_submission(h.request) == failed
        assert len(h.store.opens) == opens == 1
        async with h.factory() as session, session.begin():
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(OutboxEvent.event_type == COMPLETION_EVENT)
                )
                == 0
            )
            with pytest.raises(CheckerExecutionUnavailable, match="current_result"):
                await EvaluationCoordinator(session).read_current_result(h.request)


@pytest.mark.parametrize("substitution", ["prepared", "receipt"])
async def test_action_authority_is_not_interchangeable(
    tmp_path, isolated_database_env, substitution
):
    from contextlib import asynccontextmanager
    from app.core.hashing import canonical_json_hash
    from app.core.identifiers import new_record_id
    from app.modules.checkers.api.execution import (
        PreparedExecution,
        PreparedFinalization,
        ExecuteEvidence,
        FinalizeEvidence,
    )
    from .test_concurrency import final_facts
    from .support import ControlledFinalizeAuthority

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = controlled_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = final_facts(h, lease)

        # Hold the other boundary valid so each type guard is independently exercised.
        class WrongPrepared(
            PreparedExecution if substitution == "prepared" else PreparedFinalization
        ):
            async def consume(self, value):
                receipt = FinalizeEvidence if substitution == "prepared" else ExecuteEvidence
                return receipt(
                    evidence_id=new_record_id(),
                    facts_digest=canonical_json_hash(value.model_dump(mode="json")),
                )

        class WrongAuthority(ControlledFinalizeAuthority):
            @asynccontextmanager
            async def prepare_finalization(self, request):
                yield WrongPrepared()

        executor._finalize_authority = lambda session: WrongAuthority()
        with pytest.raises(
            CheckerExecutionUnavailable, match="authority_unavailable|action_evidence_unavailable"
        ):
            await executor.finalize(facts)
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
            assert run.status == "running" and run.result_json is None
            assert await session.scalar(select(func.count()).select_from(CheckerResult)) == 0
        executor._finalize_authority = lambda session: ControlledFinalizeAuthority()
        assert await executor.finalize(facts) == facts.result


async def test_zero_output_finalization(tmp_path, isolated_database_env):
    from pydantic import ValidationError
    from app.core.identifiers import new_record_id
    from app.modules.checkers.api.output_custody import (
        CheckerOutputSelector,
        CheckerOutputUnavailable,
    )
    from app.modules.checkers.execution_coordination import CheckerOutputReservations
    from .test_concurrency import final_facts

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = controlled_executor(h)
        lease, _ = await executor._claim(h.request)
        selector = CheckerOutputSelector(
            evaluation=h.request,
            checker_run_id=lease.reservation.attempt_id,
            worker_lease_id=lease.lease_id,
            worker_lease_generation=lease.lease_generation,
            slot_key="invented",
        )
        async with h.factory() as session, session.begin():
            slots = await CheckerOutputReservations(session).resolve(selector)
            assert slots.slots == ()
            with pytest.raises(CheckerOutputUnavailable, match="slot_unavailable"):
                slots.select(selector)
        facts = final_facts(h, lease)
        with pytest.raises(ValidationError):
            await executor.finalize(
                facts.model_copy(update={"output_binding_ids": (new_record_id(),)})
            )
        assert await executor.finalize(facts) == facts.result
        async with h.factory() as session:
            from app.modules.artifacts.models import ArtifactBinding

            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactBinding)
                    .where(ArtifactBinding.resource_type == "checker_run")
                )
                == 0
            )


async def test_finalization_outbox_failure_rolls_back(tmp_path, isolated_database_env):
    from sqlalchemy import event, text
    from app.adapters.outbox import outbox_append
    from app.modules.outbox.api import OutboxPersistenceError
    from .test_concurrency import final_facts

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await reserve(h)
        executor = controlled_executor(h)
        lease, _ = await executor._claim(h.request)
        facts = final_facts(h, lease)
        async with h.factory() as session, session.begin():
            await session.execute(
                text("""create function test_checker_outbox_failure() returns trigger language plpgsql as $$
              begin if NEW.event_type='PostSubmissionEvaluationCompleted' then
                raise exception 'controlled checker completion insert failure' using errcode='23514';
              end if; return NEW; end $$""")
            )
            await session.execute(
                text(
                    "create trigger test_checker_outbox_failure before insert on outbox_events for each row execute function test_checker_outbox_failure()"
                )
            )
        observations = []

        def failed_insert(context):
            if "controlled checker completion insert failure" in str(context.original_exception):
                observations.append(
                    context.statement.lower().startswith("insert into outbox_events")
                )

        event.listen(h.engine.sync_engine, "handle_error", failed_insert)

        class ObservingAppend:
            def __init__(self, session):
                self.session = session

            async def append(self, value):
                assert await self.session.scalar(
                    select(func.count()).select_from(CheckerResult)
                ) == len(h.request.policy.entries)
                return await outbox_append(self.session).append(value)

        executor._outbox = ObservingAppend
        try:
            with pytest.raises(OutboxPersistenceError):
                await executor.finalize(facts)
            assert observations == [True]
            async with h.factory() as session:
                run = await session.get(CheckerRun, str(lease.reservation.attempt_id))
                assert (
                    run.status == "running"
                    and run.result_json is None
                    and run.completion_event_id is None
                )
                assert await session.scalar(select(func.count()).select_from(CheckerResult)) == 0
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(OutboxEvent)
                        .where(OutboxEvent.event_type == COMPLETION_EVENT)
                    )
                    == 0
                )
        finally:
            event.remove(h.engine.sync_engine, "handle_error", failed_insert)
            async with h.factory() as session, session.begin():
                await session.execute(
                    text("drop trigger test_checker_outbox_failure on outbox_events")
                )
                await session.execute(text("drop function test_checker_outbox_failure()"))
        executor._outbox = outbox_append
        assert await executor.finalize(facts) == facts.result
