"""Read exact selected awards; canonical disclosure authority belongs to CON."""

from dataclasses import dataclass
from decimal import Decimal
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


@dataclass(frozen=True, slots=True)
class ContributorAwardTotal:
    """The exact sum of one contributor's immutable awards in one instrument and unit."""

    instrument_type: str
    unit_code: str
    quantity: Decimal


class ContributorAwardTotalsPort(Protocol):
    """Sum a contributor's awards in an already authorized project set."""

    async def read_award_totals(
        self, contributor_id: UUID, project_ids: frozenset[UUID],
    ) -> tuple[ContributorAwardTotal, ...]: ...
