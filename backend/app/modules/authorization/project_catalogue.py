"""Request-local AUTH decision and signed cursor for project catalogue pages."""

from hashlib import sha256

from app.core.config import decode_pagination_cursor_hmac_secret
from app.core.hashing import canonical_json_hash
from app.modules.authorization.api.project_catalogue import (
    ProjectCatalogueCursorInvalid,
    ProjectCatalogueGrant,
    ProjectCatalogueRequest,
    ProjectCatalogueUnavailable,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.project_catalogue import ProjectCatalogueResourceContext
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.pagination import AuthorizationIdCursorCodec, InvalidPaginationCursor


class ProjectCatalogueAuthorization:
    """Use the canonical kernel for each page before decoding a continuation."""

    def __init__(self, kernel: AuthorizationService, secret) -> None:
        self._kernel, self._secret = kernel, secret

    @staticmethod
    def _query(request: ProjectCatalogueRequest) -> str:
        return canonical_json_hash(
            {
                "action_id": ActionId.PROJECT_CATALOGUE_LIST.value,
                "actor_profile_id": str(request.actor_profile_id),
                "limit": request.limit,
                "order": "id_asc",
            }
        )

    def _codec(self) -> AuthorizationIdCursorCodec:
        if self._secret is None:
            raise ProjectCatalogueUnavailable("Project catalogue unavailable")
        return AuthorizationIdCursorCodec(decode_pagination_cursor_hmac_secret(self._secret))

    async def authorize(self, request: ProjectCatalogueRequest) -> ProjectCatalogueGrant:
        codec = self._codec()
        query_digest = self._query(request)
        await self._kernel.require(
            ActionId.PROJECT_CATALOGUE_LIST,
            ProjectCatalogueResourceContext(
                resource_id=request.actor_profile_id,
                actor_profile_id=request.actor_profile_id,
                request_digest=canonical_json_hash(
                    {
                        "query_digest": query_digest,
                        "presented_cursor_digest": (
                            "sha256:" + sha256(request.cursor.encode()).hexdigest()
                            if request.cursor is not None
                            else None
                        ),
                    }
                ),
            ),
        )
        if request.cursor is None:
            return ProjectCatalogueGrant(None)
        try:
            return ProjectCatalogueGrant(codec.decode(request.cursor, query_digest=query_digest))
        except InvalidPaginationCursor as exc:
            raise ProjectCatalogueCursorInvalid("Invalid project catalogue cursor") from exc

    def encode(self, request: ProjectCatalogueRequest, position) -> str:
        return self._codec().encode(
            query_digest=self._query(request),
            resource_id=position,
        )
