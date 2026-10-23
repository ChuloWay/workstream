"""Transactional owner for durable, project-budgeted checker model calls."""

from __future__ import annotations

from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.checkers.api.model_calls import (
    AttachedModelCallAttempt,
    CompletedModelCall,
    KnownFailedModelCall,
    KnownNoEffectProof,
    ModelActionEvidence,
    ModelBudgetProvisioningFacts,
    ModelCallAuthorityPort,
    ModelCallBudgetUnavailable,
    ModelCallConflict,
    ModelCallCurrentExecutionPort,
    ModelCallEvidence,
    ModelCallEffectAuthorityFacts,
    ModelCallEvidencePort,
    ModelCallExecutionFacts,
    ModelCallRecoveryAttachment,
    ModelCallUnavailable,
    ModelCallUsage,
    ModelDispatchReservation,
    ModelPaidSlotKey,
    ModelProfileProvisioningFacts,
    ModelProfileSelector,
    PreparedModelCallAttempt,
    ProviderResponseIdentifier,
    ProjectModelBudgetConfiguration,
    ProjectModelProfile,
    model_action_digest,
    model_retry_terminal_digest,
    model_usage_cost,
)
from app.modules.checkers.model_calls.models import (
    CheckerModelBudgetAccount,
    CheckerModelBudgetConfiguration,
    CheckerModelCallAttempt,
    CheckerModelCallRecovery,
    CheckerModelCallSlot,
    CheckerModelProfile,
)
from app.modules.checkers.model_calls.repository import (
    ModelCallRepository,
    require_model_call_transaction,
)
from app.modules.checkers.model_calls.profiles import stored_model_profile


def _uuid(value: str) -> UUID:
    return UUID(value)


def _same_uuid(value: str, expected: UUID) -> bool:
    return value == str(expected)


_SHA_ADAPTER = TypeAdapter(str)
_PROVIDER_RESPONSE_ADAPTER = TypeAdapter(ProviderResponseIdentifier)


def _sha(value: str) -> str:
    # Pydantic constrained aliases are validated by their containing public values;
    # raw service arguments receive the equivalent closed check here.
    if len(value) != 71 or not value.startswith("sha256:"):
        raise ModelCallConflict("model_call_digest_invalid")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ModelCallConflict("model_call_digest_invalid") from exc
    if value[7:] != value[7:].lower():
        raise ModelCallConflict("model_call_digest_invalid")
    return _SHA_ADAPTER.validate_python(value, strict=True)


def _require_authority(action: str, facts: object, evidence: ModelActionEvidence) -> None:
    if evidence.facts_digest != model_action_digest(action, facts):
        raise ModelCallUnavailable("model_call_authority_unavailable")


def _slot_key(row: CheckerModelCallSlot) -> ModelPaidSlotKey:
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


def _evidence(row: CheckerModelCallAttempt, prefix: str) -> ModelCallEvidence:
    values = {
        "binding_id": getattr(row, f"{prefix}_binding_id"),
        "content_id": getattr(row, f"{prefix}_content_id"),
        "put_attempt_id": getattr(row, f"{prefix}_put_attempt_id"),
        "verification_receipt_id": getattr(row, f"{prefix}_verification_receipt_id"),
        "content_sha256": getattr(row, f"{prefix}_content_sha256"),
        "byte_count": getattr(row, f"{prefix}_byte_count"),
    }
    if any(value is None for value in values.values()):
        raise ModelCallUnavailable("model_call_evidence_unavailable")
    for field in (
        "binding_id",
        "content_id",
        "put_attempt_id",
        "verification_receipt_id",
    ):
        values[field] = _uuid(values[field])
    return ModelCallEvidence.model_validate(values)


def _attempt(
    slot: CheckerModelCallSlot,
    row: CheckerModelCallAttempt,
    *,
    replayed: bool,
) -> AttachedModelCallAttempt:
    values = dict(
        slot_id=_uuid(slot.id),
        slot_key=_slot_key(slot),
        attempt_id=_uuid(row.id),
        attempt_number=row.attempt_number,
        internal_call_request_id=_uuid(row.internal_call_request_id),
        request_sha256=row.request_sha256,
        state=row.state,
        replayed=replayed,
    )
    if row.state == "prepared":
        return PreparedModelCallAttempt.model_validate(values)
    return AttachedModelCallAttempt.model_validate(values)


def _effect(
    slot: CheckerModelCallSlot, row: CheckerModelCallAttempt
) -> ModelCallEffectAuthorityFacts:
    return ModelCallEffectAuthorityFacts(
        project_id=_uuid(slot.project_id),
        task_id=_uuid(slot.task_id),
        slot_id=_uuid(slot.id),
        slot_key=_slot_key(slot),
        attempt_id=_uuid(row.id),
        internal_call_request_id=_uuid(row.internal_call_request_id),
    )


def _require_effect(
    supplied: ModelCallEffectAuthorityFacts,
    slot: CheckerModelCallSlot,
    row: CheckerModelCallAttempt,
) -> None:
    if supplied != _effect(slot, row):
        raise ModelCallUnavailable("model_call_effect_unavailable")


