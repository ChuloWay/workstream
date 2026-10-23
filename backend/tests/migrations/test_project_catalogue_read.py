"""The catalogue action extends only the public audit CHECK under hostile search_path."""

import asyncio

from alembic import command
import asyncpg
import pytest

from app.db import session as db_session
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import _config


pytestmark = pytest.mark.postgres_schema_contract
NAME = "ck_audit_events_authorization_action_evidence"


async def _prepare_shadow(url):
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        role, database = await connection.fetchrow("select current_user, current_database()")
        assert role.startswith("workstream_role_") and database.startswith("workstream_test_")
        await connection.execute("create schema shadow")
        await connection.execute("create table shadow.audit_events "
                                 "(like public.audit_events including constraints)")
        before_public = await connection.fetchval(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='public.audit_events'::regclass and conname=$1", NAME)
        before_shadow = await connection.fetchval(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='shadow.audit_events'::regclass and conname=$1", NAME)
        assert before_public == before_shadow
        await connection.execute(
            f'alter role "{role}" in database "{database}" set search_path=shadow,public')
        return before_public, before_shadow
    finally:
        await connection.close()


async def _definitions(url):
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        return tuple([await connection.fetchval(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid=$1::regclass and conname=$2", table, NAME,
        ) for table in ("public.audit_events", "shadow.audit_events")])
    finally:
        await connection.close()


async def _restore_role_search_path(url):
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        role, database = await connection.fetchrow("select current_user, current_database()")
        assert role.startswith("workstream_role_") and database.startswith("workstream_test_")
        await connection.execute(
            f'alter role "{role}" in database "{database}" reset search_path')
    finally:
        await connection.close()


def test_upgrade_qualifies_public_constraint_under_shadowed_search_path(
    isolated_database_env, migration_lock,
):
    with migration_lock():
        asyncio.run(db_session.dispose_engine())
        asyncio.run(_drop_test_database_schema(isolated_database_env))
        command.upgrade(_config(), "0058_compensation_unit_create")
        before_public, before_shadow = asyncio.run(_prepare_shadow(isolated_database_env))
        try:
            command.upgrade(_config(), "0059_project_catalogue_read")
            after_public, after_shadow = asyncio.run(_definitions(isolated_database_env))
            assert before_public.count("project.catalogue.list") == 0
            assert after_public.count("project.catalogue.list") == 2
            assert after_shadow == before_shadow
        finally:
            asyncio.run(_restore_role_search_path(isolated_database_env))
