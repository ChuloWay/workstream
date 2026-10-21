#!/usr/bin/env python3
"""Provision the local agent-loop service identities through the public API.

Each identity is created by ``POST /api/v1/service-actors`` under the Access
Administrator's own authority. A deterministic Idempotency-Key per identity and
subject makes a rerun an exact replay, and an identity already provisioned
under another key is reported as ``existing``. Tokens are signed locally and
never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from uuid import UUID, uuid5

import httpx

if __package__:
    from .issue_local_flow_token import issue_token
else:
    from issue_local_flow_token import issue_token

# The fixed identities the guide upload, PRE/POST checking, routing to
# FinalAcceptance, assignment reconciliation and ART materialization use.
JOURNEY_SERVICE_IDENTITIES = (
    "workstream.artifact.put_resolver",
    "workstream.artifact.verifier",
    "workstream.artifact.scheduler",
    "workstream.artifact.binding",
    "workstream.artifact.guide_reader",
    "workstream.artifact.materializer",
    "workstream.project.setup",
    "workstream.outbox.dispatcher",
    "workstream.checker.pre_submit",
    "workstream.checker.post_submit",
    "workstream.task.post_submit_router",
    "workstream.task.assignment_reconciler",
)
_KEY_NAMESPACE = UUID("6f1d3c0e-5b7a-4c39-9a51-7f0e2d4b8c11")
_RATE_LIMIT_ATTEMPTS = 3
_MAXIMUM_RETRY_AFTER_SECONDS = 60


def idempotency_key(identity: str, subject: str) -> str:
    """Return the stable request key for one identity/subject pair."""
    return str(uuid5(_KEY_NAMESPACE, f"{identity}\n{subject}"))


def subject_for(identity: str, prefix: str) -> str:
    return f"{prefix}-{identity.removeprefix('workstream.')}"


def classify(status_code: int, body: object) -> str:
    """Map one API response to provisioned, existing or failed."""
    if status_code == 201:  # created now, or the exact replay of an earlier creation
        return "provisioned"
    code = body.get("error", {}).get("code") if isinstance(body, dict) else None
    if status_code == 409 and code == "service_identity_already_provisioned":
        return "existing"
    return f"failed:{status_code}:{code or 'unknown'}"


def _post(client: httpx.Client, token: str, identity: str, subject: str) -> httpx.Response:
    """Send one request; resend the same key after an administrative rate limit."""
    for attempt in range(_RATE_LIMIT_ATTEMPTS):
        response = client.post(
            "/api/v1/service-actors",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": idempotency_key(identity, subject),
            },
            json={
                "service_identity": identity,
                "subject": subject,
                "reason": "Local agent loop service identity",
            },
        )
        if response.status_code != 429 or attempt == _RATE_LIMIT_ATTEMPTS - 1:
            return response
        retry_after = response.headers.get("Retry-After", "")
        delay = int(retry_after) if retry_after.isdigit() else 5
        time.sleep(min(max(delay, 1), _MAXIMUM_RETRY_AFTER_SECONDS))
    raise AssertionError("unreachable")


def provision(
    client: httpx.Client, token: str, identities: tuple[str, ...], prefix: str
) -> dict[str, str]:
    results = {}
    for identity in identities:
        response = _post(client, token, identity, subject_for(identity, prefix))
        try:
            body = response.json()
        except ValueError:
            body = None
        results[identity] = classify(response.status_code, body)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--admin-subject", required=True, help="Flow subject of the Access Administrator"
    )
    parser.add_argument(
        "--api-url", default=os.environ.get("WORKSTREAM_LOCAL_API_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--subject-prefix", default="local-agent-loop")
    parser.add_argument(
        "--identity",
        action="append",
        choices=JOURNEY_SERVICE_IDENTITIES,
        help="Provision only this identity (repeatable)",
    )
    args = parser.parse_args(argv)
    identities = tuple(args.identity or JOURNEY_SERVICE_IDENTITIES)
    try:
        token = issue_token(args.admin_subject, lifetime_seconds=600)
        with httpx.Client(base_url=args.api_url, timeout=30) as client:
            results = provision(client, token, identities, args.subject_prefix)
    except (RuntimeError, ValueError, httpx.HTTPError) as error:
        print(json.dumps({"result_code": "failed", "error_type": type(error).__name__}))
        return 1
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if all(not value.startswith("failed") for value in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
