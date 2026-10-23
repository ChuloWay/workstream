"""Attempt-bound client for the trusted setup model dispatch listener."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import struct
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from app.adapters.model_usage import model_profile_reader
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.interfaces.setup_model_proxy import (
    SETUP_MODEL_PROXY_MAXIMUM_FRAME_BYTES,
    SETUP_MODEL_PROXY_PROTOCOL,
    SetupModelPhase,
    SetupModelProxyReply,
    SetupModelProxyRequest,
    SetupModelProxySubject,
    canonical_provider_json,
)
from app.modules.model_usage.api import ModelProfileSelector


class SetupModelProxyUnavailable(RuntimeError):
    """The trusted dispatch did not produce a safely replayable provider response."""


class SetupModelProxySession:
    """Allocate monotonically increasing paid slots for one immutable setup attempt."""

    def __init__(
        self,
        *,
        socket_path: Path,
        subject: SetupModelProxySubject,
        maximum_calls: int,
        maximum_output_tokens: int,
        reasoning_effort: str,
        text_verbosity: str,
        timeout_seconds: float,
    ) -> None:
        if (
            not isinstance(socket_path, Path)
            or type(subject) is not SetupModelProxySubject
            or type(maximum_calls) is not int
            or not 1 <= maximum_calls <= 100
            or type(maximum_output_tokens) is not int
            or not 1 <= maximum_output_tokens <= 10_000_000
            or reasoning_effort
            not in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
            or text_verbosity not in {"low", "medium", "high"}
            or type(timeout_seconds) is not float
            or not 0.1 <= timeout_seconds <= 7_200.0
        ):
            raise ValueError("setup model proxy session configuration is invalid")
        self._socket_path = socket_path
        self._subject = subject
        self._maximum_calls = maximum_calls
        self._maximum_output_tokens = maximum_output_tokens
        self._reasoning_effort = reasoning_effort
        self._text_verbosity = text_verbosity
        self._timeout_seconds = timeout_seconds
        self._call_index = 0
        self._blocked = False
        self._active = False

    @property
    def maximum_output_tokens(self) -> int:
        return self._maximum_output_tokens

    @property
    def reasoning_effort(self) -> str:
        return self._reasoning_effort

    @property
    def text_verbosity(self) -> str:
        return self._text_verbosity

    async def dispatch(
        self, phase: SetupModelPhase, provider_request: Mapping[str, object]
    ) -> SetupModelProxyReply:
        """Send one exact dispatch; any uncertain outcome permanently closes this session."""
        if self._blocked or self._call_index >= self._maximum_calls:
            raise SetupModelProxyUnavailable("setup model session is unavailable")
        if self._active:
            self._blocked = True
            raise SetupModelProxyUnavailable("setup model session is unavailable")
        request = SetupModelProxyRequest(
            subject=self._subject,
            phase=phase,
            call_index=self._call_index,
            provider_request_json=canonical_provider_json(provider_request),
        )
        self._active = True
        try:
            reply = await self._round_trip(request)
        except BaseException:
            self._blocked = True
            raise
        finally:
            self._active = False
        if reply.call_index != self._call_index:
            self._blocked = True
            raise SetupModelProxyUnavailable("setup model reply identity changed")
        self._call_index += 1
        if reply.session_exhausted:
            self._blocked = True
        if reply.outcome != "completed":
            self._blocked = True
            raise SetupModelProxyUnavailable("setup model dispatch is unavailable")
        return reply

    async def _round_trip(self, request: SetupModelProxyRequest) -> SetupModelProxyReply:
        identity = _validated_socket(self._socket_path)
        reader: asyncio.StreamReader | None = None
        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await asyncio.open_unix_connection(self._socket_path)
                if _validated_socket(self._socket_path) != identity:
                    raise SetupModelProxyUnavailable("setup model proxy identity changed")
                body = json.dumps(
                    request.wire_value(),
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                if not body or len(body) > SETUP_MODEL_PROXY_MAXIMUM_FRAME_BYTES:
                    raise SetupModelProxyUnavailable("setup model request exceeds transport bound")
                writer.write(struct.pack(">I", len(body)) + body)
                await writer.drain()
                header = await reader.readexactly(4)
                size = struct.unpack(">I", header)[0]
                if not 0 < size <= SETUP_MODEL_PROXY_MAXIMUM_FRAME_BYTES:
                    raise SetupModelProxyUnavailable("setup model reply exceeds transport bound")
                payload = await reader.readexactly(size)
                if await reader.read(1):
                    raise SetupModelProxyUnavailable("setup model reply has trailing bytes")
            return _decode_reply(payload)
        except (OSError, TimeoutError, asyncio.IncompleteReadError, ValueError, UnicodeError) as exc:
            raise SetupModelProxyUnavailable("setup model proxy is unavailable") from exc
        finally:
            if writer is not None:
                writer.close()
                try:
                    await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
                except (OSError, TimeoutError):
                    pass


def setup_model_session_factory(*, sessions, socket_path: Path | None):
    """Bind exact attempt/profile facts before exposing a credential-free capability."""

    @asynccontextmanager
    async def open_session(
        subject: SetupModelProxySubject | None,
        configuration: ProjectGuideRuntimeConfiguration,
    ):
        if not configuration.uses_inference:
            if subject is not None:
                raise SetupModelProxyUnavailable("setup model subject is unexpected")
            yield None
            return
        if socket_path is None or subject is None:
            raise SetupModelProxyUnavailable("setup model proxy is unavailable")
        if (
            configuration.model_profile_id is None
            or configuration.model_profile_version is None
            or configuration.model_profile_digest is None
        ):
            raise SetupModelProxyUnavailable("setup model profile is unavailable")
        selector = ModelProfileSelector(
            profile_id=configuration.model_profile_id,
            profile_version=configuration.model_profile_version,
            profile_digest=configuration.model_profile_digest,
        )
        async with sessions() as database, database.begin():
            profile = await model_profile_reader(database).read_exact(
                selector,
                project_id=subject.project_id,
            )
        if (
            profile.spec.provider,
            profile.spec.api,
            profile.spec.model_snapshot,
        ) != (
            configuration.model_provider,
            configuration.model_api,
            configuration.model,
        ):
            raise SetupModelProxyUnavailable("setup model profile is unavailable")
        if subject != SetupModelProxySubject(
            compilation_attempt_id=subject.compilation_attempt_id,
            project_id=subject.project_id,
            guide_id=subject.guide_id,
            source_snapshot_id=subject.source_snapshot_id,
            setup_run_id=subject.setup_run_id,
            setup_generation=subject.setup_generation,
            runtime_configuration_hash=configuration.sha256,
            profile_id=profile.profile_id,
            profile_version=profile.spec.profile_version,
            profile_digest=profile.profile_digest,
            provider=profile.spec.provider,
            api=profile.spec.api,
            model=profile.spec.model_snapshot,
        ):
            raise SetupModelProxyUnavailable("setup model profile is unavailable")
        yield SetupModelProxySession(
            socket_path=socket_path,
            subject=subject,
            maximum_calls=profile.spec.maximum_calls,
            maximum_output_tokens=profile.spec.maximum_output_tokens,
            reasoning_effort=profile.spec.settings.reasoning_effort,
            text_verbosity=profile.spec.settings.text_verbosity,
            timeout_seconds=profile.spec.deadline_ms / 1000.0,
        )

    return open_session


def _decode_reply(payload: bytes) -> SetupModelProxyReply:
    value = json.loads(
        payload.decode("utf-8"),
        parse_constant=_reject_constant,
        object_pairs_hook=_closed_object,
    )
    expected = {
        "protocol_version",
        "operation",
        "outcome",
        "call_index",
        "status_code",
        "response_json",
        "response_headers",
        "failure_code",
        "session_exhausted",
    }
    if type(value) is not dict or set(value) != expected:
        raise ValueError("setup model reply root is invalid")
    if (
        value["protocol_version"] != SETUP_MODEL_PROXY_PROTOCOL
        or value["operation"] != "dispatch"
        or type(value["response_headers"]) is not dict
    ):
        raise ValueError("setup model reply protocol is invalid")
    return SetupModelProxyReply(
        outcome=value["outcome"],
        call_index=value["call_index"],
        status_code=value["status_code"],
        response_json=value["response_json"],
        response_headers=tuple(sorted(value["response_headers"].items())),
        failure_code=value["failure_code"],
        session_exhausted=value["session_exhausted"],
    )


def _validated_socket(path: Path) -> tuple[int, int]:
    encoded = os.fsencode(path)
    if not path.is_absolute() or not encoded or b"\0" in encoded or len(encoded) >= 108:
        raise SetupModelProxyUnavailable("setup model proxy path is invalid")
    metadata = os.lstat(path)
    if (
        not stat.S_ISSOCK(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.geteuid()
        or metadata.st_gid != os.getegid()
    ):
        raise SetupModelProxyUnavailable("setup model proxy custody is invalid")
    return metadata.st_dev, metadata.st_ino


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate setup model proxy field")
        value[key] = item
    return value


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite setup model proxy number")


__all__ = (
    "SetupModelProxySession",
    "SetupModelProxyUnavailable",
    "create_setup_httpx_client",
    "setup_model_session_factory",
)


def create_setup_httpx_client(
    session: SetupModelProxySession,
    *,
    model: str,
    api: str,
    phase: Callable[[], SetupModelPhase],
    timeout_seconds: float,
):
    """Build a no-network httpx2 client that preserves native SDK request parsing."""
    import httpx2

    expected_path = {
        "responses": "/v1/responses",
        "chat_completions": "/v1/chat/completions",
    }.get(api)
    if expected_path is None:
        raise ValueError("setup model API is unsupported")

    class DispatchTransport(httpx2.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if (
                request.method != "POST"
                or request.url.host != "model-proxy.invalid"
                or request.url.path != expected_path
            ):
                raise httpx2.TransportError("setup model SDK request is outside policy")
            body = await request.aread()
            try:
                value = json.loads(
                    body,
                    parse_constant=_reject_constant,
                    object_pairs_hook=_closed_object,
                )
            except (ValueError, UnicodeError) as exc:
                raise httpx2.TransportError("setup model SDK request is invalid") from exc
            if (
                not isinstance(value, dict)
                or value.get("model") != model
                or value.get("stream", False) is not False
            ):
                raise httpx2.TransportError("setup model SDK request is outside policy")
            try:
                reply = await session.dispatch(phase(), value)
            except SetupModelProxyUnavailable as exc:
                raise httpx2.TransportError("setup model dispatch is unavailable") from exc
            assert reply.status_code is not None and reply.response_json is not None
            return httpx2.Response(
                status_code=reply.status_code,
                headers=dict(reply.response_headers),
                content=reply.response_json.encode("utf-8"),
                request=request,
            )

    return httpx2.AsyncClient(
        transport=DispatchTransport(),
        trust_env=False,
        follow_redirects=False,
        timeout=timeout_seconds,
    )
