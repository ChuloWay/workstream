"""Retain exact hidden delivery custody without fabricating historical attempts."""

from alembic import op
import sqlalchemy as sa

revision = "0027_outbox_delivery_custody"
down_revision = "0026_outbox_dispatch_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add immutable attempts and bidirectional deferred projection checks."""
    op.execute("""
        do $$ begin
          if exists (select 1 from outbox_events where claim_generation <> 0) then
            raise exception 'outbox attempts require provable delivery custody';
          end if;
        end $$;
    """)
    # Attempted cancellation has no outcome in the closed delivery contract.
    # Preserve generation-zero cancellation without retaining that obsolete branch.
    op.drop_constraint(op.f("ck_outbox_events_delivery_state_shape"), "outbox_events")
    op.create_check_constraint(
        op.f("ck_outbox_events_delivery_state_shape"),
        "outbox_events",
        "(delivery_state = 'pending' and attempt_count = 0 and next_attempt_at is not null and "
        "claim_owner is null and claimed_at is null and claim_expires_at is null and "
        "last_attempt_at is null and last_error_code is null and finalized_at is null and "
        "archived_at is null) or (delivery_state = 'claimed' and attempt_count > 0 and "
        "next_attempt_at is null and claim_owner is not null and claimed_at is not null and "
        "claim_expires_at is not null and last_attempt_at = claimed_at and finalized_at is null and "
        "archived_at is null) or (delivery_state = 'retryable' and attempt_count > 0 and "
        "next_attempt_at is not null and claim_owner is null and claimed_at is null and "
        "claim_expires_at is null and last_attempt_at is not null and last_error_code is not null "
        "and finalized_at is null and archived_at is null) or (delivery_state = 'acknowledged' and "
        "attempt_count > 0 and next_attempt_at is null and claim_owner is null and claimed_at is "
        "null and claim_expires_at is null and last_attempt_at is not null and finalized_at is not "
        "null) or (delivery_state = 'dead_letter' and attempt_count > 0 and next_attempt_at is null "
        "and claim_owner is null and claimed_at is null and claim_expires_at is null and "
        "last_attempt_at is not null and last_error_code is not null and finalized_at is not null) "
        "or (delivery_state = 'cancelled' and next_attempt_at is null and claim_owner is null and "
        "claimed_at is null and claim_expires_at is null and finalized_at is not null and "
        "attempt_count = 0 and last_attempt_at is null and last_error_code is null) ",
    )
    # Reuse the existing pure canonical JSON serializer; it does not read PROJECTS data.
    op.execute("""
        create function outbox_delivery_outcome_valid(
          body text, digest text, claimed timestamptz, expires timestamptz, invoked timestamptz
        ) returns boolean immutable language plpgsql as $$
        declare value jsonb; completed timestamptz; final_time timestamptz;
                retry_time timestamptz; outcome_state text; code text; unknown boolean;
        begin
          value := body::jsonb;
          if jsonb_typeof(value) <> 'object' or
             (select array_agg(k order by k) from jsonb_object_keys(value) k) <>
             array['delivery_state','error_code','finalized_at','invocation_unknown',
                   'invoked_at','next_attempt_at','receipt_completed_at'] or
             body <> project_guide_projection_canonical_json(value) or
             digest <> 'sha256:' || encode(sha256(convert_to(body, 'UTF8')), 'hex') or
             jsonb_typeof(value->'delivery_state') <> 'string' or
             jsonb_typeof(value->'invocation_unknown') <> 'boolean' or
             jsonb_typeof(value->'receipt_completed_at') <> 'string' then return false; end if;
          if (value->>'receipt_completed_at') is null or
             jsonb_typeof(value->'error_code') not in ('null','string') or
             jsonb_typeof(value->'finalized_at') not in ('null','string') or
             jsonb_typeof(value->'next_attempt_at') not in ('null','string') or
             jsonb_typeof(value->'invoked_at') not in ('null','string') then return false; end if;
          completed := (value->>'receipt_completed_at')::timestamptz;
          final_time := (value->>'finalized_at')::timestamptz;
          retry_time := (value->>'next_attempt_at')::timestamptz;
          outcome_state := value->>'delivery_state'; code := value->>'error_code';
          unknown := (value->>'invocation_unknown')::boolean;
          if completed < claimed or (invoked is not null and completed < invoked)
             or (value->>'invoked_at')::timestamptz is distinct from invoked then return false; end if;
          if invoked is null and (completed < expires or code not in
             ('LEASE_EXPIRED_BEFORE_INVOKE','ATTEMPTS_EXHAUSTED')) then return false; end if;
          if invoked is not null and not unknown and completed >= expires then return false; end if;
          if retry_time > completed + interval '1 day' then return false; end if;
          if unknown then
            return invoked is not null and outcome_state = 'dead_letter'
              and code = 'INVOKE_OUTCOME_UNKNOWN' and retry_time is null and final_time = completed;
          elsif outcome_state = 'acknowledged' then
            return invoked is not null and code is null and retry_time is null
              and final_time = completed;
          elsif outcome_state = 'retryable' then
            return final_time is null and retry_time > completed and
              ((invoked is null and code = 'LEASE_EXPIRED_BEFORE_INVOKE') or
               (invoked is not null and code = 'RETRY_REQUESTED'));
          elsif outcome_state = 'dead_letter' then
            return retry_time is null and final_time = completed and
              (code = 'ATTEMPTS_EXHAUSTED' or (invoked is not null and code = 'HANDLER_REJECTED'));
          end if;
          return false;
        exception when others then return false;
        end $$;
    """)
    op.create_table(
        "outbox_delivery_attempts",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("outbox_events.event_id"), primary_key=True),
        sa.Column("claim_generation", sa.BigInteger(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("payload_digest", sa.String(71), nullable=False),
        sa.Column("claim_owner", sa.String(120), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("invoked_at", sa.DateTime(timezone=True)),
        sa.Column("outcome_json", sa.String(2048)),
        sa.Column("outcome_digest", sa.String(71)),
        sa.CheckConstraint("claim_generation between 1 and 2147483647", name="generation"),
        sa.CheckConstraint("claim_owner ~ '^[A-Za-z0-9._:-]{1,120}$'", name="owner"),
        sa.CheckConstraint("payload_digest ~ '^sha256:[0-9a-f]{64}$'", name="payload_digest"),
        sa.CheckConstraint(
            "claim_expires_at > claimed_at and claim_expires_at <= claimed_at + interval '1 hour'",
            name="lease",
        ),
        sa.CheckConstraint(
            "(stage = 'claimed' and invoked_at is null and outcome_json is null "
            "and outcome_digest is null) or "
            "(stage = 'invoked' and invoked_at is not null and invoked_at >= claimed_at and invoked_at < claim_expires_at "
            "and outcome_json is null and outcome_digest is null) or "
            "(stage = 'completed' and outcome_json is not null and outcome_digest is not null "
            "and (invoked_at is null or (invoked_at >= claimed_at and invoked_at < claim_expires_at)))",
            name="stage_shape",
        ),
        sa.CheckConstraint(
            "outcome_json is null or coalesce(outbox_delivery_outcome_valid("
            "outcome_json, outcome_digest, claimed_at, claim_expires_at, invoked_at), false)",
            name="outcome",
        ),
    )
    op.execute("""
        create function guard_outbox_delivery_attempt() returns trigger language plpgsql as $$
        begin
          if tg_op in ('DELETE','TRUNCATE') then
            raise exception 'outbox delivery custody cannot be removed' using errcode='55000';
          elsif tg_op = 'INSERT' then
            if new.stage <> 'claimed' or new.claimed_at > clock_timestamp()
               or new.claim_expires_at <= clock_timestamp() then
              raise exception 'outbox delivery must begin claimed' using errcode='23514';
            end if;
          else
            if (new.event_id,new.claim_generation,new.project_id,new.payload_digest,new.claim_owner,
                new.claimed_at,new.claim_expires_at) is distinct from
               (old.event_id,old.claim_generation,old.project_id,old.payload_digest,old.claim_owner,
                old.claimed_at,old.claim_expires_at) or old.stage = 'completed' then
              raise exception 'outbox delivery custody is immutable' using errcode='55000';
            end if;
            if not ((old.stage = 'claimed' and new.stage in ('invoked','completed')) or
                    (old.stage = 'invoked' and new.stage = 'completed')) or
               (old.stage = 'claimed' and new.stage = 'completed' and new.invoked_at is not null) or
               (old.stage = 'invoked' and new.invoked_at is distinct from old.invoked_at) then
              raise exception 'illegal outbox custody transition' using errcode='23514';
            end if;
          end if;
          if new.stage = 'invoked' and (new.invoked_at > clock_timestamp()
             or new.claim_expires_at <= clock_timestamp()) then
            raise exception 'outbox invocation lease is not current' using errcode='23514';
          end if;
          if new.stage = 'completed' and
             (new.outcome_json::jsonb->>'receipt_completed_at')::timestamptz > clock_timestamp() then
            raise exception 'outbox completion cannot be in the future' using errcode='23514';
          end if;
          return new;
        end $$;
    """)
    op.execute("""
        create trigger outbox_delivery_attempt_guard before insert or update or delete
          on outbox_delivery_attempts for each row execute function guard_outbox_delivery_attempt();
    """)
    op.execute("""
        create trigger outbox_delivery_attempt_truncate_guard before truncate
          on outbox_delivery_attempts for each statement execute function guard_outbox_delivery_attempt();
    """)
    op.execute("""
        create function check_outbox_delivery_projection() returns trigger language plpgsql as $$
        declare e outbox_events%rowtype; a outbox_delivery_attempts%rowtype;
                receipt jsonb; attempt_total bigint;
        begin
          select * into e from outbox_events where event_id = new.event_id;
          select count(*) into attempt_total from outbox_delivery_attempts where event_id = e.event_id;
          if attempt_total <> e.claim_generation or exists (
            select 1 from outbox_delivery_attempts x where x.event_id = e.event_id and
            (x.claim_generation > e.claim_generation or x.project_id <> e.project_id or
             x.payload_digest <> e.payload_digest or x.claimed_at < e.occurred_at or
             (x.claim_generation < e.claim_generation and x.stage <> 'completed'))
          ) then raise exception 'outbox delivery custody does not match event' using errcode='23514'; end if;
          if e.claim_generation = 0 then return null; end if;
          select * into a from outbox_delivery_attempts where event_id=e.event_id
            and claim_generation=e.claim_generation;
          if not found then
            raise exception 'outbox delivery custody missing' using errcode='23514';
          end if;
          if e.delivery_state = 'claimed' then
            if a.stage not in ('claimed','invoked') or
               (e.claim_owner,e.claimed_at,e.claim_expires_at,e.last_attempt_at) is distinct from
               (a.claim_owner,a.claimed_at,a.claim_expires_at,a.claimed_at) then
              raise exception 'outbox claim custody mismatch' using errcode='23514'; end if;
          else
            receipt := a.outcome_json::jsonb;
            if a.stage <> 'completed' or e.last_attempt_at is distinct from a.claimed_at or
               (e.delivery_state,e.last_error_code,e.next_attempt_at,e.finalized_at) is distinct from
               (receipt->>'delivery_state',receipt->>'error_code',
                (receipt->>'next_attempt_at')::timestamptz,(receipt->>'finalized_at')::timestamptz) then
              raise exception 'outbox outcome custody mismatch' using errcode='23514'; end if;
          end if;
          return null;
        end $$;
    """)
    op.execute("""
        create constraint trigger outbox_event_delivery_custody
          after insert or update on outbox_events deferrable initially deferred
          for each row execute function check_outbox_delivery_projection();
    """)
    op.execute("""
        create constraint trigger outbox_attempt_delivery_custody
          after insert or update on outbox_delivery_attempts deferrable initially deferred
          for each row execute function check_outbox_delivery_projection();
    """)


def downgrade() -> None:
    """Retained delivery evidence cannot be silently discarded."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
