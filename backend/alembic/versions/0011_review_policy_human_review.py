"""Version the human-review requirement without rewriting policy history."""

from alembic import op
import sqlalchemy as sa

revision = "0011_review_policy_human_review"
down_revision = "0010_project_guide_setup_finalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Backfill legacy interpretation, then require explicit new persisted mode."""
    op.add_column(
        "review_policies",
        sa.Column("human_review_required", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "review_policies",
        sa.Column("semantics_format", sa.String(2), nullable=False, server_default="v1"),
    )
    op.alter_column("review_policies", "human_review_required", server_default=None)
    op.alter_column("review_policies", "semantics_format", server_default="v2")
    op.create_check_constraint(
        "review_policy_semantics_format",
        "review_policies",
        "semantics_format in ('v1','v2') and (semantics_format <> 'v1' or human_review_required)",
    )


def downgrade() -> None:
    """Refuse loss of any versioned policy meaning, including explicit true."""
    if (
        op.get_bind()
        .execute(
            sa.text("select exists(select 1 from review_policies where semantics_format='v2')")
        )
        .scalar_one()
    ):
        raise RuntimeError("v2 review policy history cannot be downgraded")
    op.drop_constraint("review_policy_semantics_format", "review_policies", type_="check")
    op.drop_column("review_policies", "semantics_format")
    op.drop_column("review_policies", "human_review_required")
