"""Commit new bound Submissions with exact authority and initial dispatch custody."""

from alembic import op
import sqlalchemy as sa

revision = "0025_submission_dispatch"
down_revision = "0024_require_second_review_false"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
    op.create_table("submission_binding_receipts",
        sa.Column("admission_id", sa.Uuid(), sa.ForeignKey("public.submission_bundle_admissions.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("binding_id", sa.Uuid(), sa.ForeignKey("public.artifact_bindings.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("decision_id", sa.Uuid(), sa.ForeignKey("public.audit_events.id", ondelete="RESTRICT"), nullable=False, unique=True),
        schema="public")
    op.create_table("submission_dispatches",
        sa.Column("submission_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("contributor_id", sa.Uuid(), nullable=False),
        sa.Column("admission_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_binding_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_content_id", sa.Uuid(), nullable=False),
        sa.Column("creation_decision_id", sa.Uuid(), nullable=False),
        sa.Column("binding_decision_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_request_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_result_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_event_id", sa.Uuid(), nullable=False),
        sa.Column("submission_version", sa.Integer(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("evaluation_request_digest", sa.String(71), nullable=False),
        sa.Column("creation_kind", sa.String(16), nullable=False),
        sa.Column("creation_status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id", "project_id"], ["public.workstream_tasks.id", "public.workstream_tasks.project_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submission_id", "task_id", "submission_version"], ["public.submissions.id", "public.submissions.task_id", "public.submissions.version"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assignment_id", "task_id", "contributor_id"], ["public.task_assignments.id", "public.task_assignments.task_id", "public.task_assignments.contributor_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$' and evaluation_request_digest ~ '^sha256:[0-9a-f]{64}$'", name="sha256_shapes"),
        sa.CheckConstraint("(submission_version = 1 and creation_kind = 'initial' and creation_status = 'in_progress') or (submission_version > 1 and creation_kind = 'revision' and creation_status = 'needs_revision')", name="creation_shape"),
        sa.CheckConstraint("creation_decision_id <> binding_decision_id", name="distinct_authority"),
        sa.ForeignKeyConstraint(["admission_id"], ["public.submission_bundle_admissions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["artifact_binding_id"], ["public.artifact_bindings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["artifact_content_id"], ["public.artifact_contents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["creation_decision_id"], ["public.audit_events.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["binding_decision_id"], ["public.audit_events.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evaluation_attempt_id"], ["public.checker_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evaluation_event_id"], ["public.outbox_events.event_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("admission_id"),
        sa.UniqueConstraint("artifact_binding_id"),
        sa.UniqueConstraint("creation_decision_id"),
        sa.UniqueConstraint("binding_decision_id"),
        sa.UniqueConstraint("evaluation_request_id"),
        sa.UniqueConstraint("evaluation_attempt_id"),
        sa.UniqueConstraint("evaluation_result_id"),
        sa.UniqueConstraint("evaluation_event_id"),
        schema="public")
    definition = op.get_bind().execute(sa.text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid='public.audit_events'::regclass AND conname='ck_audit_events_authority_privacy_bounds'"
    )).scalar_one()
    anchor = "('pre_submit_checker_input'::character varying)::text"
    if definition.count(anchor) != 1:
        raise RuntimeError("submission authority resource registry changed")
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT ck_audit_events_authority_privacy_bounds")
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT ck_audit_events_authority_privacy_bounds " + definition.replace(
        anchor, anchor + ", ('submission_creation'::character varying)::text, ('submission_binding'::character varying)::text"))
    _resource_functions()
    _custody_functions()
    op.execute("""
CREATE TRIGGER submission_dispatch_immutable BEFORE UPDATE OR DELETE ON public.submission_dispatches
FOR EACH ROW EXECUTE FUNCTION public.deny_submission_dispatch_mutation();
""")
    op.execute("""
CREATE TRIGGER submission_dispatch_no_truncate BEFORE TRUNCATE ON public.submission_dispatches
FOR EACH STATEMENT EXECUTE FUNCTION public.deny_submission_dispatch_mutation();
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER submission_dispatch_complete AFTER INSERT ON public.submission_dispatches
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_submission_dispatch_receipt();
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER submission_dispatch_required AFTER INSERT OR UPDATE ON public.submissions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_submission_dispatch_parent();
""")
    op.execute("""
CREATE TRIGGER submission_dispatch_parent_immutable BEFORE UPDATE ON public.submissions
FOR EACH ROW EXECUTE FUNCTION public.guard_dispatched_submission_immutable();
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER submission_binding_receipt_required AFTER INSERT OR UPDATE ON public.submission_bundle_admissions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_submission_binding_receipt();
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER submission_binding_receipt_complete AFTER INSERT ON public.submission_binding_receipts
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_submission_binding_receipt_row();
""")
    op.execute("""
CREATE TRIGGER submission_binding_receipt_immutable BEFORE UPDATE OR DELETE ON public.submission_binding_receipts
FOR EACH ROW EXECUTE FUNCTION public.deny_submission_binding_receipt_mutation();
""")
    op.execute("""
CREATE TRIGGER submission_binding_receipt_no_truncate BEFORE TRUNCATE ON public.submission_binding_receipts
FOR EACH STATEMENT EXECUTE FUNCTION public.deny_submission_binding_receipt_mutation();
""")


def _resource_functions() -> None:
    op.execute("""
CREATE FUNCTION public.submission_binding_resource(admission_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
 SELECT pg_catalog.jsonb_build_object(
  'resource_type','submission_binding','resource_id',a.id,'admission_id',a.id,
  'evidence_set_id',e.id,'actor_profile_id',a.actor_profile_id,'identity_link_id',a.identity_link_id,
  'project_id',a.project_id,'task_id',a.task_id,'assignment_id',a.assignment_id,
  'predecessor_submission_id',a.predecessor_submission_id,'predecessor_submission_version',a.predecessor_submission_version,
  'submission_id',a.consumed_by_submission_id,'submission_version',a.consumed_by_submission_version,
  'guide_id',e.guide_id,'guide_version',e.guide_version,'source_snapshot_id',e.source_snapshot_id,
  'source_snapshot_sha256',e.source_snapshot_sha256,'effective_policy_id',e.effective_policy_id,
  'effective_policy_sha256',e.locked_artifact_policy_sha256,'pre_submit_policy_id',e.pre_submit_policy_id,
  'pre_submit_policy_sha256',e.locked_checker_policy_sha256,'locked_policy_context_hash',e.locked_policy_context_hash,
  'semantic_manifest_id',e.semantic_manifest_id,'semantic_manifest_sha256',e.semantic_manifest_sha256,
  'content_id',a.artifact_content_id,'sha256',a.archive_sha256,'byte_count',a.archive_byte_count,
  'logical_role','submission_bundle_original'
 ) FROM public.submission_bundle_admissions a JOIN public.pre_submit_evidence_sets e ON e.id=a.pre_submit_evidence_set_id
 WHERE a.id=$1 AND a.status='consumed'
$$;
""")
    op.execute("""
CREATE FUNCTION public.submission_creation_resource(submission_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
 SELECT pg_catalog.jsonb_build_object(
  'resource_type','submission_creation','resource_id',s.id,'scope_project_id',t.project_id,
  'actor_profile_id',s.contributor_id,'identity_link_id',a.identity_link_id,'task_id',s.task_id,
  'assignment_id',s.task_assignment_id,'contribution_policy_version_id',s.contribution_policy_version_id,
  'admission_id',s.submission_bundle_admission_id,'predecessor_submission_id',s.supersedes_submission_id,
  'predecessor_submission_version',p.version,'submission_id',s.id,'submission_version',s.version,
  'task_status',CASE WHEN s.supersedes_submission_id IS NULL THEN 'in_progress' ELSE 'needs_revision' END,
  'submission_kind',CASE WHEN s.supersedes_submission_id IS NULL THEN 'initial' ELSE 'revision' END,
  'guide_version',s.locked_guide_version,'source_snapshot_id',s.locked_guide_source_snapshot_id,
  'source_snapshot_sha256',s.locked_guide_source_snapshot_hash,
  'effective_policy_id',s.locked_effective_project_submission_artifact_policy_id,
  'effective_policy_sha256',s.locked_effective_project_submission_artifact_policy_hash,
  'pre_submit_policy_id',s.locked_pre_submit_checker_policy_id,'pre_submit_policy_sha256',s.locked_pre_submit_checker_bundle_hash
 ) FROM public.submissions s JOIN public.workstream_tasks t ON t.id=s.task_id
 JOIN public.submission_bundle_admissions a ON a.id=s.submission_bundle_admission_id
 LEFT JOIN public.submissions p ON p.id=s.supersedes_submission_id AND p.task_id=s.task_id
 WHERE s.id=$1
$$;
""")
    op.execute("""
CREATE FUNCTION public.submission_authority_receipt_valid(decision_id uuid, resource jsonb, creation boolean)
RETURNS boolean LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
 SELECT coalesce(EXISTS (
  SELECT 1 FROM public.audit_events a JOIN public.actor_profiles p ON p.id::text=a.actor_id
  WHERE a.id=$1 AND $2 IS NOT NULL AND a.event_domain='authority' AND a.event_type='SensitiveAuthorizationAllowed'
   AND a.actor_ref_kind='actor_profile' AND a.denial_code IS NULL
   AND a.action_id=CASE WHEN $3 THEN 'submission.create' ELSE 'artifact.submission.binding.create' END
   AND a.permission_id=CASE WHEN $3 THEN 'submission.create' ELSE 'artifact.binding.create' END AND a.request_id IS NOT NULL AND a.correlation_id IS NOT NULL
   AND a.project_id::text=coalesce($2->>'scope_project_id',$2->>'project_id')
   AND a.resource_type=$2->>'resource_type' AND a.resource_id=$2->>'resource_id'
   AND a.target_ref_kind='project' AND a.target_ref_id=a.project_id::text
   AND a.after_facts::jsonb=pg_catalog.jsonb_build_object('allowed',true,'resource_context_digest',
    'sha256:' || pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
      public.project_guide_projection_canonical_json(pg_catalog.jsonb_build_object(
        'resource_context',pg_catalog.jsonb_strip_nulls($2))), 'UTF8')), 'hex'))
   AND CASE WHEN $3 THEN p.actor_kind='human' AND p.id::text=$2->>'actor_profile_id'
     AND EXISTS (SELECT 1 FROM public.actor_identity_links l WHERE l.id::text=$2->>'identity_link_id' AND l.actor_profile_id=p.id)
     AND EXISTS (SELECT 1 FROM public.project_role_grants g WHERE g.id::text=a.matched_grant_id
       AND g.actor_profile_id=p.id AND g.project_id=a.project_id AND g.role='submitter')
    ELSE p.actor_kind='service' AND p.service_identity='workstream.artifact.binding'
      AND a.matched_grant_id IS NULL END
 ),false)
$$;
""")


def _custody_functions() -> None:
    op.execute("""
CREATE FUNCTION public.submission_binding_receipt_valid(r public.submission_binding_receipts) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
 SELECT coalesce(EXISTS(
  SELECT 1 FROM public.submission_bundle_admissions a JOIN public.artifact_bindings b ON b.id=r.binding_id
  JOIN public.submissions s ON s.id=a.consumed_by_submission_id AND s.version=a.consumed_by_submission_version
    AND s.submission_bundle_admission_id=a.id AND s.artifact_binding_id=b.id AND s.artifact_content_id=a.artifact_content_id
  WHERE a.id=r.admission_id AND a.status='consumed' AND b.project_id=a.project_id
   AND b.content_id=a.artifact_content_id AND b.resource_type='submission'
   AND b.resource_id=a.consumed_by_submission_id::text AND b.logical_role='submission_bundle_original'
   AND b.scope_version=1 AND b.actor_id=a.actor_profile_id::text
   AND public.submission_authority_receipt_valid(r.decision_id,public.submission_binding_resource(a.id),false)
 ),false)
$$;
""")
    op.execute("""
CREATE FUNCTION public.guard_submission_binding_receipt_row() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
 IF NOT public.submission_binding_receipt_valid(NEW) THEN
  RAISE EXCEPTION 'submission binding receipt mismatch' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$;
""")
    op.execute("""
CREATE FUNCTION public.deny_submission_binding_receipt_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN RAISE EXCEPTION 'submission binding receipt is immutable' USING ERRCODE='23514'; END $$;
""")
    op.execute("""
CREATE FUNCTION public.submission_dispatch_valid(d public.submission_dispatches) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
 SELECT coalesce(EXISTS (
 SELECT 1 FROM public.submissions s
 JOIN public.workstream_tasks t ON t.id=s.task_id
 JOIN public.task_assignments assignment ON assignment.id=s.task_assignment_id
 JOIN public.submission_bundle_admissions a ON a.id=s.submission_bundle_admission_id
 JOIN public.artifact_bindings b ON b.id=s.artifact_binding_id
 JOIN public.submission_binding_receipts br ON br.admission_id=a.id AND br.binding_id=b.id
 JOIN public.checker_runs r ON r.id=d.evaluation_attempt_id
 JOIN public.outbox_events e ON e.event_id=d.evaluation_event_id
 WHERE s.id=d.submission_id AND s.version=d.submission_version AND s.task_id=d.task_id AND t.project_id=d.project_id
  AND s.task_assignment_id=d.assignment_id AND s.contributor_id=d.contributor_id
  AND assignment.task_id=s.task_id AND assignment.project_id=t.project_id AND assignment.contributor_id=s.contributor_id
  AND assignment.submitter_contribution_policy_version_id=s.contribution_policy_version_id
  AND a.id=d.admission_id AND a.status='consumed' AND a.consumed_by_submission_id=s.id AND a.consumed_by_submission_version=s.version
  AND a.project_id=d.project_id AND a.task_id=d.task_id AND a.assignment_id=d.assignment_id AND a.actor_profile_id=d.contributor_id
  AND a.predecessor_submission_id IS NOT DISTINCT FROM s.supersedes_submission_id
  AND br.decision_id=d.binding_decision_id AND s.artifact_content_id=d.artifact_content_id
  AND b.id=d.artifact_binding_id AND b.project_id=d.project_id AND b.content_id=d.artifact_content_id
  AND b.resource_type='submission' AND b.resource_id=s.id::text AND b.logical_role='submission_bundle_original' AND b.scope_version=1
  AND d.creation_kind=CASE WHEN s.supersedes_submission_id IS NULL THEN 'initial' ELSE 'revision' END
  AND d.creation_status=CASE WHEN s.supersedes_submission_id IS NULL THEN 'in_progress' ELSE 'needs_revision' END
  AND d.request_digest='sha256:' || pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
    public.project_guide_projection_canonical_json(pg_catalog.jsonb_build_object(
      'domain','workstream.submission.creation','request',pg_catalog.jsonb_build_object(
       'admission_id',a.id,'task_id',s.task_id,'assignment_id',s.task_assignment_id,'contributor_id',s.contributor_id,
       'predecessor_submission_id',s.supersedes_submission_id,'summary',s.summary,'contributor_attestation',s.worker_attestation))), 'UTF8')), 'hex')
  AND public.submission_authority_receipt_valid(d.creation_decision_id,public.submission_creation_resource(s.id),true)
  AND public.submission_authority_receipt_valid(d.binding_decision_id,public.submission_binding_resource(a.id),false)
  AND r.project_id=d.project_id AND r.task_id=d.task_id AND r.submission_id=s.id AND r.submission_version=s.version
  AND r.phase='post_submission' AND r.evaluation_generation=1 AND r.evaluation_request_id=d.evaluation_request_id
  AND r.request_digest=d.evaluation_request_digest AND r.result_id=d.evaluation_result_id
  AND (r.request_json::jsonb->>'assignment_id')=d.assignment_id::text
  AND (r.request_json::jsonb->>'content_id')=d.artifact_content_id::text
  AND (r.request_json::jsonb->>'binding_id')=d.artifact_binding_id::text
  AND (r.request_json::jsonb->>'content_sha256')=a.archive_sha256
  AND (r.request_json::jsonb->'byte_count')=pg_catalog.to_jsonb(a.archive_byte_count)
  AND (r.request_json::jsonb->'structural_input'->>'summary')=s.summary
  AND (r.request_json::jsonb->'structural_input'->>'worker_attestation')=s.worker_attestation
  AND e.event_type='PostSubmissionEvaluationRequested' AND e.event_version=1 AND e.producer='workstream'
  AND e.aggregate_type='submission' AND e.aggregate_id=s.id AND e.project_id=d.project_id
  AND e.correlation_id=d.evaluation_request_id::text AND e.causation_event_id IS NULL
  AND e.idempotency_key='submission-evaluation:' || s.id::text
  AND e.payload::jsonb=pg_catalog.jsonb_build_object(
   'project_id',d.project_id,'task_id',d.task_id,'submission_id',s.id,'submission_version',s.version,
   'request_id',d.evaluation_request_id,'request_digest',d.evaluation_request_digest,'evaluation_generation',1,
   'attempt_id',d.evaluation_attempt_id,'result_id',d.evaluation_result_id,
   'creation_decision_id',d.creation_decision_id,'binding_decision_id',d.binding_decision_id)
 ),false)
$$;
""")
    op.execute("""
CREATE FUNCTION public.deny_submission_dispatch_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN RAISE EXCEPTION 'submission dispatch is immutable' USING ERRCODE='23514'; END $$;
""")
    op.execute("""
CREATE FUNCTION public.guard_submission_dispatch_receipt() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
 IF NOT public.submission_dispatch_valid(NEW) THEN
  RAISE EXCEPTION 'submission dispatch custody mismatch' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$;
""")
    op.execute("""
CREATE FUNCTION public.guard_submission_dispatch_parent() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE s public.submissions%ROWTYPE; d public.submission_dispatches%ROWTYPE;
BEGIN
 IF TG_OP='UPDATE' AND ROW(NEW.submission_bundle_admission_id,NEW.artifact_binding_id,NEW.artifact_content_id)
    IS NOT DISTINCT FROM ROW(OLD.submission_bundle_admission_id,OLD.artifact_binding_id,OLD.artifact_content_id) THEN
  RETURN NULL;
 END IF;
 SELECT * INTO s FROM public.submissions WHERE id=NEW.id;
 IF NOT FOUND THEN RAISE EXCEPTION 'submission dispatch parent missing' USING ERRCODE='23514'; END IF;
 IF s.submission_bundle_admission_id IS NULL THEN RETURN NULL; END IF;
 SELECT * INTO d FROM public.submission_dispatches WHERE submission_id=s.id;
 IF NOT FOUND THEN RAISE EXCEPTION 'submission dispatch required' USING ERRCODE='23514'; END IF;
 IF NOT public.submission_dispatch_valid(d) THEN
  RAISE EXCEPTION 'submission dispatch custody mismatch' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$;
""")
    op.execute("""
CREATE FUNCTION public.guard_dispatched_submission_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM public.submission_dispatches WHERE submission_id=OLD.id)
    AND pg_catalog.to_jsonb(NEW)-'status' IS DISTINCT FROM pg_catalog.to_jsonb(OLD)-'status' THEN
  RAISE EXCEPTION 'dispatched submission facts are immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
""")
    op.execute("""
CREATE FUNCTION public.guard_submission_binding_receipt() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE a public.submission_bundle_admissions%ROWTYPE; r public.submission_binding_receipts%ROWTYPE;
BEGIN
 IF TG_OP='UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status THEN
  RETURN NULL;
 END IF;
 SELECT * INTO a FROM public.submission_bundle_admissions WHERE id=NEW.id;
 IF NOT FOUND THEN RAISE EXCEPTION 'submission binding parent missing' USING ERRCODE='23514'; END IF;
 IF a.status='consumed' THEN
  SELECT * INTO r FROM public.submission_binding_receipts WHERE admission_id=a.id;
  IF NOT FOUND THEN
   RAISE EXCEPTION 'submission binding receipt required' USING ERRCODE='23514';
  END IF;
  IF NOT public.submission_binding_receipt_valid(r) THEN
   RAISE EXCEPTION 'submission binding receipt required' USING ERRCODE='23514';
  END IF;
 ELSIF EXISTS(SELECT 1 FROM public.submission_binding_receipts WHERE admission_id=a.id) THEN
  RAISE EXCEPTION 'unconsumed submission has binding receipt' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$;
""")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
