#!/usr/bin/env python3
"""Merge independently executed semantic-lane bundles fail closed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any

from scripts.run_test_lanes import LANES, LaneError, SCHEMA_VERSION
from scripts.ci_selection_receipt import (
    SelectionError, receipt_bytes, receipt_digest, verify_receipt,
)


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _read_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise LaneError("missing_lane_bundle_file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LaneError("invalid_lane_bundle_json") from exc
    if not isinstance(value, dict):
        raise LaneError("invalid_lane_bundle_json")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_bound(source: Path, destination: Path, expected_digest: Any) -> None:
    if (
        not isinstance(expected_digest, str)
        or len(expected_digest) != 64
        or source.is_symlink()
        or not source.is_file()
        or _digest(source) != expected_digest
        or destination.exists()
        or destination.is_symlink()
    ):
        raise LaneError("invalid_lane_bundle_file")
    shutil.copyfile(source, destination)


def select_lane_bundles(
    input_root: Path, head_sha: str, run_attempt: int, *,
    selection: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Select latest numeric attempts, never an older passing bundle after failure."""
    if (
        re.fullmatch(r"[0-9a-f]{40}", head_sha) is None
        or type(run_attempt) is not int
        or run_attempt < 1
        or input_root.is_symlink()
        or not input_root.is_dir()
    ):
        raise LaneError("invalid_lane_bundle_root")
    expected = set(selection["lanes"]) if selection is not None else {lane.name for lane in LANES}
    if not expected or not expected <= {lane.name for lane in LANES}:
        raise LaneError("invalid_selected_lane_set")
    prefix = (f"backend-selected-{receipt_digest(selection)}" if selection is not None
              else "backend-lane")
    pattern = re.compile(rf"{prefix}-{head_sha}-([a-z_]+)-attempt-([1-9][0-9]*)")
    selected: dict[str, tuple[int, Path]] = {}
    for path in input_root.iterdir():
        match = pattern.fullmatch(path.name)
        if path.is_symlink() or not path.is_dir() or match is None:
            raise LaneError("invalid_lane_bundle_set")
        lane, attempt_text = match.groups()
        attempt = int(attempt_text)
        if lane not in expected or attempt > run_attempt:
            raise LaneError("invalid_lane_bundle_set")
        if lane not in selected or attempt > selected[lane][0]:
            selected[lane] = (attempt, path)
    if selected.keys() != expected:
        raise LaneError("invalid_lane_bundle_set")
    return {lane.name: selected[lane.name][1] for lane in LANES if lane.name in expected}


