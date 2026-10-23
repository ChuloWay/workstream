"""Typed private protocol for request-bound checker model calls."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass


MODEL_PROXY_PROTOCOL = "workstream.checker_model_proxy.v1"
MODEL_PROXY_MAXIMUM_FRAME_BYTES = 1024 * 1024
_MODEL_GRANT_PREFIX = "model_"
_SHA256_PREFIX = "sha256:"


@dataclass(frozen=True, slots=True, repr=False)
class ModelProxyRequest:
    """One strict relay request; repr never exposes its grant or prompt."""

    grant_id: str
    request_digest: str
    prompt: str

    def __post_init__(self) -> None:
        if (
            not _valid_model_grant(self.grant_id)
            or not _valid_sha256(self.request_digest)
            or type(self.prompt) is not str
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

    def __post_init__(self) -> None:
        completed = (
            self.outcome == "completed"
            and type(self.output) is str
            and bool(self.output)
            and _valid_sha256(self.receipt_digest)
            and self.failure_code is None
        )
        unavailable = (
            self.outcome == "unavailable"
            and self.output is None
            and self.receipt_digest is None
            and _valid_failure_code(self.failure_code)
        )
        if not completed and not unavailable:
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
)
