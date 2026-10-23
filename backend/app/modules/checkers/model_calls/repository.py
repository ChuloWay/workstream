"""Flush-only persistence and lock order for project model-call ownership."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.model_calls import ModelPaidSlotKey, ModelCallUnavailable
from app.modules.checkers.model_calls.models import (
    CheckerModelBudgetAccount,
    CheckerModelBudgetConfiguration,
    CheckerModelCallAttempt,
    CheckerModelCallRecovery,
    CheckerModelCallSlot,
    CheckerModelProfile,
)


def require_model_call_transaction(session: AsyncSession) -> None:
    """Require one caller-owned root transaction and reject nested ownership."""
    transaction = session.sync_session.get_transaction()
    if transaction is None or not transaction.is_active or session.in_nested_transaction():
        raise ModelCallUnavailable("model_call_transaction_unavailable")


class ModelCallRepository:
    """Own model-call row locks without committing the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def now(self):
        return await self._session.scalar(select(func.clock_timestamp()))

    async def advisory(self, key: str) -> None:
        await self._session.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": key},
        )

    async def lock_profile_scopes(
        self, operation_id: UUID, project_id: UUID, profile_version: int
    ) -> None:
        for key in (
            f"checker-model-profile-operation:{operation_id}",
            f"checker-model-profile:{project_id}",
        ):
            await self.advisory(key)

    async def profile_by_operation(self, operation_id: UUID):
        return await self._session.scalar(
            select(CheckerModelProfile).where(CheckerModelProfile.operation_id == str(operation_id))
        )

    async def profile_by_version(self, project_id: UUID, profile_version: int):
        return await self._session.scalar(
            select(CheckerModelProfile).where(
                CheckerModelProfile.project_id == str(project_id),
                CheckerModelProfile.profile_version == profile_version,
            )
        )

    async def latest_profile(self, project_id: UUID):
        return await self._session.scalar(
            select(CheckerModelProfile)
            .where(CheckerModelProfile.project_id == str(project_id))
            .order_by(CheckerModelProfile.profile_version.desc())
            .limit(1)
        )

    async def profile_exact(self, profile_id: UUID, profile_version: int, profile_digest: str):
        return await self._session.scalar(
            select(CheckerModelProfile).where(
                CheckerModelProfile.id == str(profile_id),
                CheckerModelProfile.profile_version == profile_version,
                CheckerModelProfile.profile_digest == profile_digest,
            )
        )

    async def lock_budget_scope(self, project_id: UUID) -> None:
        await self.advisory(f"checker-model-budget:{project_id}")

    async def budget_account(self, project_id: UUID, *, lock: bool = False):
        query = select(CheckerModelBudgetAccount).where(
            CheckerModelBudgetAccount.project_id == str(project_id)
        )
        if lock:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def budget_configuration_by_operation(self, operation_id: UUID):
        return await self._session.scalar(
            select(CheckerModelBudgetConfiguration).where(
                CheckerModelBudgetConfiguration.operation_id == str(operation_id)
            )
        )

    async def budget_configuration_by_version(self, project_id: UUID, version: int):
        return await self._session.scalar(
            select(CheckerModelBudgetConfiguration).where(
                CheckerModelBudgetConfiguration.project_id == str(project_id),
                CheckerModelBudgetConfiguration.configuration_version == version,
            )
        )

    async def current_budget_configuration(self, account: CheckerModelBudgetAccount):
        return await self._session.get(
            CheckerModelBudgetConfiguration,
            account.current_configuration_id,
            populate_existing=True,
        )

    @staticmethod
    def _slot_predicates(key: ModelPaidSlotKey):
        return (
            CheckerModelCallSlot.project_id == str(key.project_id),
            CheckerModelCallSlot.assignment_id == str(key.assignment_id),
            CheckerModelCallSlot.submission_id == str(key.submission_id),
            CheckerModelCallSlot.submission_version == key.submission_version,
            CheckerModelCallSlot.requirement_id == key.requirement_id,
            CheckerModelCallSlot.registry_entry_digest == key.registry_entry_digest,
            CheckerModelCallSlot.configuration_sha256 == key.configuration_sha256,
            CheckerModelCallSlot.profile_id == str(key.profile_id),
            CheckerModelCallSlot.profile_version == key.profile_version,
            CheckerModelCallSlot.profile_digest == key.profile_digest,
            CheckerModelCallSlot.slot_index == key.slot_index,
        )

    async def lock_slot_scope(self, key: ModelPaidSlotKey) -> None:
        await self.advisory("checker-model-call-slot:" + key.digest)

    async def slot(self, key: ModelPaidSlotKey, *, lock: bool = False):
        query = select(CheckerModelCallSlot).where(*self._slot_predicates(key))
        if lock:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def latest_attempt(self, slot_id: str, *, lock: bool = False):
        query = (
            select(CheckerModelCallAttempt)
            .where(CheckerModelCallAttempt.slot_id == slot_id)
            .order_by(CheckerModelCallAttempt.attempt_number.desc())
            .limit(1)
        )
        if lock:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def attempt(self, attempt_id: UUID, *, lock: bool = False):
        query = select(CheckerModelCallAttempt).where(CheckerModelCallAttempt.id == str(attempt_id))
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
        return await self._session.scalar(
            select(CheckerModelCallRecovery).where(
                CheckerModelCallRecovery.attempt_id == str(attempt_id),
                CheckerModelCallRecovery.checker_run_id == str(checker_run_id),
                CheckerModelCallRecovery.worker_lease_id == str(worker_lease_id),
                CheckerModelCallRecovery.worker_lease_generation == worker_lease_generation,
            )
        )

    async def add(self, row) -> None:
        self._session.add(row)
        await self._session.flush()

    async def flush(self) -> None:
        await self._session.flush()


__all__ = ("ModelCallRepository", "require_model_call_transaction")
