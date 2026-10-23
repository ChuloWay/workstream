"""Fixed per-call parser subprocess entry point."""

from __future__ import annotations

import json
import struct
import sys

from .identity import child_identity_from_environment


def main() -> int:
    """Verify isolation before importing parsers or reading one framed source."""
    try:
        child_identity_from_environment()
    except RuntimeError:
        return 2
    return _run_protocol()


def _run_protocol() -> int:
    """Read exactly one framed source and emit one bounded framed result."""
    from pydantic import ValidationError

    from .contracts import (
        GUIDE_DOCUMENT_PARSER_PROTOCOL,
        GuideDocumentParserRequest,
        MAXIMUM_REQUEST_METADATA_BYTES,
        MAXIMUM_RESPONSE_BYTES,
    )
    from .parsing import ParserDocumentRejected, parse_document

    try:
        header = _read_exact(4)
        metadata_size = struct.unpack(">I", header)[0]
        if metadata_size == 0 or metadata_size > MAXIMUM_REQUEST_METADATA_BYTES:
            return 2
        metadata = json.loads(_read_exact(metadata_size))
        if (
            type(metadata) is not dict
            or set(metadata) != {"protocol_version", "operation", "request"}
            or metadata["protocol_version"] != GUIDE_DOCUMENT_PARSER_PROTOCOL
            or metadata["operation"] != "parse"
        ):
            return 2
        request = GuideDocumentParserRequest.model_validate(metadata["request"])
        source = _read_exact(request.source_byte_count)
        if sys.stdin.buffer.read(1):
            return 2
        result = parse_document(request, source)
        body = {
            "protocol_version": GUIDE_DOCUMENT_PARSER_PROTOCOL,
            "status": "ok",
            "result": result.model_dump(mode="json"),
        }
    except ParserDocumentRejected as exc:
        body = {
            "protocol_version": GUIDE_DOCUMENT_PARSER_PROTOCOL,
            "status": "rejected",
            "reason": exc.reason,
        }
    except (EOFError, ValueError, TypeError, UnicodeError, json.JSONDecodeError, ValidationError):
        return 2
    raw = _json_bytes(body)
    if not raw or len(raw) > MAXIMUM_RESPONSE_BYTES:
        return 2
    sys.stdout.buffer.write(struct.pack(">I", len(raw)))
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    return 0


def _read_exact(size: int) -> bytes:
    value = sys.stdin.buffer.read(size)
    if len(value) != size:
        raise EOFError
    return value


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


if __name__ == "__main__":  # pragma: no cover - exercised through the service subprocess
    raise SystemExit(main())


__all__ = ("main",)
