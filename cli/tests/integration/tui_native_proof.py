"""Exact-selection pytest evidence for native terminal proof, not release assets."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys


SUITE = "cli/tests/integration/test_tui_http.py"
TARGETS = {
    ("Linux", "x86_64"): "linux-amd64",
    ("Darwin", "x86_64"): "darwin-amd64",
    ("Darwin", "arm64"): "darwin-arm64",
    ("Windows", "AMD64"): "windows-amd64",
}


class ProofError(ValueError):
    """Incomplete, mismatched or unsuccessful native proof."""


class Reports:
    """Observe collection before selection and retain every phase, including XPASS."""

    def __init__(self):
        self.collected = []
        self.selected = []
        self.deselected = []
        self.collection_errors = []
        self.reports = []

    def pytest_itemcollected(self, item):
        self.collected.append(item.nodeid)

    def pytest_deselected(self, items):
        self.deselected.extend(item.nodeid for item in items)

    def pytest_collection_finish(self, session):
        self.selected = [item.nodeid for item in session.items]

    def pytest_collectreport(self, report):
        if report.outcome != "passed":
            self.collection_errors.append(
                {"nodeid": report.nodeid, "outcome": report.outcome}
            )

    def pytest_runtest_logreport(self, report):
        self.reports.append(
            {
                "nodeid": report.nodeid,
                "when": report.when,
                "outcome": report.outcome,
                # Presence, not truthiness: an empty xfail reason is still xfail.
                "wasxfail": getattr(report, "wasxfail", None),
                "has_wasxfail": hasattr(report, "wasxfail"),
            }
        )


def validate(evidence, binding):
    if evidence["binding"] != binding or evidence["finished"] is not True:
        raise ProofError("unfinished or mismatched proof")
    if type(evidence["exit_code"]) is not int or evidence["exit_code"] != 0:
        raise ProofError("pytest did not exit successfully")
    collected = evidence["collected"]
    if not collected or any(not isinstance(node, str) for node in collected):
        raise ProofError("empty or invalid collection")
    if len(set(collected)) != len(collected):
        raise ProofError("duplicate collected node IDs")
    if evidence["deselected"] or evidence["collection_errors"]:
        raise ProofError("deselection or collection failure")
    if Counter(evidence["selected"]) != Counter(collected):
        raise ProofError("selected tests differ from raw collection")
    reports = {node: [] for node in collected}
    for report in evidence["reports"]:
        node = report["nodeid"]
        if node not in reports:
            raise ProofError("report for uncollected test")
        if (
            report["outcome"] != "passed"
            or report["has_wasxfail"] is not False
            or report["wasxfail"] is not None
        ):
            raise ProofError("unsuccessful or xfail phase")
        reports[node].append(report["when"])
    if any(phases != ["setup", "call", "teardown"] for phases in reports.values()):
        raise ProofError("missing, duplicate or out-of-order phase reports")
    return len(collected)


def run_tests(test_file, binding, output, *, extra_args=(), plugins=()):
    """Internal seam for adversarial self-tests; CLI always selects SUITE exactly."""
    output.mkdir(parents=True, exist_ok=True)
    receipt = output / "completion.json"
    receipt.unlink(missing_ok=True)  # A failed retry cannot inherit prior success.
    os.environ.pop("PYTEST_ADDOPTS", None)
    os.environ.pop("PYTEST_PLUGINS", None)
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    import pytest

    observer = Reports()
    evidence = {"binding": binding, "finished": False, "exit_code": None}
    try:
        code = pytest.main(
            [
                "-c",
                os.devnull,
                "--rootdir",
                str(test_file.parent),
                "--confcutdir",
                str(test_file.parent),
                "-p",
                "no:cacheprovider",
                "-o",
                "addopts=",
                "-q",
                str(test_file),
                *extra_args,
            ],
            plugins=[observer, *plugins],
        )
        evidence.update(finished=True, exit_code=int(code))
    finally:
        evidence.update(vars(observer))
        raw = json.dumps(evidence, indent=2, sort_keys=True).encode() + b"\n"
        (output / "reports.json").write_bytes(raw)
    count = validate(evidence, binding)
    receipt.write_text(
        json.dumps(
            {
                "binding": binding,
                "reports_sha256": hashlib.sha256(raw).hexdigest(),
                "passed": count,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def verify(output, binding):
    receipt = json.loads((output / "completion.json").read_text(encoding="utf-8"))
    raw = (output / "reports.json").read_bytes()
    if receipt["binding"] != binding:
        raise ProofError("receipt binding differs")
    if receipt["reports_sha256"] != hashlib.sha256(raw).hexdigest():
        raise ProofError("report bytes differ from completion receipt")
    count = validate(json.loads(raw), binding)
    if type(receipt["passed"]) is not int or receipt["passed"] != count:
        raise ProofError("receipt count differs")
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["run", "verify"])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--platform", required=True, choices=sorted(TARGETS.values()))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.source):
            raise ProofError("full source SHA required")
        if not all(
            re.fullmatch(r"[1-9][0-9]*", value)
            for value in [args.run_id, args.run_attempt]
        ):
            raise ProofError("positive workflow run and attempt required")
        binding = {
            "source": args.source,
            "platform": args.platform,
            "run_id": args.run_id,
            "run_attempt": args.run_attempt,
            "suite": SUITE,
        }
        if args.operation == "run":
            root = Path(__file__).resolve().parents[3]
            actual = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            if actual != args.source:
                raise ProofError("checkout source differs")
            if subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=root, text=True
            ).strip():
                raise ProofError("native proof requires an unchanged checkout")
            if TARGETS.get((platform.system(), platform.machine())) != args.platform:
                raise ProofError("runner is not the claimed native target")
            run_tests(root / SUITE, binding, args.output)
        count = verify(args.output, binding)
        print(f"Validated native terminal proof: {count} tests; {args.platform}")
    except (ProofError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"native terminal proof rejected: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
