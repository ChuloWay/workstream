"""Durable task command replay within the existing caller-owned transaction."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.tasks.api.authorization import TaskAuthorityFacts, TaskAuthorityOperation
from app.modules.tasks.models import TaskAssignment, TaskCommandReceipt, WorkstreamTask
from app.modules.tasks.schemas import TaskResponse, TaskWithAssignmentResponse
from app.modules.tasks.service import TaskServiceError


class TaskReplayConflict(TaskServiceError):
    """A currently authorized retry conflicts with its durable command receipt."""

    status_code = 409

    def __init__(self, code: str):
        self.code = code
        super().__init__("Task command conflicts with the original request or current state")


class TaskCommandReplay:
    """Reserve first, then lock TASK and AUTH; never own a separate transaction."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def reserve(
        self, actor_id: UUID, operation: TaskAuthorityOperation, key: UUID,
        task_id: UUID, reason: str | None,
    ) -> tuple[TaskCommandReceipt, str, bool]:
        if not isinstance(key, UUID):
            raise ValueError("task command requires an idempotency UUID")
        digest = canonical_json_hash({"task_id": str(task_id), "reason": reason})
        inserted_id = uuid4()
        receipt_id = await self._session.scalar(
            insert(TaskCommandReceipt).values(
                id=inserted_id, actor_profile_id=str(actor_id), action_id=operation.value,
                idempotency_key=key, request_digest=digest, task_id=str(task_id), status="pending",
            ).on_conflict_do_update(
                index_elements=[TaskCommandReceipt.actor_profile_id, TaskCommandReceipt.action_id,
                                TaskCommandReceipt.idempotency_key],
                set_={"id": TaskCommandReceipt.id},
            ).returning(TaskCommandReceipt.id)
        )
        receipt = await self._session.get(TaskCommandReceipt, receipt_id, populate_existing=True)
        if receipt is None:
            raise RuntimeError("task command reservation disappeared")
        return receipt, digest, receipt_id == inserted_id

    @staticmethod
    def replay_assignment(receipt: TaskCommandReceipt, task_id: UUID) -> UUID | None:
        """Only a committed same-task receipt may request post-state authorization."""
        if receipt.status == "committed" and receipt.task_id == str(task_id) and receipt.assignment_id:
            return UUID(receipt.assignment_id)
        return None

    @staticmethod
    def recover(
        receipt: TaskCommandReceipt, digest: str, facts: TaskAuthorityFacts,
        task: WorkstreamTask, assignment: TaskAssignment | None, *, reserved: bool,
    ) -> TaskResponse | TaskWithAssignmentResponse | None:
        """Call only after fresh exact AUTH; a receipt never supplies authority."""
        if receipt.request_digest != digest or receipt.task_id != task.id:
            raise TaskReplayConflict("idempotency_mismatch")
        if receipt.status == "pending":
            if reserved:
                return None
            raise TaskReplayConflict("idempotency_pending")
        if (
            assignment is None or assignment.status != "active"
            or receipt.assignment_id != assignment.id
            or receipt.contributor_id != assignment.contributor_id
            or task.assigned_to != assignment.contributor_id
            or receipt.locked_context_hash != facts.locked_context_hash
        ):
            raise TaskReplayConflict("task_replay_state_changed")
        response_type = TaskWithAssignmentResponse if facts.operation is TaskAuthorityOperation.CLAIM else TaskResponse
        try:
            response = response_type.model_validate(receipt.response)
        except ValidationError as exc:
            raise TaskReplayConflict("task_replay_state_changed") from exc
        captured_task = response.task if isinstance(response, TaskWithAssignmentResponse) else response
        if (
            captured_task.id != task.id or captured_task.project_id != task.project_id
            or captured_task.status != task.status or captured_task.assigned_to is not None
            or (isinstance(response, TaskWithAssignmentResponse) and (
                response.assignment.id != assignment.id
                or response.assignment.task_id != task.id
                or response.assignment.contributor_id != assignment.contributor_id
            ))
        ):
            raise TaskReplayConflict("task_replay_state_changed")
        return response

    @staticmethod
    def complete(
        receipt: TaskCommandReceipt, assignment: TaskAssignment, facts: TaskAuthorityFacts,
        response: TaskResponse | TaskWithAssignmentResponse,
    ) -> None:
        """Stage the result alongside the assignment, transition and evidence."""
        if receipt.status != "pending":
            raise RuntimeError("task command receipt already completed")
        receipt.assignment_id = assignment.id
        receipt.contributor_id = assignment.contributor_id
        receipt.locked_context_hash = facts.locked_context_hash
        receipt.response = response.model_dump(mode="json")
        receipt.status = "committed"
        receipt.committed_at = datetime.now(UTC)
