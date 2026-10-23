"""Current invocation and call-stable private evidence custody."""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable,
    EvaluationTaskGuard,
    ExecutionLease,
)
from app.modules.checkers.api.model_calls import (
    ModelCallCurrentExecutionPort,
    ModelCallExecutionFacts,
    ModelCallUnavailable,
    ModelPaidSlotKey,
)
from app.modules.checkers.api.output_custody import (
    CheckerOutputReservation,
    CheckerOutputSelector,
    CheckerOutputSlot,
    CheckerOutputTaskCustodyPort,
    CheckerOutputUnavailable,
)
from app.modules.checkers.execution_repository import (
    ExecutionRepository,
    require_transaction,
    reservation,
    stored_request,
)
from app.modules.checkers.models import CheckerRun
from app.modules.checkers.model_calls.repository import ModelCallRepository
from app.modules.checkers.model_calls.grants import CheckerModelInvocationGrant


class ModelCallCurrentExecution:
    """Check the exact locked project binding before any paid effect is reserved."""

    def __init__(self, session: AsyncSession, *, tasks: EvaluationTaskGuard):
        self._session, self._tasks = session, tasks

    @staticmethod
    def _require_binding(request, slot: ModelPaidSlotKey) -> None:
        if request.assignment_id != slot.assignment_id or (
            slot.project_id,
            slot.submission_id,
            slot.submission_version,
        ) != (request.project_id, request.submission_id, request.submission_version):
            raise ModelCallUnavailable("model_call_execution_unavailable")
        bindings = [
            binding
            for binding in request.policy.entries
            if binding.requirement_id == slot.requirement_id
            and binding.registry.entry_digest == slot.registry_entry_digest
            and binding.configuration_sha256 == slot.configuration_sha256
        ]
        if len(bindings) != 1:
            raise ModelCallUnavailable("model_call_binding_unavailable")
        configuration = bindings[0].configuration
        if (
            configuration.get("model_profile_id") != str(slot.profile_id)
            or type(configuration.get("model_profile_version")) is not int
            or configuration.get("model_profile_version") != slot.profile_version
            or configuration.get("model_profile_digest") != slot.profile_digest
        ):
            raise ModelCallUnavailable("model_call_profile_unavailable")

    async def require_current(
        self,
        facts: ModelCallExecutionFacts,
        slot: ModelPaidSlotKey,
    ) -> None:
        """Read immutable request facts, then lock TASK before the CHECKERS fence."""
        require_transaction(self._session)
        facts = ModelCallExecutionFacts.model_validate(facts)
        slot = ModelPaidSlotKey.model_validate(slot)
        run = await self._session.scalar(
            select(CheckerRun)
            .where(
                CheckerRun.id == str(facts.checker_run_id),
                CheckerRun.project_id == str(facts.project_id),
                CheckerRun.task_id == str(facts.task_id),
                CheckerRun.submission_id == str(facts.submission_id),
                CheckerRun.submission_version == facts.submission_version,
                CheckerRun.evaluation_request_id == str(facts.evaluation_request_id),
                CheckerRun.evaluation_generation == facts.evaluation_generation,
            )
            .execution_options(populate_existing=True)
        )
        if run is None:
            raise ModelCallUnavailable("model_call_execution_unavailable")
        request = stored_request(run)
        if request.assignment_id != facts.assignment_id:
            raise ModelCallUnavailable("model_call_execution_unavailable")
        self._require_binding(request, slot)
        try:
            if not await self._tasks.lock_evaluation_scope(request):
                raise ModelCallUnavailable("model_call_execution_unavailable")
            await ExecutionRepository(self._session).require_lease(
                request,
                ExecutionLease(
                    reservation=reservation(run),
                    lease_id=facts.worker_lease_id,
                    lease_generation=facts.worker_lease_generation,
                    expires_at=facts.worker_lease_expires_at,
                ),
            )
        except CheckerExecutionUnavailable:
            raise ModelCallUnavailable("model_call_execution_unavailable") from None

    async def require_recovery_current(
        self, slot: ModelPaidSlotKey, parent_attempt_id: UUID
    ) -> None:
        """Lock current TASK/Submission custody for a terminal source, without a lease."""
        require_transaction(self._session)
        slot = ModelPaidSlotKey.model_validate(slot)
        repo = ModelCallRepository(self._session)
        slot_row = await repo.slot(slot)
        parent = await repo.attempt(parent_attempt_id)
        grant = await self._session.scalar(
            select(CheckerModelInvocationGrant).where(
                CheckerModelInvocationGrant.selected_attempt_id == str(parent_attempt_id)
            )
        )
        if (
            slot_row is None
            or parent is None
            or parent.slot_id != slot_row.id
            or grant is None
            or grant.project_id != str(slot.project_id)
            or grant.paid_slot != slot.model_dump(mode="json")
            or grant.selected_request_sha256 != parent.request_sha256
        ):
            raise ModelCallUnavailable("model_call_recovery_unavailable")
        run = await self._session.get(CheckerRun, grant.checker_run_id)
        if (
            run is None
            or run.task_id != slot_row.task_id
            or run.status != "infrastructure_failed"
            or run.failure_code is None
            or run.completed_at is None
        ):
            raise ModelCallUnavailable("model_call_recovery_unavailable")
        try:
            execution = ModelCallExecutionFacts.model_validate_json(
                json.dumps(grant.execution_facts)
            )
            request = stored_request(run)
        except (CheckerExecutionUnavailable, ValueError):
            raise ModelCallUnavailable("model_call_recovery_unavailable") from None
        if execution.checker_run_id != UUID(run.id) or execution.task_id != UUID(slot_row.task_id):
            raise ModelCallUnavailable("model_call_recovery_unavailable")
        self._require_binding(request, slot)
        try:
            if not await self._tasks.lock_evaluation_scope(request):
                raise ModelCallUnavailable("model_call_recovery_unavailable")
        except CheckerExecutionUnavailable:
            raise ModelCallUnavailable("model_call_recovery_unavailable") from None


