"""Admit exact uncertain post-submit delivery authorization evidence pairs."""

from alembic import op
from sqlalchemy import text


revision = "0055_delivery_reconciliation"
down_revision = "0054_artifact_proof_timing"
branch_labels = None
depends_on = None


_CONSTRAINT = "ck_audit_events_authorization_action_evidence"
_ANCHOR = (
    "(((action_id)::text = 'operations.checker_retry_source.list'::text) AND "
    "((permission_id)::text = 'operations.status.read'::text))"
)
_PAIRS = (
    (
        "(((action_id)::text = 'operations.post_submit_delivery.list'::text) AND "
        "((permission_id)::text = 'operations.status.read'::text))"
    ),
    (
        "(((action_id)::text = 'operations.post_submit_delivery.reconcile'::text) AND "
        "((permission_id)::text = 'operations.reconcile.run'::text))"
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
    if definition.count(_ANCHOR) != 2 or any(pair in definition for pair in _PAIRS):
        raise RuntimeError(
            "operational delivery audit predecessor constraint shape changed"
        )
    additions = "".join(f" OR {pair}" for pair in _PAIRS)
    _replace(definition.replace(_ANCHOR, _ANCHOR + additions))


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