def merge_bundles(
    input_root: Path, metadata_dir: Path, summary_json: Path, *,
    expected_head: str, run_attempt: int,
    selection_file: Path | None = None, base_sha: str = "", pr_head_sha: str = "",
    repository_root: Path | None = None,
) -> None:
    """Merge exactly one authenticated bundle for each declared lane."""
    if (
        input_root.is_symlink()
        or not input_root.is_dir()
        or metadata_dir.exists()
        or metadata_dir.is_symlink()
        or summary_json.exists()
        or summary_json.is_symlink()
    ):
        raise LaneError("invalid_lane_bundle_root")
    selection = _read_object(selection_file) if selection_file is not None else None
    if selection is None and (base_sha or pr_head_sha):
        raise LaneError("selection_identity_without_receipt")
    bundles = select_lane_bundles(input_root, expected_head, run_attempt, selection=selection)
    metadata_dir.mkdir(mode=0o700)

    manifest_bytes: bytes | None = None
    manifest_digest: str | None = None
    head_sha: str | None = None
    canonical_node_count: int | None = None
    lane_rows: list[dict[str, Any]] = []
    elapsed_seconds = 0.0
    for lane in LANES:
        if lane.name not in bundles:
            continue
        bundle = bundles[lane.name]
        print(f"Selected lane evidence: {bundle.name}")
        summary = _read_object(bundle / "summary.json")
        if (
            summary.get("schema_version") != SCHEMA_VERSION
            or summary.get("head_sha") != expected_head
            or summary.get("mode") != ("selected_lane" if selection is not None else "lane")
            or not isinstance(summary.get("lanes"), list)
            or len(summary["lanes"]) != 1
            or not isinstance(summary["lanes"][0], dict)
            or summary["lanes"][0].get("name") != lane.name
        ):
            raise LaneError("invalid_lane_bundle_summary")
        row = summary["lanes"][0]
        if (
            row.get("collection_exit_code") != 0
            or row.get("execution_exit_code") != 0
            or row.get("interrupted") is not False
        ):
            raise LaneError("lane_bundle_execution_incomplete")
        source_metadata = bundle / "metadata"
        if source_metadata.is_symlink() or not source_metadata.is_dir():
            raise LaneError("invalid_lane_bundle_metadata")
        manifest_name = summary.get("manifest_file")
        if not isinstance(manifest_name, str) or Path(manifest_name).name != manifest_name:
            raise LaneError("invalid_lane_bundle_manifest")
        source_manifest = source_metadata / manifest_name
        if source_manifest.is_symlink() or not source_manifest.is_file():
            raise LaneError("invalid_lane_bundle_manifest")
        current_manifest = source_manifest.read_bytes()
        if _digest(source_manifest) != summary.get("manifest_sha256"):
            raise LaneError("invalid_lane_bundle_manifest")
        if manifest_bytes is None:
            if selection is not None:
                selection = verify_receipt(
                    selection_file, repository_root or Path(__file__).resolve().parents[2],
                    base_sha=base_sha, pr_head_sha=pr_head_sha, tested_sha=expected_head,
                    manifest=_read_object(source_manifest),
                )
                (metadata_dir / "selection.json").write_bytes(receipt_bytes(selection))
            manifest_bytes = current_manifest
            manifest_digest = summary["manifest_sha256"]
            head_sha = summary.get("head_sha")
            canonical_node_count = summary.get("canonical_node_count")
            (metadata_dir / "manifest.json").write_bytes(current_manifest)
        elif (
            current_manifest != manifest_bytes
            or summary.get("manifest_sha256") != manifest_digest
            or summary.get("head_sha") != head_sha
            or summary.get("canonical_node_count") != canonical_node_count
        ):
            raise LaneError("lane_manifest_mismatch")

        if selection is not None:
            if (summary.get("selection_file") != "selection.json" or
                    summary.get("selection_sha256") != receipt_digest(selection) or
                    (source_metadata / "selection.json").is_symlink() or
                    (source_metadata / "selection.json").read_bytes() != receipt_bytes(selection)):
                raise LaneError("lane_selection_mismatch")

        for file_key, digest_key in (
            ("evidence_file", "evidence_sha256"),
            ("coverage_file", "coverage_sha256"),
        ):
            name = row.get(file_key)
            if not isinstance(name, str) or Path(name).name != name:
                raise LaneError("invalid_lane_bundle_file")
            _copy_bound(source_metadata / name, metadata_dir / name, row.get(digest_key))
        evidence = _read_object(metadata_dir / row["evidence_file"])
        isolation_name = evidence.get("isolation_metadata_file")
        if not isinstance(isolation_name, str) or Path(isolation_name).name != isolation_name:
            raise LaneError("invalid_lane_bundle_file")
        _copy_bound(
            source_metadata / isolation_name,
            metadata_dir / isolation_name,
            evidence.get("isolation_metadata_sha256"),
        )
        if not isinstance(row.get("elapsed_seconds"), (int, float)):
            raise LaneError("invalid_lane_bundle_timing")
        elapsed_seconds = max(elapsed_seconds, float(row["elapsed_seconds"]))
        lane_rows.append(row)

    elapsed = [float(row["elapsed_seconds"]) for row in lane_rows]
    summary_json.write_bytes(
        _canonical_json(
            {
                "aggregate_runner_seconds": round(sum(elapsed), 3),
                "canonical_node_count": canonical_node_count,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "head_sha": head_sha,
                "lanes": lane_rows,
                "manifest_file": "manifest.json",
                "manifest_sha256": manifest_digest,
                "mode": "selected_run" if selection is not None else "run",
                **({"selection_file": "selection.json", "selection_sha256": receipt_digest(selection)}
                   if selection is not None else {}),
                "schema_version": SCHEMA_VERSION,
                "slowest_lane_seconds": round(max(elapsed), 3),
            }
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--metadata-dir", required=True, type=Path)
    parser.add_argument("--summary-json", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--selection-file", type=Path)
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--pr-head-sha", default="")
    args = parser.parse_args()
    try:
        merge_bundles(
            args.input_root, args.metadata_dir, args.summary_json,
            expected_head=args.expected_head, run_attempt=args.run_attempt,
            selection_file=args.selection_file, base_sha=args.base_sha, pr_head_sha=args.pr_head_sha,
        )
    except (LaneError, SelectionError, OSError, KeyError, TypeError) as exc:
        code = exc.args[0] if isinstance(exc, LaneError) else "lane_merge_failed"
        print(f"test lane merge failed: {code}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
