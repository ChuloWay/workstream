"""PostgreSQL proof for immutable AWS artifact activation custody."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts.s3_compatible import aws_s3_namespace_fingerprint
from app.core.config import Settings
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import ArtifactProviderLiveProofRequiredError
from app.modules.artifacts.provider_activation import (
    SqlAlchemyArtifactProviderActivationGuard,
    artifact_provider_database_time,
    coordinate_artifact_provider_activation,
    record_artifact_provider_probe_result,
)
from app.modules.artifacts.models import ArtifactProviderProbeResult
from tests.artifact_store_helpers import artifact_admission_limit_settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        **artifact_admission_limit_settings(),
        environment="production",
        artifact_store_backend="s3_compatible",
        artifact_scratch_root=tmp_path / "scratch",
        artifact_s3_provider_profile="aws_s3",
        artifact_s3_region="us-east-1",
        artifact_s3_bucket="workstream-artifacts-prod",
        artifact_s3_private_prefix="workstream/artifacts",
        artifact_s3_credential_mode="aws_workload_identity",
        artifact_s3_aws_workload_identity_method="container-role",
        release_id="sha256:" + "1" * 64,
        artifact_s3_runtime_role_arn="arn:aws:iam::123456789012:role/workstream-runtime",
        artifact_s3_runtime_trust_policy_sha256="sha256:" + "3" * 64,
        artifact_s3_runtime_policy_arn="arn:aws:iam::123456789012:policy/workstream-runtime",
        artifact_s3_readiness_role_arn="arn:aws:iam::123456789012:role/workstream-readiness",
        artifact_s3_readiness_trust_policy_sha256="sha256:" + "4" * 64,
        artifact_s3_readiness_policy_arn="arn:aws:iam::123456789012:policy/workstream-readiness",
        artifact_s3_negative_role_arn="arn:aws:iam::123456789012:role/workstream-negative",
        artifact_s3_negative_trust_policy_sha256="sha256:" + "5" * 64,
        artifact_s3_bootstrap_principal_arn="arn:aws:iam::123456789012:role/workstream-bootstrap",
        artifact_s3_bucket_policy_sha256="sha256:" + "2" * 64,
        artifact_s3_operation_total_timeout_seconds=300,
        artifact_complete_read_deadline_seconds=300,
        artifact_terminal_persistence_margin_seconds=120,
    )


async def _insert_group(
    factory,
    settings: Settings,
    namespace_fingerprint: str,
    group_nonce: UUID,
    *,
    omit: str | None = None,
    fail: str | None = None,
    settings_by_type: dict[str, Settings] | None = None,
) -> dict[str, UUID]:
    principals = {
        "readiness": settings.artifact_s3_readiness_role_arn,
        "runtime_immutability": settings.artifact_s3_runtime_role_arn,
        "negative_access": settings.artifact_s3_negative_role_arn,
    }
    ids: dict[str, UUID] = {}
    async with factory() as session, session.begin():
        for probe_type, principal in principals.items():
            if probe_type == omit:
                continue
            row_settings = (settings_by_type or {}).get(probe_type, settings)
            principal = {
                "readiness": row_settings.artifact_s3_readiness_role_arn,
                "runtime_immutability": row_settings.artifact_s3_runtime_role_arn,
                "negative_access": row_settings.artifact_s3_negative_role_arn,
            }[probe_type]
            assert principal is not None
            started_at = await artifact_provider_database_time(session)
            ids[probe_type] = await record_artifact_provider_probe_result(
                session,
                row_settings,
                probe_type=probe_type,  # type: ignore[arg-type]
                namespace_fingerprint=namespace_fingerprint,
                group_nonce=group_nonce,
                expected_principal_arn=principal,
                observed_principal_arn=principal,
                passed=probe_type != fail,
                evidence={"mode": probe_type, "actual_calls": True},
                error_code="access_denied" if probe_type == fail else None,
                started_at=started_at,
            )
    return ids


@pytest.mark.asyncio
async def test_overlapping_exact_groups_activate_and_latest_is_selected_deterministically(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        first_group, second_group = uuid4(), uuid4()
        await _insert_group(factory, settings, namespace, first_group)
        async with factory() as session, session.begin():
            first_id = await coordinate_artifact_provider_activation(
                session,
                settings,
                namespace_fingerprint=namespace,
                group_nonce=first_group,
            )
        await _insert_group(factory, settings, namespace, second_group)
        async with factory() as session, session.begin():
            second_id = await coordinate_artifact_provider_activation(
                session,
                settings,
                namespace_fingerprint=namespace,
                group_nonce=second_group,
            )

        lease = await SqlAlchemyArtifactProviderActivationGuard(
            factory,
            settings,
        ).select_for_call(namespace_fingerprint=namespace)
        assert first_id != second_id
        assert lease.activation_id == second_id
        async with factory() as session:
            predecessor = await session.scalar(
                text(
                    "select supersedes_activation_id from artifact_provider_activations "
                    "where id=:id"
                ),
                {"id": second_id},
            )
        assert str(predecessor) == str(first_id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_activation_guard_uses_real_postgresql_across_two_sync_task_loops(
    isolated_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.adapters.artifacts import internal_workers
    from app.workers.async_runner import run_async_task

    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    group_nonce = uuid4()
    try:
        await _insert_group(factory, settings, namespace, group_nonce)
        async with factory() as session, session.begin():
            activation_id = await coordinate_artifact_provider_activation(
                session,
                settings,
                namespace_fingerprint=namespace,
                group_nonce=group_nonce,
            )
    finally:
        await engine.dispose()

    monkeypatch.setattr(internal_workers, "get_database_url", lambda: isolated_database_env)
    guard = internal_workers._LoopScopedArtifactProviderActivationGuard(settings)

    async def select_in_owned_loop() -> UUID:
        async with internal_workers._artifact_worker_database():
            lease = await guard.select_for_call(namespace_fingerprint=namespace)
            return lease.activation_id

    assert run_async_task(select_in_owned_loop) == activation_id
    assert run_async_task(select_in_owned_loop) == activation_id


@pytest.mark.asyncio
async def test_mixed_or_incomplete_nonce_group_cannot_activate(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_group, second_group = uuid4(), uuid4()
    try:
        await _insert_group(
            factory,
            settings,
            namespace,
            first_group,
            omit="negative_access",
        )
        await _insert_group(
            factory,
            settings,
            namespace,
            second_group,
            omit="readiness",
        )
        with pytest.raises(
            ArtifactProviderLiveProofRequiredError,
            match="incomplete or mixed",
        ):
            async with factory() as session, session.begin():
                await coordinate_artifact_provider_activation(
                    session,
                    settings,
                    namespace_fingerprint=namespace,
                    group_nonce=first_group,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["failed", "binding_drift"])
async def test_failed_or_mixed_binding_group_cannot_activate(
    isolated_database_env: str,
    tmp_path: Path,
    case: str,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    group_nonce = uuid4()
    try:
        if case == "failed":
            await _insert_group(
                factory,
                settings,
                namespace,
                group_nonce,
                fail="negative_access",
            )
        else:
            drifted = settings.model_copy(
                update={"artifact_s3_negative_trust_policy_sha256": "sha256:" + "6" * 64}
            )
            await _insert_group(
                factory,
                settings,
                namespace,
                group_nonce,
                settings_by_type={"negative_access": drifted},
            )
        with pytest.raises(
            ArtifactProviderLiveProofRequiredError,
            match="incomplete or mixed",
        ):
            async with factory() as session, session.begin():
                await coordinate_artifact_provider_activation(
                    session,
                    settings,
                    namespace_fingerprint=namespace,
                    group_nonce=group_nonce,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_expired_direct_probe_group_cannot_activate(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    source_group, expired_group = uuid4(), uuid4()
    try:
        rows = await _insert_group(factory, settings, namespace, source_group)
        async with factory() as session, session.begin():
            for source_id in rows.values():
                await session.execute(
                    text(
                        """
                        INSERT INTO artifact_provider_probe_results (
                          id,probe_type,proof_version,result,release_id,namespace_fingerprint,
                          aws_partition,aws_account_id,region,runtime_role_arn,
                          runtime_trust_policy_sha256,runtime_policy_arn,readiness_role_arn,
                          readiness_trust_policy_sha256,readiness_policy_arn,negative_role_arn,
                          negative_trust_policy_sha256,bootstrap_principal_arn,
                          expected_principal_arn,observed_principal_arn,bucket_policy_sha256,
                          group_nonce,evidence_sha256,error_code,started_at,completed_at,expires_at)
                        SELECT :id,probe_type,proof_version,result,release_id,namespace_fingerprint,
                          aws_partition,aws_account_id,region,runtime_role_arn,
                          runtime_trust_policy_sha256,runtime_policy_arn,readiness_role_arn,
                          readiness_trust_policy_sha256,readiness_policy_arn,negative_role_arn,
                          negative_trust_policy_sha256,bootstrap_principal_arn,
                          expected_principal_arn,observed_principal_arn,bucket_policy_sha256,
                          :group_nonce,evidence_sha256,error_code,
                          clock_timestamp()-interval '16 minutes',
                          clock_timestamp()-interval '15 minutes 30 seconds',
                          clock_timestamp()-interval '1 minute'
                        FROM artifact_provider_probe_results WHERE id=:source_id
                        """
                    ),
                    {
                        "id": str(new_record_id()),
                        "group_nonce": str(expired_group),
                        "source_id": str(source_id),
                    },
                )
        with pytest.raises(
            ArtifactProviderLiveProofRequiredError,
            match="incomplete or mixed",
        ):
            async with factory() as session, session.begin():
                await coordinate_artifact_provider_activation(
                    session,
                    settings,
                    namespace_fingerprint=namespace,
                    group_nonce=expired_group,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_probe_and_activation_rows_reject_mutation_and_deletion(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    group_nonce = uuid4()
    try:
        results = await _insert_group(factory, settings, namespace, group_nonce)
        async with factory() as session, session.begin():
            activation_id = await coordinate_artifact_provider_activation(
                session,
                settings,
                namespace_fingerprint=namespace,
                group_nonce=group_nonce,
            )
        for statement, identifier in (
            (
                "update artifact_provider_probe_results set result='fail' where id=:id",
                results["readiness"],
            ),
            ("delete from artifact_provider_activations where id=:id", activation_id),
        ):
            with pytest.raises(DBAPIError):
                async with factory() as session, session.begin():
                    await session.execute(text(statement), {"id": identifier})
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_probe_recorder_rejects_a_principal_from_another_proof_mode(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            started_at = await artifact_provider_database_time(session)
            with pytest.raises(
                ArtifactProviderLiveProofRequiredError,
                match="does not match its proof mode",
            ):
                await record_artifact_provider_probe_result(
                    session,
                    settings,
                    probe_type="readiness",
                    namespace_fingerprint=namespace,
                    group_nonce=uuid4(),
                    expected_principal_arn=settings.artifact_s3_runtime_role_arn,  # type: ignore[arg-type]
                    observed_principal_arn=settings.artifact_s3_runtime_role_arn,
                    passed=True,
                    evidence={"mode": "readiness", "actual_calls": True},
                    error_code=None,
                    started_at=started_at,
                )
            assert (
                await session.scalar(select(func.count()).select_from(ArtifactProviderProbeResult))
                == 0
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_rejects_direct_probe_insert_with_cross_mode_principal(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    namespace = aws_s3_namespace_fingerprint(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    group_nonce = uuid4()
    try:
        rows = await _insert_group(factory, settings, namespace, group_nonce)
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO artifact_provider_probe_results (
                          id,probe_type,proof_version,result,release_id,namespace_fingerprint,
                          aws_partition,aws_account_id,region,runtime_role_arn,
                          runtime_trust_policy_sha256,runtime_policy_arn,readiness_role_arn,
                          readiness_trust_policy_sha256,readiness_policy_arn,negative_role_arn,
                          negative_trust_policy_sha256,bootstrap_principal_arn,
                          expected_principal_arn,observed_principal_arn,bucket_policy_sha256,
                          group_nonce,evidence_sha256,error_code,started_at,completed_at,expires_at)
                        SELECT :id,probe_type,proof_version,result,release_id,namespace_fingerprint,
                          aws_partition,aws_account_id,region,runtime_role_arn,
                          runtime_trust_policy_sha256,runtime_policy_arn,readiness_role_arn,
                          readiness_trust_policy_sha256,readiness_policy_arn,negative_role_arn,
                          negative_trust_policy_sha256,bootstrap_principal_arn,
                          runtime_role_arn,runtime_role_arn,bucket_policy_sha256,
                          :group_nonce,evidence_sha256,error_code,started_at,completed_at,expires_at
                        FROM artifact_provider_probe_results WHERE id=:source_id
                        """
                    ),
                    {
                        "id": str(new_record_id()),
                        "group_nonce": str(uuid4()),
                        "source_id": str(rows["readiness"]),
                    },
                )
        async with factory() as session, session.begin():
            activation_id = await coordinate_artifact_provider_activation(
                session,
                settings,
                namespace_fingerprint=namespace,
                group_nonce=group_nonce,
            )
        assert type(activation_id) is UUID
    finally:
        await engine.dispose()
