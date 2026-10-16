"""Validate durable PM-attention notices against the immutable paused preparation."""

import json
from uuid import UUID

from app.modules.outbox.api import HandlerOutcome, OutboxEventEnvelope
from app.modules.tasks.api.revision_expiry import REVISION_CONTEXT_BLOCKED_EVENT
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.revision.expiry_event import revision_preparation_event
from app.modules.tasks.revision.models import TaskRevisionPreparation


class TaskRevisionBlockedNoticeOperation:
    """Acknowledge committed attention facts; PM reads expose the paused context."""

    def __init__(self, session, *, observer):
        """Bind exact delivery observation to read-only TASK evidence."""
        self._session, self._observer = session, observer

    async def acknowledge(self, envelope: OutboxEventEnvelope) -> HandlerOutcome:
        """Reject altered notices without changing the clock or delivering a push."""
        try:
            envelope = OutboxEventEnvelope.model_validate(envelope)
            payload = json.loads(envelope.payload_json)
            preparation_id = UUID(payload["preparation_id"])
        except (AttributeError, KeyError, TypeError, ValueError):
            return HandlerOutcome.REJECT
        if (envelope.event_type != REVISION_CONTEXT_BLOCKED_EVENT or envelope.event_version != 1
                or envelope.aggregate_type != "task"
                or await self._observer.observe_invocation(envelope) is None):
            return HandlerOutcome.REJECT
        head = await self._session.get(TaskRevisionPreparation, preparation_id)
        if head is None or head.deadline_at is not None or head.blocked_reason != "context_blocked":
            return HandlerOutcome.REJECT
        manifest = await self._session.get(TaskPostSubmitRoutingManifest, head.routing_manifest_id)
        if manifest is None:
            return HandlerOutcome.REJECT
        expected = revision_preparation_event(manifest, head)
        if (envelope.claim.project_id != expected.project_id
                or envelope.aggregate_id != expected.aggregate_id
                or envelope.correlation_id != expected.correlation_id
                or envelope.causation_event_id != expected.causation_event_id
                or envelope.idempotency_key != expected.idempotency_key
                or payload != expected.payload):
            return HandlerOutcome.REJECT
        return HandlerOutcome.ACKNOWLEDGE
