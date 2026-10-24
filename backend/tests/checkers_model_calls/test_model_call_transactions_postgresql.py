from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.model_usage.api import (
    KnownNoEffectProof,
    ModelBudgetProvisioningFacts,
    ModelCallBudgetUnavailable,
    ModelCallConflict,
    ModelCallEvidence,
    ModelCallExecutionFacts,
    ModelCallUsage,
    ModelCallUnavailable,
    ModelGenerationSettings,
    ModelPaidSlotKey,
    ModelPricing,
    ModelProfileProvisioningFacts,
    ProjectModelBudgetConfigurationSpec,
    ProjectModelProfileSpec,
    SetupModelUsageSlotKey,
    model_retry_terminal_digest,
    model_usage_instant,
)
from app.modules.model_usage.models import ModelUsageBudgetAccount
from app.modules.model_usage.service import ModelCallService
from app.modules.model_usage.setup import SetupModelUsageService
from tests.checkers_model_calls.model_usage_pg_support import (
    DatabaseFacts,
    model_database as _model_database,
)
from tests.checkers_model_calls.model_usage_boundary_support import (
    BoundaryPorts,
    DatabaseBoundaryPorts,
)

model_database = _model_database


def sha(label: str) -> str:
    return canonical_json_hash({"label": label})


def service(session: AsyncSession, ports: BoundaryPorts) -> ModelCallService:
    boundaries = DatabaseBoundaryPorts(session, ports)
    return ModelCallService(
        session,
        authority=boundaries,
        current_execution=boundaries,
        evidence=boundaries,
    )


def setup_service(session: AsyncSession, ports: BoundaryPorts) -> SetupModelUsageService:
    boundaries = DatabaseBoundaryPorts(session, ports)
    return SetupModelUsageService(
        session,
        authority=boundaries,
        evidence=boundaries,
        owner=boundaries,
    )


async def setup_slot_key(
    facts: DatabaseFacts,
    profile,
    *,
    call_index: int = 0,
) -> SetupModelUsageSlotKey:
    attempt_id = new_record_id()
    guide_id = new_record_id()
    snapshot_id = new_record_id()
    setup_run_id = new_record_id()
    runtime_configuration = {
        "model_provider": profile.spec.provider,
        "model_api": profile.spec.api,
        "model": profile.spec.model_snapshot,
        "model_profile_id": str(profile.profile_id),
        "model_profile_version": profile.spec.profile_version,
        "model_profile_digest": profile.profile_digest,
    }
    runtime_hash = canonical_json_hash(runtime_configuration)
    async with facts.engine.begin() as connection:
        await connection.execute(
            text(
                "insert into project_guide_compilation_attempts(id,project_id,guide_id,source_snapshot_id,setup_run_id,setup_generation,runtime_configuration,runtime_configuration_hash,status) values(:id,:project,:guide,:snapshot,:run,1,cast(:configuration as jsonb),:runtime,'compilation_reserved')"
            ),
            {
                "id": attempt_id,
                "project": facts.project_id,
                "guide": guide_id,
                "snapshot": snapshot_id,
                "run": setup_run_id,
                "configuration": json.dumps(runtime_configuration),
                "runtime": runtime_hash,
            },
        )
    return SetupModelUsageSlotKey(
        compilation_attempt_id=attempt_id,
        project_id=facts.project_id,
        guide_id=guide_id,
        source_snapshot_id=snapshot_id,
        setup_run_id=setup_run_id,
        setup_generation=1,
        runtime_configuration_hash=runtime_hash,
        profile_id=profile.profile_id,
        profile_version=profile.spec.profile_version,
        profile_digest=profile.profile_digest,
        phase="draft",
        call_index=call_index,
    )


