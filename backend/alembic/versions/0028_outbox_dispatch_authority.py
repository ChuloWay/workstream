"""Bind each outbox phase to real fixed-dispatcher authority without backfill."""

from alembic import op
import sqlalchemy as sa

revision = "0028_outbox_dispatch_authority"
down_revision = "0027_outbox_delivery_custody"
branch_labels = None
depends_on = None


def _audit_vocabulary():
    """Extend only the exact resource and action pair in existing closed guards."""
    connection = op.get_bind()
    connection.execute(sa.text("lock table audit_events in access exclusive mode"))
    for name, anchor, addition, expected in (
        (
            "ck_audit_events_authority_registries",
            "('actor.profile.read_self'::character varying)::text",
            ", ('outbox.dispatch'::character varying)::text",
            1,
        ),
        (
            "ck_audit_events_authority_privacy_bounds",
            "('contribution_policy'::character varying)::text",
            ", ('outbox_event'::character varying)::text",
            1,
        ),
        (
            "ck_audit_events_authorization_action_evidence",
            "(((action_id)::text = 'actor.profile.read_self'::text) AND ((permission_id)::text = 'actor.profile.read_self'::text))",
            " OR (((action_id)::text = 'outbox.dispatch'::text) AND ((permission_id)::text = 'outbox.dispatch'::text))",
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
        if definition.count(anchor) != expected or addition in definition:
            raise RuntimeError("outbox audit constraint shape changed")
        op.execute("alter table audit_events drop constraint " + name)
        op.execute(
            "alter table audit_events add constraint "
            + name
            + " "
            + definition.replace(anchor, anchor + addition)
        )


def _protect_service_identity():
    """Keep the fixed principal immutable in the existing actor history guard."""
    definition = op.get_bind().execute(sa.text(
        "select pg_get_functiondef('guard_actor_profile_history()'::regprocedure)"
    )).scalar_one()
    for row in ("new", "old"):
        anchor = f"{row}.provisioning_method,{row}.created_by"
        if definition.count(anchor) != 1:
            raise RuntimeError("actor profile history guard shape changed")
        definition = definition.replace(anchor, f"{row}.provisioning_method,{row}.service_identity,{row}.created_by")
    op.execute(definition)


def upgrade():
    """Refuse unprovable attempts before changing schema or retained data."""
    op.execute("lock table actor_profiles, outbox_events, outbox_delivery_attempts in access exclusive mode")
    op.execute("""
        do $$ begin
          if exists(select 1 from outbox_delivery_attempts)
             or exists(select 1 from outbox_events where claim_generation <> 0) then
            raise exception 'outbox attempts without phase authority prevent activation';
          end if;
        end $$;
    """)
    _protect_service_identity()
    _audit_vocabulary()
    for phase in ("claim", "invoke", "finalize"):
        column = phase + "_decision_event_id"
        op.add_column(
            "outbox_delivery_attempts", sa.Column(column, sa.String(36), nullable=phase != "claim")
        )
        op.create_foreign_key(None, "outbox_delivery_attempts", "audit_events", [column], ["id"])
        op.create_unique_constraint(None, "outbox_delivery_attempts", [column])
    op.create_check_constraint(
        "phase_decisions",
        "outbox_delivery_attempts",
        "(stage = 'claimed' and invoke_decision_event_id is null and finalize_decision_event_id is null) or "
        "(stage = 'invoked' and invoke_decision_event_id is not null and finalize_decision_event_id is null) or "
        "(stage = 'completed' and finalize_decision_event_id is not null and "
        "((invoked_at is null and invoke_decision_event_id is null) or "
        "(invoked_at is not null and invoke_decision_event_id is not null)))",
    )
    op.execute("""
        create function outbox_dispatch_utc(value timestamptz) returns text
        language sql immutable strict as $$
          select to_char(value at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') ||
            case when value = date_trunc('second', value) then ''
              else to_char(value at time zone 'UTC', '.US') end || '+00:00'
        $$;
    """)
    op.execute("""
        create function outbox_dispatch_authority_digest(a outbox_delivery_attempts, phase text)
        returns text language sql immutable strict as $$
          select 'sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(
            jsonb_build_object(
              'domain','workstream.authorization.outbox_dispatch',
              'action_id','outbox.dispatch','permission_id','outbox.dispatch',
              'service_identity','workstream.outbox.dispatcher',
              'resource_type','outbox_event','resource_id',a.event_id::text,
              'scope_project_id',a.project_id,
              'facts',jsonb_build_object(
                'phase',phase,'event_id',a.event_id::text,'project_id',a.project_id,
                'payload_digest',a.payload_digest,'claim_generation',a.claim_generation,
                'claim_owner',a.claim_owner,'claimed_at',outbox_dispatch_utc(a.claimed_at),
                'claim_expires_at',outbox_dispatch_utc(a.claim_expires_at),
                'outcome_digest',case when phase='finalize' then a.outcome_digest else null end
              )
            )), 'UTF8')), 'hex')
        $$;
    """)
    op.execute("""
        create function require_outbox_phase_authority() returns trigger language plpgsql as $$
        declare phase text; decision_id text; previous_id text; e audit_events%rowtype;
                actor actor_profiles%rowtype; link actor_identity_links%rowtype;
        begin
          foreach phase in array array['claim','invoke','finalize'] loop
            decision_id := to_jsonb(new)->>(phase || '_decision_event_id');
            previous_id := case when tg_op='UPDATE' then to_jsonb(old)->>(phase || '_decision_event_id') else null end;
            if previous_id is not null and decision_id is distinct from previous_id then
              raise exception 'outbox phase authority is immutable' using errcode='55000';
            end if;
            if decision_id is null then continue; end if;
            select * into e from audit_events where id=decision_id;
            if e.id is null or e.event_domain is distinct from 'authority'
               or e.event_type is distinct from 'SensitiveAuthorizationAllowed'
               or e.entity_type is distinct from 'authorization_decision'
               or e.entity_id is distinct from e.id or e.actor_ref_kind is distinct from 'actor_profile'
               or e.denial_code is not null or e.matched_grant_id is not null
               or e.action_id is distinct from 'outbox.dispatch'
               or e.permission_id is distinct from 'outbox.dispatch'
               or e.project_id is distinct from new.project_id
               or e.resource_type is distinct from 'outbox_event'
               or e.resource_id is distinct from new.event_id::text
               or e.target_ref_kind is distinct from 'project'
               or e.target_ref_id is distinct from new.project_id
               or e.after_facts->>'allowed' is distinct from 'true'
               or e.after_facts->>'resource_context_digest' is distinct from outbox_dispatch_authority_digest(new,phase) then
              raise exception 'outbox phase authority evidence mismatch' using errcode='23514';
            end if;
            -- Normal writes hold AUTH locks before event/attempt. Never reverse that
            -- order in this guard. The stable one-to-one link identifies the principal.
            select * into actor from actor_profiles where id=e.actor_id;
            select * into link from actor_identity_links where actor_profile_id=e.actor_id;
            if actor.id is null or actor.actor_kind is distinct from 'service'
               or actor.service_identity is distinct from 'workstream.outbox.dispatcher'
               or link.id is null or link.subject_kind is distinct from 'service' then
              raise exception 'outbox phase authority identity mismatch' using errcode='23514';
            end if;
            if previous_id is null and (actor.status is distinct from 'active' or link.status is distinct from 'active') then
              raise exception 'outbox current dispatcher authority missing' using errcode='23514';
            end if;
          end loop;
          return new;
        end $$;
    """)
    op.execute("""
        create trigger outbox_delivery_authority_guard before insert or update
          on outbox_delivery_attempts for each row execute function require_outbox_phase_authority();
    """)


def downgrade():
    """Never erase retained phase authority or restore unaudited delivery."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
