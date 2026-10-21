from __future__ import annotations

import asyncio
import datetime
import hashlib
import os
from pathlib import Path
import platform
import shlex
import sys
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest

from app.adapters.artifacts import aws_roles_anywhere, s3_compatible
from app.core.config import Settings
from app.interfaces.artifacts import ArtifactConfigurationError
from tests.assertion_helpers import assert_secret_not_retained
from tests.artifact_store_helpers import artifact_admission_limit_settings


RUNTIME_ROLE_ARN = "arn:aws:iam::123456789012:role/workstream-runtime"
READINESS_ROLE_ARN = "arn:aws:iam::123456789012:role/workstream-readiness"
NEGATIVE_ROLE_ARN = "arn:aws:iam::123456789012:role/workstream-negative"
TRUST_ANCHOR_ARN = (
    "arn:aws:rolesanywhere:us-east-1:123456789012:"
    "trust-anchor/11111111-1111-4111-8111-111111111111"
)
PROFILE_ARN = (
    "arn:aws:rolesanywhere:us-east-1:123456789012:"
    "profile/22222222-2222-4222-8222-222222222222"
)


def write_roles_anywhere_identity(
    tmp_path: Path,
    *,
    role_arn: str = RUNTIME_ROLE_ARN,
    common_name: str | None = None,
    expired: bool = False,
    ca: bool = False,
    key_matches: bool = True,
) -> tuple[Path, Path]:
    """Write one private test leaf identity; never represents live AWS proof."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.UTC)
    certificate_key = ec.generate_private_key(ec.SECP256R1())
    stored_key = certificate_key if key_matches else ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [
            x509.NameAttribute(
                NameOID.COMMON_NAME,
                common_name if common_name is not None else role_arn.rsplit("/", 1)[-1],
            )
        ]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(certificate_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=2))
        .not_valid_after(
            now - datetime.timedelta(days=1)
            if expired
            else now + datetime.timedelta(days=1)
        )
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .sign(certificate_key, hashes.SHA256())
    )
    certificate_path = tmp_path / "roles-anywhere-certificate.pem"
    private_key_path = tmp_path / "roles-anywhere-private-key.pem"
    for path in (certificate_path, private_key_path):
        if path.exists():
            path.chmod(0o600)
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private_key_path.write_bytes(
        stored_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    certificate_path.chmod(0o400)
    private_key_path.chmod(0o400)
    return certificate_path, private_key_path


def make_roles_anywhere_settings(
    tmp_path: Path,
    *,
    selected_role_arn: str = RUNTIME_ROLE_ARN,
    identity_paths: tuple[Path, Path] | None = None,
    **overrides: object,
) -> Settings:
    """Build one complete local test configuration with no AWS access."""
    if identity_paths is None:
        identity_paths = write_roles_anywhere_identity(
            tmp_path,
            role_arn=selected_role_arn,
        )
    certificate_path, private_key_path = identity_paths
    values: dict[str, object] = {
        **artifact_admission_limit_settings(),
        "environment": "production",
        "artifact_store_backend": "s3_compatible",
        "artifact_scratch_root": tmp_path / "scratch",
        "artifact_s3_provider_profile": "aws_s3",
        "artifact_s3_region": "us-east-1",
        "artifact_s3_bucket": "workstream-artifacts-prod",
        "artifact_s3_private_prefix": "workstream/artifacts",
        "artifact_s3_addressing_style": "virtual",
        "artifact_s3_credential_mode": "aws_workload_identity",
        "artifact_s3_aws_workload_identity_method": "roles-anywhere",
        "release_id": "sha256:" + "1" * 64,
        "artifact_s3_runtime_role_arn": RUNTIME_ROLE_ARN,
        "artifact_s3_runtime_trust_policy_sha256": "sha256:" + "2" * 64,
        "artifact_s3_runtime_policy_arn": (
            "arn:aws:iam::123456789012:policy/workstream-runtime"
        ),
        "artifact_s3_readiness_role_arn": READINESS_ROLE_ARN,
        "artifact_s3_readiness_trust_policy_sha256": "sha256:" + "3" * 64,
        "artifact_s3_readiness_policy_arn": (
            "arn:aws:iam::123456789012:policy/workstream-readiness"
        ),
        "artifact_s3_negative_role_arn": NEGATIVE_ROLE_ARN,
        "artifact_s3_negative_trust_policy_sha256": "sha256:" + "4" * 64,
        "artifact_s3_bootstrap_principal_arn": (
            "arn:aws:iam::123456789012:role/workstream-bootstrap"
        ),
        "artifact_s3_bucket_policy_sha256": "sha256:" + "5" * 64,
        "artifact_s3_roles_anywhere_trust_anchor_arn": TRUST_ANCHOR_ARN,
        "artifact_s3_roles_anywhere_trust_anchor_sha256": "sha256:" + "6" * 64,
        "artifact_s3_roles_anywhere_profile_arn": PROFILE_ARN,
        "artifact_s3_roles_anywhere_profile_sha256": "sha256:" + "7" * 64,
        "artifact_s3_roles_anywhere_role_arn": selected_role_arn,
        "artifact_s3_roles_anywhere_certificate_file": certificate_path,
        "artifact_s3_roles_anywhere_private_key_file": private_key_path,
        "artifact_s3_operation_total_timeout_seconds": 300,
        "artifact_complete_read_deadline_seconds": 300,
        "artifact_terminal_persistence_margin_seconds": 120,
    }
    values.update(overrides)
    return Settings(**values)


def install_fake_roles_anywhere_helper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    own_role_arn: str = RUNTIME_ROLE_ARN,
    behavior: str = "isolate",
) -> Path:
    """Install a real local process with deterministic non-network behavior."""
    helper = tmp_path / f"fake-signing-helper-{behavior}"
    pid_path = tmp_path / "fake-signing-helper.pid"
    counter_path = tmp_path / "fake-signing-helper.count"
    if helper.exists():
        helper.chmod(0o700)
    pid_path.unlink(missing_ok=True)
    counter_path.unlink(missing_ok=True)
    if behavior in {"hang", "oversized-stdout", "oversized-stderr"}:
        output = "" if behavior == "oversized-stdout" else " >&2"
        if behavior == "hang":
            action = "exec /usr/bin/sleep 60"
        else:
            chunk = "x" * 4096
            action = (
                "count=0\n"
                "while [ \"$count\" -lt 512 ]; do\n"
                f"    printf '%s' {shlex.quote(chunk)}{output}\n"
                "    count=$((count + 1))\n"
                "done\n"
                "exec /usr/bin/sleep 60"
            )
        source = (
            "#!/bin/sh\n"
            f"printf '%s' \"$$\" > {shlex.quote(str(pid_path))}\n"
            "trap '' TERM\n"
            f"{action}\n"
        )
    else:
        source = f"""#!{sys.executable}
