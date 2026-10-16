"""Admit the exact current operational-read authorization evidence pairs."""

from alembic import op
from sqlalchemy import text


revision = "0050_operational_read_audit"
down_revision = "0049_attempt_outcome_findings"
branch_labels = None
depends_on = None


_CONSTRAINT = "ck_audit_events_authorization_action_evidence"
_ANCHOR = (
    "(((action_id)::text = 'checker.registry.register'::text) AND "
    "((permission_id)::text = 'operations.reconcile.run'::text))"
)
_READ_PAIRS = (
    (
        "(((action_id)::text = 'checker.registry.read'::text) AND "
        "((permission_id)::text = 'operations.status.read'::text))"
    ),
    (
        "(((action_id)::text = 'operations.checker_retry_source.list'::text) AND "
        "((permission_id)::text = 'operations.status.read'::text))"
    ),
)


def _definition() -> str:
    return op.get_bind().execute(
        text(
            "select pg_get_constraintdef(oid) from pg_catalog.pg_constraint "
            "where conrelid='public.audit_events'::regclass and conname=:name"
        ),
        {"name": _CONSTRAINT},
    ).scalar_one()


def _replace(definition: str) -> None:
    op.execute(f"alter table public.audit_events drop constraint {_CONSTRAINT}")
    op.execute(
        f"alter table public.audit_events add constraint {_CONSTRAINT} {definition}"
    )


def upgrade() -> None:
    definition = _definition()
    if definition.count(_ANCHOR) != 2 or any(pair in definition for pair in _READ_PAIRS):
        raise RuntimeError("operational read audit predecessor constraint shape changed")
    additions = "".join(f" OR {pair}" for pair in _READ_PAIRS)
    _replace(definition.replace(_ANCHOR, _ANCHOR + additions))


def downgrade() -> None:
    definition = _definition()
    if definition.count(_ANCHOR) != 2 or any(
        definition.count(pair) != 2 for pair in _READ_PAIRS
    ):
        raise RuntimeError("operational read audit downgrade constraint shape changed")
    for pair in reversed(_READ_PAIRS):
        definition = definition.replace(f" OR {pair}", "")
    _replace(definition)