def _usage(row: CheckerModelCallAttempt) -> ModelCallUsage | None:
    values = (
        row.input_tokens,
        row.cached_input_tokens,
        row.output_tokens,
        row.reasoning_tokens,
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ModelCallUnavailable("model_call_usage_unavailable")
    return ModelCallUsage(
        input_tokens=row.input_tokens,
        cached_input_tokens=row.cached_input_tokens,
        output_tokens=row.output_tokens,
        reasoning_tokens=row.reasoning_tokens,
    )


class ModelCallService:
    """Flush-only state machine; the caller owns commit or rollback."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authority: ModelCallAuthorityPort,
        current_execution: ModelCallCurrentExecutionPort,
        evidence: ModelCallEvidencePort,
    ) -> None:
        self._session = session
        self._repo = ModelCallRepository(session)
        self._authority = authority
        self._current = current_execution
        self._evidence = evidence

    def _require_transaction(self) -> None:
        require_model_call_transaction(self._session)

    async def provision_profile(self, facts: ModelProfileProvisioningFacts) -> ProjectModelProfile:
        """Publish one immutable Operator-authorized exact model profile."""
        self._require_transaction()
        facts = ModelProfileProvisioningFacts.model_validate(facts)
        _ = facts.spec.maximum_reservation_nanodollars
        authority = await self._authority.authorize_profile(facts)
        _require_authority("profile", facts, authority)

        await self._repo.lock_profile_scopes(
            facts.operation_id, facts.spec.project_id, facts.spec.profile_version
        )
        by_operation = await self._repo.profile_by_operation(facts.operation_id)
        if by_operation is not None:
            existing = stored_model_profile(by_operation)
            stored_facts = ModelProfileProvisioningFacts(
                operation_id=existing.operation_id,
                actor_profile_id=existing.actor_profile_id,
                spec=existing.spec,
                profile_digest=existing.profile_digest,
            )
            if stored_facts != facts:
                raise ModelCallConflict("model_profile_operation_conflict")
            return existing
        if (
            await self._repo.profile_by_version(facts.spec.project_id, facts.spec.profile_version)
            is not None
        ):
            raise ModelCallConflict("model_profile_version_conflict")
        latest = await self._repo.latest_profile(facts.spec.project_id)
        expected_version = 1 if latest is None else latest.profile_version + 1
        if facts.spec.profile_version != expected_version:
            raise ModelCallConflict("model_profile_version_conflict")

        spec = facts.spec
        pricing = spec.pricing
        row = CheckerModelProfile(
            id=str(new_record_id()),
            project_id=str(spec.project_id),
            profile_version=spec.profile_version,
            profile_digest=facts.profile_digest,
            registry_entry_id=str(spec.registry_entry_id),
            registry_entry_digest=spec.registry_entry_digest,
            provider=spec.provider,
            api=spec.api,
            model_snapshot=spec.model_snapshot,
            generation_settings=spec.settings.model_dump(mode="json"),
            maximum_request_bytes=spec.maximum_request_bytes,
            maximum_output_bytes=spec.maximum_output_bytes,
            maximum_response_bytes=spec.maximum_response_bytes,
            maximum_input_tokens=spec.maximum_input_tokens,
            maximum_output_tokens=spec.maximum_output_tokens,
            deadline_ms=spec.deadline_ms,
            call_slots=spec.call_slots,
            pricing_policy_id=str(pricing.pricing_policy_id),
            pricing_policy_version=pricing.pricing_policy_version,
            pricing_policy_digest=pricing.pricing_policy_digest,
            uncached_input_rate=pricing.uncached_input_nanodollars_per_token,
            cached_input_rate=pricing.cached_input_nanodollars_per_token,
            output_rate=pricing.output_nanodollars_per_token,
            operation_id=str(facts.operation_id),
            actor_profile_id=str(facts.actor_profile_id),
            authorization_evidence_id=str(authority.evidence_id),
        )
        await self._repo.add(row)
        return stored_model_profile(row)

    async def provision_budget(
        self, facts: ModelBudgetProvisioningFacts
    ) -> ProjectModelBudgetConfiguration:
        """Advance a ceiling version without resetting project lifetime counters."""
        self._require_transaction()
        facts = ModelBudgetProvisioningFacts.model_validate(facts)
        authority = await self._authority.authorize_budget(facts)
        _require_authority("budget", facts, authority)
        spec = facts.spec

        await self._repo.lock_budget_scope(spec.project_id)
        by_operation = await self._repo.budget_configuration_by_operation(facts.operation_id)
        if by_operation is not None:
            account = await self._repo.budget_account(spec.project_id, lock=True)
            if account is None:
                raise ModelCallUnavailable("model_budget_account_unavailable")
            result = self._budget_result(by_operation, account)
            stored_facts = ModelBudgetProvisioningFacts(
                operation_id=result.operation_id,
                actor_profile_id=result.actor_profile_id,
                spec=result.spec,
                configuration_digest=result.configuration_digest,
            )
            if stored_facts != facts:
                raise ModelCallConflict("model_budget_operation_conflict")
            return result

        account = await self._repo.budget_account(spec.project_id, lock=True)
        current = (
            await self._repo.current_budget_configuration(account) if account is not None else None
        )
        expected_version = 1 if current is None else current.configuration_version + 1
        if spec.configuration_version != expected_version:
            raise ModelCallConflict("model_budget_version_conflict")
        if (
            await self._repo.budget_configuration_by_version(
                spec.project_id, spec.configuration_version
            )
            is not None
        ):
            raise ModelCallConflict("model_budget_version_conflict")
        reserved = 0 if account is None else account.lifetime_reserved_nanodollars
        settled = 0 if account is None else account.lifetime_settled_nanodollars
        if spec.lifetime_limit_nanodollars < reserved + settled:
            raise ModelCallBudgetUnavailable("model_budget_below_lifetime_usage")

        row = CheckerModelBudgetConfiguration(
            id=str(new_record_id()),
            project_id=str(spec.project_id),
            configuration_version=spec.configuration_version,
            configuration_digest=facts.configuration_digest,
            lifetime_limit_nanodollars=spec.lifetime_limit_nanodollars,
            operation_id=str(facts.operation_id),
            actor_profile_id=str(facts.actor_profile_id),
            authorization_evidence_id=str(authority.evidence_id),
        )
        await self._repo.add(row)
        if account is None:
            account = CheckerModelBudgetAccount(
                project_id=str(spec.project_id),
                current_configuration_id=row.id,
                lifetime_reserved_nanodollars=0,
                lifetime_settled_nanodollars=0,
            )
            await self._repo.add(account)
        else:
            account.current_configuration_id = row.id
            await self._repo.flush()
        return self._budget_result(row, account)

    @staticmethod
    def _budget_result(
        row: CheckerModelBudgetConfiguration, account: CheckerModelBudgetAccount
    ) -> ProjectModelBudgetConfiguration:
        return ProjectModelBudgetConfiguration(
            configuration_id=_uuid(row.id),
            operation_id=_uuid(row.operation_id),
            actor_profile_id=_uuid(row.actor_profile_id),
            spec={
                "project_id": _uuid(row.project_id),
                "configuration_version": row.configuration_version,
                "lifetime_limit_nanodollars": row.lifetime_limit_nanodollars,
            },
            configuration_digest=row.configuration_digest,
            authorization_evidence_id=_uuid(row.authorization_evidence_id),
            created_at=row.created_at,
            lifetime_reserved_nanodollars=account.lifetime_reserved_nanodollars,
            lifetime_settled_nanodollars=account.lifetime_settled_nanodollars,
        )

    async def read_exact(
        self,
        selector: ModelProfileSelector,
        *,
        project_id: UUID,
        registry_entry_id: UUID,
        registry_entry_digest: str,
    ) -> ProjectModelProfile:
        """Read an exact profile without treating a partial selector as authority."""
        self._require_transaction()
        selector = ModelProfileSelector.model_validate(selector)
        row = await self._repo.profile_exact(
            selector.profile_id, selector.profile_version, selector.profile_digest
        )
        if row is None:
            raise ModelCallUnavailable("model_profile_unavailable")
        result = stored_model_profile(row)
        if (
            result.spec.project_id != project_id
            or result.spec.registry_entry_id != registry_entry_id
            or result.spec.registry_entry_digest != registry_entry_digest
        ):
            raise ModelCallUnavailable("model_profile_unavailable")
        return result

    @staticmethod
    def _require_execution_slot(execution: ModelCallExecutionFacts, slot: ModelPaidSlotKey) -> None:
        if (
            execution.project_id != slot.project_id
            or execution.assignment_id != slot.assignment_id
            or execution.submission_id != slot.submission_id
            or execution.submission_version != slot.submission_version
        ):
            raise ModelCallUnavailable("model_call_execution_unavailable")

    async def _profile_for_slot(
        self, slot: ModelPaidSlotKey, registry_entry_id: UUID
    ) -> ProjectModelProfile:
        return await self.read_exact(
            ModelProfileSelector(
                profile_id=slot.profile_id,
                profile_version=slot.profile_version,
                profile_digest=slot.profile_digest,
            ),
            project_id=slot.project_id,
            registry_entry_id=registry_entry_id,
            registry_entry_digest=slot.registry_entry_digest,
        )

    async def _profile_for_stored_slot(self, slot: ModelPaidSlotKey) -> ProjectModelProfile:
        row = await self._repo.profile_exact(
            slot.profile_id, slot.profile_version, slot.profile_digest
        )
        if row is None:
            raise ModelCallUnavailable("model_profile_unavailable")
        result = stored_model_profile(row)
        if (
            result.spec.project_id != slot.project_id
            or result.spec.registry_entry_digest != slot.registry_entry_digest
        ):
            raise ModelCallUnavailable("model_profile_unavailable")
        return result

    async def prepare_attempt(
        self,
        execution: ModelCallExecutionFacts,
        slot: ModelPaidSlotKey,
        *,
        registry_entry_id: UUID,
        request_sha256: str,
    ) -> AttachedModelCallAttempt:
        """Allocate a server-owned attempt before private request ART upload."""
        self._require_transaction()
        execution = ModelCallExecutionFacts.model_validate(execution)
        slot = ModelPaidSlotKey.model_validate(slot)
        request_sha256 = _sha(request_sha256)
        self._require_execution_slot(execution, slot)
        authority = await self._authority.authorize_prepare(execution, slot, request_sha256)
        _require_authority(
            "prepare",
            {
                "execution": execution.model_dump(mode="json"),
                "slot": slot.model_dump(mode="json"),
                "request_sha256": request_sha256,
            },
            authority,
        )
        await self._current.require_current(execution, slot)
        await self._profile_for_slot(slot, registry_entry_id)

        await self._repo.lock_slot_scope(slot)
        slot_row = await self._repo.slot(slot, lock=True)
        if slot_row is None:
            slot_row = CheckerModelCallSlot(
                id=str(new_record_id()),
                task_id=str(execution.task_id),
                **slot.model_dump(mode="json"),
                first_request_sha256=request_sha256,
            )
            await self._repo.add(slot_row)
        elif slot_row.first_request_sha256 != request_sha256 or slot_row.task_id != str(
            execution.task_id
        ):
            raise ModelCallConflict("model_call_request_conflict")
        attempt = await self._repo.latest_attempt(slot_row.id, lock=True)
        if attempt is not None:
            return _attempt(slot_row, attempt, replayed=True)

        attempt = CheckerModelCallAttempt(
            id=str(new_record_id()),
            slot_id=slot_row.id,
            attempt_number=1,
            internal_call_request_id=str(new_record_id()),
            request_sha256=request_sha256,
            state="prepared",
            prepared_authorization_evidence_id=str(authority.evidence_id),
        )
        await self._repo.add(attempt)
        return _attempt(slot_row, attempt, replayed=False)

    async def prepare_recovery_child(
        self,
        execution: ModelCallExecutionFacts,
        slot: ModelPaidSlotKey,
        *,
        registry_entry_id: UUID,
        parent_attempt_id: UUID,
        terminal_digest: str,
        request_sha256: str,
    ) -> PreparedModelCallAttempt:
        """Allocate N+1 only after an authorized, fully-known terminal parent."""
        self._require_transaction()
        execution = ModelCallExecutionFacts.model_validate(execution)
        slot = ModelPaidSlotKey.model_validate(slot)
        terminal_digest = _sha(terminal_digest)
        request_sha256 = _sha(request_sha256)
        self._require_execution_slot(execution, slot)
        authority = await self._authority.authorize_child(
            execution, parent_attempt_id, terminal_digest
        )
        child_facts = {
            "execution": execution.model_dump(mode="json"),
            "parent_attempt_id": str(parent_attempt_id),
            "terminal_digest": terminal_digest,
        }
        _require_authority("child", child_facts, authority)
        await self._current.require_current(execution, slot)
        await self._profile_for_slot(slot, registry_entry_id)

        await self._repo.lock_slot_scope(slot)
        slot_row = await self._repo.slot(slot, lock=True)
        if slot_row is None:
            raise ModelCallUnavailable("model_call_parent_unavailable")
        if slot_row.first_request_sha256 != request_sha256:
            raise ModelCallConflict("model_call_request_conflict")
        latest = await self._repo.latest_attempt(slot_row.id, lock=True)
        if latest is None:
            raise ModelCallUnavailable("model_call_parent_unavailable")
        if latest.id != str(parent_attempt_id):
            if (
                latest.attempt_number > 1
                and latest.state == "prepared"
                and latest.parent_attempt_id == str(parent_attempt_id)
                and latest.request_sha256 == request_sha256
            ):
                return PreparedModelCallAttempt.model_validate(
                    _attempt(slot_row, latest, replayed=True)
                )
            raise ModelCallConflict("model_call_parent_superseded")
        if not self._eligible_parent(latest, terminal_digest):
            raise ModelCallConflict("model_call_parent_not_retryable")

        child = CheckerModelCallAttempt(
            id=str(new_record_id()),
            slot_id=slot_row.id,
            attempt_number=latest.attempt_number + 1,
            internal_call_request_id=str(new_record_id()),
            parent_attempt_id=str(parent_attempt_id),
            request_sha256=request_sha256,
            state="prepared",
            prepared_authorization_evidence_id=str(authority.evidence_id),
        )
        await self._repo.add(child)
        return PreparedModelCallAttempt.model_validate(_attempt(slot_row, child, replayed=False))

    @staticmethod
    def _eligible_parent(row: CheckerModelCallAttempt, terminal_digest: str) -> bool:
        if row.state == "known_no_effect":
            actual = canonical_json_hash(
                {
                    "state": row.state,
                    "proof_id": row.no_effect_proof_id,
                    "proof_digest": row.no_effect_proof_digest,
                    "observed_at": (
                        row.no_effect_observed_at.isoformat()
                        if row.no_effect_observed_at is not None
                        else None
                    ),
                }
            )
            return row.reserved_nanodollars is not None and actual == terminal_digest
        if row.state == "known_failed":
            result = ModelCallService._failed_result(row, replayed=False)
            return (
                row.settlement_authorization_evidence_id is not None
                and row.settled_at is not None
                and model_retry_terminal_digest(result) == terminal_digest
            )
        return False

    async def reserve_dispatch(
        self,
        execution: ModelCallExecutionFacts,
        attempt: PreparedModelCallAttempt,
        request_evidence: ModelCallEvidence,
    ) -> ModelDispatchReservation:
        """Verify ART, then atomically persist intent and reserve lifetime spend."""
        self._require_transaction()
        execution = ModelCallExecutionFacts.model_validate(execution)
        attempt = PreparedModelCallAttempt.model_validate(attempt)
        request_evidence = ModelCallEvidence.model_validate(request_evidence)
        self._require_execution_slot(execution, attempt.slot_key)
        authority = await self._authority.authorize_dispatch(execution, attempt, request_evidence)
        dispatch_facts = {
            "execution": execution.model_dump(mode="json"),
            "attempt": attempt.model_dump(mode="json"),
            "request_evidence": request_evidence.model_dump(mode="json"),
        }
        _require_authority("dispatch", dispatch_facts, authority)
        await self._current.require_current(execution, attempt.slot_key)
        await self._evidence.require_request(attempt, request_evidence)
        profile = await self._profile_for_stored_slot(attempt.slot_key)
        if (
            request_evidence.content_sha256 != attempt.request_sha256
            or request_evidence.byte_count > profile.spec.maximum_request_bytes
        ):
            raise ModelCallConflict("model_call_request_evidence_conflict")

        await self._repo.lock_slot_scope(attempt.slot_key)
        slot_row = await self._repo.slot(attempt.slot_key, lock=True)
        if slot_row is None or slot_row.id != str(attempt.slot_id):
            raise ModelCallUnavailable("model_call_attempt_unavailable")
        row = await self._repo.attempt(attempt.attempt_id, lock=True)
        if row is None or row.slot_id != slot_row.id:
            raise ModelCallUnavailable("model_call_attempt_unavailable")
        if row.state != "prepared":
            if _evidence(row, "request") != request_evidence:
                raise ModelCallConflict("model_call_dispatch_conflict")
            return self._dispatch_result(row, slot=slot_row, replayed=True)
        if (
            row.request_sha256 != attempt.request_sha256
            or row.attempt_number != attempt.attempt_number
            or row.internal_call_request_id != str(attempt.internal_call_request_id)
        ):
            raise ModelCallConflict("model_call_attempt_conflict")

        await self._repo.lock_budget_scope(attempt.slot_key.project_id)
        account = await self._repo.budget_account(attempt.slot_key.project_id, lock=True)
        if account is None:
            raise ModelCallBudgetUnavailable("model_budget_unavailable")
        budget = await self._repo.current_budget_configuration(account)
        if budget is None:
            raise ModelCallBudgetUnavailable("model_budget_unavailable")
        reservation = profile.spec.maximum_reservation_nanodollars
        if (
            account.lifetime_reserved_nanodollars
            + account.lifetime_settled_nanodollars
            + reservation
            > budget.lifetime_limit_nanodollars
        ):
            raise ModelCallBudgetUnavailable("model_budget_exhausted")

        account.lifetime_reserved_nanodollars += reservation
        self._set_evidence(row, "request", request_evidence)
        row.budget_configuration_id = budget.id
        row.budget_configuration_version = budget.configuration_version
        row.budget_configuration_digest = budget.configuration_digest
        row.reserved_nanodollars = reservation
        row.dispatch_authorization_evidence_id = str(authority.evidence_id)
        row.dispatched_at = await self._repo.now()
        row.state = "dispatching"
        await self._repo.flush()
        return self._dispatch_result(row, slot=slot_row, replayed=False)

    @staticmethod
    def _set_evidence(
        row: CheckerModelCallAttempt, prefix: str, evidence: ModelCallEvidence
    ) -> None:
        for field, value in evidence.model_dump(mode="json", exclude={"media_type"}).items():
            setattr(row, f"{prefix}_{field}", value)

    @staticmethod
    def _dispatch_result(
        row: CheckerModelCallAttempt,
        *,
        slot: CheckerModelCallSlot | None = None,
        replayed: bool,
    ) -> ModelDispatchReservation:
        if row.state not in {"dispatching", "uncertain", "completed"}:
            raise ModelCallConflict("model_call_not_dispatchable")
        if slot is None:
            raise ModelCallUnavailable("model_call_effect_unavailable")
        return ModelDispatchReservation(
            slot_id=_uuid(row.slot_id),
            attempt_id=_uuid(row.id),
            attempt_number=row.attempt_number,
            internal_call_request_id=_uuid(row.internal_call_request_id),
            effect=_effect(slot, row),
            request_sha256=row.request_sha256,
            request_evidence=_evidence(row, "request"),
            budget_configuration_id=_uuid(row.budget_configuration_id),
            budget_configuration_version=row.budget_configuration_version,
            budget_configuration_digest=row.budget_configuration_digest,
            reserved_nanodollars=row.reserved_nanodollars,
            state=row.state,
            provider_response_id=row.provider_response_id,
            response_evidence=(
                _evidence(row, "response") if row.response_content_sha256 is not None else None
            ),
            replayed=replayed,
        )

    async def attach_recovery(
        self,
        execution: ModelCallExecutionFacts,
        effect: ModelCallEffectAuthorityFacts,
    ) -> ModelCallRecoveryAttachment:
        """Attach a fresh run to an existing effect; this never creates a call."""
        self._require_transaction()
        execution = ModelCallExecutionFacts.model_validate(execution)
        effect = ModelCallEffectAuthorityFacts.model_validate(effect)
        self._require_execution_slot(execution, effect.slot_key)
        if execution.task_id != effect.task_id:
            raise ModelCallUnavailable("model_call_execution_unavailable")
        authority = await self._authority.authorize_recover(execution, effect)
        facts = {
            "execution": execution.model_dump(mode="json"),
            "effect": effect.model_dump(mode="json"),
        }
        _require_authority("recover", facts, authority)
        await self._current.require_current(execution, effect.slot_key)
        row = await self._repo.attempt(effect.attempt_id)
        if row is None:
            raise ModelCallUnavailable("model_call_attempt_unavailable")
        slot = await self._session.get(CheckerModelCallSlot, row.slot_id)
        if slot is None:
            raise ModelCallUnavailable("model_call_attempt_unavailable")
        self._require_execution_slot(execution, _slot_key(slot))
        await self._repo.lock_slot_scope(_slot_key(slot))
        row = await self._repo.attempt(effect.attempt_id, lock=True)
        if row is not None:
            _require_effect(effect, slot, row)
        recoverable = (
            row is not None
            and row.provider_response_id is not None
            and row.state in {"dispatching", "uncertain"}
        )
        if not recoverable:
            raise ModelCallUnavailable("model_call_recovery_unavailable")
        existing = await self._repo.recovery(
            effect.attempt_id,
            execution.checker_run_id,
            execution.worker_lease_id,
            execution.worker_lease_generation,
        )
        if existing is None:
            await self._repo.add(
                CheckerModelCallRecovery(
                    id=str(new_record_id()),
                    attempt_id=str(effect.attempt_id),
                    checker_run_id=str(execution.checker_run_id),
                    worker_lease_id=str(execution.worker_lease_id),
                    worker_lease_generation=execution.worker_lease_generation,
                    authorization_evidence_id=str(authority.evidence_id),
                )
            )
        return ModelCallRecoveryAttachment(
            slot_id=_uuid(slot.id),
            attempt_id=_uuid(row.id),
            attempt_number=row.attempt_number,
            internal_call_request_id=_uuid(row.internal_call_request_id),
            provider_response_id=row.provider_response_id,
            state=row.state,
            replayed=existing is not None,
        )

    async def attach_completed(
        self,
        execution: ModelCallExecutionFacts,
        effect: ModelCallEffectAuthorityFacts,
    ) -> CompletedModelCall:
        """Attach a fresh current run to immutable cached response evidence."""
        self._require_transaction()
        execution = ModelCallExecutionFacts.model_validate(execution)
        effect = ModelCallEffectAuthorityFacts.model_validate(effect)
        self._require_execution_slot(execution, effect.slot_key)
        if execution.task_id != effect.task_id:
            raise ModelCallUnavailable("model_call_execution_unavailable")
        authority = await self._authority.authorize_recover(execution, effect)
        facts = {
            "execution": execution.model_dump(mode="json"),
            "effect": effect.model_dump(mode="json"),
        }
        _require_authority("recover", facts, authority)
        await self._current.require_current(execution, effect.slot_key)
        row = await self._repo.attempt(effect.attempt_id)
        if row is None:
            raise ModelCallUnavailable("model_call_attempt_unavailable")
        slot = await self._session.get(CheckerModelCallSlot, row.slot_id)
        if slot is None:
            raise ModelCallUnavailable("model_call_attempt_unavailable")
        self._require_execution_slot(execution, _slot_key(slot))
        await self._repo.lock_slot_scope(_slot_key(slot))
        row = await self._repo.attempt(effect.attempt_id, lock=True)
        if row is None or row.state != "completed":
            raise ModelCallUnavailable("model_call_completion_unavailable")
        _require_effect(effect, slot, row)
        existing = await self._repo.recovery(
            effect.attempt_id,
            execution.checker_run_id,
            execution.worker_lease_id,
            execution.worker_lease_generation,
        )
        if existing is None:
            await self._repo.add(
                CheckerModelCallRecovery(
                    id=str(new_record_id()),
                    attempt_id=str(effect.attempt_id),
                    checker_run_id=str(execution.checker_run_id),
                    worker_lease_id=str(execution.worker_lease_id),
                    worker_lease_generation=execution.worker_lease_generation,
                    authorization_evidence_id=str(authority.evidence_id),
                )
            )
        return self._completed_result(row, replayed=existing is not None)

    async def mark_uncertain(
        self,
        effect: ModelCallEffectAuthorityFacts,
        uncertainty_digest: str,
        *,
        provider_response_id: str | None = None,
    ) -> ModelDispatchReservation:
        """Conserve the full reservation after an ambiguous dispatched effect."""
        self._require_transaction()
        effect = ModelCallEffectAuthorityFacts.model_validate(effect)
        uncertainty_digest = _sha(uncertainty_digest)
        if provider_response_id is not None:
            provider_response_id = _PROVIDER_RESPONSE_ADAPTER.validate_python(
                provider_response_id, strict=True
            )
        authority = await self._authority.authorize_observe(
            effect, provider_response_id, uncertainty_digest
        )
        observation_facts = {
            "effect": effect.model_dump(mode="json"),
            "provider_response_id": provider_response_id,
            "observation_digest": uncertainty_digest,
        }
        _require_authority("observe", observation_facts, authority)
        _, slot, _ = await self._terminal_preflight(effect.attempt_id)
        row = await self._lock_terminal(slot, effect.attempt_id)
        _require_effect(effect, slot, row)
        if row.state == "uncertain":
            if (
                row.uncertainty_digest != uncertainty_digest
                or row.provider_response_id != provider_response_id
            ):
                raise ModelCallConflict("model_call_uncertainty_conflict")
            return self._dispatch_result(row, slot=slot, replayed=True)
        if row.state != "dispatching":
            raise ModelCallConflict("model_call_uncertainty_conflict")
        row.state = "uncertain"
        row.uncertainty_digest = uncertainty_digest
        row.provider_response_id = provider_response_id
        row.observation_authorization_evidence_id = str(authority.evidence_id)
        await self._repo.flush()
        return self._dispatch_result(row, slot=slot, replayed=False)

    async def complete(
        self,
        effect: ModelCallEffectAuthorityFacts,
        *,
        provider_response_id: str,
        provider_model_snapshot: str,
        response_evidence: ModelCallEvidence,
        usage: ModelCallUsage,
    ) -> CompletedModelCall:
        """Store verified usable response evidence and settle cost exactly once."""
        effect = ModelCallEffectAuthorityFacts.model_validate(effect)
        attempt_id = effect.attempt_id
        provider_response_id = _PROVIDER_RESPONSE_ADAPTER.validate_python(
            provider_response_id, strict=True
        )
        response_evidence = ModelCallEvidence.model_validate(response_evidence)
        usage = ModelCallUsage.model_validate(usage)
        terminal = {
            "status": "completed",
            "provider_response_id": provider_response_id,
            "provider_model_snapshot": provider_model_snapshot,
            "response_evidence": response_evidence.model_dump(mode="json"),
            "usage": usage.model_dump(mode="json"),
        }
        terminal_digest = canonical_json_hash(terminal)
        authority = await self._authority.authorize_complete(
            effect, response_evidence, terminal_digest
        )
        _require_authority(
            "complete",
            {
                "effect": effect.model_dump(mode="json"),
                "response_evidence": response_evidence.model_dump(mode="json"),
                "terminal_digest": terminal_digest,
            },
            authority,
        )
        await self._evidence.require_response(attempt_id, response_evidence)
        row, slot, profile = await self._terminal_preflight(attempt_id)
        if (
            provider_model_snapshot != profile.spec.model_snapshot
            or response_evidence.byte_count > profile.spec.maximum_response_bytes
        ):
            raise ModelCallConflict("model_call_response_conflict")
        cost = model_usage_cost(profile.spec, usage)
        row = await self._lock_terminal(slot, attempt_id)
        _require_effect(effect, slot, row)
        if row.state == "completed":
            if (
                row.provider_response_id != provider_response_id
                or _evidence(row, "response") != response_evidence
                or _usage(row) != usage
                or row.settled_nanodollars != cost
            ):
                raise ModelCallConflict("model_call_terminal_conflict")
            return self._completed_result(row, replayed=True)
        self._require_effect_pending(row)
        if (
            row.provider_response_id is not None
            and row.provider_response_id != provider_response_id
        ):
            raise ModelCallConflict("model_call_provider_response_conflict")
        await self._settle(row, slot, cost)
        self._set_evidence(row, "response", response_evidence)
        self._set_usage(row, usage)
        row.provider_response_id = provider_response_id
        row.settled_nanodollars = cost
        row.terminal_authorization_evidence_id = str(authority.evidence_id)
        row.terminal_at = await self._repo.now()
        row.state = "completed"
        await self._repo.flush()
        return self._completed_result(row, replayed=False)

    async def complete_known_failure(
        self,
        effect: ModelCallEffectAuthorityFacts,
        *,
        provider_response_id: str,
        provider_model_snapshot: str,
        response_evidence: ModelCallEvidence,
        usage: ModelCallUsage,
    ) -> KnownFailedModelCall:
        """Record and settle a terminal failed effect with complete authenticated usage."""
        effect = ModelCallEffectAuthorityFacts.model_validate(effect)
        attempt_id = effect.attempt_id
        provider_response_id = _PROVIDER_RESPONSE_ADAPTER.validate_python(
            provider_response_id, strict=True
        )
        response_evidence = ModelCallEvidence.model_validate(response_evidence)
        usage = ModelCallUsage.model_validate(usage)
        terminal = {
            "status": "known_failed",
            "provider_response_id": provider_response_id,
            "provider_model_snapshot": provider_model_snapshot,
            "response_evidence": response_evidence.model_dump(mode="json"),
            "usage": usage.model_dump(mode="json"),
        }
        terminal_digest = canonical_json_hash(terminal)
        authority = await self._authority.authorize_complete(
            effect, response_evidence, terminal_digest
        )
        _require_authority(
            "complete",
            {
                "effect": effect.model_dump(mode="json"),
                "response_evidence": response_evidence.model_dump(mode="json"),
                "terminal_digest": terminal_digest,
            },
            authority,
        )
        await self._evidence.require_response(attempt_id, response_evidence)
        row, slot, profile = await self._terminal_preflight(attempt_id)
        if (
            provider_model_snapshot != profile.spec.model_snapshot
            or response_evidence.byte_count > profile.spec.maximum_response_bytes
        ):
            raise ModelCallConflict("model_call_response_conflict")
        cost = model_usage_cost(profile.spec, usage)
        row = await self._lock_terminal(slot, attempt_id)
        _require_effect(effect, slot, row)
        if row.state == "known_failed":
            stored_usage = _usage(row)
            same_response = (
                row.provider_response_id == provider_response_id
                and _evidence(row, "response") == response_evidence
            )
            if not same_response or stored_usage != usage or row.settled_nanodollars != cost:
                raise ModelCallConflict("model_call_terminal_conflict")
            return self._failed_result(row, replayed=True)
        self._require_effect_pending(row)
        if (
            row.provider_response_id is not None
            and row.provider_response_id != provider_response_id
        ):
            raise ModelCallConflict("model_call_provider_response_conflict")
        await self._settle(row, slot, cost)
        self._set_usage(row, usage)
        row.settled_nanodollars = cost
        row.settlement_authorization_evidence_id = str(authority.evidence_id)
        row.settled_at = await self._repo.now()
        self._set_evidence(row, "response", response_evidence)
        row.provider_response_id = provider_response_id
        row.terminal_authorization_evidence_id = str(authority.evidence_id)
        row.terminal_at = await self._repo.now()
        row.state = "known_failed"
        await self._repo.flush()
        return self._failed_result(row, replayed=False)

    async def mark_known_no_effect(
        self, effect: ModelCallEffectAuthorityFacts, proof: KnownNoEffectProof
    ) -> AttachedModelCallAttempt:
        """Release reservation only for authenticated proof that create had no effect."""
        effect = ModelCallEffectAuthorityFacts.model_validate(effect)
        attempt_id = effect.attempt_id
        proof = KnownNoEffectProof.model_validate(proof)
        terminal_digest = model_retry_terminal_digest(proof)
        authority = await self._authority.authorize_complete(effect, None, terminal_digest)
        _require_authority(
            "complete",
            {
                "effect": effect.model_dump(mode="json"),
                "response_evidence": None,
                "terminal_digest": terminal_digest,
            },
            authority,
        )
        _, slot, _ = await self._terminal_preflight(attempt_id)
        row = await self._lock_terminal(slot, attempt_id)
        _require_effect(effect, slot, row)
        if row.state == "known_no_effect":
            if (
                row.no_effect_proof_id != str(proof.proof_id)
                or row.no_effect_proof_digest != proof.proof_digest
                or row.no_effect_observed_at != proof.observed_at
            ):
                raise ModelCallConflict("model_call_terminal_conflict")
            return _attempt(slot, row, replayed=True)
        self._require_effect_pending(row)
        if row.provider_response_id is not None:
            raise ModelCallConflict("model_call_no_effect_conflict")
        await self._release(row, slot)
        row.no_effect_proof_id = str(proof.proof_id)
        row.no_effect_proof_digest = proof.proof_digest
        row.no_effect_observed_at = proof.observed_at
        row.terminal_authorization_evidence_id = str(authority.evidence_id)
        row.terminal_at = await self._repo.now()
        row.state = "known_no_effect"
        await self._repo.flush()
        return _attempt(slot, row, replayed=False)

    async def _terminal_preflight(
        self, attempt_id: UUID
    ) -> tuple[CheckerModelCallAttempt, CheckerModelCallSlot, ProjectModelProfile]:
        self._require_transaction()
        row = await self._repo.attempt(attempt_id)
        if row is None:
            raise ModelCallUnavailable("model_call_attempt_unavailable")
        slot = await self._session.get(CheckerModelCallSlot, row.slot_id)
        if slot is None:
            raise ModelCallUnavailable("model_call_attempt_unavailable")
        profile_row = await self._repo.profile_exact(
            _uuid(slot.profile_id), slot.profile_version, slot.profile_digest
        )
        if profile_row is None:
            raise ModelCallUnavailable("model_profile_unavailable")
        return row, slot, stored_model_profile(profile_row)

    async def _lock_terminal(
        self, slot: CheckerModelCallSlot, attempt_id: UUID
    ) -> CheckerModelCallAttempt:
        await self._repo.lock_slot_scope(_slot_key(slot))
        row = await self._repo.attempt(attempt_id, lock=True)
        if row is None or row.slot_id != slot.id:
            raise ModelCallUnavailable("model_call_attempt_unavailable")
        return row

    @staticmethod
    def _require_effect_pending(row: CheckerModelCallAttempt) -> None:
        if row.state not in {"dispatching", "uncertain"}:
            raise ModelCallConflict("model_call_terminal_conflict")
        if row.reserved_nanodollars is None:
            raise ModelCallUnavailable("model_call_reservation_unavailable")

    async def _settle(
        self,
        row: CheckerModelCallAttempt,
        slot: CheckerModelCallSlot,
        cost: int,
    ) -> None:
        await self._repo.lock_budget_scope(_uuid(slot.project_id))
        account = await self._repo.budget_account(_uuid(slot.project_id), lock=True)
        if account is None or row.reserved_nanodollars is None:
            raise ModelCallUnavailable("model_budget_unavailable")
        if account.lifetime_reserved_nanodollars < row.reserved_nanodollars:
            raise ModelCallUnavailable("model_budget_conservation_failed")
        account.lifetime_reserved_nanodollars -= row.reserved_nanodollars
        account.lifetime_settled_nanodollars += cost

    async def _release(self, row: CheckerModelCallAttempt, slot: CheckerModelCallSlot) -> None:
        await self._repo.lock_budget_scope(_uuid(slot.project_id))
        account = await self._repo.budget_account(_uuid(slot.project_id), lock=True)
        if account is None or row.reserved_nanodollars is None:
            raise ModelCallUnavailable("model_budget_unavailable")
        if account.lifetime_reserved_nanodollars < row.reserved_nanodollars:
            raise ModelCallUnavailable("model_budget_conservation_failed")
        account.lifetime_reserved_nanodollars -= row.reserved_nanodollars

    @staticmethod
    def _set_usage(row: CheckerModelCallAttempt, usage: ModelCallUsage) -> None:
        row.input_tokens = usage.input_tokens
        row.cached_input_tokens = usage.cached_input_tokens
        row.output_tokens = usage.output_tokens
        row.reasoning_tokens = usage.reasoning_tokens

    @staticmethod
    def _completed_result(row: CheckerModelCallAttempt, *, replayed: bool) -> CompletedModelCall:
        usage = _usage(row)
        if usage is None or row.terminal_at is None or row.settled_nanodollars is None:
            raise ModelCallUnavailable("model_call_completion_unavailable")
        return CompletedModelCall(
            slot_id=_uuid(row.slot_id),
            attempt_id=_uuid(row.id),
            attempt_number=row.attempt_number,
            internal_call_request_id=_uuid(row.internal_call_request_id),
            provider_response_id=row.provider_response_id,
            request_evidence=_evidence(row, "request"),
            response_evidence=_evidence(row, "response"),
            usage=usage,
            settled_nanodollars=row.settled_nanodollars,
            completed_at=row.terminal_at,
            replayed=replayed,
        )

    @staticmethod
    def _failed_result(row: CheckerModelCallAttempt, *, replayed: bool) -> KnownFailedModelCall:
        usage = _usage(row)
        if row.terminal_at is None or usage is None or row.settled_nanodollars is None:
            raise ModelCallUnavailable("model_call_completion_unavailable")
        return KnownFailedModelCall(
            slot_id=_uuid(row.slot_id),
            attempt_id=_uuid(row.id),
            attempt_number=row.attempt_number,
            internal_call_request_id=_uuid(row.internal_call_request_id),
            provider_response_id=row.provider_response_id,
            request_evidence=_evidence(row, "request"),
            response_evidence=_evidence(row, "response"),
            usage=usage,
            settled_nanodollars=row.settled_nanodollars,
            completed_at=row.terminal_at,
            replayed=replayed,
        )


__all__ = ("ModelCallService",)
