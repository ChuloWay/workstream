"""Public inspection and separate manager decisions on an exact derived policy."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.guide_proposal_http import (
    IDEMPOTENCY_PARAMETER, proposal_http_error, require_matching_target, require_proposal_key,
)
from app.api.deps.post_policy import PostPolicyRequest, get_post_policy_request
from app.core.api_controls import ApiErrorResponse
from app.modules.checkers.api.post_submit_catalogue import CompiledPostSubmitPolicy
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.api.post_policy import (
    PostPolicyApproval, PostPolicyApprovalInput, PostPolicyCorrection, PostPolicyCorrectionInput,
    PostPolicyReceipt, PostPolicyReviewPackage, PostPolicySelection, PostPolicyTarget,
)

router = APIRouter(
    prefix="/projects/{project_id}/guides/{guide_id}/compilations/{compilation_id}"
           "/post-submission-policies/{policy_id}",
    tags=["projects"], dependencies=[Depends(enforce_human_authorization_read)],
    responses={code: {"model": ApiErrorResponse} for code in (404, 409, 422, 503)},
)


def require_policy_target(
    target: PostPolicyTarget, project_id: UUID, guide_id: UUID,
    compilation_id: UUID, policy_id: UUID,
) -> None:
    """Bind every body identity to the selected public resource."""
    require_matching_target(target.proposal, project_id, guide_id, compilation_id)
    if target.policy_id != policy_id:
        raise proposal_http_error(GuideProposalError("proposal_unavailable"))


@router.get(
    "", response_model=PostPolicyReviewPackage[CompiledPostSubmitPolicy],
    openapi_extra={"x-workstream-action-id": "project.guide_compilation.review_package.read"},
)
async def read_post_policy(
    project_id: UUID, guide_id: UUID, compilation_id: UUID, policy_id: UUID,
    request: Annotated[PostPolicyRequest, Depends(get_post_policy_request)],
) -> PostPolicyReviewPackage[CompiledPostSubmitPolicy]:
    """Read the complete canonical body and discover any saved correction."""
    try:
        response = await request.service.review_package(
            PostPolicySelection(project_id=project_id, guide_id=guide_id,
                                compilation_id=compilation_id, policy_id=policy_id),
            actor=request.actor, request_id=request.request_id,
        )
        await request.session.commit()
        return response
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
    except SQLAlchemyError as exc:
        raise proposal_http_error(GuideProposalError("storage_unavailable")) from exc


@router.post(
    "/approval", response_model=PostPolicyReceipt,
    openapi_extra={"x-workstream-action-id": "project.post_submit_checker_policy.approve",
                   "parameters": [IDEMPOTENCY_PARAMETER]},
    dependencies=[Depends(require_proposal_key)],
)
async def approve_post_policy(
    project_id: UUID, guide_id: UUID, compilation_id: UUID, policy_id: UUID,
    payload: PostPolicyApprovalInput,
    key: Annotated[UUID, Depends(require_proposal_key)],
    request: Annotated[PostPolicyRequest, Depends(get_post_policy_request)],
) -> PostPolicyReceipt:
    """Separately approve the displayed policy without replacing its body."""
    require_policy_target(payload.target, project_id, guide_id, compilation_id, policy_id)
    try:
        response = await request.service.approve(
            PostPolicyApproval(**payload.model_dump(), idempotency_key=key),
            actor=request.actor, request_id=request.request_id,
        )
        await request.session.commit()
        return response
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
    except SQLAlchemyError as exc:
        raise proposal_http_error(GuideProposalError("storage_unavailable")) from exc


@router.post(
    "/corrections", response_model=PostPolicyReceipt, status_code=201,
    openapi_extra={"x-workstream-action-id": "project.post_submit_checker_policy.correction.request",
                   "parameters": [IDEMPOTENCY_PARAMETER]},
    dependencies=[Depends(require_proposal_key)],
)
async def correct_post_policy(
    project_id: UUID, guide_id: UUID, compilation_id: UUID, policy_id: UUID,
    payload: PostPolicyCorrectionInput,
    key: Annotated[UUID, Depends(require_proposal_key)],
    request: Annotated[PostPolicyRequest, Depends(get_post_policy_request)],
) -> PostPolicyReceipt:
    """Create the canonical unified successor; existing explicit dispatch starts it."""
    require_policy_target(payload.target, project_id, guide_id, compilation_id, policy_id)
    try:
        response = await request.service.request_correction(
            PostPolicyCorrection(**payload.model_dump(), idempotency_key=key),
            actor=request.actor, request_id=request.request_id,
            guide_authorization=request.guide_authorization,
        )
        await request.session.commit()
        return response
    except GuideProposalError as exc:
        raise proposal_http_error(exc) from exc
    except SQLAlchemyError as exc:
        raise proposal_http_error(GuideProposalError("storage_unavailable")) from exc
