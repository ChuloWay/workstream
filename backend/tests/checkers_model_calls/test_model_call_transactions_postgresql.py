from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import asyncio
import json
from pathlib import Path
import runpy
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.authorization.domain.checker_models import (
    BUDGET_CONFIGURE,
    PROFILE_PROVISION,
    project_model_admin_resource,
)
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.checkers.api.model_calls import (
    KnownNoEffectProof,
    ModelActionEvidence,
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
    model_action_digest,
    model_retry_terminal_digest,
)
from app.modules.checkers.model_calls.models import CheckerModelBudgetAccount
from app.modules.checkers.model_calls.profiles import ModelProfileReader
from app.modules.checkers.model_calls.service import ModelCallService


def sha(label: str) -> str:
    return canonical_json_hash({"label": label})


@dataclass(frozen=True)
class DatabaseFacts:
    engine: AsyncEngine
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    submission_id: UUID
    registry_entry_id: UUID
    registry_entry_digest: str


@pytest.fixture
async def model_database(postgres_database_url: str):
    schema = f"model_calls_{uuid4().hex}"
    engine = create_async_engine(
        postgres_database_url,
        connect_args={"server_settings": {"search_path": schema}},
    )
    project_id = new_record_id()
    task_id = new_record_id()
    assignment_id = new_record_id()
    submission_id = new_record_id()
    registry_entry_id = new_record_id()
    registry_entry_digest = sha("registry")
    migration = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "alembic/versions/0059_checker_model_runtime.py")
    )

    def isolated(statement: str) -> str:
        return statement.replace("public.", f'"{schema}".').replace(
            "pg_catalog,public,pg_temp", f'pg_catalog,"{schema}",pg_temp'
        )

    async with engine.begin() as connection:
        await connection.execute(text(f'create schema "{schema}"'))
        for statement in (
            "create table projects(id uuid primary key)",
            "create table workstream_tasks(id uuid primary key, project_id uuid not null, "
            "unique(id,project_id))",
            "create table task_assignments(id uuid primary key, task_id uuid not null, "
            "project_id uuid not null)",
            "create table submissions(id uuid primary key, task_id uuid not null, "
            "version integer not null, unique(id,task_id,version))",
            "create table external_checker_registry_entries(id uuid primary key)",
            "create table checker_runs(id uuid primary key)",
            "create table actor_profiles(id uuid primary key)",
            "create table audit_events(id uuid primary key, event_domain text, event_type text, "
            "actor_ref_kind text, actor_id text, action_id text, permission_id text, "
            "denial_code text, after_facts jsonb)",
            "create table artifact_bindings(id uuid primary key)",
            "create table artifact_contents(id uuid primary key)",
            "create table artifact_put_attempts(id uuid primary key)",
            "create table artifact_verification_receipts(id uuid primary key)",
        ):
            await connection.execute(text(statement))
        for statement in migration["_TABLES"]:
            await connection.execute(text(isolated(statement)))
        for statement in migration["_FUNCTIONS"]:
            await connection.execute(text(isolated(statement)))
        for statement in migration["_TRIGGERS"]:
            await connection.execute(text(isolated(statement)))
        await connection.execute(text("insert into projects(id) values (:id)"), {"id": project_id})
        await connection.execute(
            text("insert into workstream_tasks(id,project_id) values (:id,:project)"),
            {"id": task_id, "project": project_id},
        )
        await connection.execute(
            text("insert into task_assignments(id,task_id,project_id) values (:id,:task,:project)"),
            {"id": assignment_id, "task": task_id, "project": project_id},
        )
        await connection.execute(
            text("insert into submissions(id,task_id,version) values (:id,:task,1)"),
            {"id": submission_id, "task": task_id},
        )
        await connection.execute(
            text("insert into external_checker_registry_entries(id) values (:id)"),
            {"id": registry_entry_id},
        )
    try:
        yield DatabaseFacts(
            engine,
            project_id,
            task_id,
            assignment_id,
            submission_id,
            registry_entry_id,
            registry_entry_digest,
        )
    finally:
        try:
            async with engine.begin() as connection:
                await connection.execute(text("set local search_path = pg_catalog"))
                await connection.execute(text(f'drop schema if exists "{schema}" cascade'))
        finally:
            await engine.dispose()


