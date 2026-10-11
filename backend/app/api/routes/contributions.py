"""Bounded complete contribution evidence, with the same JSON/CSV projection."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, ValidationError

from app.api.deps.contribution_exports import (
    ContributionExportRequest, contribution_export_response, get_contribution_export_request,
)
from app.core.api_controls import ApiErrorResponse, StructuredHTTPException
from app.modules.contributions.api.records import ContributionExportResponse, ContributionReadRequest

router = APIRouter(tags=["contributions"])
_ERRORS = {status: {"model": ApiErrorResponse} for status in (404, 422, 503)}
_CSV = {"200": {"content": {"text/csv": {"schema": {"type": "string"}}}}}


def _selected(context, audience, project_id, output_format, contribution_type, recorded_from, recorded_before):
    """Bind self actor on the server and reject inverted/naive recorded-time filters."""
    try:
        return ContributionReadRequest(
            audience=audience, actor_profile_id=context.actor_profile_id, project_id=project_id,
            output_format=output_format, contribution_type=contribution_type,
            recorded_from=recorded_from, recorded_before=recorded_before,
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
):
    """Return all selected own records, refusing over 1000 instead of truncating."""
    return await contribution_export_response(context, _selected(
        context, "self", project_id, format, contribution_type, recorded_from, recorded_before,
    ))


@router.get("/projects/{project_id}/contributions/export", response_model=ContributionExportResponse,
            responses=_ERRORS | _CSV, openapi_extra={"x-workstream-action-id": "contribution.read_project"})
async def export_project_contributions(
    project_id: UUID,
    context: Annotated[ContributionExportRequest, Depends(get_contribution_export_request)],
    format: Literal["json", "csv"] = "json",
    contribution_type: Literal["accepted_submission", "completed_review"] | None = None,
    recorded_from: AwareDatetime | None = None, recorded_before: AwareDatetime | None = None,
):
    """Export one project for covering PM or exact-project Finance authority."""
    return await contribution_export_response(context, _selected(
        context, "project", project_id, format, contribution_type, recorded_from, recorded_before,
    ))
