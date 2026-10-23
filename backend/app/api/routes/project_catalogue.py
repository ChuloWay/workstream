"""Minimal system-covered project discovery; exact membership remains separate."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.project_catalogue import (
    ProjectCataloguePage, ProjectCatalogueReadOperation, get_project_catalogue_reads,
)
from app.core.api_controls import ApiErrorResponse

router = APIRouter(dependencies=[Depends(enforce_human_authorization_read)])
Reads = Annotated[ProjectCatalogueReadOperation, Depends(get_project_catalogue_reads)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageCursor = Annotated[str | None, Query(min_length=1, max_length=512)]
_ERRORS = {status: {"model": ApiErrorResponse} for status in (404, 422, 503)}


@router.get(
    "/projects", response_model=ProjectCataloguePage, tags=["projects"],
    responses=_ERRORS, openapi_extra={"x-workstream-action-id": "project.catalogue.list"},
)
async def list_system_covered_projects(
    reads: Reads, limit: PageLimit = 50, cursor: PageCursor = None,
) -> ProjectCataloguePage:
    """One current system Project Reader's ID/name/status page, with no guide facts."""
    return await reads.list(limit=limit, cursor=cursor)
