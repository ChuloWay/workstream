"""Keep audit validation independent of the restore session's search path."""

from alembic import op

revision = "0060_audit_restore_path"
down_revision = "0059_neutral_guide_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve validation bodies and bind their sibling calls to public owners."""
    for signature in (
        "public.authority_event_facts_are_safe(text,json,json,text)",
        "public.authority_grant_facts_are_safe(json,text[],text,boolean,text)",
    ):
        op.execute(f"ALTER FUNCTION {signature} SET search_path=pg_catalog,public,pg_temp")


def downgrade() -> None:
    """Never restore session-dependent validation on retained audit evidence."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
