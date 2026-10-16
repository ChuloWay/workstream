"""Durable terminal notice for recovery of an already exhausted source."""

from uuid import UUID

from app.modules.outbox.api import OutboxAppendInput
from app.modules.tasks.api.revision_exhaustion import REVISION_EXHAUSTED_EVENT


def revision_exhausted_event(receipt, manifest):
    """Bind the outcome to its immutable receipt and original routing event."""
    return OutboxAppendInput(
        event_type=REVISION_EXHAUSTED_EVENT, event_version=1,
        aggregate_type="task", aggregate_id=UUID(receipt.task_id),
        project_id=UUID(receipt.project_id), correlation_id=str(manifest.id),
        causation_event_id=manifest.outcome_event_id,
        idempotency_key="task.revision.exhausted:" + str(manifest.id),
        payload={
            "project_id": receipt.project_id, "task_id": receipt.task_id,
            "assignment_id": receipt.assignment_id, "contributor_id": receipt.contributor_id,
            "source_submission_id": receipt.source_submission_id,
            "routing_manifest_id": str(manifest.id), "exhaustion_receipt_id": str(receipt.id),
            "authorization_decision_id": receipt.authorization_decision_id,
            "audit_event_id": receipt.audit_event_id, "exhausted_at": receipt.exhausted_at.isoformat(),
        },
    )
