"""Bind replacement intake and Submission creation to one completed checker route."""

from alembic import op
import sqlalchemy as sa

revision = "0034_checker_replacement"
down_revision = "0033_contribution_reads"
branch_labels = None
depends_on = None


def _replace(signature: str, old: str, new: str) -> None:
    body = op.get_bind().execute(sa.text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError("replacement migration function shape changed: " + signature)
    op.execute(body.replace(old, new))


def upgrade() -> None:
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.submissions, public.pre_submit_evidence_sets, "
               "public.submission_bundle_admissions, public.submission_dispatches "
               "IN ACCESS EXCLUSIVE MODE")
    # Retained revisions have no persisted exact checker cause or AUTH digest.
    # A guessed backfill would invent evidence. The entire Alembic transaction
    # therefore refuses them before the first schema change.
    op.execute("""
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.submissions WHERE version>1 OR supersedes_submission_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM public.pre_submit_evidence_sets WHERE predecessor_submission_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM public.submission_bundle_admissions WHERE predecessor_submission_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM public.submission_dispatches WHERE creation_kind<>'initial')
      THEN RAISE EXCEPTION 'retained replacement cause and receipts cannot be proven'
        USING ERRCODE='23514'; END IF;
    END $$;
    """)
    for table in ("pre_submit_evidence_sets", "submission_bundle_admissions", "submission_dispatches"):
        op.add_column(table, sa.Column("checker_remediation_manifest_id", sa.Uuid(), nullable=True), schema="public")
        op.create_foreign_key(
            op.f(f"fk_{table}_checker_remediation_manifest"), table,
            "task_post_submit_routing_manifests", ["checker_remediation_manifest_id"], ["id"],
            source_schema="public", referent_schema="public", ondelete="RESTRICT",
        )
    op.create_check_constraint(
        op.f("ck_pre_submit_evidence_sets_remediation_shape"), "pre_submit_evidence_sets",
        "(predecessor_submission_id is null) = (checker_remediation_manifest_id is null)",
        schema="public",
    )
    op.create_check_constraint(
        op.f("ck_submission_bundle_admissions_remediation_shape"), "submission_bundle_admissions",
        "(predecessor_submission_id is null) = (checker_remediation_manifest_id is null)",
        schema="public",
    )
    op.alter_column("submission_dispatches", "creation_kind", type_=sa.String(32),
                    existing_type=sa.String(16), existing_nullable=False, schema="public")
    op.drop_constraint(op.f("ck_submission_dispatches_creation_shape"), "submission_dispatches", type_="check", schema="public")
    op.create_check_constraint(
        op.f("ck_submission_dispatches_creation_shape"), "submission_dispatches",
        "(submission_version=1 and creation_kind='initial' and creation_status='in_progress' "
        "and checker_remediation_manifest_id is null) or "
        "(submission_version>1 and creation_kind='checker_remediation' "
        "and creation_status='needs_revision' and checker_remediation_manifest_id is not null)",
        schema="public",
    )

    _replace("public.guard_pre_submit_evidence_set_creation()",
             "return new;",
             """if new.checker_remediation_manifest_id is not null then
            -- Hold owner rows in TASK -> assignment -> predecessor -> CHECKERS
            -- order until commit, so a newly reserved checker run cannot
            -- supersede the cause between intake validation and evidence insert.
            perform 1 from public.workstream_tasks t
              where t.id=new.task_id and t.project_id=new.project_id
                and t.status='needs_revision' and t.assigned_to=new.actor_profile_id
              for update;
            if not found then raise exception 'pre-submit remediation task is not current'
              using errcode='23514'; end if;
            perform 1 from public.task_assignments a
              where a.id=new.assignment_id and a.task_id=new.task_id
                and a.project_id=new.project_id and a.contributor_id=new.actor_profile_id
                and a.status='active' and a.accepted_at is not null and a.released_at is null
              for update;
            if not found then raise exception 'pre-submit remediation assignment is not current'
              using errcode='23514'; end if;
            perform 1 from public.submissions s
              where s.id=new.predecessor_submission_id and s.task_id=new.task_id
                and s.contributor_id=new.actor_profile_id
                and s.task_assignment_id=new.assignment_id
                and s.version=new.predecessor_submission_version
                and not exists (select 1 from public.submissions successor
                  where successor.task_id=s.task_id and successor.version>s.version)
              for update;
            if not found then raise exception 'pre-submit remediation predecessor is not current'
              using errcode='23514'; end if;
            perform 1 from public.checker_submission_fences f
              join public.task_post_submit_routing_manifests m
                on m.submission_id=f.submission_id and m.checker_run_id=f.current_run_id
              where m.id=new.checker_remediation_manifest_id
                and f.submission_id=new.predecessor_submission_id
              for update of f;
            if not found then raise exception 'pre-submit remediation evaluation is not current'
              using errcode='23514'; end if;
          end if;
          if new.checker_remediation_manifest_id is not null and not exists (
            select 1 from public.task_post_submit_routing_manifests m
            where m.id=new.checker_remediation_manifest_id
              and m.project_id=new.project_id and m.task_id=new.task_id
              and m.assignment_id=new.assignment_id and m.contributor_id=new.actor_profile_id
              and m.submission_id=new.predecessor_submission_id
              and m.submission_version=new.predecessor_submission_version
              and m.routing_recommendation='needs_revision'
              and public.task_routing_outcome_complete(m)
          ) then
            raise exception 'pre-submit remediation source mismatch' using errcode='23514';
          end if;
          return new;""")
    _replace("public.require_pre_submit_attempt_evidence()",
             "'predecessor_submission_id','predecessor_submission_version',",
             "'predecessor_submission_id','predecessor_submission_version',\n"
             "   'checker_remediation_manifest_id',")
    _replace("public.guard_submission_bundle_admission_lineage()",
             "old.predecessor_submission_version,",
             "old.predecessor_submission_version, old.checker_remediation_manifest_id,")
    _replace("public.guard_submission_bundle_admission_lineage()",
             "new.predecessor_submission_version,",
             "new.predecessor_submission_version, new.checker_remediation_manifest_id,")
    _replace("public.guard_submission_bundle_admission_verified_lineage()",
             "and new.predecessor_submission_version is not distinct from evidence.predecessor_submission_version",
             "and new.predecessor_submission_version is not distinct from evidence.predecessor_submission_version\n"
             "            and new.checker_remediation_manifest_id is not distinct from evidence.checker_remediation_manifest_id")

    _replace("public.submission_binding_resource(uuid)",
             "'predecessor_submission_version',a.predecessor_submission_version,",
             "'predecessor_submission_version',a.predecessor_submission_version,\n"
             "  'checker_remediation_manifest_id',a.checker_remediation_manifest_id,")
    _replace("public.submission_creation_resource(uuid)",
             "'predecessor_submission_version',p.version,'submission_id'",
             "'predecessor_submission_version',p.version,\n"
             "  'checker_remediation_manifest_id',a.checker_remediation_manifest_id,'submission_id'")
    _replace("public.submission_creation_resource(uuid)",
             "THEN 'initial' ELSE 'revision' END",
             "THEN 'initial' ELSE 'checker_remediation' END")

    dispatch = "public.submission_dispatch_valid(public.submission_dispatches)"
    _replace(dispatch,
             "JOIN public.submission_bundle_admissions a ON a.id=s.submission_bundle_admission_id",
             "JOIN public.submission_bundle_admissions a ON a.id=s.submission_bundle_admission_id\n"
             " JOIN public.pre_submit_evidence_sets evidence ON evidence.id=a.pre_submit_evidence_set_id\n"
             " LEFT JOIN public.task_post_submit_routing_manifests cause ON cause.id=d.checker_remediation_manifest_id")
    _replace(dispatch,
             "AND d.creation_kind=CASE WHEN s.supersedes_submission_id IS NULL THEN 'initial' ELSE 'revision' END",
             """AND evidence.checker_remediation_manifest_id IS NOT DISTINCT FROM a.checker_remediation_manifest_id
  AND d.checker_remediation_manifest_id IS NOT DISTINCT FROM a.checker_remediation_manifest_id
  AND (d.checker_remediation_manifest_id IS NULL OR (
    cause.project_id=d.project_id AND cause.task_id=d.task_id
    AND cause.assignment_id=d.assignment_id AND cause.contributor_id=d.contributor_id
    AND cause.submission_id=s.supersedes_submission_id
    AND cause.submission_version=a.predecessor_submission_version
    AND cause.routing_recommendation='needs_revision'
    AND public.task_routing_context_valid(cause)
    AND EXISTS (SELECT 1 FROM public.audit_events routed WHERE routed.id=cause.audit_event_id
      AND routed.entity_type='task' AND routed.entity_id=d.task_id
      AND routed.event_type='TaskPostSubmitRouted'
      AND routed.from_status='evaluation_pending' AND routed.to_status='needs_revision'
      AND routed.actor_id=cause.router_actor_id::text AND routed.auth_source='local_lifecycle'
      AND routed.event_payload::jsonb=pg_catalog.jsonb_build_object('references',pg_catalog.jsonb_build_object(
        'project_id',cause.project_id::text,'task_id',cause.task_id::text,
        'submission_id',cause.submission_id::text,'assignment_id',cause.assignment_id::text,
        'authorization_decision_id',cause.authorization_decision_id::text,
        'routing_manifest_id',cause.id::text)))
    AND EXISTS (SELECT 1 FROM public.outbox_events notice WHERE notice.event_id=cause.outcome_event_id
      AND notice.event_type='TaskPostSubmitRouted' AND notice.event_version=1
      AND notice.aggregate_type='task' AND notice.aggregate_id=d.task_id
      AND notice.project_id=d.project_id AND notice.causation_event_id=cause.completion_event_id
      AND notice.correlation_id=cause.authority_context#>>'{request,route_operation_id}'
      AND notice.idempotency_key='task-routed:' || cause.id::text
      AND notice.payload::jsonb=pg_catalog.jsonb_build_object(
        'routing_manifest_id',cause.id::text,'task_id',cause.task_id::text,
        'submission_id',cause.submission_id::text,
        'authorization_decision_id',cause.authorization_decision_id::text,
        'human_review_required',cause.human_review_required,
        'final_acceptance_id',cause.final_acceptance_id::text))
  ))
  AND d.creation_kind=CASE WHEN s.supersedes_submission_id IS NULL THEN 'initial' ELSE 'checker_remediation' END""")
    # This deferred insert guard checks currentness at commit. Do not add the
    # mutable fence to submission_dispatch_valid: retained dispatches must
    # remain valid after a later evaluation generation is reserved.
    _replace("public.guard_submission_dispatch_receipt()",
             "IF NOT public.submission_dispatch_valid(NEW) THEN",
             """IF NEW.checker_remediation_manifest_id IS NOT NULL THEN
  PERFORM 1 FROM public.workstream_tasks t WHERE t.id=NEW.task_id
    AND t.project_id=NEW.project_id AND t.assigned_to=NEW.contributor_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'replacement dispatch task is not current'
    USING ERRCODE='23514'; END IF;
  PERFORM 1 FROM public.task_assignments a WHERE a.id=NEW.assignment_id
    AND a.task_id=NEW.task_id AND a.project_id=NEW.project_id
    AND a.contributor_id=NEW.contributor_id AND a.status='active'
    AND a.accepted_at IS NOT NULL AND a.released_at IS NULL FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'replacement dispatch assignment is not current'
    USING ERRCODE='23514'; END IF;
  PERFORM 1 FROM public.submissions prior JOIN public.submissions created
    ON created.supersedes_submission_id=prior.id
    WHERE created.id=NEW.submission_id AND created.task_id=NEW.task_id
      AND prior.task_id=NEW.task_id AND prior.version=NEW.submission_version-1
    FOR UPDATE OF prior;
  IF NOT FOUND THEN RAISE EXCEPTION 'replacement dispatch predecessor is not current'
    USING ERRCODE='23514'; END IF;
  PERFORM 1 FROM public.checker_submission_fences f
    JOIN public.task_post_submit_routing_manifests m
      ON m.submission_id=f.submission_id AND m.checker_run_id=f.current_run_id
    JOIN public.submissions created ON created.supersedes_submission_id=f.submission_id
    WHERE created.id=NEW.submission_id AND m.id=NEW.checker_remediation_manifest_id
    FOR UPDATE OF f;
  IF NOT FOUND THEN RAISE EXCEPTION 'replacement dispatch evaluation is not current'
    USING ERRCODE='23514'; END IF;
 END IF;
 IF NOT public.submission_dispatch_valid(NEW) THEN""")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