@dataclass
class BoundaryPorts:
    decisions: dict[str, UUID] = field(default_factory=dict)
    fresh_authority_evidence: bool = True
    request_checks: int = 0
    response_checks: int = 0
    current_checks: int = 0
    events: list[str] = field(default_factory=list)
    corrupt_admin_receipt: bool = False

    def _decision(self, action: str, facts: object) -> ModelActionEvidence:
        self.events.append(action)
        digest = model_action_digest(action, facts)
        evidence_id = (
            new_record_id()
            if self.fresh_authority_evidence
            else self.decisions.setdefault(digest, new_record_id())
        )
        return ModelActionEvidence(evidence_id=evidence_id, facts_digest=digest)

    async def authorize_profile(self, facts):
        return self._decision("profile", facts)

    async def authorize_budget(self, facts):
        return self._decision("budget", facts)

    async def authorize_prepare(self, execution, slot, request_sha256):
        return self._decision(
            "prepare",
            {
                "execution": execution.model_dump(mode="json"),
                "slot": slot.model_dump(mode="json"),
                "request_sha256": request_sha256,
            },
        )

    async def authorize_dispatch(self, execution, attempt, request_evidence):
        return self._decision(
            "dispatch",
            {
                "execution": execution.model_dump(mode="json"),
                "attempt": attempt.model_dump(mode="json"),
                "request_evidence": request_evidence.model_dump(mode="json"),
            },
        )

    async def authorize_recover(self, execution, effect):
        return self._decision(
            "recover",
            {
                "execution": execution.model_dump(mode="json"),
                "effect": effect.model_dump(mode="json"),
            },
        )

    async def authorize_observe(self, effect, provider_response_id, observation_digest):
        return self._decision(
            "observe",
            {
                "effect": effect.model_dump(mode="json"),
                "provider_response_id": provider_response_id,
                "observation_digest": observation_digest,
            },
        )

    async def authorize_child(self, execution, parent_attempt_id, terminal_digest):
        return self._decision(
            "child",
            {
                "execution": execution.model_dump(mode="json"),
                "parent_attempt_id": str(parent_attempt_id),
                "terminal_digest": terminal_digest,
            },
        )

    async def authorize_complete(self, effect, response_evidence, terminal_digest):
        return self._decision(
            "complete",
            {
                "effect": effect.model_dump(mode="json"),
                "response_evidence": (
                    response_evidence.model_dump(mode="json")
                    if response_evidence is not None
                    else None
                ),
                "terminal_digest": terminal_digest,
            },
        )

    async def require_current(self, facts, slot):
        self.current_checks += 1
        self.events.append("current")

    async def require_request(self, attempt, evidence):
        self.request_checks += 1

    async def require_response(self, attempt_id, evidence):
        self.response_checks += 1


