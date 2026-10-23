"""Shared ledger service for exact setup-owned model-use subjects."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.model_usage.api import (
    CompletedSetupModelUsageEffect,
    KnownNoEffectProof,
    KnownNoEffectSetupModelUsageEffect,
    ModelActionEvidence,
    ModelCallBudgetUnavailable,
    ModelCallConflict,
    ModelCallEvidence,
    ModelCallUsage,
    ModelCallUnavailable,
    ObservedSetupModelUsageEffect,
    PreparedSetupModelUsageEffect,
    SetupModelDispatchReservation,
    SetupModelEffectAuthorityFacts,
    SetupModelOwnerProfile,
    SetupModelUsageAuthorityPort,
    SetupModelUsageEvidencePort,
    SetupModelUsageOwnerPort,
    SetupModelUsageSlotKey,
    model_action_digest,
    model_retry_terminal_digest,
    model_usage_cost,
)
from app.modules.model_usage.models import (
    ModelUsageEffect,
    SetupModelUsageEnvelope,
    SetupModelUsageSlot,
)
from app.modules.model_usage.profiles import stored_model_profile
from app.modules.model_usage.repository import (
    ModelCallRepository,
    require_model_call_transaction,
)
from app.modules.model_usage.service import (
    _PROVIDER_RESPONSE_ADAPTER,
    _evidence,
    _sha,
    _usage,
)


def _require_authority(action: str, facts: object, evidence: ModelActionEvidence) -> None:
    if evidence.facts_digest != model_action_digest(action, facts):
        raise ModelCallUnavailable("setup_model_authority_unavailable")


def _prepared(
    envelope: SetupModelUsageEnvelope,
    slot: SetupModelUsageSlot,
    effect: ModelUsageEffect,
    key: SetupModelUsageSlotKey,
    *,
    replayed: bool,
) -> PreparedSetupModelUsageEffect:
    return PreparedSetupModelUsageEffect(
        envelope_id=UUID(envelope.id),
        slot_id=UUID(slot.id),
        slot_key=key,
        effect_id=UUID(effect.id),
        attempt_number=effect.attempt_number,
        internal_call_request_id=UUID(effect.internal_call_request_id),
        request_sha256=effect.request_sha256,
        replayed=replayed,
    )


def _slot_key(slot: SetupModelUsageSlot) -> SetupModelUsageSlotKey:
    return SetupModelUsageSlotKey(
        compilation_attempt_id=UUID(slot.compilation_attempt_id),
        project_id=UUID(slot.project_id),
        guide_id=UUID(slot.guide_id),
        source_snapshot_id=UUID(slot.source_snapshot_id),
        setup_run_id=UUID(slot.setup_run_id),
        setup_generation=slot.setup_generation,
        runtime_configuration_hash=slot.runtime_configuration_hash,
        profile_id=UUID(slot.profile_id),
        profile_version=slot.profile_version,
        profile_digest=slot.profile_digest,
        phase=slot.phase,
        call_index=slot.call_index,
    )


def _effect(slot: SetupModelUsageSlot, row: ModelUsageEffect) -> SetupModelEffectAuthorityFacts:
    key = _slot_key(slot)
    return SetupModelEffectAuthorityFacts(
        project_id=key.project_id,
        slot_id=UUID(slot.id),
        slot_key=key,
        effect_id=UUID(row.id),
        internal_call_request_id=UUID(row.internal_call_request_id),
    )


def _require_effect(
    supplied: SetupModelEffectAuthorityFacts,
    slot: SetupModelUsageSlot,
    row: ModelUsageEffect,
) -> None:
    if supplied != _effect(slot, row):
        raise ModelCallUnavailable("setup_model_effect_unavailable")


class SetupModelUsageService:
    """Allocate setup effects only after exact PROJECTS and AUTH custody."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authority: SetupModelUsageAuthorityPort,
        evidence: SetupModelUsageEvidencePort,
        owner: SetupModelUsageOwnerPort,
    ) -> None:
        self._session = session
        self._repo = ModelCallRepository(session)
        self._authority = authority
        self._evidence = evidence
        self._owner = owner

    async def _profile(
        self,
        key: SetupModelUsageSlotKey,
        owner_profile: SetupModelOwnerProfile | None = None,
    ):
        row = await self._repo.profile_exact(
            key.profile_id, key.profile_version, key.profile_digest
        )
        if row is None:
            raise ModelCallUnavailable("model_profile_unavailable")
        profile = stored_model_profile(row)
        if (
            profile.spec.project_id != key.project_id
            or (
                owner_profile is not None
                and (
                    profile.selector != owner_profile.selector
                    or (profile.spec.provider, profile.spec.api, profile.spec.model_snapshot)
                    != (
                        owner_profile.provider,
                        owner_profile.api,
                        owner_profile.model_snapshot,
                    )
                )
            )
        ):
            raise ModelCallUnavailable("model_profile_unavailable")
        return profile

    async def prepare(
        self, key: SetupModelUsageSlotKey, request_sha256: str
    ) -> PreparedSetupModelUsageEffect:
        """Allocate one durable setup call identity before request persistence."""
        require_model_call_transaction(self._session)
        key = SetupModelUsageSlotKey.model_validate(key)
        facts = {"slot": key.model_dump(mode="json"), "request_sha256": request_sha256}
        authority = await self._authority.authorize_setup_prepare(key, request_sha256)
        _require_authority("setup_prepare", facts, authority)
        owner_profile = await self._owner.require_setup_current(key)
        profile = await self._profile(key, owner_profile)
        if key.call_index >= profile.spec.maximum_calls:
            raise ModelCallConflict("setup_model_call_index_conflict")

        await self._repo.lock_setup_envelope_scope(key)
        envelope = await self._repo.setup_envelope(key, lock=True)
        if envelope is None:
            values = key.model_dump(mode="json", exclude={"phase", "call_index"})
            envelope = SetupModelUsageEnvelope(id=str(new_record_id()), **values)
            await self._repo.add(envelope)
        await self._repo.lock_setup_slot_scope(key)
        slot = await self._repo.setup_slot(key, lock=True)
        if slot is None:
            slot = SetupModelUsageSlot(
                id=str(new_record_id()),
                envelope_id=envelope.id,
                request_sha256=request_sha256,
                **key.model_dump(mode="json"),
            )
            await self._repo.add(slot)
        elif slot.request_sha256 != request_sha256 or slot.envelope_id != envelope.id:
            raise ModelCallConflict("setup_model_request_conflict")
        effect = await self._repo.latest_setup_effect(slot.id, lock=True)
        if effect is not None:
            return _prepared(envelope, slot, effect, key, replayed=True)
        effect = ModelUsageEffect(
            id=str(new_record_id()),
            setup_slot_id=slot.id,
            attempt_number=1,
            internal_call_request_id=str(new_record_id()),
            request_sha256=request_sha256,
            state="prepared",
            prepared_authorization_evidence_id=str(authority.evidence_id),
        )
        await self._repo.add(effect)
        return _prepared(envelope, slot, effect, key, replayed=False)

    async def reserve_dispatch(
        self,
        prepared: PreparedSetupModelUsageEffect,
        request_evidence: ModelCallEvidence,
    ) -> SetupModelDispatchReservation:
        """Reserve one actual setup provider dispatch under run and project caps."""
        require_model_call_transaction(self._session)
        prepared = PreparedSetupModelUsageEffect.model_validate(prepared)
        request_evidence = ModelCallEvidence.model_validate(request_evidence)
        facts = {
            "prepared": prepared.model_dump(mode="json"),
            "request_evidence": request_evidence.model_dump(mode="json"),
        }
        authority = await self._authority.authorize_setup_dispatch(prepared, request_evidence)
        _require_authority("setup_dispatch", facts, authority)
        key = prepared.slot_key
        owner_profile = await self._owner.require_setup_current(key)
        await self._evidence.require_setup_request(prepared, request_evidence)
        profile = await self._profile(key, owner_profile)
        if (
            request_evidence.content_sha256 != prepared.request_sha256
            or request_evidence.byte_count > profile.spec.maximum_request_bytes
        ):
            raise ModelCallConflict("setup_model_request_evidence_conflict")

        await self._repo.lock_setup_envelope_scope(key)
        envelope = await self._repo.setup_envelope(key, lock=True)
        if envelope is None or envelope.id != str(prepared.envelope_id):
            raise ModelCallUnavailable("setup_model_envelope_unavailable")
        await self._repo.lock_setup_slot_scope(key)
        slot = await self._repo.setup_slot(key, lock=True)
        if slot is None or slot.id != str(prepared.slot_id):
            raise ModelCallUnavailable("setup_model_effect_unavailable")
        effect = await self._repo.attempt(prepared.effect_id, lock=True)
        if effect is None or effect.setup_slot_id != slot.id:
            raise ModelCallUnavailable("setup_model_effect_unavailable")
        if effect.state != "prepared":
            if effect.request_content_sha256 != request_evidence.content_sha256:
                raise ModelCallConflict("setup_model_dispatch_conflict")
            if effect.state != "dispatching":
                raise ModelCallConflict("setup_model_effect_not_dispatchable")
            return self._dispatch_result(envelope, slot, effect, key, request_evidence, True)

        totals = await self._repo.setup_envelope_totals(envelope.id)
        reservation = profile.spec.maximum_dispatch_reservation_nanodollars
        if (
            totals.dispatches >= profile.spec.maximum_calls
            or totals.reserved_nanodollars + totals.settled_nanodollars + reservation
            > profile.spec.maximum_reservation_nanodollars
            or totals.request_bytes + request_evidence.byte_count
            > profile.spec.maximum_total_request_bytes
            or totals.response_bytes
            + (totals.pending_dispatches + 1) * profile.spec.maximum_response_bytes
            > profile.spec.maximum_total_response_bytes
            or totals.input_tokens
            + (totals.pending_dispatches + 1) * profile.spec.maximum_input_tokens
            > profile.spec.maximum_total_input_tokens
            or totals.output_tokens
            + (totals.pending_dispatches + 1) * profile.spec.maximum_output_tokens
            > profile.spec.maximum_total_output_tokens
        ):
            raise ModelCallBudgetUnavailable("model_run_envelope_unavailable")
        await self._repo.lock_budget_scope(key.project_id)
        account = await self._repo.budget_account(key.project_id, lock=True)
        if account is None:
            raise ModelCallBudgetUnavailable("model_budget_unavailable")
        budget = await self._repo.current_budget_configuration(account)
        if budget is None or (
            account.lifetime_reserved_nanodollars
            + account.lifetime_settled_nanodollars
            + reservation
            > budget.lifetime_limit_nanodollars
        ):
            raise ModelCallBudgetUnavailable("model_budget_unavailable")

        for field, value in request_evidence.model_dump(
            mode="json", exclude={"media_type"}
        ).items():
            setattr(effect, f"request_{field}", value)
        effect.budget_configuration_id = budget.id
        effect.budget_configuration_version = budget.configuration_version
        effect.budget_configuration_digest = budget.configuration_digest
        effect.reserved_nanodollars = reservation
        effect.dispatch_authorization_evidence_id = str(authority.evidence_id)
        effect.dispatched_at = await self._repo.now()
        effect.state = "dispatching"
        account.lifetime_reserved_nanodollars += reservation
        await self._repo.flush()
        return self._dispatch_result(envelope, slot, effect, key, request_evidence, False)

    @staticmethod
    def _dispatch_result(
        envelope: SetupModelUsageEnvelope,
        slot: SetupModelUsageSlot,
        effect: ModelUsageEffect,
        key: SetupModelUsageSlotKey,
        evidence: ModelCallEvidence,
        replayed: bool,
    ) -> SetupModelDispatchReservation:
        return SetupModelDispatchReservation(
            envelope_id=UUID(envelope.id),
            slot_id=UUID(slot.id),
            slot_key=key,
            effect_id=UUID(effect.id),
            attempt_number=effect.attempt_number,
            internal_call_request_id=UUID(effect.internal_call_request_id),
            effect=_effect(slot, effect),
            request_sha256=effect.request_sha256,
            request_evidence=evidence,
            budget_configuration_id=UUID(effect.budget_configuration_id),
            budget_configuration_version=effect.budget_configuration_version,
            budget_configuration_digest=effect.budget_configuration_digest,
            reserved_nanodollars=effect.reserved_nanodollars,
            replayed=replayed,
        )

    async def mark_uncertain(
        self,
        supplied: SetupModelEffectAuthorityFacts,
        uncertainty_digest: str,
        *,
        provider_response_id: str | None = None,
    ) -> ObservedSetupModelUsageEffect:
        """Retain an ambiguous setup provider effect without releasing its reservation."""
        require_model_call_transaction(self._session)
        supplied = SetupModelEffectAuthorityFacts.model_validate(supplied)
        uncertainty_digest = _sha(uncertainty_digest)
        if provider_response_id is not None:
            provider_response_id = _PROVIDER_RESPONSE_ADAPTER.validate_python(
                provider_response_id, strict=True
            )
        authority = await self._authority.authorize_setup_observe(
            supplied, provider_response_id, uncertainty_digest
        )
        facts = {
            "effect": supplied.model_dump(mode="json"),
            "provider_response_id": provider_response_id,
            "observation_digest": uncertainty_digest,
        }
        _require_authority("setup_observe", facts, authority)
        row, slot, _ = await self._terminal_preflight(supplied.effect_id)
        row = await self._lock_terminal(slot, supplied.effect_id)
        _require_effect(supplied, slot, row)
        if row.state == "uncertain":
            if (
                row.uncertainty_digest != uncertainty_digest
                or row.provider_response_id != provider_response_id
            ):
                raise ModelCallConflict("setup_model_uncertainty_conflict")
            replayed = True
        else:
            if row.state != "dispatching":
                raise ModelCallConflict("setup_model_uncertainty_conflict")
            row.state = "uncertain"
            row.uncertainty_digest = uncertainty_digest
            row.provider_response_id = provider_response_id
            row.observation_authorization_evidence_id = str(authority.evidence_id)
            await self._repo.flush()
            replayed = False
        return ObservedSetupModelUsageEffect(
            effect=_effect(slot, row),
            uncertainty_digest=row.uncertainty_digest,
            provider_response_id=row.provider_response_id,
            replayed=replayed,
        )

    async def complete(
        self,
        supplied: SetupModelEffectAuthorityFacts,
        *,
        provider_response_id: str,
        provider_model_snapshot: str,
        response_evidence: ModelCallEvidence,
        usage: ModelCallUsage,
    ) -> CompletedSetupModelUsageEffect:
        """Settle one verified setup response under narrow retained-effect authority."""
        require_model_call_transaction(self._session)
        supplied = SetupModelEffectAuthorityFacts.model_validate(supplied)
        provider_response_id = _PROVIDER_RESPONSE_ADAPTER.validate_python(
            provider_response_id, strict=True
        )
        response_evidence = ModelCallEvidence.model_validate(response_evidence)
        usage = ModelCallUsage.model_validate(usage)
        terminal_digest = canonical_json_hash(
            {
                "status": "completed",
                "provider_response_id": provider_response_id,
                "provider_model_snapshot": provider_model_snapshot,
                "response_evidence": response_evidence.model_dump(mode="json"),
                "usage": usage.model_dump(mode="json"),
            }
        )
        authority = await self._authority.authorize_setup_complete(
            supplied, response_evidence, terminal_digest
        )
        _require_authority(
            "setup_complete",
            {
                "effect": supplied.model_dump(mode="json"),
                "response_evidence": response_evidence.model_dump(mode="json"),
                "terminal_digest": terminal_digest,
            },
            authority,
        )
        await self._evidence.require_setup_response(supplied.effect_id, response_evidence)
        row, slot, profile = await self._terminal_preflight(supplied.effect_id)
        if (
            provider_model_snapshot != profile.spec.model_snapshot
            or response_evidence.byte_count > profile.spec.maximum_response_bytes
        ):
            raise ModelCallConflict("setup_model_response_conflict")
        cost = model_usage_cost(profile.spec, usage)
        row = await self._lock_terminal(slot, supplied.effect_id)
        _require_effect(supplied, slot, row)
        if row.state == "completed":
            if (
                row.provider_response_id != provider_response_id
                or _evidence(row, "response") != response_evidence
                or _usage(row) != usage
                or row.settled_nanodollars != cost
            ):
                raise ModelCallConflict("setup_model_terminal_conflict")
            return self._completed(row, slot, replayed=True)
        self._require_pending(row)
        if row.provider_response_id not in {None, provider_response_id}:
            raise ModelCallConflict("setup_model_provider_response_conflict")
        await self._settle(row, slot, cost)
        self._set_evidence(row, "response", response_evidence)
        self._set_usage(row, usage)
        row.provider_response_id = provider_response_id
        row.settled_nanodollars = cost
        row.terminal_authorization_evidence_id = str(authority.evidence_id)
        row.terminal_at = await self._repo.now()
        row.state = "completed"
        await self._repo.flush()
        return self._completed(row, slot, replayed=False)

    async def mark_known_no_effect(
        self,
        supplied: SetupModelEffectAuthorityFacts,
        proof: KnownNoEffectProof,
    ) -> KnownNoEffectSetupModelUsageEffect:
        """Release only an authenticated setup dispatch proven to have no effect."""
        require_model_call_transaction(self._session)
        supplied = SetupModelEffectAuthorityFacts.model_validate(supplied)
        proof = KnownNoEffectProof.model_validate(proof)
        terminal_digest = model_retry_terminal_digest(proof)
        authority = await self._authority.authorize_setup_complete(supplied, None, terminal_digest)
        _require_authority(
            "setup_complete",
            {
                "effect": supplied.model_dump(mode="json"),
                "response_evidence": None,
                "terminal_digest": terminal_digest,
            },
            authority,
        )
        _, slot, _ = await self._terminal_preflight(supplied.effect_id)
        row = await self._lock_terminal(slot, supplied.effect_id)
        _require_effect(supplied, slot, row)
        if row.state == "known_no_effect":
            if (
                row.no_effect_proof_id != str(proof.proof_id)
                or row.no_effect_proof_digest != proof.proof_digest
                or row.no_effect_observed_at != proof.observed_at
            ):
                raise ModelCallConflict("setup_model_terminal_conflict")
            replayed = True
        else:
            self._require_pending(row)
            if row.provider_response_id is not None:
                raise ModelCallConflict("setup_model_no_effect_conflict")
            await self._release(row, slot)
            row.no_effect_proof_id = str(proof.proof_id)
            row.no_effect_proof_digest = proof.proof_digest
            row.no_effect_observed_at = proof.observed_at
            row.terminal_authorization_evidence_id = str(authority.evidence_id)
            row.terminal_at = await self._repo.now()
            row.state = "known_no_effect"
            await self._repo.flush()
            replayed = False
        return KnownNoEffectSetupModelUsageEffect(
            effect=_effect(slot, row), proof=proof, replayed=replayed
        )

    async def _terminal_preflight(self, effect_id: UUID):
        row = await self._repo.attempt(effect_id)
        if row is None or row.setup_slot_id is None:
            raise ModelCallUnavailable("setup_model_effect_unavailable")
        slot = await self._session.get(SetupModelUsageSlot, row.setup_slot_id)
        if slot is None:
            raise ModelCallUnavailable("setup_model_effect_unavailable")
        return row, slot, await self._profile(_slot_key(slot))

    async def _lock_terminal(self, slot: SetupModelUsageSlot, effect_id: UUID) -> ModelUsageEffect:
        key = _slot_key(slot)
        await self._repo.lock_setup_envelope_scope(key)
        if await self._repo.setup_envelope(key, lock=True) is None:
            raise ModelCallUnavailable("setup_model_envelope_unavailable")
        await self._repo.lock_setup_slot_scope(key)
        locked_slot = await self._repo.setup_slot(key, lock=True)
        if locked_slot is None or locked_slot.id != slot.id:
            raise ModelCallUnavailable("setup_model_effect_unavailable")
        row = await self._repo.attempt(effect_id, lock=True)
        if row is None or row.setup_slot_id != slot.id:
            raise ModelCallUnavailable("setup_model_effect_unavailable")
        return row

    @staticmethod
    def _require_pending(row: ModelUsageEffect) -> None:
        if row.state not in {"dispatching", "uncertain"}:
            raise ModelCallConflict("setup_model_terminal_conflict")
        if row.reserved_nanodollars is None:
            raise ModelCallUnavailable("model_budget_unavailable")

    async def _settle(self, row: ModelUsageEffect, slot: SetupModelUsageSlot, cost: int) -> None:
        await self._repo.lock_budget_scope(UUID(slot.project_id))
        account = await self._repo.budget_account(UUID(slot.project_id), lock=True)
        if account is None or row.reserved_nanodollars is None:
            raise ModelCallUnavailable("model_budget_unavailable")
        if account.lifetime_reserved_nanodollars < row.reserved_nanodollars:
            raise ModelCallUnavailable("model_budget_conservation_failed")
        account.lifetime_reserved_nanodollars -= row.reserved_nanodollars
        account.lifetime_settled_nanodollars += cost

    async def _release(self, row: ModelUsageEffect, slot: SetupModelUsageSlot) -> None:
        await self._repo.lock_budget_scope(UUID(slot.project_id))
        account = await self._repo.budget_account(UUID(slot.project_id), lock=True)
        if account is None or row.reserved_nanodollars is None:
            raise ModelCallUnavailable("model_budget_unavailable")
        if account.lifetime_reserved_nanodollars < row.reserved_nanodollars:
            raise ModelCallUnavailable("model_budget_conservation_failed")
        account.lifetime_reserved_nanodollars -= row.reserved_nanodollars

    @staticmethod
    def _set_evidence(row: ModelUsageEffect, prefix: str, evidence: ModelCallEvidence) -> None:
        for field, value in evidence.model_dump(mode="json", exclude={"media_type"}).items():
            setattr(row, f"{prefix}_{field}", value)

    @staticmethod
    def _set_usage(row: ModelUsageEffect, usage: ModelCallUsage) -> None:
        row.input_tokens = usage.input_tokens
        row.cached_input_tokens = usage.cached_input_tokens
        row.output_tokens = usage.output_tokens
        row.reasoning_tokens = usage.reasoning_tokens

    @staticmethod
    def _completed(
        row: ModelUsageEffect,
        slot: SetupModelUsageSlot,
        *,
        replayed: bool,
    ) -> CompletedSetupModelUsageEffect:
        usage = _usage(row)
        if usage is None or row.terminal_at is None or row.settled_nanodollars is None:
            raise ModelCallUnavailable("setup_model_completion_unavailable")
        return CompletedSetupModelUsageEffect(
            effect=_effect(slot, row),
            provider_response_id=row.provider_response_id,
            request_evidence=_evidence(row, "request"),
            response_evidence=_evidence(row, "response"),
            usage=usage,
            settled_nanodollars=row.settled_nanodollars,
            completed_at=row.terminal_at,
            replayed=replayed,
        )


__all__ = ("SetupModelUsageService",)
