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
SDK_ENVIRONMENT_BY_LANE = {lane.name: lane.sdk_environment for lane in LANES}


@dataclass(frozen=True)
class CiScope:
    """One fail-closed selection for a Backend workflow run."""

    full_suite: bool
    preflight: bool
    external_checker: bool
    cli_contract: bool
    lanes: tuple[str, ...]
    reason: str
    mcp_contract: bool = False

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
                {
                    "include": [
                        {
                            "lane": lane,
                            "sdk_environment": SDK_ENVIRONMENT_BY_LANE[lane],
                        }
                        for lane in matrix_lanes
                    ]
                },
                separators=(",", ":"),
            ),
            "scope_reason": self.reason,
            "mcp_contract": _boolean(self.mcp_contract),
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
        mcp_contract=True,
    )


def _normalize_paths(paths: Iterable[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for raw in paths:
        value = raw
        path = PurePosixPath(value)
        if (not value or path.is_absolute() or ".." in path.parts
                or "\\" in value or any(ord(char) < 32 for char in value)
                or path.as_posix() != value):
            raise ValueError(f"invalid changed path: {raw!r}")
        normalized.add(path.as_posix())
    return tuple(sorted(normalized))


def select_scope(
    paths: Iterable[str],
    *,
    event_name: str,
    pull_request_draft: bool,
) -> CiScope:
    """Select positively classified impact; unknown dependencies run everything."""
    del pull_request_draft  # Check naming differs; dependency impact does not.
    changed = _normalize_paths(paths)
    if event_name != "pull_request":
        return full_scope("protected_push")
    if not changed:
        return full_scope("empty_diff_fails_closed")
    cli_contract = False
    mcp_contract = False
    for path in changed:
        if (path in {"README.md", "CHANGELOG.md"} or
                path.endswith(".md") and path.startswith(("docs/", ".commitrail/changes/"))):
            continue
        if path.startswith("cli/"):
            cli_contract = True
            continue
        if path.startswith("mcp_server/"):
            mcp_contract = True
            continue
        return full_scope("unknown_or_cross_cutting_path")
    return CiScope(
        full_suite=False,
        preflight=False,
        external_checker=False,
        cli_contract=cli_contract,
        lanes=(),
        reason="verified_changed_paths",
        mcp_contract=mcp_contract,
    )


def changed_paths(
    base_ref: str, head_ref: str, *, repository_root: Path | None = None,
) -> tuple[str, ...]:
    """Read the exact base-to-head changed-file set from Git."""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--no-renames",
            "--name-only",
            "-z",
            "--diff-filter=ACDMRT",
            f"{base_ref}...{head_ref}",
            "--",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=repository_root,
    )
    return _normalize_paths(result.stdout.split("\0")[:-1])


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
    parser.add_argument("--base-ref", default="")
    parser.add_argument("--head-ref", default="")
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.event_name == "pull_request" and not args.changed_path and (not args.base_ref or not args.head_ref):
        parser.error(
            "base/head refs are required when changed paths are not supplied for pull requests"
        )
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Select and emit one exact CI scope."""
    args = parse_args(argv)
    if args.changed_path:
        paths: Sequence[str] = tuple(args.changed_path)
    elif args.event_name == "pull_request":
        try:
            paths = changed_paths(args.base_ref, args.head_ref)
        except (ValueError, subprocess.SubprocessError):
            scope = full_scope("unavailable_diff")
            write_github_outputs(args.github_output, scope)
            print(json.dumps(scope.outputs(), sort_keys=True))
            return 0
    else:
        paths = ()
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
