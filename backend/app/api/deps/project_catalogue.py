"""Compose one system-authorized project identity page without guide disclosure."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.authorization import get_authorization_actor_identity, get_authorization_service
from app.api.deps.snapshot_reads import run_snapshot_read
from app.core.api_controls import StructuredHTTPException
from app.db.session import get_db_session
from app.modules.authorization.api import ActorIdentityFacts
from app.modules.authorization.api.project_catalogue import (
    ProjectCatalogueAuthorizationPort,
    ProjectCatalogueCursorInvalid,
    ProjectCatalogueRequest,
    ProjectCatalogueUnavailable,
)
from app.modules.projects.api.project_summaries import ProjectCatalogueReadPort, ProjectStatus


_FROZEN = ConfigDict(extra="forbid", frozen=True)


class ProjectCatalogueItem(BaseModel):
    """The complete public row: no guide, grant, actor or management facts."""

    model_config = _FROZEN
    project_id: UUID
    name: str
    status: ProjectStatus


class ProjectCataloguePage(BaseModel):
    model_config = _FROZEN
    items: tuple[ProjectCatalogueItem, ...]
    next_cursor: str | None


def _cursor_invalid() -> StructuredHTTPException:
    return StructuredHTTPException(
        status_code=422,
        detail="Invalid project catalogue cursor",
        error_code="project_catalogue_cursor_invalid",
        error_message="Invalid project catalogue cursor",
    )


def _unavailable() -> StructuredHTTPException:
    return StructuredHTTPException(
        status_code=503,
        detail="Project catalogue unavailable",
        error_code="project_catalogue_unavailable",
        error_message="Project catalogue unavailable",
        retryable=True,
    )


class ProjectCatalogueReadOperation:
    """AUTH decision and PROJECTS page share one repeatable-read response transaction."""

    def __init__(
        self,
        session: AsyncSession,
        actor_profile_id: UUID,
        authority: ProjectCatalogueAuthorizationPort,
        projects: ProjectCatalogueReadPort,
    ) -> None:
        self._session, self._actor_id = session, actor_profile_id
        self._authority, self._projects = authority, projects

    async def list(self, *, limit: int, cursor: str | None) -> ProjectCataloguePage:
        request = ProjectCatalogueRequest(
            actor_profile_id=self._actor_id, limit=limit, cursor=cursor
        )

        async def read(grant):
            rows, more = await self._projects.read_project_catalogue(
                after=grant.position, limit=limit
            )
            last = rows[-1] if rows else None
            return ProjectCataloguePage(
                items=tuple(
                    ProjectCatalogueItem(
                        project_id=row.project_id,
                        name=row.name,
                        status=row.status,
                    )
                    for row in rows
                ),
                next_cursor=(
                    self._authority.encode(request, last.project_id) if more and last else None
                ),
            )

        return await run_snapshot_read(
            self._session,
            lambda: self._authority.authorize(request),
            read,
            cursor_invalid=ProjectCatalogueCursorInvalid,
            invalid_cursor=_cursor_invalid,
            faults=(ProjectCatalogueUnavailable, SQLAlchemyError, ValueError),
            unavailable=_unavailable,
        )


async def get_project_catalogue_reads(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: Annotated[ActorIdentityFacts, Depends(get_authorization_actor_identity)],
    authority: Annotated[object, Depends(get_authorization_service)],
) -> ProjectCatalogueReadOperation:
    """Wire public AUTH and PROJECTS ports at the API composition root."""
    from app.adapters.auth import project_catalogue_authorization
    from app.adapters.projects import project_summary_reader

    return ProjectCatalogueReadOperation(
        session,
        actor.actor_profile_id,
        project_catalogue_authorization(
            authority, request.app.state.settings.pagination_cursor_hmac_secret
        ),
        project_summary_reader(session),
    )
