"""Issue one short-lived local Flow-HMAC token without granting authority."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import os
import sys

if __package__:
    from .local_flow_tokens import issue_flow_token
else:
    from local_flow_tokens import issue_flow_token


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value


def issue_token(subject: str, *, lifetime_seconds: int) -> str:
    """Use the existing local Flow signer with no authority-bearing role claims."""
    if not subject or subject != subject.strip() or len(subject.encode("utf-8")) > 500:
        raise ValueError("subject must be a non-empty trimmed value of at most 500 bytes")
    if not 60 <= lifetime_seconds <= 86_400:
        raise ValueError("lifetime must be between 60 and 86400 seconds")
    now = datetime.now(UTC)
    return issue_flow_token(
        subject,
        [],
        issuer=_required_environment("WORKSTREAM_FLOW_AUTH_ISSUER"),
        audience=_required_environment("WORKSTREAM_FLOW_AUTH_AUDIENCE"),
        secret=_required_environment("WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET"),
        issued_at=now,
        expires_at=now + timedelta(seconds=lifetime_seconds),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--lifetime-seconds", type=int, default=3_600)
    args = parser.parse_args(argv)
    try:
        token = issue_token(args.subject, lifetime_seconds=args.lifetime_seconds)
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
