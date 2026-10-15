"""Freeze authorized revision context, deadline and guarded task rebase custody."""

from alembic import op
from sqlalchemy import text

revision = "0043_revision_preparation"
down_revision = "0042_revision_lineage"
branch_labels = None
depends_on = None


def _replace(signature, old, new):
    body = op.get_bind().execute(text(
        "SELECT pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("revision migration function shape changed: " + signature)
    op.execute(body.replace(old, new))


def _extend_repair_audit_contract():
    """Admit the one AUTH action/resource without weakening existing bounds."""
    def definition(name):
        return op.get_bind().execute(text(
            "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
            "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
        ), {"name": name}).scalar_one()

    name = "ck_audit_events_authorization_action_evidence"
    value = definition(name)
    anchor = "(((action_id)::text = 'project.task.create'::text) AND ((permission_id)::text = 'project.task.manage'::text))"
    addition = " OR (((action_id)::text = 'project.task.revision.repair'::text) AND ((permission_id)::text = 'project.task.manage'::text))"
    if value.count(anchor) != 2 or "project.task.revision.repair" in value:
        raise RuntimeError("revision repair AUTH action constraint shape changed")
    op.execute(f"ALTER TABLE public.audit_events DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE public.audit_events ADD CONSTRAINT {name} " + value.replace(anchor, anchor + addition))

    name = "ck_audit_events_authority_privacy_bounds"
    value = definition(name)
    resource = value.index("resource_type IS NULL")
    array = value.index("ARRAY[", resource) + len("ARRAY[")
    # Older deployments may already carry this generic TASK authority resource.
    if "('task_authority'::character varying)::text" not in value[resource:value.index("target_ref_kind IS NULL", resource)]:
        value = value[:array] + "('task_authority'::character varying)::text, " + value[array:]
        op.execute(f"ALTER TABLE public.audit_events DROP CONSTRAINT {name}")
        op.execute(f"ALTER TABLE public.audit_events ADD CONSTRAINT {name} " + value)


def upgrade():
    """Keep historical facts valid and require exact new-effect revision receipts."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    _extend_repair_audit_contract()
    op.execute("ALTER TABLE public.submission_dispatches DROP CONSTRAINT ck_submission_dispatches_creation_shape")
    op.execute("""ALTER TABLE public.submission_dispatches ADD CONSTRAINT ck_submission_dispatches_creation_shape
      CHECK ((submission_version > 0 AND creation_kind='initial' AND creation_status='in_progress'
        AND checker_remediation_manifest_id IS NULL) OR
        (submission_version > 1 AND creation_kind='checker_remediation'
        AND creation_status='needs_revision' AND checker_remediation_manifest_id IS NOT NULL))""")
    op.execute("\nCREATE TABLE public.task_revision_preparations (\n\tid UUID NOT NULL, \n\tproject_id UUID NOT NULL, \n\ttask_id UUID NOT NULL, \n\tassignment_id UUID NOT NULL, \n\tcontributor_id UUID NOT NULL, \n\tsubmission_id UUID NOT NULL, \n\trouting_manifest_id UUID NOT NULL, \n\tpredecessor_id UUID, \n\tsequence INTEGER NOT NULL, \n\tsource_submission_version INTEGER NOT NULL, \n\tnext_revision_round INTEGER NOT NULL, \n\tmax_revision_rounds INTEGER NOT NULL, \n\trequested_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tdeadline_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL, \n\tcreation_xid VARCHAR(20) DEFAULT pg_current_xact_id()::text NOT NULL, \n\toutcome VARCHAR(16) NOT NULL, \n\tblocked_reason VARCHAR(40), \n\tpacket JSONB NOT NULL, \n\tpreparation_sha256 VARCHAR(71) NOT NULL, \n\tauthorization_decision_id UUID NOT NULL, \n\taudit_event_id UUID NOT NULL, \n\tCONSTRAINT pk_task_revision_preparations PRIMARY KEY (id), \n\tCONSTRAINT ck_task_revision_preparations_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128), \n\tCONSTRAINT fk_revision_preparation_task_project FOREIGN KEY(task_id, project_id) REFERENCES workstream_tasks (id, project_id), \n\tCONSTRAINT fk_revision_preparation_assignment FOREIGN KEY(assignment_id, task_id, contributor_id) REFERENCES task_assignments (id, task_id, contributor_id), \n\tCONSTRAINT fk_revision_preparation_submission FOREIGN KEY(submission_id, task_id, source_submission_version) REFERENCES submissions (id, task_id, version), \n\tCONSTRAINT uq_revision_preparation_successor UNIQUE (predecessor_id), \n\tCONSTRAINT uq_revision_preparation_sequence UNIQUE (routing_manifest_id, sequence), \n\tCONSTRAINT ck_task_revision_preparations_positive_rounds CHECK (sequence > 0 and source_submission_version > 0 and next_revision_round > 0 and max_revision_rounds > 0), \n\tCONSTRAINT ck_task_revision_preparations_chain_shape CHECK ((sequence = 1) = (predecessor_id IS NULL)), \n\tCONSTRAINT ck_task_revision_preparations_outcome CHECK (outcome in ('kept','rebased','blocked')), \n\tCONSTRAINT ck_task_revision_preparations_blocked_reason CHECK (blocked_reason is null or blocked_reason in ('context_blocked','revision_limit_reached','revision_deadline_expired')), \n\tCONSTRAINT ck_task_revision_preparations_blocked_shape CHECK ((outcome = 'blocked') = (blocked_reason IS NOT NULL)), \n\tCONSTRAINT ck_task_revision_preparations_digest CHECK (preparation_sha256 ~ '^sha256:[0-9a-f]{64}$'), \n\tCONSTRAINT ck_task_revision_preparations_deadline CHECK (deadline_at > requested_at), \n\tCONSTRAINT fk_task_revision_preparations_routing_manifest_id_task__85db FOREIGN KEY(routing_manifest_id) REFERENCES task_post_submit_routing_manifests (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_task_revision_preparations_predecessor_id_task_revis_ac5f FOREIGN KEY(predecessor_id) REFERENCES task_revision_preparations (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_task_revision_preparations_authorization_decision_id_4599 FOREIGN KEY(authorization_decision_id) REFERENCES audit_events (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_task_revision_preparations_audit_event_id_audit_events FOREIGN KEY(audit_event_id) REFERENCES audit_events (id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED\n)\n\n")
    op.execute('CREATE UNIQUE INDEX uq_revision_preparation_root ON task_revision_preparations (routing_manifest_id) WHERE predecessor_id IS NULL')
    op.execute('ALTER TABLE public.task_revision_preparations ADD CONSTRAINT uq_revision_preparation_identity_digest UNIQUE (id, preparation_sha256)')
    op.execute("ALTER TABLE public.task_revision_preparations ADD COLUMN repair_actor_id uuid")
    op.execute("ALTER TABLE public.task_revision_preparations ADD COLUMN repair_idempotency_key uuid")
    op.execute("ALTER TABLE public.task_revision_preparations ADD COLUMN repair_request_digest varchar(71)")
    op.execute("ALTER TABLE public.task_revision_preparations ADD COLUMN repair_reason varchar(1000)")
    op.execute("ALTER TABLE public.task_revision_preparations ADD COLUMN repair_authority_context jsonb")
    op.execute("ALTER TABLE public.task_revision_preparations ADD CONSTRAINT uq_revision_repair_actor_key UNIQUE (repair_actor_id,repair_idempotency_key)")
    op.execute("""ALTER TABLE public.task_revision_preparations
      ADD CONSTRAINT ck_revision_preparation_repair_shape CHECK (
        (predecessor_id IS NULL AND repair_actor_id IS NULL AND repair_idempotency_key IS NULL
          AND repair_request_digest IS NULL AND repair_reason IS NULL AND repair_authority_context IS NULL)
        OR (repair_actor_id IS NOT NULL AND repair_idempotency_key IS NOT NULL
          AND repair_request_digest IS NOT NULL AND repair_request_digest ~ '^sha256:[0-9a-f]{64}$'
          AND repair_reason IS NOT NULL AND octet_length(btrim(repair_reason)) BETWEEN 1 AND 1000
          AND repair_authority_context IS NOT NULL AND jsonb_typeof(repair_authority_context)='object'))""")
    op.execute("""
CREATE FUNCTION public.revision_routing_source_current(manifest uuid)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT EXISTS (
   SELECT 1 FROM public.task_post_submit_routing_manifests m
   JOIN public.submissions s ON s.id=m.submission_id
   JOIN public.checker_submission_fences f ON f.submission_id=s.id
   WHERE m.id=manifest AND m.routing_recommendation='needs_revision'
     AND s.task_id=m.task_id AND s.version=m.submission_version
     AND f.current_run_id=m.checker_run_id
     AND NOT EXISTS (SELECT 1 FROM public.submissions later
       WHERE later.task_id=m.task_id AND later.version>s.version)
 );
$$;
    """)
    op.execute("""
CREATE FUNCTION public.revision_preparation_source_current(p public.task_revision_preparations)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT EXISTS (
   SELECT 1 FROM public.task_post_submit_routing_manifests m
   JOIN public.checker_submission_fences f ON f.submission_id=m.submission_id
   JOIN public.submissions s ON s.id=m.submission_id
   WHERE m.id=p.routing_manifest_id AND m.project_id=p.project_id
     AND m.task_id=p.task_id AND m.assignment_id=p.assignment_id
     AND m.contributor_id=p.contributor_id AND m.submission_id=p.submission_id
     AND m.submission_version=p.source_submission_version
     AND m.routing_recommendation='needs_revision'
     AND f.current_run_id=m.checker_run_id
     AND s.task_id=p.task_id AND s.version=p.source_submission_version
     AND NOT EXISTS (SELECT 1 FROM public.submissions later
       WHERE later.task_id=p.task_id AND later.version>s.version)
     AND NOT EXISTS (SELECT 1 FROM public.task_revision_preparations child
       WHERE child.predecessor_id=p.id)
 );
$$;
    """)
    op.execute("""
CREATE FUNCTION public.revision_task_lineage(value jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT jsonb_object_agg(part.key,part.value) FROM jsonb_each(value) AS part(key,value)
 WHERE part.key IN ('locked_guide_version','locked_guide_source_snapshot_id',
 'locked_guide_source_snapshot_hash','locked_effective_project_submission_artifact_policy_id',
 'locked_effective_project_submission_artifact_policy_hash','locked_pre_submit_checker_policy_id',
 'locked_pre_submit_checker_bundle_hash','locked_post_submit_checker_policy_id',
 'locked_post_submit_checker_policy_version','locked_post_submit_checker_policy_hash',
 'locked_review_policy_id','locked_review_policy_generation','locked_review_policy_hash',
 'locked_revision_policy_id','locked_revision_policy_generation','locked_revision_policy_hash',
 'locked_contribution_policy_version_id');
$$;
    """)
    op.execute("""
CREATE FUNCTION public.revision_activation_lineage(receipt jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT jsonb_build_object(
 'locked_guide_version',receipt#>'{command,target,proposal,guide_version}',
 'locked_guide_source_snapshot_id',receipt#>'{command,target,proposal,source_snapshot_id}',
 'locked_guide_source_snapshot_hash',receipt#>'{command,target,proposal,source_snapshot_hash}',
 'locked_effective_project_submission_artifact_policy_id',receipt#>'{command,target,upstream,effective_policy_id}',
 'locked_effective_project_submission_artifact_policy_hash',receipt#>'{command,target,upstream,effective_policy_hash}',
 'locked_pre_submit_checker_policy_id',receipt#>'{command,target,upstream,pre_submit_policy_id}',
 'locked_pre_submit_checker_bundle_hash',receipt#>'{command,target,upstream,pre_submit_bundle_hash}',
 'locked_post_submit_checker_policy_id',receipt#>'{command,target,policy_id}',
 'locked_post_submit_checker_policy_version',receipt#>'{command,target,proposal,guide_version}',
 'locked_post_submit_checker_policy_hash',receipt#>'{command,target,policy_hash}',
 'locked_review_policy_id',receipt#>'{command,review,policy_id}',
 'locked_review_policy_generation',receipt#>'{command,review,generation}',
 'locked_review_policy_hash',receipt#>'{command,review,policy_hash}',
 'locked_revision_policy_id',receipt#>'{command,revision,policy_id}',
 'locked_revision_policy_generation',receipt#>'{command,revision,generation}',
 'locked_revision_policy_hash',receipt#>'{command,revision,policy_hash}',
 'locked_contribution_policy_version_id',receipt#>'{command,contribution_policy_version_id}');
$$;
    """)
    op.execute("""
CREATE FUNCTION public.require_revision_snapshot(snapshot jsonb, project uuid, active boolean) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE r public.guide_mutation_idempotency_records%ROWTYPE;
BEGIN
 SELECT * INTO r FROM public.guide_mutation_idempotency_records
 WHERE operation_id=(snapshot->>'activation_operation_id')::uuid
   AND project_id=project AND resource_id=(snapshot->>'guide_id')::uuid
   AND action_id='project.guide.activate' AND status='committed';
 IF NOT FOUND OR snapshot->'lineage' IS DISTINCT FROM public.revision_activation_lineage(r.response_json::jsonb)
    OR (snapshot->>'activation_generation')::integer IS DISTINCT FROM r.operation_generation
    OR (snapshot->>'activated_at')::timestamptz IS DISTINCT FROM (r.response_json->>'effective_at')::timestamptz
 THEN RAISE EXCEPTION 'revision activation context differs' USING ERRCODE='23514'; END IF;
 PERFORM public.require_guide_activation_custody(r.operation_id,false);
 IF active THEN
   PERFORM 1 FROM public.projects p WHERE p.id=project AND p.status='active' FOR UPDATE;
   IF NOT FOUND THEN RAISE EXCEPTION 'revision active project unavailable' USING ERRCODE='23514'; END IF;
   PERFORM 1 FROM public.project_guides g
   WHERE g.id=r.resource_id AND g.project_id=project AND g.status='active'
     AND g.activation_operation_id=r.operation_id
   FOR UPDATE;
   IF NOT FOUND THEN RAISE EXCEPTION 'revision active guide unavailable' USING ERRCODE='23514'; END IF;
 END IF;
END $$;
    """)
    op.execute("""
CREATE FUNCTION public.revision_task_context_digest(t public.workstream_tasks) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT 'sha256:'||pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
   public.project_guide_projection_canonical_json(
     public.revision_task_lineage(to_jsonb(t)) || jsonb_build_object(
       'locked_post_submit_checker_policy_body',t.locked_post_submit_checker_policy_body::jsonb)),
   'UTF8')),'hex');
$$;
    """)
    op.execute("""
CREATE FUNCTION public.guard_revision_preparation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE m public.task_post_submit_routing_manifests%ROWTYPE;
 s public.submissions%ROWTYPE; t public.workstream_tasks%ROWTYPE;
 a public.task_assignments%ROWTYPE;
 prior public.task_revision_preparations%ROWTYPE; policy public.revision_policies%ROWTYPE;
 c jsonb; target_limit integer; reason text; expected_outcome text; stamp jsonb;
 auth_context jsonb; auth_digest text; source_round integer;
BEGIN
 IF TG_OP <> 'INSERT' THEN
   RAISE EXCEPTION 'revision preparation is immutable' USING ERRCODE='55000';
 END IF;
 SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id FOR UPDATE;
 SELECT * INTO m FROM public.task_post_submit_routing_manifests WHERE id=NEW.routing_manifest_id;
 SELECT * INTO s FROM public.submissions WHERE id=NEW.submission_id;
 IF m.id IS NULL OR s.id IS NULL OR t.id IS NULL
  OR m.routing_recommendation<>'needs_revision' OR t.status<>'needs_revision'
  OR ROW(NEW.project_id,NEW.task_id,NEW.assignment_id,NEW.contributor_id,NEW.submission_id,NEW.source_submission_version)
     IS DISTINCT FROM ROW(m.project_id,m.task_id,m.assignment_id,m.contributor_id,m.submission_id,m.submission_version)
  OR NEW.creation_xid IS DISTINCT FROM pg_current_xact_id()::text
  OR NEW.preparation_sha256 IS DISTINCT FROM 'sha256:'||pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(public.project_guide_projection_canonical_json(NEW.packet),'UTF8')),'hex')
  OR NEW.packet->>'domain' IS DISTINCT FROM 'workstream.task_revision_preparation.v1'
  OR (NEW.packet->>'id')::uuid IS DISTINCT FROM NEW.id
  OR (NEW.packet->>'routing_manifest_id')::uuid IS DISTINCT FROM NEW.routing_manifest_id
  OR (NEW.packet->>'predecessor_id')::uuid IS DISTINCT FROM NEW.predecessor_id
  OR (NEW.packet->>'sequence')::integer IS DISTINCT FROM NEW.sequence
  OR (NEW.packet->>'source_submission_version')::integer IS DISTINCT FROM NEW.source_submission_version
  OR (NEW.packet->>'next_revision_round')::integer IS DISTINCT FROM NEW.next_revision_round
  OR (NEW.packet->>'max_revision_rounds')::integer IS DISTINCT FROM NEW.max_revision_rounds
  OR (NEW.packet->>'requested_at')::timestamptz IS DISTINCT FROM NEW.requested_at
  OR (NEW.packet->>'deadline_at')::timestamptz IS DISTINCT FROM NEW.deadline_at
  OR NEW.packet->>'outcome' IS DISTINCT FROM NEW.outcome
  OR NEW.packet->>'blocked_reason' IS DISTINCT FROM NEW.blocked_reason
  OR NEW.packet->'previous_task_lineage' IS DISTINCT FROM public.revision_task_lineage(to_jsonb(t))
  OR jsonb_typeof(NEW.packet->'candidate') IS DISTINCT FROM 'object'
  OR NOT (NEW.packet->'candidate' ? 'target')
  OR NOT (NEW.packet->'candidate' ? 'target_max_revision_rounds')
 THEN RAISE EXCEPTION 'revision preparation source differs' USING ERRCODE='23514'; END IF;
 SELECT count(*) INTO source_round FROM public.submissions counted
 WHERE counted.task_assignment_id=NEW.assignment_id
   AND counted.version<=NEW.source_submission_version;
 IF NEW.next_revision_round IS DISTINCT FROM source_round THEN
   RAISE EXCEPTION 'revision assignment round differs' USING ERRCODE='23514'; END IF;
 c:=NEW.packet->'candidate';
 stamp:=public.revision_task_lineage(to_jsonb(s)) || jsonb_build_object('locked_contribution_policy_version_id',s.contribution_policy_version_id);
 IF c#>'{prior,lineage}' IS DISTINCT FROM stamp THEN
   RAISE EXCEPTION 'revision prior context differs' USING ERRCODE='23514'; END IF;
 PERFORM public.require_revision_snapshot(c->'prior',NEW.project_id,false);
 SELECT * INTO a FROM public.task_assignments WHERE id=NEW.assignment_id FOR UPDATE;
 IF a.id IS NULL OR a.project_id<>NEW.project_id OR a.task_id<>NEW.task_id
   OR a.contributor_id<>NEW.contributor_id OR a.status<>'active'
   OR a.accepted_at IS NULL OR a.released_at IS NOT NULL
   OR t.project_id<>NEW.project_id OR t.assigned_to<>NEW.contributor_id
   OR s.task_assignment_id<>NEW.assignment_id OR s.contributor_id<>NEW.contributor_id
   OR s.version<>NEW.source_submission_version
   OR NOT public.task_routing_context_valid(m)
 THEN RAISE EXCEPTION 'revision current source differs' USING ERRCODE='23514'; END IF;
 IF NOT public.revision_routing_source_current(NEW.routing_manifest_id) THEN
   RAISE EXCEPTION 'revision current source differs'
     USING ERRCODE='23514', CONSTRAINT='ck_revision_preparation_current_source';
 END IF;
 SELECT * INTO policy FROM public.revision_policies WHERE id=s.locked_revision_policy_id;
 IF policy.id IS NULL OR policy.semantics_status<>'complete'
  OR policy.project_id<>NEW.project_id OR policy.guide_version<>s.locked_guide_version
  OR policy.policy_generation<>s.locked_revision_policy_generation
  OR policy.policy_hash<>s.locked_revision_policy_hash
  OR (c->>'max_revision_rounds')::integer IS DISTINCT FROM policy.max_revision_rounds
  OR (c->>'revision_deadline_hours')::integer IS DISTINCT FROM policy.revision_deadline_hours
 THEN RAISE EXCEPTION 'revision source policy differs' USING ERRCODE='23514'; END IF;
 IF NEW.predecessor_id IS NULL THEN
   IF NEW.sequence<>1 OR NEW.requested_at IS DISTINCT FROM m.created_at
    OR NEW.deadline_at IS DISTINCT FROM m.created_at + make_interval(hours=>policy.revision_deadline_hours)
    OR NEW.max_revision_rounds IS DISTINCT FROM policy.max_revision_rounds
   THEN RAISE EXCEPTION 'revision root custody differs' USING ERRCODE='23514'; END IF;
   IF NEW.repair_actor_id IS NULL AND
      (NEW.authorization_decision_id IS DISTINCT FROM m.authorization_decision_id
       OR NEW.audit_event_id IS DISTINCT FROM m.audit_event_id)
   THEN RAISE EXCEPTION 'revision routing root authority differs' USING ERRCODE='23514'; END IF;
 ELSE
   SELECT * INTO prior FROM public.task_revision_preparations WHERE id=NEW.predecessor_id;
   IF prior.id IS NULL OR prior.routing_manifest_id<>m.id OR NEW.sequence<>prior.sequence+1
    OR ROW(prior.project_id,prior.task_id,prior.assignment_id,prior.contributor_id,
           prior.submission_id,prior.source_submission_version,prior.next_revision_round)
       IS DISTINCT FROM ROW(NEW.project_id,NEW.task_id,NEW.assignment_id,
                            NEW.contributor_id,NEW.submission_id,NEW.source_submission_version,
                            NEW.next_revision_round)
    OR ROW(NEW.requested_at,NEW.deadline_at,NEW.max_revision_rounds)
       IS DISTINCT FROM ROW(prior.requested_at,prior.deadline_at,prior.max_revision_rounds)
   THEN RAISE EXCEPTION 'revision successor custody differs' USING ERRCODE='23514'; END IF;
   IF prior.deadline_at<=clock_timestamp() THEN
     RAISE EXCEPTION 'revision deadline expired'
       USING ERRCODE='23514', CONSTRAINT='ck_revision_preparation_deadline_expired';
   END IF;
   IF NEW.next_revision_round>NEW.max_revision_rounds
     OR EXISTS(SELECT 1 FROM public.task_revision_preparations child
       WHERE child.predecessor_id=prior.id)
   THEN RAISE EXCEPTION 'revision repair window unavailable' USING ERRCODE='23514'; END IF;
 END IF;
 IF NEW.repair_actor_id IS NOT NULL THEN
   auth_context:=NEW.repair_authority_context;
   IF auth_context IS DISTINCT FROM jsonb_build_object(
     'resource_type','task_authority','resource_id',NEW.task_id::text,
     'scope_project_id',NEW.project_id::text,'actor_profile_id',NEW.repair_actor_id::text,
     'identity_link_id',auth_context->'identity_link_id',
     'task_status','needs_revision','assigned_to',NEW.contributor_id::text,
     'assignment_id',NEW.assignment_id::text,
     'assignment_contributor_id',NEW.contributor_id::text,
     'locked_context_hash',public.revision_task_context_digest(t),
     'reason',NEW.repair_reason,'idempotency_key',NEW.repair_idempotency_key::text,
     'replay_assignment_id',NULL,'request_digest',NEW.repair_request_digest,
     'replay_command_id',NULL,'revision_preparation_id',prior.id::text,
     'revision_preparation_sha256',prior.preparation_sha256,
     'revision_routing_manifest_id',NEW.routing_manifest_id::text,
     'revision_replay_preparation_id',NULL)
   THEN RAISE EXCEPTION 'revision repair authorization context differs' USING ERRCODE='23514'; END IF;
   auth_digest:='sha256:'||pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
     public.project_guide_projection_canonical_json(jsonb_build_object(
       'resource_context',jsonb_strip_nulls(auth_context))), 'UTF8')),'hex');
   IF NOT EXISTS(SELECT 1 FROM public.audit_events decision
     WHERE decision.id=NEW.authorization_decision_id
       AND decision.event_domain='authority'
       AND decision.event_type='SensitiveAuthorizationAllowed'
       AND decision.action_id='project.task.revision.repair'
       AND decision.permission_id='project.task.manage'
       AND decision.resource_type='project'
       AND decision.resource_id=NEW.project_id::text
       AND decision.project_id=NEW.project_id
       AND decision.actor_id=NEW.repair_actor_id::text
       AND decision.denial_code IS NULL
       AND decision.after_facts::jsonb=jsonb_build_object(
         'allowed',true,'resource_context_digest',auth_digest))
   THEN RAISE EXCEPTION 'revision repair authorization unavailable' USING ERRCODE='23514'; END IF;
 END IF;
 IF c->'target' <> 'null'::jsonb THEN
   PERFORM public.require_revision_snapshot(c->'target',NEW.project_id,true);
   SELECT max_revision_rounds INTO target_limit FROM public.revision_policies
   WHERE id=(c#>>'{target,lineage,locked_revision_policy_id}')::uuid
     AND project_id=NEW.project_id AND semantics_status='complete'
     AND guide_version=c#>>'{target,lineage,locked_guide_version}'
     AND policy_generation=(c#>>'{target,lineage,locked_revision_policy_generation}')::integer
     AND policy_hash=c#>>'{target,lineage,locked_revision_policy_hash}';
   IF target_limit IS NULL OR (c->>'target_max_revision_rounds')::integer IS DISTINCT FROM target_limit
    OR NOT EXISTS (SELECT 1 FROM public.checker_policies p
       WHERE p.id=(c#>>'{target,lineage,locked_post_submit_checker_policy_id}')::uuid
         AND p.project_id=NEW.project_id
         AND p.guide_version=c#>>'{target,lineage,locked_guide_version}'
         AND p.policy_hash=c#>>'{target,lineage,locked_post_submit_checker_policy_hash}'
         AND p.policy_body::jsonb=(c->>'target_post_policy_json')::jsonb)
   THEN RAISE EXCEPTION 'revision target policy differs' USING ERRCODE='23514'; END IF;
 ELSE
   IF c->'target' IS DISTINCT FROM 'null'::jsonb OR c->'target_max_revision_rounds' IS DISTINCT FROM 'null'::jsonb
      OR c->'target_post_policy_json' IS DISTINCT FROM 'null'::jsonb
   THEN RAISE EXCEPTION 'revision absent target differs' USING ERRCODE='23514'; END IF;
 END IF;
 reason:=CASE WHEN NEW.next_revision_round>NEW.max_revision_rounds OR NEW.next_revision_round>target_limit
                 THEN 'revision_limit_reached'
              WHEN clock_timestamp()>=NEW.deadline_at THEN 'revision_deadline_expired'
              WHEN c->'target'='null'::jsonb THEN 'context_blocked' ELSE NULL END;
 expected_outcome:=CASE WHEN reason IS NOT NULL THEN 'blocked'
   WHEN c->'prior'=c->'target' THEN 'kept' ELSE 'rebased' END;
 IF NEW.repair_actor_id IS NOT NULL AND reason='revision_deadline_expired'
    AND NEW.blocked_reason IS DISTINCT FROM reason THEN
   RAISE EXCEPTION 'revision deadline expired'
     USING ERRCODE='23514', CONSTRAINT='ck_revision_preparation_deadline_expired';
 END IF;
 IF NEW.blocked_reason IS DISTINCT FROM reason OR NEW.outcome IS DISTINCT FROM expected_outcome THEN
   RAISE EXCEPTION 'revision disposition differs' USING ERRCODE='23514'; END IF;
 IF NEW.predecessor_id IS NOT NULL AND
    (NEW.outcome='blocked' OR c->'target' IS NOT DISTINCT FROM (prior.packet#>'{candidate,target}'))
 THEN RAISE EXCEPTION 'revision repair has no eligible changed target' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("CREATE TRIGGER revision_preparation_immutable BEFORE INSERT OR UPDATE OR DELETE ON public.task_revision_preparations FOR EACH ROW EXECUTE FUNCTION public.guard_revision_preparation()")
    op.execute("""
CREATE FUNCTION public.revision_task_update_authorized(old_task public.workstream_tasks,
  new_task public.workstream_tasks) RETURNS boolean
LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT EXISTS (SELECT 1 FROM public.task_revision_preparations p
   WHERE p.task_id=old_task.id AND p.project_id=old_task.project_id
     AND p.creation_xid=pg_current_xact_id()::text AND p.outcome IN ('kept','rebased')
     AND p.packet->'previous_task_lineage'=public.revision_task_lineage(to_jsonb(old_task))
     AND p.packet#>'{candidate,target,lineage}'=public.revision_task_lineage(to_jsonb(new_task))
     AND (p.packet#>>'{candidate,target_post_policy_json}')::jsonb
         IS NOT DISTINCT FROM new_task.locked_post_submit_checker_policy_body::jsonb
     AND old_task.status='needs_revision' AND new_task.status='needs_revision'
     AND old_task.assigned_to=p.contributor_id AND new_task.assigned_to=p.contributor_id);
$$;
    """)
    op.execute("""
CREATE FUNCTION public.guard_revision_task_lineage_update() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF public.revision_task_lineage(to_jsonb(NEW)) IS DISTINCT FROM
      public.revision_task_lineage(to_jsonb(OLD))
    OR NEW.locked_post_submit_checker_policy_body::jsonb IS DISTINCT FROM
       OLD.locked_post_submit_checker_policy_body::jsonb
 THEN
   IF OLD.status IN ('draft','screening') THEN RETURN NEW; END IF;
   IF NOT public.revision_task_update_authorized(OLD,NEW) THEN
     RAISE EXCEPTION 'task revision context lacks current preparation' USING ERRCODE='23514';
   END IF;
 END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("CREATE TRIGGER revision_task_lineage_update BEFORE UPDATE ON public.workstream_tasks FOR EACH ROW EXECUTE FUNCTION public.guard_revision_task_lineage_update()")
    op.execute("""
CREATE OR REPLACE FUNCTION public.protect_task_contribution_stamp() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_OP='INSERT' THEN
   IF NEW.status<>'draft' OR NEW.locked_contribution_policy_version_id IS NOT NULL THEN
     RAISE EXCEPTION 'task contribution stamp requires initial screening' USING ERRCODE='23514';
   END IF;
 ELSIF NEW.locked_contribution_policy_version_id IS DISTINCT FROM
       OLD.locked_contribution_policy_version_id THEN
   IF NOT (OLD.locked_contribution_policy_version_id IS NULL
       AND OLD.status='draft' AND NEW.status='screening'
       AND NEW.locked_contribution_policy_version_id IS NOT NULL)
     AND NOT public.revision_task_update_authorized(OLD,NEW)
   THEN RAISE EXCEPTION 'task contribution stamp is immutable' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("""
CREATE OR REPLACE FUNCTION public.protect_assignment_contribution_stamp() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE task_stamp uuid;
BEGIN
 IF TG_OP='INSERT' THEN
   SELECT locked_contribution_policy_version_id INTO task_stamp
   FROM public.workstream_tasks WHERE id=NEW.task_id AND project_id=NEW.project_id FOR SHARE;
   IF task_stamp IS NULL OR task_stamp IS DISTINCT FROM
      NEW.submitter_contribution_policy_version_id THEN
     RAISE EXCEPTION 'assignment contribution stamp differs from task' USING ERRCODE='23514';
   END IF;
 ELSIF ROW(NEW.id,NEW.task_id,NEW.project_id,NEW.contributor_id) IS DISTINCT FROM
       ROW(OLD.id,OLD.task_id,OLD.project_id,OLD.contributor_id) THEN
   RAISE EXCEPTION 'assignment contribution identity is immutable' USING ERRCODE='23514';
 ELSIF NEW.submitter_contribution_policy_version_id IS DISTINCT FROM
       OLD.submitter_contribution_policy_version_id THEN
   IF NOT (OLD.status='active' AND NEW.status='active' AND OLD.released_at IS NULL
     AND NEW.released_at IS NULL AND EXISTS (
       SELECT 1 FROM public.task_revision_preparations p
       WHERE p.assignment_id=OLD.id AND p.task_id=OLD.task_id
         AND p.contributor_id=OLD.contributor_id AND p.project_id=OLD.project_id
         AND p.creation_xid=pg_current_xact_id()::text AND p.outcome IN ('kept','rebased')
         AND (p.packet#>>'{previous_task_lineage,locked_contribution_policy_version_id}')::uuid
             =OLD.submitter_contribution_policy_version_id
         AND (p.packet#>>'{candidate,target,lineage,locked_contribution_policy_version_id}')::uuid
             =NEW.submitter_contribution_policy_version_id
     )) THEN
     RAISE EXCEPTION 'assignment contribution identity is immutable' USING ERRCODE='23514';
   END IF;
 END IF;
 RETURN NEW;
END $$;
    """)
    # A retained dispatch compares immutable facts with immutable facts. Its
    # original mutable Assignment comparison is moved to a new-effect guard.
    _replace("public.submission_dispatch_valid(public.submission_dispatches)",
             "AND assignment.submitter_contribution_policy_version_id=s.contribution_policy_version_id", "")
    _replace("public.guard_submission_dispatch_receipt()",
             "IF NOT public.submission_dispatch_valid(NEW) THEN",
             """IF NOT EXISTS (SELECT 1 FROM public.submissions s
   JOIN public.task_assignments a ON a.id=s.task_assignment_id
   JOIN public.workstream_tasks t ON t.id=s.task_id
   WHERE s.id=NEW.submission_id AND a.id=NEW.assignment_id AND t.id=NEW.task_id
     AND s.contribution_policy_version_id=a.submitter_contribution_policy_version_id
     AND s.contribution_policy_version_id=t.locked_contribution_policy_version_id)
 THEN RAISE EXCEPTION 'new dispatch contribution context differs' USING ERRCODE='23514'; END IF;
 IF NOT public.submission_dispatch_valid(NEW) THEN""")
    op.execute("""
CREATE FUNCTION public.revision_submission_lineage(s public.submissions) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT public.revision_task_lineage(to_jsonb(s)) ||
   jsonb_build_object('locked_contribution_policy_version_id',s.contribution_policy_version_id);
$$;
    """)
    op.execute("""
CREATE FUNCTION public.guard_new_revision_submission() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE t public.workstream_tasks%ROWTYPE; a public.task_assignments%ROWTYPE;
 p public.task_revision_preparations%ROWTYPE; prior public.submissions%ROWTYPE;
BEGIN
 IF NEW.supersedes_submission_id IS NULL THEN RETURN NEW; END IF;
 SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id FOR UPDATE;
 SELECT * INTO a FROM public.task_assignments WHERE id=NEW.task_assignment_id FOR UPDATE;
 SELECT * INTO prior FROM public.submissions WHERE id=NEW.supersedes_submission_id FOR UPDATE;
 SELECT * INTO p FROM public.task_revision_preparations
 WHERE submission_id=NEW.supersedes_submission_id
   AND task_id=NEW.task_id AND assignment_id=NEW.task_assignment_id
   AND contributor_id=NEW.contributor_id
   AND EXISTS (SELECT 1 FROM public.task_post_submit_routing_manifests m
     JOIN public.checker_submission_fences f ON f.submission_id=m.submission_id
     WHERE m.id=task_revision_preparations.routing_manifest_id
       AND f.current_run_id=m.checker_run_id)
   AND NOT EXISTS (SELECT 1 FROM public.task_revision_preparations child
     WHERE child.predecessor_id=task_revision_preparations.id);
 IF t.id IS NULL OR a.id IS NULL OR prior.id IS NULL OR p.id IS NULL
   OR t.status<>'needs_revision' OR t.assigned_to<>NEW.contributor_id
   OR a.status<>'active' OR a.accepted_at IS NULL OR a.released_at IS NOT NULL
   OR a.project_id<>t.project_id OR a.contributor_id<>NEW.contributor_id
   OR a.submitter_contribution_policy_version_id<>NEW.contribution_policy_version_id
   OR t.locked_contribution_policy_version_id<>NEW.contribution_policy_version_id
   OR prior.version<>p.source_submission_version OR NEW.version<>p.source_submission_version+1
   OR p.outcome='blocked'
   OR p.packet#>'{candidate,target,lineage}' IS DISTINCT FROM
      public.revision_submission_lineage(NEW)
   OR p.packet#>'{candidate,target,lineage}' IS DISTINCT FROM
      public.revision_task_lineage(to_jsonb(t))
 THEN RAISE EXCEPTION 'revision context unavailable for new submission' USING ERRCODE='23514'; END IF;
 IF p.deadline_at<=clock_timestamp() THEN
   RAISE EXCEPTION 'revision deadline expired'
     USING ERRCODE='23514', CONSTRAINT='ck_revision_submission_deadline_expired';
 END IF;
 RETURN NEW;
END $$;
    """)
    # The existing 0040 capacity trigger runs first, preserving its exact
    # over-cap refusal even for a directly forged successor INSERT.
    op.execute("CREATE TRIGGER z_revision_submission_eligibility BEFORE INSERT ON public.submissions FOR EACH ROW EXECUTE FUNCTION public.guard_new_revision_submission()")
    op.execute("""
CREATE FUNCTION public.guard_revision_submission_deadline() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE deadline timestamptz;
BEGIN
 IF NEW.supersedes_submission_id IS NULL THEN RETURN NULL; END IF;
 SELECT p.deadline_at INTO deadline FROM public.task_revision_preparations p
   WHERE p.submission_id=NEW.supersedes_submission_id AND p.task_id=NEW.task_id
     AND p.assignment_id=NEW.task_assignment_id AND p.contributor_id=NEW.contributor_id
     AND p.source_submission_version+1=NEW.version AND p.outcome IN ('kept','rebased')
     AND p.packet#>'{candidate,target,lineage}'=public.revision_submission_lineage(NEW)
     AND EXISTS (SELECT 1 FROM public.task_post_submit_routing_manifests m
       JOIN public.checker_submission_fences f ON f.submission_id=m.submission_id
       WHERE m.id=p.routing_manifest_id AND f.current_run_id=m.checker_run_id)
     AND NOT EXISTS (SELECT 1 FROM public.task_revision_preparations child
       WHERE child.predecessor_id=p.id)
   ORDER BY p.sequence DESC LIMIT 1;
 IF deadline IS NULL THEN
   RAISE EXCEPTION 'revision context changed before commit'
     USING ERRCODE='23514', CONSTRAINT='ck_revision_submission_context_changed';
 END IF;
 IF deadline<=clock_timestamp() THEN
   RAISE EXCEPTION 'revision deadline expired before commit'
     USING ERRCODE='23514', CONSTRAINT='ck_revision_submission_deadline_expired';
 END IF;
 RETURN NULL;
END $$;
    """)
    op.execute("CREATE CONSTRAINT TRIGGER revision_submission_deadline AFTER INSERT ON public.submissions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_revision_submission_deadline()")
    op.execute("""
CREATE FUNCTION public.guard_revision_preparation_closure() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE p public.task_revision_preparations%ROWTYPE;
 t public.workstream_tasks%ROWTYPE; a public.task_assignments%ROWTYPE;
 m public.task_post_submit_routing_manifests%ROWTYPE; expected jsonb;
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
 IF p.repair_actor_id IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM public.audit_events event
   WHERE event.id=p.audit_event_id AND event.event_domain='legacy_lifecycle'
     AND event.event_type='TaskRevisionContextRepaired'
     AND event.entity_type='task' AND event.entity_id=p.task_id
     AND event.actor_id=p.repair_actor_id::text
     AND event.auth_source='local_lifecycle' AND event.is_dev_auth=false
     AND event.from_status IS NULL AND event.to_status IS NULL
     AND event.reason=p.repair_reason
     AND event.event_payload::jsonb=jsonb_build_object('references',jsonb_build_object(
       'project_id',p.project_id::text,'task_id',p.task_id::text,
       'assignment_id',p.assignment_id::text,'submission_id',p.submission_id::text,
       'routing_manifest_id',p.routing_manifest_id::text,
       'revision_preparation_id',p.id::text,
       'authorization_decision_id',p.authorization_decision_id::text))
 ) THEN RAISE EXCEPTION 'revision repair audit unavailable' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END $$;
    """)
    op.execute("CREATE CONSTRAINT TRIGGER revision_preparation_closure AFTER INSERT ON public.task_revision_preparations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_revision_preparation_closure()")
    op.execute("""
CREATE FUNCTION public.reject_revision_preparation_truncate() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN RAISE EXCEPTION 'revision preparations are immutable' USING ERRCODE='55000'; END $$;
    """)
    op.execute("CREATE TRIGGER revision_preparation_no_truncate BEFORE TRUNCATE ON public.task_revision_preparations FOR EACH STATEMENT EXECUTE FUNCTION public.reject_revision_preparation_truncate()")
    op.execute("ALTER TABLE public.submission_bundle_admissions ADD COLUMN revision_preparation_id uuid")
    op.execute("ALTER TABLE public.submission_bundle_admissions ADD COLUMN revision_preparation_sha256 varchar(71)")
    op.execute("ALTER TABLE public.submission_bundle_admissions ADD CONSTRAINT ck_submission_bundle_admissions_revision_preparation_shape CHECK ((revision_preparation_id IS NULL)=(revision_preparation_sha256 IS NULL))")
    op.execute("ALTER TABLE public.submission_bundle_admissions ADD CONSTRAINT ck_submission_bundle_admissions_revision_preparation_digest CHECK (revision_preparation_sha256 IS NULL OR revision_preparation_sha256 ~ '^sha256:[0-9a-f]{64}$')")
    op.execute("ALTER TABLE public.submission_bundle_admissions ADD CONSTRAINT fk_submission_bundle_admission_revision_preparation FOREIGN KEY (revision_preparation_id,revision_preparation_sha256) REFERENCES public.task_revision_preparations(id,preparation_sha256) ON DELETE RESTRICT")
    op.execute("""
CREATE FUNCTION public.guard_revision_admission_context() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE request jsonb; t public.workstream_tasks%ROWTYPE;
 a public.task_assignments%ROWTYPE; predecessor public.submissions%ROWTYPE;
 p public.task_revision_preparations%ROWTYPE;
BEGIN
 SELECT selected_request_json INTO request FROM public.submission_bundle_durable_intents
 WHERE id=NEW.durable_intent_id;
 IF NEW.predecessor_submission_id IS NULL THEN
   IF NEW.revision_preparation_id IS NOT NULL OR NEW.revision_preparation_sha256 IS NOT NULL
      OR request#>'{admission_lineage,revision_preparation_id}' IS NOT NULL
      OR request#>'{admission_lineage,revision_preparation_sha256}' IS NOT NULL
   THEN RAISE EXCEPTION 'initial admission has revision preparation' USING ERRCODE='23514'; END IF;
   RETURN NEW;
 END IF;
 SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id FOR UPDATE;
 SELECT * INTO a FROM public.task_assignments WHERE id=NEW.assignment_id FOR UPDATE;
 SELECT * INTO predecessor FROM public.submissions
 WHERE id=NEW.predecessor_submission_id FOR UPDATE;
 SELECT * INTO p FROM public.task_revision_preparations
 WHERE id=NEW.revision_preparation_id;
 IF request IS NULL OR NEW.selected_pre_submit_run_id IS NULL
   OR NEW.revision_preparation_id IS NULL OR NEW.revision_preparation_sha256 IS NULL
   OR NEW.revision_preparation_id::text IS DISTINCT FROM
      request#>>'{admission_lineage,revision_preparation_id}'
   OR NEW.revision_preparation_sha256 IS DISTINCT FROM
      request#>>'{admission_lineage,revision_preparation_sha256}'
   OR p.id IS NULL OR p.preparation_sha256<>NEW.revision_preparation_sha256
   OR p.outcome='blocked'
   OR ROW(p.project_id,p.task_id,p.assignment_id,p.contributor_id,p.submission_id,
          p.source_submission_version,p.routing_manifest_id)
      IS DISTINCT FROM ROW(NEW.project_id,NEW.task_id,NEW.assignment_id,
        NEW.actor_profile_id,NEW.predecessor_submission_id,
        NEW.predecessor_submission_version,NEW.checker_remediation_manifest_id)
   OR t.id IS NULL OR t.status<>'needs_revision' OR t.assigned_to<>NEW.actor_profile_id
   OR a.id IS NULL OR a.status<>'active' OR a.released_at IS NOT NULL
   OR predecessor.id IS NULL OR predecessor.version<>p.source_submission_version
   OR p.packet#>'{candidate,target,lineage}' IS DISTINCT FROM
      public.revision_task_lineage(to_jsonb(t))
   OR NOT EXISTS (SELECT 1 FROM public.task_post_submit_routing_manifests m
      JOIN public.checker_submission_fences f ON f.submission_id=m.submission_id
      WHERE m.id=p.routing_manifest_id AND f.current_run_id=m.checker_run_id)
   OR EXISTS(SELECT 1 FROM public.task_revision_preparations child
     WHERE child.predecessor_id=p.id)
 THEN RAISE EXCEPTION 'revision admission context unavailable' USING ERRCODE='23514'; END IF;
 IF p.deadline_at<=clock_timestamp() THEN
   RAISE EXCEPTION 'revision admission deadline expired'
     USING ERRCODE='23514', CONSTRAINT='ck_revision_admission_deadline_expired';
 END IF;
 RETURN NEW;
END $$;
    """)
    op.execute("CREATE TRIGGER a_revision_admission_context BEFORE INSERT ON public.submission_bundle_admissions FOR EACH ROW EXECUTE FUNCTION public.guard_revision_admission_context()")


def downgrade() -> None:
    """Retained revision custody cannot be safely removed in place."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
