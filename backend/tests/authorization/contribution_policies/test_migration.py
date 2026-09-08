"""Exact audit vocabulary migration and direct-SQL privacy regression proof."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.modules.tasks.models import AuditEvent
from .postgresql_support import world, snapshot

PRIOR = "0011_review_policy_human_review"
OWN = "0012_contribution_policy_audit_resource"
TOKEN = ", ('contribution_policy'::character varying)::text"


async def schema_value(statement):
    """Read installed schema facts through an independent session."""
    async with db_session.get_session_factory()() as session:
        return await session.scalar(text(statement))


async def definition():
    """Read the actual PostgreSQL check expression, including every privacy clause."""
    return await schema_value(
        "select pg_get_constraintdef(oid) from pg_constraint where conrelid='audit_events'::regclass and conname='ck_audit_events_authority_privacy_bounds'"
    )


async def migrate(direction, revision, migration_lock):
    """Run actual Alembic under the canonical schema-owner lock."""
    await db_session.dispose_engine()
    config = Config(Path(__file__).resolve().parents[3] / "alembic.ini")
    with migration_lock():
        await asyncio.to_thread(getattr(command, direction), config, revision)


@pytest.mark.asyncio
@pytest.mark.postgres_schema_contract
async def test_audit_resource_migration_roundtrip_preserves_every_other_clause(
    auth_database_env, migration_lock
):
    await migrate("downgrade", PRIOR, migration_lock)
    before = await definition()
    assert TOKEN not in before
    await migrate("upgrade", OWN, migration_lock)
    after = await definition()
    assert after.count(TOKEN) == 1
    assert after.replace(TOKEN, "", 1) == before
    await migrate("downgrade", PRIOR, migration_lock)
    assert await definition() == before
    await migrate("upgrade", OWN, migration_lock)
    assert await definition() == after
    assert await schema_value("select version_num from alembic_version") == OWN


@pytest.mark.asyncio
@pytest.mark.postgres_schema_contract
async def test_audit_resource_downgrade_preserves_retained_policy_evidence(
    admin_access, migration_lock
):
    target = await world(admin_access)
    await target.execute("create_draft", target.request("create_draft"))
    before, constraint = await snapshot(target.project), await definition()
    with pytest.raises(RuntimeError, match="ContributionPolicy audit history prevents downgrade"):
        await migrate("downgrade", PRIOR, migration_lock)
    assert await snapshot(target.project) == before
    assert await definition() == constraint
    assert await schema_value("select version_num from alembic_version") == OWN


async def clone_decision(event, changes):
    """Bypass Python input validation to exercise the database's closed vocabulary."""
    identity = str(uuid4())
    payload = {"id": identity, "entity_id": identity, **changes}
    async with db_session.get_session_factory()() as session, session.begin():
        await session.execute(
            text(
                "insert into audit_events select (jsonb_populate_record(null::audit_events, to_jsonb(a) || cast(:changes as jsonb))).* from audit_events a where a.id=:id"
            ),
            {"id": event.id, "changes": json.dumps(payload)},
        )
    return identity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper,constraint",
    (
        ("resource", "ck_audit_events_authority_privacy_bounds"),
        ("private_fact", "ck_audit_events_fact_bounds"),
    ),
)
async def test_policy_audit_sql_retains_resource_and_private_fact_guards(
    admin_access, tamper, constraint
):
    target = await world(admin_access)
    await target.execute("create_draft", target.request("create_draft"))
    async with db_session.get_session_factory()() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.project_id == str(target.project),
                AuditEvent.action_id == "contribution.policy.create_draft",
            )
        )
    control = await clone_decision(event, {})
    async with db_session.get_session_factory()() as session:
        assert (await session.get(AuditEvent, control)).resource_type == "contribution_policy"
    changes = (
        {"resource_type": "unregistered_policy_resource"}
        if tamper == "resource"
        else {"after_facts": {**event.after_facts, "private_material": "must-not-persist"}}
    )
    before = await snapshot(target.project)
    with pytest.raises(DBAPIError, match=constraint):
        await clone_decision(event, changes)
    assert await snapshot(target.project) == before


@pytest.mark.parametrize(
    "shape", ("missing_anchor", "duplicate_anchor", "existing_token", "first_token")
)
def test_audit_resource_migration_rejects_ambiguous_constraint_shape(monkeypatch, shape):
    """A malformed installed expression cannot reach either constraint DDL call."""
    import importlib.util
    from unittest.mock import Mock

    path = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/0012_contribution_policy_audit_resource.py"
    )
    spec = importlib.util.spec_from_file_location("cp05_audit_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expressions = {
        "missing_anchor": "CHECK (true)",
        "duplicate_anchor": module._ANCHOR + module._ANCHOR,
        "existing_token": module._ANCHOR + module._TOKEN,
        "first_token": module._RESOURCE + module._ANCHOR,
    }
    connection = Mock()
    connection.execute.return_value.scalar_one.return_value = expressions[shape]
    monkeypatch.setattr(module.op, "get_bind", lambda: connection)
    ddl = Mock()
    monkeypatch.setattr(module.op, "execute", ddl)
    with pytest.raises(RuntimeError, match="audit resource constraint shape changed"):
        module.upgrade()
    assert (
        str(connection.execute.call_args_list[0].args[0])
        == "lock table audit_events in access exclusive mode"
    )
    ddl.assert_not_called()
