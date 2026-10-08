"""Populated predecessor upgrade preserves canonical owners without inventing packets."""

import asyncio

import asyncpg
import pytest
from alembic import command

from tests.historical_submission_fixtures import historical_material_fixture
from app.db import session as db_session
from tests.migration_fixtures import add_current_art_seed_column, restore_predecessor_evidence_schema
from tests.migration_fixtures import _config
from tests.reviews.packet.support import packet_source

pytestmark = pytest.mark.postgres_schema_contract


async def snapshot(connection):
    return {
        table: await connection.fetch(
            f"SELECT to_jsonb(r)::text AS value FROM public.{table} r ORDER BY 1"
        )
        for table in (
            "submissions",
            "checker_runs",
            "checker_results",
            "artifact_bindings",
            "artifact_contents",
            "guide_source_artifact_ingests",
            "project_guides",
            "guide_source_snapshot_items",
            "review_queue_entries",
            "review_leases",
        )
    }


async def test_packet_upgrade_preserves_existing_owners(
    tmp_path, isolated_database_env, migration_lock
):
    with migration_lock():
        await db_session.dispose_engine()
        url = isolated_database_env.replace("+asyncpg", "")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0011_task_routing_source")
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with packet_source(tmp_path, isolated_database_env, material_source=historical_material_fixture):
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            connection = await asyncpg.connect(url)
            try:
                before = await snapshot(connection)
                assert (
                    await connection.fetchval(
                        "SELECT to_regclass('public.review_packet_manifests')"
                    )
                    is None
                )
            finally:
                await connection.close()
            await asyncio.to_thread(command.upgrade, _config(), "0012_review_packet")
            connection = await asyncpg.connect(url)
            try:
                assert await snapshot(connection) == before
                assert (
                    await connection.fetchval("SELECT count(*) FROM public.review_packet_manifests")
                    == 0
                )
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM public.review_packet_guide_items"
                    )
                    == 0
                )
            finally:
                await connection.close()
