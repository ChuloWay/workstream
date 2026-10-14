"""Exact service authority for recovering an old routed revision window."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.tasks.api.authorization import TaskAuthorityDecision


RECOVERY_REASON = "Recover retained revision window"


@dataclass(frozen=True, slots=True)
class TaskRevisionRecoveryFacts:
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    routing_manifest_id: UUID
    locked_context_hash: str
    request_digest: str
    preparation_id: UUID | None = None
    preparation_sha256: str | None = None


class TaskRevisionRecoveryAuthorizationPort(Protocol):
    async def authorize(self, facts: TaskRevisionRecoveryFacts) -> tuple[UUID, TaskAuthorityDecision]: ...
