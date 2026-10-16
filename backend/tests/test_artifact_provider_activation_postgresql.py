"""PostgreSQL proof for immutable AWS artifact activation custody."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts.s3_compatible import aws_s3_namespace_fingerprint
from app.core.config import Settings
from app.interfaces.artifacts import ArtifactProviderLiveProofRequiredError
from app.modules.artifacts.provider_activation import (
    SqlAlchemyArtifactProviderActivationGuard,
    artifact_provider_database_time,
    coordinate_artifact_provider_activation,
    record_artifact_provider_probe_result,
)
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
        artifact_s3_runtime_policy_arn="arn:aws:iam::123456789012:policy/workstream-runtime",
        artifact_s3_readiness_role_arn="arn:aws:iam::123456789012:role/workstream-readiness",
        artifact_s3_readiness_policy_arn="arn:aws:iam::123456789012:policy/workstream-readiness",
        artifact_s3_negative_role_arn="arn:aws:iam::123456789012:role/workstream-negative",
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
            assert principal is not None
            started_at = await artifact_provider_database_time(session)
            ids[probe_type] = await record_artifact_provider_probe_result(
                session,
                settings,
                probe_type=probe_type,  # type: ignore[arg-type]
                namespace_fingerprint=namespace_fingerprint,
                group_nonce=group_nonce,
                expected_principal_arn=principal,
                observed_principal_arn=principal,
                passed=True,
                evidence={"mode": probe_type, "actual_calls": True},
                error_code=None,
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
