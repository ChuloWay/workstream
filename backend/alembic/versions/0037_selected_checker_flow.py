"""Install selected PRE custody and selected POST policy lineage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0037_selected_checker_flow"
down_revision = "0036_contribution_export_pages"
branch_labels = None
depends_on = None


def _definition(table: str, name: str) -> str:
    return op.get_bind().execute(sa.text(
        "select pg_catalog.pg_get_constraintdef(oid) from pg_catalog.pg_constraint "
        "where conrelid=cast(:table as regclass) and conname=:name"
    ), {"table": "public." + table, "name": name}).scalar_one()


def _replace(table: str, name: str, definition: str) -> None:
    op.execute(f"alter table public.{table} drop constraint {name}")
    op.execute(f"alter table public.{table} add constraint {name} {definition}")


def _extend(table: str, name: str, anchor: str, addition: str, count: int) -> None:
    definition = _definition(table, name)
    if definition.count(anchor) != count or addition in definition:
        raise RuntimeError(f"selected checker constraint shape changed: {name}")
    _replace(table, name, definition.replace(anchor, anchor + addition))


def _extend_authority_vocabulary() -> None:
    _extend(
        "actor_profiles", "ck_actor_profiles_kind_service_identity",
        "('workstream.checker.post_submit'::character varying)::text",
        ", ('workstream.checker.pre_submit'::character varying)::text", 1,
    )
    _extend(
        "audit_events", "ck_audit_events_authority_registries",
        "('checker.post_submit.execute'::character varying)::text",
        ", ('checker.pre_submit.execute'::character varying)::text, "
        "('checker.pre_submit.finalize'::character varying)::text", 1,
    )
    _extend(
        "audit_events", "ck_audit_events_authority_privacy_bounds",
        "('checker_run'::character varying)::text",
        ", ('selected_pre_submit_run'::character varying)::text", 1,
    )
    name = "ck_audit_events_authorization_action_evidence"
    definition = _definition("audit_events", name)
    anchor = (
        "(((action_id)::text = 'project.task.create'::text) AND "
        "((permission_id)::text = 'project.task.manage'::text))"
    )
    additions = " OR ".join(
        "(((action_id)::text = "
        f"'{action}'::text) AND ((permission_id)::text = '{action}'::text))"
        for action in ("checker.pre_submit.execute", "checker.pre_submit.finalize")
    )
    if definition.count(anchor) != 2 or additions in definition:
        raise RuntimeError("selected PRE audit action constraint shape changed")
    _replace("audit_events", name, definition.replace(anchor, anchor + " OR " + additions))


def _create_selected_run_table() -> None:
    op.create_table(
        "selected_pre_submit_runs",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("actor_profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("identity_link_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("task_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("assignment_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("prepared_generation_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("request_json", postgresql.JSONB(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("policy_sha256", sa.String(71), nullable=False),
        sa.Column("default_behavior_sha256", sa.String(71), nullable=False),
        sa.Column("default_input_sha256", sa.String(71), nullable=False),
        sa.Column("archive_sha256", sa.String(71), nullable=False),
        sa.Column("archive_byte_count", sa.BigInteger(), nullable=False),
        sa.Column("semantic_manifest_sha256", sa.String(71), nullable=False),
        sa.Column("execution_budget_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("lease_id", sa.Uuid(as_uuid=False)),
        sa.Column("lease_generation", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("execute_evidence_id", sa.Uuid(as_uuid=False)),
        sa.Column("finalize_evidence_id", sa.Uuid(as_uuid=False)),
        sa.Column("terminal_json", postgresql.JSONB()),
        sa.Column("terminal_digest", sa.String(71)),
        sa.Column("eligible", sa.Boolean()),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("(get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128", name="id_uuid7"),
        sa.CheckConstraint("status in ('queued','running','completed','infrastructure_failed')", name="status"),
        sa.CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$' and policy_sha256 ~ '^sha256:[0-9a-f]{64}$' and default_behavior_sha256 ~ '^sha256:[0-9a-f]{64}$' and default_input_sha256 ~ '^sha256:[0-9a-f]{64}$' and archive_sha256 ~ '^sha256:[0-9a-f]{64}$' and semantic_manifest_sha256 ~ '^sha256:[0-9a-f]{64}$' and (terminal_digest is null or terminal_digest ~ '^sha256:[0-9a-f]{64}$')", name="digests"),
        sa.CheckConstraint("archive_byte_count > 0", name="archive_size"),
        sa.CheckConstraint("execution_budget_ms between 100 and 14400000", name="execution_budget"),
        sa.CheckConstraint("lease_generation >= 0", name="lease_generation"),
        sa.CheckConstraint("jsonb_typeof(request_json)='object' and (terminal_json is null or jsonb_typeof(terminal_json)='object')", name="json_objects"),
        sa.CheckConstraint(
            "(status='queued' and lease_id is null and lease_expires_at is null and terminal_json is null and terminal_digest is null and eligible is null and started_at is null and completed_at is null and execute_evidence_id is null and finalize_evidence_id is null) or "
            "(status='running' and lease_id is not null and lease_generation>0 and lease_expires_at is not null and terminal_json is null and terminal_digest is null and eligible is null and started_at is not null and completed_at is null and execute_evidence_id is not null and finalize_evidence_id is null) or "
            "(status='completed' and lease_id is not null and lease_generation>0 and lease_expires_at is not null and terminal_json is not null and terminal_digest is not null and eligible is not null and started_at is not null and completed_at is not null and execute_evidence_id is not null and finalize_evidence_id is not null) or "
            "(status='infrastructure_failed' and lease_id is not null and lease_generation>0 and lease_expires_at is not null and terminal_json is not null and terminal_digest is not null and eligible is null and started_at is not null and completed_at is not null and execute_evidence_id is not null and finalize_evidence_id is not null)",
            name="lifecycle",
        ),
        sa.ForeignKeyConstraint(["task_id", "project_id"], ["workstream_tasks.id", "workstream_tasks.project_id"], name="fk_selected_pre_run_task_project"),
        sa.ForeignKeyConstraint(["assignment_id", "task_id", "actor_profile_id"], ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"], name="fk_selected_pre_run_assignment"),
        sa.ForeignKeyConstraint(["identity_link_id", "actor_profile_id"], ["actor_identity_links.id", "actor_identity_links.actor_profile_id"], name="fk_selected_pre_run_actor_link"),
        sa.ForeignKeyConstraint(["execute_evidence_id"], ["audit_events.id"], name="fk_selected_pre_submit_runs_execute_evidence_id_audit_events", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["finalize_evidence_id"], ["audit_events.id"], name="fk_selected_pre_submit_runs_finalize_evidence_id_audit_events", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_selected_pre_submit_runs"),
        sa.UniqueConstraint("request_digest", name="request_digest"),
        sa.UniqueConstraint("actor_profile_id", "idempotency_key", name="uq_selected_pre_run_actor_key"),
        schema="public",
    )
    op.create_index("ix_selected_pre_runs_task", "selected_pre_submit_runs", ["task_id"])
    op.create_index("ix_selected_pre_runs_status", "selected_pre_submit_runs", ["status"])


def _alter_selected_lineage() -> None:
    for table in ("submissions", "checker_runs"):
        op.add_column(table, sa.Column("selected_post_submit_policy_sha256", sa.String(71)))
        op.add_column(table, sa.Column("selected_post_submit_policy_body", postgresql.JSONB()))
        op.create_check_constraint(
            "selected_post_submit_policy", table,
            "(selected_post_submit_policy_sha256 is null and selected_post_submit_policy_body is null) or (selected_post_submit_policy_sha256 ~ '^sha256:[0-9a-f]{64}$' and jsonb_typeof(selected_post_submit_policy_body)='object')",
        )

    table = "submission_bundle_durable_intents"
    op.alter_column(table, "pre_submit_evidence_set_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column(table, sa.Column("selected_pre_submit_run_id", sa.Uuid(as_uuid=False)))
    op.add_column(table, sa.Column("selected_request_json", postgresql.JSONB()))
    op.add_column(table, sa.Column("selected_request_digest", sa.String(71)))
    op.add_column(table, sa.Column("selected_terminal_json", postgresql.JSONB()))
    op.add_column(table, sa.Column("selected_terminal_digest", sa.String(71)))
    op.create_foreign_key(op.f("fk_submission_bundle_durable_intents_selected_pre_submit_run_id_selected_pre_submit_runs"), table, "selected_pre_submit_runs", ["selected_pre_submit_run_id"], ["id"], ondelete="RESTRICT")
    op.create_index(op.f("ix_submission_bundle_durable_intents_selected_pre_submit_run_id"), table, ["selected_pre_submit_run_id"])
    op.create_unique_constraint("uq_submission_bundle_intent_selected_run", table, ["selected_pre_submit_run_id"])
    op.create_check_constraint("pre_submit_lineage", table, "((pre_submit_evidence_set_id is not null)::int + (selected_pre_submit_run_id is not null)::int)=1")
    op.create_check_constraint("selected_snapshot", table, "(pre_submit_evidence_set_id is not null and selected_request_json is null and selected_request_digest is null and selected_terminal_json is null and selected_terminal_digest is null) or (selected_pre_submit_run_id is not null and jsonb_typeof(selected_request_json)='object' and selected_request_digest ~ '^sha256:[0-9a-f]{64}$' and jsonb_typeof(selected_terminal_json)='object' and selected_terminal_digest ~ '^sha256:[0-9a-f]{64}$')")

    table = "submission_bundle_admissions"
    op.alter_column(table, "pre_submit_evidence_set_id", existing_type=sa.Uuid(), nullable=True)
    columns = (
        sa.Column("selected_pre_submit_run_id", sa.Uuid(as_uuid=False)),
        sa.Column("guide_id", sa.Uuid(as_uuid=False)), sa.Column("guide_version", sa.String(50)),
        sa.Column("source_snapshot_id", sa.Uuid(as_uuid=False)), sa.Column("source_snapshot_sha256", sa.String(71)),
        sa.Column("effective_policy_id", sa.Uuid(as_uuid=False)), sa.Column("effective_policy_sha256", sa.String(71)),
        sa.Column("pre_submit_policy_id", sa.Uuid(as_uuid=False)), sa.Column("pre_submit_policy_sha256", sa.String(71)),
        sa.Column("effective_plan_sha256", sa.String(71)), sa.Column("selected_rules_sha256", sa.String(71)),
        sa.Column("selected_post_submit_policy_sha256", sa.String(71)), sa.Column("selected_post_submit_policy_body", postgresql.JSONB()),
        sa.Column("packet_sha256", sa.String(71)), sa.Column("semantic_manifest_body", postgresql.JSONB()),
    )
    for column in columns:
        op.add_column(table, column)
    op.create_foreign_key(op.f("fk_submission_bundle_admissions_selected_pre_submit_run_id_selected_pre_submit_runs"), table, "selected_pre_submit_runs", ["selected_pre_submit_run_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_submission_bundle_admissions_selected_pre_submit_run_id", table, ["selected_pre_submit_run_id"])
    op.create_unique_constraint("uq_submission_bundle_admission_selected_run", table, ["selected_pre_submit_run_id"])
    op.create_check_constraint("pre_submit_lineage", table, "((pre_submit_evidence_set_id is not null)::int + (selected_pre_submit_run_id is not null)::int)=1")
    op.create_check_constraint("manifest_body", table, "(selected_pre_submit_run_id is null and semantic_manifest_body is null) or (selected_pre_submit_run_id is not null and jsonb_typeof(semantic_manifest_body)='object')")
    for name in ("packet_sha256", "effective_plan_sha256", "selected_rules_sha256"):
        op.create_check_constraint(name, table, f"(selected_pre_submit_run_id is null and {name} is null) or (selected_pre_submit_run_id is not null and {name} ~ '^sha256:[0-9a-f]{{64}}$')")
    op.create_check_constraint("selected_post_submit_policy", table, "(selected_pre_submit_run_id is null and selected_post_submit_policy_sha256 is null and selected_post_submit_policy_body is null) or (selected_pre_submit_run_id is not null and selected_post_submit_policy_sha256 ~ '^sha256:[0-9a-f]{64}$' and jsonb_typeof(selected_post_submit_policy_body)='object')")
    op.create_check_constraint("locked_policy_digests", table, "(selected_pre_submit_run_id is null and guide_id is null and guide_version is null and source_snapshot_id is null and source_snapshot_sha256 is null and effective_policy_id is null and effective_policy_sha256 is null and pre_submit_policy_id is null and pre_submit_policy_sha256 is null) or (selected_pre_submit_run_id is not null and guide_id is not null and octet_length(guide_version) between 1 and 50 and source_snapshot_id is not null and effective_policy_id is not null and pre_submit_policy_id is not null and source_snapshot_sha256 ~ '^sha256:[0-9a-f]{64}$' and effective_policy_sha256 ~ '^sha256:[0-9a-f]{64}$' and pre_submit_policy_sha256 ~ '^sha256:[0-9a-f]{64}$')")



def _replace_admission_guards() -> None:
    op.execute(r"""
