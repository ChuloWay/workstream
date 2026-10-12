"""0035 preserves retained checker custody and installs terminal retry closure."""

import asyncio
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from uuid import UUID

import asyncpg
import pytest
from alembic import command
from sqlalchemy.exc import IntegrityError

from app.adapters.checkers import evaluation_coordinator
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.checkers.api.post_submit import PostSubmissionEvaluationRequest
from tests.checkers.post_submit.support import change_request
from tests.migration_fixtures import _config


pytestmark = pytest.mark.postgres_schema_contract
PREDECESSOR = "0034_checker_replacement"
SUCCESSOR = "0035_checker_retry"
# Pin the last F3 writer: current F4 delivery reads the 0035 retry table.
HISTORICAL_WRITER = "926b4ef118db3708e50d1869db5ee78a79e5b5de"
HISTORICAL_SEED = """
import asyncio
import json
import os
from pathlib import Path
import sys

import pytest

from app.adapters.artifacts import internal_workers
from app.adapters.artifacts.local import LocalStorageAdapter
from app.db import session as db_session
from app.interfaces.artifacts import ArtifactObjectMissingError
from tests.post_submit_materialization_helpers import material_fixture
from tests.tasks.evaluation_delivery.support import delivery_fixture, outcome, state
from tests.tasks.evaluation_delivery.test_worker_materialization import _worker_port


async def seed():
    database_url = os.environ["WS_MIGRATION_DATABASE_URL"]
    tmp_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])

    def missing(_store, _reference):
        raise ArtifactObjectMissingError("controlled verified object loss")

    try:
        with pytest.MonkeyPatch.context() as monkeypatch:
            async with material_fixture(tmp_path, database_url, provider="local") as h:
                port = _worker_port(h, monkeypatch)
                try:
                    delivery = await delivery_fixture(h, materialization=port)
                    with monkeypatch.context() as patch:
                        patch.setattr(LocalStorageAdapter, "open", missing)
                        initial = await delivery.delivery.deliver(
                            h.created.evaluation_event_id, h.request.project_id, "retry-source",
                        )
                    assert outcome(initial)["delivery_state"] == "acknowledged"
                    saved = await state(h)
                    assert saved["run"]["status"] == "infrastructure_failed"
                    assert json.loads(saved["run"]["result_json"])["infrastructure_failure_code"] == "material_unavailable"
                    result_path.write_text(json.dumps({
                        "submission_id": str(h.created.submission_id),
                        "request": h.request.model_dump(mode="json"),
                    }))
                finally:
                    internal_workers.shutdown_artifact_internal_runtime()
    finally:
        await db_session.dispose_engine()


asyncio.run(seed())
"""
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


def _historical_backend(tmp_path):
    root = Path(__file__).resolve().parents[4]
    archived = subprocess.run(
        ["git", "archive", "--format=tar", HISTORICAL_WRITER, "backend"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    source = tmp_path / "historical"
    with tarfile.open(fileobj=io.BytesIO(archived.stdout), mode="r:") as archive:
        archive.extractall(source, filter="data")
    return source / "backend"


def _seed_with_historical_writer(tmp_path, database_url):
    backend = _historical_backend(tmp_path)
    result_path = tmp_path / "historical-seed.json"
    subprocess.run(
        [sys.executable, "-c", HISTORICAL_SEED, str(tmp_path), str(result_path)],
        cwd=backend,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(backend), str(backend / "tests"))),
            "WS_MIGRATION_DATABASE_URL": database_url,
        },
        check=True,
    )
    return json.loads(result_path.read_text())


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


async def _predecessor_evidence(connection, submission_id):
    """Verify the actual old writer's complete source before comparing its upgrade."""
    assert await connection.fetchval("SELECT version_num FROM public.alembic_version") == PREDECESSOR
    assert await connection.fetchval(
        "SELECT to_regclass('public.checker_retry_receipts') IS NULL"
    ) is True
    before = await _retained_rows(connection)
    assert all(before[table] for table in (
        "submissions", "submission_dispatches", "checker_runs",
        "checker_submission_fences", "audit_events", "outbox_events",
        "pre_submit_evidence_sets", "submission_bundle_admissions", "artifact_bindings",
    ))
    assert await connection.fetchval("""
        SELECT count(*) FROM public.audit_events
        WHERE action_id='checker.post_submit.finalize'
    """) == 1
    source = await _source_custody(connection, submission_id)
    assert source["status"] == "infrastructure_failed"
    assert source["failure_code"] == "material_unavailable"
    assert source["result_digest"].startswith("sha256:")
    assert all(source[key] is True for key in (
        "finalized", "finalize_authority_valid", "finalize_allowed",
        "no_completion_event", "current_run", "dispatch_valid", "binding_valid",
        "creation_authority_valid", "binding_authority_valid",
    ))
    return before, source


async def test_retry_upgrade_preserves_evidence_and_installs_closure(
    tmp_path,
    isolated_database_env,
    migration_lock,
):
    with migration_lock():
        await _reset_to_predecessor(isolated_database_env)
        seed = await asyncio.to_thread(
            _seed_with_historical_writer, tmp_path, isolated_database_env
        )
        submission_id = UUID(seed["submission_id"])
        request = PostSubmissionEvaluationRequest.model_validate_json(
            json.dumps(seed["request"])
        )
        assert request.submission_id == submission_id
        connection = await _connection(isolated_database_env)
        try:
            before, source = await _predecessor_evidence(connection, submission_id)
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
            assert await _source_custody(connection, submission_id) == source
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
            request,
            evaluation_request_id=new_record_id(),
            evaluation_generation=2,
        )
        with pytest.raises(
            IntegrityError,
            match="terminal checker infrastructure retry requires Operator receipt",
        ):
            async with db_session.get_session_factory().begin() as session:
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
