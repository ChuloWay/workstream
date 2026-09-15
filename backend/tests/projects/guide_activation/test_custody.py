"""Stored receipt validation never substitutes mutable current policy state."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.projects.api.guide_activation import (
    GuideActivationAuthorityReceipt,
    GuideActivationFacts,
    GuideActivationLocator,
    GuideActivationReceipt,
)
from app.modules.projects.guide_activation.custody import (
    activation_custody,
    load_guide_activation,
    require_authority,
)
from .test_contracts import receipt_values


def custody_case():
    receipt = GuideActivationReceipt(**receipt_values())
    locator = GuideActivationLocator(
        project_id=receipt.command.target.proposal.project_id,
        guide_id=receipt.command.target.proposal.guide_id,
        actor_profile_id=uuid4(),
        identity_link_id=uuid4(),
        operation_id=receipt.operation_id,
        request_id=uuid4(),
    )
    facts = GuideActivationFacts(locator=locator, receipt=receipt)
    authority = GuideActivationAuthorityReceipt(
        actor_profile_id=locator.actor_profile_id,
        identity_link_id=locator.identity_link_id,
        admin_role_grant_id=uuid4(),
        authorization_decision_event_id=uuid4(),
        action_id="project.guide.activate",
        permission_id="project.guide.manage",
        scope_project_id=locator.project_id,
        resource_context_digest=facts.digest,
    )
    record = SimpleNamespace(
        response_json=receipt.model_dump(mode="json"),
        activation_facts_json=facts.resource_json(),
        activation_authority_json=authority.model_dump(mode="json"),
        status="committed",
        action_id="project.guide.activate",
        request_digest=receipt.command.digest,
        resource_context_digest=facts.digest,
        operation_id=receipt.operation_id,
        operation_generation=receipt.activation_generation,
        idempotency_key=receipt.command.idempotency_key,
        setup_run_id=None,
        project_id=str(locator.project_id),
        resource_id=str(locator.guide_id),
        actor_profile_id=str(locator.actor_profile_id),
        identity_link_id=str(locator.identity_link_id),
    )
    return record, receipt, facts, authority


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "pending"),
        ("action_id", "project.guide.create"),
        ("request_digest", "sha256:" + "b" * 64),
        ("resource_context_digest", "sha256:" + "b" * 64),
        ("operation_generation", 3),
        ("setup_run_id", "unexpected"),
        ("actor_profile_id", "other"),
        ("identity_link_id", "other"),
        ("project_id", "other"),
        ("resource_id", "other"),
        ("operation_id", None),
        ("idempotency_key", None),
    ],
)
def test_stored_activation_rejects_mismatched_ledger_identity(field, value):
    record, _, facts, _ = custody_case()
    setattr(record, field, value)
    with pytest.raises(ValueError, match="custody mismatch"):
        activation_custody(record, request_id=facts.locator.request_id)


def test_original_receipt_replay_facts_bind_fresh_request_id_only():
    record, receipt, _, authority = custody_case()
    request = uuid4()
    stored, facts, allowed = activation_custody(record, request_id=request)
    assert stored == receipt and allowed == authority
    assert facts.locator.request_id == request and facts.digest == record.resource_context_digest


@pytest.mark.parametrize(
    "field", ["actor_profile_id", "identity_link_id", "scope_project_id", "resource_context_digest"]
)
def test_consumed_authority_must_match_exact_locked_facts(field):
    _, _, facts, authority = custody_case()
    changed = authority.model_copy(
        update={field: "sha256:" + "b" * 64 if field == "resource_context_digest" else uuid4()}
    )
    with pytest.raises(ValueError, match="authority mismatch"):
        require_authority(changed, facts)


def bound_guide(record, receipt):
    guide = SimpleNamespace(
        id=record.resource_id,
        project_id=record.project_id,
        status="active",
        version=receipt.command.target.proposal.guide_version,
        activation_operation_id=record.operation_id,
        mutation_generation=receipt.activation_generation,
        effective_at=receipt.effective_at,
        approved_by=record.actor_profile_id,
        contribution_policy_id=receipt.command.contribution_policy_id,
        contribution_policy_version_id=receipt.command.contribution_policy_version_id,
    )
    for kind in ("review", "revision"):
        selected = getattr(receipt.command, kind)
        setattr(guide, f"selected_{kind}_policy_id", str(selected.policy_id))
        setattr(guide, f"selected_{kind}_policy_generation", selected.generation)
        setattr(guide, f"selected_{kind}_policy_hash", selected.policy_hash)
    return guide


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "contribution_policy_id",
        "contribution_policy_version_id",
        "mutation_generation",
        "approved_by",
        "effective_at",
        "status",
        "selected_review_policy_id",
        "selected_revision_policy_hash",
    ],
)
async def test_binding_read_rejects_mismatched_guide(field):
    record, receipt, _, _ = custody_case()
    guide = bound_guide(record, receipt)
    setattr(guide, field, None)
    with pytest.raises(ValueError, match="mismatch"):
        await load_guide_activation(SimpleNamespace(scalar=AsyncMock(return_value=record)), guide)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["active", "superseded"])
async def test_binding_read_uses_only_immutable_ledger(status):
    record, receipt, _, _ = custody_case()
    guide = bound_guide(record, receipt)
    guide.status = status
    session = SimpleNamespace(scalar=AsyncMock(return_value=record))
    assert await load_guide_activation(session, guide) == receipt
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_binding_read_requires_operation_and_record():
    record, receipt, _, _ = custody_case()
    guide = bound_guide(record, receipt)
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    with pytest.raises(ValueError, match="binding unavailable"):
        await load_guide_activation(session, guide)
    guide.activation_operation_id = None
    session.scalar.reset_mock()
    with pytest.raises(ValueError, match="binding unavailable"):
        await load_guide_activation(session, guide)
    session.scalar.assert_not_called()
