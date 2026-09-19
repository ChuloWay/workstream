from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Message, Receive, Scope, Send

from workstream_mcp.auth import CredentialError, request_bearer, request_correlation_id
from workstream_mcp.config import Settings
from workstream_mcp.errors import adapter_failure
from workstream_mcp.http_gateway import WorkstreamGateway, create_http_client
from workstream_mcp.schemas import profile_output_schema
from workstream_mcp.tools.profile import TOOL_NAME, definition, invoke

SERVER_NAME = "workstream-mcp"


class IngressLimitError(Exception):
    """The inbound request exceeded its frame or elapsed-time budget."""


class _McpPrivacyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "mcp" or record.name.startswith("mcp."):
            if record.levelno >= logging.WARNING:
                record.msg = "MCP request processing failed"
                record.args = ()
                record.exc_info = None
                record.exc_text = None
        return True


def _install_sdk_log_filter() -> None:
    filter_ = _McpPrivacyFilter()
    handlers = logging.getLogger().handlers + logging.getLogger("uvicorn.error").handlers
    for handler in handlers:
        if not any(isinstance(item, _McpPrivacyFilter) for item in handler.filters):
            handler.addFilter(filter_)

    loggers = [logging.getLogger("mcp")]
    for name, logger in logging.root.manager.loggerDict.items():
        if isinstance(logger, logging.Logger) and name.startswith("mcp."):
            loggers.append(logger)

    for logger in loggers:
        if not any(isinstance(item, _McpPrivacyFilter) for item in logger.filters):
            logger.addFilter(filter_)


def create_app(settings: Settings) -> Starlette:
    _install_sdk_log_filter()
    profile_output_schema()
    server: Server[Any] = Server(SERVER_NAME)
    gateway: WorkstreamGateway | None = None

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[Any]:
        return [definition()]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        if name != TOOL_NAME:
            return adapter_failure("unknown_tool", status=404)
        if arguments != {}:
            return adapter_failure("invalid_tool_input", status=400)
        request = server.request_context.request
        if request is None:
            return adapter_failure("missing_request_context", status=401)
        try:
            bearer = request_bearer(request.headers)
        except CredentialError:
            return adapter_failure("invalid_credentials", status=401)
        if gateway is None:
            return adapter_failure("adapter_unavailable", status=503)
        return await invoke(gateway, bearer, request_correlation_id(request.headers))

    manager = StreamableHTTPSessionManager(
        server,
        stateless=True,
        json_response=True,
        max_request_body_size=settings.max_request_bytes,
        security_settings=TransportSecuritySettings(
            allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=[],
        ),
    )

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        nonlocal gateway
        async with create_http_client(settings) as client, manager.run():
            gateway = WorkstreamGateway(settings, client)
            try:
                yield
            finally:
                gateway = None

    class Endpoint:
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            raw_headers = scope.get("headers", [])
            if any(key.lower() == b"origin" for key, _ in raw_headers):
                await JSONResponse(
                    {"error": "origin_not_allowed"},
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
                return
            header_size = sum(len(key) + len(value) for key, value in raw_headers)
            if header_size > settings.max_header_bytes:
                await JSONResponse(
                    {"error": "headers_too_large"},
                    status_code=431,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
                return
            content_lengths = [
                value for key, value in raw_headers if key.lower() == b"content-length"
            ]
            if len(content_lengths) > 1:
                await JSONResponse(
                    {"error": "invalid_content_length"},
                    status_code=400,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
                return
            if content_lengths:
                try:
                    declared_length = int(content_lengths[0])
                except ValueError:
                    declared_length = -1
                if declared_length < 0 or declared_length > settings.max_request_bytes:
                    await JSONResponse(
                        {"error": "request_too_large"},
                        status_code=413,
                        headers={"Cache-Control": "no-store"},
                    )(scope, receive, send)
                    return

            loop = asyncio.get_running_loop()
            deadline = loop.time() + settings.ingress_timeout_seconds
            request_frames = 0
            request_bytes = 0
            response_started = False

            # Bounded queue prevents uncontrolled memory consumption during streaming
            receive_queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=2)
            disconnect_event = asyncio.Event()

            async def pump_receive() -> None:
                while True:
                    try:
                        msg = await receive()
                    except BaseException:
                        break
                    await receive_queue.put(msg)
                    if msg.get("type") == "http.disconnect":
                        disconnect_event.set()
                        break

            pump_task = asyncio.create_task(pump_receive())

            async def bounded_receive() -> Message:
                nonlocal request_frames, request_bytes
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise IngressLimitError
                try:
                    message = await asyncio.wait_for(receive_queue.get(), timeout=remaining)
                except TimeoutError as exc:
                    raise IngressLimitError from exc
                if message.get("type") == "http.request":
                    request_frames += 1
                    request_bytes += len(message.get("body", b""))
                    if (
                        request_frames > settings.max_request_frames
                        or request_bytes > settings.max_request_bytes
                    ):
                        raise IngressLimitError
                return message

            async def no_store_send(message: Message) -> None:
                nonlocal response_started
                if message["type"] == "http.response.start":
                    response_started = True
                    headers = message.setdefault("headers", [])
                    headers[:] = [item for item in headers if item[0].lower() != b"cache-control"]
                    headers.append((b"cache-control", b"no-store"))
                await send(message)

            try:
                # Workaround for MCP SDK v1.29.0: StreamableHTTPServerTransport does not
                # use try...finally, so transport termination is skipped on disconnect.
                from mcp.server.streamable_http import StreamableHTTPServerTransport

                if not getattr(StreamableHTTPServerTransport, "_workstream_patched", False):
                    original_handle = StreamableHTTPServerTransport.handle_request

                    async def patched_handle(self_obj: Any, *args: Any, **kwargs: Any) -> None:
                        try:
                            await original_handle(self_obj, *args, **kwargs)
                        except asyncio.CancelledError:
                            await self_obj.terminate()
                            raise

                    StreamableHTTPServerTransport.handle_request = patched_handle  # type: ignore
                    StreamableHTTPServerTransport._workstream_patched = True  # type: ignore[attr-defined]

                manager_task = asyncio.create_task(
                    manager.handle_request(scope, bounded_receive, no_store_send)
                )

                async def watch_disconnect() -> None:
                    disconnect_task = asyncio.create_task(disconnect_event.wait())
                    done, pending = await asyncio.wait(
                        [manager_task, disconnect_task], return_when=asyncio.FIRST_COMPLETED
                    )
                    if disconnect_task in done:
                        manager_task.cancel()
                    else:
                        disconnect_task.cancel()

                await watch_disconnect()
                await manager_task
            except asyncio.CancelledError:
                pass
            except IngressLimitError:
                if not response_started:
                    await JSONResponse(
                        {"error": "request_ingress_limit"},
                        status_code=408,
                        headers={"Cache-Control": "no-store"},
                    )(scope, receive, send)
            finally:
                pump_task.cancel()

    return Starlette(
        routes=[Route("/mcp", Endpoint(), methods=["POST", "GET", "DELETE"])],
        lifespan=lifespan,
    )
