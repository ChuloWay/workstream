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

Integrity rules (owner decision 20) apply whenever facts are compared and fail
closed: every required check must be bound to an App; a change to CI or
repository configuration paths needs explicit human acceptance; the head commit
needs an independent approval (latest decisive review, not the author, not a
bot); and approval only by configured operators adds a non-blocking
``harnessy.operator_approved`` warning.
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


DEFAULT_PROTECTED_PATHS = (".github/**", "**/CODEOWNERS", ".gitlab-ci.yml", ".circleci/**")
DEFAULT_REQUIRED_INDEPENDENT_APPROVALS = 1
OPERATOR_APPROVED_CODE = "harnessy.operator_approved"
_APPROVAL_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED"})
_MAX_LISTED_PATHS = 5
_CONFIGURATION_KEYS = frozenset(
    {
        "github_repository",
        "base_branch",
        "allow_unbound_required_checks",
        "protected_paths",
        "required_independent_approvals",
        "operator_logins",
    }
)


def _strings(value: object) -> bool:
    """Return whether a value is a list of non-empty strings."""
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _github_configuration(configuration: object) -> dict | None | bool:
    """Return the normalized GitHub configuration, None for shape mode, or False.

    Integrity options take safe defaults: unbound required checks are errors,
    the default protected paths apply, and one independent approval is needed.
    """
    if not isinstance(configuration, dict) or not configuration:
        return None
    repository = configuration.get("github_repository")
    base_branch = configuration.get("base_branch")
    allow_unbound = configuration.get("allow_unbound_required_checks", False)
    protected = configuration.get("protected_paths", [])
    approvals = configuration.get(
        "required_independent_approvals", DEFAULT_REQUIRED_INDEPENDENT_APPROVALS
    )
    operators = configuration.get("operator_logins", [])
    if (
        not set(configuration) <= _CONFIGURATION_KEYS
        or not isinstance(repository, str)
        or not isinstance(base_branch, str)
        or not repository
        or not base_branch
        or not isinstance(allow_unbound, bool)
        or not _strings(protected)
        or type(approvals) is not int
        or approvals < 1
        or not _strings(operators)
    ):
        return False
    return {
        "repository": repository,
        "base_branch": base_branch,
        "allow_unbound": allow_unbound,
        "protected_paths": (*DEFAULT_PROTECTED_PATHS, *protected),
        "required_approvals": approvals,
        "operators": frozenset(login.casefold() for login in operators),
    }


def _actor(value: object) -> bool:
    """Return whether a value has the GitHub actor fact shape."""
    return (
        isinstance(value, dict)
        and isinstance(value.get("login"), str)
        and type(value.get("id")) is int
        and isinstance(value.get("type"), str)
    )


def _valid_facts(facts: object) -> bool:
    """Accept only the exact ``workstream.github_facts.v1`` field shape."""
    if not isinstance(facts, dict) or facts.get("schema_version") != GITHUB_FACTS_SCHEMA:
        return False
    checks = facts.get("required_checks")
    merge_sha = facts.get("merge_commit_sha")
    reviews = facts.get("reviews")
    files = facts.get("changed_files")
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
        and _actor(facts.get("author"))
        and isinstance(reviews, list)
        and all(
            isinstance(review, dict)
            and type(review.get("id")) is int
            and (review.get("reviewer") is None or _actor(review.get("reviewer")))
            and isinstance(review.get("state"), str)
            and (review.get("commit_id") is None or isinstance(review.get("commit_id"), str))
            for review in reviews
        )
        and isinstance(files, list)
        and type(facts.get("changed_files_count")) is int
        and facts["changed_files_count"] == len(files)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("filename"), str)
            and (
                item.get("previous_filename") is None
                or isinstance(item.get("previous_filename"), str)
            )
            for item in files
        )
        and isinstance(checks, list)
        and len(checks) > 0
        and all(
            isinstance(check, dict)
            and isinstance(check.get("name"), str)
            and isinstance(check.get("conclusion"), str)
            and isinstance(check.get("app_bound"), bool)
            for check in checks
        )
    )


