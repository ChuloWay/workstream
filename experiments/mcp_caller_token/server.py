"""Loopback-only passthrough experiment; NOT production MCP OAuth authorization."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from urllib.parse import urlsplit

import httpx
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, Tool
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

TOOL = "workstream_profile_get"
INPUT = {"type": "object", "properties": {}, "additionalProperties": False}
LIMIT = 65536


def local_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or not parsed.port):
        raise ValueError("experiment requires an explicit IPv4 loopback HTTP port")
    return value.rstrip("/")


def failure(status: int) -> CallToolResult:
    return CallToolResult(isError=True, content=[TextContent(
        type="text", text=json.dumps({"error": "profile_request_failed", "status": status})
    )])


def create_app(api_url: str):
    api_url = local_url(api_url)
    server = Server("workstream-local-token-experiment")
    client = None
    slots = asyncio.Semaphore(8)

    @server.list_tools()
    async def list_tools():
        return [Tool(name=TOOL, description="Read the caller's Workstream profile.",
                     inputSchema=INPUT)]

    @server.call_tool()
    async def call_tool(name, arguments):
        if name != TOOL or arguments != {}:
            return failure(400)
        request = server.request_context.request
        headers = request.headers.getlist("authorization") if request else []
        if len(headers) != 1 or not headers[0].startswith("Bearer "):
            return failure(401)
        # No token parsing, shared identity, user selection, or credential cache.
        # This intentionally tests upstream-only authentication, not MCP OAuth.
        try:
            async with asyncio.timeout(12), slots:
                async with client.stream("GET", "/api/v1/actors/me", headers={
                    "Authorization": headers[0], "Accept": "application/json"
                }) as response:
                    if response.status_code != 200:
                        return failure(response.status_code)
                    payload = bytearray()
                    async for part in response.aiter_bytes():
                        payload.extend(part)
                        if len(payload) > LIMIT:
                            return failure(502)
                    profile = json.loads(payload)
                    if not isinstance(profile, dict) or "actor_profile_id" not in profile:
                        return failure(502)
                    return CallToolResult(content=[TextContent(
                        type="text", text=json.dumps(profile)
                    )], structuredContent=profile)
        except (httpx.HTTPError, TimeoutError, ValueError):
            return failure(502)

    manager = StreamableHTTPSessionManager(
        server, stateless=True, json_response=True, max_request_body_size=LIMIT,
        security_settings=TransportSecuritySettings(
            allowed_hosts=["127.0.0.1:*"], allowed_origins=[]),
    )

    @asynccontextmanager
    async def lifespan(app):
        nonlocal client
        async with httpx.AsyncClient(
            base_url=api_url, timeout=10, follow_redirects=False, trust_env=False,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=8),
        ) as client, manager.run():
            yield

    class Endpoint:
        async def __call__(self, scope, receive, send):
            headers = scope.get("headers", [])
            if any(key == b"origin" for key, _ in headers):
                await JSONResponse({"error": "native_client_only"}, 403,
                                   headers={"Cache-Control": "no-store"})(scope, receive, send)
                return
            if sum(len(key) + len(value) for key, value in headers) > 16384:
                await JSONResponse({"error": "headers_too_large"}, 431,
                                   headers={"Cache-Control": "no-store"})(scope, receive, send)
                return

            async def private_send(message):
                if message["type"] == "http.response.start":
                    message.setdefault("headers", []).append((b"cache-control", b"no-store"))
                await send(message)

            await manager.handle_request(scope, receive, private_send)

    return Starlette(routes=[Route("/mcp", Endpoint(), methods=["POST", "GET", "DELETE"])],
                     lifespan=lifespan)


if __name__ == "__main__":
    uvicorn.run(create_app(os.environ["MCP_EXPERIMENT_API_URL"]), host="127.0.0.1",
                port=int(os.environ["MCP_EXPERIMENT_PORT"]), log_level="error",
                access_log=False, limit_concurrency=32, timeout_keep_alive=5)
