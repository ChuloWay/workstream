"""Immutable Review source facts, without a canonical decision writer."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Review(Base):
    """One complete immutable human judgment about an exact Submission."""

    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        UniqueConstraint("submission_id"),
        UniqueConstraint("review_lease_id"),
        UniqueConstraint("packet_manifest_id"),
        UniqueConstraint("predecessor_review_id"),
        CheckConstraint("decision in ('accept','needs_revision','reject')", name="decision"),
        CheckConstraint(
            "length(btrim(summary)) between 1 and 4000 and summary ~ '[^[:space:]]'", name="summary"
        ),
        CheckConstraint(
            "submission_version > 0 and locked_review_policy_generation > 0",
            name="positive_versions",
        ),
        CheckConstraint(
            "finding_count between 0 and 100 and blocking_finding_count between 0 and finding_count and resolution_count between 0 and 100",
            name="counts",
        ),
        CheckConstraint("length(btrim(locked_guide_version)) > 0", name="guide_version"),
        CheckConstraint("aggregate_digest ~ '^sha256:[0-9a-f]{64}$'", name="aggregate_digest"),
        CheckConstraint(
            "packet_manifest_digest ~ '^sha256:[0-9a-f]{64}$'", name="packet_manifest_digest"
        ),
        CheckConstraint("artifact_hash ~ '^sha256:[0-9a-f]{64}$'", name="artifact_hash"),
        CheckConstraint(
            "locked_review_policy_hash ~ '^sha256:[0-9a-f]{64}$'", name="locked_review_policy_hash"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("workstream_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    task_assignment_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("task_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    submission_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("submissions.id", ondelete="RESTRICT"), nullable=False
    )
    review_queue_entry_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("review_queue_entries.id", ondelete="RESTRICT"), nullable=False
    )
    review_lease_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("review_leases.id", ondelete="RESTRICT"), nullable=False
    )
    packet_manifest_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("review_packet_manifests.id", ondelete="RESTRICT"), nullable=False
    )
    reviewer_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    reviewer_contribution_policy_version_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("contribution_policy_versions.id", ondelete="RESTRICT"), nullable=False
    )
    locked_review_policy_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("review_policies.id", ondelete="RESTRICT"), nullable=False
    )
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    packet_manifest_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    locked_guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    locked_review_policy_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    locked_review_policy_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    predecessor_review_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("reviews.id", ondelete="RESTRICT"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str] = mapped_column(String(4000), nullable=False)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    blocking_finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_count: Mapped[int] = mapped_column(Integer, nullable=False)
    aggregate_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ReviewFinding(Base):
    """A retained ordered finding owned by one immutable Review."""

    __tablename__ = "review_findings"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        UniqueConstraint("review_id", "item_order"),
        CheckConstraint("item_order between 0 and 99", name="order"),
        CheckConstraint("finding_kind in ('blocking','advisory')", name="kind"),
        CheckConstraint(
            "length(btrim(area)) between 1 and 200 and area ~ '[^[:space:]]'", name="area"
        ),
        CheckConstraint(
            "length(btrim(issue)) between 1 and 4000 and issue ~ '[^[:space:]]'", name="issue"
        ),
        CheckConstraint(
            "length(btrim(required_fix)) between 1 and 4000 and required_fix ~ '[^[:space:]]'",
            name="required_fix",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    review_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("reviews.id", ondelete="RESTRICT"), nullable=False
    )
    item_order: Mapped[int] = mapped_column(Integer, nullable=False)
    finding_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    area: Mapped[str] = mapped_column(String(200), nullable=False)
    issue: Mapped[str] = mapped_column(String(4000), nullable=False)
    required_fix: Mapped[str] = mapped_column(String(4000), nullable=False)


class FindingResolution(Base):
    """An immutable later judgment; it never edits the prior finding."""

    __tablename__ = "finding_resolutions"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        UniqueConstraint("review_id", "item_order"),
        UniqueConstraint("review_id", "finding_id", name="uq_finding_resolution_source"),
        CheckConstraint("item_order between 0 and 99", name="order"),
        CheckConstraint("result in ('resolved','unresolved','not_applicable')", name="result"),
        CheckConstraint(
            "length(btrim(rationale)) between 1 and 4000 and rationale ~ '[^[:space:]]'",
            name="rationale",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    review_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("reviews.id", ondelete="RESTRICT"), nullable=False
    )
    finding_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("review_findings.id", ondelete="RESTRICT"), nullable=False
    )
    item_order: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(String(4000), nullable=False)


class ReviewDecisionRequest(Base):
    """Completed request association; no pending command or authority receipt."""

    __tablename__ = "review_decision_requests"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        UniqueConstraint("project_id", "reviewer_id", "idempotency_key"),
        UniqueConstraint("operation_id"),
        UniqueConstraint("review_id"),
        CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_digest"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    reviewer_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    review_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("reviews.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
