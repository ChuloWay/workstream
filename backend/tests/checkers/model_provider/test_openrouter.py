"""Offline OpenRouter transport tests for checker model custody."""

from __future__ import annotations

from datetime import UTC, datetime
import json

import httpx
import pytest

from app.adapters.checkers.openrouter_model_provider import (
    OpenRouterCheckerModelProvider,
)
from app.adapters.model_usage.openrouter import (
    bounded_response_bytes,
    openrouter_request_options,
    openrouter_usage,
    require_direct_openrouter_model,
)
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.checker_model_provider import (
    CHECKER_MODEL_CAPABILITY_KEY,
    MAX_CHECKER_MODEL_NAME_LENGTH,
    CheckerModelCreateFailure,
    CheckerModelCreateOutcome,
    CheckerModelObservation,
    CheckerModelProviderStatus,
    CheckerModelRecoveryOutcome,
    CheckerModelRequest,
    CheckerModelResponseReference,
    CheckerModelUsage,
)
from app.modules.model_usage.api import ProjectModelProfile, ProjectModelProfileSpec
from tests.checkers_model_calls.test_model_call_contract import profile_spec


def profile(**overrides) -> ProjectModelProfile:
    values = profile_spec().model_dump(mode="python")
    values.update(
        provider="openrouter",
        api="chat_completions",
        model_snapshot="openai/model",
        **overrides,
    )
    values.update(
        maximum_total_request_bytes=values["maximum_request_bytes"],
        maximum_total_response_bytes=values["maximum_response_bytes"],
        maximum_total_input_tokens=values["maximum_input_tokens"],
        maximum_total_output_tokens=values["maximum_output_tokens"],
    )
    spec = ProjectModelProfileSpec.model_validate(values)
    return ProjectModelProfile(
        operation_id=new_record_id(),
        actor_profile_id=new_record_id(),
        spec=spec,
        profile_digest=canonical_json_hash(spec.model_dump(mode="json")),
        profile_id=new_record_id(),
        authorization_evidence_id=new_record_id(),
        created_at=datetime.now(UTC),
    )


def metadata(**changes) -> dict:
    data = {
        "id": "openai/model",
        "canonical_slug": "openai/model-20261026",
        "context_length": 100,
        "top_provider": {
            "context_length": 100,
            "max_completion_tokens": 50,
        },
        "supported_parameters": [
            "max_tokens",
            "reasoning_effort",
            "tool_choice",
            "tools",
            "verbosity",
        ],
        "pricing": {
            "prompt": "0.000000011",
            "completion": "0.000000029",
            "input_cache_read": "0.000000002",
            "input_cache_write": "0.000000011",
        },
    }
    data.update(changes)
    return {"data": data}


def completion(**changes) -> dict:
    value = {
        "id": "generation-known",
        "model": "openai/model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "verbatim output"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 8,
            "prompt_tokens_details": {"cached_tokens": 3},
            "completion_tokens": 5,
            "completion_tokens_details": {"reasoning_tokens": 2},
            "total_tokens": 13,
        },
    }
    value.update(changes)
    return value


def adapter(handler, *, configured_profile=None) -> OpenRouterCheckerModelProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenRouterCheckerModelProvider(configured_profile or profile(), client)


def test_shared_identity_and_request_controls_are_exact_and_fresh() -> None:
    model = "a" * 79 + "/" + "b" * 80
    assert len(model) == MAX_CHECKER_MODEL_NAME_LENGTH
    observed = CheckerModelObservation(
        CheckerModelResponseReference("generation-known"),
        model,
        CheckerModelProviderStatus.COMPLETED,
        "bounded",
        CheckerModelUsage(1, 0, 1, 0, 2),
    )
    assert observed.provider_model == model
    with pytest.raises(ValueError, match="response identity"):
        CheckerModelResponseReference("provider/response")
    with pytest.raises(ValueError, match="provider identity"):
        CheckerModelObservation(
            CheckerModelResponseReference("generation-known"),
            "x" * (MAX_CHECKER_MODEL_NAME_LENGTH + 1),
            CheckerModelProviderStatus.FAILED,
            None,
            None,
        )
    assert require_direct_openrouter_model("openai/model") == "openai/model"
    for invalid in ("model", "openai/model/variant", "openrouter/model", "openai/model:free"):
        with pytest.raises(ValueError, match="routing"):
            require_direct_openrouter_model(invalid)
    first = openrouter_request_options()
    second = openrouter_request_options()
    assert first == second
    assert first is not second
    assert first["provider"] == {"allow_fallbacks": False, "data_collection": "deny"}
    assert all(plugin["enabled"] is False for plugin in first["plugins"])


