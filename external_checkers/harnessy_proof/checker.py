"""Networkless Harnessy work-proof checker for the local agent loop.

The checker reads one ``external_checker_request.v1`` envelope on stdin and the
verified, read-only Submission material under ``/work/input``. It validates the
claims in ``proof.json`` and writes one ``external_checker_result.v1`` envelope.

Shape mode (empty binding configuration, no facts in the request input): the
checker validates only the shape and values that ``proof.json`` claims. It does
not confirm that the pull request, commit or CI run exist on GitHub. A passing
verdict means "well-formed proof claims", not "independently verified work".

GitHub comparison mode: the binding configuration names
``{"github_repository": "owner/name", "base_branch": "main"}``, and WorkStream
places ``workstream.github_facts.v1`` facts it read from GitHub in the request
input under ``github_facts``. The checker compares every claim with those facts
and reports one error finding per mismatch. Missing or malformed facts when the
configuration requires them are an error finding, never a pass. Facts present
without configuration are still compared, except the configured repository and
base branch. The checker itself never uses the network or a credential.
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
GITHUB_FACTS_INPUT_KEY = "github_facts"
GITHUB_FACTS_SCHEMA = "workstream.github_facts.v1"
_COMMIT_SHA = re.compile(r"[0-9a-fA-F]{40}")
_LOWER_SHA = re.compile(r"[0-9a-f]{40}")
_PULL_PATH = re.compile(
    r"/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9._-]{1,100})/pull/([1-9][0-9]{0,9})"
)
_MAX_CHECK_NAME_CHARACTERS = 200


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


def evaluate_proof(
    raw: bytes | None,
    *,
    configuration: object = None,
    input_value: object = None,
) -> list[dict[str, object]]:
    """Return error findings for one proof document; an empty list passes.

    ``configuration`` is the locked binding configuration and ``input_value`` the
    request input. Together they select shape mode or GitHub comparison mode.
    """
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
    findings.extend(compare_github_facts(proof, configuration, input_value))
    return findings


def _github_configuration(configuration: object) -> tuple[str, str] | None | bool:
    """Return (repository, base branch), None for shape mode, or False if invalid."""
    if not isinstance(configuration, dict) or not configuration:
        return None
    repository = configuration.get("github_repository")
    base_branch = configuration.get("base_branch")
    if (
        set(configuration) != {"github_repository", "base_branch"}
        or not isinstance(repository, str)
        or not isinstance(base_branch, str)
        or not repository
        or not base_branch
    ):
        return False
    return repository, base_branch


def _valid_facts(facts: object) -> bool:
    """Accept only the exact ``workstream.github_facts.v1`` field shape."""
    if not isinstance(facts, dict) or facts.get("schema_version") != GITHUB_FACTS_SCHEMA:
        return False
    checks = facts.get("required_checks")
    merge_sha = facts.get("merge_commit_sha")
    return (
        isinstance(facts.get("repository"), str)
        and type(facts.get("pull_request_number")) is int
        and isinstance(facts.get("merged"), bool)
        and (
            merge_sha is None
            or (isinstance(merge_sha, str) and _LOWER_SHA.fullmatch(merge_sha) is not None)
        )
        and isinstance(facts.get("base_ref"), str)
        and isinstance(facts.get("head_sha"), str)
        and _LOWER_SHA.fullmatch(facts["head_sha"]) is not None
        and isinstance(checks, list)
        and len(checks) > 0
        and all(
            isinstance(check, dict)
            and isinstance(check.get("name"), str)
            and isinstance(check.get("conclusion"), str)
            for check in checks
        )
    )


def _display(value: str) -> str:
    """Bound a GitHub-provided name for a contributor-visible message."""
    printable = "".join(character if character.isprintable() else "?" for character in value)
    if len(printable) > _MAX_CHECK_NAME_CHARACTERS:
        return printable[:_MAX_CHECK_NAME_CHARACTERS] + "..."
    return printable


def compare_github_facts(
    proof: dict, configuration: object, input_value: object
) -> list[dict[str, object]]:
    """Compare proof claims with WorkStream-read GitHub facts; one finding per mismatch."""
    configured = _github_configuration(configuration)
    if configured is False:
        return [
            _finding(
                "github.configuration",
                "The checker configuration must name github_repository and base_branch.",
            )
        ]
    facts = input_value.get(GITHUB_FACTS_INPUT_KEY) if isinstance(input_value, dict) else None
    if facts is None:
        if configured is None:
            return []
        return [
            _finding(
                "github.facts_missing",
                "GitHub facts are required for this check but were not provided.",
            )
        ]
    if not _valid_facts(facts):
        return [_finding("github.facts_invalid", "The provided GitHub facts are malformed.")]
    findings = []
    repository = facts["repository"]
    if configured is not None:
        expected_repository, expected_base = configured
        if repository.casefold() != expected_repository.casefold():
            findings.append(
                _finding(
                    "github.repository",
                    f"The pull request belongs to {_display(repository)}, "
                    f"not {_display(expected_repository)}.",
                )
            )
        if facts["base_ref"] != expected_base:
            findings.append(
                _finding(
                    "github.base_branch",
                    f"The pull request targets {_display(facts['base_ref'])}, "
                    f"not {_display(expected_base)}.",
                )
            )
    pr_url = proof.get("pr_url")
    match = (
        _PULL_PATH.fullmatch(urlsplit(pr_url).path.rstrip("/"))
        if _github_https_url(pr_url)
        else None
    )
    if match is None:
        findings.append(
            _finding(
                "github.pr_url",
                "pr_url must be https://github.com/<owner>/<repository>/pull/<number>.",
            )
        )
    else:
        if f"{match.group(1)}/{match.group(2)}".casefold() != repository.casefold():
            findings.append(
                _finding(
                    "github.pr_repository",
                    "pr_url names a different repository than the GitHub facts.",
                )
            )
        if int(match.group(3)) != facts["pull_request_number"]:
            findings.append(
                _finding(
                    "github.pull_request_number",
                    "pr_url names a different pull request than the GitHub facts.",
                )
            )
    if facts["merged"] is not True:
        findings.append(
            _finding("github.merged", "GitHub reports that the pull request is not merged.")
        )
    commit_sha = proof.get("commit_sha")
    if not isinstance(commit_sha, str) or facts["merge_commit_sha"] != commit_sha.lower():
        findings.append(
            _finding(
                "github.merge_commit_sha",
                "commit_sha does not equal the pull request's merge commit on GitHub.",
            )
        )
    for check in facts["required_checks"]:
        if check["conclusion"] != "success":
            findings.append(
                _finding(
                    "github.required_check",
                    f"Required check {_display(check['name'])} is "
                    f"{_display(check['conclusion'])}, not success, "
                    "for the pull request head commit.",
                )
            )
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
    findings = evaluate_proof(
        read_proof(Path("/work/input")),
        configuration=request.get("configuration"),
        input_value=request.get("input"),
    )
    result = build_result(request, findings)
    sys.stdout.write(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
