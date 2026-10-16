"""Translate project-wide management reads through the canonical AUTH kernel and cursor codec."""

from hashlib import sha256

from app.core.config import decode_pagination_cursor_hmac_secret
from app.core.hashing import canonical_json_hash
from app.modules.authorization.api.management_reads import (
    UNPAGED_MANAGEMENT_READ_ACTIONS, ProjectManagementReadCursorInvalid, ProjectManagementReadGrant, ProjectManagementReadPosition,
    ProjectManagementReadRequest, ProjectManagementReadUnavailable,
)
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.domain.management_reads import (
    MANAGEMENT_RESOURCE_BY_ACTION, ProjectManagementReadResourceContext,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.pagination import AuthorizationReadCursorCodec, InvalidPaginationCursor
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.schemas import AdminRole


class ProjectManagementReadAuthorization:
    """One request-local adapter; the caller's response transaction owns evidence."""

    def __init__(self, kernel: AuthorizationService, repository: AdminAuthorizationRepository, secret):
        """Bind the kernel, the grant repository and the cursor secret."""
        self._kernel, self._repository, self._secret = kernel, repository, secret

    @staticmethod
    def _query(request: ProjectManagementReadRequest) -> str:
        """Bind a cursor to the caller, project, resource, filters, limit and order."""
        return canonical_json_hash({
            "action_id": request.action,
            "actor_profile_id": str(request.actor_profile_id),
            "project_id": str(request.project_id),
            "resource_id": str(request.resource_id),
            "query": dict(request.query),
        })

    def _codec(self) -> AuthorizationReadCursorCodec:
        """The HMAC cursor codec for project management reads."""
        if self._secret is None:
            raise ProjectManagementReadUnavailable("Project management reads unavailable")
        return AuthorizationReadCursorCodec(decode_pagination_cursor_hmac_secret(self._secret))

    async def authorize(self, request: ProjectManagementReadRequest) -> ProjectManagementReadGrant:
        """Authorize the exact request, then return the project, position and disclosure."""
        query_digest = self._query(request)
        cursor = request.presented_cursor
        # Paged reads need the cursor secret before any decision is recorded.
        codec = None if request.action in UNPAGED_MANAGEMENT_READ_ACTIONS else self._codec()
        digest = canonical_json_hash({
            "query_digest": query_digest,
            "presented_cursor_digest": (
                "sha256:" + sha256(cursor.encode()).hexdigest() if cursor is not None else None
            ),
        })
        action = ActionId(request.action)
        await self._kernel.require(action, ProjectManagementReadResourceContext(
            resource_type=MANAGEMENT_RESOURCE_BY_ACTION[action], resource_id=request.resource_id,
            scope_project_id=request.project_id, actor_profile_id=request.actor_profile_id,
            request_digest=digest,
        ))
        position = None
        if cursor is not None:
            try:
                timestamp, record_id = codec.decode(cursor, query_digest=query_digest)
            except InvalidPaginationCursor as exc:
                raise ProjectManagementReadCursorInvalid("Invalid project management read cursor") from exc
            position = ProjectManagementReadPosition(timestamp, record_id)
        award_totals_visible = False
        if action is ActionId.PROJECT_SUMMARY_READ:
            # Award totals follow the PILOT-10 precedent: only an exact-project
            # Finance grant discloses them; a system Finance grant does not.
            # Locked with the decision so the disclosure holds until commit.
            award_totals_visible = await self._repository.find_effective_grant(
                request.actor_profile_id, PermissionId.COMPENSATION_AWARD_READ,
                scope_project_id=request.project_id, exact_project_scope=True, for_update=True,
                allowed_roles=frozenset({AdminRole.FINANCE_AUTHORITY}),
            ) is not None
        return ProjectManagementReadGrant(request.project_id, position, award_totals_visible)

    def encode(self, request: ProjectManagementReadRequest, position: ProjectManagementReadPosition) -> str:
        """Sign the last returned row's boundary for the same exact query."""
        return self._codec().encode(
            query_digest=self._query(request), timestamp=position.timestamp, resource_id=position.record_id,
        )
