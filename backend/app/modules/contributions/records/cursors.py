"""CON-owned signed continuation of one expiring contribution membership export."""

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import re
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.contributions.api.records import ContributionReadRequest, InvalidContributionCursor

MAX_CURSOR_BYTES = 4096
_CURSOR = re.compile(r"^[A-Za-z0-9_-]+$")
_FIELDS = {"v", "q", "export", "at", "expires", "last_at", "last_id"}


@dataclass(frozen=True)
class ContributionCursor:
    """Verified scope and position; current read authority is still mandatory."""

    export_id: UUID
    exported_at: datetime
    expires_at: datetime
    last_recorded_at: datetime
    last_contribution_id: UUID


def contribution_query_digest(request: ContributionReadRequest) -> str:
    """Bind normalized actor, audience, filters, format and page size, excluding position."""
    return canonical_json_hash({
        "domain": "contribution-export-membership-v1",
        "query": request.model_dump(mode="json", exclude={"cursor"}),
    })


def _json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) > MAX_CURSOR_BYTES or not _CURSOR.fullmatch(value):
        raise InvalidContributionCursor("Invalid contribution export cursor")
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _encode(decoded) != value:
        raise InvalidContributionCursor("Invalid contribution export cursor")
    return decoded


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidContributionCursor("Invalid contribution export cursor")
        result[key] = value
    return result


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Export cursor requires aware timestamps")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InvalidContributionCursor("Invalid contribution export cursor")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if _time(parsed) != value:
        raise InvalidContributionCursor("Invalid contribution export cursor")
    return parsed


def _uuid(value: str) -> UUID:
    parsed = UUID(value)
    if str(parsed) != value:
        raise InvalidContributionCursor("Invalid contribution export cursor")
    return parsed


class ContributionCursorCodec:
    """Use the existing configured pagination HMAC secret with a distinct domain."""

    def __init__(self, secret: bytes) -> None:
        if len(secret) != 32:
            raise ValueError("Invalid pagination cursor HMAC secret")
        self._secret = bytes(secret)

    def encode(self, state: ContributionCursor, *, query_digest: str) -> str:
        """Emit canonical bounded signed state; no bearer credential is embedded."""
        payload = {"v": 1, "q": query_digest, "export": str(state.export_id),
                   "at": _time(state.exported_at), "expires": _time(state.expires_at),
                   "last_at": _time(state.last_recorded_at), "last_id": str(state.last_contribution_id)}
        signature = hmac.new(self._secret, _json(payload), hashlib.sha256).digest()
        token = _encode(_json({"p": payload, "s": _encode(signature)}))
        if len(token) > MAX_CURSOR_BYTES:
            raise ValueError("Export cursor exceeds its bound")
        return token

    def decode(self, value: str, *, query_digest: str, now: datetime) -> ContributionCursor:
        """Verify all signed fields before any membership lookup; reject expiry exactly."""
        try:
            envelope = json.loads(_decode(value), object_pairs_hook=_unique)
            if not isinstance(envelope, dict) or set(envelope) != {"p", "s"}:
                raise ValueError()
            payload = envelope["p"]
            if not isinstance(payload, dict) or set(payload) != _FIELDS or type(payload["v"]) is not int or payload["v"] != 1:
                raise ValueError()
            expected = hmac.new(self._secret, _json(payload), hashlib.sha256).digest()
            if not hmac.compare_digest(expected, _decode(envelope["s"])) or not hmac.compare_digest(payload["q"], query_digest):
                raise ValueError()
            state = ContributionCursor(
                export_id=_uuid(payload["export"]), exported_at=_parse_time(payload["at"]),
                expires_at=_parse_time(payload["expires"]), last_recorded_at=_parse_time(payload["last_at"]),
                last_contribution_id=_uuid(payload["last_id"]),
            )
            if not state.exported_at <= now < state.expires_at or (
                state.expires_at - state.exported_at
            ).total_seconds() != 900:
                raise ValueError()
            return state
        except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error, OverflowError):
            raise InvalidContributionCursor("Invalid contribution export cursor") from None
