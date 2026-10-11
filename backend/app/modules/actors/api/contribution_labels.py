"""Bounded contributor display labels for already-authorized canonical evidence."""

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContributionActorLabel(BaseModel):
    """Public display text only; no identity links, subjects, email or profile status."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
    actor_profile_id: UUID
    display_name: str | None


class ContributionActorLabelPort(Protocol):
    """CON owns disclosure authority over the exact selected contributor IDs."""

    async def read_contribution_labels(
        self, actor_ids: tuple[UUID, ...]
    ) -> tuple[ContributionActorLabel, ...]:
        """Load only the bounded selected contributor display labels."""
        ...
