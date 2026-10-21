"""Generate a closed hosted Roles Anywhere configuration from AWS read results."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import stat
import sys
from app.adapters.artifacts.aws_roles_anywhere_proof import (
    ROLES_ANYWHERE_CA_ISSUER_COMMON_NAME,
    ROLES_ANYWHERE_PROFILE_ATTRIBUTE_MAPPINGS,
    ROLES_ANYWHERE_PROFILE_DURATION_SECONDS,
    normalize_roles_anywhere_profile,
    normalize_roles_anywhere_trust_anchor,
    validate_roles_anywhere_trust_policy,
)
from app.core.hashing import canonical_json_hash
from app.core.s3_validation import (
    is_canonical_s3_bucket,
    is_canonical_s3_prefix,
    is_canonical_s3_region,
)
from app.interfaces.artifacts import ArtifactConfigurationError


_MAX_INPUT_BYTES = 1024 * 1024
_ROLE_ARN = re.compile(
    r"arn:(?P<partition>aws(?:-us-gov|-cn)?):iam::(?P<account>[0-9]{12}):role/"
    r"(?P<name>[A-Za-z0-9+=,.@_/-]{1,128})\Z"
)
_ROLES_ANYWHERE_ARN = re.compile(
    r"arn:(?P<partition>aws(?:-us-gov|-cn)?):rolesanywhere:"
    r"(?P<region>[a-z0-9-]+):(?P<account>[0-9]{12}):"
    r"(?P<kind>trust-anchor|profile)/[0-9a-f-]+\Z"
)
_POLICY_ARN = re.compile(
    r"arn:(?P<partition>aws(?:-us-gov|-cn)?):iam::(?P<account>[0-9]{12}):policy/"
    r"[A-Za-z0-9+=,.@_/-]{1,128}\Z"
)
_SHA256_IDENTITY = re.compile(r"sha256:[0-9a-f]{64}\Z")
_INPUT_KEYS = frozenset(
    {
        "release_id",
        "region",
        "bucket",
        "private_prefix",
        "trust_anchor_arn",
        "profile_arn",
        "roles",
        "bootstrap_principal_arn",
    }
)
_ROLE_KEYS = frozenset({"runtime", "readiness", "negative"})


class ConfigurationGenerationError(RuntimeError):
    """Operator input cannot produce the closed hosted configuration."""


def _load_json(path: Path) -> dict[str, object]:
    """Read one small regular JSON object without following a final symlink."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_INPUT_BYTES:
                raise ConfigurationGenerationError("configuration input is not a bounded file")
            content = stream.read(_MAX_INPUT_BYTES + 1)
        value = json.loads(content)
    except ConfigurationGenerationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationGenerationError("configuration input is unavailable or invalid") from exc
    if not isinstance(value, dict):
        raise ConfigurationGenerationError("configuration input must be an object")
    return value


def _closed(value: object, keys: frozenset[str], name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ConfigurationGenerationError(f"{name} must contain the exact supported fields")
    return value


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or "\n" in value
        or "\r" in value
        or "\x00" in value
    ):
        raise ConfigurationGenerationError(f"{name} is invalid")
    return value


def _role_details(value: object, name: str) -> tuple[str, str | None, str, str]:
    required = frozenset(
        {
            "role_arn",
            "certificate_host_file",
            "private_key_host_file",
            *(("policy_arn",) if name != "negative" else ()),
        }
    )
    role = _closed(value, required, f"{name} role")
    arn = _text(role["role_arn"], f"{name} role ARN")
    match = _ROLE_ARN.fullmatch(arn)
    if match is None:
        raise ConfigurationGenerationError(f"{name} role ARN is invalid")
    basename = match.group("name").rsplit("/", 1)[-1]
    if len(basename) > 64:
        raise ConfigurationGenerationError(f"{name} role basename exceeds certificate CN limit")
    policy_arn = None
    if "policy_arn" in role:
        policy_arn = _text(role["policy_arn"], f"{name} policy ARN")
        policy_match = _POLICY_ARN.fullmatch(policy_arn)
        if (
            policy_match is None
            or policy_match.group("partition") != match.group("partition")
            or policy_match.group("account") != match.group("account")
        ):
            raise ConfigurationGenerationError(f"{name} policy ARN scope differs")
    certificate = Path(_text(role["certificate_host_file"], f"{name} certificate path"))
    private_key = Path(_text(role["private_key_host_file"], f"{name} private key path"))
    if not certificate.is_absolute() or not private_key.is_absolute():
        raise ConfigurationGenerationError(f"{name} certificate paths must be absolute")
    if certificate == private_key:
        raise ConfigurationGenerationError(f"{name} certificate paths must be distinct")
    return arn, policy_arn, match.group("partition"), match.group("account")


