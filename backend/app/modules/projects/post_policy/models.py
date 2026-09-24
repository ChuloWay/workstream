"""Append-only evidence for the one canonical post-policy operation family."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, JSON,
    String, UniqueConstraint, Uuid, text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class PostPolicyOperation(Base):
    """One projection, approval or correction bound to exact immutable output."""

    __tablename__ = "project_post_policy_operations"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(operation_id), 6) >> 4) = 7 and (get_byte(uuid_send(operation_id), 8) & 192) = 128", name="operation_id_uuid7"),
        ForeignKeyConstraint(
            ["compilation_id", "project_id", "guide_id"],
            ["project_guide_compilations.id", "project_guide_compilations.project_id", "project_guide_compilations.guide_id"],
            name="fk_post_policy_operation_compilation_scope",
        ),
        ForeignKeyConstraint(
            ["policy_id", "project_id", "guide_id"],
            ["checker_policies.id", "checker_policies.project_id", "checker_policies.guide_id"],
            name="fk_post_policy_operation_policy_scope",
            deferrable=True, initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["actor_identity_links.id", "actor_identity_links.actor_profile_id"],
            name="fk_post_policy_operation_actor_link",
        ),
        UniqueConstraint("policy_id", "kind", name="uq_post_policy_operation_kind"),
        UniqueConstraint("actor_profile_id", "kind", "idempotency_key", name="uq_post_policy_operation_key"),
        UniqueConstraint("authorization_decision_event_id", name="uq_post_policy_operation_decision"),
        Index("uq_post_policy_projection_upstream", "upstream_approval_operation_id", unique=True,
              postgresql_where=text("kind = 'derive'")),
        CheckConstraint("kind in ('derive','approve','correction')", name="post_policy_operation_kind"),
        CheckConstraint(
            "target_digest ~ '^sha256:[0-9a-f]{64}$' and request_digest ~ '^sha256:[0-9a-f]{64}$' "
            "and resource_context_digest ~ '^sha256:[0-9a-f]{64}$' and output_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="post_policy_operation_hashes",
        ),
        CheckConstraint(
            "(kind = 'derive' and service_identity = 'workstream.project.setup' and admin_role_grant_id is null) "
            "or (kind != 'derive' and service_identity is null and admin_role_grant_id is not null)",
            name="post_policy_operation_actor_kind",
        ),
        CheckConstraint(
            "octet_length(target_json::text) <= 32768 and octet_length(receipt_json::text) <= 49152 "
            "and octet_length(request_json::text) <= 49152 and octet_length(resource_context_json::text) <= 16384",
            name="post_policy_operation_sizes",
        ),
    )

    operation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    guide_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    compilation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    policy_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    upstream_approval_operation_id: Mapped[UUID] = mapped_column(
        ForeignKey("project_guide_proposal_approvals.operation_id"), nullable=False,
    )
    target_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    target_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    resource_context_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    resource_context_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    receipt_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    actor_profile_id: Mapped[str] = mapped_column(ForeignKey("actor_profiles.id"), nullable=False)
    identity_link_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    admin_role_grant_id: Mapped[UUID | None] = mapped_column(ForeignKey("admin_role_grants.id"))
    service_identity: Mapped[str | None] = mapped_column(String(100))
    authorization_decision_event_id: Mapped[str] = mapped_column(ForeignKey("audit_events.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
