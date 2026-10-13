#!/usr/bin/env python3
"""Select conservative Backend CI components for one exact repository diff."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Iterable, Sequence

# Direct-file CI execution and package imports share one catalogue.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.test_lane_catalogue import LANES


ALL_LANES = tuple(lane.name for lane in LANES)
LANES_BY_TEST_MODULE = {
    module: tuple(lane.name for lane in LANES if module in lane.modules)
    for lane in LANES
    for module in lane.modules
}

FULL_SCOPE_PATHS = frozenset(
    {
        ".github/workflows/backend.yml",
        "backend/scripts/select_ci_scope.py",
        "backend/scripts/test_lane_catalogue.py",
        "scripts/test_lightweight_agent_gates.py",
    }
)
PREFLIGHT_PREFIXES = (
    ".ci/auth-boundaries/",
    ".ci/behavior-ownership/",
)


@dataclass(frozen=True)
class CiScope:
    """One fail-closed selection for a Backend workflow run."""

    full_suite: bool
    preflight: bool
    external_checker: bool
    cli_contract: bool
    lanes: tuple[str, ...]
    reason: str

    @property
    def lanes_required(self) -> bool:
        """Return whether at least one semantic lane must run."""
        return bool(self.lanes)

    @property
    def minio_image(self) -> bool:
        """Return whether a selected component consumes the MinIO artifact."""
        return self.lanes_required or self.cli_contract or self.full_suite

    def outputs(self) -> dict[str, str]:
        """Render stable GitHub output strings."""
        # GitHub validates a dynamic matrix even when its owning job is skipped.
        # Keep the matrix non-empty and use lanes_required as the actual gate.
        matrix_lanes = self.lanes or ALL_LANES
        return {
            "full_suite": _boolean(self.full_suite),
            "preflight": _boolean(self.preflight),
            "external_checker": _boolean(self.external_checker),
            "cli_contract": _boolean(self.cli_contract),
            "minio_image": _boolean(self.minio_image),
            "lanes_required": _boolean(self.lanes_required),
            "lane_matrix": json.dumps(
                {"lane": list(matrix_lanes)}, separators=(",", ":")
            ),
            "scope_reason": self.reason,
        }


def _boolean(value: bool) -> str:
    return "true" if value else "false"


def full_scope(reason: str) -> CiScope:
    """Return the complete blocking Backend proof selection."""
    return CiScope(
        full_suite=True,
        preflight=True,
        external_checker=True,
        cli_contract=True,
        lanes=ALL_LANES,
        reason=reason,
    )


def _normalize_paths(paths: Iterable[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for raw in paths:
        value = raw.strip().replace("\\", "/")
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"invalid changed path: {raw!r}")
        normalized.add(path.as_posix())
    return tuple(sorted(normalized))


def _test_module_lanes(path: str) -> tuple[str, ...] | None:
    if not path.startswith("backend/tests/") or not path.endswith(".py"):
        return None
    module = path.removeprefix("backend/")
    if not PurePosixPath(module).name.startswith("test_"):
        return None
    return LANES_BY_TEST_MODULE.get(module)


def select_scope(
    paths: Iterable[str],
    *,
    event_name: str,
    pull_request_draft: bool,
) -> CiScope:
    """Select draft feedback or the complete merge-candidate suite."""
    changed = _normalize_paths(paths)
    if event_name != "pull_request":
        return full_scope("protected_push")
    if not pull_request_draft:
        return full_scope("ready_pull_request")
    if not changed:
        return full_scope("empty_diff_fails_closed")

    selected_lanes: set[str] = set()
    preflight = False
    external_checker = False
    cli_contract = False
    fallback_all_lanes = False

    for path in changed:
        if path in FULL_SCOPE_PATHS or path.startswith("docker/minio/"):
            preflight = True
            external_checker = True
            cli_contract = True
            fallback_all_lanes = True
            continue
        if path == ".github/workflows/cli.yml" or path.startswith("cli/"):
            cli_contract = True
            continue
        if path.startswith("external_checkers/"):
            external_checker = True
            continue
        if path.startswith(PREFLIGHT_PREFIXES):
            preflight = True
            continue
        if path.startswith("backend/tests/"):
            preflight = True
            lanes = _test_module_lanes(path)
            if lanes is None:
                fallback_all_lanes = True
            else:
                selected_lanes.update(lanes)
            continue
        if path.startswith("backend/"):
            preflight = True
            fallback_all_lanes = True
            cli_contract = True

    lanes = ALL_LANES if fallback_all_lanes else tuple(
        lane for lane in ALL_LANES if lane in selected_lanes
    )
    return CiScope(
        full_suite=False,
        preflight=preflight,
        external_checker=external_checker,
        cli_contract=cli_contract,
        lanes=lanes,
        reason="draft_changed_paths",
    )


def changed_paths(base_ref: str, head_ref: str) -> tuple[str, ...]:
    """Read the exact base-to-head changed-file set from Git."""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--no-renames",
            "--name-only",
            "--diff-filter=ACDMRT",
            f"{base_ref}...{head_ref}",
            "--",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return _normalize_paths(result.stdout.splitlines())


def write_github_outputs(path: Path, scope: CiScope) -> None:
    """Append the selected scope to the GitHub output file."""
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for name, value in scope.outputs().items():
            output.write(f"{name}={value}\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the deterministic scope-selector CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--pull-request-draft", choices=("true", "false"), required=True)
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref")
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.changed_path and (not args.base_ref or not args.head_ref):
        parser.error("base/head refs are required when changed paths are not supplied")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Select and emit one exact CI scope."""
    args = parse_args(argv)
    paths = tuple(args.changed_path) or changed_paths(args.base_ref, args.head_ref)
    scope = select_scope(
        paths,
        event_name=args.event_name,
        pull_request_draft=args.pull_request_draft == "true",
    )
    write_github_outputs(args.github_output, scope)
    print(json.dumps(scope.outputs(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
