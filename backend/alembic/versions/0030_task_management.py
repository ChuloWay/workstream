"""Authorize manager task readiness and retain exact replay/audit custody."""

from alembic import op
import sqlalchemy as sa

revision = "0030_task_management"
down_revision = "0029_assignment_authority"
branch_labels = None
depends_on = None

_RECEIPT_CHECKS = {
    "task_command_action": "action_id in ('task.claim','task.start','operations.task.start_override','project.task.create','project.task.screen','project.task.release')",
    "task_command_request_digest": "request_digest ~ '^sha256:[0-9a-f]{64}$'",
    "task_command_state_shape": "(status='pending' and assignment_id is null and contributor_id is null and locked_context_hash is null and response is null and committed_at is null) or (status='committed' and ((action_id in ('task.claim','task.start','operations.task.start_override') and assignment_id is not null and contributor_id is not null) or (action_id in ('project.task.create','project.task.screen','project.task.release') and assignment_id is null and contributor_id is null)) and locked_context_hash is not null and locked_context_hash ~ '^sha256:[0-9a-f]{64}$' and response is not null and jsonb_typeof(response)='object' and committed_at is not null)",
    "task_command_contributor": "status='pending' or action_id in ('project.task.create','project.task.screen','project.task.release') or (action_id='operations.task.start_override' and actor_profile_id<>contributor_id) or (action_id in ('task.claim','task.start') and actor_profile_id=contributor_id)",
}


def upgrade():
    op.execute(
        "lock table task_command_receipts, workstream_tasks, audit_events in access exclusive mode"
    )
    op.execute("""
      do $$ begin
        if exists(select 1 from task_command_receipts r
                  where not exists(select 1 from workstream_tasks t where t.id=r.task_id)) then
          raise exception 'unproven task receipt custody prevents migration';
        end if;
      end $$;
    """)
    for name, expression in _RECEIPT_CHECKS.items():
        if name == "task_command_request_digest":
            continue
        op.drop_constraint(
            op.f("ck_task_command_receipts_" + name), "task_command_receipts", type_="check"
        )
        op.create_check_constraint(
            op.f("ck_task_command_receipts_" + name), "task_command_receipts", expression
        )
    op.create_foreign_key(
        "fk_task_command_task",
        "task_command_receipts",
        "workstream_tasks",
        ["task_id"],
        ["id"],
        deferrable=True,
        initially="DEFERRED",
    )
    connection = op.get_bind()
    for name, anchor, addition, expected in (
        (
            "ck_audit_events_authorization_action_evidence",
            "(((action_id)::text = 'project.task.work_context.read'::text) AND ((permission_id)::text = 'project.task.manage'::text))",
            " OR (((action_id)::text = 'project.task.create'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'project.task.screen'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'project.task.release'::text) AND ((permission_id)::text = 'project.task.manage'::text))",
            2,
        ),
    ):
        definition = connection.execute(
            sa.text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid='audit_events'::regclass and conname=:name"
            ),
            {"name": name},
        ).scalar_one()
        if definition.count(anchor) != expected:
            raise RuntimeError("task authority constraint shape changed")
        op.execute(f"alter table audit_events drop constraint {name}")
        op.execute(
            f"alter table audit_events add constraint {name} "
            + definition.replace(anchor, anchor + addition)
        )
    op.execute(_MANAGER_AUDIT_GUARD)
    op.execute(
        "create trigger task_management_audit before insert on audit_events "
        "for each row execute function guard_task_management_audit()"
    )


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


