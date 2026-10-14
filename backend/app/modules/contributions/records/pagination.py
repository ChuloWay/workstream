"""Closed, signed continuation for one CON-owned fixed-membership export."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import re
from typing import Any
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.contributions.api.records import (
    MAX_EXPORT_MEMBERS, ContributionReadRequest, InvalidContributionCursor,
)

_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_CURSOR_BYTES = 512
_ORDER = "recorded_at_uuid_asc"


def contribution_export_query_digest(request: ContributionReadRequest) -> str:
    """Bind caller, scope, canonical filters, format, page size and ordering."""
    request = ContributionReadRequest.model_validate(request)
    selected = request.model_dump(mode="json", exclude={"cursor"})
    return canonical_json_hash({"contribution_export": selected, "order": _ORDER})


@dataclass(frozen=True)
class ContributionCursorPosition:
    snapshot_id: UUID
    next_offset: int
    expires_at: datetime


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    if not value or len(value) > _MAX_CURSOR_BYTES or _BASE64URL.fullmatch(value) is None:
        raise InvalidContributionCursor("invalid contribution cursor")
    result = base64.b64decode((value + "=" * (-len(value) % 4)).encode("ascii"),
                              altchars=b"-_", validate=True)
    if _encode(result) != value:
        raise InvalidContributionCursor("invalid contribution cursor")
    return result


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise InvalidContributionCursor("invalid contribution cursor")
        value[key] = item
    return value


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("cursor expiry must be aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ContributionExportCursorCodec:
    """Canonical HMAC cursor; the stored snapshot and fresh AUTH remain authoritative."""

    def __init__(self, secret: bytes) -> None:
        if len(secret) != 32:
            raise ValueError("invalid contribution cursor secret")
        self._secret = bytes(secret)

    def encode(
        self, *, query_digest: str, snapshot_id: UUID, next_offset: int,
        expires_at: datetime,
    ) -> str:
        if _DIGEST.fullmatch(query_digest) is None or not 1 <= next_offset < MAX_EXPORT_MEMBERS:
            raise ValueError("invalid contribution cursor position")
        payload = {"v": 1, "q": query_digest, "id": str(snapshot_id),
                   "o": next_offset, "e": _timestamp(expires_at)}
        signature = hmac.new(self._secret, _canonical_json(payload), hashlib.sha256).digest()
        return _encode(_canonical_json({"p": payload, "s": _encode(signature)}))

    def decode(self, value: str, *, query_digest: str) -> ContributionCursorPosition:
        """Reject noncanonical/forged tokens before any snapshot lookup."""
        try:
            decoded = _decode(value)
            if len(decoded) > _MAX_CURSOR_BYTES:
                raise InvalidContributionCursor("invalid contribution cursor")
            envelope = json.loads(decoded, object_pairs_hook=_unique_pairs)
            if type(envelope) is not dict or set(envelope) != {"p", "s"}:
                raise InvalidContributionCursor("invalid contribution cursor")
            payload, signature_text = envelope["p"], envelope["s"]
            if type(payload) is not dict or set(payload) != {"v", "q", "id", "o", "e"}:
                raise InvalidContributionCursor("invalid contribution cursor")
            if (type(payload["v"]) is not int or payload["v"] != 1
                    or type(payload["q"]) is not str or _DIGEST.fullmatch(payload["q"]) is None
                    or type(payload["id"]) is not str or type(payload["o"]) is not int
                    or not 1 <= payload["o"] < MAX_EXPORT_MEMBERS
                    or type(payload["e"]) is not str or type(signature_text) is not str):
                raise InvalidContributionCursor("invalid contribution cursor")
            signature = _decode(signature_text)
            if len(signature) != hashlib.sha256().digest_size:
                raise InvalidContributionCursor("invalid contribution cursor")
            expected = hmac.new(self._secret, _canonical_json(payload), hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected) or not hmac.compare_digest(
                payload["q"], query_digest
            ):
                raise InvalidContributionCursor("invalid contribution cursor")
            snapshot_id = UUID(payload["id"])
            if str(snapshot_id) != payload["id"]:
                raise InvalidContributionCursor("invalid contribution cursor")
            expires_at = datetime.strptime(payload["e"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
            if _timestamp(expires_at) != payload["e"]:
                raise InvalidContributionCursor("invalid contribution cursor")
            if _canonical_json(envelope) != decoded:
                raise InvalidContributionCursor("invalid contribution cursor")
            return ContributionCursorPosition(snapshot_id, payload["o"], expires_at)
        except InvalidContributionCursor:
            raise
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError,
                binascii.Error, OverflowError):
            raise InvalidContributionCursor("invalid contribution cursor") from None
