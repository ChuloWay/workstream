"""Extend exact routing custody to contributor remediation without acceptance."""

from alembic import op
import sqlalchemy as sa

revision = "0031_checker_remediation"
down_revision = "0030_routing_outcomes"
branch_labels = None
depends_on = None


def _replace(signature, old, new):
    """Replace one known predecessor clause; refuse an unexpected migration shape."""
    body = op.get_bind().execute(sa.text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("remediation migration function shape changed: " + signature)
    op.execute(body.replace(old, new))


def upgrade():
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.task_post_submit_routing_manifests, "
               "public.task_post_submit_routing_requests IN ACCESS EXCLUSIVE MODE")
    # A constant added-column default preserves retained success rows without
    # rewriting their immutable source JSON, AUTH receipts or outbox notices.
    op.execute("ALTER TABLE public.task_post_submit_routing_manifests "
               "ADD COLUMN routing_recommendation varchar(32) NOT NULL DEFAULT 'allow_review'")
    op.execute("ALTER TABLE public.task_post_submit_routing_manifests "
               "ALTER COLUMN routing_recommendation DROP DEFAULT")
    op.execute("ALTER TABLE public.task_post_submit_routing_manifests "
               "ADD CONSTRAINT ck_task_post_submit_routing_manifests_recommendations "
               "CHECK (routing_recommendation IN ('allow_review','needs_revision'))")
    op.execute("ALTER TABLE public.task_post_submit_routing_requests "
               "DROP CONSTRAINT ck_task_post_submit_routing_requests_allow_review_only")
    op.execute("ALTER TABLE public.task_post_submit_routing_requests "
               "ADD CONSTRAINT ck_task_post_submit_routing_requests_recommendations "
               "CHECK (routing_recommendation IN ('allow_review','needs_revision'))")

    _replace("public.guard_task_post_submit_routing_source()",
             "candidate.routing_recommendation IS NOT DISTINCT FROM 'allow_review'",
             "candidate.routing_recommendation IS NOT DISTINCT FROM NEW.routing_recommendation")
    _replace("public.guard_task_routing_request()",
             "OR run.routing_recommendation IS DISTINCT FROM 'allow_review'\n"
             "       OR NEW.routing_recommendation IS DISTINCT FROM 'allow_review'",
             "OR run.routing_recommendation IS DISTINCT FROM NEW.routing_recommendation\n"
             "       OR NEW.routing_recommendation NOT IN ('allow_review','needs_revision')")
    _replace("public.guard_task_routing_request()",
             "'routing_recommendation', 'allow_review', 'output_binding_ids'",
             "'routing_recommendation', NEW.routing_recommendation, 'output_binding_ids'")

    context = "public.task_routing_context_valid(public.task_post_submit_routing_manifests)"
    _replace(context, "q.routing_recommendation<>'allow_review'",
             "q.routing_recommendation IS DISTINCT FROM m.routing_recommendation "
             "OR r.routing_recommendation IS DISTINCT FROM m.routing_recommendation")
    _replace(context, "'routing_recommendation','allow_review',",
             "'routing_recommendation',m.routing_recommendation,")
    _replace(context, "IF m.human_review_required THEN",
             "IF m.routing_recommendation='needs_revision' THEN\n"
             "        IF m.final_acceptance_id IS NOT NULL OR m.authorized_lifecycle_generation IS NOT NULL "
             "THEN RETURN false; END IF;\n"
             "        consequence := jsonb_build_object('kind','checker_remediation',\n"
             "          'expected_task_status','evaluation_pending','target_task_status','needs_revision');\n"
             "      ELSIF m.human_review_required THEN")

    authority = "public.guard_task_routing_authority()"
    _replace(authority, "IF NOT NEW.human_review_required THEN",
             "IF NEW.routing_recommendation='allow_review' AND NOT NEW.human_review_required THEN")
    _replace(authority, "IF NOT NEW.human_review_required AND NOT EXISTS",
             "IF NEW.routing_recommendation='allow_review' AND NOT NEW.human_review_required AND NOT EXISTS")
    _replace("public.task_routing_acceptance_matches(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,bigint,boolean)",
             "AND NOT m.human_review_required AND m.authorized_lifecycle_generation>0",
             "AND m.routing_recommendation='allow_review' "
             "AND NOT m.human_review_required AND m.authorized_lifecycle_generation>0")

    complete = "public.task_routing_outcome_complete(public.task_post_submit_routing_manifests)"
    _replace(complete, "CASE WHEN m.human_review_required THEN 'review_pending' ELSE 'accepted' END",
             "CASE WHEN m.routing_recommendation='needs_revision' THEN 'needs_revision' "
             "WHEN m.human_review_required THEN 'review_pending' ELSE 'accepted' END")
    _replace(complete, "CASE WHEN m.human_review_required THEN 'active' ELSE 'completed' END",
             "CASE WHEN m.routing_recommendation='needs_revision' OR m.human_review_required "
             "THEN 'active' ELSE 'completed' END")
    _replace(complete, "IF m.human_review_required THEN",
             "IF m.routing_recommendation='needs_revision' OR m.human_review_required THEN")
    _replace("public.guard_task_accepted_routing_state()", "WHERE NOT human_review_required AND",
             "WHERE routing_recommendation='allow_review' AND NOT human_review_required AND")


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
