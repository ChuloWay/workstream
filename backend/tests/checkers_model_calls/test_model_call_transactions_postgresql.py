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
from app.modules.authorization.domain.model_usage import (
    BUDGET_CONFIGURE,
    PROFILE_PROVISION,
    project_model_admin_resource,
)
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.model_usage.api import (
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
    SetupModelUsageSlotKey,
    model_action_digest,
    model_retry_terminal_digest,
)
from app.modules.model_usage.models import ModelUsageBudgetAccount, ModelUsageEffect
from app.modules.model_usage.profiles import ModelProfileReader
from app.modules.model_usage.service import ModelCallService
from app.modules.model_usage.setup import SetupModelUsageService


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
        str(Path(__file__).resolve().parents[2] / "alembic/versions/0060_model_usage.py")
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
            "create table external_checker_registry_entries(id uuid primary key,"
            "entry_digest text not null,phase text not null)",
            "create table checker_runs(id uuid primary key)",
            "create table actor_profiles(id uuid primary key)",
            "create table audit_events(id uuid primary key, event_domain text, event_type text, "
            "actor_ref_kind text, actor_id text, action_id text, permission_id text, "
            "denial_code text, after_facts json)",
            "create table artifact_bindings(id uuid primary key)",
            "create table artifact_contents(id uuid primary key)",
            "create table artifact_put_attempts(id uuid primary key)",
            "create table artifact_verification_receipts(id uuid primary key)",
            "create table project_guide_compilation_attempts("
            "id uuid primary key,project_id uuid not null,guide_id uuid not null,"
            "source_snapshot_id uuid not null,setup_run_id uuid not null,"
            "setup_generation bigint not null,runtime_configuration_hash text,status text)",
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
            text(
                "insert into external_checker_registry_entries(id,entry_digest,phase) "
                "values (:id,:digest,'post_submit')"
            ),
            {"id": registry_entry_id, "digest": registry_entry_digest},
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

    async def authorize_child(self, project_id, parent_attempt_id, terminal_digest):
        return self._decision(
            "child",
            {
                "project_id": str(project_id),
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

    async def authorize_setup_prepare(self, slot, request_sha256):
        return self._decision(
            "setup_prepare",
            {"slot": slot.model_dump(mode="json"), "request_sha256": request_sha256},
        )

    async def authorize_setup_dispatch(self, prepared, request_evidence):
        return self._decision(
            "setup_dispatch",
            {
                "prepared": prepared.model_dump(mode="json"),
                "request_evidence": request_evidence.model_dump(mode="json"),
            },
        )

    async def authorize_setup_observe(self, effect, provider_response_id, observation_digest):
        return self._decision(
            "setup_observe",
            {
                "effect": effect.model_dump(mode="json"),
                "provider_response_id": provider_response_id,
                "observation_digest": observation_digest,
            },
        )

    async def authorize_setup_complete(self, effect, response_evidence, terminal_digest):
        return self._decision(
            "setup_complete",
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

    async def require_setup_request(self, prepared, evidence):
        self.request_checks += 1

    async def require_setup_response(self, effect_id, evidence):
        self.response_checks += 1

    async def require_current(self, facts, slot):
        self.current_checks += 1
        self.events.append("current")

    async def require_recovery_current(self, slot, parent_attempt_id):
        self.current_checks += 1
        self.events.append("recovery_current")

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
                ":action,:permission,null,cast(:after as json))"
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

    async def authorize_child(self, project_id, parent_attempt_id, terminal_digest):
        evidence = await self._ports.authorize_child(project_id, parent_attempt_id, terminal_digest)
        return await self._authority(
            evidence,
            action="project.model_call.recovery_child.authorize",
            permission="project.model_call.recovery_child.authorize",
        )

    async def authorize_complete(self, effect, response_evidence, terminal_digest):
        evidence = await self._ports.authorize_complete(effect, response_evidence, terminal_digest)
        return await self._authority(
            evidence,
            action="checker.model_call.complete",
            permission="checker.model_call.complete",
        )

    async def authorize_setup_prepare(self, slot, request_sha256):
        evidence = await self._ports.authorize_setup_prepare(slot, request_sha256)
        return await self._authority(
            evidence,
            action="project.guide_compilation.model.prepare",
            permission="project.guide_compilation.model.prepare",
        )

    async def authorize_setup_dispatch(self, prepared, request_evidence):
        evidence = await self._ports.authorize_setup_dispatch(prepared, request_evidence)
        return await self._authority(
            evidence,
            action="project.guide_compilation.model.dispatch",
            permission="project.guide_compilation.model.dispatch",
        )

    async def authorize_setup_observe(self, effect, provider_response_id, observation_digest):
        evidence = await self._ports.authorize_setup_observe(
            effect, provider_response_id, observation_digest
        )
        return await self._authority(
            evidence,
            action="project.guide_compilation.model.observe",
            permission="project.guide_compilation.model.observe",
        )

    async def authorize_setup_complete(self, effect, response_evidence, terminal_digest):
        evidence = await self._ports.authorize_setup_complete(
            effect, response_evidence, terminal_digest
        )
        return await self._authority(
            evidence,
            action="project.guide_compilation.model.complete",
            permission="project.guide_compilation.model.complete",
        )

    async def require_setup_request(self, prepared, evidence):
        await self._ports.require_setup_request(prepared, evidence)
        await self._artifact(evidence)

    async def require_setup_response(self, effect_id, evidence):
        await self._ports.require_setup_response(effect_id, evidence)
        await self._artifact(evidence)

    async def require_setup_current(self, slot):
        attempt_id = await self._session.scalar(
            text(
                "select id from project_guide_compilation_attempts "
                "where id=:id and project_id=:project and guide_id=:guide "
                "and source_snapshot_id=:snapshot and setup_run_id=:run "
                "and setup_generation=:generation and runtime_configuration_hash=:runtime "
                "and status='compilation_reserved' for update"
            ),
            {
                "id": slot.compilation_attempt_id,
                "project": slot.project_id,
                "guide": slot.guide_id,
                "snapshot": slot.source_snapshot_id,
                "run": slot.setup_run_id,
                "generation": slot.setup_generation,
                "runtime": slot.runtime_configuration_hash,
            },
        )
        if attempt_id is None:
            raise ModelCallUnavailable("setup_model_owner_unavailable")

    async def require_current(self, facts, slot):
        await self._ports.require_current(facts, slot)

    async def require_recovery_current(self, slot, parent_attempt_id):
        await self._ports.require_recovery_current(slot, parent_attempt_id)

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
    runtime_hash = sha("setup-runtime")
    async with facts.engine.begin() as connection:
        await connection.execute(
            text(
                "insert into project_guide_compilation_attempts("
                "id,project_id,guide_id,source_snapshot_id,setup_run_id,"
                "setup_generation,runtime_configuration_hash,status) values("
                ":id,:project,:guide,:snapshot,:run,1,:runtime,'compilation_reserved')"
            ),
            {
                "id": attempt_id,
                "project": facts.project_id,
                "guide": guide_id,
                "snapshot": snapshot_id,
                "run": setup_run_id,
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


async def test_profile_publication_is_not_owned_by_a_checker_registry_entry(
    model_database: DatabaseFacts,
) -> None:
    async with model_database.engine.begin() as connection:
        await connection.execute(
            text("update external_checker_registry_entries set phase='pre_submit' where id=:id"),
            {"id": model_database.registry_entry_id},
        )
    profile = await provision(model_database, BoundaryPorts(), limit=10_000)
    assert profile.spec.project_id == model_database.project_id


async def test_database_guards_recompute_profile_and_budget_digests(
    model_database: DatabaseFacts,
) -> None:
    await provision(model_database, BoundaryPorts(), limit=10_000)
    async with AsyncSession(model_database.engine) as session:
        with pytest.raises(DBAPIError, match="profile digest is invalid"):
            async with session.begin():
                await session.execute(
                    text(
                        "insert into model_usage_profiles select "
                        ":id,project_id,2,:digest,provider,api,model_snapshot,"
                        "generation_settings,maximum_request_bytes,"
                        "maximum_output_bytes,maximum_response_bytes,maximum_input_tokens,"
                        "maximum_output_tokens,maximum_calls,maximum_total_request_bytes,"
                        "maximum_total_response_bytes,maximum_total_input_tokens,"
                        "maximum_total_output_tokens,allowed_tools,maximum_tool_calls,"
                        "maximum_tool_output_bytes,deadline_ms,pricing_policy_id,"
                        "pricing_policy_version,pricing_policy_digest,uncached_input_rate,"
                        "cached_input_rate,output_rate,:operation,actor_profile_id,:authority,"
                        "clock_timestamp() from model_usage_profiles where profile_version=1"
                    ),
                    {
                        "id": new_record_id(),
                        "digest": sha("noncanonical-profile"),
                        "operation": uuid4(),
                        "authority": new_record_id(),
                    },
                )

    async with AsyncSession(model_database.engine) as session:
        with pytest.raises(DBAPIError, match="configuration digest is invalid"):
            async with session.begin():
                await session.execute(
                    text(
                        "insert into model_usage_budget_configurations select "
                        ":id,project_id,2,:digest,authorized_total_nanodollars,"
                        "externally_reconciled_prior_spend_nanodollars,"
                        "lifetime_limit_nanodollars,:operation,"
                        "actor_profile_id,:authority,clock_timestamp() "
                        "from model_usage_budget_configurations where configuration_version=1"
                    ),
                    {
                        "id": new_record_id(),
                        "digest": sha("noncanonical-budget"),
                        "operation": uuid4(),
                        "authority": new_record_id(),
                    },
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
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        assert account.lifetime_reserved_nanodollars == reservation
        assert account.lifetime_settled_nanodollars == 0


async def test_setup_and_checker_dispatches_share_one_account_and_both_win(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    per_dispatch = 100 * 11 + 50 * 29
    profile = await provision(
        model_database,
        ports,
        limit=per_dispatch * 2,
        profile_changes={
            "maximum_calls": 2,
            "maximum_total_request_bytes": 20_000,
            "maximum_total_response_bytes": 60_000,
            "maximum_total_input_tokens": 200,
            "maximum_total_output_tokens": 100,
        },
    )
    checker_run = execution(model_database)
    checker_slot = slot(model_database, profile, "shared_budget_checker")
    checker_sha = sha("shared-budget-checker")
    checker_evidence = evidence("shared-budget-checker", checker_sha)
    setup_key = await setup_slot_key(model_database, profile)
    setup_sha = sha("shared-budget-setup")
    setup_evidence = evidence("shared-budget-setup", setup_sha)

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            checker_prepared = await service(session, ports).prepare_attempt(
                checker_run,
                checker_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=checker_sha,
            )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            setup_prepared = await setup_service(session, ports).prepare(setup_key, setup_sha)

    async def reserve_checker():
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                return await service(session, ports).reserve_dispatch(
                    checker_run, checker_prepared, checker_evidence
                )

    async def reserve_setup():
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                return await setup_service(session, ports).reserve_dispatch(
                    setup_prepared, setup_evidence
                )

    checker_reserved, setup_reserved = await asyncio.gather(reserve_checker(), reserve_setup())
    assert checker_reserved.reserved_nanodollars == per_dispatch
    assert setup_reserved.reserved_nanodollars == per_dispatch
    async with AsyncSession(model_database.engine) as session:
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        assert account.lifetime_reserved_nanodollars == per_dispatch * 2
        assert account.lifetime_settled_nanodollars == 0


async def test_cheap_completed_call_reserves_remaining_aggregate_before_next_dispatch(
    model_database: DatabaseFacts,
) -> None:
    """A cheap first result cannot defer an aggregate-token failure until after I/O."""
    ports = BoundaryPorts()
    per_dispatch = 100 * 11 + 50 * 29
    profile = await provision(
        model_database,
        ports,
        limit=per_dispatch * 2,
        profile_changes={
            "maximum_calls": 2,
            "maximum_total_request_bytes": 20_000,
            "maximum_total_response_bytes": 60_000,
            "maximum_total_input_tokens": 100,
            "maximum_total_output_tokens": 100,
        },
    )
    run = execution(model_database)
    first_slot = slot(model_database, profile, "aggregate_pre_dispatch")
    second_slot = first_slot.model_copy(update={"slot_index": 1})
    first_sha = sha("aggregate-pre-dispatch-first")
    second_sha = sha("aggregate-pre-dispatch-second")

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
                evidence("aggregate-pre-dispatch-first", first_sha),
            )
            await owner.complete(
                first_dispatched.effect,
                provider_response_id="resp_cheap_cached",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=evidence(
                    "aggregate-pre-dispatch-response",
                    sha("aggregate-pre-dispatch-response"),
                ),
                usage=ModelCallUsage(
                    input_tokens=10,
                    cached_input_tokens=10,
                    output_tokens=0,
                    reasoning_tokens=0,
                ),
            )
            second_prepared = await owner.prepare_attempt(
                run,
                second_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=second_sha,
            )
            with pytest.raises(ModelCallBudgetUnavailable, match="run_envelope"):
                await owner.reserve_dispatch(
                    run,
                    second_prepared,
                    evidence("aggregate-pre-dispatch-second", second_sha),
                )

    async with AsyncSession(model_database.engine) as session:
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        second = await session.get(ModelUsageEffect, str(second_prepared.attempt_id))
        assert account.lifetime_reserved_nanodollars == 0
        assert account.lifetime_settled_nanodollars == 10 * 2
        assert second is not None and second.state == "prepared"


async def test_setup_draft_review_correction_settle_three_shared_calls(
    model_database: DatabaseFacts,
) -> None:
    """One exact setup attempt can run a finite three-call owner-controlled loop."""
    ports = BoundaryPorts()
    per_dispatch = 100 * 11 + 50 * 29
    profile = await provision(
        model_database,
        ports,
        limit=per_dispatch * 3,
        profile_changes={
            "maximum_calls": 3,
            "maximum_total_request_bytes": 30_000,
            "maximum_total_response_bytes": 90_000,
            "maximum_total_input_tokens": 300,
            "maximum_total_output_tokens": 150,
        },
    )
    base = await setup_slot_key(model_database, profile)
    settled = 0
    for index, phase in enumerate(("draft", "review", "correction")):
        key = base.model_copy(update={"phase": phase, "call_index": index})
        request_sha = sha(f"setup-loop-{phase}-request")
        response_sha = sha(f"setup-loop-{phase}-response")
        usage = ModelCallUsage(
            input_tokens=10 + index,
            cached_input_tokens=index,
            output_tokens=5 + index,
            reasoning_tokens=index,
        )
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                owner = setup_service(session, ports)
                prepared = await owner.prepare(key, request_sha)
                dispatched = await owner.reserve_dispatch(
                    prepared, evidence(f"setup-loop-{phase}-request", request_sha)
                )
                completed = await owner.complete(
                    dispatched.effect,
                    provider_response_id=f"resp_setup_{phase}",
                    provider_model_snapshot=profile.spec.model_snapshot,
                    response_evidence=evidence(f"setup-loop-{phase}-response", response_sha),
                    usage=usage,
                )
                assert completed.effect.slot_key == key
                assert completed.state == "completed"
                assert completed.replayed is False
                settled += completed.settled_nanodollars

    async with AsyncSession(model_database.engine) as session:
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        states = (
            (
                await session.execute(
                    text(
                        "select effect.state from model_usage_effects effect "
                        "join setup_model_usage_slots slot on slot.id=effect.setup_slot_id "
                        "where slot.compilation_attempt_id=:attempt order by slot.call_index"
                    ),
                    {"attempt": base.compilation_attempt_id},
                )
            )
            .scalars()
            .all()
        )
        assert states == ["completed", "completed", "completed"]
        assert account.lifetime_reserved_nanodollars == 0
        assert account.lifetime_settled_nanodollars == settled


async def test_uncertain_setup_effect_replay_never_reauthorizes_dispatch(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation)
    key = await setup_slot_key(model_database, profile)
    request_sha = sha("setup-uncertain-request")
    request_evidence = evidence("setup-uncertain-request", request_sha)
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = setup_service(session, ports)
            prepared = await owner.prepare(key, request_sha)
            dispatched = await owner.reserve_dispatch(prepared, request_evidence)
            observed = await owner.mark_uncertain(
                dispatched.effect,
                sha("setup-uncertain-observation"),
            )
            assert observed.state == "uncertain"

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = setup_service(session, ports)
            replayed = await owner.prepare(key, request_sha)
            with pytest.raises(ModelCallConflict, match="not_dispatchable"):
                await owner.reserve_dispatch(replayed, request_evidence)
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == reservation
            assert account.lifetime_settled_nanodollars == 0


async def test_setup_and_checker_dispatches_share_one_account_cap(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    per_dispatch = 100 * 11 + 50 * 29
    profile = await provision(
        model_database,
        ports,
        limit=per_dispatch,
        profile_changes={
            "maximum_calls": 2,
            "maximum_total_request_bytes": 20_000,
            "maximum_total_response_bytes": 60_000,
            "maximum_total_input_tokens": 200,
            "maximum_total_output_tokens": 100,
        },
    )
    checker_run = execution(model_database)
    checker_slot = slot(model_database, profile, "shared_cap_checker")
    checker_sha = sha("shared-cap-checker")
    checker_evidence = evidence("shared-cap-checker", checker_sha)
    setup_key = await setup_slot_key(model_database, profile)
    setup_sha = sha("shared-cap-setup")
    setup_evidence = evidence("shared-cap-setup", setup_sha)

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            checker_prepared = await service(session, ports).prepare_attempt(
                checker_run,
                checker_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=checker_sha,
            )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            setup_prepared = await setup_service(session, ports).prepare(setup_key, setup_sha)

    async def reserve_checker():
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                return await service(session, ports).reserve_dispatch(
                    checker_run, checker_prepared, checker_evidence
                )

    async def reserve_setup():
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                return await setup_service(session, ports).reserve_dispatch(
                    setup_prepared, setup_evidence
                )

    results = await asyncio.gather(reserve_checker(), reserve_setup(), return_exceptions=True)
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert sum(isinstance(result, ModelCallBudgetUnavailable) for result in results) == 1
    async with AsyncSession(model_database.engine) as session:
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        assert account.lifetime_reserved_nanodollars == per_dispatch
        assert account.lifetime_settled_nanodollars == 0


async def test_setup_reservation_rollback_releases_shared_account(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    per_dispatch = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=per_dispatch)
    setup_key = await setup_slot_key(model_database, profile)
    setup_sha = sha("rollback-shared-setup")
    setup_evidence = evidence("rollback-shared-setup", setup_sha)
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            setup_prepared = await setup_service(session, ports).prepare(setup_key, setup_sha)
        with pytest.raises(RuntimeError, match="force setup rollback"):
            async with session.begin():
                await setup_service(session, ports).reserve_dispatch(setup_prepared, setup_evidence)
                raise RuntimeError("force setup rollback")

    checker_run = execution(model_database)
    checker_slot = slot(model_database, profile, "after_setup_rollback")
    checker_sha = sha("after-setup-rollback")
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            checker_prepared = await service(session, ports).prepare_attempt(
                checker_run,
                checker_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=checker_sha,
            )
            reserved = await service(session, ports).reserve_dispatch(
                checker_run,
                checker_prepared,
                evidence("after-setup-rollback", checker_sha),
            )
            assert reserved.reserved_nanodollars == per_dispatch
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == per_dispatch
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
                    paid_slot,
                    registry_entry_id=model_database.registry_entry_id,
                    parent_attempt_id=prepared.attempt_id,
                    terminal_digest=sha("ordered-uncertain"),
                    request_sha256=prepared.request_sha256,
                )
            assert ports.events == ["child", "recovery_current"]


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
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
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
                "select project_id from model_usage_budget_accounts "
                "where project_id=:project_id for update"
            ),
            {"project_id": model_database.project_id},
        )

        if terminal_kind == "complete":
            terminal_task = asyncio.create_task(
                service(terminal, ports).complete(
                    first_dispatched.effect,
                    provider_response_id="resp_lock_order",
                    provider_model_snapshot=profile.spec.model_snapshot,
                    response_evidence=evidence(
                        "terminal-order-response", sha("terminal-order-response")
                    ),
                    usage=ModelCallUsage(
                        input_tokens=40,
                        cached_input_tokens=10,
                        output_tokens=12,
                        reasoning_tokens=7,
                    ),
                )
            )
        else:
            terminal_task = asyncio.create_task(
                service(terminal, ports).mark_known_no_effect(
                    first_dispatched.effect,
                    KnownNoEffectProof(
                        proof_id=new_record_id(),
                        proof_digest=sha("terminal-order-no-effect"),
                        observed_at=datetime.now(UTC),
                    ),
                )
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
        observed_at=datetime.now(UTC),
    )
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
                paid_slot,
                registry_entry_id=model_database.registry_entry_id,
                parent_attempt_id=prepared.attempt_id,
                terminal_digest=model_retry_terminal_digest(failed),
                request_sha256=prepared.request_sha256,
            )
            assert child.attempt_number == 2
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
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
                        "update checker_model_usage_slots set first_request_sha256=:digest "
                        "where id=:slot_id"
                    ),
                    {"digest": sha("substituted"), "slot_id": dispatched.slot_id},
                )

    async with AsyncSession(model_database.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await session.execute(
                    text(
                        "update model_usage_budget_accounts "
                        "set lifetime_reserved_nanodollars=lifetime_reserved_nanodollars-1 "
                        "where project_id=:project_id"
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


async def test_profile_reader_requires_exact_project_and_selector(
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
                )
                == profile
            )
            with pytest.raises(ModelCallUnavailable, match="model_profile_unavailable"):
                await reader.read_exact(profile.selector, project_id=new_record_id())
            with pytest.raises(ModelCallUnavailable, match="model_profile_unavailable"):
                await reader.read_exact(
                    profile.selector.model_copy(
                        update={"profile_digest": sha("substituted-profile")}
                    ),
                    project_id=model_database.project_id,
                )
