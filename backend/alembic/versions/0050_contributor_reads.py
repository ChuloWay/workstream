"""Admit the caller's own grant and work read decisions to the audit ledger."""

from alembic import op
from sqlalchemy import text

revision = "0050_contributor_reads"
down_revision = "0049_attempt_outcome_findings"
branch_labels = None
depends_on = None

_ACTIONS = (
    ("actor.project.list", "actor.profile.read_self"),
    ("actor.assignment.list", "submission.read_own"),
    ("actor.submission.list", "submission.read_own"),
    ("actor.work_summary.read", "submission.read_own"),
    ("task.submission_bundle_preparation.list", "submission.read_own"),
    ("task.submission_bundle_preparation.read", "submission.read_own"),
)


def upgrade():
    """Extend only the closed action/permission evidence vocabulary; no data changes."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.audit_events IN ACCESS EXCLUSIVE MODE")
    name = "ck_audit_events_authorization_action_evidence"
    definition = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
    ), {"name": name}).scalar_one()
    anchor = (
        "(((action_id)::text = 'contribution.read_self'::text) AND "
        "((permission_id)::text = 'contribution.read_self'::text))"
    )
    addition = "".join(
        f" OR (((action_id)::text = '{action}'::text) AND ((permission_id)::text = '{permission}'::text))"
        for action, permission in _ACTIONS
    )
    if definition.count(anchor) != 2 or any(action in definition for action, _ in _ACTIONS):
        raise RuntimeError("contributor read audit action constraint shape changed")
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT " + name + " "
               + definition.replace(anchor, anchor + addition))


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
