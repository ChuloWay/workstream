"""Register the planned router identity without enabling authority or provisioning."""

from alembic import op
import sqlalchemy as sa

revision = "0017_acceptance_source_contracts"
down_revision = "0016_review_lifecycle_fence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Extend only the closed actor vocabulary, preserving all retained rows."""
    op.execute("set local search_path = pg_catalog, public, pg_temp")
    op.execute("lock table public.actor_profiles in access exclusive mode")
    definition = (
        op.get_bind()
        .execute(
            sa.text(
                "select pg_catalog.pg_get_constraintdef(oid) from pg_catalog.pg_constraint "
                "where conrelid='public.actor_profiles'::regclass "
                "and conname='ck_actor_profiles_kind_service_identity'"
            )
        )
        .scalar_one()
    )
    if definition.count("ARRAY[") != 1:
        raise RuntimeError("actor service identity constraint shape changed")
    extended = definition.replace(
        "ARRAY[", "ARRAY[('workstream.task.post_submit_router'::character varying)::text, "
    )
    op.execute(
        "alter table public.actor_profiles drop constraint ck_actor_profiles_kind_service_identity"
    )
    op.execute(
        "alter table public.actor_profiles add constraint ck_actor_profiles_kind_service_identity "
        + extended
    )


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
