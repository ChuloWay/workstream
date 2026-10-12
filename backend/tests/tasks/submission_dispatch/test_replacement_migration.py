"""0034 preserves initial custody and refuses uncaused retained replacements."""

import asyncio
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import asyncpg
import pytest
from alembic import command
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from tests.migration_fixtures import _config


pytestmark = pytest.mark.postgres_schema_contract
PREDECESSOR = "0033_contribution_reads"
SUCCESSOR = "0034_checker_replacement"
# The last merged 0032 writer could produce an authorized revision without a
# persisted checker-remediation cause; current runtime deliberately cannot.
HISTORICAL_WRITER = "735cf26591e4ed616bcaa57f12eeb37cee741973"
HISTORICAL_SEED = """
import asyncio
import os
from pathlib import Path
import sys

from app.adapters.tasks import evaluation_completion_handler
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.outbox.api import HandlerOutcome
from app.modules.tasks.api import SubmissionCreationRequest
from tests.post_submit_materialization_helpers import material_fixture
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import revision_archive
from tests.tasks.submission_lineage_support import _verified_admission
from tests.test_default_pre_submit_execution import _bytes


async def seed():
    tmp_path = Path(sys.argv[2])
    database_url = os.environ["WS_MIGRATION_DATABASE_URL"]
    if sys.argv[1] == "initial":
        async with material_fixture(tmp_path, database_url) as h:
            assert h.created.submission_version == 1
    else:
        async with remediation_source(tmp_path, database_url) as h:
            assert await evaluation_completion_handler(sessions=h.factory)(h.envelope) is HandlerOutcome.ACKNOWLEDGE
            changed = revision_archive(h.data)
            preparation = SubmissionBundlePreparationRequest(
                actor=ActorIdentityFacts(
                    h.actor_context.actor_profile_id,
                    h.actor_context.identity_link_id,
                    ActorKind.HUMAN,
                ),
                request_id=new_record_id(), correlation_id=new_record_id(),
                task_id=h.request.task_id, assignment_id=h.request.assignment_id,
                predecessor_submission_id=h.created.submission_id,
                idempotency_key=new_record_id(),
                summary=h.request.structural_input.summary,
                contributor_attestation=h.request.structural_input.worker_attestation,
                media_type="application/zip", byte_source=_bytes(changed),
            )
            admission_id = await _verified_admission(
                h.factory, h.store, h.namespace, h.settings, h.actor_context, preparation,
            )
            async with h.factory() as session:
                created = await compose_hidden_submission_creation_command(
                    session,
                    h.actor_context.model_copy(update={
                        "request_id": new_record_id(), "correlation_id": new_record_id(),
                    }),
                    request_id=new_record_id(), correlation_id=new_record_id(),
                ).create(SubmissionCreationRequest(
                    task_id=h.request.task_id, assignment_id=h.request.assignment_id,
                    contributor_id=h.actor_context.actor_profile_id,
                    predecessor_submission_id=h.created.submission_id,
                    admission_id=admission_id, summary=preparation.summary,
                    contributor_attestation=preparation.contributor_attestation,
                ))
            assert created.submission_version == 2
    await db_session.dispose_engine()


asyncio.run(seed())
"""
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


def _seed_with_historical_writer(tmp_path, database_url, mode):
    backend = _historical_backend(tmp_path)
    subprocess.run(
        [sys.executable, "-c", HISTORICAL_SEED, mode, str(tmp_path)],
        cwd=backend,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(backend), str(backend / "tests"))),
            "WS_MIGRATION_DATABASE_URL": database_url,
        },
        check=True,
    )


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


async def test_upgrade_preserves_real_initial_rows_and_exact_receipts(
    tmp_path,
    isolated_database_env,
    migration_lock,
):
    with migration_lock():
        await _reset_to_predecessor(isolated_database_env)
        await asyncio.to_thread(
            _seed_with_historical_writer, tmp_path, isolated_database_env, "initial"
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
    """A real 0032 writer can retain version two without a persisted source ID."""
    with migration_lock():
        await _reset_to_predecessor(isolated_database_env)
        await asyncio.to_thread(
            _seed_with_historical_writer, tmp_path, isolated_database_env, "revision"
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
