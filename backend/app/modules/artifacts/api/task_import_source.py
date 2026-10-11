"""Project-bound canonical JSON source capabilities, without provider coordinates."""

from collections.abc import AsyncIterable, AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

class TaskImportSourceError(RuntimeError):
    """A closed source outcome mapped to a concealed or explicit HTTP response."""

    def __init__(self, code: str, status_code: int):
        self.code, self.status_code = code, status_code
        super().__init__(code)


class TaskImportSourceAction(StrEnum):
    """Separate source admission and read actions under covered PM authority."""

    DECLARE = "artifact.task_import_source.declare"
    UPLOAD = "artifact.task_import_source.upload"
    READ = "artifact.task_import_source.read"


class TaskImportSourceDeclare(BaseModel):
    """Exact caller byte commitment retained before any upload is admitted."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=1, le=8388608)


class TaskImportSourceResponse(BaseModel):
    """Original source commitment and ART status, without a task/batch success claim."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source_id: UUID
    project_id: UUID
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=1, le=8388608)
    media_type: Literal["application/json"] = "application/json"
    status: Literal["declared", "prepared", "put_in_flight", "acknowledgement_unknown", "object_confirmed",
                    "absent_replay_required", "integrity_mismatch", "provider_unavailable", "conflict", "verified", "missing"]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TaskImportSourceAuthorityFacts:
    """Exact source facts that AUTH binds to the current actor and identity link."""

    source_id: UUID
    project_id: UUID
    actor_profile_id: UUID
    sha256: str
    byte_count: int
    operation_identity: str
    idempotency_key: UUID


class TaskImportSourceAuthorityDenied(RuntimeError):
    """Source authority is absent or no longer current."""


class TaskImportSourceAuthorizationPort(Protocol):
    """Consume fresh exact authority and preserve denial evidence after rollback."""

    async def authorize(self, action: TaskImportSourceAction, facts: TaskImportSourceAuthorityFacts) -> UUID:
        """Return the transaction-local ALLOW decision for the exact source action."""
        ...

    async def restage_denial(self, error: TaskImportSourceAuthorityDenied) -> None:
        """Retain the original canonical denial in the caller's new transaction."""
        ...


@dataclass(frozen=True, slots=True)
class VerifiedTaskImportSourceRead:
    """Verified source metadata and bytes scoped to the owning read context."""

    source: TaskImportSourceResponse
    stream: AsyncIterator[bytes]


class VerifiedTaskImportSourceBinding(BaseModel):
    """Immutable native byte ancestry; the ART participant revalidates every reference."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source_id: UUID
    project_id: UUID
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=1, le=8388608)
    operation_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    put_attempt_id: UUID
    content_id: UUID
    replica_id: UUID
    verification_job_id: UUID
    verification_generation: int = Field(ge=1)
    verification_receipt_id: UUID
    operation_receipt_id: UUID | None
    observation_receipt_id: UUID | None

    @model_validator(mode="after")
    def exact_acknowledgement(self):
        """Require precisely one retained operation or observation acknowledgement."""
        if (self.operation_receipt_id is None) == (self.observation_receipt_id is None):
            raise ValueError("verified source requires exactly one acknowledgement")
        return self


class TaskImportSourceBindingPort(Protocol):
    """Prepare immutable source custody before caller-root AUTH and authorize it freshly."""

    async def source_commitment(self, project_id: UUID, source_id: UUID) -> TaskImportSourceAuthorityFacts:
        """Read native immutable declaration facts without claiming or granting authority."""
        ...

    async def authorize_commitment(self, facts: TaskImportSourceAuthorityFacts) -> UUID:
        """Freshly authorize actual source facts before exposing preparation outcomes."""
        ...

    async def prepare_binding(
        self, project_id: UUID, source_id: UUID,
        expected: VerifiedTaskImportSourceBinding | None = None,
    ) -> VerifiedTaskImportSourceBinding:
        """Retain SOURCE KEY SHARE and validate actual receipts without provider access."""
        ...

    async def authorize_binding(self, binding: VerifiedTaskImportSourceBinding) -> UUID:
        """Revalidate prepared custody and consume the current caller's exact source READ."""
        ...

    async def restage_denial(self, error: TaskImportSourceAuthorityDenied) -> None:
        """Retain a caller-root denial through the actual issuing source authority."""
        ...


class TaskImportSourceCommandPort(Protocol):
    """Manage source custody only; these operations never create or transition Tasks."""

    async def declare(self, project_id: UUID, payload: TaskImportSourceDeclare, key: UUID) -> TaskImportSourceResponse:
        """Create or freshly authorize exact replay of the retained project/key source."""
        ...

    async def upload(self, project_id: UUID, source_id: UUID, byte_source: AsyncIterable[bytes]) -> TaskImportSourceResponse:
        """Validate exact declared JSON bytes before existing ART durable admission."""
        ...

    async def status(self, project_id: UUID, source_id: UUID) -> TaskImportSourceResponse:
        """Return retained source/attempt state under current exact read authority."""
        ...

    def open(self, project_id: UUID, source_id: UUID) -> AbstractAsyncContextManager[VerifiedTaskImportSourceRead]:
        """Verify every provider byte before yielding a bounded source read."""
        ...
