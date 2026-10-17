"""Immutable timers and blocked notices for source-rooted revision clock heads."""

from uuid import UUID

from app.modules.outbox.api import OutboxAppendInput
from app.modules.tasks.api.revision_expiry import (
    REVISION_EXPIRY_EVENT, REVISION_EXPIRED_EVENT, REVISION_CONTEXT_BLOCKED_EVENT, TaskRevisionExpiryReceiptSnapshot,
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


def expiry_target(manifest, root, head=None) -> TaskRevisionExpiryTarget:
    """Bind original source identity and the immutable scheduled running head."""
    if root.sequence != 1 or root.predecessor_id is not None or root.routing_manifest_id != manifest.id:
        raise ValueError("revision expiry requires the original preparation")
    head = head or root
    if head.routing_manifest_id != manifest.id or head.deadline_at is None:
        raise ValueError("revision expiry requires a running preparation")
    return TaskRevisionExpiryTarget(
        project_id=UUID(str(root.project_id)), task_id=UUID(str(root.task_id)),
        assignment_id=UUID(str(root.assignment_id)), contributor_id=UUID(str(root.contributor_id)),
        source_submission_id=UUID(str(root.submission_id)), routing_manifest_id=UUID(str(manifest.id)),
        root_preparation_id=UUID(str(root.id)), root_preparation_sha256=root.preparation_sha256,
        deadline_at=head.deadline_at,
    )


def revision_expiry_event(manifest, root, head=None) -> OutboxAppendInput:
    head = head or root
    target = expiry_target(manifest, root, head)
    return OutboxAppendInput(
        event_type=REVISION_EXPIRY_EVENT, event_version=1,
        aggregate_type="task", aggregate_id=target.task_id,
        project_id=target.project_id,
        correlation_id=str(target.routing_manifest_id),
        causation_event_id=UUID(str(manifest.outcome_event_id)),
        idempotency_key="task.revision.expire:" + str(target.routing_manifest_id)
        + (":" + str(head.id) if head.id != root.id else ""),
        payload=target.model_dump(mode="json"),
        not_before_at=target.deadline_at,
    )


def revision_preparation_event(manifest, root, head=None) -> OutboxAppendInput:
    """Publish a running timer or durable PM attention for one paused head."""
    head = head or root
    if head.deadline_at is not None:
        return revision_expiry_event(manifest, root, head)
    if head.blocked_reason != "context_blocked" or head.remaining_microseconds is None:
        raise ValueError("paused revision requires blocked context and allowance")
    return OutboxAppendInput(
        event_type=REVISION_CONTEXT_BLOCKED_EVENT, event_version=1,
        aggregate_type="task", aggregate_id=UUID(str(head.task_id)),
        project_id=UUID(str(head.project_id)), correlation_id=str(manifest.id),
        causation_event_id=UUID(str(manifest.outcome_event_id)),
        idempotency_key=f"task.revision.context-blocked:{manifest.id}:{head.id}",
        payload={
            "project_id": str(head.project_id), "task_id": str(head.task_id),
            "assignment_id": str(head.assignment_id),
            "source_submission_id": str(head.submission_id),
            "routing_manifest_id": str(manifest.id), "preparation_id": str(head.id),
            "preparation_sha256": head.preparation_sha256,
            "authorization_decision_id": str(head.authorization_decision_id),
            "audit_event_id": str(head.audit_event_id), "reason": "context_blocked",
            "remaining_microseconds": head.remaining_microseconds,
        },
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
