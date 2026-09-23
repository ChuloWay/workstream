"""Bind assignment release receipts to exact fixed-service decisions."""

from alembic import op
import sqlalchemy as sa

revision = "0029_assignment_authority"
down_revision = "0028_outbox_dispatch_authority"
branch_labels = None
depends_on = None


def upgrade():
    """Extend closed vocabularies without provisioning or fabricating evidence."""
    op.execute("lock table actor_profiles, audit_events in access exclusive mode")
    op.execute("""
        do $$ begin
          if exists(select 1 from audit_events where event_type='TaskAssignmentAuthorityRevoked') then
            raise exception 'assignment releases without exact service authority prevent activation';
          end if;
        end $$;
    """)
    connection = op.get_bind()
    for table, name, anchor, addition, expected in (
        (
            "actor_profiles", "ck_actor_profiles_kind_service_identity",
            "'workstream.outbox.dispatcher'::character varying",
            ", 'workstream.task.assignment_reconciler'::character varying", 1,
        ),
        (
            "audit_events", "ck_audit_events_authority_registries",
            "('outbox.dispatch'::character varying)::text",
            ", ('task.assignment.authority_reconcile'::character varying)::text", 1,
        ),
        (
            "audit_events", "ck_audit_events_authorization_action_evidence",
            "(((action_id)::text = 'outbox.dispatch'::text) AND ((permission_id)::text = 'outbox.dispatch'::text))",
            " OR (((action_id)::text = 'task.assignment.authority_reconcile'::text) AND ((permission_id)::text = 'task.assignment.authority_reconcile'::text))", 2,
        ),
    ):
        definition = connection.execute(sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid=cast(:table as regclass) and conname=:name"
        ), {"table": table, "name": name}).scalar_one()
        if definition.count(anchor) != expected or addition in definition:
            raise RuntimeError("assignment authority constraint shape changed")
        op.execute(f"alter table {table} drop constraint {name}")
        op.execute(f"alter table {table} add constraint {name} " + definition.replace(anchor, anchor + addition))
    op.execute("""
        create function guard_assignment_release_authority() returns trigger
        language plpgsql as $$
        declare d audit_events%rowtype; refs jsonb; facts jsonb; target jsonb; digest text;
        begin
          if new.event_type <> 'TaskAssignmentAuthorityRevoked' then return new; end if;
          refs := new.event_payload->'references';
          digest := new.event_payload->>'authorization_resource_digest';
          facts := new.event_payload::jsonb->'assignment_invalidation_facts';
          target := facts->'target';
          select * into d from audit_events where id=refs->>'authorization_decision_id';
          if not found or not coalesce(
            new.event_domain='legacy_lifecycle' and new.auth_source='local_lifecycle'
            and new.entity_type='task' and new.is_dev_auth=false
            and new.from_status in ('claimed','in_progress') and new.to_status='ready'
            and new.reason='lifecycle_state_changed'
            and digest ~ '^sha256:[0-9a-f]{64}$'
            and new.event_payload::jsonb=jsonb_build_object('references',refs,'authorization_resource_digest',digest,
              'assignment_invalidation_facts',facts)
            and target=jsonb_build_object('project_id',refs->>'project_id','task_id',new.entity_id,
              'assignment_id',refs->>'assignment_id','contributor_id',target->>'contributor_id',
              'authority_invalidation_event_id',refs->>'authority_invalidation_event_id')
            and jsonb_typeof(facts)='object'
            and octet_length(convert_to(project_guide_projection_canonical_json(facts),'UTF8'))<=4096
            and facts=jsonb_build_object('target',target,'cause_event_id',facts->'cause_event_id',
              'delivery_event_id',facts->'delivery_event_id','delivery_generation',facts->'delivery_generation',
              'cause_digest',facts->'cause_digest','invocation_digest',facts->'invocation_digest',
              'task_status',facts->'task_status','locked_context_hash',facts->'locked_context_hash')
            and jsonb_typeof(facts->'delivery_generation')='number'
            and (facts->>'delivery_generation') ~ '^[1-9][0-9]*$'
            and not exists(select 1 from jsonb_each(target) f where jsonb_typeof(f.value)<>'string'
              or (f.value#>>'{}') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
            and not exists(select 1 from jsonb_each(facts) f where f.key in ('cause_event_id','delivery_event_id')
              and (jsonb_typeof(f.value)<>'string' or (f.value#>>'{}') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'))
            and not exists(select 1 from jsonb_each(facts) f where f.key in ('cause_digest','invocation_digest','locked_context_hash')
              and (jsonb_typeof(f.value)<>'string' or (f.value#>>'{}') !~ '^sha256:[0-9a-f]{64}$'))
            and facts->>'task_status'=new.from_status
            and digest='sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(
              jsonb_build_object('resource_context',jsonb_build_object(
                'resource_type','task_authority','resource_id',new.entity_id,
                'scope_project_id',refs->>'project_id','facts',facts))), 'UTF8')), 'hex')
            and refs=jsonb_build_object(
              'project_id',refs->>'project_id','task_id',new.entity_id,
              'assignment_id',refs->>'assignment_id',
              'authority_invalidation_event_id',refs->>'authority_invalidation_event_id',
              'authorization_decision_id',d.id)
            and d.event_domain='authority' and d.event_type='SensitiveAuthorizationAllowed'
            and d.action_id='task.assignment.authority_reconcile'
            and d.permission_id='task.assignment.authority_reconcile'
            and d.actor_id=new.actor_id and d.actor_ref_kind='actor_profile'
            and d.resource_type='task' and d.resource_id=new.entity_id
            and d.project_id=refs->>'project_id'
            and d.request_id::text=facts->>'delivery_event_id'
            and d.correlation_id::text=refs->>'authority_invalidation_event_id'
            and d.after_facts::jsonb=jsonb_build_object('allowed',true,'resource_context_digest',digest)
            and exists(select 1 from actor_profiles p where p.id=d.actor_id
              and p.actor_kind='service' and p.service_identity='workstream.task.assignment_reconciler')
            and exists(select 1 from task_assignments a where a.id=refs->>'assignment_id'
              and a.task_id=new.entity_id and a.project_id=d.project_id
              and a.contributor_id=target->>'contributor_id')
            and exists(select 1 from audit_events cause where cause.id=refs->>'authority_invalidation_event_id'
              and cause.event_domain='authority' and cause.event_type='AuthorityInvalidationRequested'
              and cause.invalidation_cause_event_id=facts->>'cause_event_id'),
            false
          ) then raise exception 'assignment release authority mismatch'; end if;
          return new;
        end $$;
    """)
    op.execute("""
        create trigger assignment_release_authority
        before insert on audit_events for each row execute function guard_assignment_release_authority();
    """)


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
