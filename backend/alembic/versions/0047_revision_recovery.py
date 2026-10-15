"""Authorize bounded automatic recovery of retained revision windows."""

from alembic import op
from sqlalchemy import text

revision = "0047_revision_recovery"
down_revision = "0046_revision_expiry_retry"
branch_labels = None
depends_on = None


def _replace(signature, old, new):
    body = op.get_bind().execute(text(
        "SELECT pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("revision recovery predecessor function shape changed: " + signature)
    op.execute(body.replace(old, new))


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    name = "ck_audit_events_authorization_action_evidence"
    definition = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
    ), {"name": name}).scalar_one()
    anchor = "(((action_id)::text = 'task.revision.expire'::text) AND ((permission_id)::text = 'task.revision.expire'::text))"
    addition = " OR (((action_id)::text = 'task.revision.recover'::text) AND ((permission_id)::text = 'task.revision.recover'::text))"
    if definition.count(anchor) != 2 or "task.revision.recover" in definition:
        raise RuntimeError("revision recovery AUTH constraint shape changed")
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT " + name + " " + definition.replace(anchor, anchor + addition))

    name = "ck_audit_events_authority_registries"
    definition = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
    ), {"name": name}).scalar_one()
    anchor = "('task.revision.expire'::character varying)::text"
    addition = ", ('task.revision.recover'::character varying)::text"
    if definition.count(anchor) != 1 or "task.revision.recover" in definition:
        raise RuntimeError("revision recovery AUTH registry shape changed")
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT " + name + " " + definition.replace(anchor, anchor + addition))

    _replace(
        "public.guard_revision_preparation()",
        """AND decision.action_id='project.task.revision.repair'
       AND decision.permission_id='project.task.manage'""",
        """AND (
         (decision.action_id='project.task.revision.repair'
          AND decision.permission_id='project.task.manage')
         OR (NEW.predecessor_id IS NULL AND NEW.outcome IN ('kept','blocked')
          AND NEW.repair_idempotency_key=NEW.routing_manifest_id
          AND NEW.repair_reason='Recover retained revision window'
          AND NEW.repair_request_digest='sha256:'||pg_catalog.encode(pg_catalog.sha256(
            pg_catalog.convert_to(public.project_guide_projection_canonical_json(
              jsonb_build_object('routing_manifest_id',NEW.routing_manifest_id::text,
                'preparation_id',NULL,'preparation_sha256',NULL,
                'candidate',NEW.packet->'candidate')),'UTF8')),'hex')
          AND decision.action_id='task.revision.recover'
          AND decision.permission_id='task.revision.recover'
          AND decision.request_id=NEW.routing_manifest_id
          AND decision.correlation_id=NEW.routing_manifest_id
          AND EXISTS (SELECT 1 FROM public.actor_profiles service_actor
            WHERE service_actor.id=NEW.repair_actor_id
              AND service_actor.actor_kind='service'
              AND service_actor.service_identity='workstream.task.revision_expirer'
              AND service_actor.status='active'))
       )""",
    )
    op.execute("""
CREATE OR REPLACE FUNCTION public.guard_revision_preparation_closure() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE p public.task_revision_preparations%ROWTYPE;
 t public.workstream_tasks%ROWTYPE; a public.task_assignments%ROWTYPE;
 m public.task_post_submit_routing_manifests%ROWTYPE; expected jsonb;
 refs jsonb;
BEGIN
 SELECT * INTO p FROM public.task_revision_preparations WHERE id=NEW.id;
 SELECT * INTO t FROM public.workstream_tasks WHERE id=p.task_id;
 SELECT * INTO a FROM public.task_assignments WHERE id=p.assignment_id;
 SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE id=p.routing_manifest_id;
 expected:=CASE WHEN p.outcome='blocked' THEN p.packet->'previous_task_lineage'
   ELSE p.packet#>'{candidate,target,lineage}' END;
 IF t.id IS NULL OR a.id IS NULL OR m.id IS NULL
   OR NOT public.task_routing_outcome_complete(m)
   OR t.status<>'needs_revision' OR t.assigned_to<>p.contributor_id
   OR a.status<>'active' OR a.released_at IS NOT NULL
   OR public.revision_task_lineage(to_jsonb(t)) IS DISTINCT FROM expected
   OR a.submitter_contribution_policy_version_id::text IS DISTINCT FROM
      expected->>'locked_contribution_policy_version_id'
   OR (p.outcome<>'blocked' AND t.locked_post_submit_checker_policy_body::jsonb
       IS DISTINCT FROM (p.packet#>>'{candidate,target_post_policy_json}')::jsonb)
 THEN RAISE EXCEPTION 'revision preparation has no complete task outcome' USING ERRCODE='23514'; END IF;
 refs:=jsonb_build_object(
   'project_id',p.project_id::text,'task_id',p.task_id::text,
   'assignment_id',p.assignment_id::text,'submission_id',p.submission_id::text,
   'routing_manifest_id',p.routing_manifest_id::text,
   'revision_preparation_id',p.id::text,
   'authorization_decision_id',p.authorization_decision_id::text);
 IF p.repair_actor_id IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM public.audit_events event
   JOIN public.audit_events decision ON decision.id=p.authorization_decision_id
   LEFT JOIN public.outbox_events expiry ON
     expiry.idempotency_key='task.revision.expire:'||p.routing_manifest_id::text
     AND expiry.event_type='TaskRevisionExpiryRequested'
   WHERE event.id=p.audit_event_id AND event.event_domain='legacy_lifecycle'
     AND event.event_type='TaskRevisionContextRepaired'
     AND event.entity_type='task' AND event.entity_id=p.task_id
     AND event.actor_id=p.repair_actor_id::text
     AND event.auth_source='local_lifecycle' AND event.is_dev_auth=false
     AND event.from_status IS NULL AND event.to_status IS NULL
     AND event.reason=p.repair_reason
     AND (
       (decision.action_id='project.task.revision.repair'
         AND event.event_payload::jsonb=jsonb_build_object('references',refs))
       OR
       (decision.action_id='task.revision.recover' AND expiry.event_id IS NOT NULL
         AND expiry.event_version=1 AND expiry.producer='workstream'
         AND expiry.aggregate_type='task' AND expiry.aggregate_id=p.task_id
         AND expiry.project_id=p.project_id
         AND expiry.correlation_id=p.routing_manifest_id::text
         AND expiry.causation_event_id=m.outcome_event_id
         AND expiry.not_before_at=p.deadline_at
         AND expiry.payload - 'deadline_at'=jsonb_build_object(
           'project_id',p.project_id::text,'task_id',p.task_id::text,
           'assignment_id',p.assignment_id::text,
           'contributor_id',p.contributor_id::text,
           'source_submission_id',p.submission_id::text,
           'routing_manifest_id',p.routing_manifest_id::text,
           'root_preparation_id',p.id::text,
           'root_preparation_sha256',p.preparation_sha256)
         AND (expiry.payload->>'deadline_at')::timestamptz=p.deadline_at
         AND event.event_payload::jsonb=jsonb_build_object(
           'references',refs||jsonb_build_object('outbox_event_id',expiry.event_id::text),
           'authorization_resource_digest',
             decision.after_facts::jsonb->>'resource_context_digest'))
     )
 ) THEN RAISE EXCEPTION 'revision repair audit unavailable' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END $$;
    """)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
