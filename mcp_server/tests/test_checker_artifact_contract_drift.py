from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import pytest

from workstream_mcp.http_gateway import CHECKER_ARTIFACT_OPERATIONS
from workstream_mcp.schemas import CHECKER_ARTIFACT_CONTRACT_NAMES

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "mcp_server" / "contracts"
BACKEND = ROOT / "backend"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _selected(openapi: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    operation = openapi["paths"][path][method.lower()]
    names: set[str] = set()
    pending: list[Any] = [operation]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str) and reference.startswith("#/components/schemas/"):
                name = reference.rsplit("/", 1)[-1]
                if name not in names:
                    names.add(name)
                    pending.append(openapi["components"]["schemas"][name])
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return {
        "operation": operation,
        "components": {
            "schemas": {name: openapi["components"]["schemas"][name] for name in sorted(names)}
        },
    }


@pytest.mark.parametrize("name", CHECKER_ARTIFACT_CONTRACT_NAMES)
def test_checker_artifact_contract_is_tamper_evident_and_matches_fixed_route(name: str) -> None:
    snapshot = json.loads((CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))
    captured = {"operation": snapshot["operation"], "components": snapshot["components"]}
    method, path, _ = CHECKER_ARTIFACT_OPERATIONS[name]
    assert snapshot["schema_version"] == 1
    assert snapshot["source"]["method"] == method
    assert snapshot["source"]["path"] == path
    assert hashlib.sha256(_canonical(captured)).hexdigest() == snapshot["canonical_sha256"]


def test_exact_checker_artifact_contract_set_is_reviewed() -> None:
    present = {
        path.stem
        for pattern in (
            "artifact_*.json",
            "checker_*.json",
            "post_submit_*.json",
            "project_checker_*.json",
            "submission_checker_*.json",
        )
        for path in CONTRACTS.glob(pattern)
    }
    assert len(CHECKER_ARTIFACT_CONTRACT_NAMES) == 19
    assert present == set(CHECKER_ARTIFACT_CONTRACT_NAMES)
    assert set(CHECKER_ARTIFACT_CONTRACT_NAMES) == set(CHECKER_ARTIFACT_OPERATIONS)


def test_checker_artifact_contracts_match_backend_openapi_when_configured() -> None:
    command = os.environ.get("WORKSTREAM_MCP_OPENAPI_COMMAND")
    if command is None:
        pytest.skip("backend OpenAPI comparison is run in the isolated backend environment")
    completed = subprocess.run(  # noqa: S603 - configured local contract probe
        shlex.split(command),
        cwd=BACKEND,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    openapi = json.loads(completed.stdout)
    for name, (method, path, _) in CHECKER_ARTIFACT_OPERATIONS.items():
        snapshot = json.loads((CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))
        assert snapshot["source"]["openapi_version"] == openapi["openapi"]
        assert {
            "operation": snapshot["operation"],
            "components": snapshot["components"],
        } == _selected(openapi, path, method)
