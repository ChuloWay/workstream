"""PROJECTS-owned minimal identity rows for an already authorized project set."""

from uuid import UUID

from sqlalchemy import and_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.api.project_summaries import (
    ActiveGuideIdentity, ProjectCatalogueFacts, ProjectSummaryFacts,
)
from app.modules.projects.models import Project, ProjectGuide


class ProjectSummaryReader:
    """Fixed columns only; the caller owns authority and the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_project_catalogue(self, *, after, limit):
        """One bounded all-project identity page; never join guide or actor rows."""
        statement = select(Project.id, Project.name, Project.status, Project.created_at)
        if after is not None:
            statement = statement.where(tuple_(Project.created_at, Project.id) > (after[0], str(after[1])))
        rows = (await self._session.execute(
            statement.order_by(Project.created_at, Project.id).limit(limit + 1),
        )).all()
        return tuple(
            ProjectCatalogueFacts(
                project_id=UUID(str(row.id)), name=row.name, status=row.status, created_at=row.created_at,
            )
            for row in rows[:limit]
        ), len(rows) > limit

    async def read_project_summaries(self, project_ids, *, after, limit):
        if not project_ids:
            return (), False
        statement = select(
            Project.id, Project.name, Project.status, Project.created_at,
            ProjectGuide.id.label("guide_id"), ProjectGuide.version,
        ).outerjoin(ProjectGuide, and_(
            ProjectGuide.project_id == Project.id, ProjectGuide.status == "active",
        )).where(Project.id.in_([str(item) for item in project_ids]))
        if after is not None:
            statement = statement.where(tuple_(Project.created_at, Project.id) > (after[0], str(after[1])))
        rows = (await self._session.execute(
            statement.order_by(Project.created_at, Project.id).limit(limit + 1),
        )).all()
        return tuple(
            ProjectSummaryFacts(
                project_id=UUID(str(row.id)), name=row.name, status=row.status, created_at=row.created_at,
                active_guide=(
                    ActiveGuideIdentity(UUID(str(row.guide_id)), row.version)
                    if row.guide_id is not None else None
                ),
            )
            for row in rows[:limit]
        ), len(rows) > limit
