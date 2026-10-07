"""Focused checks for local-pilot provisioning and token helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import importlib

import jwt
import pytest

from app.core.config import Settings


bucket_script = importlib.import_module("scripts.ensure_local_minio_bucket")
token_script = importlib.import_module("scripts.issue_local_flow_token")


def minio_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "local",
        "artifact_store_backend": "s3_compatible",
        "artifact_s3_provider_profile": "minio",
        "artifact_s3_region": "us-east-1",
        "artifact_s3_endpoint_url": "http://minio:9000",
        "artifact_s3_bucket": "workstream-local",
        "artifact_s3_private_prefix": "artifacts",
        "artifact_s3_addressing_style": "path",
        "artifact_s3_credential_mode": "local_static",
        "artifact_s3_access_key_id": "local-key",
        "artifact_s3_secret_access_key": "local-secret",
        "artifact_scratch_root": "/tmp/workstream-local-pilot-tests",
        "artifact_admission_task_maximum_bytes": 67_108_864,
        "artifact_admission_producer_maximum_bytes": 268_435_456,
        "artifact_admission_project_maximum_bytes": 1_073_741_824,
        "artifact_admission_deployment_maximum_bytes": 4_294_967_296,
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("environment", "production"),
        ("artifact_store_backend", "disabled"),
        ("artifact_s3_endpoint_url", "http://127.0.0.1:9000"),
        ("artifact_s3_endpoint_url", "https://minio:9000"),
    ],
)
def test_bucket_helper_rejects_non_compose_or_disabled_targets(field: str, value: str) -> None:
    settings = minio_settings().model_copy(update={field: value})
    with pytest.raises(RuntimeError, match="local MinIO bucket provisioning is not configured"):
        bucket_script._validate_local_minio(settings)


def test_token_helper_issues_distinct_identity_without_authority_claims(monkeypatch) -> None:
    environment = {
        "WORKSTREAM_FLOW_AUTH_ISSUER": "https://flow.local/pilot",
        "WORKSTREAM_FLOW_AUTH_AUDIENCE": "workstream-local-pilot",
        "WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET": "local-test-secret-with-at-least-32-bytes",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    token = token_script.issue_token("pilot-contributor-one", lifetime_seconds=600)
    claims = jwt.decode(
        token,
        environment["WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET"],
        algorithms=["HS256"],
        audience=environment["WORKSTREAM_FLOW_AUTH_AUDIENCE"],
        issuer=environment["WORKSTREAM_FLOW_AUTH_ISSUER"],
    )

    assert claims["sub"] == "pilot-contributor-one"
    assert claims["roles"] == []
    assert claims["scope"] == "workstream:access"
    assert claims["subject_kind"] == "human"
    assert claims["exp"] - claims["iat"] == 600
    assert claims["iat"] <= int(datetime.now(UTC).timestamp())


def test_token_helper_requires_the_shared_local_verifier_secret(monkeypatch) -> None:
    monkeypatch.setenv("WORKSTREAM_FLOW_AUTH_ISSUER", "https://flow.local/pilot")
    monkeypatch.setenv("WORKSTREAM_FLOW_AUTH_AUDIENCE", "workstream-local-pilot")
    monkeypatch.delenv("WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET must be set"):
        token_script.issue_token("pilot-manager", lifetime_seconds=600)
