"""Retain an immutable delivery deadline for durable revision timeout requests."""

from alembic import op
from sqlalchemy import text

revision = "0044_outbox_not_before"
down_revision = "0043_revision_preparation"
branch_labels = None
depends_on = None


def upgrade():
    """Extend canonical append custody without rewriting existing events."""
    op.execute("ALTER TABLE public.outbox_events ADD COLUMN not_before_at timestamptz")
    op.execute("""ALTER TABLE public.outbox_events
        ADD CONSTRAINT ck_outbox_events_not_before_delivery CHECK (
          not_before_at IS NULL OR (isfinite(not_before_at)
            AND (next_attempt_at IS NULL OR next_attempt_at >= not_before_at)
            AND (claimed_at IS NULL OR claimed_at >= not_before_at)))""")
    body = op.get_bind().execute(text(
        "SELECT pg_get_functiondef('public.guard_outbox_event()'::regprocedure)"
    )).scalar_one()
    for old, new in (
        ("new.next_attempt_at := event_time;",
         "new.next_attempt_at := greatest(event_time, new.not_before_at);"),
        ("new.payload, new.payload_digest, new.occurred_at)",
         "new.payload, new.payload_digest, new.occurred_at, new.not_before_at)"),
        ("old.payload, old.payload_digest, old.occurred_at)",
         "old.payload, old.payload_digest, old.occurred_at, old.not_before_at)"),
    ):
        if body.count(old) != 1:
            raise RuntimeError("outbox not-before custody function shape changed")
        body = body.replace(old, new)
    op.execute(body)


def downgrade():
    """Dropping retained delivery intent would make future jobs run early."""
    raise RuntimeError("outbox not-before custody cannot be downgraded")
