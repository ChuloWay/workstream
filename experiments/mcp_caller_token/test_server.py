"""Adapter boundary tests; real Workstream evidence is separately in drill.py."""

import json
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from starlette.testclient import TestClient

import server
from client import local_http_client


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


def test_client_ignores_environment_proxy(monkeypatch):
    received = []

    class Endpoint(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"local")

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Endpoint) as target:
        thread = threading.Thread(target=target.serve_forever, daemon=True)
        thread.start()
        # A closed local socket represents an unusable proxy. The counterfactual
        # default client must fail, proving NO_PROXY isn't masking this test.
        import socket
        with socket.socket() as blocked:
            blocked.bind(("127.0.0.1", 0))
            proxy_url = f"http://127.0.0.1:{blocked.getsockname()[1]}"
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                monkeypatch.setenv(name, proxy_url)
            monkeypatch.setenv("NO_PROXY", "")
            monkeypatch.setenv("no_proxy", "")

            async def probe():
                url = f"http://127.0.0.1:{target.server_port}"
                async with httpx.AsyncClient(timeout=1) as vulnerable:
                    with pytest.raises(httpx.ConnectError):
                        await vulnerable.get(url)
                assert received == []
                async with local_http_client(headers={"Authorization": "Bearer local-fixture"}) as safe:
                    response = await safe.get(url)
                    assert response.status_code == 200
                    assert not safe.follow_redirects
                assert received == ["Bearer local-fixture"]
            try:
                asyncio.run(probe())
            finally:
                target.shutdown()
                thread.join(timeout=3)
