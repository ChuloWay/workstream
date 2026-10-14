"""Read-only validation for the committed revision-expiry outcome notice."""

import json
from uuid import UUID

from app.modules.outbox.api import HandlerOutcome, OutboxEventEnvelope
from app.modules.tasks.api.revision_expiry import REVISION_EXPIRED_EVENT, TaskRevisionExpiryUnavailable
from app.modules.tasks.revision.expiry_event import expiry_receipt_snapshot, revision_expired_event
from app.modules.tasks.revision.models import TaskRevisionExpiration


class TaskRevisionExpiredNoticeOperation:
    """Acknowledge only a notice bound to the exact durable TASK receipt and audit."""

    def __init__(self, session, *, observer, audit):
        """Bind read-only receipt validation to the current delivery observer."""
        self._session, self._observer, self._audit = session, observer, audit

    async def acknowledge(self, envelope: OutboxEventEnvelope) -> HandlerOutcome:
        """Accept only the exact committed receipt and matching audit evidence."""
        try:
            envelope = OutboxEventEnvelope.model_validate(envelope)
            payload = json.loads(envelope.payload_json)
            receipt_id = UUID(payload["expiration_receipt_id"])
        except (AttributeError, KeyError, TypeError, ValueError):
            return HandlerOutcome.REJECT
        if (envelope.event_type != REVISION_EXPIRED_EVENT or envelope.event_version != 1
                or envelope.aggregate_type != "task"
                or await self._observer.observe_invocation(envelope) is None):
            return HandlerOutcome.REJECT
        receipt = await self._session.get(TaskRevisionExpiration, receipt_id)
        if receipt is None or receipt.outcome_event_id != envelope.claim.event_id:
            return HandlerOutcome.REJECT
        expected = revision_expired_event(receipt)
        if (envelope.claim.project_id != expected.project_id
                or envelope.aggregate_id != expected.aggregate_id
                or envelope.correlation_id != expected.correlation_id
                or envelope.causation_event_id != expected.causation_event_id
                or envelope.idempotency_key != expected.idempotency_key
                or payload != expected.payload):
            return HandlerOutcome.REJECT
        evidence = await self._audit.read_expiry(expiry_receipt_snapshot(receipt))
        if (evidence is None or evidence.receipt_id != receipt.id
                or evidence.audit_event_id != receipt.audit_event_id
                or evidence.authority.decision_id != receipt.authorization_decision_id):
            raise TaskRevisionExpiryUnavailable("revision expiry outcome evidence differs")
        return HandlerOutcome.ACKNOWLEDGE
