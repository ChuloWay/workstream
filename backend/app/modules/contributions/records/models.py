"""Immutable contribution lineage awaiting authorized atomic composition."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContributionRecord(Base):
    """Exact recognized source metadata; this declaration grants no authority."""

    __tablename__ = "contribution_records"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        CheckConstraint(
            "(contribution_type='completed_review' and source_review_id is not null "
            "and source_review_lease_id is not null and source_final_acceptance_id is null "
            "and source_task_assignment_id is null) or "
            "(contribution_type='accepted_submission' and source_review_id is null "
            "and source_review_lease_id is null and source_final_acceptance_id is not null "
            "and source_task_assignment_id is not null)",
            name="source_shape",
        ),
        CheckConstraint("artifact_hash ~ '^sha256:[0-9a-f]{64}$'", name="artifact_hash"),
        UniqueConstraint("source_review_id"),
        UniqueConstraint("source_final_acceptance_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("workstream_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    submission_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("submissions.id", ondelete="RESTRICT"), nullable=False
    )
    contribution_type: Mapped[str] = mapped_column(String(32), nullable=False)
    contributor_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    source_review_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("reviews.id", ondelete="RESTRICT")
    )
    source_review_lease_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("review_leases.id", ondelete="RESTRICT")
    )
    source_final_acceptance_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("final_acceptances.id", ondelete="RESTRICT")
    )
    source_task_assignment_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("task_assignments.id", ondelete="RESTRICT")
    )
    artifact_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    contribution_policy_version_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("contribution_policy_versions.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
