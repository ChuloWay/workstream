"""Bounded immutable authority-cause facts; no ORM records or permissions."""

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict


class AssignmentInvalidationCause(StrEnum):
    SUBMITTER_GRANT_REVOKED = "submitter_grant_revoked"
    ACTOR_SUSPENDED = "actor_suspended"
    ACTOR_DEACTIVATED = "actor_deactivated"
    IDENTITY_LINK_REVOKED = "identity_link_revoked"


class AuthorityInvalidationFacts(BaseModel):
    """Verified linked invalidation/cause, never authority to change TASK."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    invalidation_event_id: UUID
    cause_event_id: UUID
    recorded_at: AwareDatetime
    contributor_id: UUID
    cause: AssignmentInvalidationCause
    target_id: UUID
    project_id: UUID | None


class AuthorityInvalidationPort(Protocol):
    async def read_invalidation(self, event_id: UUID) -> AuthorityInvalidationFacts | None:
        """Read an exact committed supported chain, concealing every invalid case."""
        ...