import json
import os
from pathlib import Path
import signal
import sys
import time

behavior = {behavior!r}
own_role = {own_role_arn!r}
pid_path = Path({str(pid_path)!r})
counter_path = Path({str(counter_path)!r})
pid_path.write_text(str(os.getpid()), encoding="ascii")
count = int(counter_path.read_text(encoding="ascii")) + 1 if counter_path.exists() else 1
counter_path.write_text(str(count), encoding="ascii")
args = sys.argv[1:]
role = args[args.index("--role-arn") + 1]
certificate_path = Path(args[args.index("--certificate") + 1])
private_key_path = Path(args[args.index("--private-key") + 1])
certificate_path.read_bytes()
private_key_path.read_bytes()

if behavior == "malformed":
    print('{{"SecretAccessKey":"credential-output-secret"')
elif behavior == "expired":
    print(json.dumps({{
        "Version": 1,
        "AccessKeyId": "ASIA1234567890ABCD",
        "SecretAccessKey": "secret",
        "SessionToken": "token",
        "Expiration": "2020-01-01T00:00:00+00:00",
    }}))
elif behavior == "failure":
    print("2026/10/21 17:56:50 operation error RolesAnywhere: CreateSession, https response error StatusCode: 403, RequestID: request-id, AccessDeniedException: denied", file=sys.stderr)
    raise SystemExit(1)
