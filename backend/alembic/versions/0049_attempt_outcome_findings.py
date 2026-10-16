"""Store attempt outcomes, assignment start and per-finding checker evidence."""

import json
import re
import unicodedata

from alembic import op
from sqlalchemy import text

revision = "0049_attempt_outcome_findings"
down_revision = "0048_revision_exhaustion"
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


# Frozen copy of the finding rules this revision makes required, so the
# precondition keeps its meaning if the live contract later changes.
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_.-]{0,99}")
_RETAINED_FINDINGS = """
SELECT 'checker_runs' AS store, r.id::text AS row_id, f.value::text AS finding
  FROM public.checker_runs r
  CROSS JOIN LATERAL jsonb_path_query(r.result_json::jsonb,
    'lax $.execution.external_members[*].result.findings[*]') f(value)
  WHERE r.result_json IS NOT NULL
UNION ALL
SELECT 'selected_pre_submit_runs', p.id::text, f.value::text
  FROM public.selected_pre_submit_runs p
  CROSS JOIN LATERAL jsonb_path_query(p.terminal_json,
    'lax $.execution.external_members[*].result.findings[*]') f(value)
  WHERE p.terminal_json IS NOT NULL
"""


def _finding_current(finding):
    """Whether a retained finding satisfies the attributable, safe-location contract."""
    check_id, path = finding.get("check_id"), finding.get("path")
    if not (isinstance(check_id, str) and _IDENTIFIER.fullmatch(check_id)):
        return False
    if path is None:
        return finding.get("line") is None
    if not isinstance(path, str):
        return False
    parts = path.split("/")
    return not (
        "\\" in path or path.startswith("/")
        or any(unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"} for character in path)
        or any(part in {"", ".", ".."} or part.endswith((" ", ".")) for part in parts)
        or ":" in parts[0]
    )


def refuse_incompatible_retained_findings(bind):
    """Refuse the upgrade, before any change, while retained results would fail replay.

    Retained checker results and selected PRE terminals are immutable,
    digest-bound evidence: exact replay and completion delivery re-validate them
    against the finding contract this revision requires. Rewriting them would
    forge evidence, so v0.1 has no transition; such a database is recreated.
    """
    stale = {}
    for store, row_id, body in bind.execute(text(_RETAINED_FINDINGS)):
        finding = json.loads(body)
        if not (isinstance(finding, dict) and _finding_current(finding)):
            stale.setdefault(store, set()).add(row_id)
    if stale:
        detail = "; ".join(
            f"{store}: {len(ids)} rows (e.g. {', '.join(sorted(ids)[:3])})"
            for store, ids in sorted(stale.items())
        )
        raise RuntimeError(
            "retained checker findings lack the required check_id or a safe path, so "
            f"replay would reject them ({detail}); Workstream v0.1 requires a fresh "
            "database; recreate this database before running the 0001_uuid7_v01 migration"
        )


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
"""

_TERMINAL_REPLACEMENTS = (
    (
        "envelope jsonb; expected_members jsonb;",
        "envelope jsonb; expected_members jsonb; actual_findings jsonb; expected_findings jsonb;"
        " coverage_incomplete boolean; human_review boolean;",
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
        "      SELECT p.human_review_required INTO human_review FROM review_policies p"
        " WHERE p.project_id=current_run.project_id AND p.id=current_run.locked_review_policy_id"
        " AND p.policy_generation=current_run.locked_review_policy_generation"
        " AND p.policy_hash=current_run.locked_review_policy_hash;\n"
        "      IF human_review IS NULL THEN RAISE EXCEPTION 'checker locked review policy missing'"
        " USING ERRCODE='23514'; END IF;\n"
        "      -- A coverage gap never auto-accepts: a reviewer judges it, or it returns.\n"
        "      expected_route := CASE WHEN failed>0 OR (coverage_incomplete AND NOT human_review)"
        " THEN 'needs_revision' ELSE 'allow_review' END;",
    ),
)

# One definition of a coverage return, of an attempt's round and of a root
# revision window, shared by every guard that needs them.
ROUND_HELPERS = """
CREATE FUNCTION public.checker_run_coverage_return(run uuid) RETURNS boolean
LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
  SELECT coalesce((SELECT r.failed_count=0 AND EXISTS (
      SELECT 1 FROM public.checker_result_findings f
      WHERE f.checker_run_id=r.id AND f.level='coverage_incomplete')
    FROM public.checker_runs r WHERE r.id=run), false)
$$;

CREATE FUNCTION public.submission_revision_round(assignment uuid, through_version integer)
RETURNS bigint LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
  SELECT count(*)-1 FROM public.submissions counted
  WHERE counted.task_assignment_id=assignment AND counted.version<=through_version
    AND counted.status_reason IS DISTINCT FROM 'checker_coverage_incomplete'
$$;

-- Consecutive coverage returns keep the first return's window; any other
-- source opens a fresh locked-policy window at routing.
CREATE FUNCTION public.revision_window_origin(manifest uuid,
  OUT requested_at timestamptz, OUT deadline_at timestamptz, OUT inherited boolean)
LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
  SELECT CASE WHEN head.id IS NULL THEN m.created_at ELSE head.requested_at END,
    CASE WHEN head.id IS NULL
      THEN m.created_at+make_interval(hours=>policy.revision_deadline_hours)
      ELSE head.deadline_at END,
    head.id IS NOT NULL
  FROM public.task_post_submit_routing_manifests m
  JOIN public.submissions s ON s.id=m.submission_id
  JOIN public.revision_policies policy ON policy.id=s.locked_revision_policy_id
  LEFT JOIN public.submissions previous ON previous.id=s.supersedes_submission_id
    AND s.status_reason='checker_coverage_incomplete'
    AND previous.status_reason='checker_coverage_incomplete'
  LEFT JOIN public.task_revision_preparations head ON head.submission_id=previous.id
    AND NOT EXISTS (SELECT 1 FROM public.task_revision_preparations child
      WHERE child.predecessor_id=head.id)
  WHERE m.id=manifest
$$;
"""

# A coverage return spends no revision round: neither round count includes it.
_ROUND_COUNTS = {
    "public.guard_submission_revision_capacity()": (
        (
            """      WHERE s.task_assignment_id=NEW.task_assignment_id
        AND s.version<=predecessor.version;""",
            """      WHERE s.task_assignment_id=NEW.task_assignment_id
        AND s.version<=predecessor.version
        AND s.status_reason IS DISTINCT FROM 'checker_coverage_incomplete';""",
        ),
    ),
    "public.guard_revision_preparation()": (
        (
            " auth_context jsonb; auth_digest text; source_round integer;",
            " auth_context jsonb; auth_digest text; source_round integer;\n"
            " window_requested_at timestamptz; window_deadline_at timestamptz; window_inherited boolean;",
        ),
        (
            """   IF NEW.sequence<>1 OR NEW.requested_at IS DISTINCT FROM m.created_at
    OR (NEW.deadline_at IS NOT NULL AND NEW.deadline_at IS DISTINCT FROM
          m.created_at + make_interval(hours=>policy.revision_deadline_hours))
    OR (NEW.deadline_at IS NULL AND NEW.remaining_microseconds IS DISTINCT FROM
      CASE WHEN NEW.repair_actor_id IS NULL AND EXISTS(""",
            """   SELECT w.requested_at, w.deadline_at, w.inherited
     INTO window_requested_at, window_deadline_at, window_inherited
     FROM public.revision_window_origin(m.id) w;
   IF NEW.sequence<>1 OR NEW.requested_at IS DISTINCT FROM window_requested_at
    OR (NEW.deadline_at IS NOT NULL AND NEW.deadline_at IS DISTINCT FROM window_deadline_at)
    OR (NEW.deadline_at IS NULL AND NEW.remaining_microseconds IS DISTINCT FROM
      CASE WHEN NOT window_inherited AND NEW.repair_actor_id IS NULL AND EXISTS(""",
        ),
        (
            """      ELSE floor(extract(epoch FROM (m.created_at
       +make_interval(hours=>policy.revision_deadline_hours)-NEW.clock_observed_at))*1000000)::bigint END)
    OR NEW.max_revision_rounds IS DISTINCT FROM policy.max_revision_rounds""",
            """      ELSE floor(extract(epoch FROM (window_deadline_at-NEW.clock_observed_at))*1000000)::bigint END)
    OR NEW.max_revision_rounds IS DISTINCT FROM policy.max_revision_rounds""",
        ),
        (
            """ WHERE counted.task_assignment_id=NEW.assignment_id
   AND counted.version<=NEW.source_submission_version;""",
            """ WHERE counted.task_assignment_id=NEW.assignment_id
   AND counted.version<=NEW.source_submission_version
   AND counted.status_reason IS DISTINCT FROM 'checker_coverage_incomplete';""",
        ),
    ),
}

# #573's exhaustion guards count rounds with the shared helper, and a coverage
# return never exhausts: it spends no round and is bounded by its window.
_EXHAUSTION_ROUNDS = {
    "public.task_routing_context_valid(public.task_post_submit_routing_manifests)": (
        (
            """'revision_round',(SELECT count(*)-1 FROM public.submissions counted
              WHERE counted.task_assignment_id=m.assignment_id AND counted.version<=s.version),""",
            "'revision_round',public.submission_revision_round(m.assignment_id,s.version),",
        ),
    ),
    "public.guard_task_routing_authority()": (
        (
            """            AND (SELECT count(*)-1 FROM public.submissions counted
              WHERE counted.task_assignment_id=NEW.assignment_id AND counted.version<=s.version)
              >=p.max_revision_rounds""",
            """            AND public.submission_revision_round(NEW.assignment_id,s.version)>=p.max_revision_rounds
            AND NOT public.checker_run_coverage_return(NEW.checker_run_id)""",
        ),
    ),
    "public.guard_task_revision_exhaustion()": (
        (
            """ SELECT count(*)-1 INTO actual_round FROM public.submissions
  WHERE task_assignment_id=NEW.assignment_id AND version<=s.version;""",
            " actual_round:=public.submission_revision_round(NEW.assignment_id,s.version);",
        ),
        (
            "  OR m.routing_recommendation<>'needs_revision'\n",
            "  OR m.routing_recommendation<>'needs_revision'"
            " OR public.checker_run_coverage_return(m.checker_run_id)\n",
        ),
    ),
    "public.task_revision_exhaustion_complete(uuid)": (
        (
            """  OR e.revision_round IS DISTINCT FROM (SELECT count(*)-1 FROM public.submissions counted
     WHERE counted.task_assignment_id=e.assignment_id AND counted.version<=s.version)""",
            "  OR e.revision_round IS DISTINCT FROM public.submission_revision_round(e.assignment_id,s.version)",
        ),
    ),
    "public.guard_task_revision_expiration()": (
        (
            """    AND (SELECT count(*)-1 FROM public.submissions attempt
      WHERE attempt.task_assignment_id=source.task_assignment_id
       AND attempt.version<=source.version)>=policy.max_revision_rounds) THEN""",
            """    AND public.submission_revision_round(source.task_assignment_id,source.version)
      >=policy.max_revision_rounds) THEN""",
        ),
    ),
    "public.project_revision_preparation_clock()": (
        (" blocked boolean;", " blocked boolean; inherited boolean;"),
        (
            " original_deadline:=m.created_at+make_interval(hours=>policy.revision_deadline_hours);",
            " SELECT w.deadline_at, w.inherited INTO original_deadline, inherited\n"
            "  FROM public.revision_window_origin(m.id) w;",
        ),
        (
            "   NEW.remaining_microseconds:=CASE WHEN NEW.repair_actor_id IS NULL AND EXISTS(",
            "   NEW.remaining_microseconds:=CASE WHEN NOT inherited AND NEW.repair_actor_id IS NULL AND EXISTS(",
        ),
    ),
}

_ROUND_ZERO = """
ALTER TABLE public.task_revision_preparations
  DROP CONSTRAINT ck_task_revision_preparations_positive_rounds,
  ADD CONSTRAINT ck_task_revision_preparations_positive_rounds CHECK (
    sequence > 0 AND source_submission_version > 0 AND next_revision_round >= 0
    AND max_revision_rounds >= 0);
"""

# Backfills replay what each deciding owner would have written; tests run them
# against rows produced by the live owners to prove the two agree.
BACKFILL_SUBMISSION_ATTEMPTS = """
UPDATE public.submissions s SET attempt_status='review_pending'
  FROM public.task_post_submit_routing_manifests m
  WHERE m.submission_id=s.id AND m.routing_recommendation='allow_review'
    AND m.human_review_required;
UPDATE public.submissions s SET attempt_status='needs_revision', decided_at=m.created_at,
    status_reason=CASE WHEN public.checker_run_coverage_return(m.checker_run_id)
      THEN 'checker_coverage_incomplete' END
  FROM public.task_post_submit_routing_manifests m
  WHERE m.submission_id=s.id AND m.routing_recommendation='needs_revision';
UPDATE public.submissions s SET attempt_status='rejected',
    status_reason='revision_deadline_expired', decided_at=e.expired_at
  FROM public.task_revision_expirations e WHERE e.source_submission_id=s.id;
UPDATE public.submissions s SET attempt_status='rejected',
    status_reason='revision_limit_reached', decided_at=e.exhausted_at
  FROM public.task_revision_exhaustions e WHERE e.source_submission_id=s.id;
UPDATE public.submissions s SET attempt_status='accepted', decided_at=a.accepted_at,
    status_reason=NULL
  FROM public.final_acceptances a WHERE a.submission_id=s.id;
UPDATE public.submissions SET updated_at=greatest(submitted_at, coalesce(decided_at, submitted_at),
  coalesce((SELECT max(m.created_at) FROM public.task_post_submit_routing_manifests m
            WHERE m.submission_id=submissions.id), submitted_at));

"""

# Terminal revision assignments are immutable from 0048 onward. The backfill
# only adds the new derived columns, so the upgrade bypasses that guard for
# these two statements and restores it in the same transaction.
BACKFILL_ASSIGNMENT_STARTS = """
ALTER TABLE public.task_assignments DISABLE TRIGGER a_revision_terminal_assignment_immutable;
UPDATE public.task_assignments a SET started_at=(
  SELECT min(e.created_at) FROM public.audit_events e
  WHERE e.entity_type='task' AND e.entity_id=a.task_id
    AND e.event_type IN ('TaskStarted','TaskStartOverridden')
    AND e.created_at >= a.assigned_at
    AND (a.released_at IS NULL OR e.created_at <= a.released_at));
UPDATE public.task_assignments SET updated_at=greatest(assigned_at,
  coalesce(started_at, assigned_at), coalesce(released_at, assigned_at));
ALTER TABLE public.task_assignments ENABLE TRIGGER a_revision_terminal_assignment_immutable;

"""

_SUBMISSION_ATTEMPTS = """
ALTER TABLE public.submissions
  ADD COLUMN attempt_status character varying(30) DEFAULT 'evaluation_pending' NOT NULL,
  ADD COLUMN status_reason character varying(40),
  ADD COLUMN decided_at timestamp with time zone,
  ADD COLUMN updated_at timestamp with time zone DEFAULT now() NOT NULL;

ALTER TABLE public.submissions
  ADD CONSTRAINT ck_submissions_attempt_status CHECK (attempt_status in
    ('evaluation_pending','review_pending','accepted','needs_revision','rejected')),
  ADD CONSTRAINT ck_submissions_attempt_decision CHECK (
    (attempt_status in ('accepted','needs_revision','rejected')) = (decided_at is not null)),
  ADD CONSTRAINT ck_submissions_status_reason CHECK (status_reason is null or
    (attempt_status='rejected' and status_reason in ('revision_deadline_expired','revision_limit_reached')) or
    (attempt_status='needs_revision' and status_reason='checker_coverage_incomplete'));
CREATE INDEX ix_submissions_contributor_updated
  ON public.submissions USING btree (contributor_id, updated_at, id);

CREATE FUNCTION public.guard_submission_attempt_status() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE evidence_at timestamptz; coverage_reason text;
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
    -- A return without failed members is a checker coverage gap; it spends no round.
    SELECT m.created_at, CASE WHEN public.checker_run_coverage_return(m.checker_run_id)
      THEN 'checker_coverage_incomplete' END
      INTO evidence_at, coverage_reason
      FROM public.task_post_submit_routing_manifests m
      WHERE m.submission_id=OLD.id AND m.task_id=OLD.task_id
        AND m.routing_recommendation='needs_revision';
    NEW.decided_at := evidence_at; NEW.status_reason := coverage_reason;
  ELSIF OLD.attempt_status IN ('evaluation_pending','review_pending')
        AND NEW.attempt_status='accepted' THEN
    SELECT a.accepted_at INTO evidence_at FROM public.final_acceptances a
      WHERE a.submission_id=OLD.id AND a.task_id=OLD.task_id;
    NEW.decided_at := evidence_at; NEW.status_reason := NULL;
  ELSIF OLD.attempt_status IN ('evaluation_pending','needs_revision')
        AND NEW.attempt_status='rejected' THEN
    -- The last permitted attempt exhausts at routing, or at retained recovery.
    SELECT e.exhausted_at INTO evidence_at FROM public.task_revision_exhaustions e
      WHERE e.source_submission_id=OLD.id AND e.task_id=OLD.task_id;
    NEW.status_reason := 'revision_limit_reached';
    IF evidence_at IS NULL AND OLD.attempt_status='needs_revision' THEN
      SELECT e.expired_at INTO evidence_at FROM public.task_revision_expirations e
        WHERE e.source_submission_id=OLD.id AND e.task_id=OLD.task_id;
      NEW.status_reason := 'revision_deadline_expired';
    END IF;
    NEW.decided_at := evidence_at;
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
    refuse_incompatible_retained_findings(op.get_bind())
    _execute_script(_FINDINGS_TABLE)
    _replace("public.validate_checker_terminal_custody()", _TERMINAL_REPLACEMENTS)
    _replace("public.guard_dispatched_submission_immutable()", _DISPATCHED_IMMUTABLE)
    submission_columns, submission_guards = _SUBMISSION_ATTEMPTS.split(
        "ALTER TABLE public.submissions\n  ADD CONSTRAINT", 1,
    )
    _execute_script(submission_columns)
    _execute_script(ROUND_HELPERS)
    _execute_script(BACKFILL_SUBMISSION_ATTEMPTS)
    # Fire the deferred row checks the backfill queued so later DDL may proceed.
    op.execute("SET CONSTRAINTS ALL IMMEDIATE")
    _execute_script("ALTER TABLE public.submissions\n  ADD CONSTRAINT" + submission_guards)
    assignment_columns, assignment_guards = _ASSIGNMENTS_AND_TASKS.split(
        "CREATE INDEX ix_task_assignments_contributor_updated", 1,
    )
    _execute_script(assignment_columns)
    _execute_script(BACKFILL_ASSIGNMENT_STARTS)
    op.execute("SET CONSTRAINTS ALL IMMEDIATE")
    _execute_script("CREATE INDEX ix_task_assignments_contributor_updated" + assignment_guards)
    for signature, replacements in (_ROUND_COUNTS | _EXHAUSTION_ROUNDS).items():
        _replace(signature, replacements)
    _execute_script(_ROUND_ZERO)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
