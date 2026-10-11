"""REV-owned source facts for already-recognized accepted contributions."""

from uuid import UUID

from app.modules.reviews.api.acceptance_reads import FinalAcceptanceReadPort
from app.modules.contributions.api.source_reads import (
    ContributionAcceptanceSourceFacts,
)


class ContributionAcceptanceSourceReadAdapter:
    """Translate REV source evidence into CON's minimal selected read contract."""

    def __init__(self, source: FinalAcceptanceReadPort) -> None:
        """Use an explicit REV read port; no acceptance operation is composed."""
        self._source = source

    async def read_final_acceptances(
        self, selectors: tuple[tuple[UUID, UUID], ...],
    ) -> tuple[ContributionAcceptanceSourceFacts, ...]:
        """Copy actual accepted time and lineage while excluding authority internals."""
        return tuple(ContributionAcceptanceSourceFacts(
            id=row.id, project_id=row.project_id, task_id=row.task_id,
            submission_id=row.submission_id, accepted_submitter_id=row.accepted_submitter_id,
            accepted_at=row.accepted_at, acceptance_source=row.acceptance_source,
            source_review_id=row.source_review_id,
            source_routing_manifest_id=row.source_routing_manifest_id,
        ) for row in await self._source.read_final_acceptances(selectors))
