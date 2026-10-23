"""Configured proxy startup and provider ownership boundaries."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import signal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.adapters.checkers import model_runtime
from app.core.config import Settings
from app.modules.checkers.api.model_calls import ModelCallUnavailable
from app.workers import checker_model_proxy
from tests.artifact_store_helpers import artifact_admission_limit_settings
from tests.checkers_model_calls.test_proxy_orchestration import Harness


async def test_disabled_proxy_needs_no_database_storage_or_provider(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("disabled model proxy constructed a runtime")

    monkeypatch.setattr(model_runtime, "create_artifact_store_bootstrap", forbidden)
    async with model_runtime.configured_model_proxy_runtime(
        SimpleNamespace(checker_model_proxy_socket=None),
        None,
    ):
        pass


def test_proxy_requires_absolute_socket_and_enabled_storage(tmp_path):
    assert (
        Settings(checker_model_proxy_socket="", _env_file=None).checker_model_proxy_socket is None
    )
    with pytest.raises(ValidationError, match="must be absolute"):
        Settings(checker_model_proxy_socket=Path("relative.sock"), _env_file=None)
    with pytest.raises(ValidationError, match="requires enabled artifact"):
        Settings(checker_model_proxy_socket=tmp_path / "proxy.sock", _env_file=None)
    settings = Settings(
        environment="test",
        artifact_store_backend="local",
        artifact_local_root=tmp_path / "objects",
        artifact_scratch_root=tmp_path / "scratch",
        checker_model_proxy_socket=tmp_path / "sockets/proxy.sock",
        **artifact_admission_limit_settings(),
        _env_file=None,
    )
    assert settings.checker_model_proxy_socket == tmp_path / "sockets/proxy.sock"


async def test_provider_uses_profile_bounds_and_closes_owned_client(monkeypatch):
    profile = Harness().profile
    captured = []
    closed = []

    async def close():
        closed.append(True)

    def construct(settings):
        captured.append(settings)
        return SimpleNamespace(aclose=close)

    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    monkeypatch.setattr(model_runtime, "create_checker_model_provider", construct)
    async with model_runtime.configured_model_provider(profile):
        assert len(captured) == 1
        settings = captured[0]
        assert settings.model == profile.spec.model_snapshot
        assert settings.maximum_input_tokens == profile.spec.maximum_input_tokens
        assert settings.maximum_output_tokens == profile.spec.maximum_output_tokens
        assert settings.reasoning_effort == profile.spec.settings.reasoning_effort
        assert "private-test-key" not in repr(settings)
    assert closed == [True]


async def test_missing_provider_key_stops_before_reserving_budget(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    h = Harness()
    h.provider = model_runtime.configured_model_provider
    assert (await h.invoke()).outcome == "unavailable"
    assert h.state == "prepared"
    assert "dispatch_committed" not in h.events
    with pytest.raises(ModelCallUnavailable):
        async with model_runtime.configured_model_provider(h.profile):
            pass


async def test_singleton_worker_drains_before_engine_disposal(monkeypatch):
    """SIGTERM stops admission and awaits the owned runtime before DB disposal."""
    calls = []
    settings = SimpleNamespace(checker_model_proxy_socket=Path("/private/model.sock"))
    sessions = object()
    real_loop = asyncio.get_running_loop()

    class SignalLoop:
        def add_signal_handler(self, signum, callback):
            calls.append(("add_signal", signum))
            if signum == signal.SIGTERM:
                real_loop.call_soon(callback)

        def remove_signal_handler(self, signum):
            calls.append(("remove_signal", signum))
            return True

    @asynccontextmanager
    async def runtime(received_settings, received_sessions):
        assert received_settings is settings
        assert received_sessions is sessions
        calls.append("runtime_started")
        try:
            yield
        finally:
            calls.append("runtime_drained")

    async def dispose():
        calls.append("engine_disposed")

    monkeypatch.setattr(checker_model_proxy, "get_settings", lambda: settings)
    monkeypatch.setattr(checker_model_proxy, "get_session_factory", lambda: sessions)
    monkeypatch.setattr(checker_model_proxy, "configured_model_proxy_runtime", runtime)
    monkeypatch.setattr(checker_model_proxy, "dispose_engine", dispose)
    monkeypatch.setattr(checker_model_proxy.asyncio, "get_running_loop", SignalLoop)

    await checker_model_proxy.serve()

    assert calls == [
        ("add_signal", signal.SIGINT),
        ("add_signal", signal.SIGTERM),
        "runtime_started",
        "runtime_drained",
        ("remove_signal", signal.SIGINT),
        ("remove_signal", signal.SIGTERM),
        "engine_disposed",
    ]
