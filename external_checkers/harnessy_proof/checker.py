"""Networkless Harnessy work-proof checker for the local agent loop.

The checker reads one ``external_checker_request.v1`` envelope on stdin and the
verified, read-only Submission material under ``/work/input``. It validates the
claims in ``proof.json`` and writes one ``external_checker_result.v1`` envelope.

Trust caveat: the checker runs without network access, so it validates only the
shape and values that ``proof.json`` claims. It does not confirm that the pull
request, commit or CI run exist on GitHub, that the CI run belongs to that
commit, or that the pull request was really merged. A passing verdict means
"well-formed proof claims", not "independently verified work".
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit

PROOF_PATH = "proof.json"
PROOF_SCHEMA = "harnessy.work.proof.v1"
MAX_PROOF_BYTES = 65_536
CHECK_ID = "harnessy.proof"
_COMMIT_SHA = re.compile(r"[0-9a-fA-F]{40}")


def _finding(code: str, message: str, *, level: str = "error") -> dict[str, object]:
    return {
        "check_id": CHECK_ID,
        "code": f"{CHECK_ID}.{code}",
        "level": level,
        "message": message,
        "path": PROOF_PATH,
        "line": None,
    }


def _github_https_url(value: object) -> bool:
    """Accept only an https://github.com/... URL without credentials or port."""
    if not isinstance(value, str):
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme == "https" and parts.netloc == "github.com" and parts.path not in ("", "/")


def evaluate_proof(raw: bytes | None) -> list[dict[str, object]]:
    """Return error findings for one proof document; an empty list passes."""
    if raw is None:
        return [_finding("missing", "The submission must contain proof.json at its root.")]
    if len(raw) > MAX_PROOF_BYTES:
        return [_finding("too_large", "proof.json must be at most 64 KiB.")]
    try:
        proof = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return [_finding("invalid_json", "proof.json must be valid UTF-8 JSON.")]
    if not isinstance(proof, dict):
        return [_finding("invalid_json", "proof.json must contain a JSON object.")]
    findings = []
    if proof.get("schema") != PROOF_SCHEMA:
        findings.append(_finding("schema", f"schema must be {PROOF_SCHEMA!r}."))
    commit_sha = proof.get("commit_sha")
    if not isinstance(commit_sha, str) or _COMMIT_SHA.fullmatch(commit_sha) is None:
        findings.append(_finding("commit_sha", "commit_sha must be 40 hexadecimal characters."))
    for field in ("pr_url", "ci_run_url"):
        if not _github_https_url(proof.get(field)):
            findings.append(_finding(field, f"{field} must be an https://github.com/ URL."))
    if proof.get("ci_conclusion") != "success":
        findings.append(_finding("ci_conclusion", "ci_conclusion must be 'success'."))
    if proof.get("merged") is not True:
        findings.append(_finding("merged", "merged must be the JSON value true."))
    return findings


def read_proof(input_root: Path) -> bytes | None:
    """Read at most one byte past the limit from a regular, non-linked proof file."""
    try:
        descriptor = os.open(input_root / PROOF_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            return None
        return handle.read(MAX_PROOF_BYTES + 1)


def _canonical(value: object) -> str:
    """Match the backend canonical JSON for the string/int/bool/null result body."""
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def build_result(request: dict, findings: list[dict[str, object]]) -> dict[str, object]:
    """Bind a completed verdict to the exact request; failed iff an error exists."""
    has_error = any(item["level"] == "error" for item in findings)
    body = {
        "schema_version": "external_checker_result.v1",
        "request_digest": request["request_digest"],
        "registry_entry_id": request["registry"]["registry_entry_id"],
        "registry_entry_digest": request["registry"]["entry_digest"],
        "phase": request["identity"]["phase"],
        "outcome": "completed",
        "verdict": "failed" if has_error else "passed",
        "findings": findings,
        "infrastructure_failure_code": None,
    }
    digest = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    return {**body, "result_digest": f"sha256:{digest}"}


def main() -> int:
    request = json.load(sys.stdin)
    result = build_result(request, evaluate_proof(read_proof(Path("/work/input"))))
    sys.stdout.write(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
