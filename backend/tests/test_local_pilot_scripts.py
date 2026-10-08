"""Focused checks for local-pilot provisioning and token helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

import jwt
import pytest

from app.core.config import Settings


bucket_script = importlib.import_module("scripts.ensure_local_minio_bucket")
token_script = importlib.import_module("scripts.issue_local_flow_token")
LOCAL_PILOT_GUIDE = Path(__file__).parents[2] / "docs" / "engineering" / "local-pilot.md"


def _guide_shell_function(name: str) -> str:
    guide = LOCAL_PILOT_GUIDE.read_text(encoding="utf-8")
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$", guide)
    assert match is not None
    return match.group(0)


def _write_fake_curl(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import signal
import sys
import time

arguments = sys.argv[1:]
header_option = arguments.index("--header")
header_reference = arguments[header_option + 1]
assert header_reference.startswith("@")
header_path = Path(header_reference[1:])
header = header_path.read_text(encoding="utf-8")
token = header.removeprefix("Authorization: Bearer ").strip()
report = {
    "arguments": arguments,
    "header": header,
    "header_path": str(header_path),
    "header_mode": oct(header_path.stat().st_mode & 0o777),
    "token_in_arguments": any(token in argument for argument in arguments),
    "token_in_environment": any(token in value for value in os.environ.values()),
}
Path(os.environ["FAKE_CURL_REPORT"]).write_text(json.dumps(report), encoding="utf-8")
if os.environ.get("FAKE_CURL_SIGNAL_PARENT") == "1":
    os.kill(os.getppid(), signal.SIGTERM)
    time.sleep(0.1)
sys.exit(int(os.environ["FAKE_CURL_EXIT"]))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _run_guide_curl_helper(
    tmp_path: Path, *, exit_status: int, signal_parent: bool = False
) -> tuple[subprocess.CompletedProcess[str], dict[str, object], str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_curl(fake_bin / "curl")
    report_path = tmp_path / "curl-report.json"
    token = "synthetic-local-pilot-bearer-token"
    script = f"""{_guide_shell_function("curl_with_token")}
TOKEN='{token}'
curl_with_token "$TOKEN" --fail --silent https://workstream.invalid/example
exit $?
"""
    environment = os.environ.copy()
    environment.update(
        {
            "FAKE_CURL_EXIT": str(exit_status),
            "FAKE_CURL_REPORT": str(report_path),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "TMPDIR": str(tmp_path),
        }
    )
    if signal_parent:
        environment["FAKE_CURL_SIGNAL_PARENT"] = "1"
    completed = subprocess.run(
        ["bash"],
        input=script,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return completed, report, token


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


async def test_bucket_helper_retries_transient_first_connection(monkeypatch) -> None:
    attempts = SimpleNamespace(create=0, sleep=0)

    class Client:
        async def create_bucket(self, **kwargs: str) -> None:
            assert kwargs == {"Bucket": "workstream-local"}
            attempts.create += 1
            if attempts.create == 1:
                raise OSError("MinIO listener is not accepting requests yet")

        async def head_bucket(self, **kwargs: str) -> None:
            assert kwargs == {"Bucket": "workstream-local"}

    class ClientContext:
        async def __aenter__(self) -> Client:
            return Client()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Session:
        def set_credentials(self, access_key: str, secret_key: str) -> None:
            assert (access_key, secret_key) == ("local-key", "local-secret")

        def create_client(self, service: str, **kwargs: object) -> ClientContext:
            assert service == "s3"
            assert kwargs == {
                "endpoint_url": "http://minio:9000",
                "region_name": "us-east-1",
            }
            return ClientContext()

    async def no_wait(_seconds: float) -> None:
        attempts.sleep += 1

    monkeypatch.setattr(bucket_script.asyncio, "sleep", no_wait)
    bucket = await bucket_script.ensure_local_minio_bucket(
        minio_settings(), session_factory=Session
    )

    assert bucket == "workstream-local"
    assert (attempts.create, attempts.sleep) == (2, 1)


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


@pytest.mark.parametrize("exit_status", [0, 23])
def test_runbook_curl_helper_keeps_token_private_and_cleans_header(
    tmp_path: Path, exit_status: int
) -> None:
    completed, report, token = _run_guide_curl_helper(tmp_path, exit_status=exit_status)

    assert completed.returncode == exit_status
    assert report["header"] == f"Authorization: Bearer {token}\n"
    assert report["header_mode"] == "0o600"
    assert report["token_in_arguments"] is False
    assert report["token_in_environment"] is False
    assert not Path(str(report["header_path"])).exists()
    assert token not in completed.stdout
    assert token not in completed.stderr


def test_runbook_curl_helper_cleans_header_when_shell_is_signalled(tmp_path: Path) -> None:
    completed, report, token = _run_guide_curl_helper(
        tmp_path, exit_status=143, signal_parent=True
    )

    assert completed.returncode == 143
    assert report["header"] == f"Authorization: Bearer {token}\n"
    assert not Path(str(report["header_path"])).exists()
    assert token not in completed.stdout
    assert token not in completed.stderr


def test_runbook_routes_authorization_headers_through_private_helper() -> None:
    guide = LOCAL_PILOT_GUIDE.read_text(encoding="utf-8")

    assert guide.count("Authorization: Bearer") == 1
    assert '-H "Authorization: Bearer' not in guide
