"""Redacted exact-effect inspection without provider or transcript disclosure."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.model_usage.api import (
    ModelActionEvidence,
    ModelCallUnavailable,
    ModelUsageInspectionFacts,
    model_action_digest,
)
from app.modules.model_usage.inspection import ModelUsageInspectionService
from app.modules.model_usage.models import CheckerModelUsageSlot, ModelUsageEffect


def sha(label: str) -> str:
    return canonical_json_hash({"label": label})


class _Transaction:
    is_active = True


class _Session:
    def __init__(self, effect, slot) -> None:
        self.sync_session = self
        self._effect = effect
        self._slot = slot

    def get_transaction(self):
        return _Transaction()

    def in_nested_transaction(self):
        return False

    async def get(self, model, identity):
        if model is ModelUsageEffect and identity == self._effect.id:
            return self._effect
        if model is CheckerModelUsageSlot and identity == self._slot.id:
            return self._slot
        return None


class _Authority:
    def __init__(self) -> None:
        self.facts = None

    async def authorize_usage_read(self, facts):
        self.facts = facts
        return ModelActionEvidence(
            evidence_id=new_record_id(),
            facts_digest=model_action_digest("usage_read", facts),
        )


def _rows(project_id):
    slot = SimpleNamespace(
        id=str(new_record_id()),
        project_id=str(project_id),
        assignment_id=str(new_record_id()),
        submission_id=str(new_record_id()),
        submission_version=1,
        requirement_id="model_review",
        registry_entry_digest=sha("registry"),
        configuration_sha256=sha("configuration"),
        profile_id=str(new_record_id()),
        profile_version=2,
        profile_digest=sha("profile"),
        slot_index=1,
    )
    effect = SimpleNamespace(
        id=str(new_record_id()),
        checker_slot_id=slot.id,
        setup_slot_id=None,
        attempt_number=1,
        state="uncertain",
        provider_response_id="provider-secret-coordinate",
        request_binding_id=None,
        request_content_id=None,
        request_put_attempt_id=None,
        request_verification_receipt_id=None,
        request_content_sha256=None,
        request_byte_count=None,
        response_binding_id=None,
        response_content_id=None,
        response_put_attempt_id=None,
        response_verification_receipt_id=None,
        response_content_sha256=None,
        response_byte_count=None,
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        reasoning_tokens=None,
        budget_configuration_id=str(new_record_id()),
        budget_configuration_version=3,
        budget_configuration_digest=sha("budget"),
        reserved_nanodollars=42,
        settled_nanodollars=None,
        uncertainty_digest=sha("uncertain"),
        prepared_at=datetime.now(UTC),
        dispatched_at=datetime.now(UTC),
        terminal_at=None,
    )
    return effect, slot


@pytest.mark.asyncio
async def test_inspection_authorizes_first_and_redacts_provider_coordinate() -> None:
    project_id = new_record_id()
    effect, slot = _rows(project_id)
    authority = _Authority()
    facts = ModelUsageInspectionFacts(
        project_id=project_id,
        effect_id=effect.id,
        actor_profile_id=new_record_id(),
        request_id=new_record_id(),
    )

    result = await ModelUsageInspectionService(_Session(effect, slot), authority).inspect_effect(
        facts
    )

    assert authority.facts == facts
    assert result.provider_response_known is True
    assert result.model_dump(mode="json").get("provider_response_id") is None
    assert result.owner.project_id == project_id
    assert result.owner.assignment_id.hex == slot.assignment_id.replace("-", "")
    assert result.owner.slot_index == 1
    assert result.reserved_nanodollars == 42


@pytest.mark.asyncio
async def test_inspection_conceals_wrong_project_and_missing_effect() -> None:
    project_id = new_record_id()
    effect, slot = _rows(project_id)
    authority = _Authority()
    service = ModelUsageInspectionService(_Session(effect, slot), authority)

    with pytest.raises(ModelCallUnavailable, match="inspection_unavailable"):
        await service.inspect_effect(
            ModelUsageInspectionFacts(
                project_id=new_record_id(),
                effect_id=effect.id,
                actor_profile_id=new_record_id(),
                request_id=new_record_id(),
            )
        )
    with pytest.raises(ModelCallUnavailable, match="inspection_unavailable"):
        await service.inspect_effect(
            ModelUsageInspectionFacts(
                project_id=project_id,
                effect_id=new_record_id(),
                actor_profile_id=new_record_id(),
                request_id=new_record_id(),
            )
        )
