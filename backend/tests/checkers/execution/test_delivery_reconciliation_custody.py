"""PostgreSQL custody proofs for recovered completion routing."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.adapters.outbox import production_outbox_delivery
from app.adapters.tasks import (
    reconciliation_task_post_submit_outcome,
    task_post_submit_outcome,
)
from app.core.identifiers import new_record_id
from app.modules.authorization.domain.post_submit_deliveries import (
    PostSubmitDeliveryResourceContext,
)
from app.modules.authorization.domain.resource_digest import (
    authorization_resource_digest,
)
from app.modules.checkers.api.delivery_reconciliation import (
    PostSubmitDeliveryPreparation,
    post_submit_delivery_request_digest,
)
from app.modules.checkers.delivery_reconciliation import RECONCILIATION_EVENT
from app.modules.checkers.delivery_reconciliation_handler import (
    ReconciliationInvocationCustody,
)
from app.modules.outbox.api import (
    CommittedInvocationObservation,
    FinalizationCause,
    HandlerOutcome,
    OutboxClaim,
    OutboxEventEnvelope,
)
from app.modules.outbox.delivery import CommittedInvocationReader
from app.modules.outbox.delivery_repository import DeliveryRepository
from app.modules.outbox.service import OutboxService
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    admin_access as admin_access,
    signed_access as signed_access,
)
from tests.reviews.lifecycle.fixtures import (
    live_acceptance_lifecycle as live_acceptance_lifecycle,
)
from tests.checkers.execution.test_delivery_reconciliation_public import (
    _retained_effect_rows,
)
from tests.tasks.post_submit_routing.outcome_support import (
    apply_outcome,
    authorized_routing_source,
)


_ROUTING_GUARD = "public.guard_task_routing_authority()"


@dataclass(frozen=True)
class _RecoveredCompletion:
    source: Any
    child: OutboxEventEnvelope
    delivery: Any


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _refresh_authorization_binding(payload: dict[str, Any]) -> None:
    """Recompute the child's two canonical digests after a coherent mutation."""
    resource_json = json.loads(payload["authorization_resource_json"])
    preparation_json = resource_json["resource_context"]["preparation"]
    preparation = PostSubmitDeliveryPreparation.model_validate_json(
        _canonical_json(preparation_json)
    )
    resource = PostSubmitDeliveryResourceContext.model_validate_json(
        _canonical_json(resource_json["resource_context"])
    )
    payload["request_digest"] = post_submit_delivery_request_digest(preparation)
    payload["authorization_resource_digest"] = authorization_resource_digest(resource)
    payload["authorization_resource_json"] = _canonical_json(resource_json)


def _mutate_child_payload(payload: dict[str, Any], mutation: str) -> None:
    """Change one semantic relation while retaining canonical event bytes/digests."""
    if mutation == "original_selector":
        payload["original_event_id"] = str(new_record_id())
        return

    resource = json.loads(payload["authorization_resource_json"])
    preparation = resource["resource_context"]["preparation"]
    if mutation == "classification":
        payload["classification"] = "committed"
        preparation["source"]["classification"] = "committed"
    elif mutation == "request_cause":
        preparation["command"]["reason"] = (
            "Substituted reason with no retained Operator decision"
        )
    elif mutation == "operator_resource":
        actor_id = str(new_record_id())
        payload["operator_actor_profile_id"] = actor_id
        preparation["command"]["actor_profile_id"] = actor_id
    else:  # pragma: no cover - closed test input
        raise AssertionError(f"unsupported child mutation: {mutation}")
    payload["authorization_resource_json"] = _canonical_json(resource)
    _refresh_authorization_binding(payload)


@asynccontextmanager
async def _recovered_completion(
    tmp_path,
    database_url: str,
    access,
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload_mutation: str | None = None,
):
    """Create one terminal UNKNOWN original and one live invoked recovery child."""
    async with authorized_routing_source(
        tmp_path,
        database_url,
        human_review_required=False,
        contribution_awards=("project_points",),
    ) as source:
        async with source.factory() as session:
            await session.begin()
            await apply_outcome(session, source, 2)
            await session.rollback()
        await source.completion_delivery.finalize(
            source.envelope.claim,
            FinalizationCause.UNKNOWN,
        )

        original_append = OutboxService.append

        async def append_with_mutation(self, value):
            if value.event_type == RECONCILIATION_EVENT:
                payload = json.loads(_canonical_json(value.payload))
                assert payload_mutation is not None
                _mutate_child_payload(payload, payload_mutation)
                value = value.model_copy(update={"payload": payload})
            return await original_append(self, value)

        collection = (
            f"/api/v1/operations/projects/{source.request.project_id}"
            "/post-submit-deliveries"
        )
        command = f"{collection}/{source.envelope.claim.event_id}/reconcile"
        with monkeypatch.context() as child_patch:
            if payload_mutation is not None:
                child_patch.setattr(OutboxService, "append", append_with_mutation)
            response = await access.signed.client.post(
                command,
                headers=access.target.headers
                | {"Idempotency-Key": str(new_record_id())},
                json={"reason": "Reconcile exact uncertain completion custody"},
            )
        assert response.status_code == 201, response.text
        child_id = UUID(response.json()["successor"]["event_id"])
        delivery = production_outbox_delivery(source.factory)
        claim = await delivery.claim(
            child_id,
            source.request.project_id,
            "reconciliation-custody-proof",
        )
        assert claim is not None
        child = await delivery._begin_invocation(claim)
        assert child is not None
        yield _RecoveredCompletion(source=source, child=child, delivery=delivery)


