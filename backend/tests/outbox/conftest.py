"""Real provisioned dispatcher authority with bounded test observation hooks."""

from contextlib import asynccontextmanager
import json
from app.core.identifiers import new_record_id

import pytest

from app.adapters.auth import outbox_dispatch_authorization
from app.modules.actors.models import ActorProfile, ActorIdentityLink
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.api.outbox_dispatch import PreparedOutboxDispatch
from app.modules.outbox.api import DeliveryOptions, HandlerOutcome, OutboxEventEnvelope
from app.modules.outbox.models import OutboxEvent
from app.adapters.outbox import outbox_delivery
from app.modules.outbox.registry import HandlerRegistry
from app.modules.outbox.service import OutboxService
from tests.test_outbox import outbox_database_env, outbox_factory, _event  # noqa: F401


class TracedPrepared(PreparedOutboxDispatch):
    """Observe actual PREP consumption; never manufacture a decision."""

    def __init__(self, harness, delegate):
        self.harness, self.delegate = harness, delegate

    async def consume(self, facts):
        decision = await self.delegate.consume(facts)
        self.harness.consumed.append(facts)
        if self.harness.consume_hook:
            await self.harness.consume_hook(facts)
        return decision


class TracedPort:
    """Pre-PREP barriers keep real service locking feasible in race proofs."""

    def __init__(self, harness, session):
        self.harness, self.session = harness, session

    @asynccontextmanager
    async def prepare_outbox_dispatch(self, *, facts, request_id, correlation_id):
        self.harness.prepared.append(facts)
        if self.harness.prepare_hook:
            await self.harness.prepare_hook(facts)
        checked = self.harness.substitute(facts) if self.harness.substitute else facts
        async with outbox_dispatch_authorization(self.session).prepare_outbox_dispatch(
            facts=checked, request_id=request_id, correlation_id=correlation_id,
        ) as prepared:
            yield TracedPrepared(self.harness, prepared)


class Harness:
    """Per-test deterministic delivery, calls and fault points."""

    def __init__(self, factory, project):
        self.factory, self.project = factory, project
        self.prepared, self.consumed, self.handled = [], [], []
        self.prepare_hook = self.consume_hook = self.substitute = None
        self.result = HandlerOutcome.ACKNOWLEDGE
        self.handler_hook = None
        self.options = DeliveryOptions(
            lease_seconds=3, handler_timeout_seconds=2, retry_base_seconds=1
        )
        self.delivery = self.build()

    def build(self, registry=None):
        return outbox_delivery(
            self.factory,
            authorization_factory=lambda session: TracedPort(self, session),
            registry=registry
            if registry is not None
            else HandlerRegistry([("ContributionRecorded", 1, self.handle)]),
            options=self.options,
        )

    async def handle(self, envelope):
        self.handled.append(envelope)
        if self.handler_hook:
            await self.handler_hook(envelope)
        return self.result

    async def append(self, **changes):
        event = _event(changes.pop("project_id", self.project), **changes)
        async with self.factory() as session, session.begin():
            await OutboxService(session).append(event)
        return event

    async def claim(self, **changes):
        event = await self.append(**changes)
        claim = await self.delivery.claim(event.event_id, self.project, "test-worker")
        assert claim is not None
        return claim

    async def envelope(self, claim):
        """Detach the stored event without committing invocation for negative proofs."""
        async with self.factory() as session:
            event = await session.get(OutboxEvent, claim.event_id)
            return OutboxEventEnvelope(
                claim=claim,
                payload_json=json.dumps(event.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                **{key: getattr(event, key) for key in (
                    "event_type", "event_version", "aggregate_type", "aggregate_id",
                    "correlation_id", "causation_event_id", "idempotency_key", "occurred_at",
                )},
            )


@pytest.fixture
async def delivery_harness(outbox_factory):  # noqa: F811 - pytest fixture injection
    factory, project = outbox_factory
    h = Harness(factory, project)
    h.actor_id, h.link_id = new_record_id(), new_record_id()
    async with factory() as session, session.begin():
        session.add(ActorProfile(
            id=str(h.actor_id), actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.OUTBOX_DISPATCHER.value, created_by=str(h.actor_id),
        ))
        await session.flush()
        session.add(ActorIdentityLink(
            id=str(h.link_id), actor_profile_id=str(h.actor_id), issuer="workstream.internal",
            subject=ServiceIdentity.OUTBOX_DISPATCHER.value, subject_kind="service",
            status="active", linked_by="workstream:system:bootstrap",
        ))
    return h


async def phase_decision(session, facts):
    """Real PREP evidence for direct-SQL tests of independent custody guards."""
    async with outbox_dispatch_authorization(session).prepare_outbox_dispatch(
        facts=facts, request_id=new_record_id(), correlation_id=new_record_id(),
    ) as prepared:
        return str((await prepared.consume(facts)).decision_id)
