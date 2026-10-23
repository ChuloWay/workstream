"""Real PostgreSQL proof for one-use checker model invocation grants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import runpy
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.checkers.api.model_calls import (
    ModelActionEvidence,
    ModelCallExecutionFacts,
    ModelPaidSlotKey,
    model_action_digest,
)
from app.modules.checkers.model_calls.grants import ModelInvocationGrants
from tests.checkers_model_calls.test_model_call_transactions_postgresql import (
    BoundaryPorts,
    DatabaseFacts,
    execution,
    model_database as _ledger_database,
    provision,
    service,
    sha,
    slot,
)


ledger_database_fixture = _ledger_database


class _CaptureOperations:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


@dataclass(frozen=True)
class GrantDatabase:
    facts: DatabaseFacts
    execution: ModelCallExecutionFacts
    slot: ModelPaidSlotKey
    prepared_attempt_id: UUID
    prepared_request_sha256: str


class GrantBoundaries:
    """Persist exact fake AUTH receipts while PostgreSQL owns all ancestry checks."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        evidence_id: UUID | None = None,
        action: str = "checker.model_call.grant",
    ) -> None:
        self._session = session
        self._evidence_id = evidence_id
        self._action = action

    async def authorize_grant(
        self,
        execution_facts: ModelCallExecutionFacts,
        paid_slot: ModelPaidSlotKey,
        external_request_digest: str,
        token_hash: str,
    ) -> ModelActionEvidence:
        facts = {
            "execution": execution_facts.model_dump(mode="json"),
            "slot": paid_slot.model_dump(mode="json"),
            "external_request_digest": external_request_digest,
            "token_hash": token_hash,
        }
        evidence = ModelActionEvidence(
            evidence_id=self._evidence_id or new_record_id(),
            facts_digest=model_action_digest("grant", facts),
        )
        await self._session.execute(
            text(
                "insert into audit_events(id,event_domain,event_type,actor_ref_kind,actor_id,"
                "action_id,permission_id,denial_code,after_facts) values "
                "(:id,'authority','SensitiveAuthorizationAllowed','actor_profile',:actor,"
                ":action,'checker.model_call.grant',null,cast(:after as jsonb)) "
                "on conflict(id) do nothing"
            ),
            {
                "id": evidence.evidence_id,
                "actor": str(new_record_id()),
                "action": self._action,
                "after": json.dumps(
                    {"allowed": True, "resource_context_digest": sha("grant authority")}
                ),
            },
        )
        return evidence

    async def require_current(
        self,
        _: ModelCallExecutionFacts,
        __: ModelPaidSlotKey,
    ) -> None:
        return None


def _isolated(statement: str, schema: str) -> str:
    return statement.replace("public.", f'"{schema}".').replace(
        "pg_catalog,public,pg_temp", f'pg_catalog,"{schema}",pg_temp'
    )


