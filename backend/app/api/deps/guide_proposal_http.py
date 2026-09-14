"""Shared admission and error mapping for unified guide-policy decisions."""

from uuid import UUID
from fastapi import Request
from app.core.api_controls import StructuredHTTPException, parse_idempotency_key
from app.modules.projects.api.guide_proposals import GuideProposalError


IDEMPOTENCY_PARAMETER = {
    "name": "Idempotency-Key", "in": "header", "required": True,
    "schema": {"type": "string", "format": "uuid"},
}


def require_proposal_key(request: Request) -> UUID:
    """Require one key before FastAPI resolves identity or SQL."""
    values = request.headers.getlist("Idempotency-Key")
    return parse_idempotency_key(values[0] if len(values) == 1 else "")


def proposal_http_error(exc: GuideProposalError) -> StructuredHTTPException:
    """Conceal selectors and authority; retain bounded actionable conflicts."""
    if exc.code in {"authority_unavailable", "proposal_unavailable"}:
        code, status, message = "proposal_unavailable", 404, "Guide proposal unavailable"
    elif exc.code == "storage_unavailable":
        code, status, message = exc.code, 503, "Guide proposal storage unavailable"
    else:
        code, status, message = exc.code, 409, "Guide proposal conflicts with current state"
    return StructuredHTTPException(
        status_code=status, detail=code, error_code=code, error_message=message,
        retryable=status == 503,
    )


def require_matching_target(target, project_id, guide_id, compilation_id):
    """Never let a body substitute an object from outside the selected path."""
    if (target.project_id, target.guide_id, target.compilation_id) != (
        project_id, guide_id, compilation_id
    ):
        raise proposal_http_error(GuideProposalError("proposal_unavailable"))


