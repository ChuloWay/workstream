"""Install immutable aggregate custody for complete native batch transitions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0038_task_batch_transitions"
down_revision = "0037_task_import_batches"
branch_labels = None
depends_on = None


_TABLES = ("task_batch_transition_receipts", "task_batch_transition_members")


def _replace_function(signature: str, old: str, new: str) -> None:
    body = (
        op.get_bind()
        .execute(
            sa.text("select pg_catalog.pg_get_functiondef(cast(:signature as regprocedure))"),
            {"signature": signature},
        )
        .scalar_one()
    )
    if body.count(old) != 1:
        raise RuntimeError(f"bulk transition predecessor function shape changed: {signature}")
    op.execute(body.replace(old, new))


def _create_tables() -> None:
    op.create_table(
        "task_batch_transition_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_profile_id", sa.Uuid(), nullable=False),
        sa.Column("identity_link_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.String(160), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_digest", sa.String(71), nullable=False),
        sa.Column("membership_digest", sa.String(71), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("response", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["actor_profile_id"],
            ["public.actor_profiles.id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["public.actor_identity_links.id", "public.actor_identity_links.actor_profile_id"],
            name="fk_task_batch_transition_actor_link",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "project_id"],
            ["public.task_import_batches.id", "public.task_import_batches.project_id"],
            name="fk_task_batch_transition_batch",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "actor_profile_id",
            "action_id",
            "idempotency_key",
            name="uq_task_batch_transition_namespace",
        ),
        sa.UniqueConstraint("id", "project_id", "batch_id", name="uq_task_batch_transition_parent"),
        sa.CheckConstraint(
            "(get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128",
            name="ck_task_batch_transition_receipts_id_uuid7",
        ),
        sa.CheckConstraint(
            "action_id in ('project.task.screen','project.task.release')",
            name="ck_task_batch_transition_receipts_action",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and manifest_digest ~ '^sha256:[0-9a-f]{64}$' and membership_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_task_batch_transition_receipts_digests",
        ),
        sa.CheckConstraint(
            "row_count between 1 and 500", name="ck_task_batch_transition_receipts_bounds"
        ),
        sa.CheckConstraint(
            "reason is null or length(reason)<=1000",
            name="ck_task_batch_transition_receipts_reason_bounds",
        ),
        sa.CheckConstraint(
            "action_id<>'project.task.release' or (reason is not null and length(btrim(reason))>0)",
            name="ck_task_batch_transition_receipts_release_reason",
        ),
        sa.CheckConstraint(
            "(status='pending' and response is null and committed_at is null) or (status='committed' and response is not null and jsonb_typeof(response)='object' and committed_at is not null)",
            name="ck_task_batch_transition_receipts_state_shape",
        ),
        schema="public",
    )
    op.create_table(
        "task_batch_transition_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transition_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("native_member_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("task_idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("task_command_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_decision_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["transition_receipt_id", "project_id", "batch_id"],
            [
                "public.task_batch_transition_receipts.id",
                "public.task_batch_transition_receipts.project_id",
                "public.task_batch_transition_receipts.batch_id",
            ],
            name="fk_task_batch_transition_member_parent",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["native_member_id"],
            ["public.task_import_batch_members.id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "project_id"],
            ["public.workstream_tasks.id", "public.workstream_tasks.project_id"],
            name="fk_task_batch_transition_member_task",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["task_command_receipt_id"],
            ["public.task_command_receipts.id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["authorization_decision_id"],
            ["public.audit_events.id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "transition_receipt_id", "row_index", name="uq_task_batch_transition_member_row"
        ),
        sa.UniqueConstraint(
            "transition_receipt_id",
            "native_member_id",
            name="uq_task_batch_transition_member_native",
        ),
        sa.UniqueConstraint(
            "transition_receipt_id", "task_id", name="uq_task_batch_transition_member_task"
        ),
        sa.UniqueConstraint(
            "task_command_receipt_id", name="uq_task_batch_transition_member_command"
        ),
        sa.CheckConstraint(
            "(get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128",
            name="ck_task_batch_transition_members_id_uuid7",
        ),
        sa.CheckConstraint(
            "row_index between 0 and 499", name="ck_task_batch_transition_members_row_index"
        ),
        schema="public",
    )


def _alter_command_receipts() -> None:
    op.add_column(
        "task_command_receipts",
        sa.Column("batch_transition_receipt_id", sa.Uuid(), nullable=True),
        schema="public",
    )
    op.create_foreign_key(
        "fk_task_command_batch_transition",
        "task_command_receipts",
        "task_batch_transition_receipts",
        ["batch_transition_receipt_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_check_constraint(
        "ck_task_command_receipts_task_command_batch_transition_action",
        "task_command_receipts",
        "batch_transition_receipt_id is null or action_id in ('project.task.screen','project.task.release')",
        schema="public",
    )
    op.create_index(
        "ix_task_command_receipts_batch_transition_receipt_id",
        "task_command_receipts",
        ["batch_transition_receipt_id"],
        schema="public",
    )
    _replace_function(
        "public.protect_task_command_receipt()",
        "NEW.request_digest, NEW.task_id, NEW.created_at)",
        "NEW.request_digest, NEW.batch_transition_receipt_id, NEW.task_id, NEW.created_at)",
    )
    _replace_function(
        "public.protect_task_command_receipt()",
        "OLD.request_digest, OLD.task_id, OLD.created_at)",
        "OLD.request_digest, OLD.batch_transition_receipt_id, OLD.task_id, OLD.created_at)",
    )


def _create_custody() -> None:
    op.execute(r"""
