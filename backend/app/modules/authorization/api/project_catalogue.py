"""Current system-covered authority for a bounded project identity page."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProjectCatalogueRequest:
    actor_profile_id: UUID
    limit: int
    cursor: str | None

    def __post_init__(self) -> None:
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
    position: UUID | None


class ProjectCatalogueCursorInvalid(ValueError):
    """A malformed, forged or substituted continuation."""


class ProjectCatalogueUnavailable(RuntimeError):
    """Required signed-cursor configuration is unavailable."""


class ProjectCatalogueAuthorizationPort(Protocol):
    async def authorize(self, request: ProjectCatalogueRequest) -> ProjectCatalogueGrant: ...

    def encode(self, request: ProjectCatalogueRequest, position: UUID) -> str: ...
