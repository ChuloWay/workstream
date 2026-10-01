"""Detached immutable TASK source evidence for future post-submit routing."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class TaskPostSubmitRoutingManifest(Base):
    """One immutable route-neutral source fact; no routing authority or currentness."""

    __tablename__ = "task_post_submit_routing_manifests"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        CheckConstraint("submission_version > 0", name="submission_version_positive"),
        CheckConstraint("evaluation_generation > 0", name="evaluation_generation_positive"),
        CheckConstraint("byte_count >= 0", name="byte_count_nonnegative"),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "result_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "content_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "semantic_manifest_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="sha256_shapes",
        ),
        ForeignKeyConstraint(
            ["task_id", "project_id"],
            ["workstream_tasks.id", "workstream_tasks.project_id"],
            name="fk_task_routing_manifest_task_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["submission_id", "task_id", "submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
            name="fk_task_routing_manifest_submission_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["assignment_id", "task_id", "contributor_id"],
            ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"],
            name="fk_task_routing_manifest_assignment_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["contribution_policy_version_id", "project_id"],
            ["contribution_policy_versions.id", "contribution_policy_versions.project_id"],
            name="fk_task_routing_manifest_contribution_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["checker_run_id", "task_id", "submission_id"],
            ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"],
            name="fk_task_routing_manifest_checker_source",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "submission_id",
            "checker_run_id",
            "result_digest",
            name="uq_task_routing_manifest_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
    project_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    task_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    submission_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    assignment_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    contributor_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    contribution_policy_version_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    checker_run_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    evaluation_request_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    evaluation_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    result_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    result_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    completion_event_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "outbox_events.event_id",
            name="fk_task_routing_manifest_completion_event",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    execute_evidence_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "audit_events.id",
            name="fk_task_routing_manifest_execute_evidence",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    finalize_evidence_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "audit_events.id",
            name="fk_task_routing_manifest_finalize_evidence",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    replica_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "artifact_replicas.id",
            name="fk_task_routing_manifest_replica",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    content_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    semantic_manifest_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
