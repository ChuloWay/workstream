"""Commit one immutable TASK deadline rejection and release per routed failure."""

from alembic import op
from sqlalchemy import text

revision = "0044_task_revision_expiry"
down_revision = "0043_outbox_not_before"
branch_labels = None
depends_on = None


def _replace(signature, old, new):
    body = op.get_bind().execute(text(
        "SELECT pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("revision expiry predecessor function shape changed: " + signature)
    op.execute(body.replace(old, new))


def _extend_closed_authority_constraints():
    def definition(table, name):
        return op.get_bind().execute(text(
            "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
            "WHERE conrelid=CAST(:table AS regclass) AND conname=:name"
        ), {"table": "public." + table, "name": name}).scalar_one()

    name = "ck_actor_profiles_kind_service_identity"
    value = definition("actor_profiles", name)
    anchor = "('workstream.task.assignment_reconciler'::character varying)::text"
    addition = ", ('workstream.task.revision_expirer'::character varying)::text"
    if value.count(anchor) != 1 or "workstream.task.revision_expirer" in value:
        raise RuntimeError("service identity constraint shape changed")
    op.execute("ALTER TABLE public.actor_profiles DROP CONSTRAINT " + name)
    op.execute("ALTER TABLE public.actor_profiles ADD CONSTRAINT " + name + " " + value.replace(anchor, anchor + addition))

    name = "ck_audit_events_authorization_action_evidence"
    value = definition("audit_events", name)
    anchor = "(((action_id)::text = 'task.assignment.authority_reconcile'::text) AND ((permission_id)::text = 'task.assignment.authority_reconcile'::text))"
    addition = " OR (((action_id)::text = 'task.revision.expire'::text) AND ((permission_id)::text = 'task.revision.expire'::text))"
    if value.count(anchor) != 2 or "task.revision.expire" in value:
        raise RuntimeError("revision expiry AUTH constraint shape changed")
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT " + name + " " + value.replace(anchor, anchor + addition))

    name = "ck_audit_events_authority_registries"
    value = definition("audit_events", name)
    anchor = "('outbox.dispatch'::character varying)::text"
    addition = ", ('task.revision.expire'::character varying)::text"
    if value.count(anchor) != 1 or "task.revision.expire" in value:
        raise RuntimeError("revision expiry AUTH registry shape changed")
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT " + name + " " + value.replace(anchor, anchor + addition))


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    _extend_closed_authority_constraints()
    op.execute("""
CREATE TABLE public.task_revision_expirations (
 id uuid PRIMARY KEY,
 project_id uuid NOT NULL, task_id uuid NOT NULL,
 assignment_id uuid NOT NULL, contributor_id uuid NOT NULL,
 source_submission_id uuid NOT NULL, routing_manifest_id uuid NOT NULL,
 root_preparation_id uuid NOT NULL, root_preparation_sha256 varchar(71) NOT NULL,
 head_preparation_id uuid NOT NULL, head_preparation_sha256 varchar(71) NOT NULL,
 deadline_at timestamptz NOT NULL, expired_at timestamptz NOT NULL,
 delivery_event_id uuid NOT NULL, outcome_event_id uuid NOT NULL,
 authorization_decision_id uuid NOT NULL,
 authority_context jsonb NOT NULL, audit_event_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 creation_xid varchar(20) NOT NULL DEFAULT pg_current_xact_id()::text,
 CONSTRAINT ck_task_revision_expirations_id_uuid7 CHECK
  ((get_byte(uuid_send(id),6)>>4)=7 AND (get_byte(uuid_send(id),8)&192)=128),
 CONSTRAINT ck_task_revision_expirations_digests CHECK
  (root_preparation_sha256 ~ '^sha256:[0-9a-f]{64}$' AND
   head_preparation_sha256 ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_task_revision_expirations_deadline CHECK (expired_at>=deadline_at),
 CONSTRAINT uq_revision_expiration_manifest UNIQUE (routing_manifest_id),
 CONSTRAINT uq_revision_expiration_head UNIQUE (head_preparation_id),
 CONSTRAINT uq_revision_expiration_delivery UNIQUE (delivery_event_id),
 CONSTRAINT uq_revision_expiration_outcome UNIQUE (outcome_event_id),
 CONSTRAINT uq_revision_expiration_audit UNIQUE (audit_event_id),
 CONSTRAINT fk_revision_expiration_task_project FOREIGN KEY (task_id,project_id)
  REFERENCES public.workstream_tasks(id,project_id) ON DELETE RESTRICT,
 CONSTRAINT fk_revision_expiration_assignment FOREIGN KEY (assignment_id,task_id,contributor_id)
  REFERENCES public.task_assignments(id,task_id,contributor_id) ON DELETE RESTRICT,
 CONSTRAINT fk_revision_expiration_root_preparation FOREIGN KEY (root_preparation_id,root_preparation_sha256)
  REFERENCES public.task_revision_preparations(id,preparation_sha256) ON DELETE RESTRICT,
 CONSTRAINT fk_revision_expiration_head_preparation FOREIGN KEY (head_preparation_id,head_preparation_sha256)
  REFERENCES public.task_revision_preparations(id,preparation_sha256) ON DELETE RESTRICT,
 CONSTRAINT fk_task_revision_expirations_source_submission_id_submissions FOREIGN KEY (source_submission_id)
  REFERENCES public.submissions(id) ON DELETE RESTRICT,
 CONSTRAINT fk_task_revision_expirations_routing_manifest_id_task_post_submit_routing_manifests FOREIGN KEY (routing_manifest_id)
  REFERENCES public.task_post_submit_routing_manifests(id) ON DELETE RESTRICT,
 CONSTRAINT fk_task_revision_expirations_delivery_event_id_outbox_events FOREIGN KEY (delivery_event_id)
  REFERENCES public.outbox_events(event_id) ON DELETE RESTRICT,
 CONSTRAINT fk_task_revision_expirations_outcome_event_id_outbox_events FOREIGN KEY (outcome_event_id)
  REFERENCES public.outbox_events(event_id) ON DELETE RESTRICT,
 CONSTRAINT fk_task_revision_expirations_authorization_decision_id_audit_events FOREIGN KEY (authorization_decision_id)
  REFERENCES public.audit_events(id) ON DELETE RESTRICT,
 CONSTRAINT fk_task_revision_expirations_audit_event_id_audit_events FOREIGN KEY (audit_event_id)
  REFERENCES public.audit_events(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
);
    """)
    op.execute("""
CREATE FUNCTION public.task_revision_expired_assignment_current(prior_assignment uuid, latest_submission uuid)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT EXISTS (
  SELECT 1 FROM public.task_revision_expirations e
  JOIN public.task_assignments a ON a.id=e.assignment_id
  JOIN public.submissions s ON s.id=e.source_submission_id
  JOIN public.task_revision_preparations root ON root.id=e.root_preparation_id
  JOIN public.task_revision_preparations head ON head.id=e.head_preparation_id
  WHERE e.assignment_id=prior_assignment AND e.source_submission_id=latest_submission
   AND s.task_assignment_id=a.id AND s.task_id=e.task_id
   AND e.project_id=a.project_id AND e.contributor_id=a.contributor_id
   AND a.status='revision_expired' AND a.released_at=e.expired_at
   AND e.deadline_at<=e.expired_at
   AND root.routing_manifest_id=e.routing_manifest_id AND root.sequence=1
   AND root.preparation_sha256=e.root_preparation_sha256
   AND head.routing_manifest_id=e.routing_manifest_id
   AND head.preparation_sha256=e.head_preparation_sha256
 );
$$;
    """)
    _replace(
        "public.guard_submission_revision_capacity()",
        "OR prior_assignment.released_at IS NULL\n          THEN RAISE EXCEPTION 'submission_revision_lineage_invalid' USING ERRCODE='23514'; END IF;",
        "OR prior_assignment.released_at IS NULL\n          THEN RAISE EXCEPTION 'submission_revision_lineage_invalid' USING ERRCODE='23514'; END IF;\n          IF NOT public.task_revision_expired_assignment_current(prior.task_assignment_id,prior.id)\n          THEN RAISE EXCEPTION 'submission_revision_lineage_invalid' USING ERRCODE='23514'; END IF;",
    )
    op.execute("""
CREATE FUNCTION public.guard_task_revision_expiration() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE t public.workstream_tasks%ROWTYPE; a public.task_assignments%ROWTYPE;
 root public.task_revision_preparations%ROWTYPE; head public.task_revision_preparations%ROWTYPE;
 source public.submissions%ROWTYPE; m public.task_post_submit_routing_manifests%ROWTYPE;
 event public.outbox_events%ROWTYPE; outcome public.outbox_events%ROWTYPE;
 decision public.audit_events%ROWTYPE;
 digest text; expected_facts jsonb;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'revision expirations are immutable' USING ERRCODE='55000'; END IF;
 SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id;
 SELECT * INTO a FROM public.task_assignments WHERE id=NEW.assignment_id;
 SELECT * INTO source FROM public.submissions WHERE id=NEW.source_submission_id;
 SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE id=NEW.routing_manifest_id;
 SELECT * INTO root FROM public.task_revision_preparations WHERE id=NEW.root_preparation_id;
 SELECT * INTO head FROM public.task_revision_preparations WHERE id=NEW.head_preparation_id;
 SELECT * INTO event FROM public.outbox_events WHERE event_id=NEW.delivery_event_id;
 SELECT * INTO outcome FROM public.outbox_events WHERE event_id=NEW.outcome_event_id;
 SELECT * INTO decision FROM public.audit_events WHERE id=NEW.authorization_decision_id;
 expected_facts:=NEW.authority_context;
 digest:='sha256:'||pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
  public.project_guide_projection_canonical_json(jsonb_build_object('resource_context',
   jsonb_build_object('resource_type','task_authority','resource_id',NEW.task_id::text,
    'scope_project_id',NEW.project_id::text,'facts',expected_facts))),'UTF8')),'hex');
 IF t.id IS NULL OR a.id IS NULL OR source.id IS NULL OR m.id IS NULL
   OR root.id IS NULL OR head.id IS NULL OR event.event_id IS NULL
   OR outcome.event_id IS NULL OR decision.id IS NULL
   OR NEW.creation_xid<>pg_current_xact_id()::text
   OR NEW.expired_at<NEW.deadline_at OR NEW.expired_at>clock_timestamp()
   OR NOT public.revision_routing_source_current(NEW.routing_manifest_id)
   OR t.status<>'needs_revision' OR t.assigned_to<>NEW.contributor_id
   OR a.status<>'active' OR a.released_at IS NOT NULL OR a.accepted_at IS NULL
   OR ROW(a.task_id,a.project_id,a.contributor_id) IS DISTINCT FROM
      ROW(NEW.task_id,NEW.project_id,NEW.contributor_id)
   OR ROW(source.task_id,source.task_assignment_id,source.contributor_id) IS DISTINCT FROM
      ROW(NEW.task_id,NEW.assignment_id,NEW.contributor_id)
   OR ROW(m.project_id,m.task_id,m.assignment_id,m.contributor_id,m.submission_id) IS DISTINCT FROM
      ROW(NEW.project_id,NEW.task_id,NEW.assignment_id,NEW.contributor_id,NEW.source_submission_id)
   OR m.routing_recommendation<>'needs_revision'
   OR root.sequence<>1 OR root.predecessor_id IS NOT NULL
   OR root.routing_manifest_id<>m.id OR root.submission_id<>source.id
   OR root.preparation_sha256<>NEW.root_preparation_sha256
   OR root.deadline_at<>NEW.deadline_at
   OR head.routing_manifest_id<>m.id OR head.preparation_sha256<>NEW.head_preparation_sha256
   OR head.deadline_at<>NEW.deadline_at
   OR EXISTS (SELECT 1 FROM public.task_revision_preparations newer
      WHERE newer.routing_manifest_id=m.id AND newer.sequence>head.sequence)
   OR event.event_type<>'TaskRevisionExpiryRequested' OR event.event_version<>1
   OR event.aggregate_type<>'task' OR event.aggregate_id<>NEW.task_id
   OR event.project_id<>NEW.project_id
   OR event.correlation_id<>m.id::text
   OR event.causation_event_id<>m.outcome_event_id
   OR event.idempotency_key<>'task.revision.expire:'||m.id::text
   OR event.not_before_at<>NEW.deadline_at
   OR event.payload->>'project_id' IS DISTINCT FROM NEW.project_id::text
   OR event.payload->>'task_id' IS DISTINCT FROM NEW.task_id::text
   OR event.payload->>'assignment_id' IS DISTINCT FROM NEW.assignment_id::text
   OR event.payload->>'contributor_id' IS DISTINCT FROM NEW.contributor_id::text
   OR event.payload->>'source_submission_id' IS DISTINCT FROM NEW.source_submission_id::text
   OR event.payload->>'routing_manifest_id' IS DISTINCT FROM m.id::text
   OR event.payload->>'root_preparation_id' IS DISTINCT FROM root.id::text
   OR event.payload->>'root_preparation_sha256' IS DISTINCT FROM root.preparation_sha256
   OR (event.payload->>'deadline_at')::timestamptz IS DISTINCT FROM NEW.deadline_at
   OR outcome.event_type<>'TaskRevisionExpired' OR outcome.event_version<>1
   OR outcome.aggregate_type<>'task' OR outcome.aggregate_id<>NEW.task_id
   OR outcome.project_id<>NEW.project_id
   OR outcome.correlation_id<>m.id::text
   OR outcome.causation_event_id<>event.event_id
   OR outcome.idempotency_key<>'task.revision.expired:'||m.id::text
   OR outcome.not_before_at IS NOT NULL
   OR outcome.occurred_at<NEW.expired_at OR outcome.occurred_at>clock_timestamp()
   OR outcome.delivery_state<>'pending' OR outcome.attempt_count<>0
   OR (outcome.payload->>'deadline_at')::timestamptz IS DISTINCT FROM NEW.deadline_at
   OR (outcome.payload->>'expired_at')::timestamptz IS DISTINCT FROM NEW.expired_at
   OR (outcome.payload-'deadline_at'-'expired_at') IS DISTINCT FROM
      jsonb_build_object('project_id',NEW.project_id::text,'task_id',NEW.task_id::text,
       'assignment_id',NEW.assignment_id::text,'contributor_id',NEW.contributor_id::text,
       'source_submission_id',NEW.source_submission_id::text,
       'routing_manifest_id',m.id::text,
       'root_preparation_id',root.id::text,
       'root_preparation_sha256',root.preparation_sha256,
       'head_preparation_id',head.id::text,
       'head_preparation_sha256',head.preparation_sha256,
       'expiration_receipt_id',NEW.id::text,
       'expiry_request_event_id',event.event_id::text,
       'authorization_decision_id',decision.id::text,
       'audit_event_id',NEW.audit_event_id::text)
   OR expected_facts->'target' IS NULL
   OR expected_facts#>>'{target,routing_manifest_id}' IS DISTINCT FROM m.id::text
   OR expected_facts#>>'{target,root_preparation_id}' IS DISTINCT FROM root.id::text
   OR expected_facts#>>'{target,root_preparation_sha256}' IS DISTINCT FROM root.preparation_sha256
   OR expected_facts#>>'{target,deadline_at}' IS NULL
   OR expected_facts->'target' IS DISTINCT FROM event.payload
   OR expected_facts->>'head_preparation_id' IS DISTINCT FROM head.id::text
   OR expected_facts->>'head_preparation_sha256' IS DISTINCT FROM head.preparation_sha256
   OR expected_facts->>'delivery_event_id' IS DISTINCT FROM event.event_id::text
   OR expected_facts->>'task_status' IS DISTINCT FROM t.status
   OR expected_facts->>'assignment_status' IS DISTINCT FROM a.status
   OR decision.event_type<>'SensitiveAuthorizationAllowed'
   OR decision.action_id<>'task.revision.expire' OR decision.permission_id<>'task.revision.expire'
   OR decision.resource_type<>'task' OR decision.resource_id<>NEW.task_id::text
   OR decision.project_id<>NEW.project_id
   OR decision.request_id<>event.event_id OR decision.correlation_id<>m.id
   OR decision.after_facts::jsonb IS DISTINCT FROM
      jsonb_build_object('allowed',true,'resource_context_digest',digest)
 THEN RAISE EXCEPTION 'revision expiry source or authority differs' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("CREATE TRIGGER revision_expiration_guard BEFORE INSERT OR UPDATE OR DELETE ON public.task_revision_expirations FOR EACH ROW EXECUTE FUNCTION public.guard_task_revision_expiration()")
    op.execute("""
CREATE FUNCTION public.guard_task_revision_expiration_closure() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE t public.workstream_tasks%ROWTYPE; a public.task_assignments%ROWTYPE;
 audit public.audit_events%ROWTYPE; decision public.audit_events%ROWTYPE;
 refs jsonb; digest text;
BEGIN
 SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id;
 SELECT * INTO a FROM public.task_assignments WHERE id=NEW.assignment_id;
 SELECT * INTO audit FROM public.audit_events WHERE id=NEW.audit_event_id;
 SELECT * INTO decision FROM public.audit_events WHERE id=NEW.authorization_decision_id;
 refs:=jsonb_build_object('project_id',NEW.project_id::text,'task_id',NEW.task_id::text,
  'assignment_id',NEW.assignment_id::text,'submission_id',NEW.source_submission_id::text,
  'routing_manifest_id',NEW.routing_manifest_id::text,
  'revision_preparation_id',NEW.head_preparation_id::text,
  'authorization_decision_id',NEW.authorization_decision_id::text,
  'outbox_event_id',NEW.delivery_event_id::text);
 digest:=decision.after_facts::jsonb->>'resource_context_digest';
 IF t.status<>'ready' OR t.assigned_to IS NOT NULL
   OR a.status<>'revision_expired' OR a.released_at<>NEW.expired_at
   OR audit.id IS NULL OR audit.event_type<>'TaskRevisionExpired'
   OR audit.entity_type<>'task' OR audit.entity_id<>NEW.task_id
   OR audit.event_domain<>'legacy_lifecycle' OR audit.auth_source<>'local_lifecycle'
   OR audit.is_dev_auth OR audit.actor_id<>decision.actor_id
   OR audit.from_status<>'needs_revision' OR audit.to_status<>'ready'
   OR audit.event_payload::jsonb IS DISTINCT FROM jsonb_build_object(
     'references',refs,'authorization_resource_digest',digest,
     'revision_expiry_facts',NEW.authority_context)
 THEN RAISE EXCEPTION 'revision expiry closure unavailable' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END $$;
    """)
    op.execute("CREATE CONSTRAINT TRIGGER revision_expiration_closure AFTER INSERT ON public.task_revision_expirations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_task_revision_expiration_closure()")
    op.execute("""
CREATE FUNCTION public.guard_task_revision_expiration_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_TABLE_NAME='workstream_tasks'
    AND OLD.status='needs_revision' AND NEW.status='ready' THEN
   IF NEW.assigned_to IS NOT NULL OR NOT EXISTS (
      SELECT 1 FROM public.task_revision_expirations e
      WHERE e.task_id=OLD.id AND e.project_id=OLD.project_id
       AND e.contributor_id=OLD.assigned_to
       AND e.creation_xid=pg_current_xact_id()::text)
   THEN RAISE EXCEPTION 'revision expiry receipt required' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='task_assignments'
    AND OLD.status='active' AND NEW.status='revision_expired' THEN
   IF OLD.released_at IS NOT NULL OR NEW.released_at IS NULL OR NOT EXISTS (
      SELECT 1 FROM public.task_revision_expirations e
      WHERE e.assignment_id=OLD.id AND e.task_id=OLD.task_id
       AND e.contributor_id=OLD.contributor_id
       AND e.expired_at=NEW.released_at
       AND e.creation_xid=pg_current_xact_id()::text)
   THEN RAISE EXCEPTION 'revision expiry receipt required' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("CREATE TRIGGER revision_expiration_task_transition BEFORE UPDATE ON public.workstream_tasks FOR EACH ROW EXECUTE FUNCTION public.guard_task_revision_expiration_transition()")
    op.execute("CREATE TRIGGER revision_expiration_assignment_transition BEFORE UPDATE ON public.task_assignments FOR EACH ROW EXECUTE FUNCTION public.guard_task_revision_expiration_transition()")
    op.execute("""
CREATE FUNCTION public.reject_task_revision_expiration_truncate() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN RAISE EXCEPTION 'revision expirations are immutable' USING ERRCODE='55000'; END $$;
    """)
    op.execute("CREATE TRIGGER revision_expiration_no_truncate BEFORE TRUNCATE ON public.task_revision_expirations FOR EACH STATEMENT EXECUTE FUNCTION public.reject_task_revision_expiration_truncate()")


def downgrade():
    raise RuntimeError("Retained deadline rejections cannot be downgraded")
