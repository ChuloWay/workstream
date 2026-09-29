"""Verified checker-output bindings in the caller's final-result transaction."""

from typing import Protocol
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.checkers.api.output_custody import (
    CheckerOutputBindingRequest,
    CheckerOutputBindingResult,
    CheckerOutputReservation,
    CheckerOutputReservationPort,
    CheckerOutputSelector,
    CheckerOutputUnavailable,
)
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.checker_output_custody import (
    CheckerOutputStoredFacts,
    select_checker_output,
)
from app.modules.artifacts.models import ArtifactBinding


class CheckerOutputBindingAuthority(Protocol):
    """Prepare authority before CHECKERS locks, consume exact ART custody afterward."""

    async def preflight(self, selector: CheckerOutputSelector) -> None:
        """Deny before any owner or artifact lookup."""

    async def prepare(self, selector: CheckerOutputSelector) -> None:
        """Stabilize exact service authority before feature row locks."""

    async def consume(
        self, reservation: CheckerOutputReservation, facts: CheckerOutputStoredFacts
    ) -> None:
        """Consume binding action authority in this caller-owned transaction."""

    def discard(self) -> None:
        """Release process-local authority without committing or rolling back."""


class DenyCheckerOutputBindingAuthority:
    """No production binding until exact AUTH and CHECKERS custody are implemented."""

    async def preflight(self, selector: CheckerOutputSelector) -> None:
        """Reject before protected reads."""
        raise CheckerOutputUnavailable("checker_output_binding_unavailable")

    async def prepare(self, selector: CheckerOutputSelector) -> None:
        """Reject binding authority preparation."""
        raise CheckerOutputUnavailable("checker_output_binding_unavailable")

    async def consume(
        self, reservation: CheckerOutputReservation, facts: CheckerOutputStoredFacts
    ) -> None:
        """Reject publication authority."""
        raise CheckerOutputUnavailable("checker_output_binding_unavailable")

    def discard(self) -> None:
        """No prepared authority exists."""


class CheckerOutputBindingService:
    """Flush one immutable binding; never commit the caller's result transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        reservations: CheckerOutputReservationPort,
        authority: CheckerOutputBindingAuthority,
        namespace_fingerprint: str,
    ) -> None:
        self._session, self._reservations, self._authority = session, reservations, authority
        self._namespace_fingerprint = namespace_fingerprint

    async def bind_checker_output(
        self, request: CheckerOutputBindingRequest
    ) -> CheckerOutputBindingResult:
        """Fence current worker facts before acquiring ART binding/verification locks."""
        if (
            type(request) is not CheckerOutputBindingRequest
            or not self._session.in_transaction()
            or self._session.in_nested_transaction()
            or type(request.put_attempt_id) is not UUID
            or type(request.verification_receipt_id) is not UUID
        ):
            raise CheckerOutputUnavailable("checker_output_binding_unavailable")
        selector = CheckerOutputSelector.model_validate(request.selector)
        try:
            await self._authority.preflight(selector)
            await self._authority.prepare(selector)
            reservation = await self._reservations.resolve(selector)
            reservation.select(selector)
            await self._session.execute(
                text("select pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {
                    "key": f"checker-output:{selector.evaluation.project_id}:{selector.checker_run_id}:{selector.slot_key}",
                },
            )
            facts = await select_checker_output(
                self._session,
                selector=selector,
                reservation=reservation,
                namespace_fingerprint=self._namespace_fingerprint,
                put_attempt_id=request.put_attempt_id,
                verification_receipt_id=request.verification_receipt_id,
                lock_verified=True,
            )
            if (
                facts is None
                or facts.status != "verified"
                or facts.verification_receipt_id != request.verification_receipt_id
            ):
                raise CheckerOutputUnavailable("checker_output_verification_unavailable")
            await self._authority.consume(reservation, facts)
            binding = await self._session.scalar(
                select(ArtifactBinding)
                .where(
                    ArtifactBinding.project_id == str(selector.evaluation.project_id),
                    ArtifactBinding.resource_type == "checker_run",
                    ArtifactBinding.resource_id == str(selector.checker_run_id),
                    ArtifactBinding.logical_role == selector.slot_key,
                    ArtifactBinding.scope_version == 1,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            replayed = binding is not None
            if binding is not None:
                if (
                    binding.content_id,
                    binding.put_attempt_id,
                    binding.verification_receipt_id,
                    binding.actor_id,
                    binding.attribution_type,
                ) != (
                    str(facts.content_id),
                    str(facts.put_attempt_id),
                    str(facts.verification_receipt_id),
                    ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value,
                    "service_identity",
                ):
                    raise CheckerOutputUnavailable("checker_output_binding_conflict")
            else:
                binding = ArtifactBinding(
                    id=str(new_record_id()),
                    content_id=str(facts.content_id),
                    project_id=str(selector.evaluation.project_id),
                    resource_type="checker_run",
                    resource_id=str(selector.checker_run_id),
                    logical_role=selector.slot_key,
                    scope_version=1,
                    actor_id=ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value,
                    attribution_type="service_identity",
                    supersedes_binding_id=None,
                    put_attempt_id=str(facts.put_attempt_id),
                    verification_receipt_id=str(facts.verification_receipt_id),
                )
                self._session.add(binding)
                await self._session.flush()
            return CheckerOutputBindingResult(
                UUID(binding.id),
                UUID(binding.content_id),
                request.put_attempt_id,
                request.verification_receipt_id,
                replayed,
            )
        finally:
            self._authority.discard()