async def test_shared_usage_and_body_reader_enforce_complete_bounded_values() -> None:
    normalized = openrouter_usage(completion()["usage"])
    assert normalized.input_tokens == 8
    assert normalized.cached_input_tokens == 3
    assert normalized.output_tokens == 5
    assert normalized.reasoning_tokens == 2
    assert normalized.total_tokens == 13
    with pytest.raises(ValueError, match="usage"):
        openrouter_usage(completion()["usage"] | {"total_tokens": 12})

    class Response:
        async def aiter_bytes(self):
            yield b"a" * 8
            yield b"b"

    with pytest.raises(ValueError, match="exceeds profile"):
        await bounded_response_bytes(Response(), 8)


async def test_create_preflights_then_dispatches_one_fixed_nonstreaming_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=metadata())
        return httpx.Response(200, json=completion())

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("inspect this package"))

    assert result.outcome is CheckerModelCreateOutcome.ACCEPTED
    assert result.failure is None
    assert result.known_response == CheckerModelResponseReference("generation-known")
    assert result.observation is not None
    assert result.observation.provider_model == "openai/model"
    assert result.observation.status is CheckerModelProviderStatus.COMPLETED
    assert result.observation.output_text == "verbatim output"
    assert result.observation.usage == CheckerModelUsage(8, 3, 5, 2, 13)
    assert provider.identity.capability_key == CHECKER_MODEL_CAPABILITY_KEY
    assert provider.identity.provider_key == "openrouter"
    assert [(item.method, item.url.path) for item in requests] == [
        ("GET", "/api/v1/model/openai/model"),
        ("POST", "/api/v1/chat/completions"),
    ]
    body = json.loads(requests[1].content)
    assert body == {
        "max_tokens": 50,
        "messages": [{"content": "inspect this package", "role": "user"}],
        "model": "openai/model",
        "parallel_tool_calls": False,
        "plugins": openrouter_request_options()["plugins"],
        "provider": openrouter_request_options()["provider"],
        "reasoning_effort": "medium",
        "store": False,
        "stream": False,
        "temperature": 0,
        "tool_choice": "none",
        "tools": [],
        "top_p": 1,
        "usage": {"include": True},
        "verbosity": "low",
    }
    await provider.aclose()


async def test_request_bound_refuses_before_metadata_or_paid_dispatch() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise AssertionError("request bound must prevent network I/O")

    provider = adapter(handler, configured_profile=profile(maximum_request_bytes=400))
    result = await provider.create(CheckerModelRequest("x" * 100))

    assert result.outcome is CheckerModelCreateOutcome.NO_EFFECT
    assert result.failure is CheckerModelCreateFailure.REQUEST_BYTES_EXCEEDED
    assert requests == []
    await provider.aclose()


@pytest.mark.parametrize(
    "drift",
    [
        {"id": "openai/other"},
        {"context_length": 101},
        {"supported_parameters": ["max_tokens"]},
        {"pricing": {"prompt": "0.000000012", "completion": "0.000000029"}},
    ],
    ids=["model", "context", "parameters", "pricing"],
)
async def test_metadata_refusal_prevents_paid_dispatch(drift: dict) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        return httpx.Response(200, json=metadata(**drift))

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("one effect"))

    assert result.outcome is CheckerModelCreateOutcome.NO_EFFECT
    assert result.failure is CheckerModelCreateFailure.INPUT_COUNT_UNAVAILABLE
    assert [request.method for request in requests] == ["GET"]
    await provider.aclose()


@pytest.mark.parametrize(
    ("post_result", "failure", "known"),
    [
        (httpx.Response(503, json={"id": "generation-known"}),
         CheckerModelCreateFailure.DELIVERY_UNCERTAIN, True),
        (httpx.Response(200, json=completion(choices=[])),
         CheckerModelCreateFailure.RESPONSE_INVALID, True),
        (httpx.Response(200, content=b"not-json"),
         CheckerModelCreateFailure.RESPONSE_INVALID, False),
    ],
    ids=["non-success", "invalid-output", "invalid-json"],
)
async def test_paid_response_failures_are_uncertain_without_second_post(
    post_result: httpx.Response,
    failure: CheckerModelCreateFailure,
    known: bool,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=metadata())
        return post_result

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("one paid effect"))

    assert result.outcome is CheckerModelCreateOutcome.UNCERTAIN
    assert result.failure is failure
    assert (result.known_response is not None) is known
    assert [request.method for request in requests].count("POST") == 1
    await provider.aclose()


async def test_lost_dispatch_is_uncertain_and_never_retried() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=metadata())
        raise httpx.ReadTimeout("lost response", request=request)

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("one paid effect"))

    assert result.outcome is CheckerModelCreateOutcome.UNCERTAIN
    assert result.failure is CheckerModelCreateFailure.DELIVERY_UNCERTAIN
    assert [request.method for request in requests].count("POST") == 1
    await provider.aclose()


