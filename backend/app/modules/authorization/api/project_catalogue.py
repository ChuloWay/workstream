"""Current system-covered authority for a bounded project identity page."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProjectCatalogueRequest:
    """One actor-bound page request with bounded cursor and page size."""

    actor_profile_id: UUID
    limit: int
    cursor: str | None

    def __post_init__(self) -> None:
        """Reject malformed requests before authority or cursor processing."""
        if (
            not isinstance(self.actor_profile_id, UUID)
            or not isinstance(self.limit, int)
            or not 1 <= self.limit <= 100
            or (
                self.cursor is not None
                and (not isinstance(self.cursor, str) or not 1 <= len(self.cursor) <= 512)
            )
        ):
            raise ValueError("invalid project catalogue request")


@dataclass(frozen=True, slots=True)
class ProjectCatalogueGrant:
    """An authorized page boundary, not reusable authority for another read."""

    position: UUID | None


class ProjectCatalogueCursorInvalid(ValueError):
    """A malformed, forged or substituted continuation."""


class ProjectCatalogueUnavailable(RuntimeError):
    """Required signed-cursor configuration is unavailable."""


class ProjectCatalogueAuthorizationPort(Protocol):
    """Authorize each current request and bind its public ID continuation."""

    async def authorize(self, request: ProjectCatalogueRequest) -> ProjectCatalogueGrant:
        """Lock current system-reader authority before parsing a continuation."""
        ...

    def encode(self, request: ProjectCatalogueRequest, position: UUID) -> str:
        """Sign a disclosed ID for this actor, action, ordering and page size."""
        ...
