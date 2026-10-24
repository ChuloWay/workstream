"""Harnessy proof checker logic and its published result contract."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from app.modules.checkers.api.external import (
    ExternalCheckerContractError,
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


# GitHub comparison mode -------------------------------------------------------

CONFIGURATION = {"github_repository": "acme/widgets", "base_branch": "main"}
FACTS = {
    "schema_version": "workstream.github_facts.v1",
    "repository": "acme/widgets",
    "pull_request_number": 12,
    "state": "closed",
    "merged": True,
    "merge_commit_sha": VALID_PROOF["commit_sha"],
    "base_ref": "main",
    "head_sha": "e" * 40,
    "required_checks": [
        {"name": "backend", "app_id": 15368, "conclusion": "success"},
        {"name": "lint", "app_id": None, "conclusion": "success"},
    ],
    "fetched_at": "2026-10-24T12:00:00Z",
    "responses": [{"request": "pull_request", "sha256": "sha256:" + "f" * 64}],
}


def _input(**changes: object) -> dict:
    facts = {**FACTS, **changes}
    return {
        "schema_version": "workstream.external_checker_post_submit_input.v1",
        "github_facts": {key: value for key, value in facts.items() if value is not ...},
    }


def _compare(
    proof: bytes | None = None,
    *,
    configuration: object = CONFIGURATION,
    input_value: object = None,
) -> list[str]:
    findings = checker.evaluate_proof(
        _encoded() if proof is None else proof,
        configuration=configuration,
        input_value=_input() if input_value is None else input_value,
    )
    return [item["code"] for item in findings]


def test_proof_matching_github_facts_passes() -> None:
    assert _compare() == []
    upper = VALID_PROOF["commit_sha"].upper()
    pr_url = "https://github.com/Acme/Widgets/pull/12/"
    assert _compare(_encoded(commit_sha=upper, pr_url=pr_url)) == []


@pytest.mark.parametrize(
    ("proof_changes", "fact_changes", "code"),
    [
        (
            {"pr_url": "https://github.com/acme/other/pull/12"},
            {"repository": "acme/other"},
            "github.repository",
        ),
        ({"pr_url": "https://github.com/acme/other/pull/12"}, {}, "github.pr_repository"),
        (
            {"pr_url": "https://github.com/acme/widgets/pull/13"},
            {},
            "github.pull_request_number",
        ),
        ({"pr_url": "https://github.com/acme/widgets/issues/12"}, {}, "github.pr_url"),
        ({}, {"merged": False, "state": "open"}, "github.merged"),
        ({"commit_sha": "1" * 40}, {}, "github.merge_commit_sha"),
        ({}, {"base_ref": "release"}, "github.base_branch"),
    ],
)
def test_each_github_mismatch_reports_exactly_its_finding(
    proof_changes: dict, fact_changes: dict, code: str
) -> None:
    assert _compare(_encoded(**proof_changes), input_value=_input(**fact_changes)) == [
        f"harnessy.proof.{code}"
    ]


def test_unmerged_facts_also_fail_the_merge_commit_comparison() -> None:
    codes = _compare(input_value=_input(merged=False, merge_commit_sha=None))
    assert codes == ["harnessy.proof.github.merged", "harnessy.proof.github.merge_commit_sha"]


def test_each_unsuccessful_required_check_reports_its_own_finding() -> None:
    checks = [
        {"name": "backend", "app_id": 15368, "conclusion": "failure"},
        {"name": "lint", "app_id": None, "conclusion": "success"},
        {"name": "docs", "app_id": None, "conclusion": "missing"},
        {"name": "e2e\nspoof", "app_id": None, "conclusion": "pending"},
    ]
    findings = checker.evaluate_proof(
        _encoded(), configuration=CONFIGURATION, input_value=_input(required_checks=checks)
    )
    assert [item["code"] for item in findings] == ["harnessy.proof.github.required_check"] * 3
    messages = [item["message"] for item in findings]
    assert "backend is failure" in messages[0]
    assert "docs is missing" in messages[1]
    assert "e2e?spoof is pending" in messages[2]


@pytest.mark.parametrize(
    "input_value",
    [{}, {"schema_version": "workstream.external_checker_post_submit_input.v1"}, None],
)
def test_required_facts_missing_is_an_error_never_a_pass(input_value: object) -> None:
    findings = checker.evaluate_proof(
        _encoded(), configuration=CONFIGURATION, input_value=input_value
    )
    assert [item["code"] for item in findings] == ["harnessy.proof.github.facts_missing"]


@pytest.mark.parametrize(
    "facts_changes",
    [
        {"schema_version": "workstream.github_facts.v2"},
        {"merged": "true"},
        {"pull_request_number": "12"},
        {"required_checks": []},
        {"required_checks": [{"name": "backend"}]},
        {"merge_commit_sha": "ABC"},
        {"head_sha": ...},
    ],
)
def test_malformed_facts_are_an_error(facts_changes: dict) -> None:
    assert _compare(input_value=_input(**facts_changes)) == [
        "harnessy.proof.github.facts_invalid"
    ]


@pytest.mark.parametrize(
    "configuration",
    [
        {"github_repository": "acme/widgets"},
        {"base_branch": "main"},
        {**CONFIGURATION, "extra": True},
        {"github_repository": "", "base_branch": "main"},
    ],
)
def test_incomplete_configuration_is_an_error(configuration: dict) -> None:
    assert _compare(configuration=configuration) == ["harnessy.proof.github.configuration"]


def test_shape_mode_is_unchanged_without_configuration_or_facts() -> None:
    assert checker.evaluate_proof(_encoded(), configuration={}, input_value={}) == []
    assert checker.evaluate_proof(_encoded(merged=False)) == [
        checker._finding("merged", "merged must be the JSON value true.")
    ]


def test_unconfigured_facts_are_still_compared() -> None:
    codes = _compare(configuration={}, input_value=_input(base_ref="other", merged=False))
    assert codes == ["harnessy.proof.github.merged"]


def test_shape_errors_and_github_mismatches_are_both_reported() -> None:
    codes = _compare(_encoded(ci_conclusion="failure"), input_value=_input(merged=False))
    assert codes == ["harnessy.proof.ci_conclusion", "harnessy.proof.github.merged"]


def test_comparison_failure_produces_a_backend_valid_failed_result() -> None:
    findings = checker.evaluate_proof(
        _encoded(), configuration=CONFIGURATION, input_value=_input(base_ref="dev")
    )
    parsed = ExternalCheckerExecutionResult.model_validate_json(
        json.dumps(checker.build_result(_request(), findings))
    )
    assert parsed.verdict == "failed"
    assert [item.code for item in parsed.findings] == ["harnessy.proof.github.base_branch"]


def test_main_passes_request_configuration_and_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    request = {**_request(), "configuration": CONFIGURATION, "input": _input(merged=False)}
    monkeypatch.setattr(checker, "read_proof", lambda _root: _encoded())
    monkeypatch.setattr(checker.sys, "stdin", io.StringIO(json.dumps(request)))
    assert checker.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "failed"
    assert [item["code"] for item in result["findings"]] == ["harnessy.proof.github.merged"]


def test_registry_schemas_accept_only_supported_configuration_and_facts_input() -> None:
    digest = "sha256:" + "d" * 64
    post = ExternalCheckerRegistrySpec.model_validate(
        publish_local.registry_spec("post_submit", digest, "v2")
    )
    pre = ExternalCheckerRegistrySpec.model_validate(
        publish_local.registry_spec("pre_submit", digest, "v2")
    )
    post.configuration_schema.validate_instance({})
    post.configuration_schema.validate_instance(CONFIGURATION)
    post.input_schema.validate_instance(_input())
    post.input_schema.validate_instance(
        {"schema_version": "workstream.external_checker_post_submit_input.v1"}
    )
    pre.configuration_schema.validate_instance({})
    rejected = [
        (post.configuration_schema, {"github_repository": "acme/widgets"}),
        (post.configuration_schema, {"base_branch": "main"}),
        (post.configuration_schema, {**CONFIGURATION, "github_repository": "acme"}),
        (post.configuration_schema, {**CONFIGURATION, "extra": 1}),
        (pre.configuration_schema, CONFIGURATION),
        (post.input_schema, _input(schema_version="workstream.github_facts.v2")),
    ]
    for schema, value in rejected:
        with pytest.raises(ExternalCheckerContractError):
            schema.validate_instance(value)
