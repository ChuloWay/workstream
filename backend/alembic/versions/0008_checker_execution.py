"""Replace unreleased checker execution custody without inventing retained lineage."""

from alembic import op

revision = "0008_checker_execution"
down_revision = "0007_checker_output_custody"
branch_labels = None
depends_on = None


def upgrade():
    """Refuse retained history before any schema change, then install exact custody."""
    op.execute("lock table checker_runs, checker_results in access exclusive mode")
    op.execute(
        "DO $$ BEGIN\nIF EXISTS (SELECT 1 FROM checker_runs) OR EXISTS (SELECT 1 FROM checker_results) THEN\n RAISE EXCEPTION 'retained checker history requires an explicit preservation design' USING ERRCODE='23514';\nEND IF; END $$"
    )
    op.execute(
        "ALTER TABLE checker_runs DROP CONSTRAINT fk_checker_runs_task_locked_payment_policy"
    )
    op.execute(
        "ALTER TABLE checker_runs DROP CONSTRAINT ck_checker_runs_post_submit_policy_lock_complete"
    )
    op.execute("ALTER TABLE checker_runs DROP CONSTRAINT uq_checker_runs_submission_attempt")
    op.execute("DROP INDEX uq_checker_runs_current_per_submission")
    op.execute("ALTER TABLE checker_runs DROP COLUMN triggered_by")
    op.execute("ALTER TABLE checker_runs DROP COLUMN triggered_by_subject")
    op.execute("ALTER TABLE checker_runs DROP COLUMN triggered_by_issuer")
    op.execute("ALTER TABLE checker_runs DROP COLUMN trigger_auth_source")
    op.execute("ALTER TABLE checker_runs DROP COLUMN trigger_reason")
    op.execute("ALTER TABLE checker_runs DROP COLUMN audit_event_id")
    op.execute("ALTER TABLE checker_runs DROP COLUMN attempt_number")
    op.execute("ALTER TABLE checker_runs DROP COLUMN is_current_for_submission")
    op.execute("ALTER TABLE checker_runs DROP COLUMN locked_post_submit_checker_policy_body")
    op.execute("ALTER TABLE checker_runs DROP COLUMN locked_payment_policy_version")
    op.execute("ALTER TABLE checker_runs DROP COLUMN package_hash")
    op.execute("ALTER TABLE checker_runs DROP COLUMN artifact_hash_manifest")
    op.execute("ALTER TABLE checker_runs DROP COLUMN artifact_manifest_hash")
    op.execute("ALTER TABLE checker_runs DROP COLUMN failure_message")
    op.execute("ALTER TABLE checker_results DROP COLUMN blocks_review")
    op.execute("ALTER TABLE checker_results DROP COLUMN message")
    op.execute("ALTER TABLE checker_results DROP COLUMN worker_message")
    op.execute("ALTER TABLE checker_results DROP COLUMN worker_suggested_fix")
    op.execute("ALTER TABLE checker_results DROP COLUMN worker_evidence_refs")
    op.execute("ALTER TABLE checker_results DROP COLUMN worker_visible")
    op.execute("ALTER TABLE checker_results DROP COLUMN metadata")
    op.execute("ALTER TABLE checker_runs ADD COLUMN project_id UUID NOT NULL")
    op.execute("ALTER TABLE checker_runs ADD COLUMN evaluation_request_id UUID NOT NULL")
    op.execute("ALTER TABLE checker_runs ADD COLUMN phase VARCHAR(30) NOT NULL")
    op.execute("ALTER TABLE checker_runs ADD COLUMN evaluation_generation INTEGER NOT NULL")
    op.execute("ALTER TABLE checker_runs ADD COLUMN request_json TEXT NOT NULL")
    op.execute("ALTER TABLE checker_runs ADD COLUMN request_digest VARCHAR(71) NOT NULL")
    op.execute("ALTER TABLE checker_runs ADD COLUMN worker_lease_id UUID")
    op.execute("ALTER TABLE checker_runs ADD COLUMN worker_lease_generation INTEGER NOT NULL")
    op.execute(
        "ALTER TABLE checker_runs ADD COLUMN worker_lease_expires_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute("ALTER TABLE checker_runs ADD COLUMN execute_evidence_id UUID")
    op.execute("ALTER TABLE checker_runs ADD COLUMN finalize_evidence_id UUID")
    op.execute("ALTER TABLE checker_runs ADD COLUMN result_id UUID NOT NULL")
    op.execute("ALTER TABLE checker_runs ADD COLUMN result_json TEXT")
    op.execute("ALTER TABLE checker_runs ADD COLUMN result_digest VARCHAR(71)")
    op.execute("ALTER TABLE checker_runs ADD COLUMN material_custody JSON")
    op.execute("ALTER TABLE checker_runs ADD COLUMN completion_event_id UUID")
    op.execute("ALTER TABLE checker_results ADD COLUMN member_order INTEGER NOT NULL")
    op.execute("ALTER TABLE checker_results ADD COLUMN definition_version VARCHAR(50) NOT NULL")
    op.execute(
        "ALTER TABLE checker_results ADD COLUMN implementation_version VARCHAR(100) NOT NULL"
    )
    op.execute("ALTER TABLE checker_results ADD COLUMN code VARCHAR(100) NOT NULL")
    op.execute("ALTER TABLE checker_results ADD COLUMN failure_category VARCHAR(40) NOT NULL")
    op.execute("ALTER TABLE checker_results ADD COLUMN counters JSON NOT NULL")
    op.execute(
        "ALTER TABLE checker_runs ADD CONSTRAINT ck_checker_runs_generations CHECK (evaluation_generation > 0 and worker_lease_generation >= 0)"
    )
    op.execute(
        "ALTER TABLE checker_runs ADD CONSTRAINT ck_checker_runs_phase CHECK (phase = 'post_submission')"
    )
    op.execute(
        "ALTER TABLE checker_runs ADD CONSTRAINT ck_checker_runs_request_digest CHECK (octet_length(request_json) <= 1048576 and request_digest = 'sha256:' || encode(sha256(convert_to(request_json, 'UTF8')), 'hex'))"
    )
    op.execute(
        "ALTER TABLE checker_runs ADD CONSTRAINT ck_checker_runs_result_digest CHECK (result_json is null or result_digest = 'sha256:' || encode(sha256(convert_to(result_json, 'UTF8')), 'hex'))"
    )
    op.execute(
        "ALTER TABLE checker_runs ADD CONSTRAINT ck_checker_runs_state CHECK (status in ('queued','running','completed','infrastructure_failed'))"
    )
    op.execute(
        "ALTER TABLE checker_runs ADD CONSTRAINT fk_checker_runs_completion_event_id_outbox_events FOREIGN KEY(completion_event_id) REFERENCES outbox_events (event_id)"
    )
    op.execute(
        "ALTER TABLE checker_runs ADD CONSTRAINT fk_checker_runs_task_project FOREIGN KEY(task_id, project_id) REFERENCES workstream_tasks (id, project_id)"
    )
    op.execute(
        "ALTER TABLE checker_runs ADD CONSTRAINT uq_checker_runs_generation UNIQUE (submission_id, phase, evaluation_generation)"
    )
    op.execute(
        "ALTER TABLE checker_runs ADD CONSTRAINT uq_checker_runs_request_phase UNIQUE (evaluation_request_id, phase)"
    )
    op.execute(
        "ALTER TABLE checker_runs ADD CONSTRAINT uq_checker_runs_result_id UNIQUE (result_id)"
    )
    op.execute(
        "ALTER TABLE checker_runs ADD CONSTRAINT uq_checker_runs_submission UNIQUE (id, submission_id)"
    )
    op.execute(
        "ALTER TABLE checker_results ADD CONSTRAINT ck_checker_results_member_order CHECK (member_order between 0 and 8)"
    )
    op.execute(
        "ALTER TABLE checker_results ADD CONSTRAINT uq_checker_results_member UNIQUE (checker_run_id, checker_name)"
    )
    op.execute(
        "ALTER TABLE checker_results ADD CONSTRAINT uq_checker_results_order UNIQUE (checker_run_id, member_order)"
    )
    op.execute("CREATE INDEX ix_checker_runs_project_id ON checker_runs (project_id)")
    op.execute(
        "\nCREATE TABLE checker_submission_fences (\n\tsubmission_id UUID NOT NULL, \n\tcurrent_run_id UUID NOT NULL, \n\tCONSTRAINT pk_checker_submission_fences PRIMARY KEY (submission_id), \n\tCONSTRAINT fk_checker_submission_fences_run FOREIGN KEY(current_run_id, submission_id) REFERENCES checker_runs (id, submission_id), \n\tCONSTRAINT fk_checker_submission_fences_submission_id_submissions FOREIGN KEY(submission_id) REFERENCES submissions (id), \n\tCONSTRAINT uq_checker_submission_fences_current_run_id UNIQUE (current_run_id)\n)\n\n"
    )
    _guards()
    _review_currentness_guards()


def downgrade() -> None:
    """Refuse downgrade without deleting or rewriting retained custody."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


def _guards():
    op.execute("""
    CREATE OR REPLACE FUNCTION protect_checker_run_custody() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE body jsonb; source submissions; mutable text[];
    BEGIN
      IF TG_OP IN ('DELETE','TRUNCATE') THEN
        RAISE EXCEPTION 'checker run custody is immutable' USING ERRCODE='23514';
      END IF;
      body := NEW.request_json::jsonb;
      IF TG_OP='INSERT' THEN
        IF NEW.status IS DISTINCT FROM 'queued' OR NEW.worker_lease_generation IS DISTINCT FROM 0 THEN
          RAISE EXCEPTION 'checker attempt must start queued' USING ERRCODE='23514';
        END IF;
        SELECT * INTO source FROM submissions WHERE id=NEW.submission_id AND task_id=NEW.task_id;
        IF NOT FOUND OR source.task_assignment_id::text IS DISTINCT FROM body->>'assignment_id'
          OR source.artifact_binding_id::text IS DISTINCT FROM body->>'binding_id'
          OR source.artifact_content_id::text IS DISTINCT FROM body->>'content_id'
          OR source.locked_post_submit_checker_policy_body::jsonb IS DISTINCT FROM body->'policy'
          OR body->>'project_id' IS DISTINCT FROM NEW.project_id::text
          OR body->>'task_id' IS DISTINCT FROM NEW.task_id::text
          OR body->>'submission_id' IS DISTINCT FROM NEW.submission_id::text
          OR body->>'submission_version' IS DISTINCT FROM NEW.submission_version::text
          OR body->>'evaluation_request_id' IS DISTINCT FROM NEW.evaluation_request_id::text
          OR body->>'evaluation_generation' IS DISTINCT FROM NEW.evaluation_generation::text
          OR body#>>'{expected_context,guide_version}' IS DISTINCT FROM NEW.locked_guide_version
          OR body#>>'{expected_context,post_policy_id}' IS DISTINCT FROM NEW.locked_post_submit_checker_policy_id::text
          OR body#>>'{expected_context,post_policy_version}' IS DISTINCT FROM NEW.locked_post_submit_checker_policy_version
          OR body#>>'{expected_context,post_policy_hash}' IS DISTINCT FROM NEW.locked_post_submit_checker_policy_hash
          OR body#>>'{expected_context,review_policy_id}' IS DISTINCT FROM NEW.locked_review_policy_id::text
          OR body#>>'{expected_context,review_generation}' IS DISTINCT FROM NEW.locked_review_policy_generation::text
          OR body#>>'{expected_context,review_hash}' IS DISTINCT FROM NEW.locked_review_policy_hash
          OR body#>>'{expected_context,revision_policy_id}' IS DISTINCT FROM NEW.locked_revision_policy_id::text
          OR body#>>'{expected_context,revision_generation}' IS DISTINCT FROM NEW.locked_revision_policy_generation::text
          OR body#>>'{expected_context,revision_hash}' IS DISTINCT FROM NEW.locked_revision_policy_hash THEN
          RAISE EXCEPTION 'checker request ownership or policy mismatch' USING ERRCODE='23514';
        END IF;
      ELSE
        mutable := ARRAY['status','routing_recommendation','outcome_source','worker_lease_id',
          'worker_lease_generation','worker_lease_expires_at','execute_evidence_id','finalize_evidence_id',
          'result_json','result_digest','material_custody','completion_event_id','passed_count',
          'warning_count','failed_count','blocking_count','started_at','completed_at','failure_code'];
        IF (to_jsonb(NEW)-mutable) IS DISTINCT FROM (to_jsonb(OLD)-mutable) THEN
          RAISE EXCEPTION 'checker run custody is immutable' USING ERRCODE='23514';
        END IF;
        IF OLD.status IN ('completed','infrastructure_failed') AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
          RAISE EXCEPTION 'checker run outcome is immutable' USING ERRCODE='23514';
        END IF;
        IF OLD.status IN ('completed','infrastructure_failed') THEN RETURN NEW; END IF;
        IF NOT EXISTS(SELECT 1 FROM checker_submission_fences WHERE submission_id=NEW.submission_id AND current_run_id=NEW.id) THEN
          RAISE EXCEPTION 'checker request is no longer current' USING ERRCODE='23514';
        END IF;
        IF NEW.status='running' THEN
          IF OLD.status NOT IN ('queued','running') OR NEW.worker_lease_generation IS DISTINCT FROM OLD.worker_lease_generation+1
            OR (OLD.status='running' AND OLD.worker_lease_expires_at > clock_timestamp())
            OR NEW.worker_lease_id IS NOT DISTINCT FROM OLD.worker_lease_id
            OR NEW.worker_lease_expires_at <= clock_timestamp()
            OR NEW.worker_lease_expires_at > clock_timestamp()+interval '1 hour'
            OR (OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at) THEN
            RAISE EXCEPTION 'checker lease progression is invalid' USING ERRCODE='23514';
          END IF;
        ELSIF NEW.status IN ('completed','infrastructure_failed') THEN
          IF OLD.status IS DISTINCT FROM 'running' OR OLD.worker_lease_expires_at <= clock_timestamp()
            OR NEW.worker_lease_id IS DISTINCT FROM OLD.worker_lease_id
            OR NEW.worker_lease_generation IS DISTINCT FROM OLD.worker_lease_generation
            OR NEW.worker_lease_expires_at IS DISTINCT FROM OLD.worker_lease_expires_at
            OR NEW.execute_evidence_id IS DISTINCT FROM OLD.execute_evidence_id
            OR NEW.started_at IS DISTINCT FROM OLD.started_at THEN
            RAISE EXCEPTION 'checker terminal lease is invalid' USING ERRCODE='23514';
          END IF;
        ELSE
          RAISE EXCEPTION 'checker state transition is invalid' USING ERRCODE='23514';
        END IF;
      END IF;
      IF NEW.status='queued' THEN
        IF NEW.worker_lease_id IS NOT NULL OR NEW.worker_lease_expires_at IS NOT NULL
          OR NEW.execute_evidence_id IS NOT NULL OR NEW.started_at IS NOT NULL THEN
          RAISE EXCEPTION 'checker queued custody is invalid' USING ERRCODE='23514';
        END IF;
      ELSIF NEW.worker_lease_id IS NULL OR NEW.worker_lease_expires_at IS NULL
        OR NEW.execute_evidence_id IS NULL OR NEW.started_at IS NULL OR NEW.worker_lease_generation < 1 THEN
        RAISE EXCEPTION 'checker active custody is incomplete' USING ERRCODE='23514';
      END IF;
      IF NEW.status IN ('queued','running') AND (NEW.result_json IS NOT NULL OR NEW.result_digest IS NOT NULL
        OR NEW.finalize_evidence_id IS NOT NULL OR NEW.material_custody IS NOT NULL OR NEW.completion_event_id IS NOT NULL
        OR NEW.completed_at IS NOT NULL OR NEW.failure_code IS NOT NULL OR NEW.routing_recommendation <> 'not_evaluated'
        OR NEW.outcome_source <> 'none' OR NEW.passed_count <> 0 OR NEW.warning_count <> 0 OR NEW.failed_count <> 0 OR NEW.blocking_count <> 0) THEN
        RAISE EXCEPTION 'unfinished checker run contains terminal facts' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$
    """)
    op.execute("DROP TRIGGER checker_run_custody ON checker_runs")
    op.execute(
        "CREATE TRIGGER checker_run_custody BEFORE INSERT OR UPDATE OR DELETE ON checker_runs FOR EACH ROW EXECUTE FUNCTION protect_checker_run_custody()"
    )
    op.execute("""
    CREATE FUNCTION protect_checker_submission_fence() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE current_run checker_runs; prior checker_runs;
    BEGIN
      IF TG_OP IN ('DELETE','TRUNCATE') THEN
        RAISE EXCEPTION 'checker currentness custody is immutable' USING ERRCODE='23514';
      END IF;
      SELECT * INTO current_run FROM checker_runs WHERE id=NEW.current_run_id AND submission_id=NEW.submission_id FOR UPDATE;
      IF NOT FOUND OR current_run.status IS DISTINCT FROM 'queued' THEN
        RAISE EXCEPTION 'checker fence requires exact queued run' USING ERRCODE='23514';
      END IF;
      IF TG_OP='INSERT' THEN
        IF current_run.evaluation_generation <> 1 OR current_run.supersedes_checker_run_id IS NOT NULL THEN
          RAISE EXCEPTION 'checker initial generation is invalid' USING ERRCODE='23514';
        END IF;
      ELSE
        SELECT * INTO prior FROM checker_runs WHERE id=OLD.current_run_id AND submission_id=OLD.submission_id FOR UPDATE;
        IF NOT FOUND OR NEW.submission_id IS DISTINCT FROM OLD.submission_id
          OR current_run.evaluation_generation IS DISTINCT FROM prior.evaluation_generation+1
          OR current_run.supersedes_checker_run_id IS DISTINCT FROM prior.id THEN
          RAISE EXCEPTION 'checker successor generation is invalid' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$
    """)
    op.execute(
        "CREATE TRIGGER checker_submission_fence_custody BEFORE INSERT OR UPDATE OR DELETE ON checker_submission_fences FOR EACH ROW EXECUTE FUNCTION protect_checker_submission_fence()"
    )
    op.execute(
        "CREATE TRIGGER checker_submission_fence_no_truncate BEFORE TRUNCATE ON checker_submission_fences FOR EACH STATEMENT EXECUTE FUNCTION protect_checker_submission_fence()"
    )
    op.execute("""
    CREATE OR REPLACE FUNCTION protect_checker_result_custody() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE parent checker_runs; entry jsonb; definition jsonb;
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'checker result custody is immutable' USING ERRCODE='23514';
      END IF;
      SELECT * INTO parent FROM checker_runs
      WHERE id=NEW.checker_run_id AND task_id=NEW.task_id AND submission_id=NEW.submission_id FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'checker result violates fk_checker_results_run_ownership'
          USING ERRCODE='23503', CONSTRAINT='fk_checker_results_run_ownership', TABLE='checker_results';
      END IF;
      IF parent.status IS DISTINCT FROM 'running' OR parent.completed_at IS NOT NULL THEN
        RAISE EXCEPTION 'finished or unclaimed checker run cannot receive results' USING ERRCODE='23514';
      END IF;
      entry := parent.request_json::jsonb #> ARRAY['policy','entries',NEW.member_order::text];
      -- Closed registered structural outcomes, independent of caller JSON claims.
      SELECT jsonb_build_object('failure_code',code,'failure_category',category,
          'failure_status',status,'failure_severity',severity) INTO definition
        FROM (VALUES
          ('check_submission_packet','packet_fields_missing','submission_structure','failed','high'),
          ('check_policy_context_present','policy_context_invalid','task_configuration','failed','high'),
          ('check_evidence_present','evidence_missing','submission_structure','failed','high'),
          ('check_evidence_integrity','evidence_structure_invalid','submission_structure','failed','high'),
          ('check_required_files','required_files_missing','submission_structure','failed','high'),
          ('check_forbidden_files','forbidden_path_present','submission_structure','failed','high'),
          ('check_confidentiality_attestation','attestation_missing','submission_structure','failed','high'),
          ('check_low_quality_generated_artifacts','placeholder_signal','submission_structure','warning','medium'),
          ('check_acceptance_criteria_present','acceptance_criteria_missing','task_configuration','failed','high')
        ) registered(checker,code,category,status,severity) WHERE checker=NEW.checker_name;
      IF NOT FOUND OR NEW.definition_version IS DISTINCT FROM 'v0.1'
        OR NEW.implementation_version IS DISTINCT FROM 'workstream-structural'
        OR entry->>'checker_id' IS DISTINCT FROM NEW.checker_name
        OR entry->>'definition_version' IS DISTINCT FROM NEW.definition_version
        OR entry->>'implementation_version' IS DISTINCT FROM NEW.implementation_version
        OR jsonb_typeof(NEW.counters::jsonb) IS DISTINCT FROM 'array' OR jsonb_array_length(NEW.counters::jsonb)>4 THEN
        RAISE EXCEPTION 'checker member differs from selected definition' USING ERRCODE='23514';
      END IF;
      IF EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.counters::jsonb) c
        WHERE jsonb_typeof(c) IS DISTINCT FROM 'object'
          OR c->>'key' IS NULL OR c->>'key' NOT IN ('artifact_count','missing_count','invalid_count','matched_count')
          OR jsonb_typeof(c->'value') IS DISTINCT FROM 'number'
          OR (c->>'value') !~ '^[0-9]{1,4}$' OR (c->>'value')::numeric > 1024
          OR c - ARRAY['key','value'] <> '{}'::jsonb)
        OR (SELECT count(*) FROM jsonb_array_elements(NEW.counters::jsonb)) <>
           (SELECT count(DISTINCT c->>'key') FROM jsonb_array_elements(NEW.counters::jsonb) c) THEN
        RAISE EXCEPTION 'checker member counters invalid' USING ERRCODE='23514';
      END IF;
      IF NEW.status='passed' THEN
        IF NEW.code IS DISTINCT FROM 'passed' OR NEW.failure_category IS DISTINCT FROM 'none' OR NEW.severity IS DISTINCT FROM 'info' THEN
          RAISE EXCEPTION 'checker passing member shape invalid' USING ERRCODE='23514';
        END IF;
      ELSIF NEW.status IS DISTINCT FROM definition->>'failure_status'
        OR NEW.code IS DISTINCT FROM definition->>'failure_code'
        OR NEW.failure_category IS DISTINCT FROM definition->>'failure_category'
        OR NEW.severity IS DISTINCT FROM definition->>'failure_severity' THEN
        RAISE EXCEPTION 'checker member outcome differs from definition' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$
    """)
    _terminal_guard()


def _terminal_guard():
    op.execute("""
    CREATE FUNCTION validate_checker_terminal_custody() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE current_run checker_runs; result jsonb; members jsonb; expected_route text;
      passed integer; warning integer; failed integer; blocking integer; setup integer; envelope jsonb;
    BEGIN
      SELECT * INTO current_run FROM checker_runs WHERE id=CASE WHEN TG_TABLE_NAME='checker_results'
        THEN (to_jsonb(NEW)->>'checker_run_id')::uuid ELSE NEW.id END;
      IF NOT FOUND THEN RAISE EXCEPTION 'checker run missing' USING ERRCODE='23514'; END IF;
      IF current_run.status IN ('queued','running') THEN
        IF EXISTS(SELECT 1 FROM checker_results WHERE checker_run_id=current_run.id) THEN
          RAISE EXCEPTION 'partial checker members cannot commit' USING ERRCODE='23514';
        END IF;
        IF NOT EXISTS(SELECT 1 FROM checker_submission_fences WHERE submission_id=current_run.submission_id) THEN
          RAISE EXCEPTION 'checker run requires currentness custody' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
      END IF;
      result := current_run.result_json::jsonb;
      IF result IS NULL OR current_run.result_digest IS NULL OR current_run.finalize_evidence_id IS NULL
        OR current_run.completed_at IS NULL OR current_run.outcome_source IS DISTINCT FROM 'auto_checker'
        OR result->>'outcome' IS DISTINCT FROM current_run.status
        OR result->>'request_id' IS DISTINCT FROM current_run.evaluation_request_id::text
        OR result->>'request_digest' IS DISTINCT FROM current_run.request_digest
        OR result->>'attempt_id' IS DISTINCT FROM current_run.id::text
        OR result->>'result_id' IS DISTINCT FROM current_run.result_id::text
        OR result->>'evaluation_generation' IS DISTINCT FROM current_run.evaluation_generation::text THEN
        RAISE EXCEPTION 'checker terminal identity incomplete' USING ERRCODE='23514';
      END IF;
      SELECT coalesce(jsonb_agg(jsonb_build_object(
        'schema_version','post_submit_structural_result','checker_id',checker_name,
        'definition_version',definition_version,'implementation_version',implementation_version,
        'status',status,'code',code,'failure_category',failure_category,'severity',severity,'counters',counters
      ) ORDER BY member_order), '[]'::jsonb),
        count(*) FILTER(WHERE status='passed'), count(*) FILTER(WHERE status='warning'), count(*) FILTER(WHERE status='failed'),
        count(*) FILTER(WHERE status<>'passed' AND current_run.request_json::jsonb #> '{policy,blocking_severities}' ? severity),
        count(*) FILTER(WHERE status<>'passed' AND failure_category='task_configuration'
          AND current_run.request_json::jsonb #> '{policy,blocking_severities}' ? severity)
      INTO members,passed,warning,failed,blocking,setup FROM checker_results WHERE checker_run_id=current_run.id;
      IF result->'member_results' IS DISTINCT FROM members OR current_run.passed_count IS DISTINCT FROM passed
        OR current_run.warning_count IS DISTINCT FROM warning OR current_run.failed_count IS DISTINCT FROM failed
        OR current_run.blocking_count IS DISTINCT FROM blocking THEN
        RAISE EXCEPTION 'checker terminal members differ' USING ERRCODE='23514';
      END IF;
      IF current_run.status='infrastructure_failed' THEN
        IF members <> '[]'::jsonb OR current_run.completion_event_id IS NOT NULL
          OR current_run.failure_code IS NULL OR current_run.failure_code NOT IN
            ('capacity_exceeded','deadline_exceeded','material_unavailable','implementation_unavailable','invalid_output')
          OR result->>'infrastructure_failure_code' IS DISTINCT FROM current_run.failure_code
          OR current_run.routing_recommendation IS DISTINCT FROM 'not_evaluated' THEN
          RAISE EXCEPTION 'checker infrastructure terminal shape invalid' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
      END IF;
      expected_route := CASE WHEN setup>0 THEN 'task_setup_blocked' WHEN blocking>0 THEN 'needs_revision' ELSE 'allow_review' END;
      IF current_run.status IS DISTINCT FROM 'completed' OR current_run.routing_recommendation IS DISTINCT FROM expected_route
        OR current_run.failure_code IS NOT NULL OR result->>'infrastructure_failure_code' IS NOT NULL
        OR jsonb_array_length(members) IS DISTINCT FROM jsonb_array_length(current_run.request_json::jsonb #> '{policy,entries}')
        OR current_run.material_custody IS NULL
        OR current_run.material_custody->>'submission_id' IS DISTINCT FROM current_run.submission_id::text
        OR current_run.material_custody->>'submission_version' IS DISTINCT FROM current_run.submission_version::text
        OR current_run.material_custody->>'binding_id' IS DISTINCT FROM current_run.request_json::jsonb->>'binding_id'
        OR current_run.material_custody->>'content_id' IS DISTINCT FROM current_run.request_json::jsonb->>'content_id'
        OR current_run.material_custody->>'content_sha256' IS DISTINCT FROM current_run.request_json::jsonb->>'content_sha256'
        OR current_run.material_custody->>'byte_count' IS DISTINCT FROM current_run.request_json::jsonb->>'byte_count' THEN
        RAISE EXCEPTION 'checker completed custody or routing invalid' USING ERRCODE='23514';
      END IF;
      SELECT payload INTO envelope FROM outbox_events WHERE event_id=current_run.completion_event_id
        AND event_type='PostSubmissionEvaluationCompleted' AND event_version=1
        AND project_id=current_run.project_id AND aggregate_id=current_run.id AND aggregate_type='checker_run';
      IF NOT FOUND OR envelope->>'project_id' IS DISTINCT FROM current_run.project_id::text
        OR envelope->>'task_id' IS DISTINCT FROM current_run.task_id::text
        OR envelope->>'submission_id' IS DISTINCT FROM current_run.submission_id::text
        OR envelope#>>'{reference,request_id}' IS DISTINCT FROM current_run.evaluation_request_id::text
        OR envelope#>>'{reference,request_digest}' IS DISTINCT FROM current_run.request_digest
        OR envelope#>>'{reference,evaluation_generation}' IS DISTINCT FROM current_run.evaluation_generation::text
        OR envelope#>>'{reference,attempt_id}' IS DISTINCT FROM current_run.id::text
        OR envelope#>>'{reference,result_id}' IS DISTINCT FROM current_run.result_id::text
        OR envelope#>>'{reference,result_digest}' IS DISTINCT FROM current_run.result_digest
        OR envelope->>'routing_recommendation' IS DISTINCT FROM expected_route
        OR envelope->'output_binding_ids' IS DISTINCT FROM '[]'::jsonb
        OR envelope->>'execute_evidence_id' IS DISTINCT FROM current_run.execute_evidence_id::text
        OR envelope->>'finalize_evidence_id' IS DISTINCT FROM current_run.finalize_evidence_id::text THEN
        RAISE EXCEPTION 'checker completion event differs' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$
    """)
    op.execute(
        "CREATE CONSTRAINT TRIGGER checker_terminal_custody AFTER INSERT OR UPDATE ON checker_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_checker_terminal_custody()"
    )

    op.execute(
        "CREATE CONSTRAINT TRIGGER checker_member_terminal_custody AFTER INSERT ON checker_results DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_checker_terminal_custody()"
    )


def _review_currentness_guards():
    """Keep existing hidden REV consumers on the sole CHECKERS currentness source."""
    op.execute("""
CREATE OR REPLACE FUNCTION public.guard_review_admission_record() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          task_project uuid;
          checker_row checker_runs%rowtype;
        begin
          if tg_op='DELETE' then
            raise exception 'review admission records cannot be deleted' using errcode='55000';
          end if;
          if tg_op='INSERT' and new.status <> 'pending' then
            raise exception 'review admission must begin pending' using errcode='23514';
          end if;
          if tg_op='INSERT' then
            new.created_at := statement_timestamp();
          end if;
          if tg_op='UPDATE' then
            if (new.id,new.idempotency_key,new.operation_id,new.request_digest,new.project_id,
                new.task_id,new.submission_id,new.submission_version,
                new.admitting_checker_run_id,new.created_at)
               is distinct from
               (old.id,old.idempotency_key,old.operation_id,old.request_digest,old.project_id,
                old.task_id,old.submission_id,old.submission_version,
                old.admitting_checker_run_id,old.created_at) then
              raise exception 'review admission identity is immutable' using errcode='55000';
            end if;
            if old.status <> 'pending' or new.status <> 'committed' then
              raise exception 'invalid review admission transition' using errcode='23514';
            end if;
          end if;
          select project_id into task_project from workstream_tasks where id=new.task_id;
          if task_project is null or task_project <> new.project_id then
            raise exception 'review admission task project mismatch' using errcode='23514';
          end if;
          select * into checker_row from checker_runs where id=new.admitting_checker_run_id;
          if not found or checker_row.task_id <> new.task_id
             or checker_row.submission_id <> new.submission_id
             or checker_row.submission_version <> new.submission_version then
            raise exception 'review admission checker lineage mismatch' using errcode='23514';
          end if;
          if new.status='committed' then
            perform 1 from checker_submission_fences f
              where f.submission_id=new.submission_id and f.current_run_id=new.admitting_checker_run_id
              for update;
            if not found then
              raise exception 'review admission checker is not admissible' using errcode='23514';
            end if;
            -- Identity was qualified above without a lock. Re-read the outcome
            -- only after retaining the sole fence through the caller commit.
            select * into checker_row from checker_runs where id=new.admitting_checker_run_id;
            if checker_row.status <> 'completed' or checker_row.routing_recommendation <> 'allow_review' then
              raise exception 'review admission checker is not admissible' using errcode='23514';
            end if;
          end if;
          return new;
        end $$;
    """)
    op.execute("""
CREATE OR REPLACE FUNCTION public.guard_review_queue_entry() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          task_project uuid;
          checker_row checker_runs%rowtype;
        begin
          if tg_op='DELETE' then
            raise exception 'review queue entries cannot be deleted' using errcode='55000';
          end if;
          if tg_op='INSERT' then
            if new.queue_state <> 'pending' then
              raise exception 'review queue must begin pending' using errcode='23514';
            end if;
            new.first_queued_at := statement_timestamp();
            new.available_since := new.first_queued_at;
            new.routing_generation := 1;
            new.lifecycle_generation := 1;
            new.created_at := new.first_queued_at;
          end if;
          if tg_op='UPDATE' then
            if (new.id,new.project_id,new.task_id,new.submission_id,new.submission_version,
                new.admitting_checker_run_id,new.first_queued_at,new.created_at)
               is distinct from
               (old.id,old.project_id,old.task_id,old.submission_id,old.submission_version,
                old.admitting_checker_run_id,old.first_queued_at,old.created_at) then
              raise exception 'review queue identity is immutable' using errcode='55000';
            end if;
            if old.queue_state='closed' and new.queue_state <> 'closed' then
              raise exception 'closed review queue entries cannot reopen' using errcode='23514';
            end if;
            if new.routing_generation < old.routing_generation
               or new.lifecycle_generation < old.lifecycle_generation then
              raise exception 'review queue generations cannot decrease' using errcode='23514';
            end if;
          end if;
          if new.preferred_reviewer_id is not null and not exists(
            select 1 from actor_profiles where id=new.preferred_reviewer_id and actor_kind='human'
          ) then
            raise exception 'preferred reviewer must be human' using errcode='23514';
          end if;
          if tg_op='UPDATE' then return new; end if;
          select project_id into task_project from workstream_tasks where id=new.task_id;
          if task_project is null or task_project <> new.project_id then
            raise exception 'review queue task project mismatch' using errcode='23514';
          end if;
          select * into checker_row from checker_runs where id=new.admitting_checker_run_id;
          if not found or checker_row.task_id <> new.task_id
             or checker_row.submission_id <> new.submission_id
             or checker_row.submission_version <> new.submission_version then
            raise exception 'review queue checker lineage mismatch' using errcode='23514';
          end if;
          perform 1 from checker_submission_fences f
            where f.submission_id=new.submission_id and f.current_run_id=new.admitting_checker_run_id
            for update;
          if not found then
            raise exception 'review queue checker is not admissible' using errcode='23514';
          end if;
          select * into checker_row from checker_runs where id=new.admitting_checker_run_id;
          if checker_row.status <> 'completed' or checker_row.routing_recommendation <> 'allow_review' then
            raise exception 'review queue checker is not admissible' using errcode='23514';
          end if;
          return new;
        end $$;
    """)
