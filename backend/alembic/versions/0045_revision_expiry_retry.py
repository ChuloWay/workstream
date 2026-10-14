"""Allow unknown expiry invocations to retry under exact receipt custody."""

from alembic import op
from sqlalchemy import text

revision = "0045_revision_expiry_retry"
down_revision = "0044_task_revision_expiry"
branch_labels = None
depends_on = None


def _replace(signature, old, new):
    body = op.get_bind().execute(text(
        "SELECT pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("expiry retry predecessor function shape changed")
    op.execute(body.replace(old, new))


def upgrade():
    _replace(
        "public.outbox_delivery_outcome_valid(text,text,timestamp with time zone,timestamp with time zone,timestamp with time zone)",
        """return invoked is not null and outcome_state = 'dead_letter'
              and code = 'INVOKE_OUTCOME_UNKNOWN' and retry_time is null and final_time = completed;""",
        """return invoked is not null and code = 'INVOKE_OUTCOME_UNKNOWN' and (
              (outcome_state = 'dead_letter' and retry_time is null and final_time = completed)
              or (outcome_state = 'retryable' and retry_time > completed and final_time is null));""",
    )
    # The shape function has no event selector. Enforce the exact supported
    # feature on every retained attempt, including earlier generations.
    _replace(
        "public.check_outbox_delivery_projection()",
        "if e.claim_generation = 0 then return null; end if;",
        """if exists (
            select 1 from outbox_delivery_attempts x
            where x.event_id = e.event_id
              and x.outcome_json::jsonb->>'invocation_unknown' = 'true'
              and x.outcome_json::jsonb->>'delivery_state' = 'retryable'
              and (e.event_type not in ('TaskRevisionExpiryRequested','TaskRevisionExpired')
                   or e.event_version <> 1)
          ) then raise exception 'outbox unknown retry is not registered'
            using errcode='23514'; end if;
          if e.claim_generation = 0 then return null; end if;""",
    )


def downgrade():
    raise RuntimeError("Retained expiry retry custody cannot be downgraded")
