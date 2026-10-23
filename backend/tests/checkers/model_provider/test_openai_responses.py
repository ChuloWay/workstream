"""Offline OpenAI Responses transport tests for checker model custody."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import httpx2
from openai import AsyncOpenAI
import pytest

from app.adapters.checkers.model_provider import (
    OpenAIResponsesCheckerModelProvider,
    OpenAIResponsesSettings,
)
from app.adapters.checkers import create_checker_model_provider
from app.interfaces.checker_model_provider import (
    CHECKER_MODEL_CAPABILITY_KEY,
    MAX_CHECKER_MODEL_OUTPUT_BYTES,
    MAX_CHECKER_MODEL_PROMPT_BYTES,
    CheckerModelCreateFailure,
    CheckerModelCreateOutcome,
    CheckerModelObservation,
    CheckerModelProviderStatus,
    CheckerModelRecoveryOutcome,
    CheckerModelRequest,
    CheckerModelResponseReference,
    CheckerModelUsage,
)


def settings(**overrides) -> OpenAIResponsesSettings:
    values = {
        "api_key": "secret-test-key",
        "model": "gpt-5.6-terra",
        "maximum_request_bytes": 1_000,
        "maximum_input_tokens": 100,
        "maximum_output_tokens": 20,
        "maximum_output_bytes": 1_000,
        "request_timeout_seconds": 3.0,
        "reasoning_effort": "medium",
        "text_verbosity": "low",
    }
    values.update(overrides)
    return OpenAIResponsesSettings(**values)


def completed_response(
    *,
    response_id: str = "resp_known",
    model: str = "gpt-5.6-terra",
    status: str = "completed",
    text: str = "verbatim output",
    usage: dict | None = None,
) -> dict:
    body = {
        "id": response_id,
        "object": "response",
        "created_at": 1.0,
        "model": model,
        "status": status,
        "service_tier": "default",
        "output": [],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "temperature": None,
        "top_p": None,
        "usage": usage,
    }
    if status in {"completed", "failed", "cancelled", "incomplete"} and text:
        body["output"] = [
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ]
    return body


def usage(**overrides) -> dict:
    values = {
        "input_tokens": 8,
        "input_tokens_details": {"cached_tokens": 3, "cache_write_tokens": 0},
        "output_tokens": 5,
        "output_tokens_details": {"reasoning_tokens": 2},
        "total_tokens": 13,
    }
    values.update(overrides)
    return values


def adapter(handler, *, profile=None):
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    client = AsyncOpenAI(
        api_key="secret-test-key",
        base_url="https://provider.invalid/v1",
        http_client=http_client,
        max_retries=0,
    )
    return OpenAIResponsesCheckerModelProvider(profile or settings(), client)


def test_dtos_are_immutable_bounded_and_secret_safe() -> None:
    request = CheckerModelRequest("private prompt")
    observed = CheckerModelObservation(
        CheckerModelResponseReference("resp_known"),
        "gpt-5.6-terra",
        CheckerModelProviderStatus.COMPLETED,
        "private output",
        CheckerModelUsage(8, 3, 5, 2, 13),
    )
    configured = settings()

    assert "private prompt" not in repr(request)
    assert "private output" not in repr(observed)
    assert "secret-test-key" not in repr(configured)
    with pytest.raises(FrozenInstanceError):
        request.prompt = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="prompt"):
        CheckerModelRequest("x" * (MAX_CHECKER_MODEL_PROMPT_BYTES + 1))
    with pytest.raises(ValueError, match="usage"):
        CheckerModelUsage(8, 9, 5, 2, 13)
    with pytest.raises(ValueError, match="usage"):
        CheckerModelUsage(8, 3, 5, 6, 13)
    with pytest.raises(ValueError, match="usage"):
        CheckerModelUsage(8, 3, 5, 2, 12)
    with pytest.raises(ValueError, match="settings"):
        settings(model="unusable/model")
    with pytest.raises(ValueError, match="settings"):
        settings(maximum_request_bytes=MAX_CHECKER_MODEL_PROMPT_BYTES + 1)
    with pytest.raises(ValueError, match="settings"):
        settings(maximum_output_bytes=MAX_CHECKER_MODEL_OUTPUT_BYTES + 1)


async def test_create_counts_then_dispatches_one_stored_background_response() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if request.url.path.endswith("/responses/input_tokens"):
            return httpx2.Response(
                200,
                json={"object": "response.input_tokens", "input_tokens": 8},
            )
        return httpx2.Response(200, json=completed_response(usage=usage()))

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("inspect this package"))
    await provider.aclose()

    assert result.outcome is CheckerModelCreateOutcome.ACCEPTED
    assert result.failure is None
    assert result.known_response == CheckerModelResponseReference("resp_known")
    assert result.observation is not None
    assert result.observation.provider_model == "gpt-5.6-terra"
    assert result.observation.output_text == "verbatim output"
    assert result.observation.usage == CheckerModelUsage(8, 3, 5, 2, 13)
    assert [request.url.path for request in requests] == [
        "/v1/responses/input_tokens",
        "/v1/responses",
    ]
    counted, created = (json.loads(request.content) for request in requests)
    for body in (counted, created):
        assert body["model"] == "gpt-5.6-terra"
        assert body["input"] == "inspect this package"
        assert body["reasoning"] == {"effort": "medium"}
        assert body["text"] == {"verbosity": "low"}
        assert body["parallel_tool_calls"] is False
        assert body["tools"] == []
        assert body["truncation"] == "disabled"
    assert created["background"] is True
    assert created["store"] is True
    assert created["service_tier"] == "default"
    assert created["max_output_tokens"] == 20


@pytest.mark.parametrize(
    ("model_request", "count_response", "failure"),
    [
        (
            CheckerModelRequest("x" * 11),
            None,
            CheckerModelCreateFailure.REQUEST_BYTES_EXCEEDED,
        ),
        (
            CheckerModelRequest("bounded"),
            httpx2.Response(503),
            CheckerModelCreateFailure.INPUT_COUNT_UNAVAILABLE,
        ),
        (
            CheckerModelRequest("bounded"),
            httpx2.Response(
                200,
                json={"object": "response.input_tokens", "input_tokens": 101},
            ),
            CheckerModelCreateFailure.INPUT_LIMIT_EXCEEDED,
        ),
    ],
    ids=["request-exceeds-profile", "count-unavailable", "count-exceeds-profile"],
)
async def test_precreate_count_failures_prove_no_create_effect(
    model_request: CheckerModelRequest,
    count_response: httpx2.Response | None,
    failure: CheckerModelCreateFailure,
) -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        assert count_response is not None
        return count_response

    provider = adapter(handler, profile=settings(maximum_request_bytes=10))
    result = await provider.create(model_request)
    await provider.aclose()

    assert result.outcome is CheckerModelCreateOutcome.NO_EFFECT
    assert result.failure is failure
    assert result.known_response is None
    expected_paths = [] if count_response is None else ["/v1/responses/input_tokens"]
    assert [request.url.path for request in requests] == expected_paths


async def test_lost_create_is_uncertain_and_never_retried() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if request.url.path.endswith("/responses/input_tokens"):
            return httpx2.Response(
                200,
                json={"object": "response.input_tokens", "input_tokens": 8},
            )
        raise httpx2.ReadTimeout("lost create response", request=request)

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("one paid effect"))
    await provider.aclose()

    assert result.outcome is CheckerModelCreateOutcome.UNCERTAIN
    assert result.failure is CheckerModelCreateFailure.DELIVERY_UNCERTAIN
    assert result.known_response is None
    assert [request.url.path for request in requests] == [
        "/v1/responses/input_tokens",
        "/v1/responses",
    ]


async def test_create_http_rejection_remains_uncertain_and_never_retried() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if request.url.path.endswith("/responses/input_tokens"):
            return httpx2.Response(
                200,
                json={"object": "response.input_tokens", "input_tokens": 8},
            )
        return httpx2.Response(
            400,
            json={
                "error": {
                    "message": "provider detail must remain private",
                    "type": "invalid_request_error",
                }
            },
        )

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("one paid effect"))
    await provider.aclose()

    assert result.outcome is CheckerModelCreateOutcome.UNCERTAIN
    assert result.failure is CheckerModelCreateFailure.DELIVERY_UNCERTAIN
    assert "provider detail" not in repr(result)
    assert [request.url.path for request in requests] == [
        "/v1/responses/input_tokens",
        "/v1/responses",
    ]


async def test_recover_uses_only_the_known_response_id() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200,
            json=completed_response(
                status="queued",
                text="",
                usage=None,
            ),
        )

    provider = adapter(handler)
    reference = CheckerModelResponseReference("resp_known")
    result = await provider.recover(reference)
    await provider.aclose()

    assert result.outcome is CheckerModelRecoveryOutcome.OBSERVED
    assert result.reference == reference
    assert result.observation is not None
    assert result.observation.status is CheckerModelProviderStatus.QUEUED
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/responses/resp_known"


@pytest.mark.parametrize(
    ("body", "profile_overrides"),
    [
        (
            completed_response(
                usage=usage(
                    input_tokens_details={
                        "cached_tokens": 9,
                        "cache_write_tokens": 0,
                    }
                )
            ),
            {},
        ),
        (completed_response(usage=usage(total_tokens=12)), {}),
        (
            completed_response(usage=usage(input_tokens=101, total_tokens=106)),
            {},
        ),
        (
            completed_response(usage=usage(output_tokens=21, total_tokens=29)),
            {},
        ),
        (
            completed_response(usage=usage(output_tokens_details={"reasoning_tokens": 6})),
            {},
        ),
        (completed_response(model="gpt-5.6-terra-other", usage=usage()), {}),
        (
            completed_response(text="x" * 11, usage=usage()),
            {"maximum_output_bytes": 10},
        ),
        (completed_response(response_id="", usage=usage()), {}),
        (completed_response(usage=usage()) | {"service_tier": "priority"}, {}),
        (completed_response(usage=usage()) | {"service_tier": None}, {}),
    ],
    ids=[
        "cached-exceeds-input",
        "total-mismatch",
        "input-exceeds-profile",
        "output-exceeds-profile",
        "reasoning-exceeds-output",
        "model-mismatch",
        "output-byte-bound",
        "missing-response-id",
        "unexpected-pricing-tier",
        "missing-pricing-tier",
    ],
)
async def test_malformed_create_response_is_uncertain_and_never_releases_effect(
    body: dict,
    profile_overrides: dict,
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/responses/input_tokens"):
            return httpx2.Response(
                200,
                json={"object": "response.input_tokens", "input_tokens": 8},
            )
        return httpx2.Response(200, json=body)

    provider = adapter(handler, profile=settings(**profile_overrides))
    result = await provider.create(CheckerModelRequest("one effect"))
    await provider.aclose()

    assert result.outcome is CheckerModelCreateOutcome.UNCERTAIN
    assert result.failure is CheckerModelCreateFailure.RESPONSE_INVALID
    if body["id"]:
        assert result.known_response == CheckerModelResponseReference(body["id"])
    else:
        assert result.known_response is None


async def test_recovery_protocol_failure_is_invalid_without_create() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200,
            json=completed_response(model="wrong-model", usage=usage()),
        )

    provider = adapter(handler)
    reference = CheckerModelResponseReference("resp_known")
    result = await provider.recover(reference)
    await provider.aclose()

    assert result.outcome is CheckerModelRecoveryOutcome.INVALID
    assert result.reference == reference
    assert result.observation is None
    assert len(requests) == 1 and requests[0].method == "GET"


@pytest.mark.parametrize("status", ["failed", "cancelled", "incomplete"])
async def test_known_terminal_failures_remain_accepted_effects(status: str) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/responses/input_tokens"):
            return httpx2.Response(
                200,
                json={"object": "response.input_tokens", "input_tokens": 8},
            )
        return httpx2.Response(
            200,
            json=completed_response(status=status, text="", usage=None),
        )

    provider = adapter(handler)
    result = await provider.create(CheckerModelRequest("one effect"))
    await provider.aclose()

    assert result.outcome is CheckerModelCreateOutcome.ACCEPTED
    assert result.observation is not None
    assert result.observation.status.value == status
    assert result.observation.usage is None


async def test_factory_registers_one_zero_retry_openai_provider(monkeypatch) -> None:
    constructed: list[dict] = []

    class FakeInputTokens:
        async def count(self, **kwargs):
            raise AssertionError("factory test must not call provider")

    class FakeResponses:
        input_tokens = FakeInputTokens()

    class FakeClient:
        responses = FakeResponses()

        async def close(self):
            return None

    def client(**kwargs):
        constructed.append(kwargs)
        return FakeClient()

    monkeypatch.setattr("openai.AsyncOpenAI", client)
    provider = create_checker_model_provider(settings())

    assert provider.identity.capability_key == CHECKER_MODEL_CAPABILITY_KEY
    assert provider.identity.provider_key == "openai_responses"
    assert len(constructed) == 1
    assert constructed[0]["max_retries"] == 0
    assert constructed[0]["timeout"] == 3.0
    assert constructed[0]["api_key"] == "secret-test-key"
    await provider.aclose()
