"""Bind automatic compilation requests to immutable source consent and current service authority."""

from alembic import op
import sqlalchemy as sa

revision = "0013_compilation_request_origin"
down_revision = "0012_contribution_policy_audit_resource"
branch_labels = None
depends_on = None


def _action_evidence(*, add: bool) -> None:
    connection = op.get_bind()
    connection.execute(sa.text("lock table audit_events in access exclusive mode"))
    name = "ck_audit_events_authorization_action_evidence"
    definition = connection.execute(sa.text(
        "select pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid='audit_events'::regclass and conname=:name"
    ), {"name": name}).scalar_one()
    anchor = "(((action_id)::text = 'project.guide_compilation.execute'::text) AND ((permission_id)::text = 'project.guide_compilation.execute'::text))"
    token = " OR (((action_id)::text = 'project.guide_compilation.request_automatic'::text) AND ((permission_id)::text = 'project.guide_compilation.execute'::text))"
    if definition.count(anchor) != 2 or definition.count(token) != (0 if add else 2):
        raise RuntimeError("compilation action constraint shape changed")
    definition = definition.replace(anchor, anchor + token) if add else definition.replace(token, "")
    op.execute("alter table audit_events drop constraint " + name)
    op.execute("alter table audit_events add constraint " + name + " " + definition)


