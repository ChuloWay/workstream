"""Shared local-only Flow-HMAC token signer for drills and developer tooling."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
from uuid import uuid4


def base64url_json(payload: dict) -> str:
    """Encode a JSON payload as an unpadded base64url segment."""
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def base64url_bytes(payload: bytes) -> str:
    """Encode bytes as an unpadded base64url segment."""
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode()


def issue_flow_token(
    subject: str,
    roles: list[str],
    *,
    issuer: str,
    audience: str,
    secret: str,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
    not_before: datetime | None = None,
    subject_kind: str = "human",
) -> str:
    """Issue the HMAC token accepted only by Workstream's local Flow verifier."""
    now = issued_at or datetime.now(UTC)
    header = base64url_json({"alg": "HS256", "typ": "JWT"})
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "jti": f"local-e2e-{uuid4()}",
        "subject_kind": subject_kind,
        "scope": "workstream:service" if subject_kind == "service" else "workstream:access",
        "iat": int(now.timestamp()),
        "nbf": int((not_before or (now - timedelta(seconds=5))).timestamp()),
        "exp": int((expires_at or (now + timedelta(minutes=30))).timestamp()),
    }
    if subject_kind == "human":
        claims.update(
            {
                "email": f"{subject}@flow.local",
                "name": subject.replace("-", " ").title(),
                "roles": roles,
            }
        )
    payload = base64url_json(claims)
    signed_content = f"{header}.{payload}".encode()
    signature = hmac.new(secret.encode(), signed_content, hashlib.sha256).digest()
    return f"{header}.{payload}.{base64url_bytes(signature)}"
