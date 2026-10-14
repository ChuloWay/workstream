"""Bind selected execution to fresh collection and independently reproducible impact."""

from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.select_ci_scope import changed_paths, select_scope
from scripts.test_lane_catalogue import ADMIN_RUNNER_MODULE, LANES, PARTITION_LANES_BY_MODULE


class SelectionError(ValueError):
    """Selected proof does not match the current source and event."""


def receipt_bytes(value: dict[str, Any]) -> bytes:
    """Encode the single canonical receipt representation."""
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def receipt_digest(value: dict[str, Any]) -> str:
    """Identify one complete selection, not merely its selected modules."""
    return hashlib.sha256(receipt_bytes(value)).hexdigest()


def _git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=root, text=True).strip()


def input_digest(root: Path) -> str:
    """Bind tracked selection sources, fixtures, catalogue and collection inputs."""
    names = subprocess.check_output(
        ["git", "ls-files", "-z", "backend", ".ci/behavior-ownership"], cwd=root,
    ).decode().split("\0")[:-1]
    digest = hashlib.sha256()
    for name in sorted(names):
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise SelectionError("missing_or_symlinked_selection_input")
        digest.update(name.encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def build_receipt(
    root: Path, *, base_sha: str, pr_head_sha: str, tested_sha: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Recompute a selection from exact commits and a full fresh manifest."""
    for revision in (base_sha, pr_head_sha, tested_sha):
        if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            raise SelectionError("invalid_selection_revision")
        if _git(root, "rev-parse", f"{revision}^{{commit}}") != revision:
            raise SelectionError("unavailable_selection_revision")
    if _git(root, "rev-parse", "HEAD") != tested_sha:
        raise SelectionError("selection_tested_head_mismatch")
    # The tested tree must include both event commits. This also permits a
    # branch-head local probe when its base is already an ancestor.
    for revision in (base_sha, pr_head_sha):
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, tested_sha], cwd=root,
            check=False, capture_output=True,
        ).returncode != 0:
            raise SelectionError("selection_event_not_in_tested_tree")
    if manifest.get("head_sha") != tested_sha or manifest.get("schema_version") != 1:
        raise SelectionError("selection_manifest_mismatch")
    scope = select_scope(
        changed_paths(base_sha, tested_sha, repository_root=root),
        event_name="pull_request", pull_request_draft=False,
        repository_root=root, base_ref=base_sha,
    )
    if scope.full_suite or not scope.modules:
        raise SelectionError("selection_requires_full_execution")
    rows = manifest.get("nodes")
    if not isinstance(rows, list) or not rows:
        raise SelectionError("empty_selection_inventory")
    inventory = {module for lane in LANES for module in lane.modules}
    try:
        if {row["module"] for row in rows} != inventory:
            raise SelectionError("selection_inventory_mismatch")
        for row in rows:
            candidates = [lane.name for lane in LANES if row["module"] in lane.modules]
            partition = PARTITION_LANES_BY_MODULE.get(row["module"])
            if partition is not None:
                if candidates != list(partition):
                    raise SelectionError("selection_partition_mismatch")
                expected_lane = candidates[hashlib.sha256(row["nodeid"].encode()).digest()[0] % len(candidates)]
            elif len(candidates) == 1:
                expected_lane = candidates[0]
            else:
                raise SelectionError("ambiguous_selection_lane")
            expected_kind = "admin_runner_self_test" if row["module"] == ADMIN_RUNNER_MODULE else "ordinary_isolated"
            if (row["lane"] != expected_lane or row["execution_kind"] != expected_kind
                    or not row["nodeid"].startswith(row["module"] + "::")):
                raise SelectionError("selection_node_assignment_mismatch")
        selected = [row for row in rows if row["module"] in scope.modules]
        nodes = [row["nodeid"] for row in selected]
        if (not nodes or len(nodes) != len(set(nodes)) or nodes != sorted(nodes)
                or not any(row["module"] != ADMIN_RUNNER_MODULE for row in selected)):
            raise SelectionError("empty_or_noncanonical_selection")
        lanes = [lane.name for lane in LANES if any(row["lane"] == lane.name for row in selected)]
        if not lanes or {row["lane"] for row in selected} != set(lanes):
            raise SelectionError("invalid_selection_lanes")
    except (KeyError, TypeError) as exc:
        raise SelectionError("invalid_selection_inventory") from exc
    return {
        "schema_version": 1,
        "mode": "selected",
        "base_sha": base_sha,
        "pr_head_sha": pr_head_sha,
        "tested_sha": tested_sha,
        "input_sha256": input_digest(root),
        "manifest_sha256": hashlib.sha256(receipt_bytes(manifest)).hexdigest(),
        "selected_modules": list(scope.modules),
        "omitted_modules": sorted(inventory - set(scope.modules)),
        "selected_nodes": nodes,
        "lanes": lanes,
        "reason": scope.reason,
    }


def verify_receipt(
    path: Path, root: Path, *, base_sha: str, pr_head_sha: str,
    tested_sha: str, manifest: dict[str, Any],
) -> dict[str, Any]:
    """Reject stale, forged or partial selection using external event identities."""
    if path.is_symlink() or not path.is_file():
        raise SelectionError("missing_selection_receipt")
    expected = build_receipt(
        root, base_sha=base_sha, pr_head_sha=pr_head_sha,
        tested_sha=tested_sha, manifest=manifest,
    )
    if path.read_bytes() != receipt_bytes(expected):
        raise SelectionError("selection_receipt_mismatch")
    return expected


def main() -> int:
    """Freshly collect before publishing the exact nonempty execution matrix."""
    # Local import keeps the receipt/runner relationship acyclic at import time.
    from scripts.run_test_lanes import run_lanes

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--pr-head-sha", required=True)
    parser.add_argument("--tested-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(mode=0o700)
    metadata = args.output_dir / "collection"
    run_lanes(metadata, args.output_dir / "collection-summary.json", 1200, collect_only=True)
    manifest = json.loads((metadata / "manifest.json").read_bytes())
    receipt = build_receipt(
        Path(__file__).resolve().parents[2], base_sha=args.base_sha,
        pr_head_sha=args.pr_head_sha, tested_sha=args.tested_sha, manifest=manifest,
    )
    (args.output_dir / "selection.json").write_bytes(receipt_bytes(receipt))
    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"selection_digest={receipt_digest(receipt)}\n")
        output.write("lane_matrix=" + json.dumps({"lane": receipt["lanes"]}, separators=(",", ":")) + "\n")
    print(f"Selected {len(receipt['selected_nodes'])} nodes in {len(receipt['lanes'])} lanes; "
          f"omitted {len(receipt['omitted_modules'])} unrelated modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
