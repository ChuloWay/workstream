"""0034 preserves initial custody and refuses uncaused retained replacements."""

import asyncio

import asyncpg
import pytest
from alembic import command
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from tests.historical_submission_fixtures import restore_archived_snapshot
from tests.migration_fixtures import _config


pytestmark = pytest.mark.postgres_schema_contract
PREDECESSOR = "0033_contribution_reads"
SUCCESSOR = "0034_checker_replacement"
RETAINED_TABLES = (
    "submissions",
    "pre_submit_evidence_sets",
    "submission_bundle_admissions",
    "submission_dispatches",
    "submission_binding_receipts",
    "artifact_bindings",
    "checker_runs",
    "checker_submission_fences",
    "audit_events",
    "outbox_events",
    "workstream_tasks",
    "task_assignments",
    "task_post_submit_routing_manifests",
)


async def _connection(database_url):
    return await asyncpg.connect(database_url.replace("+asyncpg", ""))


async def _reset_to_predecessor(database_url):
    await db_session.dispose_engine()
    connection = await _connection(database_url)
    try:
        await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    finally:
        await connection.close()
    await asyncio.to_thread(command.upgrade, _config(), PREDECESSOR)


async def _retained_rows(connection):
    """Exclude only the nullable cause columns introduced by 0034."""
    return {
        table: tuple(
            row["value"]
            for row in await connection.fetch(
                f"SELECT (to_jsonb(r)-'checker_remediation_manifest_id')::text AS value "
                f"FROM public.{table} r ORDER BY value"
            )
        )
        for table in RETAINED_TABLES
    }


async def _custody(connection):
    return await connection.fetchrow("""
        SELECT d.creation_kind, d.submission_version,
          public.submission_dispatch_valid(d) AS dispatch_valid,
          public.submission_binding_receipt_valid(br) AS binding_valid,
          public.submission_authority_receipt_valid(
            d.creation_decision_id, public.submission_creation_resource(d.submission_id), true
          ) AS creation_authority_valid,
          public.submission_authority_receipt_valid(
            d.binding_decision_id, public.submission_binding_resource(d.admission_id), false
          ) AS binding_authority_valid
        FROM public.submission_dispatches d
        JOIN public.submission_binding_receipts br ON br.admission_id=d.admission_id
        ORDER BY d.submission_version DESC LIMIT 1
    """)


async def test_upgrade_preserves_archived_initial_rows_and_exact_receipts(
    tmp_path,
    isolated_database_env,
    migration_lock,
):
    with migration_lock():
        await _reset_to_predecessor(isolated_database_env)
        await restore_archived_snapshot(
            isolated_database_env, "0033_checker_replacement_initial"
        )
        connection = await _connection(isolated_database_env)
        try:
            assert (
                await connection.fetchval("SELECT version_num FROM public.alembic_version")
                == PREDECESSOR
            )
            assert (
                await connection.fetchval("SELECT count(*) FROM public.submissions WHERE version=1")
                == 1
            )
            before = await _retained_rows(connection)
            assert all(
                before[table]
                for table in (
                    "submissions",
                    "pre_submit_evidence_sets",
                    "submission_bundle_admissions",
                    "submission_dispatches",
                    "submission_binding_receipts",
                    "audit_events",
                    "checker_runs",
                    "outbox_events",
                )
            )
            initial = await _custody(connection)
            assert initial["creation_kind"] == "initial"
            assert initial["submission_version"] == 1
            assert all(
                initial[key] is True
                for key in (
                    "dispatch_valid",
                    "binding_valid",
                    "creation_authority_valid",
                    "binding_authority_valid",
                )
            )
        finally:
            await connection.close()

        await db_session.dispose_engine()
        await asyncio.to_thread(command.upgrade, _config(), SUCCESSOR)
        connection = await _connection(isolated_database_env)
        try:
            assert (
                await connection.fetchval("SELECT version_num FROM public.alembic_version")
                == SUCCESSOR
            )
            assert await _retained_rows(connection) == before
            assert (
                await connection.fetchval("""
                SELECT count(*) FROM public.submission_dispatches
                WHERE checker_remediation_manifest_id IS NOT NULL
            """)
                == 0
            )
            assert (
                await connection.fetchval("""
                SELECT count(*) FROM public.submission_bundle_admissions
                WHERE checker_remediation_manifest_id IS NOT NULL
            """)
                == 0
            )
            assert (
                await connection.fetchval("""
                SELECT count(*) FROM public.pre_submit_evidence_sets
                WHERE checker_remediation_manifest_id IS NOT NULL
            """)
                == 0
            )
            migrated = await _custody(connection)
            assert migrated["creation_kind"] == "initial"
            assert migrated["submission_version"] == 1
            assert all(
                migrated[key] is True
                for key in (
                    "dispatch_valid",
                    "binding_valid",
                    "creation_authority_valid",
                    "binding_authority_valid",
                )
            )
        finally:
            await connection.close()


async def test_retained_uncaused_revision_refuses_upgrade_without_changes(
    tmp_path,
    isolated_database_env,
    migration_lock,
):
    """The archived predecessor can retain version two without a source ID."""
    with migration_lock():
        await _reset_to_predecessor(isolated_database_env)
        await restore_archived_snapshot(
            isolated_database_env, "0033_checker_replacement_revision"
        )

        await db_session.dispose_engine()
        connection = await _connection(isolated_database_env)
        try:
            assert (
                await connection.fetchval("SELECT version_num FROM public.alembic_version")
                == PREDECESSOR
            )
            assert (
                await connection.fetchval("""
                SELECT count(*) FROM public.submission_dispatches
                WHERE creation_kind='revision' AND submission_version=2
            """)
                == 1
            )
            assert (
                await connection.fetchval("""
                SELECT count(*) FROM public.task_post_submit_routing_manifests
                WHERE routing_recommendation='needs_revision'
            """)
                == 1
            )
            before = await _retained_rows(connection)
            before_custody = await _custody(connection)
            assert before_custody["dispatch_valid"] is True
            assert before_custody["binding_valid"] is True
        finally:
            await connection.close()

        with pytest.raises(
            DBAPIError, match="retained replacement cause and receipts cannot be proven"
        ):
            await asyncio.to_thread(command.upgrade, _config(), SUCCESSOR)
        connection = await _connection(isolated_database_env)
        try:
            assert (
                await connection.fetchval("SELECT version_num FROM public.alembic_version")
                == PREDECESSOR
            )
            assert await _retained_rows(connection) == before
            assert await _custody(connection) == before_custody
            for table in (
                "pre_submit_evidence_sets",
                "submission_bundle_admissions",
                "submission_dispatches",
            ):
                assert not await connection.fetchval(
                    """
                    SELECT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=$1
                      AND column_name='checker_remediation_manifest_id')
                """,
                    table,
                )
        finally:
            await connection.close()
