"""Enforce the exact locked revision allowance on new immutable submissions."""

from alembic import op

revision = "0040_checker_revision_cap"
down_revision = "0039_false_guide_activation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Guard new writes without changing or reinterpreting retained attempts."""
    op.execute("""
    CREATE FUNCTION public.guard_submission_revision_capacity() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
    BEGIN
      IF NEW.version > 1 AND NOT EXISTS (
        SELECT 1 FROM public.revision_policies p
        JOIN public.workstream_tasks t ON t.project_id=p.project_id
        WHERE t.id=NEW.task_id
          AND p.id=NEW.locked_revision_policy_id
          AND p.guide_version=NEW.locked_guide_version
          AND p.policy_generation=NEW.locked_revision_policy_generation
          AND p.policy_hash=NEW.locked_revision_policy_hash
          AND p.semantics_status='complete'
          AND NEW.version::bigint - 1 <= p.max_revision_rounds
      ) THEN
        RAISE EXCEPTION 'revision_limit_reached' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    """)
    op.execute("""
    CREATE TRIGGER guard_submission_revision_capacity
      BEFORE INSERT ON public.submissions FOR EACH ROW
      EXECUTE FUNCTION public.guard_submission_revision_capacity();
    """)


def downgrade() -> None:
    """Require a fresh database instead of removing write custody."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
