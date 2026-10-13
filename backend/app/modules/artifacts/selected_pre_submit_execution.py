"""Selected PRE lease execution across short authority and owner transactions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationRequest,
    PreparedBundleMaterializationService,
)
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitAuthorityPort,
    SelectedPreSubmitCompletion,
    SelectedPreSubmitCoordinationPort,
    SelectedPreSubmitExecutionFacts,
    SelectedPreSubmitFinalizeFacts,
    SelectedPreSubmitInfrastructureUnavailable,
    SelectedPreSubmitReservationFacts,
)


class SelectedPreSubmitExecutionService:
    """Claim, execute and finalize one selected run without holding a DB root."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        coordinator: SelectedPreSubmitCoordinationPort,
        authority: SelectedPreSubmitAuthorityPort,
        materialization: PreparedBundleMaterializationService,
    ) -> None:
        self._session = session
        self._coordinator = coordinator
        self._authority = authority
        self._materialization = materialization

    async def execute(
        self,
        *,
        reservation: SelectedPreSubmitReservationFacts,
        materialization: PreparedBundleMaterializationRequest,
    ) -> SelectedPreSubmitCompletion:
        """Use short claim/finalize roots around one process-local ART execution."""
        run_id = reservation.attempt_id
        async with self._session.begin():
            # Preparing the fixed principal precedes CHECKERS' TASK/run locks.
            async with self._authority.prepare_execution(reservation) as prepared:
                lease = await self._coordinator.claim(
                    run_id=run_id,
                    facts=reservation,
                    authority=prepared,
                )

        execution: SelectedPreSubmitExecutionFacts | None = None
        infrastructure_failure_code: str | None = None
        try:
            capability = await self._coordinator.committed_execution(
                run_id=run_id, lease=lease
            )
            execution = await self._materialization.materialize_selected_pre_submit(
                materialization,
                run_id=run_id,
                lease=lease,
                execution_authority=capability,
            )
        except SelectedPreSubmitInfrastructureUnavailable as exc:
            infrastructure_failure_code = exc.code

        finalize_facts = SelectedPreSubmitFinalizeFacts(
            lease=lease,
            execution=execution,
            infrastructure_failure_code=infrastructure_failure_code,
        )
        async with self._session.begin():
            async with self._authority.prepare_finalization(
                finalize_facts
            ) as prepared:
                return await self._coordinator.finalize(
                    run_id=run_id,
                    lease=lease,
                    authority=prepared,
                    execution=execution,
                    infrastructure_failure_code=infrastructure_failure_code,
                )

    async def recover_expired(
        self,
        *,
        run_id: UUID,
        reservation: SelectedPreSubmitReservationFacts,
    ) -> SelectedPreSubmitCompletion:
        """Finalize a crashed lease without recreating its process-local grant."""
        if run_id != reservation.attempt_id:
            raise SelectedPreSubmitInfrastructureUnavailable(
                "material_unavailable"
            )
        async with self._session.begin():
            lease = await self._coordinator.read_expired_lease(
                run_id=reservation.attempt_id,
                facts=reservation,
            )

        finalize_facts = SelectedPreSubmitFinalizeFacts(
            lease=lease,
            execution=None,
            infrastructure_failure_code="deadline_exceeded",
        )
        async with self._session.begin():
            async with self._authority.prepare_finalization(
                finalize_facts
            ) as prepared:
                return await self._coordinator.finalize(
                    run_id=reservation.attempt_id,
                    lease=lease,
                    authority=prepared,
                    execution=None,
                    infrastructure_failure_code="deadline_exceeded",
                )


__all__ = ("SelectedPreSubmitExecutionService",)
