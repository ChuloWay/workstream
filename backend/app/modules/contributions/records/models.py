"""Immutable contribution lineage awaiting authorized atomic composition."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, text
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


class ContributionExportMembership(Base):
    """One bounded export selection; it grants no authority on later reads."""

    __tablename__ = "contribution_export_memberships"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
                        name="id_uuid7"),
        CheckConstraint("query_digest ~ '^sha256:[0-9a-f]{64}$'", name="query_digest"),
        CheckConstraint("expires_at = exported_at + interval '15 minutes'", name="expiry"),
        CheckConstraint("member_count between 0 and 100000", name="member_count"),
        CheckConstraint("audience in ('self','project') and (audience != 'project' or project_id is not null)",
                        name="audience"),
        CheckConstraint("output_format in ('json','csv')", name="output_format"),
        CheckConstraint("page_size between 1 and 1000", name="page_size"),
        CheckConstraint("contribution_type is null or contribution_type in ('accepted_submission','completed_review')",
                        name="contribution_type"),
        CheckConstraint("recorded_from is null or recorded_before is null or recorded_from < recorded_before",
                        name="recorded_interval"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    actor_profile_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False,
    )
    audience: Mapped[str] = mapped_column(String(16), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("projects.id", ondelete="RESTRICT"),
    )
    output_format: Mapped[str] = mapped_column(String(4), nullable=False)
    page_size: Mapped[int] = mapped_column(Integer, nullable=False)
    contribution_type: Mapped[str | None] = mapped_column(String(32))
    recorded_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sealed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    query_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ContributionExportMember(Base):
    """Immutable originally visible identity and its source ordering timestamp."""

    __tablename__ = "contribution_export_members"
    export_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("contribution_export_memberships.id", ondelete="CASCADE"), primary_key=True,
    )
    contribution_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("contribution_records.id", ondelete="RESTRICT"), primary_key=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
