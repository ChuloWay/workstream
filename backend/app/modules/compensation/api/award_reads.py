"""Read exact selected awards; canonical disclosure authority belongs to CON."""

from typing import Protocol
from uuid import UUID

from app.modules.compensation.api.awards import CompensationAwardFacts


class ContributionAwardReadPort(Protocol):
    """Read all retained awards for a bounded already-authorized contribution set."""

    async def read_contribution_awards(
        self, contribution_ids: tuple[UUID, ...]
    ) -> tuple[CompensationAwardFacts, ...]:
        """Return exact complete owner facts, including no rows for unpaid records."""
        ...
