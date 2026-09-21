"""Persist atomic, immutable task command replay results."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0025_task_command_replay"
down_revision = "0024_task_policy_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_command_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_profile_id", sa.String(36), sa.ForeignKey(
            "actor_profiles.id", deferrable=True, initially="DEFERRED",
        ), nullable=False),
        sa.Column("action_id", sa.String(160), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("assignment_id", sa.String(36)),
        sa.Column("contributor_id", sa.String(36)),
        sa.Column("locked_context_hash", sa.String(71)),
        sa.Column("response", JSONB(none_as_null=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("actor_profile_id", "action_id", "idempotency_key", name="uq_task_command_namespace"),
        sa.ForeignKeyConstraint(
            ["assignment_id", "task_id", "contributor_id"],
            ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"],
            name="fk_task_command_assignment",
        ),
        sa.CheckConstraint(
            "action_id in ('task.claim','task.start','operations.task.start_override')",
            name="task_command_action",
        ),
        sa.CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="task_command_request_digest"),
        sa.CheckConstraint(
            "(status='pending' and assignment_id is null and contributor_id is null "
            "and locked_context_hash is null and response is null and committed_at is null) or "
            "(status='committed' and assignment_id is not null and contributor_id is not null "
            "and locked_context_hash is not null and locked_context_hash ~ '^sha256:[0-9a-f]{64}$' "
            "and response is not null and jsonb_typeof(response)='object' and committed_at is not null)",
            name="task_command_state_shape",
        ),
        sa.CheckConstraint(
            "status='pending' or (action_id='operations.task.start_override' and actor_profile_id<>contributor_id) "
            "or (action_id in ('task.claim','task.start') and actor_profile_id=contributor_id)",
            name="task_command_contributor",
        ),
    )
    op.execute("""
        CREATE FUNCTION protect_task_command_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP <> 'UPDATE' THEN
                RAISE EXCEPTION 'task command receipts cannot be removed' USING ERRCODE='23514';
            END IF;
            IF NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
            IF OLD.status <> 'pending' OR NEW.status <> 'committed' OR
               ROW(NEW.id, NEW.actor_profile_id, NEW.action_id, NEW.idempotency_key,
                   NEW.request_digest, NEW.task_id, NEW.created_at) IS DISTINCT FROM
               ROW(OLD.id, OLD.actor_profile_id, OLD.action_id, OLD.idempotency_key,
                   OLD.request_digest, OLD.task_id, OLD.created_at) THEN
                RAISE EXCEPTION 'task command receipt is immutable' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("CREATE TRIGGER task_command_receipt_immutable BEFORE UPDATE OR DELETE ON task_command_receipts "
               "FOR EACH ROW EXECUTE FUNCTION protect_task_command_receipt()")
    op.execute("CREATE TRIGGER task_command_receipt_no_truncate BEFORE TRUNCATE ON task_command_receipts "
               "FOR EACH STATEMENT EXECUTE FUNCTION protect_task_command_receipt()")


def downgrade() -> None:
    if op.get_bind().execute(sa.text("select exists(select 1 from task_command_receipts)")).scalar_one():
        raise RuntimeError("task command history prevents downgrade")
    op.drop_table("task_command_receipts")
    op.execute("DROP FUNCTION protect_task_command_receipt()")