@pytest.mark.parametrize(
    ("finish_reason", "status"),
    [
        ("length", CheckerModelProviderStatus.INCOMPLETE),
        ("content_filter", CheckerModelProviderStatus.FAILED),
        ("error", CheckerModelProviderStatus.FAILED),
    ],
)
async def test_known_terminal_failures_settle_with_complete_usage(
    finish_reason: str,
    status: CheckerModelProviderStatus,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=metadata())
        body = completion()
        body["choices"][0]["finish_reason"] = finish_reason
        return httpx.Response(200, json=body)

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("one paid effect"))

    assert result.outcome is CheckerModelCreateOutcome.ACCEPTED
    assert result.observation is not None
    assert result.observation.status is status
    assert result.observation.usage == CheckerModelUsage(8, 3, 5, 2, 13)
    await provider.aclose()


@pytest.mark.parametrize(
    "body",
    [
        completion(model="openai/foreign"),
        completion(choices=[]),
        completion(choices=[completion()["choices"][0], completion()["choices"][0]]),
        completion(usage=completion()["usage"] | {"total_tokens": 12}),
        completion(usage=completion()["usage"] | {"prompt_tokens": 101, "total_tokens": 106}),
        completion(usage=completion()["usage"] | {"completion_tokens": 51, "total_tokens": 59}),
    ],
    ids=[
        "foreign-model",
        "missing-choice",
        "multiple-choices",
        "usage-total",
        "input-bound",
        "output-token-bound",
    ],
)
async def test_identity_choice_and_usage_substitution_cannot_settle(body: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=metadata())
        return httpx.Response(200, json=body)

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("one paid effect"))

    assert result.outcome is CheckerModelCreateOutcome.UNCERTAIN
    assert result.failure is CheckerModelCreateFailure.RESPONSE_INVALID
    assert result.known_response == CheckerModelResponseReference("generation-known")
    await provider.aclose()


@pytest.mark.parametrize(
    "choice",
    [
        {
            "index": False,
            "message": {"role": "assistant", "content": "bounded"},
            "finish_reason": "stop",
        },
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "bounded",
                "tool_calls": [{"id": "call-hidden"}],
            },
            "finish_reason": "stop",
        },
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "bounded",
                "function_call": {"name": "hidden"},
            },
            "finish_reason": "stop",
        },
    ],
    ids=["boolean-index", "tool-call", "function-call"],
)
async def test_non_text_choice_payload_cannot_settle(choice: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=metadata())
        return httpx.Response(200, json=completion(choices=[choice]))

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("one paid effect"))

    assert result.outcome is CheckerModelCreateOutcome.UNCERTAIN
    assert result.failure is CheckerModelCreateFailure.RESPONSE_INVALID
    assert result.known_response == CheckerModelResponseReference("generation-known")
    await provider.aclose()


@pytest.mark.parametrize("finish_reason", ["stop", "content_filter"])
async def test_structurally_complete_refusal_settles_as_known_failure(
    finish_reason: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=metadata())
        choice = {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "refusal": "request refused",
            },
            "finish_reason": finish_reason,
        }
        return httpx.Response(200, json=completion(choices=[choice]))

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("one paid effect"))

    assert result.outcome is CheckerModelCreateOutcome.ACCEPTED
    assert result.observation is not None
    assert result.observation.status is CheckerModelProviderStatus.FAILED
    assert result.observation.output_text is None
    assert result.observation.usage == CheckerModelUsage(8, 3, 5, 2, 13)
    await provider.aclose()


async def test_response_and_output_byte_bounds_remain_uncertain_after_post() -> None:
    async def exercise(configured_profile, body):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "GET":
                return httpx.Response(200, json=metadata())
            return httpx.Response(200, json=body)

        provider = adapter(handler, configured_profile=configured_profile)
        result = await provider.create(CheckerModelRequest("one paid effect"))
        await provider.aclose()
        assert [request.method for request in requests].count("POST") == 1
        return result

    output_result = await exercise(
        profile(maximum_output_bytes=10, maximum_response_bytes=5_000),
        completion(choices=[{
            "index": 0,
            "message": {"role": "assistant", "content": "x" * 11},
            "finish_reason": "stop",
        }]),
    )
    response_result = await exercise(
        profile(maximum_output_bytes=10, maximum_response_bytes=4_156),
        completion() | {"padding": "x" * 5_000},
    )
    for result in (output_result, response_result):
        assert result.outcome is CheckerModelCreateOutcome.UNCERTAIN
        assert result.failure is CheckerModelCreateFailure.RESPONSE_INVALID


async def test_recover_is_unavailable_with_zero_network_io() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise AssertionError("OpenRouter recovery must not use network I/O")

    provider = adapter(handler)
    reference = CheckerModelResponseReference("generation-known")
    result = await provider.recover(reference)

    assert result.outcome is CheckerModelRecoveryOutcome.UNAVAILABLE
    assert result.reference == reference
    assert result.observation is None
    assert requests == []
    await provider.aclose()
