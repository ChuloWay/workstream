#!/usr/bin/env python3
"""Reduce trusted runtime observations to the fixed WS493 proof matrix."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path


SCHEMA = "workstream.terminal_benchmark_project_checker_proof.v1"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise ValueError(f"invalid object: {path.name}")
    return value


def _ndjson(path: Path) -> list[dict[str, object]]:
    values = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    if not values or any(type(value) is not dict for value in values):
        raise ValueError(f"invalid NDJSON: {path.name}")
    return values


def _write(path: Path, value: object) -> None:
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    raw = arguments.raw
    interrupted = _json(raw / "interrupt.json")
    art_interrupted = _json(raw / "art-interrupt.json")
    restart = _json(raw / "restart-cleanup.json")
    complete = _json(raw / "complete-result.json")
    art_complete = _json(raw / "art-complete.json")
    launches = _ndjson(raw / "launches.ndjson")
    results = _ndjson(raw / "command-results.ndjson")

    checker_launches = [
        launch for launch in launches if launch.get("kind") == "checker"
    ]
    if (
        len(checker_launches) != 2
        or len({item.get("container_id") for item in checker_launches}) != 2
    ):
        raise ValueError("checker launches were not fresh")
    terminal_launches = [
        launch for launch in launches if launch.get("kind") != "checker"
    ]
    by_attempt: dict[str, list[dict[str, object]]] = defaultdict(list)
    for launch in terminal_launches:
        attempt = launch.get("attempt")
        if type(attempt) is not str:
            raise ValueError("launch attempt missing")
        by_attempt[attempt].append(launch)
    complete_attempts = [
        (attempt, items)
        for attempt, items in by_attempt.items()
        if sorted(str(item.get("kind")) for item in items)
        == ["builder", "candidate", "reference", "reference", "reference"]
    ]
    interrupted_attempts = [
        (attempt, items)
        for attempt, items in by_attempt.items()
        if [str(item.get("kind")) for item in items] == ["builder"]
    ]
    if len(complete_attempts) != 1 or len(interrupted_attempts) != 1:
        raise ValueError("launch matrix differs")
    complete_attempt, complete_launches = complete_attempts[0]
    if len({item.get("container_id") for item in complete_launches}) != 5:
        raise ValueError("complete containers were not fresh")

    statuses: dict[str, int] = {}
    for result in results:
        argv = result.get("argv")
        status = result.get("status")
        if (
            isinstance(argv, list)
            and len(argv) == 3
            and argv[:2] == ["start", "--attach"]
            and type(argv[2]) is str
            and type(status) is int
        ):
            statuses[argv[2]] = status
    builder_name = f"ws-terminal-builder-{complete_attempt}"
    candidate_name = f"ws-terminal-candidate-{complete_attempt}"
    reference_names = [
        f"ws-terminal-reference-{complete_attempt}-{index}" for index in range(3)
    ]
    if set([builder_name, candidate_name, *reference_names]) - statuses.keys():
        raise ValueError("container exit observations are incomplete")
    checker_names = [str(item.get("name")) for item in checker_launches]
    if any(statuses.get(name) != 0 for name in checker_names):
        raise ValueError("checker planning exits differ")

    result = complete.get("result")
    if (
        interrupted.get("adapter_failure") is not True
        or art_interrupted != {"ledger_empty": True, "workspace_empty": True}
        or restart
        != {
            "owned_containers_absent": True,
            "owned_images_absent": True,
            "unowned_control_preserved": True,
        }
        or type(result) is not dict
        or result.get("outcome") != "completed"
        or result.get("verdict") != "passed"
        or result.get("findings") != []
        or art_complete != {"ledger_empty": True, "workspace_empty": True}
        or statuses[builder_name] != 0
        or statuses[candidate_name] != 1
        or [statuses[name] for name in reference_names] != [0, 0, 0]
    ):
        raise ValueError("POST proof outcome differs")

    matrix = {
        "schema_version": SCHEMA,
        "head_sha": arguments.head,
        "interrupted": {
            "adapter_failure": True,
            "art_unwound": True,
            "restart_swept_owned": True,
            "unowned_control_preserved": True,
        },
        "complete": {
            "builder_exit": 0,
            "candidate_exit": 1,
            "outcome": "completed",
            "owned_resources_absent": True,
            "reference_exits": [0, 0, 0],
            "stable": True,
            "verdict": "passed",
        },
    }
    _write(arguments.output, matrix)


if __name__ == "__main__":
    main()
