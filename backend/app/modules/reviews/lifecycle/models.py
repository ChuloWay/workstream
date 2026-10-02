"""Disabled shared lifecycle genesis awaiting authorized transition ownership."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JointLifecycleReleaseControl(Base):
    """Single immutable genesis; no usable lifecycle generation is seeded."""

    __tablename__ = "joint_lifecycle_release_control"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        CheckConstraint("singleton", name="singleton_true"),
        UniqueConstraint("singleton"),
        CheckConstraint("phase in ('disabled','shadow','live','draining')", name="phase"),
        CheckConstraint("generation >= 0", name="generation_nonnegative"),
        CheckConstraint("generation <> 0 or phase='disabled'", name="genesis_disabled"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    singleton: Mapped[bool] = mapped_column(Boolean, nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
