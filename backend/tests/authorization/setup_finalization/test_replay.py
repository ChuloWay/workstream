"""Fresh exact replay authority and complete historical allow-envelope binding."""

from uuid import uuid4

import pytest

from app.modules.authorization.api import AuthorizationDenied
from app.modules.authorization.runtime import ActorStatus, IdentityLinkStatus
from .support import Case


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_domain", "legacy_lifecycle"),
        ("event_type", "SensitiveAuthorizationDenied"),
        ("actor_ref_kind", "external_subject"),
        ("actor_id", str(uuid4())),
        ("action_id", "project.guide_sufficiency.run"),
        ("permission_id", "project.read"),
        ("project_id", str(uuid4())),
        ("resource_type", "project_setup_run_mutation"),
        ("resource_id", str(uuid4())),
        ("request_id", str(uuid4())),
        ("correlation_id", str(uuid4())),
        ("denial_code", "resource_guard_denied"),
        ("after_facts", None),
        ("after_facts", {"allowed": 1}),
        ("after_facts", {"allowed": True, "resource_context_digest": "wrong"}),
    ],
)
async def test_historical_decision_envelope_is_exact(monkeypatch, field, value):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        receipt = await prepared.consume_new(case.facts)
    async with case.prepare() as prepared:
        await prepared.validate_replay(case.facts, receipt.decision_event_id)
    case.event_changes[field] = value
    async with case.prepare() as prepared:
        with pytest.raises(AuthorizationDenied, match="finalization authority denied"):
            await prepared.validate_replay(case.facts, receipt.decision_event_id)
    assert len(case.evidence.events) == 1
    assert case.closed == case.services


@pytest.mark.parametrize("mutation", ["extra_key", "integer_allowed"])
async def test_replay_rejects_noncanonical_after_facts(monkeypatch, mutation):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        receipt = await prepared.consume_new(case.facts)
    async with case.prepare() as prepared:
        await prepared.validate_replay(case.facts, receipt.decision_event_id)
    event = await case.evidence.get_authority_event(receipt.decision_event_id)
    altered = dict(event.after_facts)
    altered.update({"unexpected": "tampered"} if mutation == "extra_key" else {"allowed": 1})
    case.event_changes["after_facts"] = altered
    async with case.prepare() as prepared:
        with pytest.raises(AuthorizationDenied, match="finalization authority denied"):
            await prepared.validate_replay(case.facts, receipt.decision_event_id)
    assert len(case.evidence.events) == 1
    assert case.closed == case.services


async def test_missing_historical_decision_denies(monkeypatch):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        with pytest.raises(AuthorizationDenied):
            await prepared.validate_replay(case.facts, uuid4())
    assert case.evidence.events == []


@pytest.mark.parametrize("status", ["suspended", "deactivated", "revoked"])
async def test_fresh_prepare_rechecks_current_lifecycle(monkeypatch, status):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        receipt = await prepared.consume_new(case.facts)
    repository = case.first.service._repository
    if status == "revoked":
        repository.link_status = IdentityLinkStatus.REVOKED
    else:
        repository.actor_status = ActorStatus(status)
    with pytest.raises(AuthorizationDenied):
        async with case.prepare() as prepared:
            await prepared.validate_replay(case.facts, receipt.decision_event_id)
    assert len(case.evidence.events) == 1
    assert case.closed == case.services