class DatabaseBoundaryPorts:
    """Persist fake boundary receipts so isolated PostgreSQL exercises real ancestry FKs."""

    def __init__(self, session: AsyncSession, ports: BoundaryPorts):
        self._session = session
        self._ports = ports

    async def _authority(
        self, evidence, *, action: str, permission: str, actor_id=None, resource_digest=None
    ):
        actor = str(actor_id or new_record_id())
        if actor_id is not None:
            await self._session.execute(
                text("insert into actor_profiles(id) values (:id) on conflict do nothing"),
                {"id": actor_id},
            )
        await self._session.execute(
            text(
                "insert into audit_events(id,event_domain,event_type,actor_ref_kind,actor_id,"
                "action_id,permission_id,denial_code,after_facts) values "
                "(:id,'authority','SensitiveAuthorizationAllowed','actor_profile',:actor,"
                ":action,:permission,null,cast(:after as jsonb))"
            ),
            {
                "id": evidence.evidence_id,
                "actor": actor,
                "action": action,
                "permission": permission,
                "after": json.dumps(
                    {
                        "allowed": True,
                        "resource_context_digest": (
                            sha("substituted-authority")
                            if actor_id is not None and self._ports.corrupt_admin_receipt
                            else resource_digest or sha("authority")
                        ),
                    }
                ),
            },
        )
        return evidence

    async def authorize_profile(self, facts):
        evidence = await self._ports.authorize_profile(facts)
        return await self._authority(
            evidence,
            action="project.model_profile.provision",
            permission="project.model_profile.manage",
            actor_id=facts.actor_profile_id,
            resource_digest=authorization_resource_digest(
                project_model_admin_resource(
                    PROFILE_PROVISION, facts, actor_profile_id=facts.actor_profile_id
                )
            ),
        )

    async def authorize_budget(self, facts):
        evidence = await self._ports.authorize_budget(facts)
        return await self._authority(
            evidence,
            action="project.model_budget.configure",
            permission="project.model_budget.manage",
            actor_id=facts.actor_profile_id,
            resource_digest=authorization_resource_digest(
                project_model_admin_resource(
                    BUDGET_CONFIGURE, facts, actor_profile_id=facts.actor_profile_id
                )
            ),
        )

    async def authorize_prepare(self, execution, slot, request_sha256):
        evidence = await self._ports.authorize_prepare(execution, slot, request_sha256)
        return await self._authority(
            evidence, action="checker.model_call.prepare", permission="checker.model_call.prepare"
        )

    async def authorize_dispatch(self, execution, attempt, request_evidence):
        evidence = await self._ports.authorize_dispatch(execution, attempt, request_evidence)
        return await self._authority(
            evidence,
            action="checker.model_call.dispatch",
            permission="checker.model_call.dispatch",
        )

    async def authorize_recover(self, execution, effect):
        evidence = await self._ports.authorize_recover(execution, effect)
        return await self._authority(
            evidence, action="checker.model_call.recover", permission="checker.model_call.recover"
        )

    async def authorize_observe(self, effect, provider_response_id, observation_digest):
        evidence = await self._ports.authorize_observe(
            effect, provider_response_id, observation_digest
        )
        return await self._authority(
            evidence, action="checker.model_call.observe", permission="checker.model_call.observe"
        )

    async def authorize_child(self, execution, parent_attempt_id, terminal_digest):
        evidence = await self._ports.authorize_child(
            execution, parent_attempt_id, terminal_digest
        )
        return await self._authority(
            evidence,
            action="project.model_call.recovery_child.authorize",
            permission="project.model_call.recovery_child.authorize",
        )

    async def authorize_complete(self, effect, response_evidence, terminal_digest):
        evidence = await self._ports.authorize_complete(
            effect, response_evidence, terminal_digest
        )
        return await self._authority(
            evidence,
            action="checker.model_call.complete",
            permission="checker.model_call.complete",
        )

    async def require_current(self, facts, slot):
        await self._ports.require_current(facts, slot)

    async def _artifact(self, evidence):
        for table_name, value in (
            ("artifact_bindings", evidence.binding_id),
            ("artifact_contents", evidence.content_id),
            ("artifact_put_attempts", evidence.put_attempt_id),
            ("artifact_verification_receipts", evidence.verification_receipt_id),
        ):
            await self._session.execute(
                text(f"insert into {table_name}(id) values (:id) on conflict do nothing"),
                {"id": value},
            )

    async def require_request(self, attempt, evidence):
        await self._ports.require_request(attempt, evidence)
        await self._artifact(evidence)

    async def require_response(self, attempt_id, evidence):
        await self._ports.require_response(attempt_id, evidence)
        await self._artifact(evidence)


def service(session: AsyncSession, ports: BoundaryPorts) -> ModelCallService:
    boundaries = DatabaseBoundaryPorts(session, ports)
    return ModelCallService(
        session,
        authority=boundaries,
        current_execution=boundaries,
        evidence=boundaries,
    )


