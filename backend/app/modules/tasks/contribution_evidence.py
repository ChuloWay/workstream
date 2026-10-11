"""TASK-owned exact selected source metadata for contribution evidence."""

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api.contribution_evidence import ContributionTaskEvidence
from app.modules.tasks.models import WorkstreamTask


class ContributionTaskEvidenceRepository:
    """Read task metadata without lifecycle changes or an independent disclosure grant."""

    def __init__(self, session: AsyncSession) -> None:
        """Share the caller's export snapshot and commit ownership."""
        self._session = session

    async def read_contribution_tasks(
        self, selectors: tuple[tuple[UUID, UUID], ...]
    ) -> tuple[ContributionTaskEvidence, ...]:
        """Pre-filter by both project and task before returning any source text."""
        if len(selectors) > 1_000 or len(set(selectors)) != len(selectors):
            raise ValueError("invalid contribution task selection")
        if not selectors:
            return ()
        rows = (await self._session.scalars(select(WorkstreamTask).where(
            tuple_(WorkstreamTask.project_id, WorkstreamTask.id).in_(
                [(str(project), str(task)) for project, task in selectors]
            )
        ))).all()
        return tuple(ContributionTaskEvidence(
            project_id=UUID(row.project_id), task_id=UUID(row.id), title=row.title,
            source_type=row.source_type, source_ref=row.source_ref,
            external_task_id=row.external_task_id,
        ) for row in rows)
