"""Exact retained acceptance facts for contribution evidence; no acceptance command."""

from typing import Protocol
from uuid import UUID

from app.modules.reviews.api.acceptance import FinalAcceptanceFacts


class FinalAcceptanceReadPort(Protocol):
    """Read existing immutable sources from the caller's authorized contribution set."""

    async def read_final_acceptances(
        self, selectors: tuple[tuple[UUID, UUID], ...]
    ) -> tuple[FinalAcceptanceFacts, ...]:
        """Select exact project/acceptance pairs without creating source evidence."""
        ...
