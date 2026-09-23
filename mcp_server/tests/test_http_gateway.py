from __future__ import annotations

import asyncio
import typing

import httpx2 as httpx
import pytest
from conftest import authorization_context_fixture, profile_fixture

from workstream_mcp.config import Settings
from workstream_mcp.http_gateway import WorkstreamGateway, create_http_client


def settings(**changes: typing.Any) -> Settings:
    values: dict[str, typing.Any] = {"api_url": "http://127.0.0.1:8000"}
    values.update(changes)
    return Settings(**values)


@pytest.mark.asyncio
async def test_gateway_preserves_valid_full_profile_and_uses_safe_client() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json=profile_fixture(), headers={"content-type": "application/json"}
        )

    client = httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(handler))
    try:
        result = await WorkstreamGateway(settings(), client).profile_get("Bearer opaque")
    finally:
        await client.aclose()
    assert result.data == profile_fixture()
    assert result.failure is None
    assert seen[0].headers["accept-encoding"] == "identity"
    assert seen[0].headers["authorization"] == "Bearer opaque"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "expected_code"),
    [
        (
            401,
            {"error": {"code": "invalid_token", "message": "token secret", "details": {}}},
            "invalid_token",
        ),
        (
            403,
            {"error": {"code": "identity_link_revoked", "message": "private", "details": {}}},
            "identity_link_revoked",
        ),
        (500, {"error": {"code": "unknown_internal", "message": "secret", "details": {}}}, None),
    ],
)
async def test_gateway_returns_only_safe_upstream_failure(
    status: int, body: dict[str, object], expected_code: str | None
) -> None:
    client = httpx.AsyncClient(
        base_url="http://api.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body)),
    )
    try:
        result = await WorkstreamGateway(settings(), client).profile_get("Bearer opaque")
    finally:
        await client.aclose()
    assert result.data is None
    assert result.failure is not None
    assert result.failure.status == status
    assert result.failure.code == expected_code
    assert "secret" not in str(result.failure.payload())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        lambda: httpx.Response(
            200,
            json={"actor_profile_id": "missing fields"},
            headers={"content-type": "application/json"},
        ),
        lambda: httpx.Response(200, content=b"[]", headers={"content-type": "application/json"}),
        lambda: httpx.Response(200, json=profile_fixture(), headers={"content-type": "text/plain"}),
        lambda: httpx.Response(
            200,
            content=b"x" * 4096,
            headers={"content-type": "application/json", "content-encoding": "gzip"},
        ),
        lambda: httpx.Response(
            200,
            content=b"x" * 4096,
            headers={"content-type": "application/json", "content-length": "4096"},
        ),
    ],
)
async def test_gateway_rejects_invalid_or_oversized_success(response: typing.Any) -> None:
    client = httpx.AsyncClient(
        base_url="http://api.test", transport=httpx.MockTransport(lambda _: response())
    )
    try:
        result = await WorkstreamGateway(settings(max_response_bytes=1024), client).profile_get(
            "Bearer opaque"
        )
    finally:
        await client.aclose()
    assert result.data is None
    assert result.failure is not None
    assert result.failure.status == 502


@pytest.mark.asyncio
async def test_gateway_timeout_and_cancellation_have_distinct_outcomes() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(
            200, json=profile_fixture(), headers={"content-type": "application/json"}
        )

    client = httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(handler))
    try:
        gateway = WorkstreamGateway(
            settings(
                total_timeout_seconds=0.1, connect_timeout_seconds=0.1, read_timeout_seconds=0.1
            ),
            client,
        )
        # Timeout outcome
        result = await gateway.profile_get("Bearer opaque")
        assert result.failure is not None
        assert result.failure.status == 504

        # Cancellation outcome
        gateway_no_timeout = WorkstreamGateway(settings(), client)
        task = asyncio.create_task(gateway_no_timeout.profile_get("Bearer opaque"))
        await asyncio.sleep(0)  # Yield to let the task start
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        await client.aclose()


def test_outbound_client_disables_environment_proxy_and_redirects() -> None:
    client = create_http_client(settings())
    try:
        assert client.follow_redirects is False
        assert client._trust_env is False
    finally:
        asyncio.run(client.aclose())


@pytest.mark.asyncio
async def test_profile_update_uses_one_unkeyed_patch_and_preserves_payload() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=profile_fixture(display_name="Victor", contact_email=None),
            headers={"content-type": "application/json"},
        )

    client = httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(handler))
    try:
        result = await WorkstreamGateway(settings(), client).profile_update(
            "Bearer opaque", {"display_name": "Victor", "contact_email": None}
        )
    finally:
        await client.aclose()

    assert result.failure is None
    assert len(seen) == 1
    assert seen[0].method == "PATCH"
    assert seen[0].url.path == "/api/v1/actors/me"
    assert seen[0].headers.get("idempotency-key") is None
    assert seen[0].headers.get("if-match") is None
    assert seen[0].read() == b'{"display_name":"Victor","contact_email":null}'


@pytest.mark.asyncio
async def test_profile_update_transport_failure_is_uncertain_and_not_retried() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadError("private upstream detail")

    client = httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(handler))
    try:
        result = await WorkstreamGateway(settings(), client).profile_update(
            "Bearer opaque", {"display_name": "Victor"}
        )
    finally:
        await client.aclose()

    assert calls == 1
    assert result.failure is not None
    assert result.failure.error == "workstream_execution_uncertain"
    assert result.failure.retryable is False
    assert result.failure.correlation_id is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        lambda: httpx.Response(
            200, content=b"not-json", headers={"content-type": "application/json"}
        ),
        lambda: httpx.Response(
            200, json=profile_fixture(), headers={"content-type": "text/plain"}
        ),
        lambda: httpx.Response(
            200,
            json=profile_fixture(updated_at="not-a-date"),
            headers={"content-type": "application/json"},
        ),
    ],
)
async def test_profile_update_invalid_success_is_uncertain(response: typing.Any) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response()

    client = httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(handler))
    try:
        result = await WorkstreamGateway(settings(), client).profile_update(
            "Bearer opaque", {"display_name": "Victor"}
        )
    finally:
        await client.aclose()

    assert calls == 1
    assert result.failure is not None
    assert result.failure.error == "workstream_execution_uncertain"
    assert result.failure.retryable is False
    assert result.failure.correlation_id is not None


@pytest.mark.asyncio
async def test_authorization_context_uses_fixed_path_and_encoded_project_query() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=authorization_context_fixture(),
            headers={"content-type": "application/json"},
        )

    client = httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(handler))
    try:
        result = await WorkstreamGateway(settings(), client).authorization_context_get(
            "Bearer opaque", "project/with ? reserved"
        )
    finally:
        await client.aclose()

    assert result.failure is None
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/v1/actors/me/authorization-context"
    assert seen[0].url.params["project_id"] == "project/with ? reserved"


@pytest.mark.asyncio
async def test_authorization_context_rejects_malformed_uuid_output() -> None:
    client = httpx.AsyncClient(
        base_url="http://api.test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json=authorization_context_fixture(project_id="not-a-uuid"),
                headers={"content-type": "application/json"},
            )
        ),
    )
    try:
        result = await WorkstreamGateway(settings(), client).authorization_context_get(
            "Bearer opaque", "project"
        )
    finally:
        await client.aclose()

    assert result.failure is not None
    assert result.failure.error == "invalid_api_response"