def _require_distinct_identity_paths(roles: Mapping[str, object]) -> None:
    paths: list[Path] = []
    for name in ("runtime", "readiness", "negative"):
        role = roles[name]
        assert isinstance(role, Mapping)
        paths.extend(
            Path(_text(role[key], f"{name} identity path"))
            for key in ("certificate_host_file", "private_key_host_file")
        )
    if len(set(paths)) != 6:
        raise ConfigurationGenerationError("certificate identity paths must be distinct")


def _trust_policy(
    *, trust_anchor_arn: str, account_id: str, subject_common_name: str
) -> dict[str, object]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "rolesanywhere.amazonaws.com"},
                "Action": ["sts:AssumeRole", "sts:SetSourceIdentity", "sts:TagSession"],
                "Condition": {
                    "StringEquals": {
                        "aws:SourceAccount": account_id,
                        "aws:PrincipalTag/x509Issuer/CN": (ROLES_ANYWHERE_CA_ISSUER_COMMON_NAME),
                        "aws:PrincipalTag/x509Subject/CN": subject_common_name,
                    },
                    "ArnEquals": {"aws:SourceArn": trust_anchor_arn},
                },
            }
        ],
    }


def _artifact_policy_templates(
    *,
    partition: str,
    bucket: str,
    private_prefix: str,
    role_rows: Mapping[str, tuple[str, str | None, str, str]],
    trust_anchor_arn: str,
    profile_arn: str | None,
) -> dict[str, object]:
    """Build the exact policies consumed by the existing live proof."""
    bucket_arn = f"arn:{partition}:s3:::{bucket}"
    object_arn = f"{bucket_arn}/{private_prefix}/sha256/*"
    runtime_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "s3:PutObject", "Resource": object_arn},
            {"Effect": "Allow", "Action": "s3:GetObject", "Resource": object_arn},
            {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": bucket_arn},
        ],
    }
    readiness_pairs = [
        *(
            (action, bucket_arn)
            for action in (
                "s3:GetBucketPolicy",
                "s3:GetBucketPolicyStatus",
                "s3:GetBucketAcl",
                "s3:GetBucketPublicAccessBlock",
                "s3:GetBucketOwnershipControls",
                "s3:GetBucketVersioning",
                "s3:GetLifecycleConfiguration",
                "s3:GetEncryptionConfiguration",
            )
        ),
        *(
            (action, role_rows[name][0])
            for action in (
                "iam:GetRole",
                "iam:ListRolePolicies",
                "iam:ListAttachedRolePolicies",
            )
            for name in ("runtime", "readiness", "negative")
        ),
        *(
            (action, policy_arn)
            for action in ("iam:GetPolicy", "iam:GetPolicyVersion")
            for policy_arn in (role_rows["runtime"][1], role_rows["readiness"][1])
        ),
        *(
            (action, "*")
            for action in (
                "access-analyzer:ValidatePolicy",
                "access-analyzer:CheckAccessNotGranted",
                "access-analyzer:CheckNoPublicAccess",
            )
        ),
        ("rolesanywhere:GetTrustAnchor", trust_anchor_arn),
    ]
    if profile_arn is not None:
        readiness_pairs.append(("rolesanywhere:GetProfile", profile_arn))
    readiness_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": action, "Resource": resource}
            for action, resource in readiness_pairs
        ],
    }
    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "DenyInsecureTransport",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": [bucket_arn, object_arn],
                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
            },
            {
                "Sid": "DenyNonRuntimeObjectData",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": object_arn,
                "Condition": {
                    "ArnNotEquals": {
                        "aws:PrincipalArn": role_rows["runtime"][0],
                    }
                },
            },
            {
                "Sid": "DenyUnconditionalPut",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:PutObject",
                "Resource": object_arn,
                "Condition": {"Null": {"s3:if-none-match": "true"}},
            },
        ],
    }
    return {
        "runtime_identity_policy": runtime_policy,
        "readiness_identity_policy": readiness_policy,
        "bucket_policy": bucket_policy,
    }


