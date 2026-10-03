"""Reserve immutable TASK routing requests without source publication or authority."""

from alembic import op

revision = "0018_task_routing_request"
down_revision = "0017_acceptance_source_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
    op.execute("""

CREATE TABLE public.task_post_submit_routing_requests (
	route_operation_id UUID NOT NULL,
	routing_manifest_id UUID NOT NULL,
	project_id UUID NOT NULL,
	task_id UUID NOT NULL,
	submission_id UUID NOT NULL,
	submission_version INTEGER NOT NULL,
	checker_run_id UUID NOT NULL,
	evaluation_request_id UUID NOT NULL,
	evaluation_request_digest VARCHAR(71) NOT NULL,
	evaluation_generation INTEGER NOT NULL,
	result_id UUID NOT NULL,
	result_digest VARCHAR(71) NOT NULL,
	completion_event_id UUID NOT NULL,
	routing_recommendation VARCHAR(30) NOT NULL,
	route_request_digest VARCHAR(71) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	CONSTRAINT pk_task_post_submit_routing_requests PRIMARY KEY (route_operation_id),
	CONSTRAINT ck_task_post_submit_routing_requests_request_ids_uuid7 CHECK ((get_byte(uuid_send(route_operation_id), 6) >> 4) = 7 and (get_byte(uuid_send(route_operation_id), 8) & 192) = 128 and (get_byte(uuid_send(routing_manifest_id), 6) >> 4) = 7 and (get_byte(uuid_send(routing_manifest_id), 8) & 192) = 128),
	CONSTRAINT ck_task_post_submit_routing_requests_distinct_request_ids CHECK (route_operation_id <> routing_manifest_id and route_operation_id not in (evaluation_request_id, result_id, completion_event_id) and routing_manifest_id not in (evaluation_request_id, result_id, completion_event_id)),
	CONSTRAINT ck_task_post_submit_routing_requests_positive_versions CHECK (submission_version > 0 and evaluation_generation > 0),
	CONSTRAINT ck_task_post_submit_routing_requests_allow_review_only CHECK (routing_recommendation = 'allow_review'),
	CONSTRAINT ck_task_post_submit_routing_requests_request_digests CHECK (evaluation_request_digest ~ '^sha256:[0-9a-f]{64}$' and result_digest ~ '^sha256:[0-9a-f]{64}$' and route_request_digest ~ '^sha256:[0-9a-f]{64}$' and route_request_digest <> evaluation_request_digest),
	CONSTRAINT fk_task_route_request_task_project FOREIGN KEY(task_id, project_id) REFERENCES public.workstream_tasks (id, project_id) ON DELETE RESTRICT,
	CONSTRAINT fk_task_route_request_submission FOREIGN KEY(submission_id, task_id, submission_version) REFERENCES public.submissions (id, task_id, version) ON DELETE RESTRICT,
	CONSTRAINT fk_task_route_request_checker FOREIGN KEY(checker_run_id, task_id, submission_id) REFERENCES public.checker_runs (id, task_id, submission_id) ON DELETE RESTRICT,
	CONSTRAINT uq_task_route_request_manifest UNIQUE (routing_manifest_id),
	CONSTRAINT uq_task_route_request_completion UNIQUE (completion_event_id),
	CONSTRAINT uq_task_route_request_source UNIQUE (submission_id, checker_run_id, result_digest),
	CONSTRAINT fk_task_route_request_event FOREIGN KEY(completion_event_id) REFERENCES public.outbox_events (event_id) ON DELETE RESTRICT
)


""")
    _install_guards()


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


