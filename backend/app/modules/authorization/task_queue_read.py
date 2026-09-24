"""Translate queue facts through the canonical AUTH kernel and cursor codec."""

from hashlib import sha256

from app.core.config import decode_pagination_cursor_hmac_secret
from app.core.hashing import canonical_json_hash
from app.modules.authorization.api.task_queues import (
    TaskQueueCursorInvalid, TaskQueuePosition, TaskQueueReadRequest, TaskQueueReadUnavailable,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.task_queues import QueueReadResourceContext
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.pagination import (
    AuthorizationReadCursorCodec, InvalidPaginationCursor, authorization_read_query_digest,
)


class TaskQueueReadAuthorization:
    """One request-local adapter; decisions and transactions retain their owners."""

    def __init__(self, kernel: AuthorizationService, secret):
        self._kernel, self._secret = kernel, secret

    @staticmethod
    def _query(request: TaskQueueReadRequest) -> str:
        return authorization_read_query_digest(
            action_id=ActionId(request.action), project_id=request.project_id, limit=request.limit,
        )

    def _codec(self) -> AuthorizationReadCursorCodec:
        if self._secret is None:
            raise TaskQueueReadUnavailable("Task queue unavailable")
        return AuthorizationReadCursorCodec(decode_pagination_cursor_hmac_secret(self._secret))

    async def authorize_and_decode(self, request: TaskQueueReadRequest) -> TaskQueuePosition | None:
        """Authorize the exact request before parsing a bounded untrusted cursor."""
        cursor = request.presented_cursor
        query_digest = self._query(request)
        await self._kernel.require(ActionId(request.action), QueueReadResourceContext(
            resource_id=request.project_id, scope_project_id=request.project_id,
            request_digest=canonical_json_hash({
                "query_digest": query_digest,
                "presented_cursor_digest": "sha256:" + sha256(cursor.encode()).hexdigest() if cursor is not None else None,
            }),
        ))
        codec = self._codec()
        if cursor is None:
            return None
        try:
            timestamp, task_id = codec.decode(cursor, query_digest=query_digest)
        except InvalidPaginationCursor as exc:
            raise TaskQueueCursorInvalid("Invalid task queue cursor") from exc
        return TaskQueuePosition(timestamp, task_id)

    def encode(self, request: TaskQueueReadRequest, position: TaskQueuePosition) -> str:
        """Reuse the stable action/project/limit signing digest for continuation."""
        return self._codec().encode(
            query_digest=self._query(request), timestamp=position.created_at, resource_id=position.task_id,
        )