def generate_bootstrap_templates(
    operator_input: Mapping[str, object],
) -> dict[str, object]:
    """Generate trust and profile templates before the profile exists."""
    source = _closed(operator_input, _INPUT_KEYS, "operator input")
    roles = _closed(source["roles"], _ROLE_KEYS, "roles")
    _require_distinct_identity_paths(roles)
    role_rows = {
        name: _role_details(roles[name], name) for name in ("runtime", "readiness", "negative")
    }
    role_arns = [row[0] for row in role_rows.values()]
    if len(set(role_arns)) != 3:
        raise ConfigurationGenerationError("workload role ARNs must be distinct")
    scopes = {(row[2], row[3]) for row in role_rows.values()}
    if len(scopes) != 1:
        raise ConfigurationGenerationError("workload roles must share one partition and account")
    partition, account_id = next(iter(scopes))
    region = _text(source["region"], "region")
    bucket = _text(source["bucket"], "bucket")
    private_prefix = _text(source["private_prefix"], "private prefix")
    if not is_canonical_s3_region(region):
        raise ConfigurationGenerationError("region is invalid")
    if not is_canonical_s3_bucket(bucket):
        raise ConfigurationGenerationError("bucket is invalid")
    if not is_canonical_s3_prefix(private_prefix):
        raise ConfigurationGenerationError("private prefix is invalid")
    if source["profile_arn"] is not None:
        raise ConfigurationGenerationError("bootstrap profile ARN must be null")
    bootstrap = _text(source["bootstrap_principal_arn"], "bootstrap principal ARN")
    bootstrap_match = _ROLE_ARN.fullmatch(bootstrap)
    if bootstrap_match is None or (
        bootstrap_match.group("partition"),
        bootstrap_match.group("account"),
    ) != (partition, account_id):
        raise ConfigurationGenerationError("bootstrap principal ARN scope differs")
    release_id = _text(source["release_id"], "release ID")
    if _SHA256_IDENTITY.fullmatch(release_id) is None:
        raise ConfigurationGenerationError("release ID is invalid")
    trust_anchor_arn = _text(source["trust_anchor_arn"], "trust anchor ARN")
    match = _ROLES_ANYWHERE_ARN.fullmatch(trust_anchor_arn)
    if (
        match is None
        or match.group("kind") != "trust-anchor"
        or (match.group("partition"), match.group("account")) != (partition, account_id)
        or match.group("region") != region
    ):
        raise ConfigurationGenerationError("Roles Anywhere trust-anchor ARN scope differs")
    trust_policies: dict[str, dict[str, object]] = {}
    for name, (role_arn, _policy_arn, _partition, _account) in role_rows.items():
        subject = role_arn.rsplit("/", 1)[-1]
        policy = _trust_policy(
            trust_anchor_arn=trust_anchor_arn,
            account_id=account_id,
            subject_common_name=subject,
        )
        validate_roles_anywhere_trust_policy(
            policy,
            trust_anchor_arn=trust_anchor_arn,
            account_id=account_id,
            issuer_common_name=ROLES_ANYWHERE_CA_ISSUER_COMMON_NAME,
            subject_common_name=subject,
        )
        trust_policies[name] = policy
    return {
        "role_trust_policies": trust_policies,
        "profile_create_parameters": {
            "name": "workstream-artifacts",
            "roleArns": sorted(role_arns),
            "durationSeconds": ROLES_ANYWHERE_PROFILE_DURATION_SECONDS,
            "enabled": True,
            "managedPolicyArns": [],
            "acceptRoleSessionName": False,
            "requireInstanceProperties": False,
        },
        "profile_attribute_mappings": deepcopy(list(ROLES_ANYWHERE_PROFILE_ATTRIBUTE_MAPPINGS)),
        **_artifact_policy_templates(
            partition=partition,
            bucket=bucket,
            private_prefix=private_prefix,
            role_rows=role_rows,
            trust_anchor_arn=trust_anchor_arn,
            profile_arn=None,
        ),
    }


