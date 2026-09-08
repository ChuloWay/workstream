"""Admit exact ContributionPolicy decision resources without widening audit facts."""

from alembic import op
import sqlalchemy as sa

revision = "0012_contribution_policy_audit_resource"
down_revision = "0011_review_policy_human_review"
branch_labels = None
depends_on = None

_ANCHOR = "('project_guide_setup_finalization'::character varying)::text"
_RESOURCE = "('contribution_policy'::character varying)::text"
_TOKEN = ", " + _RESOURCE
_CONSTRAINT = "ck_audit_events_authority_privacy_bounds"


def _amend(*, add: bool) -> None:
    """Retain the installed constraint byte-for-byte except the single exact token."""
    connection = op.get_bind()
    connection.execute(sa.text("lock table audit_events in access exclusive mode"))
    if (
        not add
        and connection.execute(
            sa.text(
                "select exists(select 1 from audit_events where resource_type='contribution_policy')"
            )
        ).scalar_one()
    ):
        raise RuntimeError("ContributionPolicy audit history prevents downgrade")
    definition = connection.execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authority_privacy_bounds'"
        )
    ).scalar_one()
    if (
        definition.count(_ANCHOR) != 1
        or definition.count(_RESOURCE) != (0 if add else 1)
        or (not add and definition.count(_TOKEN) != 1)
    ):
        raise RuntimeError("audit resource constraint shape changed")
    amended = (
        definition.replace(_ANCHOR, _ANCHOR + _TOKEN, 1)
        if add
        else definition.replace(_TOKEN, "", 1)
    )
    op.execute("alter table audit_events drop constraint " + _CONSTRAINT)
    op.execute("alter table audit_events add constraint " + _CONSTRAINT + " " + amended)


def upgrade() -> None:
    """Allow only the exact policy token in the existing closed resource vocabulary."""
    _amend(add=True)


def downgrade() -> None:
    """Refuse loss of policy evidence; otherwise restore the exact prior constraint."""
    _amend(add=False)