async def provision(
    facts: DatabaseFacts,
    ports: BoundaryPorts,
    *,
    limit: int,
    replay: bool = False,
):
    profile_spec = ProjectModelProfileSpec(
        project_id=facts.project_id,
        profile_version=1,
        registry_entry_id=facts.registry_entry_id,
        registry_entry_digest=facts.registry_entry_digest,
        provider="openai_responses",
        api="responses.v1",
        model_snapshot="gpt-example-2026-10-01",
        settings=ModelGenerationSettings(reasoning_effort="medium", text_verbosity="low"),
        maximum_request_bytes=10_000,
        maximum_output_bytes=4_000,
        maximum_response_bytes=30_000,
        maximum_input_tokens=100,
        maximum_output_tokens=50,
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
    profile_facts = ModelProfileProvisioningFacts(
        operation_id=uuid4(),
        actor_profile_id=new_record_id(),
        spec=profile_spec,
        profile_digest=canonical_json_hash(profile_spec.model_dump(mode="json")),
    )
    budget_spec = ProjectModelBudgetConfigurationSpec(
        project_id=facts.project_id,
        configuration_version=1,
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


async def test_provisioning_replay_retains_original_receipts_with_fresh_authority(
    model_database: DatabaseFacts,
) -> None:
    await provision(model_database, BoundaryPorts(), limit=10_000, replay=True)


async def test_profile_publication_rejects_substituted_authority_digest(
    model_database: DatabaseFacts,
) -> None:
    with pytest.raises(DBAPIError):
        await provision(
            model_database,
            BoundaryPorts(corrupt_admin_receipt=True),
            limit=10_000,
        )


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


async def test_concurrent_dispatch_reserves_one_lifetime_budget(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation)
    prepared = []
    for requirement in ("model_a", "model_b"):
        run = execution(model_database)
        paid_slot = slot(model_database, profile, requirement)
        request_sha = sha(requirement)
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                item = await service(session, ports).prepare_attempt(
                    run,
                    paid_slot,
                    registry_entry_id=model_database.registry_entry_id,
                    request_sha256=request_sha,
                )
        prepared.append((run, item, evidence(requirement, request_sha)))

    async def dispatch(item):
        run, attempt, request_evidence = item
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                return await service(session, ports).reserve_dispatch(
                    run, attempt, request_evidence
                )

    results = await asyncio.gather(*(dispatch(item) for item in prepared), return_exceptions=True)
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert sum(isinstance(result, ModelCallBudgetUnavailable) for result in results) == 1
    async with AsyncSession(model_database.engine) as session:
        account = await session.get(CheckerModelBudgetAccount, str(model_database.project_id))
        assert account.lifetime_reserved_nanodollars == reservation
        assert account.lifetime_settled_nanodollars == 0


async def test_fresh_execution_authority_precedes_currentness_and_owner_locks(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation * 2)
    run = execution(model_database)
    paid_slot = slot(model_database, profile, "model_order")
    request_sha = sha("ordered-request")
    ports.events.clear()
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            prepared = await owner.prepare_attempt(
                run,
                paid_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=request_sha,
            )
            assert ports.events == ["prepare", "current"]
            ports.events.clear()
            dispatched = await owner.reserve_dispatch(
                run,
                prepared,
                evidence("ordered-request", request_sha),
            )
            assert ports.events == ["dispatch", "current"]
            await owner.mark_uncertain(
                dispatched.effect,
                sha("ordered-uncertain"),
                provider_response_id="resp_ordered",
            )

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            await session.execute(
                text("insert into checker_runs(id) values (:id)"),
                {"id": run.checker_run_id},
            )
            owner = service(session, ports)
            ports.events.clear()
            await owner.attach_recovery(run, dispatched.effect)
            assert ports.events == ["recover", "current"]
            ports.events.clear()
            with pytest.raises(ModelCallConflict, match="not_retryable"):
                await owner.prepare_recovery_child(
                    run,
                    paid_slot,
                    registry_entry_id=model_database.registry_entry_id,
                    parent_attempt_id=prepared.attempt_id,
                    terminal_digest=sha("ordered-uncertain"),
                    request_sha256=prepared.request_sha256,
                )
            assert ports.events == ["child", "current"]


async def test_reservation_rollback_and_completion_settle_exactly_once(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation * 2)
    run = execution(model_database)
    paid_slot = slot(model_database, profile, "model_rollback")
    request_sha = sha("rollback-request")
    request_art = evidence("request", request_sha)
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            prepared = await service(session, ports).prepare_attempt(
                run,
                paid_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=request_sha,
            )
        with pytest.raises(RuntimeError, match="force rollback"):
            async with session.begin():
                await service(session, ports).reserve_dispatch(run, prepared, request_art)
                raise RuntimeError("force rollback")
        async with session.begin():
            dispatched = await service(session, ports).reserve_dispatch(run, prepared, request_art)

    usage = ModelCallUsage(
        input_tokens=40,
        cached_input_tokens=10,
        output_tokens=12,
        reasoning_tokens=7,
    )
    response_art = evidence("response", sha("response"))
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            completed = await owner.complete(
                dispatched.effect,
                provider_response_id="resp_exact_once",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=response_art,
                usage=usage,
            )
            replay = await owner.complete(
                dispatched.effect,
                provider_response_id="resp_exact_once",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=response_art,
                usage=usage,
            )
            account = await session.get(CheckerModelBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == 0
            assert account.lifetime_settled_nanodollars == completed.settled_nanodollars
            assert replay.replayed

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            await session.execute(
                text("insert into checker_runs(id) values (:id)"),
                {"id": run.checker_run_id},
            )
            ports.events.clear()
            attached = await service(session, ports).attach_completed(run, dispatched.effect)
            assert attached.replayed is False
            assert ports.events == ["recover", "current"]


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
                    run,
                    paid_slot,
                    registry_entry_id=model_database.registry_entry_id,
                    parent_attempt_id=prepared.attempt_id,
                    terminal_digest=uncertainty,
                    request_sha256=prepared.request_sha256,
                )
            account = await session.get(CheckerModelBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == reservation

    # A distinct call proves the only zero-cost child path: authenticated no effect.
    run2, paid_slot2, prepared2, dispatched2, _ = await prepare_and_reserve(
        model_database, ports, profile, "model_no_effect"
    )
    proof = KnownNoEffectProof(
        proof_id=new_record_id(),
        proof_digest=sha("provider-no-effect"),
        observed_at=datetime.now(UTC),
    )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            await owner.mark_known_no_effect(dispatched2.effect, proof)
            child = await owner.prepare_recovery_child(
                run2,
                paid_slot2,
                registry_entry_id=model_database.registry_entry_id,
                parent_attempt_id=prepared2.attempt_id,
                terminal_digest=model_retry_terminal_digest(proof),
                request_sha256=prepared2.request_sha256,
            )
            assert child.attempt_number == 2
            assert child.state == "prepared"
            account = await session.get(CheckerModelBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == reservation


async def test_budget_adjustment_preserves_reserved_and_settles_old_snapshot(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation * 2)
    run, paid_slot, prepared, dispatched, _ = await prepare_and_reserve(
        model_database, ports, profile, "model_budget_adjustment"
    )
    adjusted_spec = ProjectModelBudgetConfigurationSpec(
        project_id=model_database.project_id,
        configuration_version=2,
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

    too_low_spec = ProjectModelBudgetConfigurationSpec(
        project_id=model_database.project_id,
        configuration_version=3,
        lifetime_limit_nanodollars=reservation - 1,
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
            account = await session.get(CheckerModelBudgetAccount, str(model_database.project_id))
            assert account.current_configuration_id == str(adjusted.configuration_id)
            assert account.lifetime_reserved_nanodollars == 0
            assert account.lifetime_settled_nanodollars == completed.settled_nanodollars


async def test_known_failed_settles_once_and_allows_authorized_child(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation * 2)
    run, paid_slot, prepared, dispatched, _ = await prepare_and_reserve(
        model_database, ports, profile, "model_known_failure"
    )
    usage = ModelCallUsage(
        input_tokens=22,
        cached_input_tokens=2,
        output_tokens=3,
        reasoning_tokens=1,
    )
    response_art = evidence("failed-response", sha("failed-response"))
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            failed = await owner.complete_known_failure(
                dispatched.effect,
                provider_response_id="resp_terminal_failure",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=response_art,
                usage=usage,
            )
            replay = await owner.complete_known_failure(
                dispatched.effect,
                provider_response_id="resp_terminal_failure",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=response_art,
                usage=usage,
            )
            assert replay.replayed
            child = await owner.prepare_recovery_child(
                run,
                paid_slot,
                registry_entry_id=model_database.registry_entry_id,
                parent_attempt_id=prepared.attempt_id,
                terminal_digest=model_retry_terminal_digest(failed),
                request_sha256=prepared.request_sha256,
            )
            assert child.attempt_number == 2
            account = await session.get(CheckerModelBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == 0
            assert account.lifetime_settled_nanodollars == failed.settled_nanodollars


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
                        "update checker_model_call_slots set first_request_sha256=:digest "
                        "where id=:slot_id"
                    ),
                    {"digest": sha("substituted"), "slot_id": dispatched.slot_id},
                )

    async with AsyncSession(model_database.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await session.execute(
                    text(
                        "update checker_model_budget_accounts "
                        "set lifetime_reserved_nanodollars=lifetime_reserved_nanodollars-1 "
                        "where project_id=:project_id"
                    ),
                    {"project_id": model_database.project_id},
                )

    async with AsyncSession(model_database.engine) as session:
        account = await session.get(CheckerModelBudgetAccount, str(model_database.project_id))
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


async def test_profile_reader_requires_exact_project_registry_and_selector(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    profile = await provision(model_database, ports, limit=10_000)
    async with AsyncSession(model_database.engine) as session:
        async with session.begin():
            reader = ModelProfileReader(session)
            assert (
                await reader.read_exact(
                    profile.selector,
                    project_id=model_database.project_id,
                    registry_entry_id=model_database.registry_entry_id,
                    registry_entry_digest=model_database.registry_entry_digest,
                )
                == profile
            )
            for changes in (
                {"project_id": new_record_id()},
                {"registry_entry_id": new_record_id()},
                {"registry_entry_digest": sha("substituted-registry")},
            ):
                scope = {
                    "project_id": model_database.project_id,
                    "registry_entry_id": model_database.registry_entry_id,
                    "registry_entry_digest": model_database.registry_entry_digest,
                }
                scope.update(changes)
                with pytest.raises(ModelCallUnavailable, match="model_profile_unavailable"):
                    await reader.read_exact(profile.selector, **scope)
