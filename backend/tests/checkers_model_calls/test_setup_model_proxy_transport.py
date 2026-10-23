"""Credential-free setup model frames share the private listener without widening it."""

import json

import pytest

from app.adapters.checkers.model_proxy_transport import ModelProxyTransport
from app.adapters.project_agents.setup_model_proxy import (
    SetupModelProxySession,
    SetupModelProxyUnavailable,
)
from app.core.identifiers import new_record_id
from app.interfaces.checker_model_proxy import ModelProxyReply
from app.interfaces.setup_model_proxy import SetupModelProxyReply, SetupModelProxySubject


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