def _display(value: str) -> str:
    """Bound a GitHub-provided name for a contributor-visible message."""
    printable = "".join(character if character.isprintable() else "?" for character in value)
    if len(printable) > _MAX_CHECK_NAME_CHARACTERS:
        return printable[:_MAX_CHECK_NAME_CHARACTERS] + "..."
    return printable


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a path glob: ``**`` spans directories, ``*`` and ``?`` do not.

    A leading ``**/`` also matches at the repository root.
    """
    parts = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(parts))


def protected_changes(files: list[dict], patterns: tuple[str, ...]) -> list[str]:
    """Return changed paths, including rename sources, that match a protected glob."""
    compiled = [_glob_regex(pattern) for pattern in patterns]
    matched = []
    for item in files:
        for path in (item.get("previous_filename"), item["filename"]):
            if path and any(regex.fullmatch(path) for regex in compiled):
                matched.append(path)
    return sorted(set(matched))


def qualifying_approvals(facts: dict) -> list[str]:
    """Return logins whose latest decisive review approves the head commit.

    Each reviewer's latest ``APPROVED``, ``CHANGES_REQUESTED`` or ``DISMISSED``
    review (by review id) decides; comments do not. The approval must name the
    head SHA and come from a ``User`` who is not the pull request author.
    """
    author = facts["author"]
    latest: dict[int, dict] = {}
    for review in facts["reviews"]:
        reviewer = review["reviewer"]
        if reviewer is None or review["state"] not in _APPROVAL_STATES:
            continue
        current = latest.get(reviewer["id"])
        if current is None or review["id"] > current["id"]:
            latest[reviewer["id"]] = review
    logins = []
    for review in latest.values():
        reviewer = review["reviewer"]
        if (
            review["state"] == "APPROVED"
            and review["commit_id"] == facts["head_sha"]
            and reviewer["type"] == "User"
            and reviewer["id"] != author["id"]
            and reviewer["login"].casefold() != author["login"].casefold()
        ):
            logins.append(reviewer["login"])
    return sorted(logins)


def _integrity_findings(facts: dict, configured: dict | None) -> list[dict[str, object]]:
    """Integrity rules that apply whenever GitHub facts are compared."""
    settings = configured or {
        "allow_unbound": False,
        "protected_paths": DEFAULT_PROTECTED_PATHS,
        "required_approvals": DEFAULT_REQUIRED_INDEPENDENT_APPROVALS,
        "operators": frozenset(),
    }
    findings = []
    if not settings["allow_unbound"]:
        for check in facts["required_checks"]:
            if not check["app_bound"]:
                findings.append(
                    _finding(
                        "github.unbound_required_check",
                        f"Required check {_display(check['name'])} accepts a result from "
                        "any source; it must be bound to the App that produces it.",
                    )
                )
    protected = protected_changes(facts["changed_files"], settings["protected_paths"])
    if protected:
        listed = ", ".join(_display(path) for path in protected[:_MAX_LISTED_PATHS])
        more = len(protected) - _MAX_LISTED_PATHS
        suffix = f" and {more} more" if more > 0 else ""
        findings.append(
            _finding(
                "github.protected_path_changed",
                f"The pull request changes CI or repository configuration ({listed}{suffix}); "
                "it requires explicit human acceptance and cannot be auto-accepted.",
            )
        )
    approvals = qualifying_approvals(facts)
    if len(approvals) < settings["required_approvals"]:
        findings.append(
            _finding(
                "github.independent_approval_missing",
                f"The head commit needs {settings['required_approvals']} approval(s) from "
                "reviewers who are neither the author nor a bot; "
                f"GitHub shows {len(approvals)}.",
            )
        )
    if approvals and all(login.casefold() in settings["operators"] for login in approvals):
        findings.append(
            {
                **_finding(
                    "operator_approved",
                    "Only operator accounts approved this work. It may earn points but may "
                    "not be paid in money until an independent reviewer confirms it.",
                    level="warning",
                ),
                "code": OPERATOR_APPROVED_CODE,
            }
        )
    return findings


def compare_github_facts(
    proof: dict, configuration: object, input_value: object
) -> list[dict[str, object]]:
    """Compare proof claims with WorkStream-read GitHub facts; one finding per mismatch."""
    configured = _github_configuration(configuration)
    if configured is False:
        return [
            _finding(
                "github.configuration",
                "The checker configuration must name github_repository and base_branch, "
                "with only supported integrity options.",
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
        if repository.casefold() != configured["repository"].casefold():
            findings.append(
                _finding(
                    "github.repository",
                    f"The pull request belongs to {_display(repository)}, "
                    f"not {_display(configured['repository'])}.",
                )
            )
        if facts["base_ref"] != configured["base_branch"]:
            findings.append(
                _finding(
                    "github.base_branch",
                    f"The pull request targets {_display(facts['base_ref'])}, "
                    f"not {_display(configured['base_branch'])}.",
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
    findings.extend(_integrity_findings(facts, configured))
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
