"""Narrow shared-ledger views injected into checker owner adapters."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.model_usage.api import (
    ModelCallExecutionFacts,
    ModelCallUnavailable,
    ModelEvidenceReservation,
    ModelEvidenceSelector,
    ModelPaidSlotKey,
    ModelRecoveryCandidate,
    ModelRecoveryOwnerFacts,
)
from app.modules.model_usage.models import (
    CheckerModelInvocationGrant,
    CheckerModelUsageSlot,
    ModelUsageEffect,
)
from app.modules.model_usage.repository import ModelCallRepository
from app.modules.model_usage.service import (
    _slot_key,
    _stored_retry_terminal_digest,
    _uuid,
)


class ModelEvidenceCustody:
    """Lock and validate exact shared effect custody after owner locks."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = ModelCallRepository(session)

    async def resolve_evidence(self, selector: ModelEvidenceSelector) -> ModelEvidenceReservation:
        selector = ModelEvidenceSelector.model_validate(selector)
        await self._repo.lock_envelope_scope(selector.paid_slot)
        if await self._repo.envelope(selector.paid_slot, lock=True) is None:
            raise ModelCallUnavailable("model_evidence_unavailable")
        await self._repo.lock_slot_scope(selector.paid_slot)
        slot = await self._repo.slot(selector.paid_slot, lock=True)
        if slot is None or (
            slot.id != str(selector.model_call_slot_id) or slot.task_id != str(selector.task_id)
        ):
            raise ModelCallUnavailable("model_evidence_unavailable")
        effect = await self._repo.attempt(selector.model_call_attempt_id, lock=True)
        if effect is None or effect.checker_slot_id != slot.id:
            raise ModelCallUnavailable("model_evidence_unavailable")
        profile = await self._repo.profile_exact(
            selector.paid_slot.profile_id,
            selector.paid_slot.profile_version,
            selector.paid_slot.profile_digest,
        )
        if profile is None or profile.project_id != str(selector.paid_slot.project_id):
            raise ModelCallUnavailable("model_evidence_profile_unavailable")
        if selector.role == "model_request":
            if effect.request_sha256 != selector.content_sha256:
                raise ModelCallUnavailable("model_evidence_request_conflict")
            maximum = profile.maximum_request_bytes
        else:
            if effect.state not in {"dispatching", "uncertain", "completed", "known_failed"}:
                raise ModelCallUnavailable("model_evidence_effect_unavailable")
            if effect.response_content_sha256 not in {None, selector.content_sha256}:
                raise ModelCallUnavailable("model_evidence_response_conflict")
            maximum = profile.maximum_response_bytes
        return ModelEvidenceReservation(maximum_bytes=maximum)


class ModelRecoverySources:
    """Project retained checker recovery lineage without owner authorization."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ModelCallRepository(session)

    async def recovery_owner(
        self, slot: ModelPaidSlotKey, parent_attempt_id: UUID
    ) -> ModelRecoveryOwnerFacts:
        slot = ModelPaidSlotKey.model_validate(slot)
        slot_row = await self._repo.slot(slot)
        parent = await self._repo.attempt(parent_attempt_id)
        grant = await self._session.scalar(
            select(CheckerModelInvocationGrant).where(
                CheckerModelInvocationGrant.selected_attempt_id == str(parent_attempt_id)
            )
        )
        if (
            slot_row is None
            or parent is None
            or parent.checker_slot_id != slot_row.id
            or grant is None
            or grant.project_id != str(slot.project_id)
            or grant.paid_slot != slot.model_dump(mode="json")
            or grant.selected_request_sha256 != parent.request_sha256
        ):
            raise ModelCallUnavailable("model_recovery_source_unavailable")
        try:
            execution = ModelCallExecutionFacts.model_validate_json(
                json.dumps(grant.execution_facts)
            )
        except ValueError as exc:
            raise ModelCallUnavailable("model_recovery_source_unavailable") from exc
        return ModelRecoveryOwnerFacts(
            checker_run_id=UUID(grant.checker_run_id),
            task_id=UUID(slot_row.task_id),
            execution=execution,
            request_sha256=parent.request_sha256,
        )

    async def recovery_candidates(
        self, source_run_ids: tuple[UUID, ...]
    ) -> dict[UUID, tuple[ModelRecoveryCandidate, ...]]:
        if not source_run_ids:
            return {}
        child = aliased(ModelUsageEffect)
        rows = (
            await self._session.execute(
                select(
                    CheckerModelInvocationGrant.checker_run_id,
                    ModelUsageEffect,
                    CheckerModelUsageSlot,
                    CheckerModelInvocationGrant.registry_entry_id,
                )
                .join(
                    ModelUsageEffect,
                    ModelUsageEffect.id == CheckerModelInvocationGrant.selected_attempt_id,
                )
                .join(
                    CheckerModelUsageSlot,
                    CheckerModelUsageSlot.id == ModelUsageEffect.checker_slot_id,
                )
                .where(
                    CheckerModelInvocationGrant.checker_run_id.in_(
                        tuple(str(value) for value in source_run_ids)
                    ),
                    ModelUsageEffect.state.in_(("known_failed", "known_no_effect")),
                    ~exists(select(child.id).where(child.parent_attempt_id == ModelUsageEffect.id)),
                )
                .order_by(CheckerModelInvocationGrant.checker_run_id, ModelUsageEffect.id)
            )
        ).all()
        projected: dict[UUID, dict[UUID, ModelRecoveryCandidate]] = {}
        for run_id, attempt, slot_row, registry_entry_id in rows:
            digest = _stored_retry_terminal_digest(attempt)
            if digest is None:
                continue
            candidate = ModelRecoveryCandidate(
                parent_attempt_id=_uuid(attempt.id),
                slot=_slot_key(slot_row),
                registry_entry_id=_uuid(registry_entry_id),
                terminal_digest=digest,
                request_sha256=attempt.request_sha256,
            )
            projected.setdefault(_uuid(run_id), {})[candidate.parent_attempt_id] = candidate
        return {run_id: tuple(candidates.values()) for run_id, candidates in projected.items()}


__all__ = ("ModelEvidenceCustody", "ModelRecoverySources")
