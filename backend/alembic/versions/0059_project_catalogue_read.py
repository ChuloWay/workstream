"""Admit exact system project catalogue decisions to the closed audit vocabulary."""

from alembic import op
from sqlalchemy import text


revision = "0059_project_catalogue_read"
down_revision = "0058_compensation_unit_create"
branch_labels = None
depends_on = None

_NAME = "ck_audit_events_authorization_action_evidence"
_ANCHOR = (
    "(((action_id)::text = 'contribution.read_self'::text) AND "
    "((permission_id)::text = 'contribution.read_self'::text))"
)
_ADDITION = (
    " OR (((action_id)::text = 'project.catalogue.list'::text) AND "
    "((permission_id)::text = 'project.read'::text))"
)


def upgrade():
    """Extend only the public audit constraint, preserving every retained event."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.audit_events IN ACCESS EXCLUSIVE MODE")
    definition = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
    ), {"name": _NAME}).scalar_one()
    if definition.count(_ANCHOR) != 2 or "project.catalogue.list" in definition:
        raise RuntimeError("project catalogue audit action constraint shape changed")
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + _NAME)
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT " + _NAME + " "
               + definition.replace(_ANCHOR, _ANCHOR + _ADDITION))


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
