"""Credential-free setup model frames share the private listener without widening it."""

from contextlib import asynccontextmanager
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from app.adapters.checkers.model_proxy_transport import ModelProxyTransport
import app.adapters.project_agents.setup_model_proxy as setup_model_proxy_adapter
from app.adapters.project_agents.setup_model_proxy import (
    SetupModelProxySession,
    SetupModelProxyUnavailable,
    setup_model_session_factory,
)
from app.core.identifiers import new_record_id
from app.interfaces.checker_model_proxy import ModelProxyReply
from app.interfaces.setup_model_proxy import SetupModelProxyReply, SetupModelProxySubject
from tests.projects.guide_compilation.helpers import runtime_configuration


def _sha(label: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _subject() -> SetupModelProxySubject:
    return SetupModelProxySubject(
        compilation_attempt_id=new_record_id(),
        project_id=new_record_id(),
        guide_id=new_record_id(),
        source_snapshot_id=new_record_id(),
        setup_run_id=new_record_id(),
        setup_generation=3,
        runtime_configuration_hash=_sha("runtime"),
        profile_id=new_record_id(),
        profile_version=4,
        profile_digest=_sha("profile"),
        provider="openai",
        api="responses",
        model="gpt-5.6-test",
    )


async def _unused_checker(_request):
    return ModelProxyReply("unavailable", None, None, "unused", 0, True)


@pytest.mark.asyncio
async def test_setup_round_trip_preserves_exact_subject_and_canonical_body(tmp_path):
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    socket = parent / "model.sock"
    observed = []

    async def handle(request):
        observed.append(request)
        return SetupModelProxyReply(
            outcome="completed",
            call_index=request.call_index,
            status_code=200,
            response_json=json.dumps(
                {"id": "resp_test", "usage": {"input_tokens": 2, "output_tokens": 1}},
                sort_keys=True,
                separators=(",", ":"),
            ),
            response_headers=(),
            failure_code=None,
            session_exhausted=False,
        )

    async with ModelProxyTransport(
        socket_path=socket,
        handler=_unused_checker,
        setup_handler=handle,
    ):
        session = SetupModelProxySession(
            socket_path=socket,
            subject=_subject(),
            maximum_calls=2,
            maximum_output_tokens=128,
            reasoning_effort="medium",
            text_verbosity="low",
            timeout_seconds=2.0,
        )
        reply = await session.dispatch(
            "draft",
            {"model": "gpt-5.6-test", "input": "bounded", "max_output_tokens": 128},
        )

    assert reply.outcome == "completed"
    assert len(observed) == 1
    assert observed[0].subject == session._subject
    assert observed[0].provider_request_json == (
        '{"input":"bounded","max_output_tokens":128,"model":"gpt-5.6-test"}'
    )


@pytest.mark.asyncio
async def test_unavailable_dispatch_permanently_blocks_sdk_retry(tmp_path):
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    socket = parent / "model.sock"
    calls = 0

    async def handle(request):
        nonlocal calls
        calls += 1
        return SetupModelProxyReply(
            outcome="unavailable",
            call_index=request.call_index,
            status_code=None,
            response_json=None,
            response_headers=(),
            failure_code="model_provider_delivery_uncertain",
            session_exhausted=True,
        )

    async with ModelProxyTransport(
        socket_path=socket,
        handler=_unused_checker,
        setup_handler=handle,
    ):
        session = SetupModelProxySession(
            socket_path=socket,
            subject=_subject(),
            maximum_calls=3,
            maximum_output_tokens=128,
            reasoning_effort="medium",
            text_verbosity="low",
            timeout_seconds=2.0,
        )
        with pytest.raises(SetupModelProxyUnavailable):
            await session.dispatch("draft", {"model": "gpt-5.6-test"})
        with pytest.raises(SetupModelProxyUnavailable):
            await session.dispatch("draft", {"model": "gpt-5.6-test"})

    assert calls == 1


def test_completed_reply_must_fit_after_inner_json_escaping():
    response_json = json.dumps(
        {"output": '"' * 500_000},
        sort_keys=True,
        separators=(",", ":"),
    )
    assert len(response_json.encode()) < 1024 * 1024

    with pytest.raises(ValueError, match="transport bound"):
        SetupModelProxyReply(
            outcome="completed",
            call_index=0,
            status_code=200,
            response_json=response_json,
            response_headers=(),
            failure_code=None,
            session_exhausted=True,
        )


def _tool_session_contract():
    profile_id = new_record_id()
    profile_digest = _sha("profile")
    configuration = runtime_configuration().model_copy(
        update={
            "model_profile_id": profile_id,
            "model_profile_version": 4,
            "model_profile_digest": profile_digest,
            "maximum_tool_calls": 3,
            "maximum_tool_output_characters": 65_536,
        }
    )
    profile = SimpleNamespace(
        profile_id=profile_id,
        profile_digest=profile_digest,
        spec=SimpleNamespace(
            profile_version=4,
            provider="openai",
            api="responses",
            model_snapshot="test-model",
            allowed_tools=("read_document", "search_document"),
            maximum_tool_calls=3,
            maximum_tool_output_bytes=65_536 * 4,
            maximum_calls=3,
            maximum_output_tokens=128,
            settings=SimpleNamespace(reasoning_effort="medium", text_verbosity="low"),
            deadline_ms=1_000,
        ),
    )
    subject = replace(
        _subject(),
        runtime_configuration_hash=configuration.sha256,
        profile_id=profile_id,
        profile_version=4,
        profile_digest=profile_digest,
        model="test-model",
    )
    return configuration, profile, subject


class _Database:
    @asynccontextmanager
    async def begin(self):
        yield


@asynccontextmanager
async def _sessions():
    yield _Database()


def _profile_reader(profile):
    class Reader:
        async def read_exact(self, selector, *, project_id):
            del selector, project_id
            return profile

    return lambda _database: Reader()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "runtime_limits",
    (
        {"maximum_tool_calls": 4},
        {"maximum_tool_output_characters": 65_537},
    ),
)
async def test_setup_session_rejects_tool_limits_above_profile_before_yield(
    monkeypatch, tmp_path, runtime_limits
):
    configuration, profile, subject = _tool_session_contract()
    monkeypatch.setattr(setup_model_proxy_adapter, "model_profile_reader", _profile_reader(profile))
    open_session = setup_model_session_factory(
        sessions=_sessions, socket_path=tmp_path / "model.sock"
    )

    yielded = False
    with pytest.raises(SetupModelProxyUnavailable, match="profile is unavailable"):
        async with open_session(subject, configuration.model_copy(update=runtime_limits)):
            yielded = True
    assert yielded is False


@pytest.mark.asyncio
async def test_setup_session_accepts_exact_profile_tool_limits(monkeypatch, tmp_path):
    configuration, profile, subject = _tool_session_contract()
    monkeypatch.setattr(setup_model_proxy_adapter, "model_profile_reader", _profile_reader(profile))
    open_session = setup_model_session_factory(
        sessions=_sessions, socket_path=tmp_path / "model.sock"
    )

    async with open_session(subject, configuration) as session:
        assert isinstance(session, SetupModelProxySession)
