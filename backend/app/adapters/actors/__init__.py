"""ACTORS-owned composition for narrowly selected contribution display labels."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.api.contribution_labels import ContributionActorLabelPort
from app.modules.actors.contribution_labels import ContributionActorLabelRepository


def contribution_actor_label_port(session: AsyncSession) -> ContributionActorLabelPort:
    """Read selected labels on the export's authorized caller-owned snapshot."""
    return ContributionActorLabelRepository(session)
