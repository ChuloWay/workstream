"""Public exact-project manager activation; readiness belongs to PROJECTS."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import TypeAdapter, ValidationError
from pydantic_core import PydanticSerializationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.guide_activation import ActivationRequest, get_activation_request
from app.api.deps.guide_proposal_http import (
    IDEMPOTENCY_PARAMETER, proposal_http_error, require_proposal_key,
)
from app.core.api_controls import ApiErrorResponse
from app.modules.projects.api.guide_activation import (
    GuideActivationCommand, GuideActivationInput, GuideActivationReceipt,
)
from app.modules.projects.api.guide_proposals import GuideProposalError

router = APIRouter(
    prefix="/projects/{project_id}/guides/{guide_id}", tags=["projects"],
    dependencies=[Depends(enforce_human_authorization_read)],
    responses={code: {"model": ApiErrorResponse} for code in (404, 409, 422, 503)},
)


@router.post(
    "/activate", response_model=GuideActivationReceipt,
    openapi_extra={"x-workstream-action-id": "project.guide.activate", "parameters": [IDEMPOTENCY_PARAMETER]},
    dependencies=[Depends(require_proposal_key)],
)
async def activate_guide(
    project_id: UUID, guide_id: UUID, payload: GuideActivationInput,
    key: Annotated[UUID, Depends(require_proposal_key)],
    request: Annotated[ActivationRequest, Depends(get_activation_request)],
) -> GuideActivationReceipt:
    """Bind displayed selections atomically; retries preserve the original receipt."""
    if (payload.target.proposal.project_id, payload.target.proposal.guide_id) != (project_id, guide_id):
        raise proposal_http_error(GuideProposalError("proposal_unavailable"))
    try:
        response = await request.service.activate(
            GuideActivationCommand(**payload.model_dump(), idempotency_key=key),
            actor=request.actor, request_id=request.request_id,
        )
        adapter = TypeAdapter(GuideActivationReceipt)
        detached = adapter.validate_json(adapter.dump_json(response, warnings="error"))
        await request.session.commit()
        return detached
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
    except (SQLAlchemyError, ValidationError, PydanticSerializationError) as exc:
        raise proposal_http_error(GuideProposalError("storage_unavailable")) from exc
