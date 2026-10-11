"""ACTORS-owned bounded labels for canonical contribution export."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.api.contribution_labels import ContributionActorLabel
from app.modules.actors.models import ActorProfile


class ContributionActorLabelRepository:
    """Project only display names; authorization and transaction belong to the caller."""

    def __init__(self, session: AsyncSession) -> None:
        """Retain the caller's single-response snapshot without committing."""
        self._session = session

    async def read_contribution_labels(
        self, actor_ids: tuple[UUID, ...]
    ) -> tuple[ContributionActorLabel, ...]:
        """Return no profile internals beyond selected ID/display text."""
        if len(actor_ids) > 1_000 or len(set(actor_ids)) != len(actor_ids):
            raise ValueError("invalid contribution actor selection")
        if not actor_ids:
            return ()
        rows = (await self._session.execute(select(
            ActorProfile.id, ActorProfile.display_name,
        ).where(ActorProfile.id.in_([str(actor_id) for actor_id in actor_ids])))).all()
        return tuple(ContributionActorLabel(
            actor_profile_id=UUID(actor_id), display_name=display_name,
        ) for actor_id, display_name in rows)