create or replace function public.guard_submission_bundle_durable_intent_put_attempt()
returns trigger language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare request_type text; selected_matches integer;
begin
 select producer_request_type into request_type from public.artifact_put_attempts
 where id=new.put_attempt_id for share;
 if request_type is distinct from 'submission_bundle' then
  raise exception 'submission bundle durable intent requires submission_bundle put attempt'
    using errcode='23514';
 end if;
 if new.selected_pre_submit_run_id is not null then
  select count(*) into selected_matches
  from public.selected_pre_submit_runs r
  join public.artifact_put_attempts a on a.id=new.put_attempt_id
  where r.id=new.selected_pre_submit_run_id and r.status='completed' and r.eligible
    and new.selected_request_json=r.request_json
    and new.selected_request_digest=r.request_digest
    and new.selected_terminal_json=r.terminal_json
    and new.selected_terminal_digest=r.terminal_digest
    and a.producer_type='actor_profile' and a.producer_ref=r.actor_profile_id::text
    and a.project_id=r.project_id and a.task_id=r.task_id
    and a.sha256=r.archive_sha256 and a.byte_count=r.archive_byte_count
    and a.media_type='application/zip';
  if selected_matches<>1 then
   raise exception 'selected PRE durable intent custody mismatch' using errcode='23514';
  end if;
 end if;
 return new;
