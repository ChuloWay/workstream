"""Typed evidence for recovery of a retained, exhausted assignment."""

from dataclasses import dataclass
from uuid import UUID

from app.modules.tasks.api.authorization import TaskAuthorityDecision

REVISION_EXHAUSTED_EVENT = "TaskRevisionExhausted"


@dataclass(frozen=True, slots=True)
class TaskRevisionExhaustionAuditFacts:
    """Closed references for the recovery terminal transition."""

    event_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    submission_id: UUID
    routing_manifest_id: UUID
    exhaustion_receipt_id: UUID
    actor_profile_id: UUID
    outbox_event_id: UUID
    authority: TaskAuthorityDecision
