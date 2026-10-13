"""One caller-root SCREEN/RELEASE over complete immutable native batch membership."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.tasks.api.authorization import TaskAuthorityDecision, TaskAuthorityOperation
from app.modules.tasks.api.task_batch_transition import (
    TaskBatchTransitionRequest, TaskBatchTransitionResponse, TaskBatchTransitionResult,
)
from app.modules.tasks.api.task_import_membership import TaskImportBatchError, TaskImportMemberIdentity
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands, TaskTransitionPreparation
from app.modules.tasks.command_replay import TaskReplayConflict
from app.modules.tasks.schemas import TaskResponse
from app.modules.tasks.service import TaskValidationError
from app.modules.tasks.task_batch_transition.models import TaskBatchTransitionMember, TaskBatchTransitionReceipt
from app.modules.tasks.task_import_membership import TaskImportMembership, TaskImportMembershipSnapshot


@dataclass(frozen=True, slots=True)
class _PreparedMember:
    native: TaskImportMemberIdentity
    task: TaskTransitionPreparation
    retained: TaskBatchTransitionMember | None


def _membership_digest(snapshot: TaskImportMembershipSnapshot) -> str:
    """Seal the actual ordered native member and original CREATE identities."""
    return canonical_json_hash({"members": [{
        "member_id": str(row.member_id), "task_id": str(row.task_id), "row_index": row.row_index,
        "external_task_id": row.external_task_id, "row_digest": row.row_digest,
        "create_idempotency_key": str(row.create_idempotency_key),
        "task_command_receipt_id": str(row.task_command_receipt_id),
        "authorization_decision_id": str(row.authorization_decision_id),
    } for row in snapshot.members]})


class TaskBatchTransitionCommands:
    """Compose canonical participants; never infer membership from a mutable Task."""

    def __init__(
        self, session: AsyncSession, *, actor_profile_id: UUID, identity_link_id: UUID,
        tasks: AuthorizedTaskCommands,
    ) -> None:
        self._session, self._actor_id, self._link_id = session, actor_profile_id, identity_link_id
        self._tasks = tasks
        self._membership = TaskImportMembership(session)

    async def screen(
        self, project_id: UUID, batch_id: UUID, reason: str | None, *, idempotency_key: UUID,
    ) -> TaskBatchTransitionResponse:
        """Screen every native member, preserving the normal guide-locking owner."""
        return await self._transition(project_id, batch_id, TaskAuthorityOperation.SCREEN, reason, idempotency_key)

    async def release(
        self, project_id: UUID, batch_id: UUID, reason: str | None, *, idempotency_key: UUID,
    ) -> TaskBatchTransitionResponse:
        """Release every native member with its normal reason and locked prerequisites."""
        return await self._transition(project_id, batch_id, TaskAuthorityOperation.RELEASE, reason, idempotency_key)

    async def _reserve(
        self, snapshot: TaskImportMembershipSnapshot, operation: TaskAuthorityOperation,
        reason: str | None, key: UUID, digest: str,
    ) -> tuple[TaskBatchTransitionReceipt, bool]:
        """Serialize the caller namespace without updating an immutable success row."""
        identifier = new_record_id()
        await self._session.execute(insert(TaskBatchTransitionReceipt).values(
            id=identifier, actor_profile_id=str(self._actor_id), identity_link_id=str(self._link_id),
            action_id=operation.value, idempotency_key=key, request_digest=digest, reason=reason,
            project_id=str(snapshot.creation.project_id), batch_id=str(snapshot.creation.batch_id),
            manifest_digest=snapshot.manifest_digest, membership_digest=_membership_digest(snapshot),
            row_count=len(snapshot.members), status="pending",
        ).on_conflict_do_nothing(constraint="uq_task_batch_transition_namespace"))
        receipt = await self._session.scalar(select(TaskBatchTransitionReceipt).where(
            TaskBatchTransitionReceipt.actor_profile_id == str(self._actor_id),
            TaskBatchTransitionReceipt.action_id == operation.value,
            TaskBatchTransitionReceipt.idempotency_key == key,
        ).with_for_update().execution_options(populate_existing=True))
        if receipt is None:
            raise RuntimeError("task batch transition reservation disappeared")
        return receipt, receipt.id == identifier

    async def _prepare(
        self, snapshot: TaskImportMembershipSnapshot, receipt: TaskBatchTransitionReceipt,
        operation: TaskAuthorityOperation, reason: str | None,
    ) -> tuple[list[_PreparedMember], int]:
        """Acquire every actual Task/assignment in UUID order before the first AUTH."""
        links = (await self._session.scalars(select(TaskBatchTransitionMember).where(
            TaskBatchTransitionMember.transition_receipt_id == receipt.id,
        ).order_by(TaskBatchTransitionMember.row_index))).all()
        by_member = {row.native_member_id: row for row in links}
        prepared = []
        for native in sorted(snapshot.members, key=lambda row: row.task_id.int):
            retained = by_member.get(str(native.member_id))
            key = retained.task_idempotency_key if retained is not None else uuid4()
            task = await self._tasks.prepare_transition(
                native.task_id, operation, reason, idempotency_key=key,
                project_id=snapshot.creation.project_id, batch_transition_receipt_id=receipt.id,
            )
            prepared.append(_PreparedMember(native, task, retained))
        return prepared, len(links)

    @staticmethod
    def _validate_custody(
        snapshot: TaskImportMembershipSnapshot, receipt: TaskBatchTransitionReceipt,
        rows: list[_PreparedMember], digest: str, reason: str | None,
        link_count: int, *, reserved: bool,
    ) -> None:
        """Compare original custody only after every member has fresh authority."""
        if receipt.request_digest != digest or receipt.reason != reason:
            raise TaskReplayConflict("idempotency_mismatch")
        if (receipt.project_id != str(snapshot.creation.project_id)
                or receipt.batch_id != str(snapshot.creation.batch_id)
                or receipt.manifest_digest != snapshot.manifest_digest
                or receipt.membership_digest != _membership_digest(snapshot)
                or receipt.row_count != len(rows)):
            raise TaskImportBatchError("task_batch_transition_custody_invalid", 409)
        if receipt.status == "pending":
            if not reserved:
                raise TaskReplayConflict("idempotency_pending")
            if link_count or any(row.retained is not None or not row.task.reserved for row in rows):
                raise TaskImportBatchError("task_batch_transition_custody_invalid", 409)
            return
        if receipt.status != "committed" or link_count != len(rows):
            raise TaskImportBatchError("task_batch_transition_custody_invalid", 409)
        for row in rows:
            link, canonical = row.retained, row.task.receipt
            if (link is None or row.task.reserved
                    or link.transition_receipt_id != receipt.id
                    or link.project_id != receipt.project_id or link.batch_id != receipt.batch_id
                    or link.task_id != str(row.native.task_id) or link.row_index != row.native.row_index
                    or link.native_member_id != str(row.native.member_id)
                    or link.task_command_receipt_id != canonical.id
                    or link.task_idempotency_key != canonical.idempotency_key
                    or canonical.status != "committed" or canonical.action_id != receipt.action_id
                    or canonical.actor_profile_id != receipt.actor_profile_id
                    or canonical.batch_transition_receipt_id != receipt.id):
                raise TaskImportBatchError("task_batch_transition_custody_invalid", 409)

    @staticmethod
    def _result(row: _PreparedMember, response: TaskResponse) -> TaskBatchTransitionResult:
        """Project actual canonical receipt facts instead of a second state snapshot."""
        canonical = row.task.receipt
        if (canonical.response != response.model_dump(mode="json")
                or response.id != str(row.native.task_id)
                or canonical.locked_context_hash is None):
            raise TaskImportBatchError("task_batch_transition_custody_invalid", 409)
        return TaskBatchTransitionResult(
            task_id=row.native.task_id, row_index=row.native.row_index, status=response.status,
            locked_guide_version=response.locked_guide_version,
            locked_contribution_policy_version_id=response.locked_contribution_policy_version_id,
            locked_context_hash=canonical.locked_context_hash,
        )

    async def _transition(
        self, project_id: UUID, batch_id: UUID, operation: TaskAuthorityOperation,
        reason: str | None, key: UUID,
    ) -> TaskBatchTransitionResponse:
        if not all(isinstance(value, UUID) for value in (project_id, batch_id, key)):
            raise ValueError("task batch transition selectors are invalid")
        reason = TaskBatchTransitionRequest(reason=reason).reason
        if operation is TaskAuthorityOperation.RELEASE and (not reason or not reason.strip()):
            raise TaskValidationError("release decision reason is required")
        digest = canonical_json_hash({"project_id": str(project_id), "batch_id": str(batch_id),
                                      "operation": operation.value, "reason": reason})
        async with self._session.begin():
            snapshot = await self._membership.prepare(project_id, batch_id)
            receipt, reserved = await self._reserve(snapshot, operation, reason, key, digest)
            rows, link_count = await self._prepare(snapshot, receipt, operation, reason)
            decisions: list[TaskAuthorityDecision] = []
            for row in rows:
                decisions.append(await self._tasks.authorize_transition(row.task))
            self._validate_custody(snapshot, receipt, rows, digest, reason, link_count, reserved=reserved)
            if (any(row.task.facts.actor_profile_id != self._actor_id for row in rows)
                    or any(decision.identity_link_id != self._link_id for decision in decisions)):
                raise TaskImportBatchError("task_batch_transition_custody_invalid", 409)
            screen_context = (
                await self._tasks.prepare_screen_context(project_id)
                if reserved and operation is TaskAuthorityOperation.SCREEN
                else None
            )
            results = []
            for row, decision in zip(rows, decisions, strict=True):
                response = await self._tasks.stage_transition(
                    row.task,
                    decision,
                    screen_context=screen_context,
                )
                results.append(self._result(row, response))
                if reserved:
                    self._session.add(TaskBatchTransitionMember(
                        id=new_record_id(), transition_receipt_id=receipt.id,
                        project_id=str(project_id), batch_id=str(batch_id),
                        native_member_id=str(row.native.member_id), task_id=str(row.native.task_id),
                        row_index=row.native.row_index, task_idempotency_key=row.task.receipt.idempotency_key,
                        task_command_receipt_id=row.task.receipt.id,
                        authorization_decision_id=str(decision.decision_id),
                    ))
            response = TaskBatchTransitionResponse(
                project_id=project_id, batch_id=batch_id,
                operation="screen" if operation is TaskAuthorityOperation.SCREEN else "release",
                row_count=len(rows), tasks=tuple(sorted(results, key=lambda row: row.row_index)),
            )
            encoded = response.model_dump(mode="json")
            if reserved:
                receipt.response, receipt.status, receipt.committed_at = encoded, "committed", datetime.now(UTC)
                await self._session.flush()
            elif receipt.response != encoded:
                raise TaskImportBatchError("task_batch_transition_custody_invalid", 409)
            # Validate/detach before root commit; serialization failure rolls back
            # every Task, receipt, lifecycle event and successful AUTH decision.
            response = TaskBatchTransitionResponse.model_validate_json(response.model_dump_json())
        return response