_MANAGER_AUDIT_GUARD = r"""
create function guard_task_management_audit() returns trigger language plpgsql as $$
declare refs jsonb; payload jsonb; decision audit_events%rowtype; expected_action text; facts jsonb; digest text;
begin
  if new.event_type not in ('TaskCreated','TaskScreened','TaskReleased') then return new; end if;
  payload := new.event_payload::jsonb; refs := payload->'references';
  facts := payload->'manager_authority_facts'; digest := payload->>'authorization_resource_digest';
  expected_action := case new.event_type when 'TaskCreated' then 'project.task.create'
    when 'TaskScreened' then 'project.task.screen' else 'project.task.release' end;
  select * into decision from audit_events where id=refs->>'authorization_decision_id';
  if not found or not coalesce(
    new.event_domain='legacy_lifecycle' and new.auth_source='local_lifecycle'
    and new.entity_type='task' and new.is_dev_auth=false
    and refs=jsonb_build_object('project_id',refs->>'project_id','task_id',new.entity_id,
                               'authorization_decision_id',decision.id)
    and decision.event_domain='authority' and decision.event_type='SensitiveAuthorizationAllowed'
    and decision.action_id=expected_action and decision.permission_id='project.task.manage'
    and decision.actor_id=new.actor_id and decision.project_id=refs->>'project_id'
    and decision.resource_type='project' and decision.resource_id=refs->>'project_id'
    and exists(select 1 from workstream_tasks t where t.id=new.entity_id
      and t.project_id=refs->>'project_id' and t.status=new.to_status
      and (new.event_type<>'TaskCreated' or t.source_type=payload->>'source_type'))
    and facts=jsonb_build_object('resource_type','task_authority','resource_id',new.entity_id,
      'scope_project_id',refs->>'project_id','actor_profile_id',new.actor_id,
      'identity_link_id',facts->'identity_link_id','task_status',coalesce(new.from_status,'draft'),
      'assigned_to',null,'assignment_id',null,'assignment_contributor_id',null,
      'locked_context_hash',facts->'locked_context_hash','reason',facts->'reason',
      'idempotency_key',facts->'idempotency_key','replay_assignment_id',null,
      'request_digest',facts->'request_digest','replay_command_id',null)
    and octet_length(convert_to(project_guide_projection_canonical_json(facts),'UTF8'))<=4096
    and (facts->>'identity_link_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    and (facts->>'locked_context_hash') ~ '^sha256:[0-9a-f]{64}$'
    and exists(select 1 from actor_identity_links l where l.id=facts->>'identity_link_id' and l.actor_profile_id=new.actor_id)
    and (new.reason is not distinct from case when new.event_type='TaskCreated' then null
      when nullif(btrim(facts->>'reason'),'') is null then 'lifecycle_state_changed' else facts->>'reason' end)
    and (new.event_type<>'TaskCreated' or facts->'reason'='null'::jsonb)
    and exists(select 1 from task_command_receipts r where r.actor_profile_id=new.actor_id
      and r.action_id=expected_action and r.idempotency_key::text=facts->>'idempotency_key'
      and r.task_id=new.entity_id and r.request_digest=facts->>'request_digest' and r.status='pending')
    and digest='sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(
      jsonb_build_object('resource_context',jsonb_strip_nulls(facts))), 'UTF8')), 'hex')
    and decision.after_facts::jsonb=jsonb_build_object('allowed',true,'resource_context_digest',digest)
    and ((new.event_type='TaskCreated' and new.from_status is null and new.to_status='draft'
          and payload=jsonb_build_object('references',refs,'source_type',payload->'source_type',
            'manager_authority_facts',facts,'authorization_resource_digest',digest)
          and payload->>'source_type' in ('manual','markdown_import','csv_import'))
         or (new.event_type in ('TaskScreened','TaskReleased')
             and ((new.event_type='TaskScreened' and new.from_status='draft' and new.to_status='screening')
               or (new.event_type='TaskReleased' and new.from_status='screening' and new.to_status='ready'
                   and btrim(new.reason)<>''))
             and exists(select 1 from workstream_tasks t where t.id=new.entity_id and
              (payload - array['references','manager_authority_facts','authorization_resource_digest']) = jsonb_build_object('locked_guide_version', to_jsonb(t)->'locked_guide_version', 'locked_guide_source_snapshot_id', to_jsonb(t)->'locked_guide_source_snapshot_id', 'locked_guide_source_snapshot_hash', to_jsonb(t)->'locked_guide_source_snapshot_hash', 'locked_effective_project_submission_artifact_policy_id', to_jsonb(t)->'locked_effective_project_submission_artifact_policy_id', 'locked_effective_project_submission_artifact_policy_hash', to_jsonb(t)->'locked_effective_project_submission_artifact_policy_hash', 'locked_pre_submit_checker_policy_id', to_jsonb(t)->'locked_pre_submit_checker_policy_id', 'locked_pre_submit_checker_bundle_hash', to_jsonb(t)->'locked_pre_submit_checker_bundle_hash', 'locked_post_submit_checker_policy_id', to_jsonb(t)->'locked_post_submit_checker_policy_id', 'locked_post_submit_checker_policy_version', to_jsonb(t)->'locked_post_submit_checker_policy_version', 'locked_post_submit_checker_policy_hash', to_jsonb(t)->'locked_post_submit_checker_policy_hash', 'locked_review_policy_id', to_jsonb(t)->'locked_review_policy_id', 'locked_review_policy_generation', to_jsonb(t)->'locked_review_policy_generation', 'locked_review_policy_hash', to_jsonb(t)->'locked_review_policy_hash', 'locked_revision_policy_id', to_jsonb(t)->'locked_revision_policy_id', 'locked_revision_policy_generation', to_jsonb(t)->'locked_revision_policy_generation', 'locked_revision_policy_hash', to_jsonb(t)->'locked_revision_policy_hash', 'locked_contribution_policy_version_id', to_jsonb(t)->'locked_contribution_policy_version_id'))
             and (payload - array['references','manager_authority_facts','authorization_resource_digest']) = jsonb_build_object('locked_guide_version', payload->'locked_guide_version', 'locked_guide_source_snapshot_id', payload->'locked_guide_source_snapshot_id', 'locked_guide_source_snapshot_hash', payload->'locked_guide_source_snapshot_hash', 'locked_effective_project_submission_artifact_policy_id', payload->'locked_effective_project_submission_artifact_policy_id', 'locked_effective_project_submission_artifact_policy_hash', payload->'locked_effective_project_submission_artifact_policy_hash', 'locked_pre_submit_checker_policy_id', payload->'locked_pre_submit_checker_policy_id', 'locked_pre_submit_checker_bundle_hash', payload->'locked_pre_submit_checker_bundle_hash', 'locked_post_submit_checker_policy_id', payload->'locked_post_submit_checker_policy_id', 'locked_post_submit_checker_policy_version', payload->'locked_post_submit_checker_policy_version', 'locked_post_submit_checker_policy_hash', payload->'locked_post_submit_checker_policy_hash', 'locked_review_policy_id', payload->'locked_review_policy_id', 'locked_review_policy_generation', payload->'locked_review_policy_generation', 'locked_review_policy_hash', payload->'locked_review_policy_hash', 'locked_revision_policy_id', payload->'locked_revision_policy_id', 'locked_revision_policy_generation', payload->'locked_revision_policy_generation', 'locked_revision_policy_hash', payload->'locked_revision_policy_hash', 'locked_contribution_policy_version_id', payload->'locked_contribution_policy_version_id')
             and jsonb_typeof(payload->'locked_guide_version')='string' and btrim((payload->>'locked_guide_version'))<>''
             and (payload->>'locked_guide_source_snapshot_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and (payload->>'locked_guide_source_snapshot_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_effective_project_submission_artifact_policy_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and (payload->>'locked_effective_project_submission_artifact_policy_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_pre_submit_checker_policy_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and (payload->>'locked_pre_submit_checker_bundle_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_post_submit_checker_policy_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and jsonb_typeof(payload->'locked_post_submit_checker_policy_version')='string' and btrim((payload->>'locked_post_submit_checker_policy_version'))<>''
             and (payload->>'locked_post_submit_checker_policy_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_review_policy_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and jsonb_typeof(payload->'locked_review_policy_generation')='number' and (payload->>'locked_review_policy_generation') ~ '^[1-9][0-9]*$'
             and (payload->>'locked_review_policy_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_revision_policy_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and jsonb_typeof(payload->'locked_revision_policy_generation')='number' and (payload->>'locked_revision_policy_generation') ~ '^[1-9][0-9]*$'
             and (payload->>'locked_revision_policy_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_contribution_policy_version_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')), false) then
    raise exception 'task management audit mismatch' using errcode='23514';
  end if;
  return new;
end $$;
"""
