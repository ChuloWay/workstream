"""Real PostgreSQL identity constraint and retained-data proof for 0026."""

import asyncio
from tests.migration_fixtures import current_schema_revision

from pathlib import Path
import re
from uuid import uuid4

from alembic import command
from alembic.config import Config
import asyncpg
import pytest

from app.modules.actors.api import SERVICE_IDENTITY_VALUES
from app.modules.actors.models import ActorProfile
from tests.migration_fixtures import run_guarded_revision_downgrade

pytestmark = pytest.mark.postgres_schema_contract
REVISION = '0026_outbox_dispatch_identity'
IDENTITY = 'workstream.outbox.dispatcher'


def config():
    """Use the actual guarded migration environment."""
    return Config(Path(__file__).resolve().parents[2] / 'alembic.ini')


async def seed(url, identity, *, with_link=True):
    """Commit exact manual provisioning facts with valid surrounding fields."""
    connection = await asyncpg.connect(url.replace('+asyncpg', ''))
    actor_id = str(uuid4())
    try:
        async with connection.transaction():
            await connection.execute(
                "insert into actor_profiles (id,actor_kind,status,provisioning_method,service_identity,created_by) "
                "values ($1,'service','active','manual_service_provisioning',$2,$1)", actor_id, identity,
            )
            if with_link:
                await connection.execute(
                    "insert into actor_identity_links (id,actor_profile_id,issuer,subject,subject_kind,status,linked_by) "
                    "values ($1,$2,'workstream.internal',$3,'service','active','workstream:system:bootstrap')",
                    str(uuid4()), actor_id, identity,
                )
        return actor_id
    finally:
        await connection.close()


async def snapshot(url):
    """Read independently committed records and exact constraint definitions."""
    connection = await asyncpg.connect(url.replace('+asyncpg', ''))
    try:
        constraints = await connection.fetch(
            "select q.conname,pg_get_constraintdef(q.oid) as definition from pg_constraint q "
            "join pg_class t on t.oid=q.conrelid join pg_namespace n on n.oid=t.relnamespace "
            "where n.nspname='public' order by t.relname,q.conname"
        )
        return {
            'revision': await connection.fetchval('select version_num from alembic_version'),
            'actors': await connection.fetchval("select jsonb_agg(to_jsonb(p) order by id)::text from actor_profiles p"),
            'links': await connection.fetchval("select jsonb_agg(to_jsonb(p) order by id)::text from actor_identity_links p"),
            'constraints': [tuple(row) for row in constraints],
        }
    finally:
        await connection.close()


def test_dispatch_identity_upgrade_preserves_records_and_exact_schema(
    isolated_database_env, migration_lock, migration_schema_at,
):
    """The committed forward upgrade changes only the closed identity CHECK."""
    with migration_lock():
        migration_schema_at('0025_task_command_replay')
        asyncio.run(seed(isolated_database_env, 'workstream.artifact.verifier'))
        before = asyncio.run(snapshot(isolated_database_env))
        assert before['revision'] == '0025_task_command_replay'
        with pytest.raises(asyncpg.CheckViolationError) as rejected:
            asyncio.run(seed(isolated_database_env, IDENTITY))
        assert rejected.value.constraint_name == 'ck_actor_profiles_kind_service_identity'
        command.upgrade(config(), REVISION)
        after = asyncio.run(snapshot(isolated_database_env))
        assert after['revision'] == REVISION
        assert (after['actors'], after['links']) == (before['actors'], before['links'])
        removed = set(before['constraints']) - set(after['constraints'])
        added = set(after['constraints']) - set(before['constraints'])
        assert len(removed) == len(added) == 1
        assert next(iter(removed))[0] == next(iter(added))[0] == 'ck_actor_profiles_kind_service_identity'
        definition = next(iter(added))[1]
        identities = re.findall(r'workstream\.[a-z_]+\.[a-z_]+', definition)
        assert set(identities) == (set(SERVICE_IDENTITY_VALUES) - {"workstream.task.assignment_reconciler"}) and len(identities) == len(SERVICE_IDENTITY_VALUES) - 1
        model = next(c for c in ActorProfile.__table__.constraints if c.name == 'ck_actor_profiles_kind_service_identity')
        assert set(re.findall(r'workstream\.[a-z_]+\.[a-z_]+', str(model.sqltext))) == set(identities) | {"workstream.task.assignment_reconciler"}
        asyncio.run(seed(isolated_database_env, IDENTITY))


def test_dispatch_identity_head_upgrade_is_repeatable(isolated_database_env, migration_lock):
    """The migration environment admits an already committed current head."""
    with migration_lock():
        command.upgrade(config(), 'head')
        asyncio.run(seed(isolated_database_env, IDENTITY))
        before = asyncio.run(snapshot(isolated_database_env))
        assert before['revision'] == current_schema_revision()
        command.upgrade(config(), 'head')
        assert asyncio.run(snapshot(isolated_database_env)) == before


def test_dispatch_identity_rejects_unknown_and_duplicate(isolated_database_env, migration_lock):
    """Correct surrounding fields isolate the closed identity and unique guards."""
    with migration_lock():
        asyncio.run(seed(isolated_database_env, IDENTITY))
        before = asyncio.run(snapshot(isolated_database_env))
        with pytest.raises(asyncpg.CheckViolationError) as unknown:
            asyncio.run(seed(isolated_database_env, 'workstream.outbox.unknown'))
        assert unknown.value.constraint_name == 'ck_actor_profiles_kind_service_identity'
        with pytest.raises(asyncpg.UniqueViolationError) as duplicate:
            asyncio.run(seed(isolated_database_env, IDENTITY))
        assert duplicate.value.constraint_name == 'service_identity'
        assert asyncio.run(snapshot(isolated_database_env)) == before


def test_dispatch_identity_downgrade_preserves_records(isolated_database_env, migration_lock):
    """Refusing downgrade preserves the registered actor and all stored history."""
    with migration_lock():
        asyncio.run(seed(isolated_database_env, IDENTITY))
        before = asyncio.run(snapshot(isolated_database_env))
        with pytest.raises(RuntimeError, match='cannot be downgraded'):
            asyncio.run(run_guarded_revision_downgrade(isolated_database_env, REVISION))
        assert asyncio.run(snapshot(isolated_database_env)) == before