def upgrade() -> None:
    """Extend one request table; retained human content and authority hashes stay exact."""
    table = "project_guide_compilation_request_operations"
    op.add_column(table, sa.Column("request_trigger", sa.String(32), nullable=False, server_default="project_manager"))
    op.alter_column(table, "request_trigger", server_default=None)
    op.add_column(table, sa.Column("source_mutation_operation_id", sa.Uuid(), nullable=True))
    op.add_column(table, sa.Column("source_authorization_decision_event_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_compilation_request_source_operation", table,
        "guide_mutation_idempotency_records", ["source_mutation_operation_id"], ["operation_id"])
    op.create_foreign_key("fk_compilation_request_source_event", table,
        "audit_events", ["source_authorization_decision_event_id"], ["id"])
    op.create_check_constraint("ck_compilation_request_origin", table,
        "(request_trigger='project_manager' and source_mutation_operation_id is null "
        "and source_authorization_decision_event_id is null) or "
        "(request_trigger='automatic_source_ready' and source_mutation_operation_id is not null "
        "and source_authorization_decision_event_id is not null)")
    _action_evidence(add=True)
    op.execute("""
create function require_automatic_compilation_origin(
  requested_project text, requested_guide text, requested_snapshot text,
  requested_setup text, requested_generation bigint, source_operation uuid, source_event text
) returns void language plpgsql as $$
declare
  guide project_guides%rowtype;
  snapshot guide_source_snapshots%rowtype;
  setup project_setup_runs%rowtype;
  mutation guide_mutation_idempotency_records%rowtype;
  event audit_events%rowtype;
begin
  select * into guide from project_guides where id=requested_guide for update;
  select * into snapshot from guide_source_snapshots where id=requested_snapshot for update;
  select * into setup from project_setup_runs where id=requested_setup for update;
  select * into mutation from guide_mutation_idempotency_records where operation_id=source_operation;
  select * into event from audit_events where id=source_event;
  if guide.id is null or snapshot.id is null or setup.id is null or mutation.id is null or event.id is null
     or guide.project_id is distinct from requested_project or guide.status is distinct from 'draft'
     or snapshot.project_id is distinct from requested_project or snapshot.guide_id is distinct from guide.id
     or snapshot.guide_version is distinct from guide.version
     or setup.project_id is distinct from requested_project or setup.guide_id is distinct from guide.id
     or setup.guide_version is distinct from guide.version
     or setup.source_snapshot_id is distinct from snapshot.id
     or setup.source_snapshot_hash is distinct from snapshot.bundle_hash
     or setup.setup_generation is distinct from requested_generation
     or exists(select 1 from guide_source_snapshots s where s.guide_id=guide.id
          and s.id<>snapshot.id and s.captured_at>=snapshot.captured_at)
     or exists(select 1 from project_setup_runs r where r.guide_id=guide.id
          and r.source_snapshot_id=snapshot.id and (r.created_at,r.id)>(setup.created_at,setup.id)) then
    raise exception 'automatic compilation origin lineage is invalid' using errcode='23514';
  end if;
  if mutation.action_id is distinct from 'project.guide_source_snapshot.create'
     or mutation.status is distinct from 'committed'
     or mutation.project_id is distinct from requested_project
     or mutation.resource_id is distinct from snapshot.id
     or mutation.setup_run_id is distinct from setup.id
     or mutation.operation_generation is distinct from snapshot.creation_generation
     or mutation.actor_profile_id is distinct from snapshot.created_by_actor_profile_id
     or mutation.identity_link_id is distinct from snapshot.created_via_identity_link_id
     or mutation.actor_profile_id is distinct from setup.authorized_by_actor_profile_id
     or mutation.identity_link_id is distinct from setup.authorized_via_identity_link_id
     or snapshot.authorization_decision_event_id is distinct from source_event
     or setup.authorization_decision_event_id is distinct from source_event
     or snapshot.creation_action_id is distinct from mutation.action_id
     or setup.authorization_action_id is distinct from mutation.action_id
     or snapshot.created_by_admin_role_grant_id is null
     or setup.authorized_by_admin_role_grant_id is distinct from snapshot.created_by_admin_role_grant_id
     or setup.authorization_scope_type is distinct from snapshot.creation_scope_type
     or setup.authorization_scope_project_id is distinct from snapshot.creation_scope_project_id then
    raise exception 'automatic compilation source operation is invalid' using errcode='23514';
  end if;
  if event.event_domain is distinct from 'authority'
     or event.event_type is distinct from 'SensitiveAuthorizationAllowed'
     or event.action_id is distinct from mutation.action_id
     or event.permission_id is distinct from 'project.guide.manage'
     or event.resource_type is distinct from 'project'
     or event.resource_id is distinct from requested_project
     or event.project_id is distinct from requested_project
     or event.actor_id is distinct from mutation.actor_profile_id
     or event.actor_ref_kind is distinct from 'actor_profile'
     or event.matched_grant_id is distinct from snapshot.created_by_admin_role_grant_id::text
     or event.after_facts->>'allowed' is distinct from 'true'
     or event.after_facts->>'resource_context_digest' is distinct from mutation.resource_context_digest then
    raise exception 'automatic compilation source authorization is invalid' using errcode='23514';
  end if;
end;
$$
""")
    op.execute("""
        create or replace function guard_project_guide_compilation_request_operation()
        returns trigger language plpgsql as $$
        declare
          attempt project_guide_compilation_attempts%rowtype;
          event audit_events%rowtype;
          grant_row admin_role_grants%rowtype;
        begin
          select * into attempt from project_guide_compilation_attempts
            where id=new.attempt_id;
          select * into event from audit_events
            where id=new.authorization_decision_event_id;
          select * into grant_row from admin_role_grants
            where id=event.matched_grant_id::uuid;
          if attempt.id is null or event.id is null then
            raise exception 'guide compilation request references are invalid'
              using errcode='23514';
          end if;
          if new.request_facts_digest is distinct from
                project_guide_compilation_request_facts_digest(new, attempt) then
            raise exception 'guide compilation request facts digest is invalid'
              using errcode='23514';
          end if;
          if new.request_trigger = 'automatic_source_ready' then
            perform require_automatic_compilation_origin(new.project_id, new.guide_id,
              new.source_snapshot_id, new.setup_run_id, new.setup_generation,
              new.source_mutation_operation_id, new.source_authorization_decision_event_id);
            if event.event_domain is distinct from 'authority'
               or event.event_type is distinct from 'SensitiveAuthorizationAllowed'
               or event.action_id is distinct from 'project.guide_compilation.request_automatic'
               or event.permission_id is distinct from 'project.guide_compilation.execute'
               or event.resource_type is distinct from 'project_guide_compilation_request'
               or event.resource_id is distinct from new.operation_id::text
               or event.project_id is distinct from new.project_id
               or event.actor_id is distinct from new.actor_profile_id
               or event.actor_ref_kind is distinct from 'actor_profile'
               or event.matched_grant_id is not null
               or event.after_facts->>'allowed' is distinct from 'true' then
              raise exception 'automatic compilation request audit event is invalid' using errcode='23514';
            end if;
            perform 1 from actor_identity_links l join actor_profiles a on a.id=l.actor_profile_id
              where l.id=new.identity_link_id and l.actor_profile_id=new.actor_profile_id
              and l.status='active' and l.subject_kind='service' and a.status='active'
              and a.actor_kind='service' and a.service_identity='workstream.project.setup'
              for update of l,a;
            if not found then
              raise exception 'automatic compilation service authority is invalid' using errcode='23514';
            end if;
            if event.after_facts->>'resource_context_digest' is distinct from
              ('sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(
                jsonb_build_object(
                  'action_id','project.guide_compilation.request_automatic',
                  'permission_id','project.guide_compilation.execute',
                  'resource_type','project_guide_compilation_request',
                  'resource_id',new.operation_id::text,'scope_project_id',new.project_id,
                  'actor_profile_id',new.actor_profile_id,'identity_link_id',new.identity_link_id,
                  'service_identity','workstream.project.setup',
                  'request_facts_digest',new.request_facts_digest,
                  'trigger',new.request_trigger,
                  'source_mutation_operation_id',new.source_mutation_operation_id::text,
                  'source_authorization_decision_event_id',new.source_authorization_decision_event_id
                )), 'UTF8')), 'hex')) then
              raise exception 'automatic compilation request authority digest is invalid' using errcode='23514';
            end if;
            return new;
          end if;
          if new.request_trigger is distinct from 'project_manager'
             or grant_row.id is null then
            raise exception 'guide compilation request trigger is invalid' using errcode='23514';
          end if;
          if event.event_domain is distinct from 'authority'
             or event.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or event.action_id is distinct from 'project.guide_compilation.request'
             or event.permission_id is distinct from 'project.guide_compilation.request'
             or event.resource_type is distinct from 'project_guide_compilation_request'
             or event.resource_id is distinct from new.operation_id::text
             or event.project_id is distinct from new.project_id
             or event.actor_id is distinct from new.actor_profile_id
             or event.actor_ref_kind is distinct from 'actor_profile'
             or event.after_facts->>'allowed' is distinct from 'true' then
            raise exception 'guide compilation request audit event is invalid'
              using errcode='23514';
          end if;
          if grant_row.target_actor_profile_id is distinct from new.actor_profile_id
             or grant_row.role is distinct from 'project_manager'
             or grant_row.status is distinct from 'active'
             or grant_row.scope_type is distinct from 'project'
             or grant_row.scope_project_id is distinct from new.project_id then
            raise exception 'guide compilation request grant is invalid'
              using errcode='23514';
          end if;
          if event.after_facts->>'resource_context_digest' is distinct from
                project_guide_compilation_request_authority_digest(new, grant_row) then
            raise exception 'guide compilation request authority digest is invalid'
              using errcode='23514';
          end if;
          return new;
        end;
        $$
""")


def downgrade() -> None:
    """Never discard retained origin or automatic authorization evidence."""
    connection = op.get_bind()
    if connection.execute(sa.text(
        "select exists(select 1 from project_guide_compilation_request_operations "
        "where request_trigger='automatic_source_ready') or exists(select 1 from audit_events "
        "where action_id='project.guide_compilation.request_automatic')"
    )).scalar_one():
        raise RuntimeError("automatic compilation evidence prevents downgrade")
    _action_evidence(add=False)
    op.execute("""
        create or replace function guard_project_guide_compilation_request_operation()
        returns trigger language plpgsql as $$
        declare
          attempt project_guide_compilation_attempts%rowtype;
          event audit_events%rowtype;
          grant_row admin_role_grants%rowtype;
        begin
          select * into attempt from project_guide_compilation_attempts
            where id=new.attempt_id;
          select * into event from audit_events
            where id=new.authorization_decision_event_id;
          select * into grant_row from admin_role_grants
            where id=event.matched_grant_id::uuid;
          if attempt.id is null or event.id is null or grant_row.id is null then
            raise exception 'guide compilation request references are invalid'
              using errcode='23514';
          end if;
          if new.request_facts_digest is distinct from
                project_guide_compilation_request_facts_digest(new, attempt) then
            raise exception 'guide compilation request facts digest is invalid'
              using errcode='23514';
          end if;
          if event.event_domain is distinct from 'authority'
             or event.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or event.action_id is distinct from 'project.guide_compilation.request'
             or event.permission_id is distinct from 'project.guide_compilation.request'
             or event.resource_type is distinct from 'project_guide_compilation_request'
             or event.resource_id is distinct from new.operation_id::text
             or event.project_id is distinct from new.project_id
             or event.actor_id is distinct from new.actor_profile_id
             or event.actor_ref_kind is distinct from 'actor_profile'
             or event.after_facts->>'allowed' is distinct from 'true' then
            raise exception 'guide compilation request audit event is invalid'
              using errcode='23514';
          end if;
          if grant_row.target_actor_profile_id is distinct from new.actor_profile_id
             or grant_row.role is distinct from 'project_manager'
             or grant_row.status is distinct from 'active'
             or grant_row.scope_type is distinct from 'project'
             or grant_row.scope_project_id is distinct from new.project_id then
            raise exception 'guide compilation request grant is invalid'
              using errcode='23514';
          end if;
          if event.after_facts->>'resource_context_digest' is distinct from
                project_guide_compilation_request_authority_digest(new, grant_row) then
            raise exception 'guide compilation request authority digest is invalid'
              using errcode='23514';
          end if;
          return new;
        end;
        $$
""")
    op.execute("drop function require_automatic_compilation_origin")
    table = "project_guide_compilation_request_operations"
    op.drop_constraint("ck_compilation_request_origin", table, type_="check")
    op.drop_constraint("fk_compilation_request_source_event", table, type_="foreignkey")
    op.drop_constraint("fk_compilation_request_source_operation", table, type_="foreignkey")
    for column in ("source_authorization_decision_event_id", "source_mutation_operation_id", "request_trigger"):
        op.drop_column(table, column)
