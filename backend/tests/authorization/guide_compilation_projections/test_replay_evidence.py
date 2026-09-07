"""Real kernel/PREP replay matching against controlled stored-shaped audit facts.

These are service-boundary proofs, not PostgreSQL corruption or isolation tests.
"""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.authorization.api import AuthorizationDenied, PreparedAuthorizationInvalid
from app.modules.authorization.domain.guide_compilation_projections import (
    projection_resource_context,
    projection_resource_digest,
)

from .replay_support import ReplayCase


@pytest.mark.parametrize(
    ("component", "action", "permission", "resource_type"),
    (
        (
            "guide_sufficiency",
            "project.guide_sufficiency.run",
            "project.guide.manage",
            "project_guide_sufficiency_projection",
        ),
        (
            "submission_artifact_policy",
            "project.submission_artifact_policy.derive",
            "project.effective_policy.manage",
            "project_submission_artifact_policy_projection",
        ),
    ),
    ids=("sufficiency", "artifact-policy"),
)
async def test_projection_exact_replay_uses_original_decision(
    monkeypatch, component, action, permission, resource_type
):
    case = ReplayCase(monkeypatch, component)
    async with case.prepare() as prepared:
        receipt = await prepared.consume_new(case.facts)
    stored = await case.evidence.get_authority_event(receipt.decision_event_id)
    assert vars(stored) == {
        "event_type": "SensitiveAuthorizationAllowed",
        "actor_id": str(case.first.actor_profile_id),
        "action_id": action,
        "permission_id": permission,
        "project_id": str(case.locator.project_id),
        "resource_type": resource_type,
        "resource_id": str(prepared.identity.operation_id),
        "request_id": str(prepared.identity.operation_id),
        "correlation_id": str(prepared.identity.correlation_id),
        "after_facts": {
            "allowed": True,
            "resource_context_digest": receipt.resource_context_digest,
        },
    }
    assert (
        projection_resource_digest(
            projection_resource_context(component, prepared.identity, case.facts)
        )
        == receipt.resource_context_digest
    )
    lookup = AsyncMock(wraps=case.evidence.get_authority_event)
    monkeypatch.setattr(case.evidence, "get_authority_event", lookup)
    original_event = case.evidence.events[0]
    async with case.prepare() as replay:
        await replay.validate_replay(case.facts, receipt.decision_event_id)
    lookup.assert_awaited_once_with(receipt.decision_event_id)
    assert case.evidence.events == [original_event]
    assert [close.call_count for close in case.close_spies] == [1, 1]


async def test_projection_replay_rejects_missing_decision_without_new_evidence(monkeypatch):
    case = ReplayCase(monkeypatch)
    missing = uuid4()
    lookup = AsyncMock(wraps=case.evidence.get_authority_event)
    monkeypatch.setattr(case.evidence, "get_authority_event", lookup)
    async with case.prepare() as prepared:
        with pytest.raises(AuthorizationDenied, match="^projection authority denied$"):
            await prepared.validate_replay(case.facts, missing)
    lookup.assert_awaited_once_with(missing)
    assert case.evidence.events == []
    assert case.close_spies[0].call_count == 1


@pytest.mark.parametrize("mutate_facts", (False, True), ids=("same-facts", "changed-facts"))
async def test_projection_replay_retires_mutation_authority(monkeypatch, mutate_facts):
    case = ReplayCase(monkeypatch)
    async with case.prepare() as prepared:
        receipt = await prepared.consume_new(case.facts)
    async with case.prepare() as replay:
        await replay.validate_replay(case.facts, receipt.decision_event_id)
        assert case.services[1]._authorization._sealed_prelocked == set()
        next_facts = replace(case.facts, guide_version="v2") if mutate_facts else case.facts
        with pytest.raises(PreparedAuthorizationInvalid):
            await replay.consume_new(next_facts)
    assert len(case.evidence.events) == 1


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("event_type", "SensitiveAuthorizationDenied"),
        ("actor_id", "uuid"),
        ("action_id", "project.read"),
        ("permission_id", "project.read"),
        ("project_id", "uuid"),
        ("resource_type", "project_submission_artifact_policy_projection"),
        ("resource_id", "uuid"),
        ("request_id", "uuid"),
        ("correlation_id", "uuid"),
        ("allowed", False),
        ("allowed", 1),
        ("resource_context_digest", "sha256:" + "b" * 64),
    ),
    ids=(
        "event-type",
        "actor",
        "action",
        "permission",
        "project",
        "resource-type",
        "resource-id",
        "request",
        "correlation",
        "denied",
        "truthy-allowed",
        "digest",
    ),
)
async def test_projection_replay_rejects_substituted_existing_decision(
    monkeypatch, field, replacement
):
    case = ReplayCase(monkeypatch)
    async with case.prepare() as original:
        receipt = await original.consume_new(case.facts)
    original_event = case.evidence.events[0]
    read = case.evidence.get_authority_event
    source = await read(receipt.decision_event_id)
    assert source is not None
    snapshot = deepcopy(vars(source))
    values = {**vars(source), "after_facts": dict(source.after_facts)}
    target = values["after_facts"] if field in ("allowed", "resource_context_digest") else values
    replacement = str(uuid4()) if replacement == "uuid" else replacement
    assert type(target[field]) is not type(replacement) or target[field] != replacement
    target[field] = replacement
    substituted = SimpleNamespace(**values)
    resolved = []

    async def lookup(event_id):
        existing = await read(event_id)
        assert existing is not None  # Never let a missing fixture stand in for a mismatch.
        resolved.append(existing)
        return substituted

    lookup_spy = AsyncMock(side_effect=lookup)
    monkeypatch.setattr(case.evidence, "get_authority_event", lookup_spy)
    async with case.prepare() as replay:
        with pytest.raises(AuthorizationDenied, match="^projection authority denied$"):
            await replay.validate_replay(case.facts, receipt.decision_event_id)
        assert case.services[1]._authorization._sealed_prelocked == set()
        with pytest.raises(PreparedAuthorizationInvalid):
            await replay.consume_new(case.facts)
    lookup_spy.assert_awaited_once_with(receipt.decision_event_id)
    assert len(resolved) == 1 and vars(resolved[0]) == snapshot
    assert case.evidence.events == [original_event]
    assert vars(await read(receipt.decision_event_id)) == snapshot
    assert [close.call_count for close in case.close_spies] == [1, 1]
