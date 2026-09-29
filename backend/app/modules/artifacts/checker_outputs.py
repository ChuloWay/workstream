"""Bounded checker bytes through the existing durable ART storage workflow."""

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.modules.checkers.api.output_custody import (
    CheckerOutputArtifactRequest,
    CheckerOutputArtifactResult,
    CheckerOutputReservation,
    CheckerOutputReservationPort,
    CheckerOutputSelector,
    CheckerOutputUnavailable,
)
from app.interfaces.artifacts import ArtifactStore
from app.modules.artifacts.checker_output_custody import (
    CheckerOutputStoredFacts,
    select_checker_output,
)
from app.modules.artifacts.models import ArtifactVerificationJob
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.artifacts.schemas import (
    ArtifactInternalAuthority,
    CheckerOutputArtifactAdmissionRequest,
)
from app.modules.artifacts.service import (
    ArtifactAdmissionService,
    ArtifactStorageOrchestrator,
    ArtifactStorageNamespaceSpec,
)


class CheckerOutputWriteAuthority(Protocol):
    """Fresh write authority; no prepared handle survives a storage operation."""

    async def preflight(self, selector: CheckerOutputSelector) -> None:
        """Deny before owner facts, source iteration or scratch access."""

    async def prepare(self, selector: CheckerOutputSelector) -> None:
        """Stabilize service authority before CHECKERS and ART transaction locks."""

    async def consume(self, request: CheckerOutputArtifactAdmissionRequest) -> None:
        """Bind the exact active worker, slot and byte commitment before admission."""

    async def consume_existing(
        self, reservation: CheckerOutputReservation, facts: CheckerOutputStoredFacts
    ) -> None:
        """Authorize exact stored output recovery with the current worker lease."""

    def discard(self) -> None:
        """Dispose transaction-local authority after each phase."""


class DenyCheckerOutputWriteAuthority:
    """Keep production output storage unavailable until ARCH-04D activation."""

    async def preflight(self, selector: CheckerOutputSelector) -> None:
        """Reject before any protected access."""
        raise CheckerOutputUnavailable("checker_output_write_unavailable")

    async def prepare(self, selector: CheckerOutputSelector) -> None:
        """Reject transaction authority preparation."""
        raise CheckerOutputUnavailable("checker_output_write_unavailable")

    async def consume(self, request: CheckerOutputArtifactAdmissionRequest) -> None:
        """Reject durable output admission."""
        raise CheckerOutputUnavailable("checker_output_write_unavailable")

    async def consume_existing(
        self, reservation: CheckerOutputReservation, facts: CheckerOutputStoredFacts
    ) -> None:
        """Reject recovery of protected output facts."""
        raise CheckerOutputUnavailable("checker_output_write_unavailable")

    def discard(self) -> None:
        """No authority was retained."""


