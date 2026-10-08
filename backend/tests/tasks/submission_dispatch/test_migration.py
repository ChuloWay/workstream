"""Additive custody never manufactures dispatch or authority for retained data."""

import asyncio

import asyncpg
import pytest
from alembic import command

from app.db import session as db_session
from tests.historical_submission_fixtures import historical_material_fixture
from tests.migration_fixtures import _config, current_schema_revision

pytestmark = pytest.mark.postgres_schema_contract


async def test_upgrade_preserves_retained_owners_without_backfill(tmp_path, isolated_database_env, migration_lock):
    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0023_remove_task_payment_policy")
        async with historical_material_fixture(tmp_path, isolated_database_env) as h:
            connection = await asyncpg.connect(url)
            tables = ("submissions", "submission_bundle_admissions", "artifact_bindings", "audit_events",
                      "checker_runs", "outbox_events", "workstream_tasks", "task_assignments")
            async def snapshot():
                return {table: await connection.fetchval(
                    f"SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text),'[]') FROM public.{table} r"
                ) for table in tables}
            try:
                before = await snapshot()
                await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
                assert await snapshot() == before
                assert await connection.fetchval("SELECT count(*) FROM public.submission_dispatches") == 0
                assert await connection.fetchval("SELECT count(*) FROM public.submission_binding_receipts") == 0
                assert await connection.fetchval("SELECT status FROM public.submission_bundle_admissions WHERE id=$1", h.created.admission_id) == "consumed"
            finally:
                await connection.close()