def _production_custody(session, recovered: _RecoveredCompletion):
    return ReconciliationInvocationCustody(
        child=recovered.child,
        original=recovered.source.envelope,
        observer=CommittedInvocationReader(recovered.source.factory),
        deliveries=DeliveryRepository(session),
    )


class _DatabaseGuardCustody:
    """Test-only seam that leaves finalized-child rejection to the SQL owner."""

    def __init__(self, original: OutboxEventEnvelope) -> None:
        self._original = original

    async def observe_invocation(self, envelope):
        return self._observation(envelope)

    async def fence_invocation(self, envelope):
        return self._observation(envelope)

    def _observation(self, envelope):
        if envelope != self._original:
            return None
        return CommittedInvocationObservation(
            claim=self._original.claim,
            observed_at=self._original.claim.claimed_at,
        )


async def _apply_recovered(
    session,
    recovered: _RecoveredCompletion,
    claim: OutboxClaim | None,
    *,
    custody=None,
):
    selected_custody = custody or _production_custody(session, recovered)

    if claim is None:
        outcome = reconciliation_task_post_submit_outcome(
            session,
            recovered.source.factory,
            selected_custody,
            None,
        )
        generation = await outcome.observe_delivery_generation(
            recovered.source.envelope
        )
        return await outcome.apply(
            recovered.source.envelope,
            current_generation=generation,
        )

    async def reconciliation_claim() -> OutboxClaim:
        return claim

    outcome = reconciliation_task_post_submit_outcome(
        session,
        recovered.source.factory,
        selected_custody,
        reconciliation_claim,
    )
    generation = await outcome.observe_delivery_generation(
        recovered.source.envelope
    )
    return await outcome.apply(
        recovered.source.envelope,
        current_generation=generation,
    )


async def _assert_guard_rejects(
    session,
    recovered: _RecoveredCompletion,
    claim: OutboxClaim | None,
    message: str,
    *,
    custody=None,
) -> None:
    with pytest.raises(DBAPIError, match=message) as caught:
        await _apply_recovered(
            session,
            recovered,
            claim,
            custody=custody,
        )
    assert getattr(caught.value.orig, "sqlstate", None) == "23514"


@pytest.mark.asyncio
async def test_routing_guard_preserves_ordinary_completion_path(
    tmp_path,
    auth_database_env,
    live_acceptance_lifecycle,
) -> None:
    """A live ordinary completion retains its original no-child authority shape."""
    async with authorized_routing_source(
        tmp_path,
        auth_database_env,
        human_review_required=False,
        contribution_awards=("project_points",),
    ) as source:
        async with source.factory() as session:
            await session.begin()
            result = await task_post_submit_outcome(
                session, source.factory
            ).apply(source.envelope, current_generation=2)
            authority_context = await session.scalar(
                text(
                    "SELECT authority_context FROM "
                    "public.task_post_submit_routing_manifests WHERE id=:id"
                ),
                {"id": result.routing_manifest_id},
            )
            assert "reconciliation_claim" not in authority_context
            await session.rollback()


@pytest.mark.asyncio
async def test_routing_guard_accepts_exact_live_reconciliation_child(
    tmp_path,
    auth_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
) -> None:
    """The exact live child can route its terminal UNKNOWN original once."""
    async with _recovered_completion(
        tmp_path,
        auth_database_env,
        live_acceptance_lifecycle,
        monkeypatch,
    ) as recovered:
        async with recovered.source.factory() as session:
            await session.begin()
            result = await _apply_recovered(
                session,
                recovered,
                recovered.child.claim,
            )
            authority_context = await session.scalar(
                text(
                    "SELECT authority_context FROM "
                    "public.task_post_submit_routing_manifests WHERE id=:id"
                ),
                {"id": result.routing_manifest_id},
            )
            assert authority_context["reconciliation_claim"] == (
                recovered.child.claim.model_dump(mode="json")
            )
            await session.rollback()


