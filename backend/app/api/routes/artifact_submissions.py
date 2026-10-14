"""Contributor ZIP preparation through ART-owned selected intake and custody."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.artifacts import (
    get_submission_bundle_preparation_actor,
    get_submission_bundle_preparation_command,
)
from app.core.api_controls import StructuredHTTPException, error_response, request_ids
from app.db.session import get_db_session
from app.modules.artifacts.api import (
    SubmissionBundlePreparationCheckFailed,
    SubmissionBundlePreparationCommand,
    SubmissionBundlePreparationRejected,
    SubmissionBundlePreparationInfrastructureUnavailable,
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationStatus,
    SubmissionBundlePreparationUnavailable,
)
from app.modules.authorization.api import ActorIdentityFacts

router = APIRouter(tags=["tasks"])


def require_single_preparation_headers(request: Request) -> None:
    """Reject ambiguous custody selectors before resolving actor or product rows."""
    for name in ("X-Task-Assignment-Id", "Idempotency-Key"):
        if len(request.headers.getlist(name)) != 1:
            raise StructuredHTTPException(
                status_code=422,
                detail="Submission preparation headers invalid",
                error_code="submission_preparation_headers_invalid",
                error_message="Submission preparation headers invalid",
            )


class SubmissionBundlePreparationResponse(BaseModel):
    """Bounded preparation state without provider or scratch coordinates."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    put_attempt_id: UUID
    admission_id: UUID | None
    submission_bundle_preparation_status: SubmissionBundlePreparationStatus
    replayed: bool


@router.post(
    "/tasks/{task_id}/submission-bundle-preparations",
    response_model=SubmissionBundlePreparationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_single_preparation_headers)],
    openapi_extra={
        "x-workstream-action-id": "artifact.submission_bundle.prepare",
        "requestBody": {
            "required": True,
            "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
        },
    },
    responses={
        404: {"description": "Task or contributor authority unavailable"},
        409: {"description": "Preparation context or replay conflicts"},
        422: {"description": "Invalid ZIP or bounded pre-submission checker feedback"},
        503: {"description": "Preparation custody or infrastructure unavailable"},
    },
)
async def prepare_submission_bundle(
    task_id: str,
    request: Request,
    actor: Annotated[ActorIdentityFacts, Depends(get_submission_bundle_preparation_actor)],
    command: Annotated[
        SubmissionBundlePreparationCommand,
        Depends(get_submission_bundle_preparation_command),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    assignment_id: Annotated[str, Header(alias="X-Task-Assignment-Id")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    summary: Annotated[str | None, Header(alias="X-Submission-Summary")] = None,
    contributor_attestation: Annotated[
        str | None, Header(alias="X-Contributor-Attestation")
    ] = None,
    predecessor_submission_id: Annotated[
        str | None, Header(alias="X-Predecessor-Submission-Id")
    ] = None,
) -> SubmissionBundlePreparationResponse | JSONResponse:
    """Run continuous ZIP preparation under fresh contributor authority."""
    try:
        identifiers = (
            UUID(task_id),
            UUID(assignment_id),
            UUID(idempotency_key),
            UUID(predecessor_submission_id) if predecessor_submission_id else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    try:
        # Actor resolution may have opened a read root; ART owns its preparation roots.
        await session.rollback()
        request_id, correlation_id = (UUID(value) for value in request_ids(request))
        result = await command.prepare(
            SubmissionBundlePreparationRequest(
                actor=actor,
                request_id=request_id,
                correlation_id=correlation_id,
                task_id=identifiers[0],
                assignment_id=identifiers[1],
                predecessor_submission_id=identifiers[3],
                idempotency_key=identifiers[2],
                summary=summary or "",
                contributor_attestation=contributor_attestation or "",
                media_type=request.headers.get("content-type", ""),
                byte_source=request.stream(),
            )
        )
    except SubmissionBundlePreparationCheckFailed as exc:
        return error_response(
            request,
            status_code=422,
            code="pre_submission_checker_failed",
            message="Pre-submission checks failed",
            details={
                "status": "failed",
                "eligible_to_submit": exc.facts.eligible,
                "results": exc.public_results(),
            },
        )
    except SubmissionBundlePreparationInfrastructureUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SubmissionBundlePreparationUnavailable as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except SubmissionBundlePreparationRejected as exc:
        code = str(exc)
        if code in {"submission_bundle_preparation_context_changed",
                    "submission_bundle_preparation_request_conflict", "revision_limit_reached"}:
            raise HTTPException(status_code=409, detail=code) from exc
        raise HTTPException(status_code=422, detail=code) from exc
    return SubmissionBundlePreparationResponse.model_validate(result, from_attributes=True)
