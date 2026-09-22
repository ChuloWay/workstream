"""Canonical project-authorized task commands with one transaction owner."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.db.errors import integrity_constraint_name
from app.modules.tasks.api.authorization import (
    TaskAuthorityFacts,
    TaskAuthorityOperation,
    TaskAuthorizationPort,
)
from app.modules.tasks.api.work_context import (
    ContributorTaskLifecycle, ContributorTaskWorkContext, ManagementTaskWorkContext,
)
from app.modules.tasks.api.task_detail import ContributorTaskDetailRequest, ManagementTaskDetailRequest
from app.modules.tasks.api.transition_audit import TaskTransitionAuditPort, TaskTransitionFacts
from app.modules.tasks.models import TaskAssignment, TaskCommandReceipt, WorkstreamTask
from app.modules.tasks.command_replay import TaskCommandReplay
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import (
    AssignmentResponse,
    TaskResponse,
    TaskWithAssignmentResponse,
)
from app.modules.tasks.service import (
    LOCKED_CONTEXT_REQUIRED_FIELDS,
    TaskAssignmentConflict,
    TaskNotFound,
    TaskService,
    TaskTransitionBlocked,
    TaskValidationError,
)


class AuthorizedTaskCommands:
    """TASK owns state and assignment; AUTH owns permission and current grants."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authorization: TaskAuthorizationPort,
        audit: TaskTransitionAuditPort,
        actor_profile_id: UUID,
        contexts: TaskService,
    ) -> None:
        self._session = session
        self._authorization = authorization
        self._audit = audit
        self._actor_id = actor_profile_id
        self._repo = TaskRepository(session)
        self._contexts = contexts
        self._replay = TaskCommandReplay(session)

    def _facts(
        self,
        task: WorkstreamTask,
        assignment: TaskAssignment | None,
        operation: TaskAuthorityOperation,
        reason: str | None,
        idempotency_key: UUID | None = None,
        replay_assignment_id: UUID | None = None,
    ) -> TaskAuthorityFacts:
        return TaskAuthorityFacts(
            operation=operation,
            task_id=UUID(task.id),
            project_id=UUID(task.project_id),
            actor_profile_id=self._actor_id,
            task_status=task.status,
            assigned_to=UUID(task.assigned_to) if task.assigned_to else None,
            assignment_id=UUID(assignment.id) if assignment else None,
            assignment_contributor_id=UUID(assignment.contributor_id) if assignment else None,
            locked_context_hash=canonical_json_hash(
                {field: (str(getattr(task, field)) if isinstance(getattr(task, field), UUID)
                         else getattr(task, field)) for field in LOCKED_CONTEXT_REQUIRED_FIELDS}
            ),
            reason=reason,
            idempotency_key=idempotency_key,
            replay_assignment_id=replay_assignment_id,
        )

    async def _locked_task(
        self,
        task_id: UUID,
        operation: TaskAuthorityOperation,
        reason: str | None = None,
        project_id: UUID | None = None,
        idempotency_key: UUID | None = None,
        receipt: TaskCommandReceipt | None = None,
    ) -> tuple[WorkstreamTask, TaskAssignment | None, UUID]:
        # Match submission creation: TASK/assignment locks precede AUTH locks.
        task = await self._repo.get_task(str(task_id), for_update=True)
        if task is None or (project_id is not None and task.project_id != str(project_id)):
            raise TaskNotFound("task not found")
        assignment = await self._repo.get_active_assignment(task.id, for_update=True)
        facts = self._facts(
            task, assignment, operation, reason, idempotency_key,
            self._replay.replay_assignment(receipt, task_id) if receipt else None,
        )
        handle = await self._authorization.prepare(facts)
        try:
            decision_id = await self._authorization.consume(handle, facts)
            return task, assignment, decision_id
        finally:
            self._authorization.close(handle)

    async def claim(
        self, task_id: UUID, reason: str | None = None, *, idempotency_key: UUID,
    ) -> TaskWithAssignmentResponse:
        try:
            async with self._session.begin():
                receipt, digest, reserved = await self._replay.reserve(
                    self._actor_id, TaskAuthorityOperation.CLAIM, idempotency_key, task_id, reason,
                )
                task, assignment, decision_id = await self._locked_task(
                    task_id,
                    TaskAuthorityOperation.CLAIM,
                    reason,
                    idempotency_key=idempotency_key, receipt=receipt,
                )
                facts = self._facts(task, assignment, TaskAuthorityOperation.CLAIM, reason, idempotency_key)
                replayed = self._replay.recover(receipt, digest, facts, task, assignment, reserved=reserved)
                if replayed is not None:
                    if not isinstance(replayed, TaskWithAssignmentResponse):
                        raise RuntimeError("invalid claim response")
                    return replayed
                self._contexts._ensure_transition_allowed(task.status, "claimed")
                if assignment is not None or task.assigned_to is not None:
                    raise TaskAssignmentConflict("task already has an active assignment")
                await self._contexts._load_locked_task_context(task)
                assignment = await self._repo.add_assignment(
                    TaskAssignment(
                        id=str(uuid4()),
                        task_id=task.id,
                        project_id=task.project_id,
                        submitter_contribution_policy_version_id=task.locked_contribution_policy_version_id,
                        contributor_id=str(self._actor_id),
                        assigned_by=str(self._actor_id),
                        accepted_at=datetime.now(UTC),
                        status="active",
                    )
                )
                task.assigned_to = str(self._actor_id)
                await self._transition(task, assignment, "claimed", decision_id, reason)
                await self._session.flush()
                await self._session.refresh(task)
                response = TaskWithAssignmentResponse(
                    task=self._contexts.task_response_for_authority(task, can_manage=False),
                    assignment=AssignmentResponse.model_validate(assignment),
                )
                self._replay.complete(receipt, assignment, facts, response)
                await self._session.flush()
            return response
        except IntegrityError as exc:
            if integrity_constraint_name(exc) == "uq_task_assignments_one_active_per_task":
                raise TaskAssignmentConflict("task already has an active assignment") from exc
            raise

    async def start(
        self,
        task_id: UUID,
        reason: str | None = None,
        *,
        idempotency_key: UUID,
        operator_override: bool = False,
    ) -> TaskResponse:
        if operator_override and not (reason and reason.strip()):
            raise TaskValidationError("operator start override reason is required")
        operation = (
            TaskAuthorityOperation.START_OVERRIDE
            if operator_override
            else TaskAuthorityOperation.START
        )
        async with self._session.begin():
            receipt, digest, reserved = await self._replay.reserve(
                self._actor_id, operation, idempotency_key, task_id, reason,
            )
            task, assignment, decision_id = await self._locked_task(
                task_id, operation, reason, idempotency_key=idempotency_key, receipt=receipt,
            )
            facts = self._facts(task, assignment, operation, reason, idempotency_key)
            replayed = self._replay.recover(receipt, digest, facts, task, assignment, reserved=reserved)
            if replayed is not None:
                if not isinstance(replayed, TaskResponse):
                    raise RuntimeError("invalid start response")
                return replayed
            self._contexts._ensure_transition_allowed(task.status, "in_progress")
            if assignment is None or assignment.contributor_id != task.assigned_to:
                raise TaskTransitionBlocked("task has no consistent active assignment")
            await self._contexts._load_locked_task_context(task)
            await self._transition(
                task,
                assignment,
                "in_progress",
                decision_id,
                reason,
                operator_override=operator_override,
            )
            await self._session.flush()
            await self._session.refresh(task)
            response = self._contexts.task_response_for_authority(task, can_manage=False)
            self._replay.complete(receipt, assignment, facts, response)
            await self._session.flush()
        return response

    async def contributor_work_context(self, task_id: UUID) -> ContributorTaskWorkContext:
        """Project current contributor instructions under the existing exact authority."""
        if not isinstance(task_id, UUID):
            raise TaskValidationError("work context task ID is invalid")
        async with self._session.begin():
            task, assignment, _ = await self._locked_task(task_id, TaskAuthorityOperation.WORK_CONTEXT)
            context = await self._contexts._load_locked_task_context(task)
            detail = await self._repo.read_contributor_task_detail(
                ContributorTaskDetailRequest(UUID(task.project_id), task_id, self._actor_id),
            )
            if detail is None:
                raise TaskNotFound("task not found")
            own_assignment = bool(
                assignment is not None
                and assignment.contributor_id == str(self._actor_id)
                and task.assigned_to == str(self._actor_id)
            )
            actions = ()
            if task.status == "ready" and assignment is None and task.assigned_to is None:
                actions = ("claim",)
            elif task.status == "claimed" and own_assignment:
                actions = ("start",)
            selection = context.facts.activation_receipt.command
            response = ContributorTaskWorkContext(
                task=detail, project=context.facts.project, guide=context.facts.guide,
                review_policy=selection.review, revision_policy=selection.revision,
                contribution_policy_version_id=selection.contribution_policy_version_id,
                lifecycle=ContributorTaskLifecycle(
                    assigned_to_current_actor=own_assignment, next_actions=actions,
                ),
            )
        return response

    async def management_work_context(
        self, project_id: UUID, task_id: UUID,
    ) -> ManagementTaskWorkContext:
        """Project manager instructions through the existing exact project authority."""
        if not isinstance(project_id, UUID) or not isinstance(task_id, UUID):
            raise TaskValidationError("work context project or task ID is invalid")
        async with self._session.begin():
            task, _, _ = await self._locked_task(
                task_id, TaskAuthorityOperation.MANAGEMENT_WORK_CONTEXT, project_id=project_id,
            )
            context = await self._contexts._load_locked_task_context(task)
            detail = await self._repo.read_management_task_detail(ManagementTaskDetailRequest(project_id, task_id))
            if detail is None:
                raise TaskNotFound("task not found")
            selection = context.facts.activation_receipt.command
            response = ManagementTaskWorkContext(
                task=detail, project=context.facts.project, guide=context.facts.guide,
                review_policy=selection.review, revision_policy=selection.revision,
                contribution_policy_version_id=selection.contribution_policy_version_id,
            )
        return response

    async def _transition(
        self,
        task: WorkstreamTask,
        assignment: TaskAssignment,
        status: str,
        decision_id: UUID,
        reason: str | None,
        *,
        operator_override: bool = False,
    ) -> None:
        before = task.status
        task.status = status
        await self._audit.record(TaskTransitionFacts(
            operation=(
                TaskAuthorityOperation.START_OVERRIDE if operator_override
                else TaskAuthorityOperation.CLAIM if status == "claimed"
                else TaskAuthorityOperation.START
            ),
            project_id=UUID(task.project_id), task_id=UUID(task.id),
            assignment_id=UUID(assignment.id), actor_profile_id=self._actor_id,
            authorization_decision_id=decision_id,
            from_status=before, to_status=status, reason=reason,
        ))