@pytest.mark.asyncio
async def test_recovered_manifest_replays_after_handler_response_loss(
    tmp_path,
    auth_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
) -> None:
    """A repeated live-child invocation validates the retained recovered manifest."""
    async with _recovered_completion(
        tmp_path,
        auth_database_env,
        live_acceptance_lifecycle,
        monkeypatch,
    ) as recovered:
        handler = recovered.delivery._registry.get(
            recovered.child.event_type,
            recovered.child.event_version,
        )
        assert handler is not None
        assert await handler(recovered.child) is HandlerOutcome.ACKNOWLEDGE
        retained = await _retained_effect_rows(
            recovered.source.factory,
            recovered.source.request.project_id,
        )

        assert await handler(recovered.child) is HandlerOutcome.ACKNOWLEDGE
        assert await _retained_effect_rows(
            recovered.source.factory,
            recovered.source.request.project_id,
        ) == retained
        receipt = await recovered.delivery.finalize(
            recovered.child.claim,
            FinalizationCause.ACKNOWLEDGE,
        )
        assert json.loads(receipt.outcome_json)["delivery_state"] == "acknowledged"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation,message",
    [
        ("missing", "routing invocation unavailable"),
        ("wrong", "routing reconciliation invocation differs"),
        ("finalized", "routing reconciliation invocation unavailable"),
    ],
)
async def test_routing_guard_rejects_missing_wrong_or_finalized_child_claim(
    tmp_path,
    auth_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
    mutation,
    message,
) -> None:
    """Recovery needs the exact still-live child claim, not a shaped substitute."""
    async with _recovered_completion(
        tmp_path,
        auth_database_env,
        live_acceptance_lifecycle,
        monkeypatch,
    ) as recovered:
        claim: OutboxClaim | None = recovered.child.claim
        custody = None
        if mutation == "missing":
            claim = None
        elif mutation == "wrong":
            claim = claim.model_copy(update={"claim_owner": "wrong-custody-owner"})
        else:
            await recovered.delivery.finalize(claim, FinalizationCause.UNKNOWN)
            custody = _DatabaseGuardCustody(recovered.source.envelope)

        async with recovered.source.factory() as session:
            await session.begin()
            await _assert_guard_rejects(
                session,
                recovered,
                claim,
                message,
                custody=custody,
            )
            await session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation,message",
    [
        ("original_selector", "routing reconciliation child differs"),
        ("classification", "routing reconciliation child differs"),
        ("request_cause", "routing reconciliation cause differs"),
        ("operator_resource", "routing reconciliation cause differs"),
    ],
)
async def test_routing_guard_rejects_substituted_child_and_operator_cause(
    tmp_path,
    auth_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
    mutation,
    message,
) -> None:
    """Canonical child bytes cannot substitute source or retained Operator cause."""
    async with _recovered_completion(
        tmp_path,
        auth_database_env,
        live_acceptance_lifecycle,
        monkeypatch,
        payload_mutation=mutation,
    ) as recovered:
        async with recovered.source.factory() as session:
            await session.begin()
            await _assert_guard_rejects(
                session,
                recovered,
                recovered.child.claim,
                message,
            )
            await session.rollback()


@pytest.mark.asyncio
async def test_reconciliation_claim_guard_removal_admits_wrong_claim_only_in_mutant(
    tmp_path,
    auth_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
) -> None:
    """The final SQL claim equality is independently necessary and transactional."""
    async with _recovered_completion(
        tmp_path,
        auth_database_env,
        live_acceptance_lifecycle,
        monkeypatch,
    ) as recovered:
        wrong_claim = recovered.child.claim.model_copy(
            update={"claim_owner": "wrong-custody-owner"}
        )
        async with recovered.source.factory() as session:
            await session.begin()
            await _assert_guard_rejects(
                session,
                recovered,
                wrong_claim,
                "routing reconciliation invocation differs",
            )
            await session.rollback()

            canonical = await session.scalar(
                text(
                    "SELECT pg_get_functiondef(CAST(:name AS regprocedure))"
                ),
                {"name": _ROUTING_GUARD},
            )
            marker = "routing reconciliation invocation differs"
            assert canonical.count(marker) == 1
            marker_at = canonical.index(marker)
            start = canonical.rfind("IF ", 0, marker_at)
            end = canonical.index("END IF;", marker_at) + len("END IF;")
            removed = canonical[start:end]
            assert "reconciliation_claim" in removed
            assert "expected_claim" in removed
            await session.execute(text(canonical[:start] + "NULL;" + canonical[end:]))

            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                await _assert_guard_rejects(
                    session,
                    recovered,
                    wrong_claim,
                    "routing reconciliation invocation differs",
                )
            await session.rollback()

        async with recovered.source.factory() as session:
            restored = await session.scalar(
                text(
                    "SELECT pg_get_functiondef(CAST(:name AS regprocedure))"
                ),
                {"name": _ROUTING_GUARD},
            )
        assert restored == canonical