class CheckerOutputReservations:
    """Resolve two bounded ART roles under one immutable paid call identity."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        current: ModelCallCurrentExecutionPort,
        tasks: CheckerOutputTaskCustodyPort,
    ):
        self._session, self._current = session, current
        self._tasks = tasks

    async def resolve(self, selector: CheckerOutputSelector) -> CheckerOutputReservation:
        """Requests require current execution; late responses retain effect custody."""
        require_transaction(self._session)
        selector = CheckerOutputSelector.model_validate(selector)
        if selector.execution is not None:
            await self._current.require_current(selector.execution, selector.paid_slot)
        else:
            await self._tasks.lock_model_evidence_scope(selector)
        repo = ModelCallRepository(self._session)
        await repo.lock_slot_scope(selector.paid_slot)
        slot = await repo.slot(selector.paid_slot, lock=True)
        if slot is None or (
            slot.id != str(selector.model_call_slot_id) or slot.task_id != str(selector.task_id)
        ):
            raise CheckerOutputUnavailable("checker_output_reservation_unavailable")
        attempt = await repo.attempt(selector.model_call_attempt_id, lock=True)
        if attempt is None or attempt.slot_id != slot.id:
            raise CheckerOutputUnavailable("checker_output_reservation_unavailable")
        profile = await repo.profile_exact(
            selector.paid_slot.profile_id,
            selector.paid_slot.profile_version,
            selector.paid_slot.profile_digest,
        )
        if profile is None or (
            profile.project_id != str(selector.paid_slot.project_id)
            or profile.registry_entry_digest != selector.paid_slot.registry_entry_digest
        ):
            raise CheckerOutputUnavailable("checker_output_profile_unavailable")
        if selector.slot_key == "model_request":
            if attempt.request_sha256 != selector.content_sha256:
                raise CheckerOutputUnavailable("checker_output_request_conflict")
            maximum = profile.maximum_request_bytes
        else:
            if attempt.state not in {"dispatching", "uncertain", "completed", "known_failed"}:
                raise CheckerOutputUnavailable("checker_output_effect_unavailable")
            if attempt.response_content_sha256 not in {None, selector.content_sha256}:
                raise CheckerOutputUnavailable("checker_output_response_conflict")
            maximum = profile.maximum_response_bytes
        return CheckerOutputReservation(
            selector=selector,
            slot=CheckerOutputSlot(key=selector.slot_key, maximum_bytes=maximum),
        )
