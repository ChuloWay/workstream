"""Flush-only persistence and lock order for project model-call ownership."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.model_usage.api import (
    ModelPaidSlotKey,
    ModelCallUnavailable,
    SetupModelUsageSlotKey,
)
from app.modules.model_usage.models import (
    ModelUsageBudgetAccount,
    ModelUsageBudgetConfiguration,
    ModelUsageEffect,
    CheckerModelUsageEnvelope,
    CheckerModelUsageRecovery,
    CheckerModelUsageSlot,
    SetupModelUsageEnvelope,
    SetupModelUsageSlot,
    ModelUsageProfile,
)


@dataclass(frozen=True)
class ModelUsageEnvelopeTotals:
    """Current committed effects beneath one locked whole-run envelope."""

    dispatches: int
    pending_dispatches: int
    reserved_nanodollars: int
    settled_nanodollars: int
    request_bytes: int
    response_bytes: int
    input_tokens: int
    output_tokens: int


def require_model_call_transaction(session: AsyncSession) -> None:
    """Require one caller-owned root transaction and reject nested ownership."""
    transaction = session.sync_session.get_transaction()
    if transaction is None or not transaction.is_active or session.in_nested_transaction():
        raise ModelCallUnavailable("model_call_transaction_unavailable")


class ModelCallRepository:
    """Own model-call row locks without committing the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind all reads, writes, and locks to the caller-owned session."""
        self._session = session

    async def now(self):
        """Read the authoritative database clock inside the current transaction."""
        return await self._session.scalar(select(func.clock_timestamp()))

    async def advisory(self, key: str) -> None:
        """Take a transaction-scoped advisory lock for one canonical owner key."""
        await self._session.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": key},
        )

    async def lock_profile_scopes(
        self, operation_id: UUID, project_id: UUID, profile_version: int
    ) -> None:
        """Serialize profile idempotency and project version allocation in order."""
        for key in (
            f"checker-model-profile-operation:{operation_id}",
            f"checker-model-profile:{project_id}",
        ):
            await self.advisory(key)

    async def profile_by_operation(self, operation_id: UUID):
        """Return the immutable profile previously written for an operation."""
        return await self._session.scalar(
            select(ModelUsageProfile).where(ModelUsageProfile.operation_id == str(operation_id))
        )

    async def profile_by_version(self, project_id: UUID, profile_version: int):
        """Return the profile occupying one project-scoped version, if present."""
        return await self._session.scalar(
            select(ModelUsageProfile).where(
                ModelUsageProfile.project_id == str(project_id),
                ModelUsageProfile.profile_version == profile_version,
            )
        )

    async def latest_profile(self, project_id: UUID):
        """Return the highest immutable profile version currently stored for a project."""
        return await self._session.scalar(
            select(ModelUsageProfile)
            .where(ModelUsageProfile.project_id == str(project_id))
            .order_by(ModelUsageProfile.profile_version.desc())
            .limit(1)
        )

    async def profile_exact(self, profile_id: UUID, profile_version: int, profile_digest: str):
        """Resolve a profile only when its ID, version, and digest all match."""
        return await self._session.scalar(
            select(ModelUsageProfile).where(
                ModelUsageProfile.id == str(profile_id),
                ModelUsageProfile.profile_version == profile_version,
                ModelUsageProfile.profile_digest == profile_digest,
            )
        )

    async def lock_budget_scope(self, project_id: UUID) -> None:
        """Serialize lifetime budget mutations for one project."""
        await self.advisory(f"checker-model-budget:{project_id}")

    async def budget_account(self, project_id: UUID, *, lock: bool = False):
        """Load the project lifetime account, optionally taking its row lock."""
        query = select(ModelUsageBudgetAccount).where(
            ModelUsageBudgetAccount.project_id == str(project_id)
        )
        if lock:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def budget_configuration_by_operation(self, operation_id: UUID):
        """Return the immutable budget configuration written for an operation."""
        return await self._session.scalar(
            select(ModelUsageBudgetConfiguration).where(
                ModelUsageBudgetConfiguration.operation_id == str(operation_id)
            )
        )

    async def budget_configuration_by_version(self, project_id: UUID, version: int):
        """Return one exact project budget version, if it exists."""
        return await self._session.scalar(
            select(ModelUsageBudgetConfiguration).where(
                ModelUsageBudgetConfiguration.project_id == str(project_id),
                ModelUsageBudgetConfiguration.configuration_version == version,
            )
        )

    async def current_budget_configuration(self, account: ModelUsageBudgetAccount):
        """Refresh the configuration selected by the locked lifetime account."""
        return await self._session.get(
            ModelUsageBudgetConfiguration,
            account.current_configuration_id,
            populate_existing=True,
        )

    @staticmethod
    def _envelope_predicates(key: ModelPaidSlotKey):
        """Build the complete stable whole-run identity predicate."""
        return (
            CheckerModelUsageEnvelope.project_id == str(key.project_id),
            CheckerModelUsageEnvelope.assignment_id == str(key.assignment_id),
            CheckerModelUsageEnvelope.submission_id == str(key.submission_id),
            CheckerModelUsageEnvelope.submission_version == key.submission_version,
            CheckerModelUsageEnvelope.requirement_id == key.requirement_id,
            CheckerModelUsageEnvelope.registry_entry_digest == key.registry_entry_digest,
            CheckerModelUsageEnvelope.configuration_sha256 == key.configuration_sha256,
            CheckerModelUsageEnvelope.profile_id == str(key.profile_id),
            CheckerModelUsageEnvelope.profile_version == key.profile_version,
            CheckerModelUsageEnvelope.profile_digest == key.profile_digest,
        )

    async def lock_envelope_scope(self, key: ModelPaidSlotKey) -> None:
        """Serialize all slots and effects under one stable checker run envelope."""
        await self.advisory("checker-model-usage-envelope:" + key.envelope_digest)

    async def envelope(self, key: ModelPaidSlotKey, *, lock: bool = False):
        """Load one exact checker whole-run envelope."""
        query = select(CheckerModelUsageEnvelope).where(*self._envelope_predicates(key))
        if lock:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    @staticmethod
    def _slot_predicates(key: ModelPaidSlotKey):
        """Build the complete paid-slot identity predicate without partial matching."""
        return (
            CheckerModelUsageSlot.project_id == str(key.project_id),
            CheckerModelUsageSlot.assignment_id == str(key.assignment_id),
            CheckerModelUsageSlot.submission_id == str(key.submission_id),
            CheckerModelUsageSlot.submission_version == key.submission_version,
            CheckerModelUsageSlot.requirement_id == key.requirement_id,
            CheckerModelUsageSlot.registry_entry_digest == key.registry_entry_digest,
            CheckerModelUsageSlot.configuration_sha256 == key.configuration_sha256,
            CheckerModelUsageSlot.profile_id == str(key.profile_id),
            CheckerModelUsageSlot.profile_version == key.profile_version,
            CheckerModelUsageSlot.profile_digest == key.profile_digest,
            CheckerModelUsageSlot.slot_index == key.slot_index,
        )

    async def lock_slot_scope(self, key: ModelPaidSlotKey) -> None:
        """Serialize creation and state transitions for one exact paid slot."""
        await self.advisory("checker-model-call-slot:" + key.digest)

    async def slot(self, key: ModelPaidSlotKey, *, lock: bool = False):
        """Load an exact paid slot and optionally lock it for mutation."""
        query = select(CheckerModelUsageSlot).where(*self._slot_predicates(key))
        if lock:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def latest_attempt(self, slot_id: str, *, lock: bool = False):
        """Load the greatest attempt number for a slot, optionally for update."""
        query = (
            select(ModelUsageEffect)
            .where(ModelUsageEffect.checker_slot_id == slot_id)
            .order_by(ModelUsageEffect.attempt_number.desc())
            .limit(1)
        )
        if lock:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def envelope_totals(self, envelope_id: str) -> ModelUsageEnvelopeTotals:
        """Aggregate all effect-bearing checker attempts under a locked envelope."""
        row = (
            await self._session.execute(
                select(
                    func.count(ModelUsageEffect.id).filter(ModelUsageEffect.state != "prepared"),
                    func.count(ModelUsageEffect.id).filter(
                        ModelUsageEffect.state.in_(("dispatching", "uncertain"))
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    ModelUsageEffect.state.in_(("dispatching", "uncertain")),
                                    ModelUsageEffect.reserved_nanodollars,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(func.sum(ModelUsageEffect.settled_nanodollars), 0),
                    func.coalesce(func.sum(ModelUsageEffect.request_byte_count), 0),
                    func.coalesce(func.sum(ModelUsageEffect.response_byte_count), 0),
                    func.coalesce(func.sum(ModelUsageEffect.input_tokens), 0),
                    func.coalesce(func.sum(ModelUsageEffect.output_tokens), 0),
                )
                .join(
                    CheckerModelUsageSlot,
                    CheckerModelUsageSlot.id == ModelUsageEffect.checker_slot_id,
                )
                .where(CheckerModelUsageSlot.envelope_id == envelope_id)
            )
        ).one()
        return ModelUsageEnvelopeTotals(*(int(value) for value in row))

    @staticmethod
    def _setup_envelope_predicates(key: SetupModelUsageSlotKey):
        return (
            SetupModelUsageEnvelope.compilation_attempt_id == key.compilation_attempt_id,
            SetupModelUsageEnvelope.project_id == str(key.project_id),
            SetupModelUsageEnvelope.guide_id == str(key.guide_id),
            SetupModelUsageEnvelope.source_snapshot_id == str(key.source_snapshot_id),
            SetupModelUsageEnvelope.setup_run_id == str(key.setup_run_id),
            SetupModelUsageEnvelope.setup_generation == key.setup_generation,
            SetupModelUsageEnvelope.runtime_configuration_hash == key.runtime_configuration_hash,
            SetupModelUsageEnvelope.profile_id == str(key.profile_id),
            SetupModelUsageEnvelope.profile_version == key.profile_version,
            SetupModelUsageEnvelope.profile_digest == key.profile_digest,
        )

    async def lock_setup_envelope_scope(self, key: SetupModelUsageSlotKey) -> None:
        """Serialize all phases and calls under one exact setup attempt envelope."""
        await self.advisory("setup-model-usage-envelope:" + key.envelope_digest)

    async def setup_envelope(self, key: SetupModelUsageSlotKey, *, lock: bool = False):
        query = select(SetupModelUsageEnvelope).where(*self._setup_envelope_predicates(key))
        if lock:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    @staticmethod
    def _setup_slot_predicates(key: SetupModelUsageSlotKey):
        return (
            SetupModelUsageSlot.compilation_attempt_id == key.compilation_attempt_id,
            SetupModelUsageSlot.runtime_configuration_hash == key.runtime_configuration_hash,
            SetupModelUsageSlot.profile_id == str(key.profile_id),
            SetupModelUsageSlot.profile_version == key.profile_version,
            SetupModelUsageSlot.profile_digest == key.profile_digest,
            SetupModelUsageSlot.phase == key.phase,
            SetupModelUsageSlot.call_index == key.call_index,
        )

    async def lock_setup_slot_scope(self, key: SetupModelUsageSlotKey) -> None:
        await self.advisory("setup-model-usage-slot:" + key.digest)

    async def setup_slot(self, key: SetupModelUsageSlotKey, *, lock: bool = False):
        query = select(SetupModelUsageSlot).where(*self._setup_slot_predicates(key))
        if lock:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def latest_setup_effect(self, slot_id: str, *, lock: bool = False):
        query = (
            select(ModelUsageEffect)
            .where(ModelUsageEffect.setup_slot_id == slot_id)
            .order_by(ModelUsageEffect.attempt_number.desc())
            .limit(1)
        )
        if lock:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def setup_envelope_totals(self, envelope_id: str) -> ModelUsageEnvelopeTotals:
        row = (
            await self._session.execute(
                select(
                    func.count(ModelUsageEffect.id).filter(ModelUsageEffect.state != "prepared"),
                    func.count(ModelUsageEffect.id).filter(
                        ModelUsageEffect.state.in_(("dispatching", "uncertain"))
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    ModelUsageEffect.state.in_(("dispatching", "uncertain")),
                                    ModelUsageEffect.reserved_nanodollars,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(func.sum(ModelUsageEffect.settled_nanodollars), 0),
                    func.coalesce(func.sum(ModelUsageEffect.request_byte_count), 0),
                    func.coalesce(func.sum(ModelUsageEffect.response_byte_count), 0),
                    func.coalesce(func.sum(ModelUsageEffect.input_tokens), 0),
                    func.coalesce(func.sum(ModelUsageEffect.output_tokens), 0),
                )
                .join(
                    SetupModelUsageSlot,
                    SetupModelUsageSlot.id == ModelUsageEffect.setup_slot_id,
                )
                .where(SetupModelUsageSlot.envelope_id == envelope_id)
            )
        ).one()
        return ModelUsageEnvelopeTotals(*(int(value) for value in row))

    async def attempt(self, attempt_id: UUID, *, lock: bool = False):
        """Load one server-owned attempt ID, optionally refreshing it under lock."""
        query = select(ModelUsageEffect).where(ModelUsageEffect.id == str(attempt_id))
        if lock:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def recovery(
        self,
        attempt_id: UUID,
        checker_run_id: UUID,
        worker_lease_id: UUID,
        worker_lease_generation: int,
    ):
        """Resolve an attachment by its complete attempt, run, and worker lease identity."""
        return await self._session.scalar(
            select(CheckerModelUsageRecovery).where(
                CheckerModelUsageRecovery.attempt_id == str(attempt_id),
                CheckerModelUsageRecovery.checker_run_id == str(checker_run_id),
                CheckerModelUsageRecovery.worker_lease_id == str(worker_lease_id),
                CheckerModelUsageRecovery.worker_lease_generation == worker_lease_generation,
            )
        )

    async def add(self, row) -> None:
        """Stage and flush a new owned row without committing the root transaction."""
        self._session.add(row)
        await self._session.flush()

    async def flush(self) -> None:
        """Flush pending state transitions while leaving commit to the caller."""
        await self._session.flush()


__all__ = (
    "ModelCallRepository",
    "ModelUsageEnvelopeTotals",
    "require_model_call_transaction",
)
