"""AUTH-owned atomic publication boundary for supported assignment authority loss."""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict


class AuthorityInvalidationPublicationUnavailable(RuntimeError):
    """Sanitized failure requiring rollback of the originating authority mutation."""


class AuthorityInvalidationPublication(BaseModel):
    """Exact newly staged cause facts; never a retained-event discovery request."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    cause_event_id: UUID
    cause_event_type: Literal[
        "ProjectRoleGrantRevoked", "ActorProfileSuspended",
        "ActorProfileDeactivated", "ActorIdentityLinkRevoked",
    ]
    invalidation_event_id: UUID
    contributor_id: UUID
    project_id: UUID | None
    correlation_id: str
    invalidated_at: AwareDatetime


class AuthorityInvalidationPublicationPort(Protocol):
    async def publish(self, facts: AuthorityInvalidationPublication) -> None:
        """Append every exact target in the caller's existing transaction."""
        ...
