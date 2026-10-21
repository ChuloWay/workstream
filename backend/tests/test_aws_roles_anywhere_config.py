"""Focused tests for generated hosted Roles Anywhere configuration."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest

from app.adapters.artifacts.aws_roles_anywhere_proof import (
    ROLES_ANYWHERE_CA_ISSUER_COMMON_NAME,
    ROLES_ANYWHERE_PROFILE_ATTRIBUTE_MAPPINGS,
    ROLES_ANYWHERE_PROFILE_DURATION_SECONDS,
    normalize_roles_anywhere_profile,
    normalize_roles_anywhere_trust_anchor,
)
from app.adapters.artifacts.aws_live_proof import (
    _validate_bucket_policy,
    _validate_readiness_policy,
    _validate_runtime_policy,
)
from app.core.hashing import canonical_json_hash
from scripts.aws_roles_anywhere_config import (
    ConfigurationGenerationError,
    _load_json,
    _write_outputs,
    generate_bootstrap_templates,
    generate_configuration,
)


_ACCOUNT = "123456789012"
_REGION = "us-east-1"
_ANCHOR = (
    f"arn:aws:rolesanywhere:{_REGION}:{_ACCOUNT}:trust-anchor/00000000-0000-0000-0000-000000000001"
)
_PROFILE = (
    f"arn:aws:rolesanywhere:{_REGION}:{_ACCOUNT}:profile/00000000-0000-0000-0000-000000000002"
)
_ROLE_ARNS = {
    name: f"arn:aws:iam::{_ACCOUNT}:role/workstream-{name}"
    for name in ("runtime", "readiness", "negative")
}


def _ca_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, ROLES_ANYWHERE_CA_ISSUER_COMMON_NAME)]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")


@pytest.fixture
def resource_inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    operator: dict[str, object] = {
        "release_id": "sha256:" + "1" * 64,
        "region": _REGION,
        "bucket": "workstream-artifacts-prod",
        "private_prefix": "workstream/artifacts",
        "trust_anchor_arn": _ANCHOR,
        "profile_arn": _PROFILE,
        "roles": {
            "runtime": {
                "role_arn": _ROLE_ARNS["runtime"],
                "policy_arn": f"arn:aws:iam::{_ACCOUNT}:policy/workstream-runtime",
                "certificate_host_file": "/etc/workstream/roles-anywhere/runtime.pem",
                "private_key_host_file": "/etc/workstream/roles-anywhere/runtime-key.pem",
            },
            "readiness": {
                "role_arn": _ROLE_ARNS["readiness"],
                "policy_arn": f"arn:aws:iam::{_ACCOUNT}:policy/workstream-readiness",
                "certificate_host_file": "/etc/workstream/roles-anywhere/readiness.pem",
                "private_key_host_file": "/etc/workstream/roles-anywhere/readiness-key.pem",
            },
            "negative": {
                "role_arn": _ROLE_ARNS["negative"],
                "certificate_host_file": "/etc/workstream/roles-anywhere/negative.pem",
                "private_key_host_file": "/etc/workstream/roles-anywhere/negative-key.pem",
            },
        },
        "bootstrap_principal_arn": f"arn:aws:iam::{_ACCOUNT}:role/workstream-bootstrap",
    }
    anchor: dict[str, object] = {
        "trustAnchor": {
            "trustAnchorArn": _ANCHOR,
            "enabled": True,
            "source": {
                "sourceType": "CERTIFICATE_BUNDLE",
                "sourceData": {"x509CertificateData": _ca_pem()},
            },
        }
    }
    profile: dict[str, object] = {
        "profile": {
            "profileArn": _PROFILE,
            "enabled": True,
            "roleArns": list(reversed(tuple(_ROLE_ARNS.values()))),
            "durationSeconds": ROLES_ANYWHERE_PROFILE_DURATION_SECONDS,
            "managedPolicyArns": [],
            "inlinePolicy": None,
            "sessionPolicy": None,
            "attributeMappings": deepcopy(list(ROLES_ANYWHERE_PROFILE_ATTRIBUTE_MAPPINGS)),
            "acceptRoleSessionName": False,
            "requireInstanceProperties": False,
        }
    }
    return operator, anchor, profile


def test_generation_reuses_canonical_resource_digests_and_closes_trust(
    resource_inputs: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    operator, anchor, profile = resource_inputs
    environment, templates = generate_configuration(operator, anchor, profile)
    _, expected_anchor = normalize_roles_anywhere_trust_anchor(
        anchor,
        expected_arn=_ANCHOR,
        expected_issuer_common_name=ROLES_ANYWHERE_CA_ISSUER_COMMON_NAME,
    )
    _, expected_profile = normalize_roles_anywhere_profile(
        profile,
        expected_arn=_PROFILE,
        expected_role_arns=_ROLE_ARNS.values(),
        expected_duration_seconds=ROLES_ANYWHERE_PROFILE_DURATION_SECONDS,
    )
    assert (
        environment["WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_TRUST_ANCHOR_SHA256"] == expected_anchor
    )
    assert environment["WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_PROFILE_SHA256"] == expected_profile
    assert environment["WORKSTREAM_ARTIFACT_S3_AWS_WORKLOAD_IDENTITY_METHOD"] == "roles-anywhere"
    assert "AWS_ACCESS_KEY_ID" not in environment
    policies = templates["role_trust_policies"]
    assert isinstance(policies, dict)
    assert {
        policy["Statement"][0]["Condition"]["StringEquals"]["aws:PrincipalTag/x509Subject/CN"]
        for policy in policies.values()
    } == {"workstream-runtime", "workstream-readiness", "workstream-negative"}
    permissions = templates["readiness_identity_policy"]["Statement"]
    roles_anywhere_permissions = [
        row for row in permissions if row["Action"].startswith("rolesanywhere:")
    ]
    assert {row["Action"] for row in roles_anywhere_permissions} == {
        "rolesanywhere:GetTrustAnchor",
        "rolesanywhere:GetProfile",
    }
    assert {row["Resource"] for row in roles_anywhere_permissions} == {
        _ANCHOR,
        _PROFILE,
    }
    assert environment["WORKSTREAM_ARTIFACT_S3_BUCKET_POLICY_SHA256"] == (
        canonical_json_hash(templates["bucket_policy"])
    )


def test_bootstrap_templates_do_not_require_a_fabricated_profile(
    resource_inputs: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    operator, _anchor, _profile = resource_inputs
    operator["profile_arn"] = None
    templates = generate_bootstrap_templates(operator)
    assert templates["profile_create_parameters"]["roleArns"] == sorted(_ROLE_ARNS.values())
    assert templates["profile_attribute_mappings"] == list(
        ROLES_ANYWHERE_PROFILE_ATTRIBUTE_MAPPINGS
    )
    permissions = templates["readiness_identity_policy"]["Statement"]
    assert {
        (row["Action"], row["Resource"])
        for row in permissions
        if row["Action"].startswith("rolesanywhere:")
    } == {("rolesanywhere:GetTrustAnchor", _ANCHOR)}
    runtime = templates["runtime_identity_policy"]
    assert {(row["Action"], row["Resource"]) for row in runtime["Statement"]} == {
        (
            "s3:PutObject",
            "arn:aws:s3:::workstream-artifacts-prod/workstream/artifacts/sha256/*",
        ),
        (
            "s3:GetObject",
            "arn:aws:s3:::workstream-artifacts-prod/workstream/artifacts/sha256/*",
        ),
        ("s3:ListBucket", "arn:aws:s3:::workstream-artifacts-prod"),
    }
    assert {row["Sid"] for row in templates["bucket_policy"]["Statement"]} == {
        "DenyInsecureTransport",
        "DenyNonRuntimeObjectData",
        "DenyUnconditionalPut",
    }


def test_final_policy_templates_pass_the_live_proof_validators(
    resource_inputs: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    operator, anchor, profile = resource_inputs
    _environment, templates = generate_configuration(operator, anchor, profile)
    settings = SimpleNamespace(
        artifact_s3_bucket=operator["bucket"],
        artifact_s3_private_prefix=operator["private_prefix"],
        artifact_s3_runtime_role_arn=_ROLE_ARNS["runtime"],
        artifact_s3_readiness_role_arn=_ROLE_ARNS["readiness"],
        artifact_s3_negative_role_arn=_ROLE_ARNS["negative"],
        artifact_s3_runtime_policy_arn=operator["roles"]["runtime"]["policy_arn"],
        artifact_s3_readiness_policy_arn=operator["roles"]["readiness"]["policy_arn"],
        artifact_s3_aws_workload_identity_method="roles-anywhere",
        artifact_s3_roles_anywhere_trust_anchor_arn=_ANCHOR,
        artifact_s3_roles_anywhere_profile_arn=_PROFILE,
    )
    _validate_runtime_policy(templates["runtime_identity_policy"], settings)
    _validate_readiness_policy(templates["readiness_identity_policy"], settings)
    _validate_bucket_policy(templates["bucket_policy"], settings)


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_operator_field",
        "same_certificate_path",
        "foreign_anchor_account",
        "profile_role_substitution",
        "profile_session_policy",
    ],
)
def test_generation_rejects_open_or_substituted_configuration(
    resource_inputs: tuple[dict[str, object], dict[str, object], dict[str, object]],
    mutation: str,
) -> None:
    operator, anchor, profile = deepcopy(resource_inputs)
    if mutation == "extra_operator_field":
        operator["access_key"] = "forbidden"
    elif mutation == "same_certificate_path":
        operator["roles"]["runtime"]["private_key_host_file"] = operator["roles"]["runtime"][
            "certificate_host_file"
        ]
    elif mutation == "foreign_anchor_account":
        operator["trust_anchor_arn"] = _ANCHOR.replace(_ACCOUNT, "999999999999")
    elif mutation == "profile_role_substitution":
        profile["profile"]["roleArns"][0] = f"arn:aws:iam::{_ACCOUNT}:role/unexpected"
    else:
        profile["profile"]["sessionPolicy"] = "{}"
    with pytest.raises(ConfigurationGenerationError):
        generate_configuration(operator, anchor, profile)


def test_outputs_are_new_private_files_without_credential_material(
    tmp_path: Path,
    resource_inputs: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    environment, templates = generate_configuration(*resource_inputs)
    output = tmp_path / "generated"
    _write_outputs(output, environment, templates)
    env_path = output / "roles-anywhere.env"
    policy_path = output / "roles-anywhere-policy-templates.json"
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert policy_path.stat().st_mode & 0o777 == 0o600
    assert (output / "runtime-identity-policy.json").stat().st_mode & 0o777 == 0o600
    assert (output / "readiness-identity-policy.json").stat().st_mode & 0o777 == 0o600
    assert (output / "bucket-policy.json").stat().st_mode & 0o777 == 0o600
    rendered = env_path.read_text() + policy_path.read_text()
    assert "SecretAccessKey" not in rendered
    assert "SessionToken" not in rendered
    assert "PRIVATE KEY-----" not in rendered
    with pytest.raises(ConfigurationGenerationError):
        _write_outputs(output, environment, templates)
    assert json.loads(policy_path.read_text()) == templates


def test_json_loader_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "operator-input"
    os.mkfifo(fifo)
    with pytest.raises(ConfigurationGenerationError, match="bounded file"):
        _load_json(fifo)
