#!/usr/bin/env python3
"""Reduce trusted runtime observations to the fixed WS493 proof matrix."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path


SCHEMA = "workstream.terminal_benchmark_project_checker_proof.v2"
SOURCE_IDENTITIES = {
    "checker": {"/work/input": "art_workspace"},
    "builder": {
        "/cache": "sealed_cache",
        "/out/candidate.tar": "art_runtime_candidate_tar",
        "/project": "art_runtime_build_context",
    },
    "candidate": {"/tests": "art_workspace_tests"},
    "reference": {
        "/tests": "art_workspace_tests",
        "/workspace/program.py": "art_workspace_reference_solution",
    },
}
CASES = {
    "complete": {
        "result": "complete-result.json",
        "art": "art-complete.json",
        "outcome": "completed",
        "verdict": "passed",
        "code": None,
        "launches": ["builder", "candidate", "reference", "reference", "reference"],
        "starts": [0, 1, 0, 0, 0],
    },
    "no-op-pass": {
        "result": "no-op-pass-result.json",
        "art": "art-no-op-pass.json",
        "outcome": "completed",
        "verdict": "failed",
        "code": "starter_unexpectedly_passed",
        "launches": ["builder", "candidate"],
        "starts": [0, 0],
    },
    "reference-failure": {
        "result": "reference-failure-result.json",
        "art": "art-reference-failure.json",
        "outcome": "completed",
        "verdict": "failed",
        "code": "reference_failed",
        "launches": ["builder", "candidate", "reference"],
        "starts": [0, 1, 1],
    },
    "reference-instability": {
        "result": "reference-instability-result.json",
        "art": "art-reference-instability.json",
        "outcome": "completed",
        "verdict": "failed",
        "code": "reference_unstable",
        "launches": ["builder", "candidate", "reference", "reference"],
        "starts": [0, 1, 0, 0],
    },
    "memory-capacity": {
        "result": "memory-capacity-result.json",
        "art": "art-memory-capacity.json",
        "outcome": "infrastructure_failed",
        "verdict": None,
        "code": "capacity_exceeded",
        "launches": ["builder", "candidate"],
        "starts": [0, 137],
    },
    "capacity-spoof": {
        "result": "capacity-spoof-result.json",
        "art": "art-capacity-spoof.json",
        "outcome": "infrastructure_failed",
        "verdict": None,
        "code": "implementation_unavailable",
        "launches": ["builder", "candidate"],
        "starts": [0, 2],
    },
    "missing-base": {
        "result": "missing-base-result.json",
        "art": "art-missing-base.json",
        "outcome": "infrastructure_failed",
        "verdict": None,
        "code": "implementation_unavailable",
        "launches": [],
        "starts": [],
    },
}


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
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validated_result(
    raw: Path, name: str, expected: dict[str, object]
) -> tuple[str, dict[str, object]]:
    value = _json(raw / str(expected["result"]))
    art = _json(raw / str(expected["art"]))
    result = value.get("result")
    isolation = value.get("isolation")
    request_digest = value.get("request_digest")
    if (
        value.get("schema_version") != "workstream.terminal_benchmark_result.v1"
        or type(result) is not dict
        or type(isolation) is not dict
        or isolation.get("runtime") != "runsc"
        or not isinstance(request_digest, str)
        or result.get("request_digest") != request_digest
        or result.get("outcome") != expected["outcome"]
        or result.get("verdict") != expected["verdict"]
        or art != {"ledger_empty": True, "workspace_empty": True}
    ):
        raise ValueError(f"{name} result differs")
    findings = result.get("findings")
    if expected["outcome"] == "completed":
        expected_codes = [] if expected["code"] is None else [expected["code"]]
        if (
            result.get("infrastructure_failure_code") is not None
            or not isinstance(findings, list)
            or [item.get("code") for item in findings if isinstance(item, dict)]
            != expected_codes
            or len(findings) != len(expected_codes)
        ):
            raise ValueError(f"{name} completed result differs")
    elif (
        findings != [] or result.get("infrastructure_failure_code") != expected["code"]
    ):
        raise ValueError(f"{name} infrastructure result differs")
    return request_digest, result


def _launch_name(kind: str, attempt: str, occurrence: int) -> str:
    if kind == "reference":
        return f"ws-terminal-reference-{attempt}-{occurrence}"
    return f"ws-terminal-{kind}-{attempt}"


def reduce_matrix(raw: Path, head: str) -> dict[str, object]:
    interrupted = _json(raw / "interrupt.json")
    art_interrupted = _json(raw / "art-interrupt.json")
    restart = _json(raw / "restart-cleanup.json")
    launches = _ndjson(raw / "launches.ndjson")
    commands = _ndjson(raw / "command-results.ndjson")
    events = _ndjson(raw / "docker-events.ndjson")
    interrupt_digest = interrupted.get("request_digest")
    if (
        interrupted.get("adapter_failure") is not True
        or not isinstance(interrupt_digest, str)
        or art_interrupted != {"ledger_empty": True, "workspace_empty": True}
        or restart
        != {
            "owned_containers_absent": True,
            "owned_images_absent": True,
            "unowned_control_preserved": True,
        }
    ):
        raise ValueError("interruption evidence differs")

    results = {
        name: _validated_result(raw, name, expected) for name, expected in CASES.items()
    }
    request_digests = [interrupt_digest, *(digest for digest, _ in results.values())]
    if len(set(request_digests)) != 8:
        raise ValueError("request digests were not fresh")

    checker_launches = [item for item in launches if item.get("kind") == "checker"]
    terminal_launches = [item for item in launches if item.get("kind") != "checker"]
    if (
        len(launches) != 27
        or len(checker_launches) != 8
        or len(terminal_launches) != 19
        or any(
            item.get("mount_source_identities") != SOURCE_IDENTITIES["checker"]
            for item in checker_launches
        )
        or any(item.get("request_digest") is not None for item in checker_launches)
        or len({item.get("container_id") for item in launches}) != 27
        or len({item.get("name") for item in launches}) != 27
    ):
        raise ValueError("launch inventory differs")

    by_digest: dict[str, list[dict[str, object]]] = defaultdict(list)
    for launch in terminal_launches:
        kind = launch.get("kind")
        digest = launch.get("request_digest")
        if (
            kind not in {"builder", "candidate", "reference"}
            or digest not in request_digests
        ):
            raise ValueError("terminal launch identity differs")
        if launch.get("mount_source_identities") != SOURCE_IDENTITIES[str(kind)]:
            raise ValueError("launch source identity differs")
        by_digest[str(digest)].append(launch)

    expected_by_digest = {interrupt_digest: ("interrupted", ["builder"], [])}
    for name, expected in CASES.items():
        expected_by_digest[results[name][0]] = (
            name,
            expected["launches"],
            expected["starts"],
        )
    starts: dict[str, list[int]] = defaultdict(list)
    for command in commands:
        argv = command.get("argv")
        status = command.get("status")
        if not isinstance(argv, list) or not argv or argv[0] != "start":
            continue
        if len(argv) == 3 and argv[:2] == ["start", "--attach"]:
            name = argv[2]
        elif len(argv) == 4 and argv[:3] == ["start", "-a", "-i"]:
            name = argv[3]
        else:
            raise ValueError("container start shape differs")
        if type(name) is not str or type(status) is not int:
            raise ValueError("container start observation is invalid")
        starts[name].append(status)

    expected_starts: dict[str, list[int]] = {
        str(item["name"]): [0] for item in checker_launches
    }
    case_summary: dict[str, object] = {}
    for digest, (case, kinds, statuses) in expected_by_digest.items():
        items = by_digest.get(digest, [])
        if [item.get("kind") for item in items] != kinds:
            raise ValueError(f"{case} launch prefix differs")
        attempts = {item.get("attempt") for item in items}
        if len(attempts) > 1 or (items and not isinstance(next(iter(attempts)), str)):
            raise ValueError(f"{case} attempt differs")
        references = 0
        if len(items) != len(kinds) or len(statuses) > len(kinds):
            raise ValueError(f"{case} launch/start cardinality differs")
        for index, (item, kind) in enumerate(zip(items, kinds, strict=True)):
            attempt = str(item["attempt"])
            expected_name = _launch_name(str(kind), attempt, references)
            if kind == "reference":
                references += 1
            if item.get("name") != expected_name:
                raise ValueError(f"{case} container name differs")
            if index < len(statuses):
                expected_starts[expected_name] = [int(statuses[index])]
        case_summary[case] = {
            "launches": kinds,
            "request_digest": digest,
            "start_statuses": statuses,
        }
    expected_terminal_digests = {
        digest for digest, (_, kinds, _) in expected_by_digest.items() if kinds
    }
    if set(by_digest) != expected_terminal_digests:
        raise ValueError("unexpected terminal attempt")
    if dict(starts) != expected_starts:
        raise ValueError("container start observations differ")

    memory_digest = results["memory-capacity"][0]
    [memory_launch] = [
        item for item in by_digest[memory_digest] if item.get("kind") == "candidate"
    ]
    oom_events = []
    for event in events:
        actor = event.get("Actor")
        attributes = actor.get("Attributes") if isinstance(actor, dict) else None
        event_id = actor.get("ID") if isinstance(actor, dict) else event.get("id")
        if (
            event.get("Type") == "container"
            and event.get("Action") == "oom"
            and isinstance(attributes, dict)
            and attributes.get("workstream.request-digest") == memory_digest
            and attributes.get("workstream.resource-kind") == "candidate"
        ):
            oom_events.append(event_id)
    if oom_events != [memory_launch.get("container_id")]:
        raise ValueError("memory OOM event differs")

    return {
        "schema_version": SCHEMA,
        "head_sha": head,
        "interrupted": {
            "adapter_failure": True,
            "art_unwound": True,
            "restart_swept_owned": True,
            "unowned_control_preserved": True,
        },
        "cases": case_summary,
        "owned_resources_absent": True,
        "memory_oom_event": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    _write(arguments.output, reduce_matrix(arguments.raw, arguments.head))


if __name__ == "__main__":
    main()
