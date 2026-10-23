"""Authorized redacted reads for one exact durable model effect."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.model_usage.api import (
    ModelCallAuthorityPort,
    ModelCallEvidence,
    ModelCallUnavailable,
    ModelCallUsage,
    ModelPaidSlotKey,
    ModelUsageEffectInspection,
    ModelUsageInspectionFacts,
    SetupModelUsageSlotKey,
    model_action_digest,
)
from app.modules.model_usage.models import (
    CheckerModelUsageSlot,
    ModelUsageEffect,
    SetupModelUsageSlot,
)
from app.modules.model_usage.repository import require_model_call_transaction


def _uuid(value: str | UUID) -> UUID:
    """Decode a stored canonical record identifier."""
    return UUID(str(value))


def _checker_key(row: CheckerModelUsageSlot) -> ModelPaidSlotKey:
    """Project one stored checker slot into its public stable owner key."""
    return ModelPaidSlotKey(
        project_id=_uuid(row.project_id),
        assignment_id=_uuid(row.assignment_id),
        submission_id=_uuid(row.submission_id),
        submission_version=row.submission_version,
        requirement_id=row.requirement_id,
        registry_entry_digest=row.registry_entry_digest,
        configuration_sha256=row.configuration_sha256,
        profile_id=_uuid(row.profile_id),
        profile_version=row.profile_version,
        profile_digest=row.profile_digest,
        slot_index=row.slot_index,
    )


def _setup_key(row: SetupModelUsageSlot) -> SetupModelUsageSlotKey:
    """Project one stored setup slot into its public stable owner key."""
    return SetupModelUsageSlotKey(
        compilation_attempt_id=_uuid(row.compilation_attempt_id),
        project_id=_uuid(row.project_id),
        guide_id=_uuid(row.guide_id),
        source_snapshot_id=_uuid(row.source_snapshot_id),
        setup_run_id=_uuid(row.setup_run_id),
        setup_generation=row.setup_generation,
        runtime_configuration_hash=row.runtime_configuration_hash,
        profile_id=_uuid(row.profile_id),
        profile_version=row.profile_version,
        profile_digest=row.profile_digest,
        phase=row.phase,
        call_index=row.call_index,
    )


def _optional_evidence(row: ModelUsageEffect, prefix: str) -> ModelCallEvidence | None:
    """Return complete bounded ART facts or reject partial retained custody."""
    values = {
        "binding_id": getattr(row, f"{prefix}_binding_id"),
        "content_id": getattr(row, f"{prefix}_content_id"),
        "put_attempt_id": getattr(row, f"{prefix}_put_attempt_id"),
        "verification_receipt_id": getattr(row, f"{prefix}_verification_receipt_id"),
        "content_sha256": getattr(row, f"{prefix}_content_sha256"),
        "byte_count": getattr(row, f"{prefix}_byte_count"),
    }
    if all(value is None for value in values.values()):
        return None
    if any(value is None for value in values.values()):
        raise ModelCallUnavailable("model_usage_inspection_unavailable")
    for field in ("binding_id", "content_id", "put_attempt_id", "verification_receipt_id"):
        values[field] = _uuid(values[field])
    return ModelCallEvidence.model_validate(values)


def _optional_usage(row: ModelUsageEffect) -> ModelCallUsage | None:
    """Return complete provider usage or reject a partial usage tuple."""
    values = {
        "input_tokens": row.input_tokens,
        "cached_input_tokens": row.cached_input_tokens,
        "output_tokens": row.output_tokens,
        "reasoning_tokens": row.reasoning_tokens,
    }
    if all(value is None for value in values.values()):
        return None
    if any(value is None for value in values.values()):
        raise ModelCallUnavailable("model_usage_inspection_unavailable")
    return ModelCallUsage.model_validate(values)


class ModelUsageInspectionService:
    """Authorize before reading MODEL-USAGE and conceal absent or foreign effects."""

    def __init__(self, session: AsyncSession, authority: ModelCallAuthorityPort) -> None:
        """Bind one database transaction to the exact-effect authority port."""
        self._session = session
        self._authority = authority

    async def inspect_effect(self, facts: ModelUsageInspectionFacts) -> ModelUsageEffectInspection:
        """Authorize and return one redacted same-project paid effect."""
        require_model_call_transaction(self._session)
        facts = ModelUsageInspectionFacts.model_validate(facts)
        evidence = await self._authority.authorize_usage_read(facts)
        if evidence.facts_digest != model_action_digest("usage_read", facts):
            raise ModelCallUnavailable("model_call_authority_unavailable")

        effect = await self._session.get(ModelUsageEffect, str(facts.effect_id))
        if effect is None:
            raise ModelCallUnavailable("model_usage_inspection_unavailable")
        if effect.checker_slot_id is not None:
            slot = await self._session.get(CheckerModelUsageSlot, effect.checker_slot_id)
            owner_kind = "checker"
            owner = _checker_key(slot) if slot is not None else None
        else:
            slot = await self._session.get(SetupModelUsageSlot, effect.setup_slot_id)
            owner_kind = "setup"
            owner = _setup_key(slot) if slot is not None else None
        if owner is None or owner.project_id != facts.project_id:
            raise ModelCallUnavailable("model_usage_inspection_unavailable")

        return ModelUsageEffectInspection(
            project_id=facts.project_id,
            effect_id=facts.effect_id,
            owner_kind=owner_kind,
            owner=owner,
            attempt_number=effect.attempt_number,
            state=effect.state,
            provider_response_known=effect.provider_response_id is not None,
            request_evidence=_optional_evidence(effect, "request"),
            response_evidence=_optional_evidence(effect, "response"),
            usage=_optional_usage(effect),
            budget_configuration_id=(
                _uuid(effect.budget_configuration_id)
                if effect.budget_configuration_id is not None
                else None
            ),
            budget_configuration_version=effect.budget_configuration_version,
            budget_configuration_digest=effect.budget_configuration_digest,
            reserved_nanodollars=effect.reserved_nanodollars,
            settled_nanodollars=effect.settled_nanodollars,
            uncertainty_digest=effect.uncertainty_digest,
            prepared_at=effect.prepared_at,
            dispatched_at=effect.dispatched_at,
            terminal_at=effect.terminal_at,
        )


__all__ = ("ModelUsageInspectionService",)
