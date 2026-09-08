"""Local command privacy and outcome handling, not database bootstrap proof."""

import json
from uuid import UUID, uuid4

import pytest

from scripts import bootstrap_access_administrator as command


def test_bootstrap_command_manifest_matches_the_active_catalogue() -> None:
    manifest = command.BOOTSTRAP_COMMAND_MANIFEST
    assert manifest.action_id.value == "admin_role_grant.bootstrap"
    assert manifest.permission_id.value == "admin_role.grant"
    assert manifest.principal == "workstream:system:bootstrap"


def test_bootstrap_cli_preserves_committed_outcome_when_engine_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    actor_id, grant_id = uuid4(), uuid4()
    outcome = {
        "result_code": "bootstrapped",
        "actor_profile_id": str(actor_id),
        "grant_id": str(grant_id),
        "changed": True,
    }
    calls = []

    async def successful_run(selected_actor: UUID, *, execute: bool):
        assert selected_actor == actor_id
        assert execute is True
        calls.append("run")
        return 0, outcome

    async def failed_cleanup() -> None:
        calls.append("cleanup")
        raise RuntimeError("private cleanup failure")

    monkeypatch.setattr(command, "_run", successful_run)
    monkeypatch.setattr(command, "dispose_engine", failed_cleanup)
    assert command.main(["--actor-profile-id", str(actor_id), "--execute"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == outcome
    assert captured.err == ""
    assert calls == ["run", "cleanup"]


def test_bootstrap_cli_does_not_relabel_internal_type_error_as_invalid_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    actor_id = uuid4()
    calls = []

    async def broken_run(selected_actor: UUID, *, execute: bool):
        assert selected_actor == actor_id
        assert execute is True
        calls.append("run")
        raise TypeError("private internal contract failure")

    async def clean_disposal() -> None:
        calls.append("cleanup")

    monkeypatch.setattr(command, "_run", broken_run)
    monkeypatch.setattr(command, "dispose_engine", clean_disposal)
    assert command.main(["--actor-profile-id", str(actor_id), "--execute"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"result_code": "infrastructure_failure"}
    assert captured.err == ""
    assert calls == ["run", "cleanup"]


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="missing-required-arguments"),
        pytest.param(
            ["--actor-profile-id", "private-not-a-uuid", "--execute"], id="invalid-uuid"
        ),
        pytest.param(
            ["--actor-profile-id", str(uuid4()), "--dry-run", "--execute"],
            id="mutually-exclusive-modes",
        ),
    ],
)
def test_bootstrap_cli_rejects_arguments_without_echoing_them(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = []

    async def forbidden_run(*args, **kwargs):
        calls.append("forbidden_run")
        raise AssertionError("malformed arguments entered execution")

    async def clean_disposal() -> None:
        calls.append("cleanup")

    monkeypatch.setattr(command, "_run", forbidden_run)
    monkeypatch.setattr(command, "dispose_engine", clean_disposal)
    assert command.main(argv) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"result_code": "invalid_request"}
    assert captured.err == ""
    assert calls == ["cleanup"]


def test_bootstrap_cli_reports_interrupt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = []

    def interrupted_then_clean(coroutine):
        calls.append(coroutine.cr_code.co_name)
        coroutine.close()
        if len(calls) == 1:
            raise KeyboardInterrupt

    monkeypatch.setattr(command.asyncio, "run", interrupted_then_clean)
    assert command.main(["--actor-profile-id", str(uuid4()), "--execute"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"result_code": "interrupted"}
    assert captured.err == ""
    assert calls == ["_run", "dispose_engine"]


def test_bootstrap_cli_reports_pre_outcome_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = []

    def failed_before_and_during_cleanup(coroutine):
        calls.append(coroutine.cr_code.co_name)
        coroutine.close()
        raise RuntimeError("private infrastructure failure")

    monkeypatch.setattr(command.asyncio, "run", failed_before_and_during_cleanup)
    assert command.main(["--actor-profile-id", str(uuid4()), "--execute"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"result_code": "infrastructure_failure"}
    assert captured.err == ""
    assert calls == ["_run", "dispose_engine"]
