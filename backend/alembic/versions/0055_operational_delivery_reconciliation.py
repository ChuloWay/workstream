"""Admit exact uncertain post-submit delivery authorization evidence pairs."""

from alembic import op
from sqlalchemy import text


revision = "0055_delivery_reconciliation"
down_revision = "0054_artifact_proof_timing"
branch_labels = None
depends_on = None


_CONSTRAINT = "ck_audit_events_authorization_action_evidence"
_PRIVACY_CONSTRAINT = "ck_audit_events_authority_privacy_bounds"
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


def _definition(name: str) -> str:
    return op.get_bind().execute(
        text(
            "select pg_get_constraintdef(oid) from pg_catalog.pg_constraint "
            "where conrelid='public.audit_events'::regclass and conname=:name"
        ),
        {"name": name},
    ).scalar_one()


def _replace(name: str, definition: str) -> None:
    op.execute(f"alter table public.audit_events drop constraint {name}")
    op.execute(
        f"alter table public.audit_events add constraint {name} {definition}"
    )


def upgrade() -> None:
    definition = _definition(_CONSTRAINT)
    if definition.count(_ANCHOR) != 2 or any(pair in definition for pair in _PAIRS):
        raise RuntimeError(
            "operational delivery audit predecessor constraint shape changed"
        )
    additions = "".join(f" OR {pair}" for pair in _PAIRS)
    _replace(_CONSTRAINT, definition.replace(_ANCHOR, _ANCHOR + additions))

    definition = _definition(_PRIVACY_CONSTRAINT)
    resource_start = definition.index("resource_type IS NULL")
    target_start = definition.index("target_ref_kind IS NULL")
    resource_registry = definition[resource_start:target_start]
    addition = "('outbox_delivery'::character varying)::text, "
    if addition in definition or resource_registry.count("ARRAY[") != 1:
        raise RuntimeError(
            "operational delivery audit privacy constraint shape changed"
        )
    index = definition.index("ARRAY[", resource_start) + len("ARRAY[")
    _replace(
        _PRIVACY_CONSTRAINT,
        definition[:index] + addition + definition[index:],
    )


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
