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
    DECLARE prior public.submissions%ROWTYPE; prior_assignment public.task_assignments%ROWTYPE;
      predecessor public.submissions%ROWTYPE; assignment_round integer;
    BEGIN
      SELECT * INTO prior FROM public.submissions s WHERE s.task_id=NEW.task_id
      ORDER BY s.version DESC LIMIT 1;
      IF NEW.version IS NULL OR NEW.version < 1
        OR NEW.version::bigint IS DISTINCT FROM coalesce(prior.version::bigint,0)+1 THEN
        RAISE EXCEPTION 'submission_revision_lineage_invalid' USING ERRCODE='23514';
      END IF;
      IF NEW.supersedes_submission_id IS NULL THEN
        IF EXISTS (SELECT 1 FROM public.submissions s
            WHERE s.task_assignment_id=NEW.task_assignment_id)
        THEN RAISE EXCEPTION 'submission_revision_lineage_invalid' USING ERRCODE='23514'; END IF;
        IF prior.id IS NOT NULL THEN
          SELECT * INTO prior_assignment FROM public.task_assignments
          WHERE id=prior.task_assignment_id;
          IF prior_assignment.id IS NULL OR prior_assignment.id=NEW.task_assignment_id
            OR prior_assignment.status<>'revision_expired'
            OR prior_assignment.released_at IS NULL
          THEN RAISE EXCEPTION 'submission_revision_lineage_invalid' USING ERRCODE='23514'; END IF;
        END IF;
        RETURN NEW;
      END IF;
      SELECT * INTO predecessor FROM public.submissions s
      WHERE s.id=NEW.supersedes_submission_id;
      IF predecessor.id IS NULL OR predecessor.id IS DISTINCT FROM prior.id
        OR predecessor.task_id<>NEW.task_id
        OR predecessor.task_assignment_id<>NEW.task_assignment_id
        OR predecessor.contributor_id<>NEW.contributor_id
        OR predecessor.version::bigint<>NEW.version::bigint-1
      THEN RAISE EXCEPTION 'submission_revision_lineage_invalid' USING ERRCODE='23514'; END IF;
      SELECT count(*) INTO assignment_round FROM public.submissions s
      WHERE s.task_assignment_id=NEW.task_assignment_id
        AND s.version<=predecessor.version;
      IF NOT EXISTS (
        SELECT 1 FROM public.revision_policies p
        JOIN public.workstream_tasks t ON t.project_id=p.project_id
        WHERE t.id=NEW.task_id
          AND p.id=NEW.locked_revision_policy_id
          AND p.guide_version=NEW.locked_guide_version
          AND p.policy_generation=NEW.locked_revision_policy_generation
          AND p.policy_hash=NEW.locked_revision_policy_hash
          AND p.semantics_status='complete'
          AND assignment_round <= p.max_revision_rounds
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
