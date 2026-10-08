"""Separate observer and TASK resolver boundaries with real stored lineages."""

import json

import pytest

from app.adapters.checkers import evaluation_coordinator
from app.core.hashing import canonical_json_hash
from app.modules.outbox.api import HandlerOutcome
from app.modules.tasks.evaluation_delivery import EvaluationDeliveryRequestReader, EvaluationDeliveryUnavailable
from tests.post_submit_materialization_helpers import material_fixture
from .support import claimed_envelope, delivery_fixture, invoked, state


async def test_claim_without_committed_invocation_cannot_execute(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h)
        claim = await d.delivery.claim(h.created.evaluation_event_id, h.request.project_id, "uninvoked")
        envelope = await claimed_envelope(h, claim)
        before = await state(h)
        assert await d.handler(envelope) is HandlerOutcome.REJECT
        assert await state(h) == before and not h.store.opens and not h.preparation._active
        committed = await d.delivery._begin_invocation(claim)
        assert await d.handler(committed) is HandlerOutcome.ACKNOWLEDGE


def changed_payload(envelope, **changes):
    payload = json.loads(envelope.payload_json)
    payload.update(changes)
    return envelope.model_copy(update={
        "payload_json": json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        "claim": envelope.claim.model_copy(update={"payload_digest": canonical_json_hash(payload)}),
    })


async def test_resolver_and_observer_independently_reject_foreign_facts(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path / "one", isolated_database_env) as h:
        async with material_fixture(tmp_path / "two", isolated_database_env,
                                    provision_services=False, storage_settings=h.settings) as other:
            d = await delivery_fixture(h)
            second = await delivery_fixture(other)
            envelope, foreign = await invoked(h, d), await invoked(other, second)
            before, other_before = await state(h), await state(other)
            async with h.factory() as session, session.begin():
                reader = EvaluationDeliveryRequestReader(session, evaluation_coordinator(session))
                assert await reader.read(envelope) == h.request
                assert await reader.read(foreign) == other.request
                foreign_payload = json.loads(foreign.payload_json)
                substitutions = [
                    changed_payload(envelope, **{key: value})
                    for key, value in foreign_payload.items()
                    if value != json.loads(envelope.payload_json)[key]
                ]
                substitutions.extend([
                    changed_payload(envelope, evaluation_generation=2),
                    changed_payload(envelope, submission_version=2),
                    envelope.model_copy(update={"aggregate_id": foreign.aggregate_id}),
                    envelope.model_copy(update={"correlation_id": foreign.correlation_id}),
                    envelope.model_copy(update={"claim": envelope.claim.model_copy(update={
                        "project_id": foreign.claim.project_id,
                    })}),
                    envelope.model_copy(update={"claim": envelope.claim.model_copy(update={
                        "event_id": foreign.claim.event_id,
                    })}),
                ])
                for mixed in substitutions:
                    # Direct owner proof: no earlier observer can mask this guard.
                    with pytest.raises(EvaluationDeliveryUnavailable, match="evaluation_delivery_unavailable"):
                        await reader.read(mixed)
                    assert await d.handler(mixed) is HandlerOutcome.REJECT
            assert await state(h) == before and await state(other) == other_before
            assert not h.store.opens and not other.store.opens and not h.preparation._active


async def test_resolver_rejects_crossed_checker_reservation(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path / "one", isolated_database_env) as h:
        async with material_fixture(tmp_path / "two", isolated_database_env,
                                    provision_services=False, storage_settings=h.settings) as other:
            d = await delivery_fixture(h)
            envelope = await invoked(h, d)
            async with h.factory() as session, session.begin():
                coordinator = evaluation_coordinator(session)
                current = await coordinator.read_reserved_evaluation(
                    project_id=h.request.project_id, task_id=h.request.task_id,
                    submission_id=h.request.submission_id, request_id=h.request.evaluation_request_id,
                )
                foreign = await coordinator.read_reserved_evaluation(
                    project_id=other.request.project_id, task_id=other.request.task_id,
                    submission_id=other.request.submission_id, request_id=other.request.evaluation_request_id,
                )

                class Crossed:
                    async def read_reserved_evaluation(self, **selectors):
                        assert await coordinator.read_reserved_evaluation(**selectors) == current
                        return replacement

                reader = EvaluationDeliveryRequestReader(session, Crossed())
                for replacement in (
                    current.model_copy(update={"request": foreign.request}),
                    current.model_copy(update={"reservation": foreign.reservation}),
                    current.model_copy(update={"reservation": current.reservation.model_copy(update={
                        "attempt_id": foreign.reservation.attempt_id,
                    })}),
                    current.model_copy(update={"reservation": current.reservation.model_copy(update={
                        "result_id": foreign.reservation.result_id,
                    })}),
                ):
                    with pytest.raises(EvaluationDeliveryUnavailable):
                        await reader.read(envelope)
                replacement = current
                assert await reader.read(envelope) == h.request
            assert not h.store.opens and not other.store.opens
