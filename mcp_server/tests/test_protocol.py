from __future__ import annotations

from typing import Any

import pytest
from conftest import mcp_call
from starlette.testclient import TestClient


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("unknown", {}),
        ("workstream_profile_get", {"actor_id": "other"}),
        ("workstream_profile_get", {"authorization": "override"}),
        ("workstream_profile_get", {"url": "https://invalid.example"}),
    ],
)
def test_unknown_tools_and_input_injection_do_not_dispatch(
    adapter: tuple[TestClient, list[Any], dict[str, Any]], name: str, arguments: dict[str, Any]
) -> None:
    client, received, _ = adapter
    response = mcp_call(client, name=name, arguments=arguments)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["result"]["isError"] is True
    assert received == []


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({"origin": "https://invalid.example"}, 403),
        ({"content-length": "-1"}, 413),
        ({"content-length": "not-a-number"}, 413),
        ({"x-large": "x" * 17000}, 431),
    ],
)
def test_ingress_rejections_are_not_cached_or_dispatched(
    adapter: tuple[TestClient, list[Any], dict[str, Any]], headers: dict[str, str], status: int
) -> None:
    client, received, _ = adapter
    response = mcp_call(client, extra_headers=headers)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert received == []


def test_duplicate_authorization_does_not_dispatch(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, received, _ = adapter
    response = client.post(
        "/mcp",
        headers=[
            ("accept", "application/json, text/event-stream"),
            ("authorization", "Bearer first"),
            ("authorization", "Bearer second"),
        ],
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "workstream_profile_get", "arguments": {}},
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is True
    assert received == []


def test_every_response_is_no_store_and_profile_is_not_cross_caller_cached(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, received, upstream = adapter
    upstream["json"]["actor_profile_id"] = "alice"
    alice = mcp_call(client, token="alice")
    upstream["json"] = {**upstream["json"], "actor_profile_id": "bob"}
    bob = mcp_call(client, token="bob")
    assert alice.headers["cache-control"] == bob.headers["cache-control"] == "no-store"
    assert alice.json()["result"]["structuredContent"]["actor_profile_id"] == "alice"
    assert bob.json()["result"]["structuredContent"]["actor_profile_id"] == "bob"
    assert [request.headers["authorization"] for request in received] == [
        "Bearer alice",
        "Bearer bob",
    ]
