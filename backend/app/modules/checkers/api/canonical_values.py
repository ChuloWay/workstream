"""Canonical bounded scalar values shared by the selected checker flow."""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

Sha256 = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Identifier = Annotated[
    StrictStr, Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.-]*$")
]
VersionNumber = Annotated[StrictInt, Field(ge=1, le=2_147_483_647)]
GuideVersion = Annotated[StrictStr, Field(min_length=1, max_length=50, pattern=r"\S")]
ResourceId = Annotated[UUID, Field(strict=True)]
ByteCount = Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]


class CheckerValue(BaseModel):
    """Reject unknown fields and revalidate previously constructed instances."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


def canonical_checker_bytes(
    value: CheckerValue,
    *,
    exclude: set[str] | None = None,
    include: set[str] | None = None,
) -> bytes:
    """Use the canonical hash encoding for bounded serialized facts."""
    return json.dumps(
        value.model_dump(mode="json", exclude=exclude, include=include),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


__all__ = (
    "ByteCount",
    "CheckerValue",
    "GuideVersion",
    "Identifier",
    "ResourceId",
    "Sha256",
    "VersionNumber",
    "canonical_checker_bytes",
)
