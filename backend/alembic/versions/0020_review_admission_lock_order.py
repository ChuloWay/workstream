"""Take TASK custody before review INSERT fence and foreign-key locks."""

from alembic import op
import sqlalchemy as sa

revision = "0020_review_admission_lock_order"
down_revision = "0019_submitter_awards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace existing guards in place, preserving rows and update semantics."""
    op.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
    op.execute(
        "LOCK TABLE public.review_queue_entries, public.review_admission_idempotency_records "
        "IN SHARE ROW EXCLUSIVE MODE"
    )
    anchor = "select project_id into task_project from workstream_tasks where id=new.task_id;"
    replacement = """
          if tg_op='INSERT' then
            select task.project_id into task_project from public.workstream_tasks task
              where task.id=new.task_id and task.project_id=new.project_id for update;
          else
            -- UPDATE already holds its admission row; never acquire TASK after it.
            select task.project_id into task_project from public.workstream_tasks task
              where task.id=new.task_id and task.project_id=new.project_id;
          end if;
    """
    for name in ("guard_review_queue_entry", "guard_review_admission_record"):
        definition = op.get_bind().execute(sa.text(
            "SELECT pg_catalog.pg_get_functiondef("
            "pg_catalog.to_regprocedure(:signature))"
        ), {"signature": f"public.{name}()"}).scalar_one()
        if definition.count(anchor) != 1:
            raise RuntimeError("review TASK custody guard shape changed")
        definition = definition.replace(anchor, replacement)
        # Pin all protected relations, including the PL/pgSQL row type.
        for table in ("checker_runs", "checker_submission_fences", "actor_profiles"):
            definition = definition.replace(table, "public." + table)
        op.execute(definition)
        op.execute(f"ALTER FUNCTION public.{name}() SET search_path = pg_catalog, public, pg_temp")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