def generate_configuration(
    operator_input: Mapping[str, object],
    trust_anchor_response: Mapping[str, object],
    profile_response: Mapping[str, object],
) -> tuple[dict[str, str], dict[str, object]]:
    """Return generated env values and reviewable policy templates."""
    source = _closed(operator_input, _INPUT_KEYS, "operator input")
    roles = _closed(source["roles"], _ROLE_KEYS, "roles")
    _require_distinct_identity_paths(roles)
    role_rows = {
        name: _role_details(roles[name], name) for name in ("runtime", "readiness", "negative")
    }
    role_arns = [row[0] for row in role_rows.values()]
    if len(set(role_arns)) != 3:
        raise ConfigurationGenerationError("workload role ARNs must be distinct")
    scopes = {(row[2], row[3]) for row in role_rows.values()}
    if len(scopes) != 1:
        raise ConfigurationGenerationError("workload roles must share one partition and account")
    partition, account_id = next(iter(scopes))
    region = _text(source["region"], "region")
    trust_anchor_arn = _text(source["trust_anchor_arn"], "trust anchor ARN")
    profile_arn = _text(source["profile_arn"], "profile ARN")
    for arn, kind in ((trust_anchor_arn, "trust-anchor"), (profile_arn, "profile")):
        match = _ROLES_ANYWHERE_ARN.fullmatch(arn)
        if (
            match is None
            or match.group("kind") != kind
            or (match.group("partition"), match.group("account")) != (partition, account_id)
            or match.group("region") != region
        ):
            raise ConfigurationGenerationError(f"Roles Anywhere {kind} ARN scope differs")
    try:
        trust_anchor_security_state, trust_anchor_sha256 = normalize_roles_anywhere_trust_anchor(
            trust_anchor_response,
            expected_arn=trust_anchor_arn,
            expected_issuer_common_name=ROLES_ANYWHERE_CA_ISSUER_COMMON_NAME,
        )
        profile_security_state, profile_sha256 = normalize_roles_anywhere_profile(
            profile_response,
            expected_arn=profile_arn,
            expected_role_arns=role_arns,
            expected_duration_seconds=ROLES_ANYWHERE_PROFILE_DURATION_SECONDS,
        )
    except ArtifactConfigurationError as exc:
        raise ConfigurationGenerationError("AWS Roles Anywhere read result differs") from exc
    bootstrap_input = dict(operator_input)
    bootstrap_input["profile_arn"] = None
    templates = generate_bootstrap_templates(bootstrap_input)
    templates.update(
        _artifact_policy_templates(
            partition=partition,
            bucket=_text(source["bucket"], "bucket"),
            private_prefix=_text(source["private_prefix"], "private prefix"),
            role_rows=role_rows,
            trust_anchor_arn=trust_anchor_arn,
            profile_arn=profile_arn,
        )
    )
    trust_policies = templates["role_trust_policies"]
    assert isinstance(trust_policies, dict)
    runtime = role_rows["runtime"]
    readiness = role_rows["readiness"]
    environment = {
        "WORKSTREAM_RELEASE_ID": _text(source["release_id"], "release ID"),
        "WORKSTREAM_ARTIFACT_S3_REGION": region,
        "WORKSTREAM_ARTIFACT_S3_BUCKET": _text(source["bucket"], "bucket"),
        "WORKSTREAM_ARTIFACT_S3_PRIVATE_PREFIX": _text(source["private_prefix"], "private prefix"),
        "WORKSTREAM_ARTIFACT_S3_AWS_WORKLOAD_IDENTITY_METHOD": "roles-anywhere",
        "WORKSTREAM_ARTIFACT_S3_RUNTIME_ROLE_ARN": runtime[0],
        "WORKSTREAM_ARTIFACT_S3_RUNTIME_TRUST_POLICY_SHA256": canonical_json_hash(
            trust_policies["runtime"]
        ),
        "WORKSTREAM_ARTIFACT_S3_RUNTIME_POLICY_ARN": runtime[1] or "",
        "WORKSTREAM_ARTIFACT_S3_READINESS_ROLE_ARN": readiness[0],
        "WORKSTREAM_ARTIFACT_S3_READINESS_TRUST_POLICY_SHA256": canonical_json_hash(
            trust_policies["readiness"]
        ),
        "WORKSTREAM_ARTIFACT_S3_READINESS_POLICY_ARN": readiness[1] or "",
        "WORKSTREAM_ARTIFACT_S3_NEGATIVE_ROLE_ARN": role_rows["negative"][0],
        "WORKSTREAM_ARTIFACT_S3_NEGATIVE_TRUST_POLICY_SHA256": canonical_json_hash(
            trust_policies["negative"]
        ),
        "WORKSTREAM_ARTIFACT_S3_BOOTSTRAP_PRINCIPAL_ARN": _text(
            source["bootstrap_principal_arn"], "bootstrap principal ARN"
        ),
        "WORKSTREAM_ARTIFACT_S3_BUCKET_POLICY_SHA256": canonical_json_hash(
            templates["bucket_policy"]
        ),
        "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_TRUST_ANCHOR_ARN": trust_anchor_arn,
        "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_TRUST_ANCHOR_SHA256": trust_anchor_sha256,
        "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_PROFILE_ARN": profile_arn,
        "WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_PROFILE_SHA256": profile_sha256,
    }
    for name in ("runtime", "readiness", "negative"):
        role = roles[name]
        assert isinstance(role, Mapping)
        prefix = f"WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_{name.upper()}"
        environment[f"{prefix}_CERTIFICATE_HOST_FILE"] = _text(
            role["certificate_host_file"], f"{name} certificate path"
        )
        environment[f"{prefix}_PRIVATE_KEY_HOST_FILE"] = _text(
            role["private_key_host_file"], f"{name} private key path"
        )
    templates["trust_anchor_security_state"] = trust_anchor_security_state
    templates["profile_security_state"] = profile_security_state
    return environment, templates


