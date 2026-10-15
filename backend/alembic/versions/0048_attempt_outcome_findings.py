"""Store attempt outcomes, assignment start and per-finding checker evidence."""

from alembic import op
from sqlalchemy import text

revision = "0048_attempt_outcome_findings"
down_revision = "0047_revision_recovery"
branch_labels = None
depends_on = None


def _replace(signature, replacements):
    """Rewrite one current function, refusing any unexpected predecessor shape."""
    body = op.get_bind().execute(text(
        "SELECT pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    for old, new in replacements:
        if body.count(old) != 1:
            raise RuntimeError("attempt outcome predecessor function shape changed: " + signature)
        body = body.replace(old, new)
    op.execute(body)


def _execute_script(script):
    """Run each top-level statement separately; asyncpg prepares one command at a time."""
    statement, quoted = [], False
    for line in script.splitlines():
        statement.append(line)
        quoted ^= line.count("$$") % 2 == 1
        if not quoted and line.rstrip().endswith(";"):
            op.execute("\n".join(statement))
            statement = []
    if "".join(statement).strip():
        raise RuntimeError("unterminated attempt outcome migration statement")


_FINDINGS_TABLE = """
CREATE TABLE public.checker_result_findings (
  id uuid NOT NULL,
  checker_result_id uuid NOT NULL,
  checker_run_id uuid NOT NULL,
  task_id uuid NOT NULL,
  submission_id uuid NOT NULL,
  member_order integer NOT NULL,
  finding_order integer NOT NULL,
  check_id character varying(100) NOT NULL,
  code character varying(100) NOT NULL,
  level character varying(30) NOT NULL,
  path character varying(1000),
  line integer,
  created_at timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT pk_checker_result_findings PRIMARY KEY (id),
  CONSTRAINT ck_checker_result_findings_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128),
  CONSTRAINT ck_checker_result_findings_member_order CHECK (member_order between 0 and 8),
  CONSTRAINT ck_checker_result_findings_finding_order CHECK (finding_order between 0 and 255),
  CONSTRAINT ck_checker_result_findings_level CHECK (level in ('info','warning','error','coverage_incomplete')),
  CONSTRAINT ck_checker_result_findings_location CHECK (line is null or (path is not null and line between 1 and 10000000)),
  CONSTRAINT uq_checker_result_findings_order UNIQUE (checker_result_id, finding_order),
  CONSTRAINT fk_checker_result_findings_member FOREIGN KEY (checker_result_id) REFERENCES public.checker_results(id),
  CONSTRAINT fk_checker_result_findings_run_ownership FOREIGN KEY (checker_run_id, task_id, submission_id)
    REFERENCES public.checker_runs(id, task_id, submission_id)
);
CREATE INDEX ix_checker_result_findings_checker_result_id
  ON public.checker_result_findings USING btree (checker_result_id);
CREATE INDEX ix_checker_result_findings_submission_level
  ON public.checker_result_findings USING btree (submission_id, checker_run_id, level);

CREATE FUNCTION public.protect_checker_result_finding_custody() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE parent public.checker_runs; member public.checker_results;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'checker result finding custody is immutable' USING ERRCODE='23514';
  END IF;
  SELECT * INTO parent FROM public.checker_runs
    WHERE id=NEW.checker_run_id AND task_id=NEW.task_id
      AND submission_id=NEW.submission_id FOR UPDATE;
  IF NOT FOUND OR parent.status IS DISTINCT FROM 'running' OR parent.completed_at IS NOT NULL THEN
    RAISE EXCEPTION 'finished or unclaimed checker run cannot receive findings'
      USING ERRCODE='23514';
  END IF;
  SELECT * INTO member FROM public.checker_results WHERE id=NEW.checker_result_id;
  IF NOT FOUND OR member.checker_run_id IS DISTINCT FROM NEW.checker_run_id
     OR member.member_order IS DISTINCT FROM NEW.member_order THEN
    RAISE EXCEPTION 'checker finding member differs' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER checker_result_finding_custody BEFORE INSERT OR DELETE OR UPDATE
  ON public.checker_result_findings FOR EACH ROW
  EXECUTE FUNCTION public.protect_checker_result_finding_custody();
CREATE TRIGGER checker_result_finding_no_truncate BEFORE TRUNCATE
  ON public.checker_result_findings FOR EACH STATEMENT
  EXECUTE FUNCTION public.protect_checker_result_finding_custody();
CREATE CONSTRAINT TRIGGER checker_finding_terminal_custody AFTER INSERT
  ON public.checker_result_findings DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
  EXECUTE FUNCTION public.validate_checker_terminal_custody();
"""

_TERMINAL_REPLACEMENTS = (
    (
        "envelope jsonb; expected_members jsonb;",
        "envelope jsonb; expected_members jsonb; actual_findings jsonb; expected_findings jsonb;"
        " coverage_incomplete boolean;",
    ),
    (
        "THEN (to_jsonb(NEW)->>'checker_run_id')::uuid ELSE NEW.id END;",
        "THEN (to_jsonb(NEW)->>'checker_run_id')::uuid WHEN TG_TABLE_NAME='checker_result_findings'"
        " THEN (to_jsonb(NEW)->>'checker_run_id')::uuid ELSE NEW.id END;",
    ),
    (
        """          RAISE EXCEPTION 'checker terminal members differ' USING ERRCODE='23514';
        END IF;
""",
        """          RAISE EXCEPTION 'checker terminal members differ' USING ERRCODE='23514';
        END IF;
        SELECT coalesce(jsonb_agg(jsonb_build_object(
          'member_id',f.checker_result_id::text,'member_order',f.member_order,
          'finding_order',f.finding_order,'check_id',f.check_id,'code',f.code,
          'level',f.level,'path',f.path,'line',f.line
        ) ORDER BY f.member_order,f.finding_order),'[]'::jsonb)
        INTO actual_findings FROM checker_result_findings f
        WHERE f.checker_run_id=current_run.id AND f.task_id=current_run.task_id
          AND f.submission_id=current_run.submission_id;
        SELECT coalesce(jsonb_agg(jsonb_build_object(
          'member_id',m.id::text,'member_order',(item->>'order')::integer,
          'finding_order',(finding.ordinality-1)::integer,
          'check_id',finding.value->>'check_id','code',finding.value->>'code',
          'level',finding.value->>'level','path',finding.value->>'path',
          'line',(finding.value->>'line')::integer
        ) ORDER BY (item->>'order')::integer,finding.ordinality),'[]'::jsonb)
        INTO expected_findings
        FROM jsonb_array_elements(result#>'{execution,external_members}') item
        CROSS JOIN LATERAL jsonb_array_elements(item#>'{result,findings}')
          WITH ORDINALITY finding(value,ordinality)
        LEFT JOIN checker_results m ON m.checker_run_id=current_run.id
          AND m.member_order=(item->>'order')::integer;
        IF actual_findings IS DISTINCT FROM expected_findings THEN
          RAISE EXCEPTION 'checker terminal findings differ' USING ERRCODE='23514';
        END IF;
""",
    ),
    (
        "expected_route := CASE WHEN failed>0 THEN 'needs_revision' ELSE 'allow_review' END;",
        "SELECT EXISTS(SELECT 1 FROM jsonb_array_elements(result#>'{execution,external_members}') item"
        " CROSS JOIN LATERAL jsonb_array_elements(item#>'{result,findings}') finding"
        " WHERE finding->>'level'='coverage_incomplete') INTO coverage_incomplete;\n"
        "      expected_route := CASE WHEN failed>0 THEN 'needs_revision'"
        " WHEN coverage_incomplete THEN 'task_setup_blocked' ELSE 'allow_review' END;",
    ),
    (
        """        RAISE EXCEPTION 'checker completed custody or routing invalid' USING ERRCODE='23514';
      END IF;
""",
        """        RAISE EXCEPTION 'checker completed custody or routing invalid' USING ERRCODE='23514';
      END IF;
      IF expected_route='task_setup_blocked' THEN
        IF current_run.completion_event_id IS NOT NULL THEN
          RAISE EXCEPTION 'checker coverage hold cannot route' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
      END IF;
""",
    ),
)

_RETRY_SOURCE = (
    (
        """      IF source.status IS DISTINCT FROM 'infrastructure_failed'
        OR source.project_id""",
        """      IF NOT (
          (source.status='infrastructure_failed'
           AND source.failure_code IS NOT DISTINCT FROM r.failure_code
           AND source.result_json::jsonb->>'outcome'='infrastructure_failed'
           AND source.result_json::jsonb->>'infrastructure_failure_code' IS NOT DISTINCT FROM r.failure_code)
          OR (source.status='completed' AND source.routing_recommendation='task_setup_blocked'
           AND source.failure_code IS NULL AND r.failure_code='coverage_incomplete'
           AND source.result_json::jsonb->>'outcome'='completed'))
        OR source.project_id""",
    ),
    (
        """        OR source.failure_code IS DISTINCT FROM r.failure_code
        OR source.result_json::jsonb->>'outcome' IS DISTINCT FROM 'infrastructure_failed'
        OR source.result_json::jsonb->>'infrastructure_failure_code' IS DISTINCT FROM r.failure_code
""",
        "",
    ),
)

_SUPERSESSION = (
    (
        "IF prior.status IS DISTINCT FROM 'infrastructure_failed' THEN RETURN NULL; END IF;",
        "IF prior.status IS DISTINCT FROM 'infrastructure_failed' AND NOT (prior.status='completed'"
        " AND prior.routing_recommendation='task_setup_blocked') THEN RETURN NULL; END IF;",
    ),
    (
        "'terminal checker infrastructure retry requires Operator receipt'",
        "'terminal checker retry requires Operator receipt'",
    ),
)

_SUBMISSION_ATTEMPTS = """
ALTER TABLE public.submissions
  ADD COLUMN attempt_status character varying(30) DEFAULT 'evaluation_pending' NOT NULL,
  ADD COLUMN status_reason character varying(40),
  ADD COLUMN decided_at timestamp with time zone,
  ADD COLUMN updated_at timestamp with time zone DEFAULT now() NOT NULL;

UPDATE public.submissions s SET attempt_status='review_pending'
  FROM public.task_post_submit_routing_manifests m
  WHERE m.submission_id=s.id AND m.routing_recommendation='allow_review'
    AND m.human_review_required;
UPDATE public.submissions s SET attempt_status='needs_revision', decided_at=m.created_at
  FROM public.task_post_submit_routing_manifests m
  WHERE m.submission_id=s.id AND m.routing_recommendation='needs_revision';
UPDATE public.submissions s SET attempt_status='rejected',
    status_reason='revision_deadline_expired', decided_at=e.expired_at
  FROM public.task_revision_expirations e WHERE e.source_submission_id=s.id;
UPDATE public.submissions s SET attempt_status='accepted', decided_at=a.accepted_at
  FROM public.final_acceptances a WHERE a.submission_id=s.id;
UPDATE public.submissions SET updated_at=greatest(submitted_at, coalesce(decided_at, submitted_at),
  coalesce((SELECT max(m.created_at) FROM public.task_post_submit_routing_manifests m
            WHERE m.submission_id=submissions.id), submitted_at));

ALTER TABLE public.submissions
  ADD CONSTRAINT ck_submissions_attempt_status CHECK (attempt_status in
    ('evaluation_pending','review_pending','accepted','needs_revision','rejected')),
  ADD CONSTRAINT ck_submissions_attempt_decision CHECK (
    (attempt_status in ('accepted','needs_revision','rejected')) = (decided_at is not null)),
  ADD CONSTRAINT ck_submissions_status_reason CHECK (status_reason is null or
    (attempt_status='rejected' and status_reason='revision_deadline_expired'));
CREATE INDEX ix_submissions_contributor_updated
  ON public.submissions USING btree (contributor_id, updated_at, id);

CREATE FUNCTION public.guard_submission_attempt_status() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE evidence_at timestamptz;
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.attempt_status IS DISTINCT FROM 'evaluation_pending'
       OR NEW.status_reason IS NOT NULL OR NEW.decided_at IS NOT NULL THEN
      RAISE EXCEPTION 'new submission attempt must await evaluation' USING ERRCODE='23514';
    END IF;
    NEW.updated_at := pg_catalog.clock_timestamp();
    RETURN NEW;
  END IF;
  NEW.updated_at := pg_catalog.clock_timestamp();
  IF NEW.attempt_status IS NOT DISTINCT FROM OLD.attempt_status THEN
    IF ROW(NEW.status_reason, NEW.decided_at) IS DISTINCT FROM ROW(OLD.status_reason, OLD.decided_at) THEN
      RAISE EXCEPTION 'submission attempt decision is immutable' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  -- The deciding owner's committed evidence supplies the timestamp and reason.
  IF OLD.attempt_status='evaluation_pending' AND NEW.attempt_status='review_pending' THEN
    SELECT m.created_at INTO evidence_at FROM public.task_post_submit_routing_manifests m
      WHERE m.submission_id=OLD.id AND m.task_id=OLD.task_id
        AND m.routing_recommendation='allow_review' AND m.human_review_required;
    NEW.decided_at := NULL; NEW.status_reason := NULL;
  ELSIF OLD.attempt_status='evaluation_pending' AND NEW.attempt_status='needs_revision' THEN
    SELECT m.created_at INTO evidence_at FROM public.task_post_submit_routing_manifests m
      WHERE m.submission_id=OLD.id AND m.task_id=OLD.task_id
        AND m.routing_recommendation='needs_revision';
    NEW.decided_at := evidence_at; NEW.status_reason := NULL;
  ELSIF OLD.attempt_status IN ('evaluation_pending','review_pending')
        AND NEW.attempt_status='accepted' THEN
    SELECT a.accepted_at INTO evidence_at FROM public.final_acceptances a
      WHERE a.submission_id=OLD.id AND a.task_id=OLD.task_id;
    NEW.decided_at := evidence_at; NEW.status_reason := NULL;
  ELSIF OLD.attempt_status='needs_revision' AND NEW.attempt_status='rejected' THEN
    SELECT e.expired_at INTO evidence_at FROM public.task_revision_expirations e
      WHERE e.source_submission_id=OLD.id AND e.task_id=OLD.task_id;
    NEW.decided_at := evidence_at; NEW.status_reason := 'revision_deadline_expired';
  ELSE
    RAISE EXCEPTION 'submission attempt transition is not allowed' USING ERRCODE='23514';
  END IF;
  IF evidence_at IS NULL THEN
    RAISE EXCEPTION 'submission attempt transition requires owner evidence' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER a_submission_attempt_status BEFORE INSERT OR UPDATE ON public.submissions
  FOR EACH ROW EXECUTE FUNCTION public.guard_submission_attempt_status();
"""

_DISPATCHED_IMMUTABLE = (
    (
        "pg_catalog.to_jsonb(NEW)-'status' IS DISTINCT FROM pg_catalog.to_jsonb(OLD)-'status'",
        "pg_catalog.to_jsonb(NEW)-ARRAY['status','attempt_status','status_reason','decided_at','updated_at']"
        " IS DISTINCT FROM pg_catalog.to_jsonb(OLD)-ARRAY['status','attempt_status','status_reason','decided_at','updated_at']",
    ),
)

_ASSIGNMENTS_AND_TASKS = """
ALTER TABLE public.task_assignments
  ADD COLUMN started_at timestamp with time zone,
  ADD COLUMN updated_at timestamp with time zone DEFAULT now() NOT NULL;

UPDATE public.task_assignments a SET started_at=(
  SELECT min(e.created_at) FROM public.audit_events e
  WHERE e.entity_type='task' AND e.entity_id=a.task_id
    AND e.event_type IN ('TaskStarted','TaskStartOverridden')
    AND e.created_at >= a.assigned_at
    AND (a.released_at IS NULL OR e.created_at <= a.released_at));
UPDATE public.task_assignments SET updated_at=greatest(assigned_at,
  coalesce(started_at, assigned_at), coalesce(released_at, assigned_at));

CREATE INDEX ix_task_assignments_contributor_updated
  ON public.task_assignments USING btree (contributor_id, updated_at, id);

CREATE FUNCTION public.stamp_record_updated_at() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
  NEW.updated_at := pg_catalog.clock_timestamp();
  RETURN NEW;
END $$;
CREATE TRIGGER a_task_assignment_updated_at BEFORE INSERT OR UPDATE ON public.task_assignments
  FOR EACH ROW EXECUTE FUNCTION public.stamp_record_updated_at();
CREATE TRIGGER a_task_updated_at BEFORE INSERT OR UPDATE ON public.workstream_tasks
  FOR EACH ROW EXECUTE FUNCTION public.stamp_record_updated_at();

CREATE FUNCTION public.guard_task_assignment_started_at() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.started_at IS NOT NULL THEN
      RAISE EXCEPTION 'a new assignment has not started' USING ERRCODE='23514';
    END IF;
  ELSIF NEW.started_at IS DISTINCT FROM OLD.started_at AND (OLD.started_at IS NOT NULL
        OR OLD.status IS DISTINCT FROM 'active' OR NOT EXISTS (
          SELECT 1 FROM public.workstream_tasks t WHERE t.id=OLD.task_id
            AND t.assigned_to=OLD.contributor_id AND t.status='in_progress')) THEN
    RAISE EXCEPTION 'assignment start requires the started task' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER task_assignment_started_at BEFORE INSERT OR UPDATE ON public.task_assignments
  FOR EACH ROW EXECUTE FUNCTION public.guard_task_assignment_started_at();
"""


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    _replace(
        "public.protect_checker_result_custody()",
        (("'external_checker_result.v1'", "'external_checker_result.v2'"),),
    )
    _execute_script(_FINDINGS_TABLE)
    _replace("public.validate_checker_terminal_custody()", _TERMINAL_REPLACEMENTS)
    _replace("public.checker_retry_receipt_valid(uuid)", _RETRY_SOURCE)
    _replace("public.require_checker_failed_supersession_receipt()", _SUPERSESSION)
    _replace("public.guard_dispatched_submission_immutable()", _DISPATCHED_IMMUTABLE)
    _execute_script(_SUBMISSION_ATTEMPTS)
    _execute_script(_ASSIGNMENTS_AND_TASKS)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
