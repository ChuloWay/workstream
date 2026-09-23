"""Explicit synthetic AUTH proof for hidden mechanics, never live authority."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.modules.authorization.api.decisions import AuthorizationDecision, DecisionOutcome
from app.modules.authorization.api.outbox_dispatch import PreparedOutboxDispatch
from app.modules.outbox.api import DeliveryOptions, DeliveryUnavailable, HandlerOutcome
from app.adapters.outbox import outbox_delivery
from app.modules.outbox.registry import HandlerRegistry
from app.modules.outbox.service import OutboxService
from tests.test_outbox import outbox_database_env, outbox_factory, _event  # noqa: F401


class SyntheticPrepared(PreparedOutboxDispatch):
    """Enforce exact facts and one consumption in the synthetic root transaction."""

    def __init__(self, harness, session, facts):
        self.harness, self.session, self.facts = harness, session, facts
        self.transaction = session.get_transaction()
        self.used = False

    async def consume(self, facts):
        if (
            self.used
            or facts != self.facts
            or self.session.get_transaction() is not self.transaction
        ):
            raise DeliveryUnavailable("synthetic_authority_mismatch")
        self.used = True
        self.harness.consumed.append(facts)
        if self.harness.consume_hook:
            await self.harness.consume_hook(facts)
        return AuthorizationDecision(
            uuid4(),
            self.harness.action,
            self.harness.permission,
            self.harness.outcome,
            "denied" if self.harness.outcome is DecisionOutcome.DENY else None,
        )


class SyntheticPort:
    """Labeled injected contract fixture; audit evidence is intentionally absent."""

    def __init__(self, harness, session):
        self.harness, self.session = harness, session

    @asynccontextmanager
    async def prepare_outbox_dispatch(self, *, facts, request_id, correlation_id):
        self.harness.prepared.append(facts)
        if self.harness.prepare_hook:
            await self.harness.prepare_hook(facts)
        checked = self.harness.substitute(facts) if self.harness.substitute else facts
        yield SyntheticPrepared(self.harness, self.session, checked)


class Harness:
    """Per-test deterministic delivery, calls and fault points."""

    def __init__(self, factory, project):
        self.factory, self.project = factory, project
        self.prepared, self.consumed, self.handled = [], [], []
        self.prepare_hook = self.consume_hook = self.substitute = None
        self.action = self.permission = "outbox.dispatch"
        self.outcome = DecisionOutcome.ALLOW
        self.result = HandlerOutcome.ACKNOWLEDGE
        self.handler_hook = None
        self.options = DeliveryOptions(
            lease_seconds=3, handler_timeout_seconds=2, retry_base_seconds=1
        )
        self.delivery = self.build()

    def build(self, registry=None):
        return outbox_delivery(
            self.factory,
            authorization_factory=lambda session: SyntheticPort(self, session),
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
        event = _event(self.project, **changes)
        async with self.factory() as session, session.begin():
            await OutboxService(session).append(event)
        return event

    async def claim(self, **changes):
        event = await self.append(**changes)
        claim = await self.delivery.claim(event.event_id, self.project, "test-worker")
        assert claim is not None
        return claim


@pytest.fixture
async def delivery_harness(outbox_factory):  # noqa: F811 - pytest fixture injection
    factory, project = outbox_factory
    return Harness(factory, project)
