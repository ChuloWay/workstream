"""Executable-boundary tests for the native AWS artifact proof command."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.adapters.artifacts.aws_live_proof import AwsArtifactProbeObservation
from app.core.config import Settings
from scripts import aws_artifact_provider_proof as command


_GROUP_NONCE = UUID("0199f68b-5dc2-7000-8000-000000000002")
_RESULT_ID = UUID("0199f68b-5dc2-7000-8000-000000000003")
_ACTIVATION_ID = UUID("0199f68b-5dc2-7000-8000-000000000004")
_STARTED_AT = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
_RUNTIME_ROLE = "arn:aws:iam::123456789012:role/workstream-runtime"
_READINESS_ROLE = "arn:aws:iam::123456789012:role/workstream-readiness"
_NEGATIVE_ROLE = "arn:aws:iam::123456789012:role/workstream-negative"


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class _DatabaseSession:
    def __init__(self, number: int, events: list[object]) -> None:
        self.number = number
        self.events = events

    async def __aenter__(self) -> _DatabaseSession:
        self.events.append(("session-enter", self.number))
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.events.append(("session-exit", self.number))

    def begin(self) -> _Transaction:
        self.events.append(("transaction", self.number))
        return _Transaction()


class _SessionFactory:
    def __init__(self, events: list[object]) -> None:
        self.events = events
        self.count = 0

    def __call__(self) -> _DatabaseSession:
        self.count += 1
        return _DatabaseSession(self.count, self.events)


def _stub_probe_persistence(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    *,
    persisted: list[dict[str, object]],
) -> None:
    sessions = _SessionFactory([])

    async def database_time(_session: _DatabaseSession) -> datetime:
        return _STARTED_AT

    async def record(
        _session: _DatabaseSession,
        actual_settings: Settings,
        **values: object,
    ) -> UUID:
        assert actual_settings is settings
        persisted.append(values)
        return _RESULT_ID

    async def dispose() -> None:
        return None

    monkeypatch.setattr(command, "get_settings", lambda: settings)
    monkeypatch.setattr(command, "get_session_factory", lambda: sessions)
    monkeypatch.setattr(command, "artifact_provider_database_time", database_time)
    monkeypatch.setattr(command, "record_artifact_provider_probe_result", record)
    monkeypatch.setattr(command, "dispose_engine", dispose)


@pytest.mark.asyncio
async def test_probe_run_executes_transport_then_persists_its_actual_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    settings = SimpleNamespace(name="bounded-settings")
    sessions = _SessionFactory(events)
    observation = AwsArtifactProbeObservation(
        probe_type="runtime_immutability",
        expected_principal_arn=_RUNTIME_ROLE,
        observed_principal_arn=_RUNTIME_ROLE,
        passed=True,
        error_code=None,
        evidence={"suite": "aws-s3-identity-custody", "exact_readback": True},
    )

    class _Proof:
        def __init__(self, actual_settings: object) -> None:
            assert actual_settings is settings
            events.append("proof-constructed")

        async def run(self, mode: str, *, group_nonce: UUID) -> AwsArtifactProbeObservation:
            assert mode == "runtime_immutability"
            assert group_nonce == _GROUP_NONCE
            events.append("proof-run")
            return observation

    async def database_time(session: _DatabaseSession) -> datetime:
        assert session.number == 1
        events.append("database-time")
        return _STARTED_AT

    async def record(
        session: _DatabaseSession,
        actual_settings: object,
        **values: object,
    ) -> UUID:
        assert session.number == 2
        assert actual_settings is settings
        assert values == {
            "probe_type": observation.probe_type,
            "namespace_fingerprint": "sha256:" + "a" * 64,
            "group_nonce": _GROUP_NONCE,
            "expected_principal_arn": _RUNTIME_ROLE,
            "observed_principal_arn": _RUNTIME_ROLE,
            "passed": True,
            "evidence": observation.evidence,
            "error_code": None,
            "started_at": _STARTED_AT,
        }
        events.append("record")
        return _RESULT_ID

    async def dispose() -> None:
        events.append("dispose")

    monkeypatch.setattr(command, "get_settings", lambda: settings)
    monkeypatch.setattr(
        command,
        "aws_s3_namespace_fingerprint",
        lambda actual: "sha256:" + "a" * 64 if actual is settings else "wrong",
    )
    monkeypatch.setattr(command, "get_session_factory", lambda: sessions)
    monkeypatch.setattr(command, "AwsArtifactLiveProof", _Proof)
    monkeypatch.setattr(command, "artifact_provider_database_time", database_time)
    monkeypatch.setattr(command, "record_artifact_provider_probe_result", record)
    monkeypatch.setattr(command, "dispose_engine", dispose)

    result = await command.run("runtime_immutability", _GROUP_NONCE)

    assert result == {
        "result": "passed",
        "probe_type": "runtime_immutability",
        "probe_result_id": str(_RESULT_ID),
        "group_nonce": str(_GROUP_NONCE),
        "error_code": None,
    }
    assert events == [
        ("session-enter", 1),
        ("transaction", 1),
        "database-time",
        ("session-exit", 1),
        "proof-constructed",
        "proof-run",
        ("session-enter", 2),
        ("transaction", 2),
        "record",
        ("session-exit", 2),
        "dispose",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "role_arn"),
    [
        ("readiness", _READINESS_ROLE),
        ("runtime_immutability", _RUNTIME_ROLE),
        ("negative_access", _NEGATIVE_ROLE),
    ],
)
async def test_roles_anywhere_command_constructs_the_exact_selected_proof_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
    role_arn: str,
) -> None:
    from app.adapters.artifacts import aws_live_proof, aws_roles_anywhere
    from tests.test_aws_roles_anywhere_credentials import (
        make_roles_anywhere_settings,
        write_roles_anywhere_identity,
    )

    certificate_path, private_key_path = write_roles_anywhere_identity(
        tmp_path / role_arn.rsplit("/", 1)[-1],
        role_arn=role_arn,
    )
    settings = make_roles_anywhere_settings(
        tmp_path,
        selected_role_arn=role_arn,
        identity_paths=(certificate_path, private_key_path),
    )
    persisted: list[dict[str, object]] = []
    _stub_probe_persistence(monkeypatch, settings, persisted=persisted)
    monkeypatch.setenv("HOME", str(tmp_path))

    async def observe(proof: object, expected: str) -> str:
        session = proof._session  # type: ignore[attr-defined]  # noqa: SLF001
        assert session is not None
        providers = session.get_component("credential_provider").providers
        assert len(providers) == 1
        provider = providers[0]
        assert type(provider) is aws_roles_anywhere.RolesAnywhereCredentialProvider
        assert provider._role_arn == role_arn  # noqa: SLF001
        assert provider._settings.artifact_s3_roles_anywhere_certificate_file == certificate_path  # noqa: SLF001
        assert provider._settings.artifact_s3_roles_anywhere_private_key_file == private_key_path  # noqa: SLF001
        return expected

    async def cloud_probe(*_args: object) -> dict[str, object]:
        return {"stubbed_cloud_transport": True}

    async def isolate(_settings: Settings) -> object:
        return SimpleNamespace(
            initial_own_role_succeeded=True,
            other_roles_access_denied=True,
            final_own_role_succeeded=True,
        )

    monkeypatch.setattr(aws_live_proof.AwsArtifactLiveProof, "_observe_principal", observe)
    monkeypatch.setattr(aws_live_proof.AwsArtifactLiveProof, "_readiness", cloud_probe)
    monkeypatch.setattr(
        aws_live_proof.AwsArtifactLiveProof,
        "_runtime_immutability",
        cloud_probe,
    )
    monkeypatch.setattr(aws_live_proof.AwsArtifactLiveProof, "_negative_access", cloud_probe)
    monkeypatch.setattr(aws_roles_anywhere, "prove_roles_anywhere_role_isolation", isolate)

    result = await command.run(mode, _GROUP_NONCE)

    assert result["result"] == "passed"
    assert persisted[0]["expected_principal_arn"] == role_arn
    assert persisted[0]["observed_principal_arn"] == role_arn
    assert persisted[0]["passed"] is True


@pytest.mark.asyncio
async def test_roles_anywhere_command_rejects_wrong_mode_before_credential_or_cloud_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.adapters.artifacts import aws_live_proof
    from tests.test_aws_roles_anywhere_credentials import (
        make_roles_anywhere_settings,
        write_roles_anywhere_identity,
    )

    identity = write_roles_anywhere_identity(
        tmp_path / "readiness",
        role_arn=_READINESS_ROLE,
    )
    settings = make_roles_anywhere_settings(
        tmp_path,
        selected_role_arn=_READINESS_ROLE,
        identity_paths=identity,
    )
    persisted: list[dict[str, object]] = []
    _stub_probe_persistence(monkeypatch, settings, persisted=persisted)
    unsafe_events: list[str] = []

    def forbidden_session(*_args: object, **_kwargs: object) -> object:
        unsafe_events.append("credential-session")
        raise AssertionError("wrong mode constructed a credential session")

    async def forbidden_cloud(*_args: object, **_kwargs: object) -> object:
        unsafe_events.append("cloud")
        raise AssertionError("wrong mode called AWS")

    monkeypatch.setattr(
        aws_live_proof,
        "create_isolated_aws_workload_identity_session",
        forbidden_session,
    )
    monkeypatch.setattr(
        aws_live_proof.AwsArtifactLiveProof,
        "_observe_principal",
        forbidden_cloud,
    )

    result = await command.run("runtime_immutability", _GROUP_NONCE)

    assert result["result"] == "failed"
    assert result["error_code"] == "proof_validation_failed"
    assert persisted[0]["expected_principal_arn"] == _RUNTIME_ROLE
    assert persisted[0]["observed_principal_arn"] is None
    assert persisted[0]["passed"] is False
    assert unsafe_events == []


@pytest.mark.asyncio
async def test_coordinate_run_uses_only_the_credential_free_database_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    settings = SimpleNamespace(name="bounded-settings")
    sessions = _SessionFactory(events)

    async def coordinate(
        session: _DatabaseSession,
        actual_settings: object,
        **values: object,
    ) -> UUID:
        assert session.number == 1
        assert actual_settings is settings
        assert values == {
            "namespace_fingerprint": "sha256:" + "b" * 64,
            "group_nonce": _GROUP_NONCE,
        }
        events.append("coordinate")
        return _ACTIVATION_ID

    async def dispose() -> None:
        events.append("dispose")

    def forbidden_proof(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("coordinate constructed an AWS transport")

    monkeypatch.setattr(command, "get_settings", lambda: settings)
    monkeypatch.setattr(command, "aws_s3_namespace_fingerprint", lambda _: "sha256:" + "b" * 64)
    monkeypatch.setattr(command, "get_session_factory", lambda: sessions)
    monkeypatch.setattr(command, "AwsArtifactLiveProof", forbidden_proof)
    monkeypatch.setattr(command, "coordinate_artifact_provider_activation", coordinate)
    monkeypatch.setattr(command, "dispose_engine", dispose)

    result = await command.run("coordinate", _GROUP_NONCE)

    assert result == {
        "result": "activated",
        "activation_id": str(_ACTIVATION_ID),
        "group_nonce": str(_GROUP_NONCE),
    }
    assert events == [
        ("session-enter", 1),
        ("transaction", 1),
        "coordinate",
        ("session-exit", 1),
        "dispose",
    ]


@pytest.mark.parametrize(
    ("mode", "result", "expected_exit"),
    [
        (
            "readiness",
            {
                "result": "passed",
                "probe_type": "readiness",
                "probe_result_id": str(_RESULT_ID),
                "group_nonce": str(_GROUP_NONCE),
                "error_code": None,
            },
            0,
        ),
        (
            "coordinate",
            {
                "result": "activated",
                "activation_id": str(_ACTIVATION_ID),
                "group_nonce": str(_GROUP_NONCE),
            },
            0,
        ),
        (
            "negative_access",
            {
                "result": "failed",
                "probe_type": "negative_access",
                "probe_result_id": str(_RESULT_ID),
                "group_nonce": str(_GROUP_NONCE),
                "error_code": "AccessDenied",
            },
            2,
        ),
    ],
    ids=["probe-passed", "coordinate-activated", "probe-failed"],
)
def test_main_parses_real_cli_boundary_and_returns_closed_result_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    result: dict[str, object],
    expected_exit: int,
) -> None:
    calls: list[tuple[str, UUID]] = []

    async def run(actual_mode: str, nonce: UUID) -> dict[str, object]:
        calls.append((actual_mode, nonce))
        return result

    monkeypatch.setattr(command, "run", run)
    monkeypatch.setattr(
        command.sys,
        "argv",
        ["aws-artifact-provider-proof", mode, "--group-nonce", str(_GROUP_NONCE)],
    )

    assert command.main() == expected_exit

    captured = capsys.readouterr()
    assert json.loads(captured.out) == result
    assert captured.err == ""
    assert calls == [(mode, _GROUP_NONCE)]


def test_main_sanitizes_transport_and_cleanup_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_value = "private-session-token-should-never-be-rendered"

    async def failed_run(_mode: str, _nonce: UUID) -> dict[str, object]:
        raise RuntimeError(f"provider response contained {private_value}")

    monkeypatch.setattr(command, "run", failed_run)
    monkeypatch.setattr(
        command.sys,
        "argv",
        [
            "aws-artifact-provider-proof",
            "runtime_immutability",
            "--group-nonce",
            str(_GROUP_NONCE),
        ],
    )

    assert command.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "result": "infrastructure_failure",
        "error_code": "proof_command_failed",
    }
    assert private_value not in captured.err
