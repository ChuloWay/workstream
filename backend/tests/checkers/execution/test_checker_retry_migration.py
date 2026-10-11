"""0034 preserves retained checker custody and installs terminal retry closure."""

import asyncio

import asyncpg
import pytest
from alembic import command
from sqlalchemy.exc import IntegrityError

from app.adapters.checkers import evaluation_coordinator
from app.core.identifiers import new_record_id
from app.db import session as db_session
from tests.checkers.execution.test_checker_retry import _failed_source
from tests.checkers.post_submit.support import change_request
from tests.migration_fixtures import _config


pytestmark = pytest.mark.postgres_schema_contract
PREDECESSOR = "0033_checker_replacement"
SUCCESSOR = "0034_checker_retry"
RETAINED_TABLES = (
    "submissions",
    "submission_dispatches",
    "submission_binding_receipts",
    "checker_runs",
    "checker_results",
    "checker_submission_fences",
    "audit_events",
    "outbox_events",
    "outbox_delivery_attempts",
    "task_post_submit_routing_manifests",
    "workstream_tasks",
    "task_assignments",
    "pre_submit_evidence_sets",
    "pre_submit_evidence_results",
    "pre_submit_execution_attempts",
    "submission_bundle_admissions",
    "submission_bundle_durable_intents",
    "artifact_bindings",
    "artifact_contents",
    "artifact_put_attempts",
    "artifact_operation_receipts",
    "artifact_verification_receipts",
    "artifact_replicas",
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
    return {
        table: tuple(
            row["value"]
            for row in await connection.fetch(
                f"SELECT to_jsonb(r)::text AS value FROM public.{table} r ORDER BY value"
            )
        )
        for table in RETAINED_TABLES
    }


async def _source_custody(connection, submission_id):
    return await connection.fetchrow(
        """
        SELECT r.status, r.failure_code, r.result_digest,
          r.finalize_evidence_id IS NOT NULL AS finalized,
          fin.action_id='checker.post_submit.finalize' AS finalize_authority_valid,
          fin.event_type='SensitiveAuthorizationAllowed' AS finalize_allowed,
          r.completion_event_id IS NULL AS no_completion_event,
          f.current_run_id=r.id AS current_run,
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
        JOIN public.checker_runs r ON r.id=d.evaluation_attempt_id
        JOIN public.audit_events fin ON fin.id=r.finalize_evidence_id
        JOIN public.checker_submission_fences f ON f.submission_id=d.submission_id
        WHERE d.submission_id=$1
    """,
        submission_id,
    )


async def test_retry_upgrade_preserves_evidence_and_installs_closure(
    tmp_path,
    isolated_database_env,
    migration_lock,
    monkeypatch,
):
    with migration_lock():
        await _reset_to_predecessor(isolated_database_env)
        async with _failed_source(tmp_path, isolated_database_env, monkeypatch) as (h, _):
            connection = await _connection(isolated_database_env)
            try:
                assert (
                    await connection.fetchval("SELECT version_num FROM public.alembic_version")
                    == PREDECESSOR
                )
                assert (
                    await connection.fetchval(
                        "SELECT to_regclass('public.checker_retry_receipts') IS NULL"
                    )
                    is True
                )
                before = await _retained_rows(connection)
                assert all(
                    before[table]
                    for table in (
                        "submissions",
                        "submission_dispatches",
                        "checker_runs",
                        "checker_submission_fences",
                        "audit_events",
                        "outbox_events",
                        "pre_submit_evidence_sets",
                        "submission_bundle_admissions",
                        "artifact_bindings",
                    )
                )
                assert (
                    await connection.fetchval("""
                    SELECT count(*) FROM public.audit_events
                    WHERE action_id='checker.post_submit.finalize'
                """)
                    == 1
                )
                source = await _source_custody(connection, h.created.submission_id)
                assert source["status"] == "infrastructure_failed"
                assert source["failure_code"] == "material_unavailable"
                assert source["result_digest"].startswith("sha256:")
                assert all(
                    source[key] is True
                    for key in (
                        "finalized",
                        "finalize_authority_valid",
                        "finalize_allowed",
                        "no_completion_event",
                        "current_run",
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
                assert await _source_custody(connection, h.created.submission_id) == source
                assert (
                    await connection.fetchval("SELECT count(*) FROM public.checker_retry_receipts")
                    == 0
                )
                assert (
                    await connection.fetchval("""
                    SELECT EXISTS (SELECT 1 FROM pg_trigger t
                    JOIN pg_class c ON c.oid=t.tgrelid
                    WHERE c.oid='public.checker_submission_fences'::regclass
                      AND t.tgname='checker_failed_supersession_receipt'
                      AND t.tgdeferrable)
                """)
                    is True
                )
                assert (
                    await connection.fetchval(
                        "SELECT public.checker_retry_receipt_valid($1)", new_record_id()
                    )
                    is False
                )
            finally:
                await connection.close()

            successor = change_request(
                h.request,
                evaluation_request_id=new_record_id(),
                evaluation_generation=2,
            )
            with pytest.raises(
                IntegrityError,
                match="terminal checker infrastructure retry requires Operator receipt",
            ):
                async with h.factory.begin() as session:
                    await evaluation_coordinator(session).reserve_current_evaluation(successor)
            connection = await _connection(isolated_database_env)
            try:
                assert await _retained_rows(connection) == before
                assert (
                    await connection.fetchval("SELECT count(*) FROM public.checker_retry_receipts")
                    == 0
                )
            finally:
                await connection.close()
