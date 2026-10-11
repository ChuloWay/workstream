"""Bounded complete contribution evidence, with the same JSON/CSV projection."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, ValidationError

from app.api.deps.contribution_exports import (
    ContributionExportRequest, contribution_export_response, get_contribution_export_request,
)
from app.core.api_controls import ApiErrorResponse, StructuredHTTPException
from app.modules.contributions.api.records import ContributionExportResponse, ContributionReadRequest

router = APIRouter(tags=["contributions"])
_ERRORS = {status: {"model": ApiErrorResponse} for status in (404, 422, 503)}
_CSV = {"200": {
    "content": {"text/csv": {"schema": {"type": "string"}}},
    "headers": {
        "X-Workstream-Exported-At": {"description": "CSV original export instant, identical on every page",
                                    "schema": {"type": "string", "format": "date-time"}},
        "X-Workstream-Next-Cursor": {"description": "CSV continuation; absent on the final page",
                                    "schema": {"type": "string", "maxLength": 4096}},
    },
}}


def _selected(context, audience, project_id, output_format, contribution_type, recorded_from, recorded_before,
              page_size, cursor):
    """Bind self actor on the server and reject inverted/naive recorded-time filters."""
    try:
        return ContributionReadRequest(
            audience=audience, actor_profile_id=context.actor_profile_id, project_id=project_id,
            output_format=output_format, contribution_type=contribution_type,
            recorded_from=recorded_from, recorded_before=recorded_before, page_size=page_size, cursor=cursor,
        )
    except ValidationError as exc:
        raise StructuredHTTPException(status_code=422, detail="contribution_export_invalid",
                                      error_code="contribution_export_invalid",
                                      error_message="Invalid contribution export filters") from exc


@router.get("/actors/me/contributions", response_model=ContributionExportResponse,
            responses=_ERRORS | _CSV, openapi_extra={"x-workstream-action-id": "contribution.read_self"})
async def read_own_contributions(
    context: Annotated[ContributionExportRequest, Depends(get_contribution_export_request)],
    project_id: UUID | None = None, format: Literal["json", "csv"] = "json",
    contribution_type: Literal["accepted_submission", "completed_review"] | None = None,
    recorded_from: AwareDatetime | None = None, recorded_before: AwareDatetime | None = None,
    page_size: Annotated[int, Query(ge=1, le=1000)] = 100,
    cursor: Annotated[str | None, Query(min_length=1, max_length=4096,
                                       pattern=r"^[A-Za-z0-9_-]+$")] = None,
):
    """Return one authorized page of a fixed own-contribution selection."""
    return await contribution_export_response(context, _selected(
        context, "self", project_id, format, contribution_type, recorded_from, recorded_before, page_size, cursor,
    ))


@router.get("/projects/{project_id}/contributions/export", response_model=ContributionExportResponse,
            responses=_ERRORS | _CSV, openapi_extra={"x-workstream-action-id": "contribution.read_project"})
async def export_project_contributions(
    project_id: UUID,
    context: Annotated[ContributionExportRequest, Depends(get_contribution_export_request)],
    format: Literal["json", "csv"] = "json",
    contribution_type: Literal["accepted_submission", "completed_review"] | None = None,
    recorded_from: AwareDatetime | None = None, recorded_before: AwareDatetime | None = None,
    page_size: Annotated[int, Query(ge=1, le=1000)] = 100,
    cursor: Annotated[str | None, Query(min_length=1, max_length=4096,
                                       pattern=r"^[A-Za-z0-9_-]+$")] = None,
):
    """Export one project for covering PM or exact-project Finance authority."""
    return await contribution_export_response(context, _selected(
        context, "project", project_id, format, contribution_type, recorded_from, recorded_before, page_size, cursor,
    ))
