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
_ACTION_CONSTRAINT = "ck_audit_events_authorization_action_evidence"
_ACTIONS = tuple("contribution.policy." + operation for operation in (
    "read", "create_draft", "update_draft", "publish", "retire"
))
_ACTION_ANCHOR = "(((action_id)::text = 'actor.profile.read_self'::text) AND ((permission_id)::text = 'actor.profile.read_self'::text))"
_ACTION_PAIRS = tuple(
    "(((action_id)::text = '" + action + "'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text))"
    for action in _ACTIONS
)
_ACTION_TOKEN = "".join(" OR " + pair for pair in _ACTION_PAIRS)


def _action_evidence(definition: str, *, add: bool) -> str:
    """Amend both existing mapping branches and reject partial or unexpected shapes."""
    if (
        definition.count(_ACTION_ANCHOR) != 2
        or any(definition.count(pair) != (0 if add else 2) for pair in _ACTION_PAIRS)
        or any(definition.count("'" + action + "'") != (0 if add else 2) for action in _ACTIONS)
        or (not add and definition.count(_ACTION_TOKEN) != 2)
    ):
        raise RuntimeError("audit action constraint shape changed")
    return (
        definition.replace(_ACTION_ANCHOR, _ACTION_ANCHOR + _ACTION_TOKEN)
        if add else definition.replace(_ACTION_TOKEN, "")
    )


def _amend(*, add: bool) -> None:
    """Retain the installed constraint byte-for-byte except the single exact token."""
    connection = op.get_bind()
    connection.execute(sa.text("lock table audit_events in access exclusive mode"))
    if (
        not add
        and connection.execute(
            sa.text(
                "select exists(select 1 from audit_events where resource_type='contribution_policy' "
                "or action_id in ('contribution.policy.read','contribution.policy.create_draft',"
                "'contribution.policy.update_draft','contribution.policy.publish','contribution.policy.retire'))"
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
    action_definition = connection.execute(sa.text(
        "select pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid='audit_events'::regclass "
        "and conname='ck_audit_events_authorization_action_evidence'"
    )).scalar_one()
    action_amended = _action_evidence(action_definition, add=add)
    op.execute("alter table audit_events drop constraint " + _ACTION_CONSTRAINT)
    op.execute("alter table audit_events add constraint " + _ACTION_CONSTRAINT + " " + action_amended)
    op.execute("alter table audit_events drop constraint " + _CONSTRAINT)
    op.execute("alter table audit_events add constraint " + _CONSTRAINT + " " + amended)


def upgrade() -> None:
    """Allow only the exact policy token in the existing closed resource vocabulary."""
    _amend(add=True)


def downgrade() -> None:
    """Refuse loss of policy evidence; otherwise restore the exact prior constraint."""
    _amend(add=False)
