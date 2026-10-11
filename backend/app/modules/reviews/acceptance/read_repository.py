"""REV-owned immutable FinalAcceptance projection for canonical evidence reads."""

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reviews.acceptance.models import FinalAcceptance
from app.modules.reviews.api.acceptance import FinalAcceptanceFacts


class FinalAcceptanceReadRepository:
    """Read existing source facts only, under the contribution caller's snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        """Use the export transaction without a lifecycle fence or mutation."""
        self._session = session

    async def read_final_acceptances(
        self, selectors: tuple[tuple[UUID, UUID], ...]
    ) -> tuple[FinalAcceptanceFacts, ...]:
        """Preserve the database-owned actual accepted time and complete source identity."""
        if len(selectors) > 1_000 or len(set(selectors)) != len(selectors):
            raise ValueError("invalid contribution acceptance selection")
        if not selectors:
            return ()
        rows = (await self._session.scalars(select(FinalAcceptance).where(
            tuple_(FinalAcceptance.project_id, FinalAcceptance.id).in_(
                [(str(project), acceptance) for project, acceptance in selectors]
            )
        ))).all()
        return tuple(FinalAcceptanceFacts(
            id=row.id, project_id=UUID(row.project_id), task_id=UUID(row.task_id),
            submission_id=UUID(row.submission_id), acceptance_source=row.acceptance_source,
            source_review_id=row.source_review_id,
            source_routing_manifest_id=row.source_routing_manifest_id,
            accepted_submitter_id=UUID(row.accepted_submitter_id), recorded_by=UUID(row.recorded_by),
            policy_context_ref=UUID(row.policy_context_ref),
            source_authorization_decision_id=UUID(row.source_authorization_decision_id),
            accepted_at=row.accepted_at,
        ) for row in rows)