end $$
""")
    op.execute(r"""
create or replace function public.guard_submission_bundle_admission_lineage()
returns trigger language plpgsql set search_path=pg_catalog,public,pg_temp as $$
begin
 if (to_jsonb(old)-array['status','consumed_at','consumed_by_submission_id',
      'consumed_by_submission_version','stale_at','stale_reason']::text[])
    is distinct from
    (to_jsonb(new)-array['status','consumed_at','consumed_by_submission_id',
      'consumed_by_submission_version','stale_at','stale_reason']::text[]) then
  raise exception 'submission bundle admission lineage is immutable' using errcode='55000';
 end if;
 if old.status<>'ready' or new.status not in ('consumed','stale') then
  raise exception 'invalid submission bundle admission transition' using errcode='23514';
 end if;
 return new;
end $$
""")
    op.execute(r"""
create or replace function public.guard_submission_bundle_admission_verified_lineage()
returns trigger language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare matches integer;
begin
 if new.pre_submit_evidence_set_id is not null then
  select count(*) into matches
  from public.submission_bundle_durable_intents intent
  join public.pre_submit_evidence_sets evidence on evidence.id=intent.pre_submit_evidence_set_id
  join public.artifact_put_attempts attempt on attempt.id=intent.put_attempt_id
  join public.artifact_replicas replica on replica.id=attempt.replica_id
  join public.artifact_contents content on content.id=replica.content_id
  join public.artifact_verification_jobs job
    on job.originating_put_attempt_id=attempt.id and job.replica_id=replica.id
  join public.artifact_verification_receipts verification on verification.verification_job_id=job.id
  where intent.id=new.durable_intent_id and evidence.id=new.pre_submit_evidence_set_id
    and attempt.id=new.put_attempt_id and content.id=new.artifact_content_id
    and replica.id=new.verified_replica_id and verification.id=new.verification_receipt_id
    and attempt.producer_request_type='submission_bundle'
    and attempt.producer_type='actor_profile' and attempt.producer_ref=evidence.actor_profile_id::text
    and attempt.project_id=evidence.project_id and attempt.task_id=evidence.task_id
    and attempt.media_type='application/zip' and content.media_type='application/zip'
    and attempt.status='object_confirmed' and evidence.terminal_status='passed' and evidence.eligible
    and replica.verification_state='verified' and replica.availability_state='available'
    and replica.integrity_state='valid' and verification.outcome='verified'
    and verification.execution_generation=job.execution_generation
    and verification.observed_sha256=attempt.sha256
    and verification.observed_sha256=content.sha256
    and verification.observed_sha256=evidence.archive_sha256
    and verification.observed_byte_count=attempt.byte_count
    and verification.observed_byte_count=content.byte_count
    and verification.observed_byte_count=evidence.archive_byte_count
    and new.actor_profile_id=evidence.actor_profile_id
    and new.identity_link_id=evidence.identity_link_id
    and new.project_id=evidence.project_id and new.task_id=evidence.task_id
    and new.assignment_id=evidence.assignment_id
    and new.predecessor_submission_id is not distinct from evidence.predecessor_submission_id
    and new.predecessor_submission_version is not distinct from evidence.predecessor_submission_version
    and new.locked_policy_context_hash=evidence.locked_policy_context_hash
    and new.semantic_manifest_id=evidence.semantic_manifest_id
    and new.semantic_manifest_sha256=evidence.semantic_manifest_sha256
    and new.archive_sha256=evidence.archive_sha256 and new.archive_byte_count=evidence.archive_byte_count
    and ((new.put_operation_receipt_id is not null and exists(
      select 1 from public.artifact_operation_receipts receipt
      where receipt.id=new.put_operation_receipt_id and receipt.put_attempt_id=attempt.id
        and receipt.replica_id=replica.id and receipt.outcome='stored_pending_verification'))
      or (new.put_observation_receipt_id is not null and exists(
      select 1 from public.artifact_put_observation_receipts observation
      where observation.id=new.put_observation_receipt_id and observation.put_attempt_id=attempt.id
        and observation.outcome='observed_confirmed'
        and observation.observed_sha256=attempt.sha256
        and observation.observed_byte_count=attempt.byte_count)));
 else
  select count(*) into matches
  from public.submission_bundle_durable_intents intent
  join public.selected_pre_submit_runs r on r.id=intent.selected_pre_submit_run_id
  join public.artifact_put_attempts attempt on attempt.id=intent.put_attempt_id
  join public.artifact_replicas replica on replica.id=attempt.replica_id
  join public.artifact_contents content on content.id=replica.content_id
  join public.artifact_verification_jobs job
    on job.originating_put_attempt_id=attempt.id and job.replica_id=replica.id
  join public.artifact_verification_receipts verification on verification.verification_job_id=job.id
  where intent.id=new.durable_intent_id and r.id=new.selected_pre_submit_run_id
    and r.status='completed' and r.eligible and intent.selected_request_json=r.request_json
    and intent.selected_request_digest=r.request_digest
    and intent.selected_terminal_json=r.terminal_json and intent.selected_terminal_digest=r.terminal_digest
    and attempt.id=new.put_attempt_id and content.id=new.artifact_content_id
    and replica.id=new.verified_replica_id and verification.id=new.verification_receipt_id
    and attempt.producer_request_type='submission_bundle'
    and attempt.producer_type='actor_profile' and attempt.producer_ref=r.actor_profile_id::text
    and attempt.project_id=r.project_id and attempt.task_id=r.task_id
    and attempt.media_type='application/zip' and content.media_type='application/zip'
    and attempt.status='object_confirmed' and replica.verification_state='verified'
    and replica.availability_state='available' and replica.integrity_state='valid'
    and verification.outcome='verified' and verification.execution_generation=job.execution_generation
    and verification.observed_sha256=attempt.sha256 and verification.observed_sha256=content.sha256
    and verification.observed_sha256=r.archive_sha256
    and verification.observed_byte_count=attempt.byte_count
    and verification.observed_byte_count=content.byte_count
    and verification.observed_byte_count=r.archive_byte_count
    and new.actor_profile_id=r.actor_profile_id
    and new.identity_link_id=r.identity_link_id and new.project_id=r.project_id
    and new.task_id=r.task_id and new.assignment_id=r.assignment_id
    and new.predecessor_submission_id is not distinct from
      nullif(r.request_json#>>'{admission_lineage,predecessor_submission_id}','')::uuid
    and new.predecessor_submission_version is not distinct from
      (r.request_json#>>'{admission_lineage,predecessor_submission_version}')::integer
    and new.guide_id=(r.request_json#>>'{admission_lineage,guide_id}')::uuid
    and new.guide_version=r.request_json#>>'{admission_lineage,guide_version}'
    and new.source_snapshot_id=(r.request_json#>>'{admission_lineage,source_snapshot_id}')::uuid
    and new.source_snapshot_sha256=r.request_json#>>'{admission_lineage,source_snapshot_sha256}'
    and new.effective_policy_id=(r.request_json#>>'{admission_lineage,effective_policy_id}')::uuid
    and new.effective_policy_sha256=r.request_json#>>'{admission_lineage,effective_policy_sha256}'
    and new.pre_submit_policy_id=(r.request_json#>>'{admission_lineage,pre_submit_policy_id}')::uuid
    and new.pre_submit_policy_sha256=r.request_json#>>'{admission_lineage,pre_submit_policy_sha256}'
    and new.effective_plan_sha256=r.request_json#>>'{admission_lineage,effective_plan_sha256}'
    and new.selected_rules_sha256=r.request_json#>>'{admission_lineage,rules_sha256}'
    and new.selected_post_submit_policy_sha256=r.request_json#>>'{admission_lineage,post_submit_policy_sha256}'
    and new.selected_post_submit_policy_body=r.request_json#>'{admission_lineage,post_submit_policy_body}'
    and new.locked_policy_context_hash=r.request_json#>>'{admission_lineage,locked_policy_context_hash}'
    and new.packet_sha256=r.request_json#>>'{admission_lineage,packet_sha256}'
    and new.semantic_manifest_id=(r.request_json#>>'{admission_lineage,semantic_manifest_id}')::uuid
    and new.semantic_manifest_body=r.request_json#>'{admission_lineage,semantic_manifest_body}'
    and new.semantic_manifest_sha256=r.semantic_manifest_sha256
    and new.archive_sha256=r.archive_sha256 and new.archive_byte_count=r.archive_byte_count
    and ((new.put_operation_receipt_id is not null and exists(
      select 1 from public.artifact_operation_receipts receipt
      where receipt.id=new.put_operation_receipt_id and receipt.put_attempt_id=attempt.id
        and receipt.replica_id=replica.id and receipt.outcome='stored_pending_verification'))
      or (new.put_observation_receipt_id is not null and exists(
      select 1 from public.artifact_put_observation_receipts observation
      where observation.id=new.put_observation_receipt_id and observation.put_attempt_id=attempt.id
        and observation.outcome='observed_confirmed'
        and observation.observed_sha256=attempt.sha256
        and observation.observed_byte_count=attempt.byte_count)));
 end if;
 if matches<>1 then
  raise exception 'submission bundle admission verified lineage mismatch' using errcode='23514';
 end if;
 return new;
end $$
""")

def _selected_run_guards() -> None:
    op.execute(r"""
create function public.selected_pre_submit_facts_digest(r public.selected_pre_submit_runs, phase text)
returns text language sql immutable strict set search_path=pg_catalog,public,pg_temp as $$
 select case phase
 when 'execute' then 'sha256:'||encode(sha256(convert_to(public.project_guide_projection_canonical_json(
   jsonb_build_object('schema_version','workstream.selected_pre_submit_execute.v1',
     'reservation',r.request_json,'lease_id',r.lease_id::text,
     'lease_generation',r.lease_generation,'lease_expires_at',public.outbox_dispatch_utc(r.lease_expires_at))), 'UTF8')),'hex')
 when 'finalize' then 'sha256:'||encode(sha256(convert_to(public.project_guide_projection_canonical_json(
   jsonb_build_object('schema_version','workstream.selected_pre_submit_finalize.v1',
     'execute_facts_digest',public.selected_pre_submit_facts_digest(r,'execute'),
     'execution',r.terminal_json->'execution',
     'infrastructure_failure_code',r.terminal_json->'infrastructure_failure_code')), 'UTF8')),'hex')
 else null end
$$
""")
    op.execute(r"""
create function public.selected_pre_submit_receipt_valid(r public.selected_pre_submit_runs, phase text, require_active boolean)
returns boolean language sql stable set search_path=pg_catalog,public,pg_temp as $$
 select coalesce(exists(
   select 1 from public.audit_events a
   join public.actor_profiles p on p.id::text=a.actor_id
   join public.actor_identity_links l on l.actor_profile_id=p.id
   where a.id=case when phase='execute' then r.execute_evidence_id else r.finalize_evidence_id end
     and phase in ('execute','finalize')
     and a.event_domain='authority' and a.event_type='SensitiveAuthorizationAllowed'
     and a.actor_ref_kind='actor_profile' and p.actor_kind='service'
     and p.service_identity='workstream.checker.pre_submit' and l.subject_kind='service'
     and (not require_active or (p.status='active' and l.status='active'))
     and a.action_id='checker.pre_submit.'||phase and a.permission_id=a.action_id
     and a.denial_code is null and a.matched_grant_id is null
     and a.project_id=r.project_id and a.resource_type='selected_pre_submit_run'
     and a.resource_id=r.id::text and a.target_ref_kind='project'
     and a.target_ref_id=r.project_id::text and a.request_id=r.id and a.correlation_id=r.id
     and a.after_facts::jsonb=jsonb_build_object('allowed',true,
       'resource_context_digest',public.selected_pre_submit_facts_digest(r,phase))
     and (phase='execute' or (r.execute_evidence_id is not null
       and r.finalize_evidence_id is distinct from r.execute_evidence_id
       and r.status in ('completed','infrastructure_failed')))
 ),false)
$$
""")
    op.execute(r"""
create function public.guard_selected_pre_submit_run() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare current_run public.selected_pre_submit_runs%rowtype;
begin
 if tg_op='DELETE' then raise exception 'selected PRE runs are retained' using errcode='55000'; end if;
 if tg_op='TRUNCATE' then raise exception 'selected PRE runs cannot be truncated' using errcode='55000'; end if;
 if row(old.id,old.actor_profile_id,old.identity_link_id,old.project_id,old.task_id,
        old.assignment_id,old.idempotency_key,old.prepared_generation_id,old.request_json,
        old.request_digest,old.policy_sha256,old.default_behavior_sha256,old.default_input_sha256,
        old.archive_sha256,old.archive_byte_count,old.semantic_manifest_sha256,
        old.execution_budget_ms,old.queued_at)
    is distinct from
    row(new.id,new.actor_profile_id,new.identity_link_id,new.project_id,new.task_id,
        new.assignment_id,new.idempotency_key,new.prepared_generation_id,new.request_json,
        new.request_digest,new.policy_sha256,new.default_behavior_sha256,new.default_input_sha256,
        new.archive_sha256,new.archive_byte_count,new.semantic_manifest_sha256,
        new.execution_budget_ms,new.queued_at)
 then raise exception 'selected PRE request custody is immutable' using errcode='55000'; end if;
 if not ((old.status='queued' and new.status='running' and new.lease_generation=1)
      or (old.status='running' and new.status in ('completed','infrastructure_failed')
          and new.lease_generation=old.lease_generation))
 then raise exception 'selected PRE lifecycle transition is invalid' using errcode='23514'; end if;
 return new;
end $$
""")
    op.execute("create trigger selected_pre_submit_run_update before update on public.selected_pre_submit_runs for each row execute function public.guard_selected_pre_submit_run()")
    op.execute("create trigger selected_pre_submit_run_delete before delete on public.selected_pre_submit_runs for each row execute function public.guard_selected_pre_submit_run()")
    op.execute("create trigger selected_pre_submit_run_truncate before truncate on public.selected_pre_submit_runs for each statement execute function public.guard_selected_pre_submit_run()")
    op.execute(r"""
create function public.guard_selected_pre_submit_receipts() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare current_run public.selected_pre_submit_runs%rowtype; new_execute boolean; new_finalize boolean;
begin
 select * into current_run from public.selected_pre_submit_runs where id=new.id;
 if not found then raise exception 'selected PRE authority parent is missing' using errcode='23514'; end if;
 if tg_op='INSERT' then
  new_execute := current_run.execute_evidence_id is not null;
  new_finalize := current_run.finalize_evidence_id is not null;
 else
  new_execute := current_run.execute_evidence_id is distinct from old.execute_evidence_id;
  new_finalize := current_run.finalize_evidence_id is distinct from old.finalize_evidence_id;
 end if;
 if (current_run.execute_evidence_id is not null and not public.selected_pre_submit_receipt_valid(current_run,'execute',new_execute))
    or (current_run.finalize_evidence_id is not null and not public.selected_pre_submit_receipt_valid(current_run,'finalize',new_finalize))
 then raise exception 'selected PRE authority receipt custody mismatch' using errcode='23514'; end if;
 return null;
end $$
""")
    op.execute("create constraint trigger selected_pre_submit_receipt_custody after insert or update on public.selected_pre_submit_runs deferrable initially deferred for each row execute function public.guard_selected_pre_submit_receipts()")


def _replace_guide_approval_custody() -> None:
    op.execute(r"""
create function public.external_checker_locked_policies_valid(value jsonb, expected_hash text)
returns boolean language plpgsql stable strict
set search_path=pg_catalog,public,pg_temp as $$
declare phase_name text; policy jsonb; binding jsonb; registry jsonb;
        registry_row public.external_checker_registry_entries%rowtype;
        prior_requirement text; prior_capability text; prior_version text;
begin
 if jsonb_typeof(value)<>'object' or (select count(*) from jsonb_object_keys(value))<>4
    or value->>'schema_version'<>'external_checker_policies.v1'
    or value->>'policies_sha256'<>expected_hash
    or public.guide_proposal_hash(value-'policies_sha256')<>expected_hash then
  raise exception 'external checker policy envelope mismatch' using errcode='23514';
 end if;
 if jsonb_typeof(value->'pre_submit')<>'object'
    or jsonb_typeof(value->'post_submit')<>'object' then
  raise exception 'external checker phase policy is missing' using errcode='23514';
 end if;
 foreach phase_name in array array['pre_submit','post_submit'] loop
  policy:=value->phase_name;
  if (select count(*) from jsonb_object_keys(policy))<>(case when phase_name='pre_submit' then 4 else 3 end)
     or policy->>'schema_version'<>'external_'||phase_name||'_policy.v1'
     or public.guide_proposal_hash(policy-'policy_sha256')<>policy->>'policy_sha256'
     or jsonb_typeof(policy->'entries')<>'array' then
   raise exception 'external checker phase policy mismatch' using errcode='23514';
  end if;
  if phase_name='pre_submit' and policy->'workstream_default' is distinct from
     jsonb_build_object('checker_id','workstream.default','checker_version','v1',
       'behavior_sha256','sha256:af2c604f792c4456d3b222036c772161b1503eace65ff90c3d3a23d9d348c28f')
  then raise exception 'Workstream default checker identity mismatch' using errcode='23514';
  end if;
  prior_requirement:=null; prior_capability:=null; prior_version:=null;
  for binding in select item from jsonb_array_elements(policy->'entries') item loop
   if jsonb_typeof(binding)<>'object' or (select count(*) from jsonb_object_keys(binding))<>5
      or binding->>'stage'<>phase_name
      or jsonb_typeof(binding->'configuration')<>'object'
      or public.external_checker_registry_digest(binding->'configuration')
         <>binding->>'configuration_sha256' then
    raise exception 'external checker policy binding mismatch' using errcode='23514';
   end if;
   registry:=binding->'registry';
   if jsonb_typeof(registry)<>'object' or (select count(*) from jsonb_object_keys(registry))<>14 then
    raise exception 'external checker registry value mismatch' using errcode='23514';
   end if;
   select * into registry_row from public.external_checker_registry_entries
    where id=(registry->>'registry_entry_id')::uuid
      and entry_digest=registry->>'entry_digest';
   if not found
      or registry_row.capability_id<>registry->>'capability_id'
      or registry_row.capability_version<>registry->>'capability_version'
      or registry_row.phase<>registry->>'phase'
      or registry_row.phase<>phase_name
      or registry_row.image_digest<>registry->>'image_digest'
      or registry_row.registration_operation_id<>(registry->>'registration_operation_id')::uuid
      or registry_row.registered_by_actor_profile_id<>(registry->>'registered_by_actor_profile_id')::uuid
      or registry_row.authorization_decision_event_id<>(registry->>'authorization_decision_event_id')::uuid
      or registry_row.created_at<>(registry->>'created_at')::timestamptz
      or registry->'configuration_schema' is distinct from jsonb_build_object(
        'schema_id',registry_row.configuration_schema_id,
        'schema_version',registry_row.configuration_schema_version,
        'document',registry_row.configuration_schema_document,
        'schema_sha256',registry_row.configuration_schema_sha256)
      or registry->'input_schema' is distinct from jsonb_build_object(
        'schema_id',registry_row.input_schema_id,
        'schema_version',registry_row.input_schema_version,
        'document',registry_row.input_schema_document,
        'schema_sha256',registry_row.input_schema_sha256)
      or registry->'output_schema' is distinct from jsonb_build_object(
        'schema_id',registry_row.output_schema_id,
        'schema_version',registry_row.output_schema_version,
        'document',registry_row.output_schema_document,
        'schema_sha256',registry_row.output_schema_sha256)
      or registry->'resources' is distinct from jsonb_build_object(
        'cpu_millis',registry_row.cpu_millis,
        'memory_bytes',registry_row.memory_bytes,
        'deadline_ms',registry_row.deadline_ms,
        'maximum_output_bytes',registry_row.maximum_output_bytes)
   then raise exception 'external checker registry custody mismatch' using errcode='23514';
   end if;
   if (prior_requirement,prior_capability,prior_version) is not null
         and row(binding->>'requirement_id',registry_row.capability_id,
                 registry_row.capability_version)
             <= row(prior_requirement,prior_capability,prior_version)
   then raise exception 'external checker policy order mismatch' using errcode='23514';
   end if;
   prior_requirement:=binding->>'requirement_id';
   prior_capability:=registry_row.capability_id;
   prior_version:=registry_row.capability_version;
  end loop;
 end loop;
 return true;
exception when sqlstate '23514' then raise;
 when others then
  raise exception 'external checker policy value is invalid' using errcode='23514';
end $$
""")
    definition = op.get_bind().execute(sa.text(
        "select pg_get_functiondef('public.require_guide_proposal_approval()'::regprocedure)"
    )).scalar_one()
    declaration = "        prior project_guide_proposal_approvals%rowtype;"
    if definition.count(declaration) != 1:
        raise RuntimeError("guide approval declaration shape changed")
    definition = definition.replace(
        declaration, declaration + "\n        external_plan boolean;"
    )
    anchor = """        IF a.operation_id IS NULL THEN
          RAISE EXCEPTION 'immutable proposal approval operation missing' USING ERRCODE='23514';
        END IF;"""
    if definition.count(anchor) != 1:
        raise RuntimeError("guide approval operation guard shape changed")
    definition = definition.replace(
        anchor,
        anchor + """
        external_plan:=a.effective_pre_submit_plan::jsonb->>'schema_version'
          ='external_checker_policies.v1';""",
    )
    selected_pre = """        SELECT * INTO pre FROM pre_submit_checker_policies WHERE id=a.pre_submit_policy_id;"""
    if definition.count(selected_pre) != 1:
        raise RuntimeError("guide approval pre policy lookup shape changed")
    definition = definition.replace(
        selected_pre,
        selected_pre + """
        IF external_plan AND pre.compiled_bundle::jsonb IS DISTINCT FROM
             a.effective_pre_submit_plan::jsonb->'pre_submit' THEN
          RAISE EXCEPTION 'external proposal PRE policy custody mismatch' USING ERRCODE='23514';
        END IF;
        IF external_plan AND NOT public.external_checker_locked_policies_valid(
             a.effective_pre_submit_plan::jsonb,a.effective_pre_submit_plan_hash) THEN
          RAISE EXCEPTION 'external proposal policy custody mismatch' USING ERRCODE='23514';
        END IF;""",
    )
    old_hashes = """           OR guide_proposal_hash(pre.compiled_bundle::jsonb) IS DISTINCT FROM pre.compiled_bundle_hash
           OR guide_proposal_hash(a.effective_pre_submit_plan::jsonb) IS DISTINCT FROM a.effective_pre_submit_plan_hash"""
    new_hashes = """           OR (NOT external_plan AND (
             guide_proposal_hash(pre.compiled_bundle::jsonb) IS DISTINCT FROM pre.compiled_bundle_hash
             OR guide_proposal_hash(a.effective_pre_submit_plan::jsonb) IS DISTINCT FROM a.effective_pre_submit_plan_hash))
           OR (external_plan AND (
             pre.compiled_bundle::jsonb IS DISTINCT FROM a.effective_pre_submit_plan::jsonb->'pre_submit'
             OR NOT public.external_checker_locked_policies_valid(
               a.effective_pre_submit_plan::jsonb,a.effective_pre_submit_plan_hash)))"""
    if definition.count(old_hashes) != 1:
        raise RuntimeError("guide approval plan digest shape changed")
    definition = definition.replace(old_hashes, new_hashes)
    old_plan = """           OR a.effective_pre_submit_plan::jsonb->'lineage' IS DISTINCT FROM jsonb_build_object(
             'project_id',a.project_id,'guide_id',a.guide_id,
             'guide_version',a.target_json->>'guide_version',
             'source_snapshot_id',a.target_json->>'source_snapshot_id',
             'source_snapshot_hash',a.target_json->>'source_snapshot_hash',
             'effective_policy_id',e.id,'effective_policy_hash',e.effective_policy_hash,
             'pre_submit_policy_id',pre.id,'pre_submit_policy_bundle_hash',pre.compiled_bundle_hash)
           OR a.effective_pre_submit_plan::jsonb->'catalogue' IS DISTINCT FROM jsonb_build_object(
             'id',a.target_json->>'pre_catalogue_id','version',a.target_json->>'pre_catalogue_version',
             'schema_version',a.target_json->>'pre_catalogue_schema_version',
             'manifest_sha256',a.target_json->>'pre_catalogue_manifest_hash')"""
    new_plan = """           OR (NOT external_plan AND (
             a.effective_pre_submit_plan::jsonb->'lineage' IS DISTINCT FROM jsonb_build_object(
               'project_id',a.project_id,'guide_id',a.guide_id,
               'guide_version',a.target_json->>'guide_version',
               'source_snapshot_id',a.target_json->>'source_snapshot_id',
               'source_snapshot_hash',a.target_json->>'source_snapshot_hash',
               'effective_policy_id',e.id,'effective_policy_hash',e.effective_policy_hash,
               'pre_submit_policy_id',pre.id,'pre_submit_policy_bundle_hash',pre.compiled_bundle_hash)
             OR a.effective_pre_submit_plan::jsonb->'catalogue' IS DISTINCT FROM jsonb_build_object(
               'id',a.target_json->>'pre_catalogue_id','version',a.target_json->>'pre_catalogue_version',
               'schema_version',a.target_json->>'pre_catalogue_schema_version',
               'manifest_sha256',a.target_json->>'pre_catalogue_manifest_hash')))"""
    if definition.count(old_plan) != 1:
        raise RuntimeError("guide approval legacy plan binding shape changed")
    op.execute(definition.replace(old_plan, new_plan))


def _replace_post_policy_custody() -> None:
    definition = op.get_bind().execute(sa.text(
        "select pg_get_functiondef('public.require_post_policy_operation()'::regprocedure)"
    )).scalar_one()
    old_policy = """         OR p.policy_hash IS DISTINCT FROM guide_proposal_hash(p.policy_body::jsonb)
         OR p.policy_body->>'catalogue_manifest_sha256' IS DISTINCT FROM t->'proposal'->>'post_catalogue_manifest_hash'"""
    new_policy = """         OR (p.policy_body->>'schema_version'='external_post_submit_policy.v1' AND (
           p.policy_hash IS DISTINCT FROM p.policy_body->>'policy_sha256'
           OR p.policy_hash IS DISTINCT FROM guide_proposal_hash(
             p.policy_body::jsonb-'policy_sha256')
           OR p.policy_body::jsonb IS DISTINCT FROM
             a.effective_pre_submit_plan::jsonb->'post_submit'))
         OR (p.policy_body->>'schema_version'<>'external_post_submit_policy.v1' AND (
           p.policy_hash IS DISTINCT FROM guide_proposal_hash(p.policy_body::jsonb)
           OR p.policy_body->>'catalogue_manifest_sha256' IS DISTINCT FROM
             t->'proposal'->>'post_catalogue_manifest_hash'))"""
    if definition.count(old_policy) != 1:
        raise RuntimeError("post policy custody shape changed")
    op.execute(definition.replace(old_policy, new_policy))


def _replace_checker_run_custody() -> None:
    definition = op.get_bind().execute(sa.text(
        "select pg_get_functiondef('public.protect_checker_run_custody()'::regprocedure)"
    )).scalar_one()
    declaration = "    DECLARE body jsonb; source submissions; mutable text[];"
    if definition.count(declaration) != 1:
        raise RuntimeError("checker run custody declaration shape changed")
    definition = definition.replace(
        declaration,
        "    DECLARE body jsonb; source submissions; mutable text[]; selected boolean;",
    )
    body_anchor = "      body := NEW.request_json::jsonb;"
    if definition.count(body_anchor) != 1:
        raise RuntimeError("checker run request body shape changed")
    definition = definition.replace(
        body_anchor,
        body_anchor + "\n      selected := body->>'schema_version'="
        "'workstream.selected_post_submit_request.v1';",
    )
    old_policy = """          OR source.locked_post_submit_checker_policy_body::jsonb IS DISTINCT FROM body->'policy'
          OR body->>'project_id' IS DISTINCT FROM NEW.project_id::text"""
    new_policy = """          OR (NOT selected AND (
            source.locked_post_submit_checker_policy_body::jsonb IS DISTINCT FROM body->'policy'
            OR NEW.selected_post_submit_policy_sha256 IS NOT NULL
            OR NEW.selected_post_submit_policy_body IS NOT NULL))
          OR (selected AND (
            source.selected_post_submit_policy_body::jsonb IS DISTINCT FROM body->'policy'
            OR source.selected_post_submit_policy_sha256 IS DISTINCT FROM
              body#>>'{expected_context,selected_post_policy_hash}'
            OR NEW.selected_post_submit_policy_body::jsonb IS DISTINCT FROM body->'policy'
            OR NEW.selected_post_submit_policy_sha256 IS DISTINCT FROM
              body#>>'{expected_context,selected_post_policy_hash}'))
          OR body->>'project_id' IS DISTINCT FROM NEW.project_id::text"""
    if definition.count(old_policy) != 1:
        raise RuntimeError("checker run policy body shape changed")
    definition = definition.replace(old_policy, new_policy)
    old_context = """          OR body#>>'{expected_context,post_policy_id}' IS DISTINCT FROM NEW.locked_post_submit_checker_policy_id::text
          OR body#>>'{expected_context,post_policy_version}' IS DISTINCT FROM NEW.locked_post_submit_checker_policy_version
          OR body#>>'{expected_context,post_policy_hash}' IS DISTINCT FROM NEW.locked_post_submit_checker_policy_hash"""
    new_context = """          OR (NOT selected AND (
            body#>>'{expected_context,post_policy_id}' IS DISTINCT FROM
              NEW.locked_post_submit_checker_policy_id::text
            OR body#>>'{expected_context,post_policy_version}' IS DISTINCT FROM
              NEW.locked_post_submit_checker_policy_version
            OR body#>>'{expected_context,post_policy_hash}' IS DISTINCT FROM
              NEW.locked_post_submit_checker_policy_hash))
          OR (selected AND (
            body#>>'{expected_context,retained_catalogue_policy_id}' IS DISTINCT FROM
              NEW.locked_post_submit_checker_policy_id::text
            OR body#>>'{expected_context,retained_catalogue_policy_version}' IS DISTINCT FROM
              NEW.locked_post_submit_checker_policy_version
            OR body#>>'{expected_context,retained_catalogue_policy_hash}' IS DISTINCT FROM
              NEW.locked_post_submit_checker_policy_hash))"""
    if definition.count(old_context) != 1:
        raise RuntimeError("checker run locked context shape changed")
    op.execute(definition.replace(old_context, new_context))


def _replace_submission_dispatch_custody() -> None:
    definition = op.get_bind().execute(sa.text(
        "select pg_get_functiondef('public.submission_dispatch_valid(public.submission_dispatches)'::regprocedure)"
    )).scalar_one()
    old_packet = """  AND (r.request_json::jsonb->'structural_input'->>'summary')=s.summary
  AND (r.request_json::jsonb->'structural_input'->>'worker_attestation')=s.worker_attestation"""
    new_packet = """  AND ((r.request_json::jsonb->>'schema_version'=
    'workstream.selected_post_submit_request.v1'
    AND r.selected_post_submit_policy_sha256=s.selected_post_submit_policy_sha256
    AND r.selected_post_submit_policy_body::jsonb=s.selected_post_submit_policy_body::jsonb
    AND r.request_json::jsonb->'policy'=s.selected_post_submit_policy_body::jsonb)
   OR (r.request_json::jsonb->>'schema_version'<>
    'workstream.selected_post_submit_request.v1'
    AND (r.request_json::jsonb->'structural_input'->>'summary')=s.summary
    AND (r.request_json::jsonb->'structural_input'->>'worker_attestation')=s.worker_attestation))"""
    if definition.count(old_packet) != 1:
        raise RuntimeError("submission dispatch packet custody shape changed")
    op.execute(definition.replace(old_packet, new_packet))


def _replace_submission_packet_custody() -> None:
    definition = op.get_bind().execute(sa.text(
        "select pg_get_functiondef('public.validate_submission_packet_custody()'::regprocedure)"
    )).scalar_one()
    old_lookup = """    SELECT evidence.packet_sha256 INTO expected_packet
      FROM public.submission_bundle_admissions AS admission
      JOIN public.pre_submit_evidence_sets AS evidence
        ON evidence.id = admission.pre_submit_evidence_set_id
     WHERE admission.id = stored.submission_bundle_admission_id;"""
    new_lookup = """    SELECT coalesce(evidence.packet_sha256,admission.packet_sha256)
      INTO expected_packet
      FROM public.submission_bundle_admissions AS admission
      LEFT JOIN public.pre_submit_evidence_sets AS evidence
        ON evidence.id = admission.pre_submit_evidence_set_id
     WHERE admission.id = stored.submission_bundle_admission_id;"""
    if definition.count(old_lookup) != 1:
        raise RuntimeError("submission packet custody lookup shape changed")
    op.execute(definition.replace(old_lookup, new_lookup))


def upgrade() -> None:
    op.execute("set local search_path=pg_catalog,public,pg_temp")
    op.execute("lock table public.actor_profiles, public.actor_identity_links, public.audit_events, public.submissions, public.checker_runs, public.submission_bundle_durable_intents, public.submission_bundle_admissions in access exclusive mode")
    _extend_authority_vocabulary()
    _create_selected_run_table()
    _alter_selected_lineage()
    _replace_admission_guards()
    _selected_run_guards()
    _replace_guide_approval_custody()
    _replace_post_policy_custody()
    _replace_checker_run_custody()
    _replace_submission_dispatch_custody()
    _replace_submission_packet_custody()


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