create function public.validate_task_batch_transition_custody(p_receipt_id uuid) returns boolean
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare b public.task_batch_transition_receipts%rowtype; expected_membership text;
  expected_request text; expected_response jsonb; expected_event text;
begin
 select * into b from public.task_batch_transition_receipts where id=p_receipt_id;
 if not found then return false; end if;
 if b.status<>'committed' or b.response is null or b.committed_at is null then return false; end if;
 if not exists(select 1 from public.task_import_batches source where source.id=b.batch_id
      and source.project_id=b.project_id and source.status='committed'
      and source.manifest_digest=b.manifest_digest and source.row_count=b.row_count) then return false; end if;

 select public.external_checker_registry_digest(jsonb_build_object('members',coalesce(jsonb_agg(
   jsonb_build_object('member_id',n.id::text,'task_id',n.task_id::text,'row_index',n.row_index,
     'external_task_id',n.external_task_id,'row_digest',n.row_digest,
     'create_idempotency_key',n.create_idempotency_key::text,
     'task_command_receipt_id',n.task_command_receipt_id::text,
     'authorization_decision_id',n.authorization_decision_id::text)
   order by n.row_index),'[]'::jsonb))) into expected_membership
 from public.task_import_batch_members n where n.batch_id=b.batch_id;
 expected_request := public.external_checker_registry_digest(jsonb_build_object(
   'project_id',b.project_id::text,'batch_id',b.batch_id::text,
   'operation',b.action_id,'reason',to_jsonb(b.reason)));
 if b.membership_digest<>expected_membership or b.request_digest<>expected_request then return false; end if;

 if (select count(*) from public.task_import_batch_members where batch_id=b.batch_id)<>b.row_count
    or (select count(*) from public.task_batch_transition_members where transition_receipt_id=b.id)<>b.row_count
    or (select count(*) from public.task_command_receipts
        where batch_transition_receipt_id=b.id)<>b.row_count
    or exists(select 1 from public.task_import_batch_members n
       left join public.task_batch_transition_members m
         on m.transition_receipt_id=b.id and m.native_member_id=n.id
       where n.batch_id=b.batch_id and (m.id is null or m.project_id<>n.project_id
         or m.batch_id<>n.batch_id or m.task_id<>n.task_id or m.row_index<>n.row_index))
    or exists(select 1 from public.task_batch_transition_members m
       left join public.task_import_batch_members n on n.id=m.native_member_id
       where m.transition_receipt_id=b.id and (n.id is null or n.batch_id<>b.batch_id)) then return false; end if;
 if exists(select 1 from public.task_command_receipts c
      left join public.task_batch_transition_members m
        on m.transition_receipt_id=b.id and m.task_command_receipt_id=c.id
      where c.batch_transition_receipt_id=b.id and m.id is null) then return false; end if;

 expected_event := case b.action_id when 'project.task.screen' then 'TaskScreened' else 'TaskReleased' end;
 if exists(select 1 from public.task_batch_transition_members m
   join public.task_import_batch_members n on n.id=m.native_member_id
   left join public.task_command_receipts c on c.id=m.task_command_receipt_id
   left join public.audit_events d on d.id=m.authorization_decision_id
   where m.transition_receipt_id=b.id and (
     m.project_id<>b.project_id or m.batch_id<>b.batch_id or m.task_id<>n.task_id
     or m.row_index<>n.row_index or m.task_idempotency_key<>c.idempotency_key
     or c.id is null or c.batch_transition_receipt_id is distinct from b.id or c.task_id<>m.task_id
     or c.actor_profile_id::text<>b.actor_profile_id::text or c.action_id<>b.action_id
     or c.status<>'committed' or c.response is null or c.locked_context_hash is null
     or c.request_digest<>public.external_checker_registry_digest(jsonb_build_object(
       'task_id',m.task_id::text,'reason',to_jsonb(b.reason),
       'batch_transition_receipt_id',b.id::text))
     or c.response::jsonb->>'id' is distinct from m.task_id::text
     or c.response::jsonb->>'project_id' is distinct from b.project_id::text
     or c.response::jsonb->>'status' is distinct from case b.action_id
       when 'project.task.screen' then 'screening' else 'ready' end
     or nullif(c.response::jsonb->>'locked_guide_version','') is null
     or not coalesce((c.response::jsonb->>'locked_contribution_policy_version_id')
       ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',false)
     or d.id is null or d.event_domain is distinct from 'authority'
     or d.event_type is distinct from 'SensitiveAuthorizationAllowed'
     or d.action_id is distinct from b.action_id
     or d.permission_id is distinct from 'project.task.manage'
     or d.actor_id is distinct from b.actor_profile_id::text
     or d.project_id is distinct from b.project_id
     or d.resource_type is distinct from 'project'
     or d.resource_id is distinct from b.project_id::text or d.denial_code is not null
     or d.after_facts::jsonb is distinct from jsonb_build_object('allowed',true,'resource_context_digest',d.after_facts::jsonb->'resource_context_digest')
     or not coalesce((d.after_facts::jsonb->>'resource_context_digest')
       ~ '^sha256:[0-9a-f]{64}$',false)
     or not exists(select 1 from public.audit_events e where e.entity_id=m.task_id
       and e.event_type=expected_event and e.actor_id=b.actor_profile_id::text
       and e.event_payload::jsonb#>>'{references,project_id}'=b.project_id::text
       and e.event_payload::jsonb#>>'{references,task_id}'=m.task_id::text
       and e.event_payload::jsonb#>>'{references,authorization_decision_id}'=m.authorization_decision_id::text
       and e.event_payload::jsonb#>>'{manager_authority_facts,resource_id}'=m.task_id::text
       and e.event_payload::jsonb#>>'{manager_authority_facts,scope_project_id}'=b.project_id::text
       and e.event_payload::jsonb#>>'{manager_authority_facts,idempotency_key}'=c.idempotency_key::text
       and e.event_payload::jsonb#>>'{manager_authority_facts,request_digest}'=c.request_digest
       and e.event_payload::jsonb#>>'{manager_authority_facts,identity_link_id}'=b.identity_link_id::text
       and e.event_payload::jsonb#>>'{manager_authority_facts,task_status}'=
         case b.action_id when 'project.task.screen' then 'draft' else 'screening' end
       and coalesce((e.event_payload::jsonb#>>'{manager_authority_facts,locked_context_hash}')
         ~ '^sha256:[0-9a-f]{64}$',false)
       and (b.action_id='project.task.screen' or
         e.event_payload::jsonb#>>'{manager_authority_facts,locked_context_hash}'=c.locked_context_hash)
       and public.external_checker_registry_digest(jsonb_build_object(
         'resource_context',jsonb_strip_nulls(
           e.event_payload::jsonb->'manager_authority_facts')))
         =d.after_facts::jsonb->>'resource_context_digest'
       and e.event_payload::jsonb->>'authorization_resource_digest'
         =d.after_facts::jsonb->>'resource_context_digest'
       and e.event_payload::jsonb->>'locked_guide_version'=c.response::jsonb->>'locked_guide_version'
       and e.event_payload::jsonb->>'locked_contribution_policy_version_id'
         =c.response::jsonb->>'locked_contribution_policy_version_id')
   )) then return false; end if;

 select jsonb_build_object('project_id',b.project_id::text,'batch_id',b.batch_id::text,
   'operation',case b.action_id when 'project.task.screen' then 'screen' else 'release' end,
   'row_count',b.row_count,'tasks',coalesce(jsonb_agg(jsonb_build_object(
     'task_id',m.task_id::text,'row_index',m.row_index,'status',c.response::jsonb->>'status',
     'locked_guide_version',c.response::jsonb->>'locked_guide_version',
     'locked_contribution_policy_version_id',c.response::jsonb->>'locked_contribution_policy_version_id',
     'locked_context_hash',c.locked_context_hash) order by m.row_index),'[]'::jsonb))
 into expected_response
 from public.task_batch_transition_members m
 join public.task_command_receipts c on c.id=m.task_command_receipt_id
 where m.transition_receipt_id=b.id;
 return b.response=expected_response;
exception when others then return false;
end $$
""")
    op.execute(r"""
create function public.trigger_validate_task_batch_transition() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare final_status text;
begin
 select status into final_status from public.task_batch_transition_receipts where id=new.id;
 if not found or final_status<>'committed' then
   raise exception 'task batch transition cannot remain pending' using errcode='23514';
 end if;
 if new.status='committed'
    and not public.validate_task_batch_transition_custody(new.id) then
   raise exception 'task batch transition custody mismatch' using errcode='23514';
 end if; return new; end $$
""")
    op.execute(r"""
create function public.trigger_validate_task_batch_transition_member() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare parent_status text; parent_xid xid;
begin
 select status,xmin into parent_status,parent_xid
 from public.task_batch_transition_receipts where id=new.transition_receipt_id;
 if not found or parent_status<>'committed'
    or parent_xid<>pg_catalog.pg_current_xact_id()::xid then
   raise exception 'task batch transition member must be committed with its root' using errcode='23514';
 end if;
 return new;
end $$
""")
    op.execute(r"""
create function public.trigger_validate_task_batch_command_root() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare parent_status text; parent_xid xid;
begin
 if new.batch_transition_receipt_id is null then return new; end if;
 select status,xmin into parent_status,parent_xid
 from public.task_batch_transition_receipts where id=new.batch_transition_receipt_id;
 if not found or parent_status<>'committed'
    or parent_xid<>pg_catalog.pg_current_xact_id()::xid then
   raise exception 'task batch transition command must be committed with its root' using errcode='23514';
 end if;
 return new;
end $$
""")
    op.execute(
        "create constraint trigger task_batch_transition_custody after insert or update on public.task_batch_transition_receipts deferrable initially deferred for each row execute function public.trigger_validate_task_batch_transition()"
    )
    op.execute(
        "create constraint trigger task_batch_transition_member_custody after insert or update on public.task_batch_transition_members deferrable initially deferred for each row execute function public.trigger_validate_task_batch_transition_member()"
    )
    op.execute(
        "create constraint trigger task_batch_transition_command_custody after insert or update of batch_transition_receipt_id,status,response,locked_context_hash on public.task_command_receipts deferrable initially deferred for each row execute function public.trigger_validate_task_batch_command_root()"
    )


def _create_guards() -> None:
    op.execute(r"""
create function public.guard_task_batch_transition_receipt() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$ begin
 if tg_op='TRUNCATE' then raise exception 'task batch transition receipts cannot be truncated' using errcode='55000'; end if;
 if tg_op='DELETE' then raise exception 'task batch transition receipts are immutable' using errcode='55000'; end if;
 if new is not distinct from old then return new; end if;
 if old.status<>'pending' or new.status<>'committed'
   or row(new.id,new.actor_profile_id,new.identity_link_id,new.action_id,new.idempotency_key,
          new.request_digest,new.reason,new.project_id,new.batch_id,new.manifest_digest,
          new.membership_digest,new.row_count,new.created_at)
      is distinct from
      row(old.id,old.actor_profile_id,old.identity_link_id,old.action_id,old.idempotency_key,
          old.request_digest,old.reason,old.project_id,old.batch_id,old.manifest_digest,
          old.membership_digest,old.row_count,old.created_at)
   or old.response is not null or old.committed_at is not null
   or new.response is null or new.committed_at is null then
   raise exception 'task batch transition receipt is immutable' using errcode='23514';
 end if; return new; end $$
""")
    op.execute(r"""
create function public.reject_task_batch_transition_member_mutation() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$ begin
 raise exception 'task batch transition members are immutable' using errcode='55000'; end $$
""")
    op.execute(
        "create trigger task_batch_transition_receipt_immutable before update or delete on public.task_batch_transition_receipts for each row execute function public.guard_task_batch_transition_receipt()"
    )
    op.execute(
        "create trigger task_batch_transition_receipt_no_truncate before truncate on public.task_batch_transition_receipts for each statement execute function public.guard_task_batch_transition_receipt()"
    )
    op.execute(
        "create trigger task_batch_transition_member_immutable before update or delete on public.task_batch_transition_members for each row execute function public.reject_task_batch_transition_member_mutation()"
    )
    op.execute(
        "create trigger task_batch_transition_member_no_truncate before truncate on public.task_batch_transition_members for each statement execute function public.reject_task_batch_transition_member_mutation()"
    )


def upgrade() -> None:
    """Install exact aggregate-to-member-to-command transition custody."""
    op.execute("set local search_path=pg_catalog,public,pg_temp")
    op.execute(
        "lock table public.task_command_receipts, public.task_import_batches, "
        "public.task_import_batch_members, public.audit_events in access exclusive mode"
    )
    _create_tables()
    _alter_command_receipts()
    _create_custody()
    _create_guards()


def downgrade() -> None:
    """Refuse removal of retained aggregate transition custody."""
    op.execute("set local search_path=pg_catalog,public,pg_temp")
    op.execute(
        "lock table public.task_batch_transition_receipts, public.task_batch_transition_members, "
        "public.task_command_receipts in access exclusive mode"
    )
    retained = (
        op.get_bind()
        .execute(
            sa.text(
                "select exists(select 1 from public.task_batch_transition_receipts) or "
                "exists(select 1 from public.task_batch_transition_members) or "
                "exists(select 1 from public.task_command_receipts where batch_transition_receipt_id is not null)"
            )
        )
        .scalar_one()
    )
    if retained:
        raise RuntimeError("cannot downgrade batch transitions with retained custody")
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
