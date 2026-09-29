"""Direct PostgreSQL proofs for exact checker output intent and binding custody."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import runpy
from types import SimpleNamespace
from uuid import UUID

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.models import (
    ArtifactPutAttempt,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.modules.artifacts.service import ArtifactStorageOrchestrator
from projects.unified_policy_fixtures import create_standalone_unified_policy
from tests.artifact_store_helpers import minted_source
from tests.test_artifact_admission import (
    _AllowArtifactAuthority,
    _admit_checker_output,
    _local_store,
    _namespace,
    _seed_checker_output_relationships,
    _settings,
)


async def _store_verified_output(
    *,
    factory,
    settings,
    namespace,
    store,
    policy_bundle,
    source_path: Path,
    payload: bytes,
):
    """Store and independently verify one output using shared test infrastructure."""
    async with factory() as session:
        async with minted_source(source_path, payload, media_type="text/plain") as source:
            project_id, task_id, checker_run_id, admission = await _admit_checker_output(
                session,
                settings,
                namespace,
                source,
                policy_bundle=policy_bundle,
            )
            orchestrator = ArtifactStorageOrchestrator(
                session,
                store,
                namespace,
                settings,
                _AllowArtifactAuthority(),
            )
            await orchestrator.ensure_storage_namespace()
            assert await orchestrator.execute_committed_put(
                attempt_id=admission.attempt_id,
                source=source,
            ) == "stored_pending_verification"
            job_id = await session.scalar(
                select(ArtifactVerificationJob.id).where(
                    ArtifactVerificationJob.originating_put_attempt_id
                    == str(admission.attempt_id)
                )
            )
            assert job_id is not None
            await session.rollback()
            assert await orchestrator.verify_object(UUID(job_id)) == "verified"
            receipt_id = await session.scalar(
                select(ArtifactVerificationReceipt.id).where(
                    ArtifactVerificationReceipt.verification_job_id == job_id,
                    ArtifactVerificationReceipt.outcome == "verified",
                )
            )
            attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
            assert attempt is not None and receipt_id is not None
            assert attempt.replica_id is not None
            logical_role = attempt.logical_role
            content_id = await session.scalar(
                text("select content_id from artifact_replicas where id=:replica_id"),
                {"replica_id": attempt.replica_id},
            )
            assert content_id is not None
            await session.rollback()
            return SimpleNamespace(
                factory=factory,
                project_id=project_id,
                task_id=task_id,
                checker_run_id=checker_run_id,
                put_attempt_id=str(admission.attempt_id),
                verification_receipt_id=receipt_id,
                content_id=str(content_id),
                logical_role=logical_role,
                namespace=namespace,
                policy_bundle=policy_bundle,
            )


@asynccontextmanager
async def _verified_output(database_url: str, tmp_path: Path):
    """Create one real local put and independently verified checker output."""
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bootstrap, store = _local_store(settings, namespace)
    policy_bundle = await create_standalone_unified_policy(factory, namespace)
    try:
        case = await _store_verified_output(
            factory=factory,
            settings=settings,
            namespace=namespace,
            store=store,
            policy_bundle=policy_bundle,
            source_path=tmp_path / "checker-output",
            payload=b"exact checker output",
        )
        case.settings = settings
        case.store = store
        yield case
    finally:
        bootstrap.close()
        await engine.dispose()


def _binding_values(case, **changes):
    values = {
        "id": str(new_record_id()),
        "content_id": case.content_id,
        "project_id": case.project_id,
        "resource_type": "checker_run",
        "resource_id": case.checker_run_id,
        "logical_role": case.logical_role,
        "scope_version": 1,
        "actor_id": ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value,
        "attribution_type": "service_identity",
        "put_attempt_id": case.put_attempt_id,
        "verification_receipt_id": case.verification_receipt_id,
        "supersedes_binding_id": None,
    }
    values.update(changes)
    return values


_INSERT_BINDING = text(
    """insert into artifact_bindings(
       id,content_id,project_id,resource_type,resource_id,logical_role,scope_version,
       actor_id,attribution_type,put_attempt_id,verification_receipt_id,supersedes_binding_id)
       values(:id,:content_id,:project_id,:resource_type,:resource_id,:logical_role,
       :scope_version,:actor_id,:attribution_type,:put_attempt_id,
       :verification_receipt_id,:supersedes_binding_id)"""
)


@pytest.mark.asyncio
async def test_exact_verified_checker_output_binding_and_generic_binding_remain_valid(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    async with _verified_output(isolated_database_env, tmp_path) as case:
        async with case.factory() as session, session.begin():
            await session.execute(_INSERT_BINDING, _binding_values(case))
            await session.execute(
                _INSERT_BINDING,
                _binding_values(
                    case,
                    id=str(new_record_id()),
                    resource_type="task",
                    resource_id=case.task_id,
                    logical_role="diagnostic",
                    actor_id="test-actor",
                    attribution_type="human",
                    put_attempt_id=None,
                    verification_receipt_id=None,
                ),
            )
        async with case.factory() as session:
            assert await session.scalar(
                text(
                    "select count(*) from artifact_bindings "
                    "where resource_type in ('checker_run','task')"
                )
            ) == 2


@pytest.mark.asyncio
async def test_checker_binding_rejects_mixed_or_foreign_ancestry(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    async with _verified_output(isolated_database_env, tmp_path) as case:
        other = await _store_verified_output(
            factory=case.factory,
            settings=case.settings,
            namespace=case.namespace,
            store=case.store,
            policy_bundle=case.policy_bundle,
            source_path=tmp_path / "other-checker-output",
            payload=b"distinct independently verified checker output",
        )
        assert case.put_attempt_id != other.put_attempt_id
        assert case.verification_receipt_id != other.verification_receipt_id
        assert case.content_id != other.content_id
        assert case.namespace.namespace_fingerprint == other.namespace.namespace_fingerprint

        async with case.factory() as session, session.begin():
            control = await session.begin_nested()
            await session.execute(_INSERT_BINDING, _binding_values(case))
            await session.execute(_INSERT_BINDING, _binding_values(other))
            assert await session.scalar(
                text("select count(*) from artifact_bindings where resource_type='checker_run'")
            ) == 2
            await control.rollback()
            assert await session.scalar(
                text("select count(*) from artifact_bindings where resource_type='checker_run'")
            ) == 0

        mixed_lineages = (
            {
                "put_attempt_id": other.put_attempt_id,
                "verification_receipt_id": other.verification_receipt_id,
                "content_id": other.content_id,
            },
            {"put_attempt_id": other.put_attempt_id},
            {"verification_receipt_id": other.verification_receipt_id},
            {"content_id": other.content_id},
        )
        for mixed in mixed_lineages:
            with pytest.raises(
                DBAPIError,
                match="checker output binding verified ancestry mismatch",
            ):
                async with case.factory() as session, session.begin():
                    await session.execute(
                        _INSERT_BINDING,
                        _binding_values(case, **mixed),
                    )
        async with case.factory() as session:
            assert await session.scalar(
                text("select count(*) from artifact_bindings where resource_type='checker_run'")
            ) == 0


@pytest.mark.asyncio
async def test_checker_attempt_static_custody_allows_only_execution_lifecycle(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    async with _verified_output(isolated_database_env, tmp_path) as case:
        for assignment in (
            "checker_request_digest='sha256:' || repeat('b',64)",
            "request_digest='sha256:' || repeat('b',64)",
            "sha256='sha256:' || repeat('b',64)",
            "submission_id='00000000-0000-7000-8000-000000000001'::uuid",
            "logical_role='substituted-slot'",
            "namespace_fingerprint='sha256:' || repeat('b',64)",
        ):
            with pytest.raises(
                DBAPIError,
                match="checker output put attempt custody is immutable",
            ):
                async with case.factory() as session, session.begin():
                    await session.execute(
                        text(
                            f"update artifact_put_attempts set {assignment} where id=:id"
                        ),
                        {"id": case.put_attempt_id},
                    )
        with pytest.raises(
            DBAPIError,
            match="checker output put attempt custody is immutable",
        ):
            async with case.factory() as session, session.begin():
                await session.execute(
                    text("delete from artifact_put_attempts where id=:id"),
                    {"id": case.put_attempt_id},
                )
        with pytest.raises(
            DBAPIError,
            match="checker output put attempt custody is immutable",
        ):
            async with case.factory() as session, session.begin():
                await session.execute(text("truncate artifact_put_attempts cascade"))
        async with case.factory() as session, session.begin():
            await session.execute(
                text(
                    "update artifact_put_attempts set cas_version=cas_version+1, "
                    "updated_at=clock_timestamp() where id=:id"
                ),
                {"id": case.put_attempt_id},
            )


@pytest.mark.asyncio
async def test_binding_guard_uses_only_artifact_ancestry_and_exact_owner_fks(
    isolated_database_env: str,
) -> None:
    engine = create_async_engine(isolated_database_env)
    try:
        async with engine.connect() as connection:
            definition = await connection.scalar(
                text(
                    "select pg_get_functiondef("
                    "'guard_checker_output_binding_insert()'::regprocedure)"
                )
            )
            assert definition is not None
            assert "checker_runs" not in definition
            assert "submissions" not in definition
            assert "workstream_tasks" not in definition
            constraints = dict(
                (await connection.execute(text(
                    "select conname,pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid='artifact_put_attempts'::regclass and conname in "
                    "('fk_artifact_put_attempts_checker_run_ownership',"
                    "'fk_artifact_put_attempts_submission_version',"
                    "'fk_artifact_put_attempts_task_project')"
                ))).all()
            )
            assert set(constraints) == {
                "fk_artifact_put_attempts_checker_run_ownership",
                "fk_artifact_put_attempts_submission_version",
                "fk_artifact_put_attempts_task_project",
            }
            assert "FOREIGN KEY (checker_run_id, task_id, submission_id)" in constraints[
                "fk_artifact_put_attempts_checker_run_ownership"
            ]
            assert "FOREIGN KEY (submission_id, task_id, submission_version)" in constraints[
                "fk_artifact_put_attempts_submission_version"
            ]
            assert "FOREIGN KEY (task_id, project_id)" in constraints[
                "fk_artifact_put_attempts_task_project"
            ]
    finally:
        await engine.dispose()


async def _restore_pre_0007_schema(connection) -> None:
    """Remove only 0007 custody inside the caller's rollback-only transaction."""
    for table, trigger in (
        ("artifact_bindings", "checker_output_binding_insert"),
        ("artifact_put_attempts", "checker_output_put_attempt_custody"),
        ("artifact_put_attempts", "checker_output_put_attempt_no_truncate"),
    ):
        await connection.execute(text(f"drop trigger {trigger} on {table}"))
    for function in (
        "guard_checker_output_binding_insert()",
        "guard_checker_output_put_attempt_custody()",
        "guard_checker_output_put_attempt_truncate()",
    ):
        await connection.execute(text(f"drop function {function}"))
    for constraint in (
        "ck_artifact_bindings_checker_output_lineage",
        "fk_artifact_bindings_checker_put_attempt",
        "fk_artifact_bindings_checker_verification_receipt",
    ):
        await connection.execute(
            text(f"alter table artifact_bindings drop constraint {constraint}")
        )
    for index in (
        "ix_artifact_bindings_put_attempt_id",
        "ix_artifact_bindings_verification_receipt_id",
    ):
        await connection.execute(text(f"drop index {index}"))
    await connection.execute(
        text(
            "alter table artifact_bindings drop column put_attempt_id, "
            "drop column verification_receipt_id"
        )
    )
    for constraint in (
        "fk_artifact_put_attempts_task_project",
        "fk_artifact_put_attempts_checker_run_ownership",
        "fk_artifact_put_attempts_submission_version",
        "ck_artifact_put_attempts_checker_request_digest",
        "ck_artifact_put_attempts_producer_reference",
    ):
        await connection.execute(
            text(f"alter table artifact_put_attempts drop constraint {constraint}")
        )
    await connection.execute(text("drop index ix_artifact_put_attempts_submission_id"))
    await connection.execute(
        text(
            "alter table artifact_put_attempts add constraint "
            "ck_artifact_put_attempts_producer_reference check ("
            "(producer_request_type='guide' and guide_source_item_id is not null "
            "and checker_run_id is null and task_id is null and logical_role is null) or "
            "(producer_request_type='checker_output' and guide_source_item_id is null "
            "and checker_run_id is not null and task_id is not null "
            "and octet_length(logical_role) between 1 and 100) or "
            "(producer_request_type='submission_bundle' and guide_source_item_id is null "
            "and checker_run_id is null and task_id is not null and logical_role is null))"
        )
    )
    await connection.execute(
        text(
            "alter table artifact_put_attempts drop column submission_id, "
            "drop column submission_version, drop column checker_request_digest"
        )
    )


