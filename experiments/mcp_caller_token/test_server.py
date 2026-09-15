"""Adapter boundary tests; real Workstream evidence is separately in drill.py."""

import json

import httpx
import pytest
from starlette.testclient import TestClient

import server


@pytest.fixture
def adapter(monkeypatch):
    calls = []
    behavior = {"status": 200, "body": {"actor_profile_id": "fixture-profile"}}

    def upstream(request):
        calls.append(request)
        return httpx.Response(behavior["status"], json=behavior["body"],
                              headers={"Location": "https://must-not-follow.invalid"})

    original = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: original(
        **kw, transport=httpx.MockTransport(upstream)))
    with TestClient(server.create_app("http://127.0.0.1:12345"),
                    base_url="http://127.0.0.1:12346") as client:
        yield client, calls, behavior


def invoke(client, *, token="fixture-bearer", arguments=None, name=server.TOOL, extra_headers=None):
    headers = {"Accept": "application/json, text/event-stream"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    headers.update(extra_headers or {})
    return client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    })


def test_request_token_not_retained(adapter):
    client, calls, _ = adapter
    for token in ("alice", "bob", "alice"):
        response = invoke(client, token=token)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert not response.json()["result"]["isError"]
        assert calls[-1].headers["authorization"] == "Bearer " + token
        assert str(calls[-1].url) == "http://127.0.0.1:12345/api/v1/actors/me"
    assert len(calls) == 3
    assert invoke(client, token=None).json()["result"]["isError"]
    assert len(calls) == 3


@pytest.mark.parametrize("kwargs", [
    {"token": None}, {"arguments": {"actor_id": "someone-else"}},
    {"arguments": {"token": "override"}}, {"arguments": {"url": "https://bad.invalid"}},
    {"name": "unknown"},
])
def test_reject_without_dispatch(adapter, kwargs):
    client, calls, _ = adapter
    response = invoke(client, **kwargs)
    payload = response.json()
    assert "error" in payload or payload["result"]["isError"]
    assert calls == []


@pytest.mark.parametrize("status", [401, 403, 429, 503, 302])
def test_denial_and_redirect_not_leaked_or_followed(adapter, status):
    client, calls, behavior = adapter
    behavior.update(status=status, body={"unsafe": "fixture-bearer"})
    response = invoke(client)
    result = response.json()["result"]
    assert result["isError"]
    assert json.loads(result["content"][0]["text"]) == {
        "error": "profile_request_failed", "status": status}
    assert "fixture-bearer" not in response.text
    assert len(calls) == 1


def test_response_bound(adapter):
    client, calls, behavior = adapter
    behavior["body"] = {"actor_profile_id": "x" * (server.LIMIT + 1)}
    result = invoke(client).json()["result"]
    assert result["isError"]
    assert json.loads(result["content"][0]["text"])["status"] == 502
    assert len(calls) == 1


def test_request_bound(adapter):
    client, calls, _ = adapter
    response = invoke(client, arguments={"oversized": "x" * (server.LIMIT + 1)})
    assert response.status_code == 413
    assert calls == []


def test_duplicate_authorization_rejected(adapter):
    client, calls, _ = adapter
    response = client.post("/mcp", headers=[
        ("Accept", "application/json, text/event-stream"),
        ("Authorization", "Bearer alice"), ("Authorization", "Bearer bob"),
    ], json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": server.TOOL, "arguments": {}}})
    assert response.json()["result"]["isError"]
    assert calls == []


@pytest.mark.parametrize("headers,status", [
    ({"Origin": "https://untrusted.invalid"}, 403),
    ({"X-Large": "x" * 17000}, 431),
    ({"Host": "untrusted.invalid"}, 421),
])
def test_transport_rejection(adapter, headers, status):
    client, calls, _ = adapter
    response = invoke(client, extra_headers=headers)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert calls == []


@pytest.mark.parametrize("url", ["https://127.0.0.1:1234", "http://remote.invalid:1234",
                                 "http://127.0.0.1", "http://user@127.0.0.1:1234",
                                 "http://127.0.0.1:1234/another", "http://127.0.0.1:1234?q=1"])
def test_nonlocal_configuration_rejected(url):
    with pytest.raises(ValueError):
        server.create_app(url)
