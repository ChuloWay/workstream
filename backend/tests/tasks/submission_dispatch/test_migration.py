"""Additive custody never manufactures dispatch or authority for retained data."""

import asyncio
import json

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
        await asyncio.to_thread(command.upgrade, _config(), "0024_require_second_review_false")
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
                after = await snapshot()
                before_admissions = json.loads(before.pop("submission_bundle_admissions"))
                after_admissions = json.loads(after.pop("submission_bundle_admissions"))
                assert len(after_admissions) == len(before_admissions)
                for retained, upgraded in zip(
                    before_admissions, after_admissions, strict=True
                ):
                    assert set(upgraded) == set(retained) | {
                        "checker_remediation_manifest_id"
                    }
                    assert upgraded.pop("checker_remediation_manifest_id") is None
                    assert upgraded == retained
                assert after == before
                columns = await connection.fetch("""
                    SELECT table_name,data_type,is_nullable
                    FROM information_schema.columns
                    WHERE table_schema='public'
                      AND table_name=ANY($1::text[])
                      AND column_name='checker_remediation_manifest_id'
                    ORDER BY table_name
                """, [
                    "pre_submit_evidence_sets",
                    "submission_bundle_admissions",
                    "submission_dispatches",
                ])
                assert [tuple(row) for row in columns] == [
                    ("pre_submit_evidence_sets", "uuid", "YES"),
                    ("submission_bundle_admissions", "uuid", "YES"),
                    ("submission_dispatches", "uuid", "YES"),
                ]
                for table in (
                    "pre_submit_evidence_sets",
                    "submission_bundle_admissions",
                    "submission_dispatches",
                ):
                    assert await connection.fetchval(
                        f"SELECT count(*) FROM public.{table} "
                        "WHERE checker_remediation_manifest_id IS NOT NULL"
                    ) == 0
                assert await connection.fetchval("SELECT count(*) FROM public.submission_dispatches") == 0
                assert await connection.fetchval("SELECT count(*) FROM public.submission_binding_receipts") == 0
                assert await connection.fetchval("SELECT status FROM public.submission_bundle_admissions WHERE id=$1", h.created["admission_id"]) == "consumed"
            finally:
                await connection.close()
