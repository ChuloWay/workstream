"""TASK-owned aggregate success custody over canonical per-Task command receipts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class TaskBatchTransitionReceipt(Base):
    """One actor/action/key root, committed only with every native batch member."""

    __tablename__ = "task_batch_transition_receipts"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        UniqueConstraint(
            "actor_profile_id",
            "action_id",
            "idempotency_key",
            name="uq_task_batch_transition_namespace",
        ),
        UniqueConstraint("id", "project_id", "batch_id", name="uq_task_batch_transition_parent"),
        ForeignKeyConstraint(
            ["batch_id", "project_id"],
            ["task_import_batches.id", "task_import_batches.project_id"],
            name="fk_task_batch_transition_batch",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["actor_identity_links.id", "actor_identity_links.actor_profile_id"],
            name="fk_task_batch_transition_actor_link",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "action_id in ('project.task.screen','project.task.release')", name="action"
        ),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and manifest_digest ~ '^sha256:[0-9a-f]{64}$' "
            "and membership_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="digests",
        ),
        CheckConstraint("row_count between 1 and 500", name="bounds"),
        CheckConstraint("reason is null or length(reason)<=1000", name="reason_bounds"),
        CheckConstraint(
            "action_id<>'project.task.release' or (reason is not null and length(btrim(reason))>0)",
            name="release_reason",
        ),
        CheckConstraint(
            "(status='pending' and response is null and committed_at is null) or "
            "(status='committed' and response is not null and jsonb_typeof(response)='object' "
            "and committed_at is not null)",
            name="state_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED")
    )
    identity_link_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    action_id: Mapped[str] = mapped_column(String(160))
    idempotency_key: Mapped[UUID] = mapped_column(Uuid())
    request_digest: Mapped[str] = mapped_column(String(71))
    reason: Mapped[str | None] = mapped_column(Text)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    batch_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    manifest_digest: Mapped[str] = mapped_column(String(71))
    membership_digest: Mapped[str] = mapped_column(String(71))
    row_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    response: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskBatchTransitionMember(Base):
    """Immutable original row linked to its root-bound canonical success and AUTH."""

    __tablename__ = "task_batch_transition_members"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        UniqueConstraint(
            "transition_receipt_id", "row_index", name="uq_task_batch_transition_member_row"
        ),
        UniqueConstraint(
            "transition_receipt_id",
            "native_member_id",
            name="uq_task_batch_transition_member_native",
        ),
        UniqueConstraint(
            "transition_receipt_id", "task_id", name="uq_task_batch_transition_member_task"
        ),
        UniqueConstraint("task_command_receipt_id", name="uq_task_batch_transition_member_command"),
        ForeignKeyConstraint(
            ["transition_receipt_id", "project_id", "batch_id"],
            [
                "task_batch_transition_receipts.id",
                "task_batch_transition_receipts.project_id",
                "task_batch_transition_receipts.batch_id",
            ],
            name="fk_task_batch_transition_member_parent",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["task_id", "project_id"],
            ["workstream_tasks.id", "workstream_tasks.project_id"],
            name="fk_task_batch_transition_member_task",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("row_index between 0 and 499", name="row_index"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    transition_receipt_id: Mapped[UUID] = mapped_column(Uuid())
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    batch_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    native_member_id: Mapped[str] = mapped_column(
        ForeignKey(
            "task_import_batch_members.id",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        )
    )
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    row_index: Mapped[int] = mapped_column(Integer)
    task_idempotency_key: Mapped[UUID] = mapped_column(Uuid())
    task_command_receipt_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "task_command_receipts.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"
        )
    )
    authorization_decision_id: Mapped[str] = mapped_column(
        ForeignKey("audit_events.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
