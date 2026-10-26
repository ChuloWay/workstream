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
from app.modules.model_usage.api import ModelCallUnavailable
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


@pytest.mark.parametrize(
    ("provider_name", "api", "model", "credential", "other_credential"),
    [
        ("openai_responses", "responses.v1", "gpt-5.6-terra", "OPENAI_API_KEY", "OPENROUTER_API_KEY"),
        ("openrouter", "chat_completions", "openai/gpt-5.6-terra", "OPENROUTER_API_KEY", "OPENAI_API_KEY"),
    ],
)
async def test_provider_uses_exact_profile_and_only_selected_key(
    monkeypatch, provider_name, api, model, credential, other_credential
):
    profile = Harness().profile
    profile = profile.model_copy(update={"spec": profile.spec.model_copy(update={
        "provider": provider_name, "api": api, "model_snapshot": model,
    })})
    captured = []
    closed = []

    async def close():
        closed.append(True)

    def construct(received_profile, *, api_key):
        captured.append((received_profile, api_key))
        return SimpleNamespace(aclose=close)

    monkeypatch.delenv(other_credential, raising=False)
    monkeypatch.setenv(credential, "private-test-key")
    monkeypatch.setattr(model_runtime, "create_checker_model_provider", construct)
    async with model_runtime.configured_model_provider(profile):
        assert captured == [(profile, "private-test-key")]
    assert closed == [True]


@pytest.mark.parametrize("provider_name,api", [
    ("unknown", "chat_completions"), ("openrouter", "responses.v1"),
    ("openai_responses", "chat_completions"),
])
async def test_unsupported_pair_denies_before_credential_or_client_access(
    monkeypatch, provider_name, api
):
    profile = Harness().profile
    profile = profile.model_copy(update={"spec": profile.spec.model_copy(update={
        "provider": provider_name, "api": api,
    })})

    class NoCredentials:
        def get(self, *_args):
            raise AssertionError("unsupported profile accessed credentials")

    monkeypatch.setattr(model_runtime, "os", SimpleNamespace(environ=NoCredentials()))
    with pytest.raises(ModelCallUnavailable, match="model_profile_provider_unavailable"):
        async with model_runtime.configured_model_provider(profile):
            pass


async def test_openrouter_factory_needs_no_openai_client(monkeypatch):
    import httpx
    import openai
    from app.adapters.checkers import create_checker_model_provider

    def forbidden(*_args, **_kwargs):
        raise AssertionError("OpenRouter constructed an OpenAI client")

    profile = Harness().profile
    profile = profile.model_copy(update={"spec": profile.spec.model_copy(update={
        "provider": "openrouter", "api": "chat_completions",
        "model_snapshot": "openai/gpt-5.6-terra",
    })})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    captured = []
    original = httpx.AsyncClient

    class CapturingClient(original):
        def __init__(self, **kwargs):
            captured.append(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", CapturingClient)
    provider = create_checker_model_provider(profile, api_key="private-openrouter-key")
    try:
        assert provider.identity.provider_key == "openrouter"
        assert len(captured) == 1
        assert captured[0]["trust_env"] is False
        assert captured[0]["follow_redirects"] is False
        assert captured[0]["timeout"] == profile.spec.deadline_ms / 1000
        assert captured[0]["headers"]["Authorization"] == "Bearer private-openrouter-key"
    finally:
        await provider.aclose()


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


async def test_missing_openrouter_key_cannot_use_openai_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "other-provider-key")
    h = Harness()
    h.profile = h.profile.model_copy(update={"spec": h.profile.spec.model_copy(update={
        "provider": "openrouter", "api": "chat_completions",
        "model_snapshot": "openai/model",
    })})
    h.provider = model_runtime.configured_model_provider
    assert (await h.invoke()).outcome == "unavailable"
    assert h.state == "prepared"
    assert "dispatch_committed" not in h.events


async def test_ordinary_post_needs_no_model_credentials_or_budget(monkeypatch):
    from app.adapters.checkers.model_execution import ModelAwareExternalExecution

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    request = SimpleNamespace(configuration={}, identity=SimpleNamespace(phase="post_submit"))
    grant, result = object(), object()
    calls = []

    async def execute(received_request, received_grant):
        calls.append((received_request, received_grant))
        return result

    def forbidden():
        raise AssertionError("ordinary POST opened model authorization/budget storage")

    adapter = ModelAwareExternalExecution(
        execution=SimpleNamespace(execute=execute), sessions=forbidden,
    )
    assert await adapter.execute(request, grant) is result
    assert calls == [(request, grant)]


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
