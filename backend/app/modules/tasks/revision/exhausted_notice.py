"""Validate committed exhaustion notices without another lifecycle mutation."""

import json
from uuid import UUID

from sqlalchemy import func, select

from app.modules.outbox.api import HandlerOutcome, OutboxEventEnvelope
from app.modules.tasks.api.revision_exhaustion import REVISION_EXHAUSTED_EVENT
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.revision.exhaustion_event import revision_exhausted_event
from app.modules.tasks.revision.models import TaskRevisionExhaustion


class TaskRevisionExhaustedNoticeOperation:
    """Observe exact delivery and independently validate durable terminal evidence."""

    def __init__(self, session, *, observer):
        """Use the caller's read session and committed delivery observer."""
        self._session, self._observer = session, observer

    async def acknowledge(self, envelope):
        """Acknowledge the immutable receipt even after a later contributor claims."""
        try:
            envelope = OutboxEventEnvelope.model_validate(envelope)
            payload = json.loads(envelope.payload_json)
            receipt_id = UUID(payload["exhaustion_receipt_id"])
        except (AttributeError, KeyError, TypeError, ValueError):
            return HandlerOutcome.REJECT
        if (envelope.event_type != REVISION_EXHAUSTED_EVENT or envelope.event_version != 1
                or envelope.aggregate_type != "task"
                or await self._observer.observe_invocation(envelope) is None):
            return HandlerOutcome.REJECT
        receipt = await self._session.get(TaskRevisionExhaustion, receipt_id)
        if receipt is None or receipt.outcome_event_id != envelope.claim.event_id:
            return HandlerOutcome.REJECT
        manifest = await self._session.get(TaskPostSubmitRoutingManifest, receipt.routing_manifest_id)
        if manifest is None or receipt.recovery_authority_context is None:
            return HandlerOutcome.REJECT
        expected = revision_exhausted_event(receipt, manifest)
        if (envelope.claim.project_id != expected.project_id
                or envelope.aggregate_id != expected.aggregate_id
                or envelope.correlation_id != expected.correlation_id
                or envelope.causation_event_id != expected.causation_event_id
                or envelope.idempotency_key != expected.idempotency_key
                or payload != expected.payload
                or not await self._session.scalar(select(func.task_revision_exhaustion_complete(receipt.id)))):
            return HandlerOutcome.REJECT
        return HandlerOutcome.ACKNOWLEDGE
