"""Translate checker retry-source pages through canonical AUTH and signed cursors."""

from hashlib import sha256

from app.core.config import decode_pagination_cursor_hmac_secret
from app.core.hashing import canonical_json_hash
from app.modules.authorization.domain.checker_retry_reads import (
    CHECKER_RETRY_SOURCE_LIST_ACTION,
    CheckerRetrySourceReadResourceContext,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import AuthorizationDenied
from app.modules.authorization.pagination import (
    AuthorizationReadCursorCodec,
    InvalidPaginationCursor,
    authorization_read_query_digest,
)
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable,
    CheckerRetryCursorInvalid,
    CheckerRetrySourcePosition,
    CheckerRetrySourceQuery,
)


class CheckerRetryDiscoveryAuthorization:
    """One request-local exact system-Operator discovery adapter."""

    def __init__(self, kernel: AuthorizationService, secret) -> None:
        self._kernel, self._secret = kernel, secret

    @staticmethod
    def _query(request: CheckerRetrySourceQuery) -> str:
        return authorization_read_query_digest(
            action_id=CHECKER_RETRY_SOURCE_LIST_ACTION,
            project_id=request.project_id,
            limit=request.limit,
        )

    def _codec(self) -> AuthorizationReadCursorCodec:
        if self._secret is None:
            raise CheckerExecutionUnavailable("checker_retry_discovery_unavailable")
        try:
            return AuthorizationReadCursorCodec(
                decode_pagination_cursor_hmac_secret(self._secret)
            )
        except ValueError as exc:
            raise CheckerExecutionUnavailable(
                "checker_retry_discovery_unavailable"
            ) from exc

    async def authorize_and_decode(
        self, request: CheckerRetrySourceQuery,
    ) -> CheckerRetrySourcePosition | None:
        """Authorize the exact page before decoding its untrusted cursor."""
        cursor = request.cursor
        query_digest = self._query(request)
        await self._kernel.require(
            CHECKER_RETRY_SOURCE_LIST_ACTION,
            CheckerRetrySourceReadResourceContext(
                resource_id=request.project_id,
                scope_project_id=request.project_id,
                request_digest=canonical_json_hash({
                    "query_digest": query_digest,
                    "presented_cursor_digest": (
                        "sha256:" + sha256(cursor.encode()).hexdigest()
                        if cursor is not None else None
                    ),
                }),
            ),
        )
        if cursor is None:
            return None
        try:
            timestamp, run_id = self._codec().decode(
                cursor, query_digest=query_digest,
            )
        except InvalidPaginationCursor as exc:
            raise CheckerRetryCursorInvalid(
                "invalid checker retry discovery cursor"
            ) from exc
        return CheckerRetrySourcePosition(
            created_at=timestamp,
            source_run_id=run_id,
        )

    def encode(
        self, request: CheckerRetrySourceQuery, position: CheckerRetrySourcePosition,
    ) -> str:
        """Sign one stable project/query/run boundary."""
        return self._codec().encode(
            query_digest=self._query(request),
            timestamp=position.created_at,
            resource_id=position.source_run_id,
        )

    async def restage_denial(self, error: Exception) -> bool:
        """Persist only the exact pending decision after caller-root rollback."""
        if isinstance(error, AuthorizationDenied):
            await self._kernel.restage_denial(error.decision)
            return True
        return False
