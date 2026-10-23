"""Canonical AWS Roles Anywhere resource identity validation."""

from __future__ import annotations

import re
from typing import Literal
from uuid import UUID


RolesAnywhereResourceType = Literal["trust-anchor", "profile"]


def iam_principal_scope(value: str | None) -> tuple[str, str] | None:
    """Return the partition and account for one exact IAM principal ARN."""
    if value is None:
        return None
    match = re.fullmatch(
        r"arn:(aws|aws-us-gov|aws-cn):iam::([0-9]{12}):"
        r"(?:root|(?:role|user)/[A-Za-z0-9+=,.@_/-]{1,512})",
        value,
    )
    if match is None:
        return None
    return match.group(1), match.group(2)


def roles_anywhere_resource_scope(
    value: str | None,
    *,
    resource_type: RolesAnywhereResourceType,
) -> tuple[str, str, str] | None:
    """Return the partition, region and account for one canonical resource ARN."""
    if value is None:
        return None
    match = re.fullmatch(
        rf"arn:(aws|aws-us-gov|aws-cn):rolesanywhere:"
        rf"([a-z0-9-]+):([0-9]{{12}}):{resource_type}/"
        rf"([0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-"
        rf"[0-9a-f]{{4}}-[0-9a-f]{{12}})",
        value,
    )
    if match is None:
        return None
    resource_id = match.group(4)
    try:
        canonical_id = str(UUID(resource_id))
    except ValueError:
        return None
    if canonical_id != resource_id:
        return None
    return match.group(1), match.group(2), match.group(3)


def roles_anywhere_region_matches_partition(region: str, partition: str) -> bool:
    """Return whether a Roles Anywhere region belongs to its ARN partition."""
    if partition == "aws-cn":
        return region.startswith("cn-")
    if partition == "aws-us-gov":
        return region.startswith("us-gov-")
    return not region.startswith(("cn-", "us-gov-"))
