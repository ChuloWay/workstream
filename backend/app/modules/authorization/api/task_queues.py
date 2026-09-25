"""Typed authority and cursor seam for the three bounded task queue reads."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

TaskQueueAction = Literal["task.queue.read", "project.task.queue.read", "operations.task.queue.read"]
READY_QUEUE_ACTION: Literal["task.queue.read"] = "task.queue.read"
MANAGEMENT_QUEUE_ACTION: Literal["project.task.queue.read"] = "project.task.queue.read"
OPERATIONAL_QUEUE_ACTION: Literal["operations.task.queue.read"] = "operations.task.queue.read"


@dataclass(frozen=True, slots=True)
class TaskQueueReadRequest:
    """Exact project, audience and bounded pagination request."""

    action: TaskQueueAction
    project_id: UUID
    limit: int
    presented_cursor: str | None

    def __post_init__(self):
        if (self.action not in {READY_QUEUE_ACTION, MANAGEMENT_QUEUE_ACTION, OPERATIONAL_QUEUE_ACTION}
                or not isinstance(self.project_id, UUID) or type(self.limit) is not int
                or not 1 <= self.limit <= 100
                or (self.presented_cursor is not None and (
                    not isinstance(self.presented_cursor, str) or len(self.presented_cursor) > 512))):
            raise ValueError("invalid task queue request")


@dataclass(frozen=True, slots=True)
class TaskQueuePosition:
    """A verified continuation position, not authority or a work reservation."""

    created_at: datetime
    task_id: UUID

    def __post_init__(self):
        if (not isinstance(self.task_id, UUID) or not isinstance(self.created_at, datetime)
                or self.created_at.utcoffset() is None):
            raise ValueError("invalid task queue position")


class TaskQueueCursorInvalid(ValueError):
    """Bounded invalid, substituted or forged pagination input."""


class TaskQueueReadUnavailable(RuntimeError):
    """Required cursor configuration is unavailable."""


class TaskQueueReadAuthorizationPort(Protocol):
    """Live authority precedes cursor verification on every page."""

    async def authorize_and_decode(self, request: TaskQueueReadRequest) -> TaskQueuePosition | None: ...

    def encode(self, request: TaskQueueReadRequest, position: TaskQueuePosition) -> str: ...
