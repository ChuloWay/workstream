"""Harnessy proof checker logic and its published result contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from app.modules.checkers.api.external import (
    ExternalCheckerExecutionResult,
    ExternalCheckerRegistrySpec,
)

CHECKER_ROOT = Path(__file__).parents[4] / "external_checkers" / "harnessy_proof"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"harnessy_proof_{name}", CHECKER_ROOT / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load("checker")
publish_local = _load("publish_local")

VALID_PROOF = {
    "schema": "harnessy.work.proof.v1",
    "commit_sha": "0123456789abcdef0123456789abcdef01234567",
    "pr_url": "https://github.com/acme/widgets/pull/12",
    "ci_run_url": "https://github.com/acme/widgets/actions/runs/345",
    "ci_conclusion": "success",
    "merged": True,
}


def _encoded(**changes: object) -> bytes:
    proof = {**VALID_PROOF, **changes}
    return json.dumps({key: value for key, value in proof.items() if value is not ...}).encode()


def _request(phase: str = "post_submit") -> dict:
    return {
        "request_digest": "sha256:" + "b" * 64,
        "registry": {"registry_entry_id": str(uuid4()), "entry_digest": "sha256:" + "c" * 64},
        "identity": {"phase": phase},
    }


def _codes(raw: bytes | None) -> list[str]:
    return [item["code"] for item in checker.evaluate_proof(raw)]


def test_valid_proof_passes_with_backend_valid_result() -> None:
    assert checker.evaluate_proof(_encoded()) == []
    for phase in ("pre_submit", "post_submit"):
        request = _request(phase)
        result = checker.build_result(request, [])
        parsed = ExternalCheckerExecutionResult.model_validate_json(json.dumps(result))
        assert (parsed.verdict, parsed.findings, parsed.phase) == ("passed", (), phase)
        assert (
            parsed.request_digest,
            str(parsed.registry_entry_id),
            parsed.registry_entry_digest,
        ) == (
            request["request_digest"],
            request["registry"]["registry_entry_id"],
            request["registry"]["entry_digest"],
        )


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"schema": "harnessy.work.proof.v2"}, "schema"),
        ({"schema": ...}, "schema"),
        ({"commit_sha": "0123456789abcdef0123456789abcdef0123456"}, "commit_sha"),
        ({"commit_sha": "g123456789abcdef0123456789abcdef01234567"}, "commit_sha"),
        ({"commit_sha": 1234}, "commit_sha"),
        ({"pr_url": "http://github.com/acme/widgets/pull/12"}, "pr_url"),
        ({"pr_url": "https://github.com.evil.example/acme/pull/12"}, "pr_url"),
        ({"pr_url": "https://user@github.com/acme/widgets/pull/12"}, "pr_url"),
        ({"pr_url": "https://github.com:8443/acme/widgets/pull/12"}, "pr_url"),
        ({"ci_run_url": "https://github.com/"}, "ci_run_url"),
        ({"ci_run_url": "https://gitlab.com/acme/widgets/-/pipelines/1"}, "ci_run_url"),
        ({"ci_conclusion": "failure"}, "ci_conclusion"),
        ({"ci_conclusion": ...}, "ci_conclusion"),
        ({"merged": "true"}, "merged"),
        ({"merged": 1}, "merged"),
        ({"merged": False}, "merged"),
    ],
)
def test_each_invalid_claim_reports_exactly_its_error(changes: dict, code: str) -> None:
    assert _codes(_encoded(**changes)) == [f"harnessy.proof.{code}"]


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (None, "missing"),
        (b"{not json", "invalid_json"),
        (b"\xff\xfe", "invalid_json"),
        (b"[]", "invalid_json"),
        (b" " * (checker.MAX_PROOF_BYTES + 1), "too_large"),
    ],
)
def test_unreadable_proof_reports_one_error(raw: bytes | None, code: str) -> None:
    assert _codes(raw) == [f"harnessy.proof.{code}"]


def test_failed_verdict_exactly_when_an_error_finding_exists() -> None:
    findings = checker.evaluate_proof(_encoded(merged=False, ci_conclusion="cancelled"))
    parsed = ExternalCheckerExecutionResult.model_validate_json(
        json.dumps(checker.build_result(_request(), findings))
    )
    assert parsed.verdict == "failed"
    assert [item.path for item in parsed.findings] == ["proof.json", "proof.json"]
    info = [{**findings[0], "level": "info"}]
    assert checker.build_result(_request(), info)["verdict"] == "passed"


def test_read_proof_rejects_links_and_bounds_bytes(tmp_path: Path) -> None:
    assert checker.read_proof(tmp_path) is None
    target = tmp_path / "elsewhere.json"
    target.write_bytes(_encoded())
    (tmp_path / "proof.json").symlink_to(target)
    assert checker.read_proof(tmp_path) is None
    (tmp_path / "proof.json").unlink()
    (tmp_path / "proof.json").write_bytes(b"x" * (checker.MAX_PROOF_BYTES + 10))
    assert len(checker.read_proof(tmp_path)) == checker.MAX_PROOF_BYTES + 1


def test_published_registry_bodies_are_backend_valid_for_both_phases() -> None:
    digest = "sha256:" + "d" * 64
    for phase in ("pre_submit", "post_submit"):
        spec = ExternalCheckerRegistrySpec.model_validate(
            publish_local.registry_spec(phase, digest, "v2")
        )
        assert (spec.phase, spec.image_digest, spec.capability_id, spec.capability_version) == (
            phase,
            digest,
            "harnessy.work_proof",
            "v2",
        )
    for registry in ("localhost:5000@registry.example", "localhost", "registry.example:5000"):
        with pytest.raises(SystemExit):
            publish_local.publish(registry, "harnessy-proof")


def test_published_service_paths_match_the_compose_overlay() -> None:
    """The service config and the overlay must name the same daemon and socket paths."""
    overlay = yaml.safe_load(
        (CHECKER_ROOT.parents[1] / "docker-compose.agent-loop.yml").read_text()
    )
    environment = overlay["x-agent-loop-backend"]["environment"]
    config = publish_local.service_config(
        {"operating_system": "linux", "architecture": "arm64"},
        compose_project="${COMPOSE_PROJECT_NAME}",
        sandbox_uid=501,
        sandbox_gid=20,
    )
    assert config["material_root"] == environment["WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT"]
    assert config["material_root"] == environment["WORKSTREAM_ARTIFACT_SCRATCH_ROOT"]
    assert config["socket_path"] == environment["WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET"]
    assert len(config["socket_path"].encode()) <= 107
    for name in ("backend", "worker", "beat", "checker", "checker-volumes-init"):
        socket_mounts = [
            mount
            for mount in overlay["services"][name]["volumes"]
            if (mount.split(":")[1] if isinstance(mount, str) else mount["target"])
            == "/run/ws-checker"
        ]
        mode = ":ro" if name in ("backend", "worker", "beat") else ""
        assert socket_mounts == [f"checker_socket:/run/ws-checker{mode}"], name
