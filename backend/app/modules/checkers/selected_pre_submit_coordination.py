"""Durable selected PRE reservation and TASK-first lease/finalization custody."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitExecutionFacts,
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
    SelectedPreSubmitTerminalFacts,
)
from app.modules.checkers.models import SelectedPreSubmitRun


class SelectedPreSubmitUnavailable(RuntimeError):
    """Conceal absent, foreign, stale, conflicting or already leased PRE custody."""


class SelectedPreSubmitTaskGuard(Protocol):
    """TASK owns current contributor/assignment/policy checks before CHECKERS locks."""

    async def lock_selected_pre_submit_scope(
        self, reservation: SelectedPreSubmitReservationFacts
    ) -> None:
        """Lock and validate exact current TASK scope through caller commit."""


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitCompletion:
    """Terminal facts and one process-local capability for immediate admission."""

    terminal: SelectedPreSubmitTerminalFacts
    capability: SelectedPreSubmitAdmissionCapability | None


_CAPABILITY_SEAL = object()


class SelectedPreSubmitAdmissionCapability:
    """One-use completed-pass authority minted inside the finalization root."""

    __slots__ = (
        "_consumed",
        "_owner",
        "_seal",
        "_lock",
        "run_id",
        "terminal_digest",
        "attempt_id",
        "prepared_generation_id",
        "archive_sha256",
        "semantic_manifest_sha256",
    )

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("selected PRE admission capabilities are coordinator-issued")

    @classmethod
    def _issued(
        cls,
        *,
        owner: SelectedPreSubmitCoordinator,
        run_id: UUID,
        terminal: SelectedPreSubmitTerminalFacts,
    ) -> SelectedPreSubmitAdmissionCapability:
        reservation = terminal.lease.reservation
        value = object.__new__(cls)
        value._owner = owner
        value._seal = _CAPABILITY_SEAL
        value._lock = threading.Lock()
        value._consumed = False
        value.run_id = run_id
        value.terminal_digest = terminal.terminal_digest
        value.attempt_id = reservation.attempt_id
        value.prepared_generation_id = reservation.prepared_generation_id
        value.archive_sha256 = reservation.archive_sha256
        value.semantic_manifest_sha256 = reservation.semantic_manifest_sha256
        return value

    def consume(
        self,
        *,
        run_id: UUID,
        terminal_digest: str,
        attempt_id: UUID,
        prepared_generation_id: UUID,
        archive_sha256: str,
        semantic_manifest_sha256: str,
    ) -> UUID:
        """Consume only for the exact finalized run and still-live prepared bytes."""
        with self._lock:
            if (
                self._seal is not _CAPABILITY_SEAL
                or self._consumed
                or self._owner._capability is not self
                or (
                    run_id,
                    terminal_digest,
                    attempt_id,
                    prepared_generation_id,
                    archive_sha256,
                    semantic_manifest_sha256,
                )
                != (
                    self.run_id,
                    self.terminal_digest,
                    self.attempt_id,
                    self.prepared_generation_id,
                    self.archive_sha256,
                    self.semantic_manifest_sha256,
                )
            ):
                raise SelectedPreSubmitUnavailable(
                    "selected_pre_submit_admission_unavailable"
                )
            self._consumed = True
            self._owner._capability = None
            return self.run_id


class SelectedPreSubmitExecutionCapability:
    """One-use authority for the committed lease's process-local ART callback."""

    __slots__ = ("_consumed", "_owner", "_seal", "_lock", "run_id", "lease")

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("selected PRE execution capabilities are coordinator-issued")

    @classmethod
    def _issued(
        cls,
        *,
        owner: SelectedPreSubmitCoordinator,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
    ) -> SelectedPreSubmitExecutionCapability:
        value = object.__new__(cls)
        value._owner = owner
        value._seal = _CAPABILITY_SEAL
        value._lock = threading.Lock()
        value._consumed = False
        value.run_id = run_id
        value.lease = lease
        return value

    def consume(
        self,
        *,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
    ) -> SelectedPreSubmitLeaseFacts:
        """Consume only for the exact committed run generation and request facts."""
        with self._lock:
            if (
                self._seal is not _CAPABILITY_SEAL
                or self._consumed
                or self._owner._execution_capability is not self
                or run_id != self.run_id
                or lease != self.lease
            ):
                raise SelectedPreSubmitUnavailable(
                    "selected_pre_submit_execution_unavailable"
                )
            self._consumed = True
            self._owner._execution_capability = None
            return self.lease


