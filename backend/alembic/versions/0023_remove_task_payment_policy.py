"""Remove unused guide-keyed payment storage without discarding retained facts."""

from alembic import op

revision = "0023_remove_task_payment_policy"
down_revision = "0022_submission_packet_custody"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Refuse retained terms or receipts before removing their empty storage."""
    op.execute("""
LOCK TABLE public.task_command_receipts, public.workstream_tasks,
           public.submissions, public.payment_policies IN ACCESS EXCLUSIVE MODE;
""")
    op.execute("""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.submissions WHERE locked_payment_policy_version IS NOT NULL) THEN
        RAISE EXCEPTION 'retained Submission payment stamp requires an explicit preservation design' USING ERRCODE='23514';
    END IF;
    IF EXISTS (SELECT 1 FROM public.workstream_tasks WHERE locked_payment_policy_version IS NOT NULL) THEN
        RAISE EXCEPTION 'retained TASK payment stamp requires an explicit preservation design' USING ERRCODE='23514';
    END IF;
    IF EXISTS (SELECT 1 FROM public.workstream_tasks WHERE base_amount IS NOT NULL) THEN
        RAISE EXCEPTION 'retained TASK base amount requires an explicit preservation design' USING ERRCODE='23514';
    END IF;
    IF EXISTS (SELECT 1 FROM public.workstream_tasks WHERE currency IS NOT NULL) THEN
        RAISE EXCEPTION 'retained TASK currency requires an explicit preservation design' USING ERRCODE='23514';
    END IF;
    IF EXISTS (SELECT 1 FROM public.workstream_tasks WHERE payout_type IS NOT NULL) THEN
        RAISE EXCEPTION 'retained TASK payout type requires an explicit preservation design' USING ERRCODE='23514';
    END IF;
    IF EXISTS (SELECT 1 FROM public.payment_policies) THEN
        RAISE EXCEPTION 'retained PaymentPolicy rows require an explicit preservation design' USING ERRCODE='23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.task_command_receipts
        WHERE response ?| ARRAY['base_amount', 'currency', 'payout_type', 'locked_payment_policy_version']
           OR (response -> 'task') ?| ARRAY['base_amount', 'currency', 'payout_type', 'locked_payment_policy_version']
    ) THEN
        RAISE EXCEPTION 'retained TASK payment response requires an explicit preservation design' USING ERRCODE='23514';
    END IF;
END;
$$;
""")
    op.drop_constraint("fk_submissions_task_locked_payment_policy", "submissions", schema="public")
    op.drop_constraint("uq_workstream_tasks_id_locked_payment_policy", "workstream_tasks", schema="public")
    op.drop_constraint("fk_workstream_tasks_locked_payment_policy", "workstream_tasks", schema="public")
    op.drop_column("submissions", "locked_payment_policy_version", schema="public")
    for column in ("locked_payment_policy_version", "base_amount", "currency", "payout_type"):
        op.drop_column("workstream_tasks", column, schema="public")
    op.drop_table("payment_policies", schema="public")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
