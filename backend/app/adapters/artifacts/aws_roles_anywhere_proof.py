"""Closed Roles Anywhere resource and IAM trust proof helpers."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime, timezone
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import NameOID

from app.core.hashing import canonical_json_hash
from app.interfaces.artifacts import ArtifactConfigurationError


ROLES_ANYWHERE_CA_ISSUER_COMMON_NAME = "Workstream Artifact Root CA"
ROLES_ANYWHERE_PROFILE_DURATION_SECONDS = 3600
ROLES_ANYWHERE_PROFILE_ATTRIBUTE_MAPPINGS: tuple[dict[str, object], ...] = (
    {"certificateField": "x509Issuer", "mappingRules": [{"specifier": "CN"}]},
    {"certificateField": "x509Subject", "mappingRules": [{"specifier": "CN"}]},
)


def normalize_roles_anywhere_trust_anchor(
    response: Mapping[str, object],
    *,
    expected_arn: str,
    expected_issuer_common_name: str,
    observed_at: datetime | None = None,
) -> tuple[dict[str, object], str]:
    """Validate and digest one enabled certificate-bundle trust anchor."""
    anchor = _resource(response, "trustAnchor")
    if anchor.get("trustAnchorArn") != expected_arn or anchor.get("enabled") is not True:
        raise ArtifactConfigurationError("AWS Roles Anywhere trust anchor identity differs")
    source = anchor.get("source")
    if not isinstance(source, Mapping) or set(source) != {"sourceType", "sourceData"}:
        raise ArtifactConfigurationError("AWS Roles Anywhere trust anchor source is not closed")
    source_data = source.get("sourceData")
    if source.get("sourceType") != "CERTIFICATE_BUNDLE" or not isinstance(
        source_data, Mapping
    ) or set(source_data) != {"x509CertificateData"}:
        raise ArtifactConfigurationError("AWS Roles Anywhere trust anchor source is invalid")
    pem = source_data.get("x509CertificateData")
    if not isinstance(pem, str) or not pem.isascii() or len(pem) > 64_000:
        raise ArtifactConfigurationError("AWS Roles Anywhere CA certificate is invalid")
    certificate = _load_ca_certificate(pem)
    issuer_common_name = _one_common_name(certificate.issuer, "issuer")
    subject_common_name = _one_common_name(certificate.subject, "subject")
    if issuer_common_name != expected_issuer_common_name:
        raise ArtifactConfigurationError("AWS Roles Anywhere CA issuer common name differs")
    instant = observed_at or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ArtifactConfigurationError("AWS Roles Anywhere certificate time is invalid")
    instant = instant.astimezone(timezone.utc)
    if not certificate.not_valid_before_utc <= instant <= certificate.not_valid_after_utc:
        raise ArtifactConfigurationError("AWS Roles Anywhere CA certificate is not currently valid")
    normalized: dict[str, object] = {
        "enabled": True,
        "source_type": "CERTIFICATE_BUNDLE",
        "certificate_sha256": "sha256:" + certificate.fingerprint(hashes.SHA256()).hex(),
        "issuer_common_name": issuer_common_name,
        "subject_common_name": subject_common_name,
    }
    return normalized, canonical_json_hash(normalized)


def normalize_roles_anywhere_profile(
    response: Mapping[str, object],
    *,
    expected_arn: str,
    expected_role_arns: Collection[str],
    expected_duration_seconds: int,
) -> tuple[dict[str, object], str]:
    """Validate and digest the one closed shared three-role profile."""
    profile = _resource(response, "profile")
    if profile.get("profileArn") != expected_arn:
        raise ArtifactConfigurationError("AWS Roles Anywhere profile identity differs")
    roles = profile.get("roleArns")
    expected_roles = tuple(sorted(expected_role_arns))
    if (
        len(expected_roles) != 3
        or len(set(expected_roles)) != 3
        or not isinstance(roles, list)
        or any(not isinstance(role, str) for role in roles)
        or tuple(sorted(roles)) != expected_roles
        or len(roles) != 3
    ):
        raise ArtifactConfigurationError("AWS Roles Anywhere profile role set differs")
    mappings = _canonical_attribute_mappings(profile.get("attributeMappings"))
    state: dict[str, object] = {
        "enabled": profile.get("enabled"),
        "roleArns": list(expected_roles),
        "durationSeconds": profile.get("durationSeconds"),
        "managedPolicyArns": profile.get("managedPolicyArns", []),
        "sessionPolicy": profile.get("sessionPolicy") or None,
        "attributeMappings": mappings,
        "acceptRoleSessionName": profile.get("acceptRoleSessionName", False),
        "requireInstanceProperties": profile.get("requireInstanceProperties", False),
    }
    expected: dict[str, object] = {
        "enabled": True,
        "roleArns": list(expected_roles),
        "durationSeconds": expected_duration_seconds,
        "managedPolicyArns": [],
        "sessionPolicy": None,
        "attributeMappings": list(ROLES_ANYWHERE_PROFILE_ATTRIBUTE_MAPPINGS),
        "acceptRoleSessionName": False,
        "requireInstanceProperties": False,
    }
    state["roleArns"] = list(expected_roles)
    if state != expected:
        raise ArtifactConfigurationError("AWS Roles Anywhere profile state is not closed")
    return state, canonical_json_hash(state)


def _canonical_attribute_mappings(value: object) -> list[dict[str, object]]:
    """Require only issuer/subject CN tags and return stable field order."""
    if not isinstance(value, list) or len(value) != 2:
        raise ArtifactConfigurationError("AWS Roles Anywhere profile mappings differ")
    normalized: list[dict[str, object]] = []
    for mapping in value:
        if not isinstance(mapping, Mapping) or set(mapping) != {
            "certificateField",
            "mappingRules",
        }:
            raise ArtifactConfigurationError("AWS Roles Anywhere profile mappings differ")
        field = mapping.get("certificateField")
        rules = mapping.get("mappingRules")
        if (
            field not in {"x509Issuer", "x509Subject"}
            or not isinstance(rules, list)
            or len(rules) != 1
            or not isinstance(rules[0], Mapping)
            or dict(rules[0]) != {"specifier": "CN"}
        ):
            raise ArtifactConfigurationError("AWS Roles Anywhere profile mappings differ")
        normalized.append(
            {"certificateField": field, "mappingRules": [{"specifier": "CN"}]}
        )
    normalized.sort(key=lambda mapping: str(mapping["certificateField"]))
    if [mapping["certificateField"] for mapping in normalized] != [
        "x509Issuer",
        "x509Subject",
    ]:
        raise ArtifactConfigurationError("AWS Roles Anywhere profile mappings differ")
    return normalized


def validate_roles_anywhere_trust_policy(
    policy: Mapping[str, object],
    *,
    trust_anchor_arn: str,
    account_id: str,
    issuer_common_name: str,
    subject_common_name: str,
) -> None:
    """Require one exact role-specific Roles Anywhere trust statement."""
    statements = policy.get("Statement")
    rows = statements if isinstance(statements, list) else [statements]
    if (
        set(policy) != {"Version", "Statement"}
        or policy.get("Version") != "2012-10-17"
        or len(rows) != 1
    ):
        raise ArtifactConfigurationError("AWS Roles Anywhere IAM trust policy is not closed")
    statement = rows[0]
    expected = {
        "Effect": "Allow",
        "Principal": {"Service": "rolesanywhere.amazonaws.com"},
        "Action": [
            "sts:AssumeRole",
            "sts:SetSourceIdentity",
            "sts:TagSession",
        ],
        "Condition": {
            "StringEquals": {
                "aws:SourceAccount": account_id,
                "aws:PrincipalTag/x509Issuer/CN": issuer_common_name,
                "aws:PrincipalTag/x509Subject/CN": subject_common_name,
            },
            "ArnEquals": {"aws:SourceArn": trust_anchor_arn},
        },
    }
    if not isinstance(statement, Mapping) or _canonical_policy_statement(statement) != expected:
        raise ArtifactConfigurationError("AWS Roles Anywhere IAM trust policy differs")


def _resource(response: Mapping[str, object], name: str) -> Mapping[str, object]:
    resource = response.get(name)
    if not isinstance(resource, Mapping):
        raise ArtifactConfigurationError(f"AWS Roles Anywhere {name} response is invalid")
    return resource


def _load_ca_certificate(pem: str) -> x509.Certificate:
    try:
        certificates = x509.load_pem_x509_certificates(pem.encode("ascii"))
        if len(certificates) != 1:
            raise ValueError
        certificate = certificates[0]
        basic = certificate.extensions.get_extension_for_class(x509.BasicConstraints)
        usage = certificate.extensions.get_extension_for_class(x509.KeyUsage)
    except (ValueError, x509.ExtensionNotFound):
        raise ArtifactConfigurationError("AWS Roles Anywhere CA certificate is invalid") from None
    if (
        not basic.critical
        or not basic.value.ca
        or not usage.critical
        or not usage.value.key_cert_sign
        or not usage.value.crl_sign
    ):
        raise ArtifactConfigurationError("AWS Roles Anywhere CA certificate constraints differ")
    return certificate


def _one_common_name(name: x509.Name, kind: str) -> str:
    values = name.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(values) != 1 or not values[0].value or len(values[0].value) > 64:
        raise ArtifactConfigurationError(
            f"AWS Roles Anywhere CA {kind} common name is invalid"
        )
    return values[0].value


def _canonical_policy_statement(statement: Mapping[str, object]) -> dict[str, object]:
    """Normalize action ordering while retaining a closed structural comparison."""
    copied: dict[str, Any] = dict(statement)
    action = copied.get("Action")
    if isinstance(action, str):
        actions = [action]
    elif isinstance(action, list) and all(isinstance(value, str) for value in action):
        actions = sorted(action)
    else:
        return copied
    copied["Action"] = actions
    return copied
