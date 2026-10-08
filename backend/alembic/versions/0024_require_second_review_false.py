"""Refuse unsupported retained second-review policy before fixing it false."""

from alembic import op

revision = "0024_require_second_review_false"
down_revision = "0023_remove_task_payment_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve retained policy facts and install the current false-only invariant."""
    op.execute("LOCK TABLE public.review_policies IN ACCESS EXCLUSIVE MODE")
    op.execute("""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.review_policies WHERE requires_second_review
    ) THEN
        RAISE EXCEPTION
            'retained requires_second_review=true policy requires an explicit preservation design'
            USING ERRCODE='23514';
    END IF;
END;
$$;
""")
    op.create_check_constraint(
        "review_policy_second_review_disabled",
        "review_policies",
        "not requires_second_review",
        schema="public",
    )


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
