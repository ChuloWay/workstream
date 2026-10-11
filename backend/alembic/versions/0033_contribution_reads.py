"""Admit exact contribution-read authorization evidence to the audit ledger."""

from alembic import op
import sqlalchemy as sa


revision = "0033_contribution_reads"
down_revision = "0032_checker_remediation"
branch_labels = None
depends_on = None


_ACTIONS = ("contribution.read_self", "contribution.read_project")


def _definition(name: str) -> str:
    return (
        op.get_bind()
        .execute(
            sa.text(
                "select pg_catalog.pg_get_constraintdef(oid) "
                "from pg_catalog.pg_constraint "
                "where conrelid='public.audit_events'::regclass and conname=:name"
            ),
            {"name": name},
        )
        .scalar_one()
    )


def _replace_constraint(name: str, definition: str) -> None:
    op.execute(f"alter table public.audit_events drop constraint {name}")
    op.execute(f"alter table public.audit_events add constraint {name} {definition}")


def _extend_action_evidence() -> None:
    name = "ck_audit_events_authorization_action_evidence"
    definition = _definition(name)
    anchor = (
        "(((action_id)::text = 'project.task.create'::text) AND "
        "((permission_id)::text = 'project.task.manage'::text))"
    )
    additions = " OR ".join(
        "(((action_id)::text = "
        f"'{action}'::text) AND ((permission_id)::text = '{action}'::text))"
        for action in _ACTIONS
    )
    if definition.count(anchor) != 2 or definition.count(additions) != 0:
        raise RuntimeError("contribution-read audit action constraint shape changed")
    _replace_constraint(name, definition.replace(anchor, anchor + " OR " + additions))


def upgrade() -> None:
    """Extend only the closed audit action and evidence vocabularies."""
    op.execute("set local search_path=pg_catalog,public,pg_temp")
    op.execute("lock table public.audit_events in access exclusive mode")
    _extend_action_evidence()


def downgrade() -> None:
    """Refuse removal of the vocabulary, especially with retained evidence."""
    op.execute("set local search_path=pg_catalog,public,pg_temp")
    op.execute("lock table public.audit_events in access exclusive mode")
    retained = op.get_bind().execute(
        sa.text(
            "select exists(select 1 from public.audit_events "
            "where action_id=any(cast(:actions as varchar[])))"
        ),
        {"actions": list(_ACTIONS)},
    ).scalar_one()
    if retained:
        raise RuntimeError(
            "cannot downgrade contribution-read audit vocabulary with retained evidence"
        )
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
