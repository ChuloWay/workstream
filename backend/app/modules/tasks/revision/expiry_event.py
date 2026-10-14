"""One scheduled expiry request per committed needs-revision routing failure."""

from uuid import UUID

from app.modules.outbox.api import OutboxAppendInput
from app.modules.tasks.api.revision_expiry import (
    REVISION_EXPIRY_EVENT, REVISION_EXPIRED_EVENT, TaskRevisionExpiryReceiptSnapshot,
    TaskRevisionExpiryTarget,
)


def expiry_receipt_snapshot(receipt) -> TaskRevisionExpiryReceiptSnapshot:
    """Pass only immutable TASK receipt facts to the AUDIT replay reader."""
    return TaskRevisionExpiryReceiptSnapshot(
        receipt_id=UUID(str(receipt.id)),
        audit_event_id=UUID(str(receipt.audit_event_id)),
        authorization_decision_id=UUID(str(receipt.authorization_decision_id)),
        routing_manifest_id=UUID(str(receipt.routing_manifest_id)),
        source_submission_id=UUID(str(receipt.source_submission_id)),
        head_preparation_id=UUID(str(receipt.head_preparation_id)),
        expired_at=receipt.expired_at,
        authority_context=receipt.authority_context,
    )


def expiry_target(manifest, root) -> TaskRevisionExpiryTarget:
    """Use the first preparation so later PM repair cannot move the deadline."""
    if root.sequence != 1 or root.predecessor_id is not None or root.routing_manifest_id != manifest.id:
        raise ValueError("revision expiry requires the original preparation")
    return TaskRevisionExpiryTarget(
        project_id=UUID(str(root.project_id)), task_id=UUID(str(root.task_id)),
        assignment_id=UUID(str(root.assignment_id)), contributor_id=UUID(str(root.contributor_id)),
        source_submission_id=UUID(str(root.submission_id)), routing_manifest_id=UUID(str(manifest.id)),
        root_preparation_id=UUID(str(root.id)), root_preparation_sha256=root.preparation_sha256,
        deadline_at=root.deadline_at,
    )


def revision_expiry_event(manifest, root) -> OutboxAppendInput:
    target = expiry_target(manifest, root)
    return OutboxAppendInput(
        event_type=REVISION_EXPIRY_EVENT, event_version=1,
        aggregate_type="task", aggregate_id=target.task_id,
        project_id=target.project_id,
        correlation_id=str(target.routing_manifest_id),
        causation_event_id=UUID(str(manifest.outcome_event_id)),
        idempotency_key="task.revision.expire:" + str(target.routing_manifest_id),
        payload=target.model_dump(mode="json"),
        not_before_at=target.deadline_at,
    )


def revision_expired_event(receipt) -> OutboxAppendInput:
    """Publish the committed TASK rejection with exact receipt and authority refs."""
    return OutboxAppendInput(
        event_type=REVISION_EXPIRED_EVENT, event_version=1,
        aggregate_type="task", aggregate_id=UUID(str(receipt.task_id)),
        project_id=UUID(str(receipt.project_id)),
        correlation_id=str(receipt.routing_manifest_id),
        causation_event_id=UUID(str(receipt.delivery_event_id)),
        idempotency_key="task.revision.expired:" + str(receipt.routing_manifest_id),
        payload={
            "project_id": str(receipt.project_id),
            "task_id": str(receipt.task_id),
            "assignment_id": str(receipt.assignment_id),
            "contributor_id": str(receipt.contributor_id),
            "source_submission_id": str(receipt.source_submission_id),
            "routing_manifest_id": str(receipt.routing_manifest_id),
            "root_preparation_id": str(receipt.root_preparation_id),
            "root_preparation_sha256": receipt.root_preparation_sha256,
            "head_preparation_id": str(receipt.head_preparation_id),
            "head_preparation_sha256": receipt.head_preparation_sha256,
            "expiration_receipt_id": str(receipt.id),
            "expiry_request_event_id": str(receipt.delivery_event_id),
            "authorization_decision_id": str(receipt.authorization_decision_id),
            "audit_event_id": str(receipt.audit_event_id),
            "deadline_at": receipt.deadline_at.isoformat(),
            "expired_at": receipt.expired_at.isoformat(),
        },
    )