class CheckerArtifactOutputService:
    """Own preparation lifetime; reuse put/observation and independent verification."""

    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        reservations: Callable[[AsyncSession], CheckerOutputReservationPort],
        authority: Callable[[AsyncSession], CheckerOutputWriteAuthority],
        internal_authority: Callable[[AsyncSession], ArtifactInternalAuthority],
        preparation: ArtifactPreparationService,
        store: ArtifactStore,
        namespace: ArtifactStorageNamespaceSpec,
        settings: Settings,
    ) -> None:
        self._sessions, self._reservations, self._authority = sessions, reservations, authority
        self._internal_authority, self._preparation = internal_authority, preparation
        self._store, self._namespace, self._settings = store, namespace, settings

    async def store(self, request: CheckerOutputArtifactRequest) -> CheckerOutputArtifactResult:
        """Commit checked output bytes before I/O, never a CHECKERS completion."""
        if type(request) is not CheckerOutputArtifactRequest:
            raise TypeError("invalid checker output request")
        selector = CheckerOutputSelector.model_validate(request.selector)
        prepared = None
        async with self._sessions() as session:
            authority = self._authority(session)
            try:
                await authority.preflight(selector)
                async with session.begin():
                    await authority.prepare(selector)
                    reservation = await self._reservations(session).resolve(selector)
                    slot = reservation.select(selector)
                authority.discard()
                prepared = await self._preparation.prepare(
                    request.byte_source,
                    media_type=slot.media_type,
                    maximum_bytes=slot.maximum_bytes,
                )
                async with session.begin():
                    await authority.prepare(selector)
                    current = await self._reservations(session).resolve(selector)
                    if current.select(selector) != slot:
                        raise CheckerOutputUnavailable("checker_output_slot_changed")
                    admission = await ArtifactAdmissionService(
                        session, self._settings, self._namespace
                    ).admit(
                        CheckerOutputArtifactAdmissionRequest(
                            reservation=current,
                            slot_key=slot.key,
                            source=prepared.committed_source,
                        ),
                        checker_output_authority=authority,
                        existing_transaction=True,
                    )
                authority.discard()
                storage = self._storage(session)
                if admission.status == "object_confirmed":
                    status = admission.status
                elif admission.replayed:
                    status = await storage.resume_committed_put(
                        attempt_id=admission.attempt_id,
                        source=prepared.committed_source,
                    )
                else:
                    status = await storage.execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=prepared.committed_source,
                    )
                await self._verify(session, storage, admission.attempt_id, status)
                return await self._result(session, authority, selector, replayed=admission.replayed)
            finally:
                authority.discard()
                if prepared is not None:
                    await prepared.close()

    async def recover(self, selector: CheckerOutputSelector) -> CheckerOutputArtifactResult | None:
        """Recover a lost response by logical identity without regenerating bytes."""
        selector = CheckerOutputSelector.model_validate(selector)
        async with self._sessions() as session:
            authority = self._authority(session)
            try:
                await authority.preflight(selector)
                async with session.begin():
                    await authority.prepare(selector)
                    reservation = await self._reservations(session).resolve(selector)
                    reservation.select(selector)
                    facts = await select_checker_output(
                        session,
                        selector=selector,
                        reservation=reservation,
                        namespace_fingerprint=self._namespace.namespace_fingerprint,
                    )
                    if facts is None:
                        return None
                    await authority.consume_existing(reservation, facts)
                authority.discard()
                storage = self._storage(session)
                status = facts.status
                if status not in {"object_confirmed", "verified"}:
                    status = await storage.resolve_put_attempt(facts.put_attempt_id)
                await self._verify(session, storage, facts.put_attempt_id, status)
                return await self._result(session, authority, selector, replayed=True)
            finally:
                authority.discard()

    def _storage(self, session: AsyncSession) -> ArtifactStorageOrchestrator:
        """Use the shared put, observation and verification implementation."""
        return ArtifactStorageOrchestrator(
            session, self._store, self._namespace, self._settings, self._internal_authority(session)
        )

    async def _verify(
        self,
        session: AsyncSession,
        storage: ArtifactStorageOrchestrator,
        attempt_id: UUID,
        status: str,
    ) -> None:
        """Independently verify confirmed bytes through the existing ART worker."""
        if status not in {
            "object_confirmed",
            "verified",
            "stored_pending_verification",
            "observed_confirmed",
        }:
            return
        async with session.begin():
            job_id = await session.scalar(
                select(ArtifactVerificationJob.id)
                .where(
                    ArtifactVerificationJob.originating_put_attempt_id == str(attempt_id),
                    ArtifactVerificationJob.status == "pending",
                )
                .order_by(ArtifactVerificationJob.id)
                .limit(1)
            )
        if job_id is not None:
            await storage.verify_object(UUID(job_id))

    async def _result(
        self,
        session: AsyncSession,
        authority: CheckerOutputWriteAuthority,
        selector: CheckerOutputSelector,
        *,
        replayed: bool,
    ) -> CheckerOutputArtifactResult:
        """Recheck current owner custody and authority after provider operations."""
        async with session.begin():
            await authority.prepare(selector)
            reservation = await self._reservations(session).resolve(selector)
            reservation.select(selector)
            facts = await select_checker_output(
                session,
                selector=selector,
                reservation=reservation,
                namespace_fingerprint=self._namespace.namespace_fingerprint,
            )
            if facts is None:
                raise CheckerOutputUnavailable("checker_output_unavailable")
            await authority.consume_existing(reservation, facts)
            return CheckerOutputArtifactResult(
                facts.put_attempt_id,
                facts.status,
                facts.content_id,
                facts.verification_receipt_id,
                replayed,
            )