def _run_0007_upgrade(connection) -> None:
    module = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "alembic/versions/0007_checker_output_custody.py"
        )
    )
    with Operations.context(MigrationContext.configure(connection)):
        module["upgrade"]()


@pytest.mark.asyncio
async def test_migration_refuses_unprovable_or_inconsistent_retained_checker_attempts(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    """The old schema lacks evaluation/slot custody, so retained attempts fail closed."""
    async with _verified_output(isolated_database_env, tmp_path / "retained") as case:
        async with case.factory() as seed_session:
            _, other_task_id, _ = await _seed_checker_output_relationships(
                seed_session,
                case.namespace,
                policy_bundle=case.policy_bundle,
            )
        async with case.factory() as session:
            connection = await session.connection()
            await _restore_pre_0007_schema(connection)
            before = await session.scalar(
                text("select to_jsonb(a) from artifact_put_attempts a where id=:id"),
                {"id": case.put_attempt_id},
            )
            with pytest.raises(
                DBAPIError,
                match="retained checker output request custody is unprovable",
            ):
                async with connection.begin_nested():
                    await connection.run_sync(_run_0007_upgrade)
            assert await session.scalar(
                text("select to_jsonb(a) from artifact_put_attempts a where id=:id"),
                {"id": case.put_attempt_id},
            ) == before

            await session.execute(
                text("update artifact_put_attempts set task_id=:task where id=:id"),
                {"id": case.put_attempt_id, "task": other_task_id},
            )
            mismatched = await session.scalar(
                text("select to_jsonb(a) from artifact_put_attempts a where id=:id"),
                {"id": case.put_attempt_id},
            )
            with pytest.raises(
                DBAPIError,
                match="retained checker output attempt ownership is inconsistent",
            ):
                async with connection.begin_nested():
                    await connection.run_sync(_run_0007_upgrade)
            assert await session.scalar(
                text("select to_jsonb(a) from artifact_put_attempts a where id=:id"),
                {"id": case.put_attempt_id},
            ) == mismatched
            await session.rollback()
