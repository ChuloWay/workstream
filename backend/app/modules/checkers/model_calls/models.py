"""SQLAlchemy rows for immutable profiles, lifetime budgets and paid call slots."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text

from app.db.base import Base


_UUID7 = "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128"
_SHA = "^sha256:[0-9a-f]{64}$"


class CheckerModelProfile(Base):
    """One immutable Operator-authorized provider/pricing profile."""

    __tablename__ = "checker_model_profiles"
    __table_args__ = (
        CheckConstraint(_UUID7, name="id_uuid7"),
        UniqueConstraint("project_id", "profile_version", name="checker_model_profiles_version"),
        UniqueConstraint(
            "id",
            "profile_version",
            "profile_digest",
            name="checker_model_profiles_identity",
        ),
        UniqueConstraint("profile_digest", name="checker_model_profiles_digest"),
        UniqueConstraint("operation_id", name="checker_model_profiles_operation"),
        UniqueConstraint("authorization_evidence_id", name="checker_model_profiles_authority"),
        CheckConstraint(
            f"profile_digest ~ '{_SHA}' and registry_entry_digest ~ '{_SHA}' and "
            f"pricing_policy_digest ~ '{_SHA}'",
            name="digests",
        ),
        CheckConstraint(
            "profile_version > 0 and pricing_policy_version > 0 and call_slots = 1",
            name="versions",
        ),
        CheckConstraint(
            "provider = 'openai_responses' and api = 'responses.v1'",
            name="provider_api",
        ),
        CheckConstraint(
            "maximum_request_bytes between 1 and 1048576 and "
            "maximum_output_bytes between 1 and 1048576 and "
            "maximum_response_bytes between 1 and 1048576 and "
            "maximum_response_bytes >= 6 * maximum_output_bytes + 4096 and "
            "maximum_input_tokens between 1 and 10000000 and "
            "maximum_output_tokens between 1 and 10000000 and "
            "deadline_ms between 100 and 3600000",
            name="bounds",
        ),
        CheckConstraint(
            "uncached_input_rate >= 0 and cached_input_rate >= 0 and "
            "output_rate >= 0 and "
            "greatest(uncached_input_rate,cached_input_rate,output_rate) > 0",
            name="pricing",
        ),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    registry_entry_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("external_checker_registry_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    registry_entry_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    provider: Mapped[str] = mapped_column(String(160), nullable=False)
    api: Mapped[str] = mapped_column(String(160), nullable=False)
    model_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    generation_settings: Mapped[dict] = mapped_column(JSONB(), nullable=False)
    maximum_request_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_output_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_response_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    deadline_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    call_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    pricing_policy_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    pricing_policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    pricing_policy_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    uncached_input_rate: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cached_input_rate: Mapped[int] = mapped_column(BigInteger, nullable=False)
    output_rate: Mapped[int] = mapped_column(BigInteger, nullable=False)
    operation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    actor_profile_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    authorization_evidence_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CheckerModelBudgetAccount(Base):
    """One project lifetime account; configuration versions never reset counters."""

    __tablename__ = "checker_model_budget_accounts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["current_configuration_id", "project_id"],
            [
                "checker_model_budget_configurations.id",
                "checker_model_budget_configurations.project_id",
            ],
            ondelete="RESTRICT",
            name="configuration_identity",
        ),
        CheckConstraint(
            "lifetime_reserved_nanodollars >= 0 and lifetime_settled_nanodollars >= 0",
            name="nonnegative_totals",
        ),
    )

    project_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("projects.id", ondelete="RESTRICT"), primary_key=True
    )
    current_configuration_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), nullable=False, unique=True
    )
    lifetime_reserved_nanodollars: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    lifetime_settled_nanodollars: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class CheckerModelBudgetConfiguration(Base):
    """Immutable Operator-authorized adjustment of one project's lifetime ceiling."""

    __tablename__ = "checker_model_budget_configurations"
    __table_args__ = (
        CheckConstraint(_UUID7, name="id_uuid7"),
        UniqueConstraint(
            "project_id",
            "configuration_version",
            name="checker_model_budget_configurations_version",
        ),
        UniqueConstraint(
            "id",
            "project_id",
            "configuration_version",
            "configuration_digest",
            name="checker_model_budget_configurations_identity",
        ),
        UniqueConstraint(
            "id",
            "configuration_version",
            "configuration_digest",
            name="checker_model_budget_configurations_attempt_identity",
        ),
        UniqueConstraint("configuration_digest", name="checker_model_budget_configurations_digest"),
        UniqueConstraint("operation_id", name="checker_model_budget_configurations_operation"),
        UniqueConstraint(
            "authorization_evidence_id",
            name="checker_model_budget_configurations_authority",
        ),
        CheckConstraint(f"configuration_digest ~ '{_SHA}'", name="digest"),
        CheckConstraint(
            "configuration_version > 0 and lifetime_limit_nanodollars > 0",
            name="positive_values",
        ),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    configuration_version: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    lifetime_limit_nanodollars: Mapped[int] = mapped_column(BigInteger, nullable=False)
    operation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    actor_profile_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    authorization_evidence_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CheckerModelCallSlot(Base):
    """Submission-stable paid effect identity independent of run generation and lease."""

    __tablename__ = "checker_model_call_slots"
    __table_args__ = (
        CheckConstraint(_UUID7, name="id_uuid7"),
        UniqueConstraint(
            "project_id",
            "assignment_id",
            "submission_id",
            "submission_version",
            "requirement_id",
            "registry_entry_digest",
            "configuration_sha256",
            "profile_id",
            "profile_version",
            "profile_digest",
            "slot_index",
            name="checker_model_call_slots_stable_identity",
        ),
        ForeignKeyConstraint(
            ["profile_id", "profile_version", "profile_digest"],
            [
                "checker_model_profiles.id",
                "checker_model_profiles.profile_version",
                "checker_model_profiles.profile_digest",
            ],
            name="profile_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"registry_entry_digest ~ '{_SHA}' and configuration_sha256 ~ '{_SHA}' and "
            f"profile_digest ~ '{_SHA}' and first_request_sha256 ~ '{_SHA}'",
            name="digests",
        ),
        CheckConstraint(
            "submission_version > 0 and profile_version > 0 and slot_index = 0",
            name="versions",
        ),
        CheckConstraint(
            "requirement_id ~ '^[a-z][a-z0-9_.-]{0,99}$'",
            name="requirement_id",
        ),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("workstream_tasks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assignment_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("task_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    submission_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("submissions.id", ondelete="RESTRICT"), nullable=False
    )
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    requirement_id: Mapped[str] = mapped_column(String(100), nullable=False)
    registry_entry_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    configuration_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    profile_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_request_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CheckerModelCallAttempt(Base):
    """One server-numbered provider effect attempt beneath a stable paid slot."""

    __tablename__ = "checker_model_call_attempts"
    __table_args__ = (
        CheckConstraint(_UUID7, name="id_uuid7"),
        UniqueConstraint("slot_id", "attempt_number", name="checker_model_call_attempts_number"),
        UniqueConstraint(
            "internal_call_request_id", name="checker_model_call_attempts_internal_request"
        ),
        UniqueConstraint(
            "prepared_authorization_evidence_id",
            name="checker_model_call_attempts_prepare_authority",
        ),
        ForeignKeyConstraint(
            [
                "budget_configuration_id",
                "budget_configuration_version",
                "budget_configuration_digest",
            ],
            [
                "checker_model_budget_configurations.id",
                "checker_model_budget_configurations.configuration_version",
                "checker_model_budget_configurations.configuration_digest",
            ],
            ondelete="RESTRICT",
            name="budget_identity",
        ),
        CheckConstraint(
            "state in ('prepared','dispatching','uncertain','completed','known_failed','known_no_effect')",
            name="state",
        ),
        CheckConstraint(f"request_sha256 ~ '{_SHA}'", name="request_digest"),
        CheckConstraint(
            "attempt_number > 0 and (reserved_nanodollars is null or reserved_nanodollars > 0) "
            "and (settled_nanodollars is null or settled_nanodollars >= 0)",
            name="amounts",
        ),
        CheckConstraint(
            "input_tokens is null or (input_tokens >= 0 and cached_input_tokens between 0 and input_tokens "
            "and output_tokens >= 0 and reasoning_tokens between 0 and output_tokens)",
            name="usage",
        ),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    slot_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("checker_model_call_slots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    internal_call_request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    parent_attempt_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("checker_model_call_attempts.id", ondelete="RESTRICT"),
    )
    request_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    prepared_authorization_evidence_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False
    )
    request_binding_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("artifact_bindings.id", ondelete="RESTRICT")
    )
    request_content_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("artifact_contents.id", ondelete="RESTRICT")
    )
    request_put_attempt_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("artifact_put_attempts.id", ondelete="RESTRICT")
    )
    request_verification_receipt_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("artifact_verification_receipts.id", ondelete="RESTRICT"),
    )
    request_content_sha256: Mapped[str | None] = mapped_column(String(71))
    request_byte_count: Mapped[int | None] = mapped_column(Integer)
    budget_configuration_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    budget_configuration_version: Mapped[int | None] = mapped_column(Integer)
    budget_configuration_digest: Mapped[str | None] = mapped_column(String(71))
    reserved_nanodollars: Mapped[int | None] = mapped_column(BigInteger)
    dispatch_authorization_evidence_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), unique=True
    )
    provider_response_id: Mapped[str | None] = mapped_column(String(256))
    response_binding_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("artifact_bindings.id", ondelete="RESTRICT")
    )
    response_content_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("artifact_contents.id", ondelete="RESTRICT")
    )
    response_put_attempt_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("artifact_put_attempts.id", ondelete="RESTRICT")
    )
    response_verification_receipt_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("artifact_verification_receipts.id", ondelete="RESTRICT"),
    )
    response_content_sha256: Mapped[str | None] = mapped_column(String(71))
    response_byte_count: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    settled_nanodollars: Mapped[int | None] = mapped_column(BigInteger)
    settlement_authorization_evidence_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), unique=True
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    no_effect_proof_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    no_effect_proof_digest: Mapped[str | None] = mapped_column(String(71))
    no_effect_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_authorization_evidence_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), unique=True
    )
    uncertainty_digest: Mapped[str | None] = mapped_column(String(71))
    observation_authorization_evidence_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), unique=True
    )
    prepared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CheckerModelCallRecovery(Base):
    """One fresh current-run recovery attachment to an existing paid effect."""

    __tablename__ = "checker_model_call_recoveries"
    __table_args__ = (
        CheckConstraint(_UUID7, name="id_uuid7"),
        UniqueConstraint(
            "attempt_id",
            "checker_run_id",
            "worker_lease_id",
            "worker_lease_generation",
            name="checker_model_call_recoveries_attachment",
        ),
        UniqueConstraint(
            "authorization_evidence_id", name="checker_model_call_recoveries_authority"
        ),
        CheckConstraint("worker_lease_generation > 0", name="lease_generation"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("checker_model_call_attempts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    checker_run_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("checker_runs.id", ondelete="RESTRICT"), nullable=False
    )
    worker_lease_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    worker_lease_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    authorization_evidence_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


__all__ = (
    "CheckerModelBudgetAccount",
    "CheckerModelBudgetConfiguration",
    "CheckerModelCallAttempt",
    "CheckerModelCallRecovery",
    "CheckerModelCallSlot",
    "CheckerModelProfile",
)
