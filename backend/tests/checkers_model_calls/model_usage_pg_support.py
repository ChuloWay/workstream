"""Shared isolated PostgreSQL substrate for MODEL-USAGE owner tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import runpy
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id


def _sha(label: str) -> str:
    return canonical_json_hash({"label": label})


@dataclass(frozen=True)
class DatabaseFacts:
    """Stable owner identities and engine for one isolated MODEL schema."""

    engine: AsyncEngine
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    submission_id: UUID
    registry_entry_id: UUID
    registry_entry_digest: str


@pytest.fixture
async def model_database(postgres_database_url: str):
    """Install 0061 against the minimal real owner tables used by MODEL tests."""
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
    registry_entry_digest = _sha("registry")
    migration = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "alembic/versions/0061_model_usage.py")
    )

    def isolated(statement: str) -> str:
        return statement.replace("public.", f'"{schema}".').replace(
            "pg_catalog,public,pg_temp", f'pg_catalog,"{schema}",pg_temp'
        )

    async with engine.begin() as connection:
        await connection.execute(text(f'create schema "{schema}"'))
        for statement in (
            "create table projects(id uuid primary key)",
            "create table workstream_tasks(id uuid primary key, project_id uuid not null, unique(id,project_id))",
            "create table task_assignments(id uuid primary key, task_id uuid not null, project_id uuid not null)",
            "create table submissions(id uuid primary key, task_id uuid not null, version integer not null, unique(id,task_id,version))",
            "create table external_checker_registry_entries(id uuid primary key,entry_digest text not null,phase text not null)",
            "create table checker_runs(id uuid primary key,task_id uuid,submission_id uuid,submission_version integer,project_id uuid,evaluation_request_id uuid,phase text,evaluation_generation integer,request_json text,worker_lease_id uuid,worker_lease_generation integer,worker_lease_expires_at timestamptz,status text)",
            "create table actor_profiles(id uuid primary key,actor_kind text default 'human',status text default 'active',service_identity text)",
            "create table audit_events(id uuid primary key, event_domain text, event_type text, actor_ref_kind text, actor_id text, action_id text, permission_id text, denial_code text, after_facts json)",
            "create table artifact_bindings(id uuid primary key)",
            "create table artifact_contents(id uuid primary key)",
            "create table artifact_put_attempts(id uuid primary key)",
            "create table artifact_verification_receipts(id uuid primary key)",
            "create table project_guide_compilation_attempts(id uuid primary key,project_id uuid not null,guide_id uuid not null,source_snapshot_id uuid not null,setup_run_id uuid not null,setup_generation bigint not null,runtime_configuration jsonb,runtime_configuration_hash text,status text)",
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