def _require_root(session: AsyncSession) -> None:
    transaction = session.sync_session.get_transaction()
    if (
        transaction is None
        or not transaction.is_active
        or session.in_nested_transaction()
    ):
        raise RuntimeError("selected PRE coordination requires one root transaction")


def _matches(row: SelectedPreSubmitRun, facts: SelectedPreSubmitReservationFacts) -> bool:
    return (
        row.request_json == facts.canonical_body()
        and row.request_digest == facts.request_digest
        and row.id == str(facts.attempt_id)
        and row.actor_profile_id == str(facts.actor_profile_id)
        and row.identity_link_id == str(facts.identity_link_id)
        and row.project_id == str(facts.project_id)
        and row.task_id == str(facts.task_id)
        and row.assignment_id == str(facts.assignment_id)
        and row.prepared_generation_id == str(facts.prepared_generation_id)
        and row.policy_sha256 == facts.policy_sha256
        and row.default_behavior_sha256 == facts.default_behavior_sha256
        and row.default_input_sha256 == facts.default_input_sha256
        and row.archive_sha256 == facts.archive_sha256
        and row.archive_byte_count == facts.archive_byte_count
        and row.semantic_manifest_sha256 == facts.semantic_manifest_sha256
        and row.execution_budget_ms == facts.execution_budget_ms
    )