@pytest.fixture
async def grant_database(ledger_database_fixture: DatabaseFacts) -> GrantDatabase:
    ledger_database = ledger_database_fixture
    async with ledger_database.engine.connect() as connection:
        schema = str(await connection.scalar(text("select current_schema()")))
    migration = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "alembic/versions/0060_checker_model_runtime.py")
    )
    capture = _CaptureOperations()
    migration["_upgrade_invocation_grants"].__globals__["op"] = capture
    migration["_upgrade_invocation_grants"]()
    async with ledger_database.engine.begin() as connection:
        await connection.execute(
            text(
                "alter table external_checker_registry_entries "
                "add column entry_digest text, add column phase text"
            )
        )
        await connection.execute(
            text(
                "update external_checker_registry_entries set entry_digest=:digest,"
                "phase='post_submit' where id=:id"
            ),
            {
                "digest": ledger_database.registry_entry_digest,
                "id": ledger_database.registry_entry_id,
            },
        )
        await connection.execute(
            text(
                "alter table checker_runs add column project_id uuid, add column task_id uuid,"
                "add column submission_id uuid, add column submission_version integer,"
                "add column evaluation_request_id uuid, add column evaluation_generation integer,"
                "add column request_json text, add column worker_lease_id uuid,"
                "add column worker_lease_generation integer,"
                "add column worker_lease_expires_at timestamptz, add column status text,"
                "add column phase text, add column selected_post_submit_policy_sha256 text,"
                "add column selected_post_submit_policy_body jsonb,"
                "add column locked_post_submit_checker_policy_hash text"
            )
        )
        for statement in capture.statements:
            await connection.execute(text(_isolated(statement, schema)))

    profile = await provision(ledger_database, BoundaryPorts(), limit=100_000)
    current = execution(ledger_database)
    paid_slot = slot(ledger_database, profile, "model_judge")
    request_sha256 = sha("prepared request")
    async with AsyncSession(ledger_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            prepared = await service(session, BoundaryPorts()).prepare_attempt(
                current,
                paid_slot,
                registry_entry_id=ledger_database.registry_entry_id,
                request_sha256=request_sha256,
            )

    policy_sha256 = sha("locked post policy")
    policy = {
        "schema_version": "external_post_submit_policy.v1",
        "entries": [
            {
                "requirement_id": paid_slot.requirement_id,
                "stage": "post_submit",
                "registry": {
                    "registry_entry_id": str(ledger_database.registry_entry_id),
                    "entry_digest": paid_slot.registry_entry_digest,
                },
                "configuration": {
                    "model_profile_id": str(paid_slot.profile_id),
                    "model_profile_version": paid_slot.profile_version,
                    "model_profile_digest": paid_slot.profile_digest,
                },
                "configuration_sha256": paid_slot.configuration_sha256,
            }
        ],
        "policy_sha256": policy_sha256,
    }
    async with ledger_database.engine.begin() as connection:
        await connection.execute(
            text(
                "insert into checker_runs(id,project_id,task_id,submission_id,submission_version,"
                "evaluation_request_id,evaluation_generation,request_json,worker_lease_id,"
                "worker_lease_generation,worker_lease_expires_at,status,phase,"
                "selected_post_submit_policy_sha256,selected_post_submit_policy_body,"
                "locked_post_submit_checker_policy_hash) values "
                "(:id,:project,:task,:submission,:version,:request,:generation,:request_json,"
                ":lease,:lease_generation,:expires,'running','post_submission',:policy_sha,"
                "cast(:policy as jsonb),:policy_sha)"
            ),
            {
                "id": current.checker_run_id,
                "project": current.project_id,
                "task": current.task_id,
                "submission": current.submission_id,
                "version": current.submission_version,
                "request": current.evaluation_request_id,
                "generation": current.evaluation_generation,
                "request_json": json.dumps({"assignment_id": str(current.assignment_id)}),
                "lease": current.worker_lease_id,
                "lease_generation": current.worker_lease_generation,
                "expires": current.worker_lease_expires_at,
                "policy_sha": policy_sha256,
                "policy": json.dumps(policy),
            },
        )
    return GrantDatabase(
        ledger_database,
        current,
        paid_slot,
        prepared.attempt_id,
        request_sha256,
    )


async def _issue(
    database: GrantDatabase,
    *,
    boundaries: GrantBoundaries,
    session: AsyncSession,
):
    return await ModelInvocationGrants(
        session,
        authority=boundaries,
        current=boundaries,
    ).issue(
        database.execution,
        database.slot,
        sha("external checker request"),
        registry_entry_id=database.facts.registry_entry_id,
    )


async def test_grant_round_trip_consumes_once_and_becomes_immutable(
    grant_database: GrantDatabase,
) -> None:
    async with AsyncSession(grant_database.facts.engine, expire_on_commit=False) as session:
        async with session.begin():
            boundaries = GrantBoundaries(session)
            grant = await _issue(
                grant_database,
                boundaries=boundaries,
                session=session,
            )
            owner = ModelInvocationGrants(
                session,
                authority=boundaries,
                current=boundaries,
            )
            facts = await owner.resolve(grant.grant_id, grant.binding_digest)
            await owner.consume_prepared(
                facts,
                request_sha256=grant_database.prepared_request_sha256,
                prepared_attempt_id=grant_database.prepared_attempt_id,
            )
            row = (
                (
                    await session.execute(
                        text(
                            "select selected_request_sha256,selected_attempt_id,consumed_at,"
                            "issued_at,expires_at,token_hash from "
                            "checker_model_invocation_grants"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert row.selected_request_sha256 == grant_database.prepared_request_sha256
            assert row.selected_attempt_id == grant_database.prepared_attempt_id
            assert row.issued_at < row.consumed_at < row.expires_at
            assert row.token_hash != grant.grant_id

    for mutation in (
        "update checker_model_invocation_grants set external_request_digest="
        "'sha256:" + "d" * 64 + "'",
        "delete from checker_model_invocation_grants",
        "truncate checker_model_invocation_grants",
    ):
        async with AsyncSession(grant_database.facts.engine) as session:
            with pytest.raises(DBAPIError):
                async with session.begin():
                    await session.execute(text(mutation))


async def test_grant_rejects_reused_or_wrong_authority_and_stale_db_clock(
    grant_database: GrantDatabase,
) -> None:
    evidence_id = new_record_id()
    async with AsyncSession(grant_database.facts.engine) as session:
        async with session.begin():
            boundaries = GrantBoundaries(session, evidence_id=evidence_id)
            await _issue(grant_database, boundaries=boundaries, session=session)

    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session, evidence_id=evidence_id)
                await _issue(grant_database, boundaries=boundaries, session=session)

    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session, action="checker.model_call.dispatch")
                await _issue(grant_database, boundaries=boundaries, session=session)

    expired = grant_database.execution.model_copy(
        update={"worker_lease_expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    async with grant_database.facts.engine.begin() as connection:
        await connection.execute(
            text("update checker_runs set worker_lease_expires_at=:expires where id=:id"),
            {"expires": expired.worker_lease_expires_at, "id": expired.checker_run_id},
        )
    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session)
                await ModelInvocationGrants(
                    session,
                    authority=boundaries,
                    current=boundaries,
                ).issue(
                    expired,
                    grant_database.slot,
                    sha("expired request"),
                    registry_entry_id=grant_database.facts.registry_entry_id,
                )


async def test_grant_rejects_locked_binding_and_consumption_substitution(
    grant_database: GrantDatabase,
) -> None:
    async with AsyncSession(grant_database.facts.engine, expire_on_commit=False) as session:
        async with session.begin():
            boundaries = GrantBoundaries(session)
            grant = await _issue(grant_database, boundaries=boundaries, session=session)
            facts = await ModelInvocationGrants(
                session,
                authority=boundaries,
                current=boundaries,
            ).resolve(grant.grant_id, grant.binding_digest)

    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await session.execute(
                    text(
                        "update checker_model_invocation_grants "
                        "set external_request_digest=:request"
                    ),
                    {"request": sha("immutable grant facts")},
                )

    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await session.execute(
                    text(
                        "update checker_model_invocation_grants set "
                        "selected_request_sha256=:request,selected_attempt_id=:attempt,"
                        "consumed_at=clock_timestamp()"
                    ),
                    {
                        "request": sha("substituted request"),
                        "attempt": grant_database.prepared_attempt_id,
                    },
                )

    other_slot = grant_database.slot.model_copy(update={"requirement_id": "other_judge"})
    other_request = sha("other prepared request")
    async with AsyncSession(grant_database.facts.engine, expire_on_commit=False) as session:
        async with session.begin():
            other_attempt = await service(session, BoundaryPorts()).prepare_attempt(
                grant_database.execution,
                other_slot,
                registry_entry_id=grant_database.facts.registry_entry_id,
                request_sha256=other_request,
            )
    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await session.execute(
                    text(
                        "update checker_model_invocation_grants set "
                        "selected_request_sha256=:request,selected_attempt_id=:attempt,"
                        "consumed_at=clock_timestamp()"
                    ),
                    {"request": other_request, "attempt": other_attempt.attempt_id},
                )

    foreign_registry = new_record_id()
    async with grant_database.facts.engine.begin() as connection:
        await connection.execute(
            text(
                "insert into external_checker_registry_entries(id,entry_digest,phase) "
                "values (:id,:digest,'post_submit')"
            ),
            {"id": foreign_registry, "digest": grant_database.slot.registry_entry_digest},
        )
    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session)
                await ModelInvocationGrants(
                    session,
                    authority=boundaries,
                    current=boundaries,
                ).issue(
                    grant_database.execution,
                    grant_database.slot,
                    sha("foreign registry request"),
                    registry_entry_id=foreign_registry,
                )

    foreign_project = new_record_id()
    async with grant_database.facts.engine.begin() as connection:
        await connection.execute(
            text("insert into projects(id) values (:id)"),
            {"id": foreign_project},
        )
    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session)
                await ModelInvocationGrants(
                    session,
                    authority=boundaries,
                    current=boundaries,
                ).issue(
                    grant_database.execution.model_copy(update={"project_id": foreign_project}),
                    grant_database.slot.model_copy(update={"project_id": foreign_project}),
                    sha("foreign project request"),
                    registry_entry_id=grant_database.facts.registry_entry_id,
                )

    async with grant_database.facts.engine.begin() as connection:
        await connection.execute(
            text(
                "update checker_runs set selected_post_submit_policy_body="
                "jsonb_set(selected_post_submit_policy_body,"
                "'{entries,0,configuration_sha256}',to_jsonb(cast(:digest as text)))"
            ),
            {"digest": sha("substituted configuration")},
        )
    async with AsyncSession(grant_database.facts.engine) as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                boundaries = GrantBoundaries(session)
                await _issue(grant_database, boundaries=boundaries, session=session)

    assert facts.slot == grant_database.slot


async def test_grant_trigger_locks_authority_then_task_then_checker_ancestry(
    grant_database: GrantDatabase,
) -> None:
    async with grant_database.facts.engine.connect() as connection:
        definition = await connection.scalar(
            text(
                "select pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n "
                "on n.oid=p.pronamespace where p.proname="
                "'guard_checker_model_invocation_grant' and n.nspname=current_schema()"
            )
        )
    insert_branch = definition.split("IF jsonb_typeof", maxsplit=1)[1]
    assert insert_branch.index("audit_events") < insert_branch.index("workstream_tasks")
    assert insert_branch.index("workstream_tasks") < insert_branch.index("checker_runs")
    assert insert_branch.index("checker_runs") < insert_branch.index("checker_model_profiles")
