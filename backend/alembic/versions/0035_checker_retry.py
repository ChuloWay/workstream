"""Retain exact Operator custody for terminal checker infrastructure retry."""

from alembic import op
import sqlalchemy as sa


revision = "0035_checker_retry"
down_revision = "0034_checker_replacement"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.create_table(
        "checker_retry_receipts",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("actor_profile_id", sa.Uuid(as_uuid=False), sa.ForeignKey("actor_profiles.id"), nullable=False),
        sa.Column("identity_link_id", sa.Uuid(as_uuid=False), sa.ForeignKey("actor_identity_links.id"), nullable=False),
        sa.Column("request_key", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("task_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("assignment_id", sa.Uuid(as_uuid=False), sa.ForeignKey("task_assignments.id"), nullable=False),
        sa.Column("submission_id", sa.Uuid(as_uuid=False), sa.ForeignKey("submissions.id"), nullable=False),
        sa.Column("submission_version", sa.Integer(), nullable=False),
        sa.Column("source_run_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("source_request_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("source_request_digest", sa.String(71), nullable=False),
        sa.Column("source_result_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("source_result_digest", sa.String(71), nullable=False),
        sa.Column("source_finalize_evidence_id", sa.Uuid(as_uuid=False), sa.ForeignKey("audit_events.id"), nullable=False),
        sa.Column("source_generation", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(100), nullable=False),
        sa.Column("successor_run_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("successor_request_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("successor_request_digest", sa.String(71), nullable=False),
        sa.Column("successor_result_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("successor_generation", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("outbox_events.event_id"), nullable=False),
        sa.Column("audit_event_id", sa.Uuid(as_uuid=False), sa.ForeignKey("audit_events.id"), nullable=False),
        sa.Column("authorization_decision_id", sa.Uuid(as_uuid=False), sa.ForeignKey("audit_events.id"), nullable=False),
        sa.Column("resource_digest", sa.String(71), nullable=False),
        sa.Column("resource_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        sa.CheckConstraint("successor_generation = source_generation + 1 and source_generation > 0", name="generation"),
        sa.CheckConstraint("length(reason) between 1 and 500 and reason !~ '[[:cntrl:]]'", name="reason"),
        sa.CheckConstraint("source_request_digest ~ '^sha256:[0-9a-f]{64}$' and source_result_digest ~ '^sha256:[0-9a-f]{64}$' and successor_request_digest ~ '^sha256:[0-9a-f]{64}$' and resource_digest ~ '^sha256:[0-9a-f]{64}$'", name="digests"),
        sa.CheckConstraint("octet_length(resource_json) <= 8192 and resource_json = public.project_guide_projection_canonical_json(resource_json::jsonb) and resource_digest = 'sha256:' || encode(sha256(convert_to(resource_json, 'UTF8')), 'hex')", name="resource_json_digest"),
        sa.UniqueConstraint("actor_profile_id", "request_key", name="uq_checker_retry_actor_key"),
        sa.UniqueConstraint("source_run_id", name="uq_checker_retry_source"),
        sa.UniqueConstraint("successor_run_id", name="uq_checker_retry_successor"),
        sa.UniqueConstraint("event_id", name="uq_checker_retry_event"),
        sa.UniqueConstraint("audit_event_id", name="uq_checker_retry_audit"),
        sa.ForeignKeyConstraint(["source_run_id", "task_id", "submission_id"], ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"], name="fk_checker_retry_source_ownership"),
        sa.ForeignKeyConstraint(["successor_run_id", "task_id", "submission_id"], ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"], name="fk_checker_retry_successor_ownership"),
        schema="public",
    )

    op.execute("""
    CREATE FUNCTION public.checker_retry_receipt_valid(receipt_id uuid) RETURNS boolean
    LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE r public.checker_retry_receipts%ROWTYPE;
      source public.checker_runs%ROWTYPE; successor public.checker_runs%ROWTYPE;
      authority public.audit_events%ROWTYPE; initiation public.audit_events%ROWTYPE;
      request_event public.outbox_events%ROWTYPE; body jsonb; prepared jsonb;
      source_body jsonb; successor_body jsonb;
    BEGIN
      SELECT * INTO r FROM public.checker_retry_receipts WHERE id=receipt_id;
      IF NOT FOUND THEN RETURN false; END IF;
      SELECT * INTO source FROM public.checker_runs WHERE id=r.source_run_id;
      IF NOT FOUND THEN RETURN false; END IF;
      SELECT * INTO successor FROM public.checker_runs WHERE id=r.successor_run_id;
      IF NOT FOUND THEN RETURN false; END IF;
      SELECT * INTO authority FROM public.audit_events WHERE id=r.authorization_decision_id;
      IF NOT FOUND THEN RETURN false; END IF;
      SELECT * INTO initiation FROM public.audit_events WHERE id=r.audit_event_id;
      IF NOT FOUND THEN RETURN false; END IF;
      SELECT * INTO request_event FROM public.outbox_events WHERE event_id=r.event_id;
      IF NOT FOUND THEN RETURN false; END IF;
      body := r.resource_json::jsonb->'resource_context';
      prepared := body->'preparation';
      source_body := prepared->'source';
      successor_body := body->'successor';
      IF body IS NULL OR prepared IS NULL OR source_body IS NULL OR successor_body IS NULL
        OR r.resource_json::jsonb - 'resource_context' <> '{}'::jsonb
        OR body - ARRAY['resource_type','resource_id','project_id','identity_link_id','preparation','successor'] <> '{}'::jsonb
        OR prepared - ARRAY['actor_profile_id','request_key','reason','source'] <> '{}'::jsonb
        OR source_body - ARRAY['project_id','task_id','assignment_id','submission_id','submission_version','source_run_id','source_request_id','source_request_digest','source_result_id','source_result_digest','source_finalize_evidence_id','source_generation','failure_code'] <> '{}'::jsonb
        OR successor_body - ARRAY['request_id','request_digest','run_id','result_id','generation','event_id','audit_event_id'] <> '{}'::jsonb
        OR body->>'resource_type' IS DISTINCT FROM 'checker_run'
        OR body->>'resource_id' IS DISTINCT FROM r.source_run_id::text
        OR body->>'project_id' IS DISTINCT FROM r.project_id::text
        OR body->>'identity_link_id' IS DISTINCT FROM r.identity_link_id::text
        OR prepared->>'actor_profile_id' IS DISTINCT FROM r.actor_profile_id::text
        OR prepared->>'request_key' IS DISTINCT FROM r.request_key::text
        OR prepared->>'reason' IS DISTINCT FROM r.reason
        OR source_body->>'project_id' IS DISTINCT FROM r.project_id::text
        OR source_body->>'task_id' IS DISTINCT FROM r.task_id::text
        OR source_body->>'assignment_id' IS DISTINCT FROM r.assignment_id::text
        OR source_body->>'submission_id' IS DISTINCT FROM r.submission_id::text
        OR source_body->>'submission_version' IS DISTINCT FROM r.submission_version::text
        OR source_body->>'source_run_id' IS DISTINCT FROM r.source_run_id::text
        OR source_body->>'source_request_id' IS DISTINCT FROM r.source_request_id::text
        OR source_body->>'source_request_digest' IS DISTINCT FROM r.source_request_digest
        OR source_body->>'source_result_id' IS DISTINCT FROM r.source_result_id::text
        OR source_body->>'source_result_digest' IS DISTINCT FROM r.source_result_digest
        OR source_body->>'source_finalize_evidence_id' IS DISTINCT FROM r.source_finalize_evidence_id::text
        OR source_body->>'source_generation' IS DISTINCT FROM r.source_generation::text
        OR source_body->>'failure_code' IS DISTINCT FROM r.failure_code
        OR successor_body->>'request_id' IS DISTINCT FROM r.successor_request_id::text
        OR successor_body->>'request_digest' IS DISTINCT FROM r.successor_request_digest
        OR successor_body->>'run_id' IS DISTINCT FROM r.successor_run_id::text
        OR successor_body->>'result_id' IS DISTINCT FROM r.successor_result_id::text
        OR successor_body->>'generation' IS DISTINCT FROM r.successor_generation::text
        OR successor_body->>'event_id' IS DISTINCT FROM r.event_id::text
        OR successor_body->>'audit_event_id' IS DISTINCT FROM r.audit_event_id::text
      THEN RETURN false; END IF;
      IF source.status IS DISTINCT FROM 'infrastructure_failed'
        OR source.project_id IS DISTINCT FROM r.project_id
        OR source.task_id IS DISTINCT FROM r.task_id
        OR source.submission_id IS DISTINCT FROM r.submission_id
        OR source.submission_version IS DISTINCT FROM r.submission_version
        OR source.evaluation_request_id IS DISTINCT FROM r.source_request_id
        OR source.request_digest IS DISTINCT FROM r.source_request_digest
        OR source.result_id IS DISTINCT FROM r.source_result_id
        OR source.result_digest IS DISTINCT FROM r.source_result_digest
        OR source.finalize_evidence_id IS DISTINCT FROM r.source_finalize_evidence_id
        OR source.evaluation_generation IS DISTINCT FROM r.source_generation
        OR source.failure_code IS DISTINCT FROM r.failure_code
        OR source.result_json::jsonb->>'outcome' IS DISTINCT FROM 'infrastructure_failed'
        OR source.result_json::jsonb->>'infrastructure_failure_code' IS DISTINCT FROM r.failure_code
        OR source.completion_event_id IS NOT NULL
        OR source.request_json::jsonb->>'assignment_id' IS DISTINCT FROM r.assignment_id::text
        OR successor.status IS DISTINCT FROM 'queued'
        OR successor.project_id IS DISTINCT FROM r.project_id
        OR successor.task_id IS DISTINCT FROM r.task_id
        OR successor.submission_id IS DISTINCT FROM r.submission_id
        OR successor.submission_version IS DISTINCT FROM r.submission_version
        OR successor.evaluation_request_id IS DISTINCT FROM r.successor_request_id
        OR successor.request_digest IS DISTINCT FROM r.successor_request_digest
        OR successor.result_id IS DISTINCT FROM r.successor_result_id
        OR successor.evaluation_generation IS DISTINCT FROM r.successor_generation
        OR successor.supersedes_checker_run_id IS DISTINCT FROM source.id
        OR successor.request_json::jsonb - ARRAY['evaluation_request_id','evaluation_generation']
           IS DISTINCT FROM source.request_json::jsonb - ARRAY['evaluation_request_id','evaluation_generation']
        OR NOT EXISTS (SELECT 1 FROM public.checker_submission_fences f
            WHERE f.submission_id=r.submission_id AND f.current_run_id=successor.id)
      THEN RETURN false; END IF;
      IF authority.event_domain IS DISTINCT FROM 'authority'
        OR authority.event_type IS DISTINCT FROM 'SensitiveAuthorizationAllowed'
        OR authority.actor_ref_kind IS DISTINCT FROM 'actor_profile'
        OR authority.actor_id IS DISTINCT FROM r.actor_profile_id::text
        OR authority.action_id IS DISTINCT FROM 'operations.checker.retry'
        OR authority.permission_id IS DISTINCT FROM 'operations.checker.retry'
        OR authority.project_id IS DISTINCT FROM r.project_id
        OR authority.resource_type IS DISTINCT FROM 'checker_run'
        OR authority.resource_id IS DISTINCT FROM r.source_run_id::text
        OR authority.target_ref_kind IS DISTINCT FROM 'project'
        OR authority.target_ref_id IS DISTINCT FROM r.project_id::text
        OR authority.request_id IS DISTINCT FROM r.request_key
        OR authority.correlation_id IS DISTINCT FROM r.request_key
        OR authority.denial_code IS NOT NULL
        OR authority.after_facts::jsonb IS DISTINCT FROM jsonb_build_object(
            'allowed',true,'resource_context_digest',r.resource_digest)
        OR NOT EXISTS (SELECT 1 FROM public.actor_profiles p
            WHERE p.id=r.actor_profile_id AND p.actor_kind='human' AND p.status='active')
        OR NOT EXISTS (SELECT 1 FROM public.admin_role_grants g
            WHERE g.id::text=authority.matched_grant_id
              AND g.target_actor_profile_id=r.actor_profile_id
              AND g.role='operator' AND g.scope_type='system'
              AND g.scope_project_id IS NULL AND g.status='active')
        OR NOT EXISTS (SELECT 1 FROM public.actor_identity_links link
            WHERE link.id=r.identity_link_id AND link.actor_profile_id=r.actor_profile_id
              AND link.status='active')
      THEN RETURN false; END IF;
      IF initiation.event_domain IS DISTINCT FROM 'legacy_lifecycle'
        OR initiation.auth_source IS DISTINCT FROM 'local_lifecycle'
        OR initiation.entity_type IS DISTINCT FROM 'checker_run'
        OR initiation.entity_id IS DISTINCT FROM r.successor_run_id
        OR initiation.event_type IS DISTINCT FROM 'CheckerRetryRequested'
        OR initiation.actor_id IS DISTINCT FROM r.actor_profile_id::text
        OR initiation.reason IS DISTINCT FROM 'lifecycle_fact_recorded'
        OR initiation.event_payload::jsonb IS DISTINCT FROM jsonb_build_object(
            'references', jsonb_build_object(
                'project_id',r.project_id::text,'task_id',r.task_id::text,
                'assignment_id',r.assignment_id::text,'submission_id',r.submission_id::text,
                'checker_run_id',r.successor_run_id::text,
                'source_checker_run_id',r.source_run_id::text,
                'authorization_decision_id',r.authorization_decision_id::text,
                'outbox_event_id',r.event_id::text),
            'operator_reason',r.reason,
            'authorization_resource_digest',r.resource_digest)
      THEN RETURN false; END IF;
      IF request_event.event_type IS DISTINCT FROM 'PostSubmissionEvaluationRequested'
        OR request_event.event_version IS DISTINCT FROM 1
        OR request_event.producer IS DISTINCT FROM 'workstream'
        OR request_event.aggregate_type IS DISTINCT FROM 'submission'
        OR request_event.aggregate_id IS DISTINCT FROM r.submission_id
        OR request_event.project_id IS DISTINCT FROM r.project_id
        OR request_event.correlation_id IS DISTINCT FROM r.source_run_id::text
        OR request_event.causation_event_id IS NOT NULL
        OR request_event.idempotency_key IS DISTINCT FROM 'checker-retry:'||r.source_run_id::text
        OR request_event.payload_digest IS DISTINCT FROM 'sha256:' || encode(sha256(convert_to(
            public.project_guide_projection_canonical_json(request_event.payload), 'UTF8')), 'hex')
        OR request_event.payload IS DISTINCT FROM jsonb_build_object(
            'project_id',r.project_id::text,'task_id',r.task_id::text,
            'submission_id',r.submission_id::text,'submission_version',r.submission_version,
            'request_id',r.successor_request_id::text,
            'request_digest',r.successor_request_digest,
            'evaluation_generation',r.successor_generation,
            'attempt_id',r.successor_run_id::text,'result_id',r.successor_result_id::text,
            'source_run_id',r.source_run_id::text,
            'source_result_digest',r.source_result_digest,
            'retry_receipt_id',r.id::text)
      THEN RETURN false; END IF;
      RETURN true;
    END $$
    """)
    op.execute("""
    CREATE FUNCTION public.guard_checker_retry_receipt() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'checker retry receipt is immutable' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$
    """)
    op.execute("CREATE TRIGGER checker_retry_receipt_immutable BEFORE INSERT OR UPDATE OR DELETE ON public.checker_retry_receipts FOR EACH ROW EXECUTE FUNCTION public.guard_checker_retry_receipt()")
    op.execute("CREATE TRIGGER checker_retry_receipt_no_truncate BEFORE TRUNCATE ON public.checker_retry_receipts FOR EACH STATEMENT EXECUTE FUNCTION public.guard_checker_retry_receipt()")
    op.execute("""
    CREATE FUNCTION public.validate_checker_retry_receipt() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
    BEGIN
      IF NOT public.checker_retry_receipt_valid(NEW.id) THEN
        RAISE EXCEPTION 'checker retry receipt closure invalid' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$
    """)
    op.execute("CREATE CONSTRAINT TRIGGER checker_retry_receipt_closure AFTER INSERT ON public.checker_retry_receipts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_checker_retry_receipt()")
    op.execute("""
    CREATE FUNCTION public.require_checker_failed_supersession_receipt() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE prior public.checker_runs%ROWTYPE; receipt_id uuid;
    BEGIN
      IF TG_OP <> 'UPDATE' THEN RETURN NULL; END IF;
      SELECT * INTO prior FROM public.checker_runs WHERE id=OLD.current_run_id;
      IF prior.status IS DISTINCT FROM 'infrastructure_failed' THEN RETURN NULL; END IF;
      SELECT id INTO receipt_id FROM public.checker_retry_receipts
        WHERE source_run_id=OLD.current_run_id AND successor_run_id=NEW.current_run_id;
      IF receipt_id IS NULL OR NOT public.checker_retry_receipt_valid(receipt_id) THEN
        RAISE EXCEPTION 'terminal checker infrastructure retry requires Operator receipt' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$
    """)
    op.execute("CREATE CONSTRAINT TRIGGER checker_failed_supersession_receipt AFTER UPDATE ON public.checker_submission_fences DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_checker_failed_supersession_receipt()")


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
