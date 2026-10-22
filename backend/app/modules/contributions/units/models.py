"""Immutable creation evidence for project-scoped compensation units."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint, Uuid, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectCompensationUnitCreationEvent(Base):
    """Immutable recoverable truth for the one creation of a project unit."""

    __tablename__ = "project_compensation_unit_creation_events"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        ForeignKeyConstraint(
            ["project_id", "instrument_type", "unit_code"],
            [
                "project_compensation_units.project_id",
                "project_compensation_units.instrument_type",
                "project_compensation_units.unit_code",
            ],
            name="fk_project_compensation_unit_creation_unit",
        ),
        UniqueConstraint("operation_id", name="uq_project_compensation_unit_creation_operation"),
        UniqueConstraint(
            "project_id", "instrument_type", "unit_code",
            name="uq_project_compensation_unit_creation_unit",
        ),
        CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_digest"),
        CheckConstraint("instrument_type = 'project_points'", name="instrument_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_project_compensation_unit_creation_actor"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_project_compensation_unit_creation_project"),
        nullable=False,
    )
    instrument_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
