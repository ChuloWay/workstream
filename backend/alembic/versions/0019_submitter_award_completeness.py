"""Require complete frozen awards for accepted-submission contributions."""

from alembic import op

revision = "0019_submitter_awards"
down_revision = "0018_task_routing_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
    op.execute(
        "LOCK TABLE public.contribution_records, public.compensation_awards "
        "IN SHARE ROW EXCLUSIVE MODE"
    )
    op.execute("""
CREATE FUNCTION public.accepted_submission_award_set_is_complete(record_uuid uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT NOT EXISTS (
        SELECT 1
        FROM public.contribution_records record
        WHERE record.id = record_uuid
          AND record.contribution_type = 'accepted_submission'
          AND (
              EXISTS (
                  SELECT 1
                  FROM public.contribution_rules rule
                  JOIN public.contribution_award_definitions definition
                    ON definition.contribution_rule_id = rule.id
                   AND definition.contribution_policy_version_id = rule.contribution_policy_version_id
                   AND definition.project_id = rule.project_id
                   AND definition.contribution_type = rule.contribution_type
                  WHERE rule.contribution_policy_version_id = record.contribution_policy_version_id
                    AND rule.project_id = record.project_id
                    AND rule.contribution_type = record.contribution_type
                    AND NOT EXISTS (
                        SELECT 1
                        FROM public.compensation_awards award
                        WHERE award.contribution_record_id = record.id
                          AND award.award_definition_id = definition.id
                    )
              )
              OR EXISTS (
                  SELECT 1
                  FROM public.compensation_awards award
                  WHERE award.contribution_record_id = record.id
                    AND NOT EXISTS (
                        SELECT 1
                        FROM public.contribution_rules rule
                        JOIN public.contribution_award_definitions definition
                          ON definition.contribution_rule_id = rule.id
                         AND definition.contribution_policy_version_id = rule.contribution_policy_version_id
                         AND definition.project_id = rule.project_id
                         AND definition.contribution_type = rule.contribution_type
                        WHERE rule.contribution_policy_version_id = record.contribution_policy_version_id
                          AND rule.project_id = record.project_id
                          AND rule.contribution_type = record.contribution_type
                          AND definition.id = award.award_definition_id
                    )
              )
          )
    )
$$
""")
    op.execute("""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.contribution_records record
        WHERE record.contribution_type = 'accepted_submission'
          AND NOT public.accepted_submission_award_set_is_complete(record.id)
    ) THEN
        RAISE EXCEPTION 'retained accepted-submission contribution has incomplete award set'
          USING ERRCODE = '23514';
    END IF;
END
$$
""")
    op.execute("""
CREATE FUNCTION public.require_accepted_submission_award_set()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    record_uuid uuid;
BEGIN
    IF TG_TABLE_SCHEMA = 'public' AND TG_TABLE_NAME = 'contribution_records' THEN
        record_uuid := NEW.id;
    ELSIF TG_TABLE_SCHEMA = 'public' AND TG_TABLE_NAME = 'compensation_awards' THEN
        record_uuid := NEW.contribution_record_id;
    ELSE
        RAISE EXCEPTION 'accepted-submission award guard installed on unexpected table'
          USING ERRCODE = '55000';
    END IF;

    IF NOT public.accepted_submission_award_set_is_complete(record_uuid) THEN
        RAISE EXCEPTION 'accepted-submission contribution has incomplete award set'
          USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END
$$
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER accepted_submission_award_set_from_contribution
AFTER INSERT ON public.contribution_records
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION public.require_accepted_submission_award_set()
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER accepted_submission_award_set_from_award
AFTER INSERT ON public.compensation_awards
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION public.require_accepted_submission_award_set()
""")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
