"""Populated source upgrade preserves retained truth; downgrade never deletes it."""

import asyncio

import asyncpg
import pytest
from alembic import command

from app.db import session as db_session
from tests.migration_fixtures import _config
from tests.reviews.acceptance.support import acceptance_source, insert_acceptance
from tests.reviews.acceptance.test_migration import snapshot as parent_snapshot

pytestmark = pytest.mark.postgres_schema_contract


async def snapshot(connection):
    result = await parent_snapshot(connection)
    result["final_acceptances"] = await connection.fetch(
        "SELECT to_jsonb(r)::text AS value FROM public.final_acceptances r ORDER BY 1"
    )
    return result


async def test_contribution_upgrade_preserves_sources(tmp_path, isolated_database_env, migration_lock):
    with migration_lock():
        await db_session.dispose_engine()
        url = isolated_database_env.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0014_final_acceptance")
        async with acceptance_source(tmp_path, isolated_database_env) as h:
            async with h.factory() as session:
                await insert_acceptance(session, h.acceptance)
                await session.commit()
            connection = await asyncpg.connect(url)
            try:
                before = await snapshot(connection)
                assert len(before["final_acceptances"]) == 1
                assert await connection.fetchval("SELECT to_regclass('public.contribution_records')") is None
                assert await connection.fetchval("SELECT to_regclass('public.compensation_awards')") is None
            finally:
                await connection.close()
            await asyncio.to_thread(command.upgrade, _config(), "0015_contribution_awards")
            connection = await asyncpg.connect(url)
            try:
                assert await snapshot(connection) == before
                for table in ("contribution_records", "compensation_awards"):
                    assert await connection.fetchval(f"SELECT count(*) FROM public.{table}") == 0
                assert await connection.fetchval("SELECT version_num FROM alembic_version") == "0015_contribution_awards"
            finally:
                await connection.close()
            with pytest.raises(RuntimeError, match="Workstream v0.1 migrations cannot be downgraded; recreate the database"):
                await asyncio.to_thread(command.downgrade, _config(), "0014_final_acceptance")
            connection = await asyncpg.connect(url)
            try:
                assert await snapshot(connection) == before
                assert await connection.fetchval("SELECT version_num FROM alembic_version") == "0015_contribution_awards"
            finally:
                await connection.close()
