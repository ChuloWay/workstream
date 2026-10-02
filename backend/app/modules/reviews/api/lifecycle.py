"""Shared lifecycle fence facts, never an authorization capability."""

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class JointLifecyclePhase(StrEnum):
    """REV-owned lifecycle vocabulary; transition semantics require its owner."""

    DISABLED = "disabled"
    SHADOW = "shadow"
    LIVE = "live"
    DRAINING = "draining"


class JointLifecycleUnavailable(RuntimeError):
    """The caller cannot obtain the expected canonical lifecycle fence."""


class JointLifecycleControlFacts(BaseModel):
    """Detached state read while the caller's root transaction holds the fence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    singleton_id: UUID
    phase: JointLifecyclePhase
    generation: int = Field(ge=0, le=9_223_372_036_854_775_807)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_genesis(self):
        """Reject malformed identities and generation-zero activation claims."""
        if self.singleton_id.version != 7:
            raise ValueError("lifecycle singleton must be UUIDv7")
        if self.generation == 0 and self.phase is not JointLifecyclePhase.DISABLED:
            raise ValueError("lifecycle generation zero must be disabled")
        return self


class JointLifecycleMutationFence(Protocol):
    """Serialize through the caller's active root transaction, without committing.

    Facts are mechanical custody, not AUTH or permission to write. The caller
    must retain the transaction through every protected operation and roll back
    after acquisition fails. PostgreSQL rejects managed and raw-SQL savepoints;
    prior root-level queries remain permitted. The native root check retains a
    discarded export snapshot until transaction end, so keep transactions short.
    PostgreSQL two-phase prepare is unsupported.
    """

    async def acquire(self, expected_generation: int) -> JointLifecycleControlFacts:
        """Lock the canonical controller or deny stale/malformed transaction state."""
        ...