class SelectedPreSubmitCoordinator:
    """Reserve, lease and finalize one selected PRE run in caller-owned roots."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        tasks: SelectedPreSubmitTaskGuard,
    ) -> None:
        self._session = session
        self._tasks = tasks
        self._capability: SelectedPreSubmitAdmissionCapability | None = None
        self._execution_capability: SelectedPreSubmitExecutionCapability | None = None

    async def reserve(self, facts: SelectedPreSubmitReservationFacts) -> UUID:
        """Acquire TASK custody before the CHECKERS key and exact request row."""
        _require_root(self._session)
        if type(facts) is not SelectedPreSubmitReservationFacts:
            raise TypeError("selected PRE reservation facts are invalid")
        await self._tasks.lock_selected_pre_submit_scope(facts)
        await self._session.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "checkers:selected-pre:" + str(facts.attempt_id)},
        )
        row = await self._session.scalar(
            select(SelectedPreSubmitRun)
            .where(SelectedPreSubmitRun.id == str(facts.attempt_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is not None:
            if not _matches(row, facts):
                raise SelectedPreSubmitUnavailable("selected_pre_submit_request_conflict")
            return UUID(row.id)
        row = SelectedPreSubmitRun(
            id=str(facts.attempt_id),
            actor_profile_id=str(facts.actor_profile_id),
            identity_link_id=str(facts.identity_link_id),
            project_id=str(facts.project_id),
            task_id=str(facts.task_id),
            assignment_id=str(facts.assignment_id),
            prepared_generation_id=str(facts.prepared_generation_id),
            request_json=facts.canonical_body(),
            request_digest=facts.request_digest,
            policy_sha256=facts.policy_sha256,
            default_behavior_sha256=facts.default_behavior_sha256,
            default_input_sha256=facts.default_input_sha256,
            archive_sha256=facts.archive_sha256,
            archive_byte_count=facts.archive_byte_count,
            semantic_manifest_sha256=facts.semantic_manifest_sha256,
            execution_budget_ms=facts.execution_budget_ms,
            status="queued",
            lease_generation=0,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError:
            raise SelectedPreSubmitUnavailable("selected_pre_submit_request_conflict") from None
        return facts.attempt_id

    async def claim(
        self,
        *,
        run_id: UUID,
        facts: SelectedPreSubmitReservationFacts,
        execute_evidence_id: UUID,
    ) -> SelectedPreSubmitLeaseFacts:
        """Issue one database-timed lease after fresh TASK and execute authority."""
        row = await self._lock(run_id=run_id, facts=facts)
        if row.status != "queued" or not isinstance(execute_evidence_id, UUID):
            raise SelectedPreSubmitUnavailable("selected_pre_submit_lease_unavailable")
        now = await self._session.scalar(select(func.clock_timestamp()))
        assert now is not None
        lease = SelectedPreSubmitLeaseFacts(
            reservation=facts,
            lease_id=new_record_id(),
            lease_generation=row.lease_generation + 1,
            lease_expires_at=now + timedelta(milliseconds=facts.execution_budget_ms),
        )
        row.lease_id = str(lease.lease_id)
        row.lease_generation = lease.lease_generation
        row.lease_expires_at = lease.lease_expires_at
        row.execute_evidence_id = str(execute_evidence_id)
        row.started_at = now
        row.status = "running"
        await self._session.flush()
        return lease

    async def committed_execution(
        self,
        *,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
    ) -> SelectedPreSubmitExecutionCapability:
        """Mint execution authority only after a fresh root observes the committed lease."""
        if self._session.in_transaction():
            raise RuntimeError("selected PRE execution requires a committed lease")
        async with self._session.begin():
            row = await self._lock(run_id=run_id, facts=lease.reservation)
            if (
                row.status != "running"
                or row.lease_id != str(lease.lease_id)
                or row.lease_generation != lease.lease_generation
                or row.lease_expires_at != lease.lease_expires_at
            ):
                raise SelectedPreSubmitUnavailable(
                    "selected_pre_submit_execution_unavailable"
                )
        capability = SelectedPreSubmitExecutionCapability._issued(
            owner=self,
            run_id=run_id,
            lease=lease,
        )
        self._execution_capability = capability
        return capability

    async def finalize(
        self,
        *,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
        finalize_evidence_id: UUID,
        execution: SelectedPreSubmitExecutionFacts | None,
        infrastructure_failure_code: str | None,
    ) -> SelectedPreSubmitCompletion:
        """Fence the lease and persist one exact terminal value under fresh TASK custody."""
        facts = lease.reservation
        row = await self._lock(run_id=run_id, facts=facts)
        if (
            row.status != "running"
            or row.lease_id != str(lease.lease_id)
            or row.lease_generation != lease.lease_generation
            or row.lease_expires_at != lease.lease_expires_at
            or not isinstance(finalize_evidence_id, UUID)
        ):
            raise SelectedPreSubmitUnavailable("selected_pre_submit_finalization_unavailable")
        completed_at = await self._session.scalar(select(func.clock_timestamp()))
        assert completed_at is not None and row.started_at is not None
        if execution is not None and completed_at > lease.lease_expires_at:
            raise SelectedPreSubmitUnavailable("selected_pre_submit_lease_expired")
        outcome = "completed" if execution is not None else "infrastructure_failed"
        terminal = SelectedPreSubmitTerminalFacts(
            lease=lease,
            outcome=outcome,
            execution=execution,
            infrastructure_failure_code=infrastructure_failure_code,
            queued_at=row.queued_at,
            started_at=row.started_at,
            completed_at=completed_at,
        )
        row.status = outcome
        row.terminal_json = terminal.canonical_body()
        row.terminal_digest = terminal.terminal_digest
        row.eligible = execution.eligible if execution is not None else None
        row.finalize_evidence_id = str(finalize_evidence_id)
        row.completed_at = completed_at
        await self._session.flush()
        capability = (
            SelectedPreSubmitAdmissionCapability._issued(
                owner=self, run_id=run_id, terminal=terminal
            )
            if execution is not None and execution.eligible
            else None
        )
        self._capability = capability
        return SelectedPreSubmitCompletion(terminal=terminal, capability=capability)

    async def _lock(
        self, *, run_id: UUID, facts: SelectedPreSubmitReservationFacts
    ) -> SelectedPreSubmitRun:
        _require_root(self._session)
        if not isinstance(run_id, UUID) or type(facts) is not SelectedPreSubmitReservationFacts:
            raise SelectedPreSubmitUnavailable("selected_pre_submit_run_unavailable")
        await self._tasks.lock_selected_pre_submit_scope(facts)
        row = await self._session.scalar(
            select(SelectedPreSubmitRun)
            .where(
                SelectedPreSubmitRun.id == str(run_id),
                SelectedPreSubmitRun.project_id == str(facts.project_id),
                SelectedPreSubmitRun.task_id == str(facts.task_id),
                SelectedPreSubmitRun.assignment_id == str(facts.assignment_id),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or not _matches(row, facts):
            raise SelectedPreSubmitUnavailable("selected_pre_submit_run_unavailable")
        return row


__all__ = (
    "SelectedPreSubmitAdmissionCapability",
    "SelectedPreSubmitCompletion",
    "SelectedPreSubmitCoordinator",
    "SelectedPreSubmitExecutionCapability",
    "SelectedPreSubmitTaskGuard",
    "SelectedPreSubmitUnavailable",
)
