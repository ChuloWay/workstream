"""Bind CON's exact server-bound query to the closed AUTH read evaluator."""

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.contribution_reads import (
    ContributionProjectReadResourceContext, ContributionSelfReadResourceContext,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.contributions.api.records import (
    ContributionReadDenied, ContributionReadRequest, ContributionExportUnavailable,
)
from app.modules.authorization.runtime import AuthorizationDenied, AuthorizationEvidenceUnavailable


class ContributionReadAuthorization:
    """Mandatory request-local authority; no facts, grants or decisions are cached."""

    def __init__(self, kernel: AuthorizationService) -> None:
        """Use the caller's AUTH kernel and response transaction without a fallback."""
        self._kernel = kernel

    async def authorize(self, request: ContributionReadRequest) -> None:
        """Digest the full selected query and require its exact actor or project resource."""
        request = ContributionReadRequest.model_validate(request)
        digest = canonical_json_hash({"contribution_read": request.model_dump(mode="json")})
        if request.audience == "self":
            action = ActionId.CONTRIBUTION_READ_SELF
            resource = ContributionSelfReadResourceContext(
                resource_id=request.actor_profile_id, actor_profile_id=request.actor_profile_id,
                request_digest=digest,
            )
        else:
            action = ActionId.CONTRIBUTION_READ_PROJECT
            resource = ContributionProjectReadResourceContext(
                resource_id=request.project_id, scope_project_id=request.project_id,
                actor_profile_id=request.actor_profile_id, request_digest=digest,
            )
        try:
            await self._kernel.require(action, resource)
        except AuthorizationDenied as exc:
            raise ContributionReadDenied("Contribution read denied") from exc
        except AuthorizationEvidenceUnavailable as exc:
            raise ContributionExportUnavailable("Contribution authority unavailable") from exc
