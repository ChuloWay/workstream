"""Retained-data refusal and exact preservation through the real CP08 migration."""

from app.core.config import get_settings

import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.adapters.tasks import task_service
from app.adapters.projects import project_locked_policy_context_port
from scripts.schema_baseline_manifest import build_manifest
from tests.migration_fixtures import run_alembic_revision, run_scoped_revision_upgrade
from tests.projects.locked_policy_fixtures import activated_context

pytestmark = pytest.mark.postgres_schema_contract
PRIOR = "0023_guide_activation_custody"
OWN = "0024_task_policy_lineage"


async def _rows(factory):
    """Snapshot every retained product row, normalizing only the new nullable Task column."""
    async with factory() as session:
        names = list(
            await session.scalars(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version' ORDER BY tablename"
                )
            )
        )
        result = {}
        for name in names:
            value = (
                "to_jsonb(t) - 'locked_contribution_policy_version_id'"
                if name == "workstream_tasks"
                else "to_jsonb(t)"
            )
            result[name] = list(
                await session.scalars(
                    text(f'SELECT {value} FROM "{name}" t ORDER BY {value}::text')
                )
            )
        return result


async def _insert(session, table, values):
    """Insert explicit historical fields under the actual prior schema."""
    params, expressions = {}, []
    for key, value in values.items():
        params[key] = json.dumps(value) if isinstance(value, (dict, list)) else value
        expressions.append(
            f"CAST(:{key} AS json)" if isinstance(value, (dict, list)) else f":{key}"
        )
    await session.execute(
        text(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join(expressions)})"), params
    )


async def _prior_task(factory, receipt, actor, kind):
    project = receipt.command.target.proposal.project_id
    async with factory() as session, session.begin():
        facts = await project_locked_policy_context_port(session).lock_active_policy_context(
            project
        )
        locks = task_service(session, settings=get_settings())._policy_stamps(facts)
    locks.pop("locked_contribution_policy_version_id")
    task_id = str(uuid4())
    async with factory() as session, session.begin():
        await _insert(
            session,
            "workstream_tasks",
            {
                "id": task_id,
                "project_id": str(project),
                "title": "Retained task",
                "description": "Earlier work with no recorded contribution stamp",
                "source_type": "manual",
                "skill_tags": [],
                "created_by": str(actor.actor_profile_id),
                "status": "screening" if kind == "task" else "draft",
                **locks,
            },
        )
        if kind == "assignment":
            await _insert(
                session,
                "task_assignments",
                {
                    "id": str(uuid4()),
                    "task_id": task_id,
                    "contributor_id": str(actor.actor_profile_id),
                    "assigned_by": str(actor.actor_profile_id),
                    "status": "active",
                },
            )
        if kind == "submission":
            # Prior schema required a PaymentPolicy selector. The real retained row is
            # intentionally separate from any current no-payment writer.
            await _insert(
                session,
                "payment_policies",
                {
                    "id": str(uuid4()),
                    "project_id": str(project),
                    "guide_version": facts.guide_version,
                    "base_amount": 1,
                    "currency": "USD",
                    "payout_type": "fixed",
                },
            )
            await session.execute(
                text(
                    "UPDATE workstream_tasks SET locked_payment_policy_version=:version WHERE id=:id"
                ),
                dict(version=facts.guide_version, id=task_id),
            )
            await _insert(
                session,
                "submissions",
                {
                    "id": str(uuid4()),
                    "task_id": task_id,
                    "contributor_id": str(actor.actor_profile_id),
                    "version": 1,
                    "status": "submitted",
                    "summary": "Retained submission",
                    "worker_attestation": "Original work",
                    "artifact_hash_manifest": [],
                    "locked_payment_policy_version": facts.guide_version,
                    **locks,
                },
            )
    return task_id


async def test_0024_preserves_draft_tasks_and_activation_evidence(
    clean_postgres_database, migration_lock
):
    async with activated_context(clean_postgres_database) as (factory, receipt, actor, *_):
        with migration_lock():
            await run_alembic_revision("downgrade", PRIOR)
        task_id = await _prior_task(factory, receipt, actor, "draft")
        before = await _rows(factory)
        with migration_lock():
            await run_alembic_revision("upgrade", OWN)
        assert await _rows(factory) == before
        async with factory() as session:
            assert (
                await session.scalar(
                    text(
                        "SELECT locked_contribution_policy_version_id FROM workstream_tasks WHERE id=:id"
                    ),
                    dict(id=task_id),
                )
                is None
            )
            assert await session.scalar(text("SELECT version_num FROM alembic_version")) == OWN


@pytest.mark.parametrize("kind", ["task", "assignment", "submission"])
async def test_0024_refuses_retained_attempt_without_schema_or_row_mutation(
    clean_postgres_database,
    migration_lock,
    kind,
):
    async with activated_context(clean_postgres_database) as (factory, receipt, actor, *_):
        with migration_lock():
            await run_alembic_revision("downgrade", PRIOR)
        await _prior_task(factory, receipt, actor, kind)
        before_rows = await _rows(factory)
        before_schema = await build_manifest(clean_postgres_database)
        with pytest.raises(
            RuntimeError, match="cannot infer retained attempt contribution policy lineage"
        ):
            await run_scoped_revision_upgrade(clean_postgres_database, OWN)
        assert await build_manifest(clean_postgres_database) == before_schema
        assert await _rows(factory) == before_rows
        async with factory() as session:
            assert await session.scalar(text("SELECT version_num FROM alembic_version")) == PRIOR
