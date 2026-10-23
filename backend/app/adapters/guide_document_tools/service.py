"""Bounded Unix-socket service for fixed guide-document parsing."""

from __future__ import annotations

import argparse
import asyncio
import errno
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import signal
import socket
import stat
import struct
import sys
from typing import Final

from pydantic import ValidationError

from .client import PARSER_SOCKET_GID, PARSER_SOCKET_MODE, PARSER_SOCKET_UID
from .contracts import (
    FIXED_PARSER_BUILD_DIGEST,
    GUIDE_DOCUMENT_PARSER_PROTOCOL,
    GuideDocumentParserRequest,
    GuideDocumentParserResponse,
    MAXIMUM_REQUEST_METADATA_BYTES,
    MAXIMUM_RESPONSE_BYTES,
)


PARSER_SOCKET_DIRECTORY_MODE = 0o750
_FIXED_CHILD_COMMAND: Final = (
    sys.executable,
    "-m",
    "app.adapters.guide_document_tools.child",
)
_CHILD_ENVIRONMENT: Final = {
    "PYTHONHASHSEED": "0",
    "PYTHONIOENCODING": "utf-8",
}


class GuideDocumentParserService:
    """Own one private socket and dispatch bounded work to disposable children."""

    def __init__(
        self,
        *,
        socket_path: Path,
        maximum_concurrency: int = 2,
        maximum_admitted_connections: int = 8,
        request_read_timeout_seconds: float = 5.0,
        child_timeout_seconds: float = 8.0,
        expected_uid: int = PARSER_SOCKET_UID,
        expected_gid: int = PARSER_SOCKET_GID,
    ) -> None:
        if (
            not socket_path.is_absolute()
            or type(maximum_concurrency) is not int
            or not 1 <= maximum_concurrency <= 8
            or type(maximum_admitted_connections) is not int
            or not maximum_concurrency <= maximum_admitted_connections <= 32
            or type(request_read_timeout_seconds) is not float
            or not 0.1 <= request_read_timeout_seconds <= 30.0
            or type(child_timeout_seconds) is not float
            or not 0.1 <= child_timeout_seconds <= 30.0
            or type(expected_uid) is not int
            or type(expected_gid) is not int
            or expected_uid < 0
            or expected_gid < 0
        ):
            raise ValueError("guide parser service configuration is invalid")
        self._socket_path = socket_path
        self._maximum_admitted = maximum_admitted_connections
        self._request_timeout = request_read_timeout_seconds
        self._child_timeout = child_timeout_seconds
        self._expected_uid = expected_uid
        self._expected_gid = expected_gid
        self._semaphore = asyncio.Semaphore(maximum_concurrency)
        self._admitted = 0
        self._server: asyncio.AbstractServer | None = None
        self._socket_inode: tuple[int, int] | None = None

    async def start(self) -> None:
        """Validate socket custody, remove only proven stale state, and bind."""
        if self._server is not None:
            raise RuntimeError("guide parser service is already started")
        self._validate_process_and_directory()
        _remove_owned_stale_socket(
            self._socket_path,
            expected_uid=self._expected_uid,
            expected_gid=self._expected_gid,
        )
        self._server = await asyncio.start_unix_server(
            self._handle_connection,
            path=self._socket_path,
            start_serving=False,
        )
        try:
            os.chmod(self._socket_path, PARSER_SOCKET_MODE, follow_symlinks=False)
            info = os.lstat(self._socket_path)
            if (
                not stat.S_ISSOCK(info.st_mode)
                or info.st_uid != self._expected_uid
                or info.st_gid != self._expected_gid
                or stat.S_IMODE(info.st_mode) != PARSER_SOCKET_MODE
            ):
                raise RuntimeError("guide parser socket custody is invalid")
            self._socket_inode = (info.st_dev, info.st_ino)
            await self._server.start_serving()
        except BaseException:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            self._remove_own_socket()
            raise

    async def serve_forever(self) -> None:
        """Serve until cancelled, then close and remove only this service's socket."""
        await self.start()
        assert self._server is not None
        try:
            await self._server.serve_forever()
        finally:
            await self.close()

    async def close(self) -> None:
        """Stop admission and remove the exact socket inode created at start."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._remove_own_socket()

    def _validate_process_and_directory(self) -> None:
        parent = self._socket_path.parent
        info = os.lstat(parent)
        allowed_groups = {os.getegid(), *os.getgroups()}
        if (
            os.geteuid() != self._expected_uid
            or self._expected_gid not in allowed_groups
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != self._expected_uid
            or info.st_gid != self._expected_gid
            or stat.S_IMODE(info.st_mode) != PARSER_SOCKET_DIRECTORY_MODE
        ):
            raise RuntimeError("guide parser socket directory custody is invalid")

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if self._admitted >= self._maximum_admitted:
            writer.close()
            await writer.wait_closed()
            return
        self._admitted += 1
        try:
            async with asyncio.timeout(self._request_timeout + self._child_timeout):
                metadata_raw = await _read_frame(reader, maximum=MAXIMUM_REQUEST_METADATA_BYTES)
                metadata = json.loads(metadata_raw)
                if type(metadata) is not dict or metadata.get("protocol_version") != GUIDE_DOCUMENT_PARSER_PROTOCOL:
                    raise ValueError("guide parser request protocol is invalid")
                if metadata.get("operation") == "health":
                    if set(metadata) != {"protocol_version", "operation"}:
                        raise ValueError("guide parser health request is invalid")
                    response = {
                        "protocol_version": GUIDE_DOCUMENT_PARSER_PROTOCOL,
                        "status": "ready",
                        "parser_build_digest": FIXED_PARSER_BUILD_DIGEST,
                    }
                else:
                    if set(metadata) != {"protocol_version", "operation", "request"} or metadata.get(
                        "operation"
                    ) != "parse":
                        raise ValueError("guide parser request shape is invalid")
                    request = GuideDocumentParserRequest.model_validate(metadata["request"])
                    source = await reader.readexactly(request.source_byte_count)
                    if f"sha256:{sha256(source).hexdigest()}" != request.source_sha256:
                        raise ValueError("guide parser source identity is invalid")
                    async with self._semaphore:
                        response = await self._run_child(
                            metadata_raw=metadata_raw,
                            source=source,
                            request=request,
                            disconnect_reader=reader,
                        )
                await _write_frame(writer, _json_bytes(response))
        except asyncio.CancelledError:
            raise
        except (
            TimeoutError,
            OSError,
            EOFError,
            ValueError,
            TypeError,
            UnicodeError,
            json.JSONDecodeError,
            ValidationError,
            asyncio.IncompleteReadError,
        ):
            pass
        finally:
            self._admitted -= 1
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _run_child(
        self,
        *,
        metadata_raw: bytes,
        source: bytes,
        request: GuideDocumentParserRequest,
        disconnect_reader: asyncio.StreamReader,
    ) -> dict[str, object]:
        process = await asyncio.create_subprocess_exec(
            *_FIXED_CHILD_COMMAND,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=_CHILD_ENVIRONMENT,
            start_new_session=True,
            preexec_fn=_apply_child_limits,
        )
        frame = struct.pack(">I", len(metadata_raw)) + metadata_raw + source
        child = asyncio.create_task(process.communicate(frame))
        disconnected = asyncio.create_task(disconnect_reader.read(1))
        try:
            done, _ = await asyncio.wait(
                {child, disconnected},
                timeout=self._child_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if child not in done:
                raise TimeoutError
            if disconnected in done:
                # EOF means the caller abandoned the in-flight request; any byte is
                # forbidden trailing request data. Both cases stop the child.
                raise ConnectionError("guide parser caller disconnected")
            stdout, _ = child.result()
        except BaseException:
            child.cancel()
            await _stop_child(process)
            await asyncio.gather(child, return_exceptions=True)
            raise
        finally:
            disconnected.cancel()
            await asyncio.gather(disconnected, return_exceptions=True)
        if process.returncode != 0:
            raise OSError("guide parser child failed")
        raw = _decode_single_frame(stdout, maximum=MAXIMUM_RESPONSE_BYTES)
        body = json.loads(raw)
        if type(body) is not dict or body.get("protocol_version") != GUIDE_DOCUMENT_PARSER_PROTOCOL:
            raise ValueError("guide parser child protocol is invalid")
        if body.get("status") == "rejected":
            if set(body) != {"protocol_version", "status", "reason"} or body["reason"] not in {
                "document_encrypted",
                "document_limit_exceeded",
                "document_malformed",
                "document_unsupported",
            }:
                raise ValueError("guide parser child rejection is invalid")
            return body
        if set(body) != {"protocol_version", "status", "result"} or body["status"] != "ok":
            raise ValueError("guide parser child response is invalid")
        result = GuideDocumentParserResponse.model_validate(body["result"])
        result.validate_against(request)
        return body

    def _remove_own_socket(self) -> None:
        if self._socket_inode is None:
            return
        try:
            current = os.lstat(self._socket_path)
            if (current.st_dev, current.st_ino) == self._socket_inode and stat.S_ISSOCK(
                current.st_mode
            ):
                self._socket_path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self._socket_inode = None


def _apply_child_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    if hasattr(resource, "RLIMIT_NPROC"):
        resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))


async def _stop_child(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        await process.wait()
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=0.25)
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


def _remove_owned_stale_socket(path: Path, *, expected_uid: int, expected_gid: int) -> None:
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISSOCK(before.st_mode)
        or before.st_uid != expected_uid
        or before.st_gid != expected_gid
    ):
        raise RuntimeError("guide parser socket path is not an owned socket")
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(0.1)
    try:
        probe.connect(str(path))
    except OSError as exc:
        if exc.errno != errno.ECONNREFUSED:
            raise RuntimeError("guide parser socket liveness is uncertain") from None
    else:
        raise RuntimeError("guide parser socket already has a live listener")
    finally:
        probe.close()
    current = os.lstat(path)
    if (
        (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
        or not stat.S_ISSOCK(current.st_mode)
        or current.st_uid != expected_uid
        or current.st_gid != expected_gid
    ):
        raise RuntimeError("guide parser socket changed during stale check")
    path.unlink()


async def _read_frame(reader: asyncio.StreamReader, *, maximum: int) -> bytes:
    size = struct.unpack(">I", await reader.readexactly(4))[0]
    if size == 0 or size > maximum:
        raise ValueError("guide parser frame is invalid")
    return await reader.readexactly(size)


async def _write_frame(writer: asyncio.StreamWriter, raw: bytes) -> None:
    if not raw or len(raw) > MAXIMUM_RESPONSE_BYTES:
        raise ValueError("guide parser response frame is invalid")
    writer.write(struct.pack(">I", len(raw)) + raw)
    await writer.drain()


def _decode_single_frame(raw: bytes, *, maximum: int) -> bytes:
    if len(raw) < 4:
        raise ValueError("guide parser child response is truncated")
    size = struct.unpack(">I", raw[:4])[0]
    if size == 0 or size > maximum or len(raw) != size + 4:
        raise ValueError("guide parser child response frame is invalid")
    return raw[4:]


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


async def _healthcheck(path: Path) -> int:
    metadata = _json_bytes(
        {"protocol_version": GUIDE_DOCUMENT_PARSER_PROTOCOL, "operation": "health"}
    )
    try:
        async with asyncio.timeout(2.0):
            reader, writer = await asyncio.open_unix_connection(path)
            try:
                writer.write(struct.pack(">I", len(metadata)) + metadata)
                await writer.drain()
                raw = await _read_frame(reader, maximum=MAXIMUM_RESPONSE_BYTES)
            finally:
                writer.close()
                await writer.wait_closed()
        body = json.loads(raw)
        if body != {
            "parser_build_digest": FIXED_PARSER_BUILD_DIGEST,
            "protocol_version": GUIDE_DOCUMENT_PARSER_PROTOCOL,
            "status": "ready",
        }:
            return 1
        return 0
    except (TimeoutError, OSError, ValueError, json.JSONDecodeError, asyncio.IncompleteReadError):
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Workstream fixed guide-document parser")
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--healthcheck", action="store_true")
    arguments = parser.parse_args()
    if arguments.healthcheck:
        return asyncio.run(_healthcheck(arguments.socket))
    service = GuideDocumentParserService(socket_path=arguments.socket)
    try:
        asyncio.run(service.serve_forever())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover - container entry point
    raise SystemExit(main())


__all__ = ("GuideDocumentParserService", "PARSER_SOCKET_DIRECTORY_MODE", "main")