async def provision(
    facts: DatabaseFacts,
    ports: BoundaryPorts,
    *,
    limit: int,
    replay: bool = False,
    profile_changes: dict | None = None,
):
    profile_spec = ProjectModelProfileSpec(
        project_id=facts.project_id,
        profile_version=1,
        provider="openai_responses",
        api="responses.v1",
        model_snapshot="gpt-example-2026-10-01",
        settings=ModelGenerationSettings(reasoning_effort="medium", text_verbosity="low"),
        maximum_request_bytes=10_000,
        maximum_output_bytes=4_000,
        maximum_response_bytes=30_000,
        maximum_input_tokens=100,
        maximum_output_tokens=50,
        maximum_calls=1,
        maximum_total_request_bytes=10_000,
        maximum_total_response_bytes=30_000,
        maximum_total_input_tokens=100,
        maximum_total_output_tokens=50,
        allowed_tools=(),
        maximum_tool_calls=0,
        maximum_tool_output_bytes=0,
        deadline_ms=30_000,
        pricing=ModelPricing(
            pricing_policy_id=new_record_id(),
            pricing_policy_version=1,
            pricing_policy_digest=sha("pricing"),
            uncached_input_nanodollars_per_token=11,
            cached_input_nanodollars_per_token=2,
            output_nanodollars_per_token=29,
        ),
    )
    if profile_changes:
        profile_spec = profile_spec.model_copy(update=profile_changes)
    profile_facts = ModelProfileProvisioningFacts(
        operation_id=uuid4(),
        actor_profile_id=new_record_id(),
        spec=profile_spec,
        profile_digest=canonical_json_hash(profile_spec.model_dump(mode="json")),
    )
    budget_spec = ProjectModelBudgetConfigurationSpec(
        project_id=facts.project_id,
        configuration_version=1,
        authorized_total_nanodollars=10_000_000_000,
        externally_reconciled_prior_spend_nanodollars=0,
        lifetime_limit_nanodollars=limit,
    )
    budget_facts = ModelBudgetProvisioningFacts(
        operation_id=uuid4(),
        actor_profile_id=new_record_id(),
        spec=budget_spec,
        configuration_digest=canonical_json_hash(budget_spec.model_dump(mode="json")),
    )
    async with AsyncSession(facts.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            profile = await owner.provision_profile(profile_facts)
            budget = await owner.provision_budget(budget_facts)
            if replay:
                replayed_profile = await owner.provision_profile(profile_facts)
                replayed_budget = await owner.provision_budget(budget_facts)
                assert replayed_profile.authorization_evidence_id == (
                    profile.authorization_evidence_id
                )
                assert replayed_budget.authorization_evidence_id == (
                    budget.authorization_evidence_id
                )
    return profile


def execution(facts: DatabaseFacts) -> ModelCallExecutionFacts:
    return ModelCallExecutionFacts(
        project_id=facts.project_id,
        task_id=facts.task_id,
        assignment_id=facts.assignment_id,
        submission_id=facts.submission_id,
        submission_version=1,
        evaluation_request_id=new_record_id(),
        evaluation_generation=1,
        checker_run_id=new_record_id(),
        worker_lease_id=new_record_id(),
        worker_lease_generation=1,
        worker_lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


async def insert_checker_run(session: AsyncSession, run: ModelCallExecutionFacts) -> None:
    """Persist the exact running lease used by a recovery attachment."""
    await session.execute(
        text(
            "insert into checker_runs(id,task_id,submission_id,submission_version,project_id,"
            "evaluation_request_id,phase,evaluation_generation,request_json,worker_lease_id,"
            "worker_lease_generation,worker_lease_expires_at,status) values "
            "(:id,:task,:submission,:version,:project,:request,'post_submission',:generation,"
            ":request_json,:lease,:lease_generation,:expires,'running')"
        ),
        {
            "id": run.checker_run_id,
            "task": run.task_id,
            "submission": run.submission_id,
            "version": run.submission_version,
            "project": run.project_id,
            "request": run.evaluation_request_id,
            "generation": run.evaluation_generation,
            "request_json": json.dumps({"assignment_id": str(run.assignment_id)}),
            "lease": run.worker_lease_id,
            "lease_generation": run.worker_lease_generation,
            "expires": run.worker_lease_expires_at,
        },
    )


def slot(facts: DatabaseFacts, profile, requirement: str) -> ModelPaidSlotKey:
    return ModelPaidSlotKey(
        project_id=facts.project_id,
        assignment_id=facts.assignment_id,
        submission_id=facts.submission_id,
        submission_version=1,
        requirement_id=requirement,
        registry_entry_digest=facts.registry_entry_digest,
        configuration_sha256=sha("configuration"),
        profile_id=profile.profile_id,
        profile_version=profile.spec.profile_version,
        profile_digest=profile.profile_digest,
    )


def evidence(label: str, content_sha256: str) -> ModelCallEvidence:
    return ModelCallEvidence(
        binding_id=new_record_id(),
        content_id=new_record_id(),
        put_attempt_id=new_record_id(),
        verification_receipt_id=new_record_id(),
        content_sha256=content_sha256,
        byte_count=100,
    )


async def wait_until_blocked_by(
    engine: AsyncEngine,
    *,
    blocked_pid: int,
    blocker_pid: int,
) -> None:
    """Observe an actual PostgreSQL lock wait instead of inferring final totals."""
    for _ in range(200):
        async with engine.connect() as connection:
            blockers = await connection.scalar(
                text("select pg_blocking_pids(:pid)"), {"pid": blocked_pid}
            )
        if blocker_pid in blockers:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"backend {blocked_pid} did not block behind backend {blocker_pid}")


async def prepare_and_reserve(
    facts: DatabaseFacts,
    ports: BoundaryPorts,
    profile,
    requirement: str,
):
    run = execution(facts)
    paid_slot = slot(facts, profile, requirement)
    request_sha = sha(f"request-{requirement}")
    request_evidence = evidence(f"request-{requirement}", request_sha)
    async with AsyncSession(facts.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            prepared = await owner.prepare_attempt(
                run,
                paid_slot,
                registry_entry_id=facts.registry_entry_id,
                request_sha256=request_sha,
            )
            reservation = await owner.reserve_dispatch(run, prepared, request_evidence)
    return run, paid_slot, prepared, reservation, request_evidence


async def finish_for_lock_order(session, ports, dispatched, profile, terminal_kind):
    """Run either supported terminal mutation behind the same parent lock."""
    owner = service(session, ports)
    if terminal_kind == "complete":
        await owner.complete(
            dispatched.effect,
            provider_response_id="resp_lock_order",
            provider_model_snapshot=profile.spec.model_snapshot,
            response_evidence=evidence("terminal-order-response", sha("terminal-order-response")),
            usage=ModelCallUsage(
                input_tokens=40,
                cached_input_tokens=10,
                output_tokens=12,
                reasoning_tokens=7,
            ),
        )
        return
    await owner.mark_known_no_effect(
        dispatched.effect,
        KnownNoEffectProof(
            proof_id=new_record_id(),
            proof_digest=sha("terminal-order-no-effect"),
            observed_at=datetime.now(UTC),
        ),
    )


@pytest.mark.parametrize("terminal_kind", ["complete", "known_no_effect"])
async def test_terminal_holds_envelope_before_other_slot_and_account(
    model_database: DatabaseFacts,
    terminal_kind: str,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(
        model_database,
        ports,
        limit=reservation * 2,
        profile_changes={
            "maximum_calls": 2,
            "maximum_total_request_bytes": 20_000,
            "maximum_total_response_bytes": 60_000,
            "maximum_total_input_tokens": 200,
            "maximum_total_output_tokens": 100,
        },
    )
    run = execution(model_database)
    first_slot = slot(model_database, profile, f"terminal_order_{terminal_kind}")
    second_slot = first_slot.model_copy(update={"slot_index": 1})
    first_sha = sha(f"terminal-order-{terminal_kind}-first")
    second_sha = sha(f"terminal-order-{terminal_kind}-second")
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            first_prepared = await owner.prepare_attempt(
                run,
                first_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=first_sha,
            )
            first_dispatched = await owner.reserve_dispatch(
                run,
                first_prepared,
                evidence("terminal-order-first", first_sha),
            )
            second_prepared = await owner.prepare_attempt(
                run,
                second_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=second_sha,
            )

    holder = AsyncSession(model_database.engine, expire_on_commit=False)
    terminal = AsyncSession(model_database.engine, expire_on_commit=False)
    contender = AsyncSession(model_database.engine, expire_on_commit=False)
    terminal_task = None
    contender_task = None
    try:
        await holder.begin()
        await terminal.begin()
        await contender.begin()
        holder_pid = await holder.scalar(text("select pg_backend_pid()"))
        terminal_pid = await terminal.scalar(text("select pg_backend_pid()"))
        contender_pid = await contender.scalar(text("select pg_backend_pid()"))
        await holder.execute(
            text(
                "select project_id from model_usage_budget_accounts where project_id=:project_id for update"
            ),
            {"project_id": model_database.project_id},
        )

        terminal_task = asyncio.create_task(
            finish_for_lock_order(terminal, ports, first_dispatched, profile, terminal_kind)
        )
        await wait_until_blocked_by(
            model_database.engine,
            blocked_pid=terminal_pid,
            blocker_pid=holder_pid,
        )

        contender_task = asyncio.create_task(
            service(contender, ports).reserve_dispatch(
                run,
                second_prepared,
                evidence("terminal-order-second", second_sha),
            )
        )
        await wait_until_blocked_by(
            model_database.engine,
            blocked_pid=contender_pid,
            blocker_pid=terminal_pid,
        )

        # The contender is waiting at the run envelope; it owns neither child row.
        async with AsyncSession(model_database.engine) as observer:
            async with observer.begin():
                await observer.execute(
                    text("select id from checker_model_usage_slots where id=:id for update nowait"),
                    {"id": second_prepared.slot_id},
                )
                await observer.execute(
                    text("select id from model_usage_effects where id=:id for update nowait"),
                    {"id": second_prepared.attempt_id},
                )

        await holder.commit()
        await terminal_task
        await terminal.commit()
        await contender_task
        await contender.commit()
    finally:
        for task in (terminal_task, contender_task):
            if task is not None and not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        for session in (holder, terminal, contender):
            if session.in_transaction():
                await session.rollback()
            await session.close()

    async with AsyncSession(model_database.engine) as session:
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        assert account.lifetime_reserved_nanodollars == reservation
        if terminal_kind == "complete":
            assert account.lifetime_settled_nanodollars == 30 * 11 + 10 * 2 + 12 * 29
        else:
            assert account.lifetime_settled_nanodollars == 0


async def test_uncertain_holds_budget_and_only_proven_no_effect_allows_child(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation * 2)
    run, paid_slot, prepared, dispatched, _ = await prepare_and_reserve(
        model_database, ports, profile, "model_recovery"
    )
    uncertainty = sha("uncertain-delivery")
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            with pytest.raises(ModelCallUnavailable, match="model_call_effect_unavailable"):
                await owner.mark_uncertain(
                    dispatched.effect.model_copy(update={"task_id": new_record_id()}),
                    uncertainty,
                    provider_response_id="resp_recoverable",
                )
            observed = await owner.mark_uncertain(
                dispatched.effect,
                uncertainty,
                provider_response_id="resp_recoverable",
            )
            assert observed.state == "uncertain"
            with pytest.raises(ModelCallConflict, match="not_retryable"):
                await owner.prepare_recovery_child(
                    paid_slot,
                    registry_entry_id=model_database.registry_entry_id,
                    parent_attempt_id=prepared.attempt_id,
                    terminal_digest=uncertainty,
                    request_sha256=prepared.request_sha256,
                )
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == reservation

    # A distinct call proves the only zero-cost child path: authenticated no effect.
    run2, paid_slot2, prepared2, dispatched2, _ = await prepare_and_reserve(
        model_database, ports, profile, "model_no_effect"
    )
    proof = KnownNoEffectProof(
        proof_id=new_record_id(),
        proof_digest=sha("provider-no-effect"),
        observed_at=datetime(
            2026,
            10,
            24,
            5,
            30,
            0,
            123_000,
            tzinfo=timezone(timedelta(hours=5, minutes=30)),
        ),
    )
    assert model_usage_instant(proof.observed_at) == "2026-10-24T00:00:00.123+00:00"
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            await owner.mark_known_no_effect(dispatched2.effect, proof)
            child = await owner.prepare_recovery_child(
                paid_slot2,
                registry_entry_id=model_database.registry_entry_id,
                parent_attempt_id=prepared2.attempt_id,
                terminal_digest=model_retry_terminal_digest(proof),
                request_sha256=prepared2.request_sha256,
            )
            assert child.attempt_number == 2
            assert child.state == "prepared"
            with pytest.raises(ModelCallConflict, match="parent_not_retryable"):
                await owner.prepare_recovery_child(
                    paid_slot2,
                    registry_entry_id=model_database.registry_entry_id,
                    parent_attempt_id=prepared2.attempt_id,
                    terminal_digest=sha("substituted-terminal"),
                    request_sha256=prepared2.request_sha256,
                )
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == reservation


async def test_budget_adjustment_preserves_reserved_and_settles_old_snapshot(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation)
    _run, _paid_slot, _prepared, dispatched, _ = await prepare_and_reserve(
        model_database, ports, profile, "model_budget_adjustment"
    )
    adjusted_spec = ProjectModelBudgetConfigurationSpec(
        project_id=model_database.project_id,
        configuration_version=2,
        authorized_total_nanodollars=20_000_000_000,
        externally_reconciled_prior_spend_nanodollars=123,
        lifetime_limit_nanodollars=reservation * 3,
    )
    adjusted_facts = ModelBudgetProvisioningFacts(
        operation_id=uuid4(),
        actor_profile_id=new_record_id(),
        spec=adjusted_spec,
        configuration_digest=canonical_json_hash(adjusted_spec.model_dump(mode="json")),
    )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            adjusted = await service(session, ports).provision_budget(adjusted_facts)
            assert adjusted.lifetime_reserved_nanodollars == reservation
            assert adjusted.lifetime_settled_nanodollars == 0

    # The explicitly increased ceiling admits another dispatch without resetting
    # the first reservation or counting ledger usage as external prior spend.
    _second = await prepare_and_reserve(
        model_database, ports, profile, "model_budget_adjustment_second"
    )

    too_low_spec = ProjectModelBudgetConfigurationSpec(
        project_id=model_database.project_id,
        configuration_version=3,
        authorized_total_nanodollars=20_000_000_000,
        externally_reconciled_prior_spend_nanodollars=123,
        lifetime_limit_nanodollars=reservation * 2 - 1,
    )
    too_low_facts = ModelBudgetProvisioningFacts(
        operation_id=uuid4(),
        actor_profile_id=new_record_id(),
        spec=too_low_spec,
        configuration_digest=canonical_json_hash(too_low_spec.model_dump(mode="json")),
    )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        with pytest.raises(ModelCallBudgetUnavailable, match="below_lifetime_usage"):
            async with session.begin():
                await service(session, ports).provision_budget(too_low_facts)

    usage = ModelCallUsage(
        input_tokens=31,
        cached_input_tokens=7,
        output_tokens=11,
        reasoning_tokens=4,
    )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            completed = await service(session, ports).complete(
                dispatched.effect,
                provider_response_id="resp_after_budget_adjustment",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=evidence("response", sha("budget-adjustment-response")),
                usage=usage,
            )
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
            assert account.current_configuration_id == str(adjusted.configuration_id)
            assert account.lifetime_reserved_nanodollars == reservation
            assert account.lifetime_settled_nanodollars == completed.settled_nanodollars

    next_spec = ProjectModelBudgetConfigurationSpec(
        project_id=model_database.project_id,
        configuration_version=3,
        authorized_total_nanodollars=30_000_000_000,
        externally_reconciled_prior_spend_nanodollars=456,
        lifetime_limit_nanodollars=reservation * 4,
    )
    next_facts = ModelBudgetProvisioningFacts(
        operation_id=uuid4(),
        actor_profile_id=new_record_id(),
        spec=next_spec,
        configuration_digest=canonical_json_hash(next_spec.model_dump(mode="json")),
    )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            next_budget = await service(session, ports).provision_budget(next_facts)
            replayed_old = await service(session, ports).provision_budget(adjusted_facts)
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
            assert replayed_old.configuration_id == adjusted.configuration_id
            assert account.current_configuration_id == str(next_budget.configuration_id)
            assert account.lifetime_reserved_nanodollars == reservation
            assert account.lifetime_settled_nanodollars == completed.settled_nanodollars

    for authorized_total, reconciled_prior in (
        (29_000_000_000, 456),
        (30_000_000_000, 455),
    ):
        shrinking_spec = ProjectModelBudgetConfigurationSpec(
            project_id=model_database.project_id,
            configuration_version=4,
            authorized_total_nanodollars=authorized_total,
            externally_reconciled_prior_spend_nanodollars=reconciled_prior,
            lifetime_limit_nanodollars=reservation * 4,
        )
        shrinking_facts = ModelBudgetProvisioningFacts(
            operation_id=uuid4(),
            actor_profile_id=new_record_id(),
            spec=shrinking_spec,
            configuration_digest=canonical_json_hash(shrinking_spec.model_dump(mode="json")),
        )
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            with pytest.raises(ModelCallConflict, match="reconciliation_conflict"):
                async with session.begin():
                    await service(session, ports).provision_budget(shrinking_facts)


async def test_database_guards_reject_ledger_mutation_and_counter_substitution(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation * 2)
    _, _, _, dispatched, _ = await prepare_and_reserve(
        model_database, ports, profile, "model_guarded"
    )

    async with AsyncSession(model_database.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await session.execute(
                    text(
                        "update checker_model_usage_slots set first_request_sha256=:digest where id=:slot_id"
                    ),
                    {"digest": sha("substituted"), "slot_id": dispatched.slot_id},
                )

    async with AsyncSession(model_database.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await session.execute(
                    text(
                        "update model_usage_budget_accounts set lifetime_reserved_nanodollars=lifetime_reserved_nanodollars-1 where project_id=:project_id"
                    ),
                    {"project_id": model_database.project_id},
                )

    async with AsyncSession(model_database.engine) as session:
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        assert account.lifetime_reserved_nanodollars == reservation
        assert account.lifetime_settled_nanodollars == 0


async def test_database_ancestry_prevents_receipt_and_artifact_deletion(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    profile = await provision(model_database, ports, limit=10_000)
    _, _, _, _, request = await prepare_and_reserve(
        model_database, ports, profile, "model_ancestry"
    )
    for statement, identifier in (
        ("delete from actor_profiles where id=:id", profile.actor_profile_id),
        ("delete from audit_events where id=:id", profile.authorization_evidence_id),
        ("delete from artifact_bindings where id=:id", request.binding_id),
        ("delete from artifact_contents where id=:id", request.content_id),
        ("delete from artifact_put_attempts where id=:id", request.put_attempt_id),
        (
            "delete from artifact_verification_receipts where id=:id",
            request.verification_receipt_id,
        ),
    ):
        async with AsyncSession(model_database.engine) as session:
            with pytest.raises(DBAPIError):
                async with session.begin():
                    await session.execute(text(statement), {"id": identifier})