elif behavior == "generic-failure" or (behavior == "generic-deny" and role != own_role):
    print("request failed", file=sys.stderr)
    raise SystemExit(1)
elif behavior == "incidental-deny" and role != own_role:
    print("2026/10/21 17:56:50 operation error RolesAnywhere: CreateSession, not AccessDeniedException: this is incidental text", file=sys.stderr)
    raise SystemExit(1)
elif behavior == "isolate" and role != own_role:
    print("2026/10/21 17:56:50 operation error RolesAnywhere: CreateSession, https response error StatusCode: 403, RequestID: request-id, AccessDeniedException: denied", file=sys.stderr)
    raise SystemExit(1)
elif behavior == "isolate-no-status" and role != own_role:
    print("2026/10/21 17:56:50 operation error RolesAnywhere: CreateSession, AccessDeniedException: denied", file=sys.stderr)
    raise SystemExit(1)
else:
    print(json.dumps({{
        "Version": 1,
        "AccessKeyId": "ASIA" + str(count).zfill(14),
        "SecretAccessKey": "temporary-secret-" + str(count),
        "SessionToken": "temporary-token-" + str(count),
        "Expiration": "2099-01-01T00:00:00+00:00",
    }}))
"""
    helper.write_text(source, encoding="utf-8")
    helper.chmod(0o500)
    digest = hashlib.sha256(helper.read_bytes()).hexdigest()
    monkeypatch.setattr(aws_roles_anywhere, "_AWS_SIGNING_HELPER_PATH", helper)
    monkeypatch.setattr(
        aws_roles_anywhere,
        "_AWS_SIGNING_HELPER_SHA256_BY_MACHINE",
        {platform.machine(): digest},
    )
    return helper


def test_roles_anywhere_config_requires_complete_selected_exact_resources(
    tmp_path: Path,
) -> None:
    settings = make_roles_anywhere_settings(tmp_path)
    assert settings.artifact_s3_roles_anywhere_role_arn == RUNTIME_ROLE_ARN

    for field in (
        "artifact_s3_roles_anywhere_trust_anchor_arn",
        "artifact_s3_roles_anywhere_trust_anchor_sha256",
        "artifact_s3_roles_anywhere_profile_arn",
        "artifact_s3_roles_anywhere_profile_sha256",
    ):
        with pytest.raises(ValueError, match="shared custody settings must be complete"):
            make_roles_anywhere_settings(tmp_path, **{field: None})

    with pytest.raises(ValueError, match="one configured workload role"):
        make_roles_anywhere_settings(
            tmp_path,
            selected_role_arn="arn:aws:iam::123456789012:role/foreign",
        )
    with pytest.raises(ValueError, match="resource ARN is invalid"):
        make_roles_anywhere_settings(
            tmp_path,
            artifact_s3_roles_anywhere_profile_arn=PROFILE_ARN.upper(),
        )
    with pytest.raises(ValueError, match="partition, region and account"):
        make_roles_anywhere_settings(
            tmp_path,
            artifact_s3_roles_anywhere_profile_arn=PROFILE_ARN.replace(
                "123456789012",
                "999999999999",
            ),
        )
    with pytest.raises(ValueError, match="configured region"):
        make_roles_anywhere_settings(
            tmp_path,
            artifact_s3_roles_anywhere_profile_arn=PROFILE_ARN.replace(
                "us-east-1",
                "us-west-2",
            ),
            artifact_s3_roles_anywhere_trust_anchor_arn=TRUST_ANCHOR_ARN.replace(
                "us-east-1",
                "us-west-2",
            ),
        )


def test_unselected_roles_anywhere_fields_reject() -> None:
    with pytest.raises(ValueError, match="require the Roles Anywhere workload method"):
        Settings(artifact_s3_roles_anywhere_profile_sha256="sha256:" + "1" * 64)


def test_runtime_session_contains_only_roles_anywhere_provider(tmp_path: Path) -> None:
    settings = make_roles_anywhere_settings(tmp_path)
    session = s3_compatible.create_isolated_aws_workload_identity_session(
        settings,
        environ={"HOME": str(tmp_path)},
    )
    providers = session.get_component("credential_provider").providers
    assert len(providers) == 1
    assert type(providers[0]) is aws_roles_anywhere.RolesAnywhereCredentialProvider
    assert providers[0].METHOD == "roles-anywhere"

    readiness_identity = write_roles_anywhere_identity(
        tmp_path / "readiness",
        role_arn=READINESS_ROLE_ARN,
    )
    readiness = make_roles_anywhere_settings(
        tmp_path,
        selected_role_arn=READINESS_ROLE_ARN,
        identity_paths=readiness_identity,
    )
    with pytest.raises(ArtifactConfigurationError, match="must select the runtime role"):
        s3_compatible.create_isolated_aws_workload_identity_session(
            readiness,
            environ={"HOME": str(tmp_path)},
        )


async def test_real_subprocess_supplies_sdk_refreshable_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_fake_roles_anywhere_helper(monkeypatch, tmp_path, behavior="success")
    session = s3_compatible.create_isolated_aws_workload_identity_session(
        make_roles_anywhere_settings(tmp_path),
        environ={"HOME": str(tmp_path)},
    )
    credentials = await s3_compatible.resolve_isolated_aws_workload_credentials(
        session,
        expected_method="roles-anywhere",
    )
    refreshed = await credentials._refresh_using()  # noqa: SLF001
    assert refreshed["access_key"].startswith("ASIA")
    assert (tmp_path / "fake-signing-helper.count").read_text(encoding="ascii") == "2"


@pytest.mark.parametrize("behavior", ["malformed", "expired", "generic-failure"])
async def test_helper_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    behavior: str,
) -> None:
    install_fake_roles_anywhere_helper(monkeypatch, tmp_path, behavior=behavior)
    provider = aws_roles_anywhere.create_roles_anywhere_credential_provider(
        make_roles_anywhere_settings(tmp_path),
        require_runtime_role=True,
    )
    with pytest.raises(
        ArtifactConfigurationError,
        match="Roles Anywhere credentials could not be resolved",
    ) as caught:
        await provider.load()
    assert "credential-output-secret" not in str(caught.value)
    assert caught.value.__cause__ is None
    if behavior == "malformed":
        assert_secret_not_retained(
            caught.value,
            "credential-output-secret",
            traceback_module_prefixes=(
                "app.adapters.artifacts.aws_roles_anywhere",
            ),
        )


async def test_hanging_and_oversized_helpers_are_killed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(aws_roles_anywhere, "_HELPER_TIMEOUT_SECONDS", 1.0)
    for behavior in ("hang", "oversized-stdout", "oversized-stderr"):
        install_fake_roles_anywhere_helper(monkeypatch, tmp_path, behavior=behavior)
        provider = aws_roles_anywhere.create_roles_anywhere_credential_provider(
            make_roles_anywhere_settings(tmp_path),
            require_runtime_role=True,
        )
        async with asyncio.timeout(3.0):
            with pytest.raises(ArtifactConfigurationError):
                await provider.load()
        process_id = int(
            (tmp_path / "fake-signing-helper.pid").read_text(encoding="ascii")
        )
        with pytest.raises(ProcessLookupError):
            os.kill(process_id, 0)


async def test_cancelled_helper_is_killed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_fake_roles_anywhere_helper(monkeypatch, tmp_path, behavior="hang")
    provider = aws_roles_anywhere.create_roles_anywhere_credential_provider(
        make_roles_anywhere_settings(tmp_path),
        require_runtime_role=True,
    )
    task = asyncio.create_task(provider.load())
    pid_path = tmp_path / "fake-signing-helper.pid"
    process_id: int | None = None
    for _ in range(200):
        try:
            process_id = int(pid_path.read_text(encoding="ascii"))
            break
        except (FileNotFoundError, ValueError):
            pass
        await asyncio.sleep(0.01)
    assert process_id is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(ProcessLookupError):
        os.kill(process_id, 0)


@pytest.mark.parametrize(
    ("identity_options", "mode"),
    [
        ({"key_matches": False}, None),
        ({"expired": True}, None),
        ({"ca": True}, None),
        ({"common_name": "workstream-readiness"}, None),
        ({}, 0o440),
    ],
)
async def test_certificate_and_key_custody_rejects_before_helper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    identity_options: dict[str, Any],
    mode: int | None,
) -> None:
    paths = write_roles_anywhere_identity(tmp_path, **identity_options)
    if mode is not None:
        paths[1].chmod(mode)
    install_fake_roles_anywhere_helper(monkeypatch, tmp_path, behavior="success")
    provider = aws_roles_anywhere.create_roles_anywhere_credential_provider(
        make_roles_anywhere_settings(tmp_path, identity_paths=paths),
        require_runtime_role=True,
    )
    with pytest.raises(ArtifactConfigurationError, match="identity is invalid"):
        await provider.load()
    assert not (tmp_path / "fake-signing-helper.pid").exists()


async def test_fifo_identity_rejects_without_blocking_or_invoking_helper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, private_key_path = write_roles_anywhere_identity(tmp_path)
    certificate_path = tmp_path / "certificate-fifo"
    os.mkfifo(certificate_path, mode=0o400)
    install_fake_roles_anywhere_helper(monkeypatch, tmp_path, behavior="success")
    provider = aws_roles_anywhere.create_roles_anywhere_credential_provider(
        make_roles_anywhere_settings(
            tmp_path,
            identity_paths=(certificate_path, private_key_path),
        ),
        require_runtime_role=True,
    )
    async with asyncio.timeout(0.5):
        with pytest.raises(ArtifactConfigurationError, match="identity is invalid"):
            await provider.load()
    assert not (tmp_path / "fake-signing-helper.pid").exists()


async def test_role_isolation_requires_exact_denial_token_bracketed_by_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_fake_roles_anywhere_helper(monkeypatch, tmp_path, behavior="isolate")
    proof = await aws_roles_anywhere.prove_roles_anywhere_role_isolation(
        make_roles_anywhere_settings(tmp_path)
    )
    assert proof == aws_roles_anywhere.RolesAnywhereRoleIsolationProof(True, True, True)
    assert (tmp_path / "fake-signing-helper.count").read_text(encoding="ascii") == "4"

    install_fake_roles_anywhere_helper(monkeypatch, tmp_path, behavior="isolate-no-status")
    assert await aws_roles_anywhere.prove_roles_anywhere_role_isolation(
        make_roles_anywhere_settings(tmp_path)
    ) == aws_roles_anywhere.RolesAnywhereRoleIsolationProof(True, True, True)

    install_fake_roles_anywhere_helper(monkeypatch, tmp_path, behavior="generic-deny")
    with pytest.raises(ArtifactConfigurationError, match="cross-role denial proof failed"):
        await aws_roles_anywhere.prove_roles_anywhere_role_isolation(
            make_roles_anywhere_settings(tmp_path)
        )

    install_fake_roles_anywhere_helper(monkeypatch, tmp_path, behavior="incidental-deny")
    with pytest.raises(ArtifactConfigurationError, match="cross-role denial proof failed"):
        await aws_roles_anywhere.prove_roles_anywhere_role_isolation(
            make_roles_anywhere_settings(tmp_path)
        )
