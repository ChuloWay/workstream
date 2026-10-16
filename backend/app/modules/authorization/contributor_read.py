"""Translate the caller's own-work reads through the canonical AUTH kernel and cursor codec."""

from hashlib import sha256
from uuid import UUID

from app.core.config import decode_pagination_cursor_hmac_secret
from app.core.hashing import canonical_json_hash
from app.modules.authorization.api.contributor_reads import (
    ActorProjectRoles, ContributorReadCursorInvalid, ContributorReadGrant, ContributorReadPosition,
    ContributorReadRequest, ContributorReadUnavailable,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.contributor_reads import (
    WORK_RESOURCE_BY_ACTION, ActorProjectListResourceContext, ContributorWorkReadResourceContext,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.pagination import AuthorizationReadCursorCodec, InvalidPaginationCursor
from app.modules.authorization.read_service import eligible_project_admin_roles
from app.modules.authorization.repository import AdminAuthorizationRepository


class ContributorReadAuthorization:
    """One request-local adapter; the caller's response transaction owns evidence."""

    def __init__(self, kernel: AuthorizationService, repository: AdminAuthorizationRepository, secret):
        """Bind the kernel, the grant repository and the cursor secret."""
        self._kernel, self._repository, self._secret = kernel, repository, secret

    @staticmethod
    def _query(request: ContributorReadRequest) -> str:
        """Bind a cursor to the caller, resource, scope, filters, limit and order."""
        return canonical_json_hash({
            "action_id": request.action,
            "actor_profile_id": str(request.actor_profile_id),
            "resource_id": str(request.resource_id),
            "scope_project_id": None if request.scope_project_id is None else str(request.scope_project_id),
            "query": dict(request.query),
        })

    def _codec(self) -> AuthorizationReadCursorCodec:
        """The HMAC cursor codec for contributor reads."""
        if self._secret is None:
            raise ContributorReadUnavailable("Contributor reads unavailable")
        return AuthorizationReadCursorCodec(decode_pagination_cursor_hmac_secret(self._secret))

    async def authorize(self, request: ContributorReadRequest) -> ContributorReadGrant:
        """Authorize the exact request, then return visible projects and the cursor position."""
        codec = self._codec()
        query_digest = self._query(request)
        cursor = request.presented_cursor
        digest = canonical_json_hash({
            "query_digest": query_digest,
            "presented_cursor_digest": (
                "sha256:" + sha256(cursor.encode()).hexdigest() if cursor is not None else None
            ),
        })
        action = ActionId(request.action)
        if action is ActionId.ACTOR_PROJECT_LIST:
            resource = ActorProjectListResourceContext(
                resource_id=request.resource_id, actor_profile_id=request.actor_profile_id,
                request_digest=digest,
            )
        else:
            resource = ContributorWorkReadResourceContext(
                resource_type=WORK_RESOURCE_BY_ACTION[action], resource_id=request.resource_id,
                actor_profile_id=request.actor_profile_id, scope_project_id=request.scope_project_id,
                request_digest=digest,
            )
        await self._kernel.require(action, resource)
        position = None
        if cursor is not None:
            try:
                timestamp, record_id = codec.decode(cursor, query_digest=query_digest)
            except InvalidPaginationCursor as exc:
                raise ContributorReadCursorInvalid("Invalid contributor read cursor") from exc
            position = ContributorReadPosition(timestamp, record_id)
        if action is ActionId.ACTOR_PROJECT_LIST:
            projects = await self._repository.exact_grant_project_ids(
                actor_profile_id=request.actor_profile_id,
            )
        elif request.scope_project_id is not None:
            projects = frozenset({request.scope_project_id})
        else:
            # Locked with the decision so the visible set holds until commit.
            projects = await self._repository.active_project_ids_for_role(
                actor_profile_id=request.actor_profile_id, role="submitter",
            )
        return ContributorReadGrant(projects, position)

    def encode(self, request: ContributorReadRequest, position: ContributorReadPosition) -> str:
        """Sign the last returned row's boundary for the same exact query."""
        return self._codec().encode(
            query_digest=self._query(request), timestamp=position.timestamp, resource_id=position.record_id,
        )

    async def project_roles(
        self, actor_profile_id: UUID, project_ids: tuple[UUID, ...],
    ) -> dict[UUID, ActorProjectRoles]:
        """Effective admin roles (system or exact) and active contributor roles per project."""
        admin = await self._repository.effective_admin_roles_for_projects(
            project_ids=project_ids, actor_profile_id=actor_profile_id,
        )
        contributor = await self._repository.active_project_roles_for_projects(
            project_ids=project_ids, actor_profile_id=actor_profile_id,
        )
        return {
            project_id: ActorProjectRoles(
                eligible_project_admin_roles(admin[project_id]), contributor[project_id],
            )
            for project_id in project_ids
        }