def _install_guards() -> None:
    op.execute("""
CREATE FUNCTION public.guard_task_routing_request() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    task_id uuid;
    submission public.submissions%ROWTYPE;
    fence public.checker_submission_fences%ROWTYPE;
    run public.checker_runs%ROWTYPE;
    selection jsonb;
    expected_payload jsonb;
    expected_digest text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'task routing request is immutable' USING ERRCODE='55000';
    END IF;
    NEW.created_at := pg_catalog.clock_timestamp();
    SELECT t.id INTO task_id FROM public.workstream_tasks t
      WHERE t.id = NEW.task_id AND t.project_id = NEW.project_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task routing request task mismatch' USING ERRCODE='23514';
    END IF;
    SELECT s.* INTO submission FROM public.submissions s
      WHERE s.id = NEW.submission_id AND s.task_id = NEW.task_id FOR UPDATE;
    IF NOT FOUND OR submission.version IS DISTINCT FROM NEW.submission_version
       OR submission.status IS DISTINCT FROM 'submitted'
       OR EXISTS (SELECT 1 FROM public.submissions s WHERE s.task_id = NEW.task_id
                  AND s.version > NEW.submission_version) THEN
        RAISE EXCEPTION 'task routing request submission mismatch' USING ERRCODE='23514';
    END IF;
    -- Qualify the requested owner before locking its currentness fence.
    SELECT f.* INTO fence FROM public.checker_submission_fences f
      WHERE f.submission_id = NEW.submission_id AND EXISTS (
        SELECT 1 FROM public.checker_runs r WHERE r.id = f.current_run_id
          AND r.id = NEW.checker_run_id AND r.project_id = NEW.project_id
          AND r.task_id = NEW.task_id AND r.submission_id = NEW.submission_id
      ) FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task routing request currentness mismatch' USING ERRCODE='23514';
    END IF;
    SELECT r.* INTO run FROM public.checker_runs r
      WHERE r.id = fence.current_run_id AND r.project_id = NEW.project_id
        AND r.task_id = NEW.task_id AND r.submission_id = NEW.submission_id FOR UPDATE;
    IF NOT FOUND OR run.id IS DISTINCT FROM NEW.checker_run_id
       OR run.submission_version IS DISTINCT FROM NEW.submission_version
       OR run.evaluation_request_id IS DISTINCT FROM NEW.evaluation_request_id
       OR run.request_digest IS DISTINCT FROM NEW.evaluation_request_digest
       OR run.evaluation_generation IS DISTINCT FROM NEW.evaluation_generation
       OR run.result_id IS DISTINCT FROM NEW.result_id
       OR run.result_digest IS DISTINCT FROM NEW.result_digest
       OR run.completion_event_id IS DISTINCT FROM NEW.completion_event_id
       OR run.status IS DISTINCT FROM 'completed'
       OR run.routing_recommendation IS DISTINCT FROM 'allow_review'
       OR NEW.routing_recommendation IS DISTINCT FROM 'allow_review'
       OR run.outcome_source IS DISTINCT FROM 'auto_checker'
       OR run.execute_evidence_id IS NULL OR run.finalize_evidence_id IS NULL
       OR run.execute_evidence_id IS NOT DISTINCT FROM run.finalize_evidence_id
       OR public.checker_post_submit_receipt_valid(run, 'execute', false) IS NOT TRUE
       OR public.checker_post_submit_receipt_valid(run, 'finalize', false) IS NOT TRUE
       OR public.art_submission_material_matches(
          run.project_id, run.task_id, run.submission_id, run.submission_version, run.material_custody::jsonb
       ) IS NOT TRUE THEN
        RAISE EXCEPTION 'task routing request checker mismatch' USING ERRCODE='23514';
    END IF;
    expected_payload := pg_catalog.jsonb_build_object(
        'project_id', NEW.project_id, 'task_id', NEW.task_id,
        'submission_id', NEW.submission_id,
        'reference', pg_catalog.jsonb_build_object(
            'schema_version', 'post_submit_current_result_reference',
            'request_id', NEW.evaluation_request_id,
            'request_digest', NEW.evaluation_request_digest,
            'attempt_id', NEW.checker_run_id,
            'evaluation_generation', NEW.evaluation_generation,
            'result_id', NEW.result_id, 'result_digest', NEW.result_digest
        ),
        'routing_recommendation', 'allow_review', 'output_binding_ids', '[]'::jsonb,
        'execute_evidence_id', run.execute_evidence_id,
        'finalize_evidence_id', run.finalize_evidence_id
    );
    IF NOT EXISTS (
        SELECT 1 FROM public.outbox_events e WHERE e.event_id = NEW.completion_event_id
          AND e.event_type = 'PostSubmissionEvaluationCompleted' AND e.event_version = 1
          AND e.project_id = NEW.project_id AND e.aggregate_type = 'checker_run'
          AND e.aggregate_id = NEW.checker_run_id
          AND e.correlation_id = NEW.evaluation_request_id::text
          AND e.idempotency_key = 'checker-completed:' || NEW.checker_run_id::text
          AND e.payload = expected_payload
    ) THEN
        RAISE EXCEPTION 'task routing request event mismatch' USING ERRCODE='23514';
    END IF;
    selection := pg_catalog.to_jsonb(NEW) - ARRAY[
        'route_operation_id', 'routing_manifest_id', 'created_at', 'route_request_digest'
    ];
    expected_digest := 'sha256:' || pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
        public.project_guide_projection_canonical_json(pg_catalog.jsonb_build_object(
            'domain', 'workstream.task_post_submit_route_request.v0.1',
            'action', 'task.post_submit.route', 'selection', selection
        )), 'UTF8'
    )), 'hex');
    IF NEW.route_request_digest IS DISTINCT FROM expected_digest THEN
        RAISE EXCEPTION 'task routing request digest mismatch' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
""")
    op.execute("""
CREATE TRIGGER task_routing_request_custody BEFORE INSERT OR UPDATE OR DELETE
ON public.task_post_submit_routing_requests FOR EACH ROW
EXECUTE FUNCTION public.guard_task_routing_request();
""")
    op.execute("""
CREATE TRIGGER task_routing_request_no_truncate BEFORE TRUNCATE
ON public.task_post_submit_routing_requests FOR EACH STATEMENT
EXECUTE FUNCTION public.guard_task_routing_request();
""")
