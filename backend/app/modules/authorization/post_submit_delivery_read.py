"""Authorize uncertain post-submit delivery pages and own signed cursors."""

from hashlib import sha256

from app.core.config import decode_pagination_cursor_hmac_secret
from app.core.hashing import canonical_json_hash
from app.modules.authorization.domain.post_submit_deliveries import (
    POST_SUBMIT_DELIVERY_LIST_ACTION,
    PostSubmitDeliveryReadResourceContext,
)
from app.modules.authorization.pagination import (
    AuthorizationReadCursorCodec,
    InvalidPaginationCursor,
    authorization_read_query_digest,
)
from app.modules.authorization.runtime import AuthorizationDenied
from app.modules.checkers.api.delivery_reconciliation import (
    PostSubmitDeliveryCursorInvalid,
    PostSubmitDeliveryOperationUnavailable,
    PostSubmitDeliveryPosition,
    PostSubmitDeliveryQuery,
)


class PostSubmitDeliveryReadAuthorization:
    """One request-local system-Operator read adapter."""

    def __init__(self, kernel, secret) -> None:
        self._kernel, self._secret = kernel, secret

    @staticmethod
    def _query(request: PostSubmitDeliveryQuery) -> str:
        return authorization_read_query_digest(
            action_id=POST_SUBMIT_DELIVERY_LIST_ACTION,
            project_id=request.project_id,
            limit=request.limit,
        )

    def _codec(self):
        if self._secret is None:
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_read_unavailable"
            )
        try:
            return AuthorizationReadCursorCodec(
                decode_pagination_cursor_hmac_secret(self._secret)
            )
        except ValueError as exc:
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_read_unavailable"
            ) from exc

    async def authorize_and_decode(self, request):
        request = PostSubmitDeliveryQuery.model_validate(request)
        cursor = request.cursor
        query_digest = self._query(request)
        await self._kernel.require(
            POST_SUBMIT_DELIVERY_LIST_ACTION,
            PostSubmitDeliveryReadResourceContext(
                resource_id=request.project_id,
                scope_project_id=request.project_id,
                request_digest=canonical_json_hash(
                    {
                        "query_digest": query_digest,
                        "presented_cursor_digest": (
                            "sha256:" + sha256(cursor.encode()).hexdigest()
                            if cursor is not None
                            else None
                        ),
                    }
                ),
            ),
        )
        if cursor is None:
            return None
        try:
            timestamp, event_id = self._codec().decode(
                cursor, query_digest=query_digest
            )
        except InvalidPaginationCursor as exc:
            raise PostSubmitDeliveryCursorInvalid(
                "invalid post-submit delivery cursor"
            ) from exc
        return PostSubmitDeliveryPosition(finalized_at=timestamp, event_id=event_id)

    def encode(self, request, position):
        return self._codec().encode(
            query_digest=self._query(request),
            timestamp=position.finalized_at,
            resource_id=position.event_id,
        )

    async def restage_denial(self, error: Exception) -> bool:
        if isinstance(error, AuthorizationDenied):
            await self._kernel.restage_denial(error.decision)
            return True
        return False