def _write_outputs(
    directory: Path, environment: Mapping[str, str], templates: Mapping[str, object]
) -> None:
    try:
        directory.mkdir(mode=0o700)
        env_path = directory / "roles-anywhere.env"
        env_path.write_text(
            "".join(f"{key}={value}\n" for key, value in sorted(environment.items())),
            encoding="utf-8",
        )
        env_path.chmod(0o600)
        _write_template_files(
            directory, templates, bundle_name="roles-anywhere-policy-templates.json"
        )
    except OSError as exc:
        raise ConfigurationGenerationError("configuration output could not be created") from exc


def _write_template_files(
    directory: Path, templates: Mapping[str, object], *, bundle_name: str
) -> None:
    rows = {
        bundle_name: templates,
        "runtime-role-trust-policy.json": templates["role_trust_policies"]["runtime"],
        "readiness-role-trust-policy.json": templates["role_trust_policies"]["readiness"],
        "negative-role-trust-policy.json": templates["role_trust_policies"]["negative"],
        "runtime-identity-policy.json": templates["runtime_identity_policy"],
        "readiness-identity-policy.json": templates["readiness_identity_policy"],
        "bucket-policy.json": templates["bucket_policy"],
        "profile-create-parameters.json": templates["profile_create_parameters"],
    }
    for name, value in rows.items():
        path = directory / name
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)


def _write_bootstrap_templates(directory: Path, templates: Mapping[str, object]) -> None:
    try:
        directory.mkdir(mode=0o700)
        _write_template_files(
            directory,
            templates,
            bundle_name="roles-anywhere-bootstrap-templates.json",
        )
    except OSError as exc:
        raise ConfigurationGenerationError("configuration output could not be created") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--trust-anchor-response", type=Path)
    parser.add_argument("--profile-response", type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--bootstrap-templates", action="store_true")
    args = parser.parse_args()
    try:
        operator_input = _load_json(args.input)
        if args.bootstrap_templates:
            if args.trust_anchor_response is not None or args.profile_response is not None:
                raise ConfigurationGenerationError("bootstrap inputs are invalid")
            _write_bootstrap_templates(
                args.output_directory, generate_bootstrap_templates(operator_input)
            )
            print("Roles Anywhere bootstrap templates generated")
            return 0
        if args.trust_anchor_response is None or args.profile_response is None:
            raise ConfigurationGenerationError("AWS read results are required")
        environment, templates = generate_configuration(
            operator_input,
            _load_json(args.trust_anchor_response),
            _load_json(args.profile_response),
        )
        _write_outputs(args.output_directory, environment, templates)
    except ConfigurationGenerationError:
        print("Roles Anywhere configuration generation failed", file=sys.stderr)
        return 1
    print("Roles Anywhere environment and policy templates generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
