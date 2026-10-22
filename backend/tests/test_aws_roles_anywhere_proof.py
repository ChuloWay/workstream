"""Focused closed-state proof for AWS Roles Anywhere resources."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest

from app.adapters.artifacts.aws_roles_anywhere_proof import (
    normalize_roles_anywhere_profile,
    normalize_roles_anywhere_trust_anchor,
    validate_roles_anywhere_trust_policy,
)
from app.interfaces.artifacts import ArtifactConfigurationError


_ACCOUNT = "123456789012"
_ANCHOR = (
    f"arn:aws:rolesanywhere:us-east-1:{_ACCOUNT}:trust-anchor/"
    "01234567-89ab-cdef-0123-456789abcdef"
)
_PROFILE = (
    f"arn:aws:rolesanywhere:us-east-1:{_ACCOUNT}:profile/"
    "11234567-89ab-cdef-0123-456789abcdef"
)
_ROLES = tuple(
    f"arn:aws:iam::{_ACCOUNT}:role/workstream-{kind}"
    for kind in ("runtime", "readiness", "negative")
)
_NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def _ca_pem(
    *,
    issuer_common_name: str = "Workstream Artifact Root CA",
    is_ca: bool = True,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_common_name)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before or _NOW - timedelta(days=1))
        .not_valid_after(not_after or _NOW + timedelta(days=365))
        .add_extension(
            x509.BasicConstraints(ca=is_ca, path_length=0 if is_ca else None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=is_ca,
                crl_sign=is_ca,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _anchor(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "trustAnchorArn": _ANCHOR,
        "enabled": True,
        "source": {
            "sourceType": "CERTIFICATE_BUNDLE",
            "sourceData": {"x509CertificateData": _ca_pem()},
        },
    }
    value.update(changes)
    return {"trustAnchor": value}


def _profile(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "profileArn": _PROFILE,
        "enabled": True,
        "roleArns": list(reversed(_ROLES)),
        "durationSeconds": 3600,
        "managedPolicyArns": [],
        "sessionPolicy": None,
        "attributeMappings": [
            {"certificateField": "x509Subject", "mappingRules": [{"specifier": "CN"}]},
            {"certificateField": "x509Issuer", "mappingRules": [{"specifier": "CN"}]},
        ],
        "acceptRoleSessionName": False,
        "requireInstanceProperties": False,
    }
    value.update(changes)
    return {"profile": value}


def test_normalizers_return_stable_closed_state_digests() -> None:
    anchor, anchor_digest = normalize_roles_anywhere_trust_anchor(
        _anchor(),
        expected_arn=_ANCHOR,
        expected_issuer_common_name="Workstream Artifact Root CA",
        observed_at=_NOW,
    )
    profile, profile_digest = normalize_roles_anywhere_profile(
        _profile(),
        expected_arn=_PROFILE,
        expected_role_arns=_ROLES,
        expected_duration_seconds=3600,
    )
    assert anchor == {
        "enabled": True,
        "source_type": "CERTIFICATE_BUNDLE",
        "certificate_sha256": anchor["certificate_sha256"],
        "issuer_common_name": "Workstream Artifact Root CA",
        "subject_common_name": "Workstream Artifact Root CA",
    }
    assert anchor_digest.startswith("sha256:")
    assert profile["roleArns"] == sorted(_ROLES)
    assert profile_digest.startswith("sha256:")


@pytest.mark.parametrize(
    "response,error",
    [
        (_anchor(enabled=False), "identity differs"),
        (_anchor(trustAnchorArn=_ANCHOR.replace("us-east-1", "us-west-2")), "identity differs"),
        (_anchor(source={"sourceType": "AWS_ACM_PCA", "sourceData": {}}), "source is invalid"),
        (
            _anchor(
                source={
                    "sourceType": "CERTIFICATE_BUNDLE",
                    "sourceData": {"x509CertificateData": _ca_pem(is_ca=False)},
                }
            ),
            "constraints differ",
        ),
        (
            _anchor(
                source={
                    "sourceType": "CERTIFICATE_BUNDLE",
                    "sourceData": {
                        "x509CertificateData": _ca_pem(
                            not_before=_NOW - timedelta(days=3),
                            not_after=_NOW - timedelta(days=2),
                        )
                    },
                }
            ),
            "not currently valid",
        ),
    ],
)
def test_trust_anchor_rejects_identity_source_constraints_and_validity(
    response: dict[str, object], error: str
) -> None:
    with pytest.raises(ArtifactConfigurationError, match=error):
        normalize_roles_anywhere_trust_anchor(
            response,
            expected_arn=_ANCHOR,
            expected_issuer_common_name="Workstream Artifact Root CA",
            observed_at=_NOW,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": False},
        {"roleArns": list(_ROLES[:2])},
        {"roleArns": [*_ROLES[:2], _ROLES[0]]},
        {"durationSeconds": 900},
        {"managedPolicyArns": [f"arn:aws:iam::{_ACCOUNT}:policy/extra"]},
        {"sessionPolicy": "{}"},
        {"attributeMappings": []},
        {
            "attributeMappings": [
                {"certificateField": "x509Issuer", "mappingRules": [{"specifier": "CN"}]},
                {"certificateField": "x509SAN", "mappingRules": [{"specifier": "DNS"}]},
            ]
        },
        {"acceptRoleSessionName": True},
        {"requireInstanceProperties": True},
    ],
)
def test_profile_rejects_every_open_security_field(change: dict[str, object]) -> None:
    with pytest.raises(ArtifactConfigurationError):
        normalize_roles_anywhere_profile(
            _profile(**change),
            expected_arn=_PROFILE,
            expected_role_arns=_ROLES,
            expected_duration_seconds=3600,
        )


def test_profile_normalizes_omitted_optional_empty_state() -> None:
    response = _profile()
    profile = response["profile"]
    assert isinstance(profile, dict)
    for field in (
        "managedPolicyArns",
        "sessionPolicy",
        "acceptRoleSessionName",
        "requireInstanceProperties",
    ):
        profile.pop(field)
    normalized, _digest = normalize_roles_anywhere_profile(
        response,
        expected_arn=_PROFILE,
        expected_role_arns=_ROLES,
        expected_duration_seconds=3600,
    )
    assert normalized["managedPolicyArns"] == []
    assert normalized["sessionPolicy"] is None
    assert normalized["acceptRoleSessionName"] is False
    assert normalized["requireInstanceProperties"] is False


def _trust_policy(**statement_changes: Any) -> dict[str, object]:
    statement: dict[str, object] = {
        "Effect": "Allow",
        "Principal": {"Service": "rolesanywhere.amazonaws.com"},
        "Action": ["sts:TagSession", "sts:AssumeRole", "sts:SetSourceIdentity"],
        "Condition": {
            "StringEquals": {
                "aws:SourceAccount": _ACCOUNT,
                "aws:PrincipalTag/x509Issuer/CN": "Workstream Artifact Root CA",
                "aws:PrincipalTag/x509Subject/CN": "workstream-runtime",
            },
            "ArnEquals": {"aws:SourceArn": _ANCHOR},
        },
    }
    statement.update(statement_changes)
    return {"Version": "2012-10-17", "Statement": [statement]}


def test_roles_anywhere_trust_policy_requires_exact_service_actions_and_conditions() -> None:
    validate_roles_anywhere_trust_policy(
        _trust_policy(),
        trust_anchor_arn=_ANCHOR,
        account_id=_ACCOUNT,
        issuer_common_name="Workstream Artifact Root CA",
        subject_common_name="workstream-runtime",
    )
    for mutation in (
        {"Principal": {"Service": "ec2.amazonaws.com"}},
        {"Action": ["sts:AssumeRole"]},
        {"Condition": {}},
        {"Resource": "*"},
    ):
        with pytest.raises(ArtifactConfigurationError, match="trust policy differs"):
            validate_roles_anywhere_trust_policy(
                _trust_policy(**mutation),
                trust_anchor_arn=_ANCHOR,
                account_id=_ACCOUNT,
                issuer_common_name="Workstream Artifact Root CA",
                subject_common_name="workstream-runtime",
            )

    extra_top_level = _trust_policy()
    extra_top_level["Id"] = "unexpected"
    with pytest.raises(ArtifactConfigurationError, match="not closed"):
        validate_roles_anywhere_trust_policy(
            extra_top_level,
            trust_anchor_arn=_ANCHOR,
            account_id=_ACCOUNT,
            issuer_common_name="Workstream Artifact Root CA",
            subject_common_name="workstream-runtime",
        )
