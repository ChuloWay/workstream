"""Closed private protocol for setup-agent provider dispatches."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Literal, Protocol
from uuid import UUID

SETUP_MODEL_PROXY_PROTOCOL = "workstream.setup_model_proxy.v1"
SETUP_MODEL_PROXY_MAXIMUM_FRAME_BYTES = 1024 * 1024
SetupModelPhase = Literal["draft", "review", "correction"]


def canonical_provider_json(value: Mapping[str, object]) -> str:
    """Encode one provider request/response without duplicate or non-finite values."""
    if not isinstance(value, Mapping):
        raise TypeError("setup model provider JSON is invalid")
    encoded = json.dumps(
        dict(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    if not encoded or len(encoded.encode("utf-8")) > SETUP_MODEL_PROXY_MAXIMUM_FRAME_BYTES:
        raise ValueError("setup model provider JSON is invalid")
    return encoded


@dataclass(frozen=True, slots=True)
class SetupModelProxySubject:
    """Exact setup attempt and locked model profile bound by trusted composition."""

    compilation_attempt_id: UUID
    project_id: UUID
    guide_id: UUID
    source_snapshot_id: UUID
    setup_run_id: UUID
    setup_generation: int
    runtime_configuration_hash: str
    profile_id: UUID
    profile_version: int
    profile_digest: str
    provider: str
    api: str
    model: str

    def __post_init__(self) -> None:
        """Reject incomplete, substituted or non-canonical setup lineage."""
        if (
            any(
                type(value) is not UUID
                for value in (
                    self.compilation_attempt_id,
                    self.project_id,
                    self.guide_id,
                    self.source_snapshot_id,
                    self.setup_run_id,
                    self.profile_id,
                )
            )
            or type(self.setup_generation) is not int
            or self.setup_generation < 1
            or type(self.profile_version) is not int
            or self.profile_version < 1
            or not _valid_sha256(self.runtime_configuration_hash)
            or not _valid_sha256(self.profile_digest)
            or any(not _valid_identifier(value) for value in (self.provider, self.api))
            or not _valid_model(self.model)
        ):
            raise ValueError("setup model proxy subject is invalid")


@dataclass(frozen=True, slots=True, repr=False)
class SetupModelProxyRequest:
    """One actual provider dispatch, with no caller-controlled endpoint or credential."""

    subject: SetupModelProxySubject
    phase: SetupModelPhase
    call_index: int
    provider_request_json: str

    def __post_init__(self) -> None:
        """Require a canonical provider request and bounded stable call index."""
        if (
            type(self.subject) is not SetupModelProxySubject
            or self.phase not in {"draft", "review", "correction"}
            or type(self.call_index) is not int
            or not 0 <= self.call_index <= 99
            or type(self.provider_request_json) is not str
        ):
            raise ValueError("setup model proxy request is invalid")
        try:
            value = json.loads(self.provider_request_json)
        except (TypeError, ValueError, UnicodeError):
            raise ValueError("setup model proxy request is invalid") from None
        if (
            not isinstance(value, dict)
            or canonical_provider_json(value) != self.provider_request_json
        ):
            raise ValueError("setup model proxy request is invalid")

    @property
    def request_sha256(self) -> str:
        """Hash exact provider bytes independently of transport framing."""
        return "sha256:" + hashlib.sha256(self.provider_request_json.encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        """Hide prompt and provider payload content from diagnostic output."""
        return "SetupModelProxyRequest(<redacted>)"

    def wire_value(self) -> dict[str, object]:
        """Return the exact closed private wire root."""
        return {
            "protocol_version": SETUP_MODEL_PROXY_PROTOCOL,
            "operation": "dispatch",
            **{
                key: str(value) if isinstance(value, UUID) else value
                for key, value in asdict(self.subject).items()
            },
            "phase": self.phase,
            "call_index": self.call_index,
            "provider_request_json": self.provider_request_json,
        }


@dataclass(frozen=True, slots=True, repr=False)
class SetupModelProxyReply:
    """Exact provider HTTP result or one closed infrastructure failure."""

    outcome: Literal["completed", "unavailable"]
    call_index: int
    status_code: int | None
    response_json: str | None
    response_headers: tuple[tuple[str, str], ...]
    failure_code: str | None
    session_exhausted: bool

    def __post_init__(self) -> None:
        """Validate completed or unavailable wire state and its frame bound."""
        completed = (
            self.outcome == "completed"
            and type(self.status_code) is int
            and 100 <= self.status_code <= 599
            and type(self.response_json) is str
            and self.failure_code is None
        )
        unavailable = (
            self.outcome == "unavailable"
            and self.status_code is None
            and self.response_json is None
            and _valid_identifier(self.failure_code)
        )
        if (
            type(self.call_index) is not int
            or not 0 <= self.call_index <= 99
            or type(self.session_exhausted) is not bool
            or type(self.response_headers) is not tuple
            or not _valid_headers(self.response_headers)
            or (not completed and not unavailable)
        ):
            raise ValueError("setup model proxy reply is invalid")
        if completed:
            try:
                value = json.loads(self.response_json)
            except (TypeError, ValueError, UnicodeError):
                raise ValueError("setup model proxy reply is invalid") from None
            if not isinstance(value, dict) or canonical_provider_json(value) != self.response_json:
                raise ValueError("setup model proxy reply is invalid")
        encoded = json.dumps(
            self.wire_value(),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if not encoded or len(encoded) > SETUP_MODEL_PROXY_MAXIMUM_FRAME_BYTES:
            raise ValueError("setup model proxy reply exceeds transport bound")

    def __repr__(self) -> str:
        """Expose only the outcome while redacting retained provider content."""
        return f"SetupModelProxyReply(outcome={self.outcome!r}, <redacted>)"

    def wire_value(self) -> dict[str, object]:
        """Return the closed response root used by private framing."""
        return {
            "protocol_version": SETUP_MODEL_PROXY_PROTOCOL,
            "operation": "dispatch",
            "outcome": self.outcome,
            "call_index": self.call_index,
            "status_code": self.status_code,
            "response_json": self.response_json,
            "response_headers": dict(self.response_headers),
            "failure_code": self.failure_code,
            "session_exhausted": self.session_exhausted,
        }


class SetupModelDispatchPort(Protocol):
    """Attempt-bound capability used at each native SDK HTTP boundary."""

    @property
    def maximum_output_tokens(self) -> int:
        """Return the immutable completion-token ceiling."""
        ...

    @property
    def reasoning_effort(self) -> str:
        """Return the immutable reasoning setting."""
        ...

    @property
    def text_verbosity(self) -> str:
        """Return the immutable text-verbosity setting."""
        ...

    async def dispatch(
        self, phase: SetupModelPhase, provider_request: Mapping[str, object]
    ) -> SetupModelProxyReply:
        """Dispatch one phase call through the trusted metered boundary."""
        ...


SetupModelProxyHandler = Callable[[SetupModelProxyRequest], Awaitable[SetupModelProxyReply]]


def setup_model_proxy_request_from_wire(value: object) -> SetupModelProxyRequest:
    """Decode one already duplicate-checked JSON root through the closed contract."""
    expected = {
        "protocol_version",
        "operation",
        "compilation_attempt_id",
        "project_id",
        "guide_id",
        "source_snapshot_id",
        "setup_run_id",
        "setup_generation",
        "runtime_configuration_hash",
        "profile_id",
        "profile_version",
        "profile_digest",
        "provider",
        "api",
        "model",
        "phase",
        "call_index",
        "provider_request_json",
    }
    if (
        type(value) is not dict
        or set(value) != expected
        or value["protocol_version"] != SETUP_MODEL_PROXY_PROTOCOL
        or value["operation"] != "dispatch"
    ):
        raise ValueError("setup model proxy request root is invalid")
    try:
        subject = SetupModelProxySubject(
            compilation_attempt_id=UUID(value["compilation_attempt_id"]),
            project_id=UUID(value["project_id"]),
            guide_id=UUID(value["guide_id"]),
            source_snapshot_id=UUID(value["source_snapshot_id"]),
            setup_run_id=UUID(value["setup_run_id"]),
            setup_generation=value["setup_generation"],
            runtime_configuration_hash=value["runtime_configuration_hash"],
            profile_id=UUID(value["profile_id"]),
            profile_version=value["profile_version"],
            profile_digest=value["profile_digest"],
            provider=value["provider"],
            api=value["api"],
            model=value["model"],
        )
    except (TypeError, ValueError, AttributeError):
        raise ValueError("setup model proxy request root is invalid") from None
    return SetupModelProxyRequest(
        subject=subject,
        phase=value["phase"],
        call_index=value["call_index"],
        provider_request_json=value["provider_request_json"],
    )


def _valid_sha256(value: object) -> bool:
    """Recognize one exact lowercase prefixed SHA-256 digest."""
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _valid_identifier(value: object) -> bool:
    """Recognize one bounded lowercase protocol identifier."""
    return (
        type(value) is str
        and 1 <= len(value) <= 64
        and value[0].isascii()
        and value[0].islower()
        and all(
            character.isascii()
            and (character.islower() or character.isdigit() or character in {"_", ".", "-"})
            for character in value
        )
    )


def _valid_model(value: object) -> bool:
    """Recognize one bounded direct provider model identifier."""
    return (
        type(value) is str
        and 1 <= len(value) <= 200
        and value[0].isalnum()
        and value[0].isascii()
        and all(
            character.isascii() and (character.isalnum() or character in "._:/-")
            for character in value
        )
    )


def _valid_headers(value: tuple[tuple[str, str], ...]) -> bool:
    """Accept only sorted bounded retry guidance headers."""
    allowed = {"retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"}
    names = [name for name, _ in value]
    return (
        names == sorted(names)
        and len(names) == len(set(names))
        and all(
            name in allowed
            and type(item) is str
            and len(item.encode("ascii", errors="ignore")) <= 256
            and all(32 <= ord(character) <= 126 for character in item)
            for name, item in value
        )
    )


__all__ = (
    "SETUP_MODEL_PROXY_MAXIMUM_FRAME_BYTES",
    "SETUP_MODEL_PROXY_PROTOCOL",
    "SetupModelDispatchPort",
    "SetupModelPhase",
    "SetupModelProxyHandler",
    "SetupModelProxyReply",
    "SetupModelProxyRequest",
    "SetupModelProxySubject",
    "canonical_provider_json",
    "setup_model_proxy_request_from_wire",
)
