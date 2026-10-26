"""Typed private protocol for bounded invocation-local model sessions."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import hashlib
import json


MODEL_PROXY_PROTOCOL = "workstream.model_session.v2"
MODEL_PROXY_MAXIMUM_FRAME_BYTES = 1024 * 1024
MODEL_PROXY_MAXIMUM_RECEIPTS = 1000
_MODEL_GRANT_PREFIX = "model_"
_SHA256_PREFIX = "sha256:"


@dataclass(frozen=True, slots=True, repr=False)
class ModelProxyResolvedReceipt:
    """Exact retained tool receipt resolved by trusted invocation code."""

    receipt_sha256: str
    canonical_receipt_utf8: str

    def __post_init__(self) -> None:
        if not _valid_sha256(self.receipt_sha256) or type(self.canonical_receipt_utf8) is not str:
            raise ValueError("model proxy receipt is invalid")
        try:
            encoded = self.canonical_receipt_utf8.encode("utf-8")
            value = json.loads(self.canonical_receipt_utf8)
        except (UnicodeError, ValueError, TypeError):
            raise ValueError("model proxy receipt is invalid") from None
        if (
            not encoded
            or len(encoded) > MODEL_PROXY_MAXIMUM_FRAME_BYTES
            or "sha256:" + hashlib.sha256(encoded).hexdigest() != self.receipt_sha256
            or json.dumps(
                value,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            != self.canonical_receipt_utf8
        ):
            raise ValueError("model proxy receipt is invalid")

    def __repr__(self) -> str:
        return "ModelProxyResolvedReceipt(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ModelProxyRequest:
    """One strict session call; repr never exposes its grant, prompt or receipts."""

    grant_id: str
    request_digest: str
    call_index: int
    prompt: str
    resolved_receipts: tuple[ModelProxyResolvedReceipt, ...] = ()

    def __post_init__(self) -> None:
        if (
            not _valid_model_grant(self.grant_id)
            or not _valid_sha256(self.request_digest)
            or type(self.call_index) is not int
            or not 0 <= self.call_index <= 99
            or type(self.prompt) is not str
            or not self.prompt
            or type(self.resolved_receipts) is not tuple
            or len(self.resolved_receipts) > MODEL_PROXY_MAXIMUM_RECEIPTS
            or any(type(item) is not ModelProxyResolvedReceipt for item in self.resolved_receipts)
            or len({item.receipt_sha256 for item in self.resolved_receipts})
            != len(self.resolved_receipts)
        ):
            raise ValueError("model proxy request is invalid")

    def __repr__(self) -> str:
        return "ModelProxyRequest(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ModelProxyReply:
    """Provider-neutral bounded reply returned to the checker image."""

    outcome: str
    output: str | None
    receipt_digest: str | None
    failure_code: str | None
    call_index: int
    session_exhausted: bool

    def __post_init__(self) -> None:
        completed = (
            self.outcome == "completed"
            and type(self.call_index) is int
            and 0 <= self.call_index <= 99
            and type(self.output) is str
            and bool(self.output)
            and _valid_sha256(self.receipt_digest)
            and self.failure_code is None
        )
        unavailable = (
            self.outcome == "unavailable"
            and type(self.call_index) is int
            and 0 <= self.call_index <= 99
            and self.output is None
            and self.receipt_digest is None
            and _valid_failure_code(self.failure_code)
        )
        if type(self.session_exhausted) is not bool or (not completed and not unavailable):
            raise ValueError("model proxy reply is invalid")

    def __repr__(self) -> str:
        return f"ModelProxyReply(outcome={self.outcome!r}, <redacted>)"

    def wire_value(self) -> dict[str, str | None]:
        """Return the exact private protocol root without provider coordinates."""
        return {
            "protocol_version": MODEL_PROXY_PROTOCOL,
            "outcome": self.outcome,
            "output": self.output,
            "receipt_digest": self.receipt_digest,
            "failure_code": self.failure_code,
            "call_index": self.call_index,
            "session_exhausted": self.session_exhausted,
        }


ModelProxyHandler = Callable[[ModelProxyRequest], Awaitable[ModelProxyReply]]


def _valid_model_grant(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == len(_MODEL_GRANT_PREFIX) + 32
        and value.startswith(_MODEL_GRANT_PREFIX)
        and all(item in "0123456789abcdef" for item in value[len(_MODEL_GRANT_PREFIX) :])
    )


def _valid_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == len(_SHA256_PREFIX) + 64
        and value.startswith(_SHA256_PREFIX)
        and all(item in "0123456789abcdef" for item in value[len(_SHA256_PREFIX) :])
    )


def _valid_failure_code(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 64
        and value[0].islower()
        and value[0].isascii()
        and all(
            item.isascii() and (item.islower() or item.isdigit() or item == "_") for item in value
        )
    )


__all__ = (
    "MODEL_PROXY_MAXIMUM_FRAME_BYTES",
    "MODEL_PROXY_PROTOCOL",
    "ModelProxyHandler",
    "ModelProxyReply",
    "ModelProxyRequest",
    "ModelProxyResolvedReceipt",
)
