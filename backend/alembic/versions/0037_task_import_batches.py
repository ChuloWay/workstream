"""Install atomic JSON-to-DRAFT Task import custody."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0037_task_import_batches"
down_revision = "0036_selected_checker_flow"
branch_labels = None
depends_on = None


_TABLES = (
    "task_import_batches",
    "task_import_batch_members",
    "task_import_batch_command_receipts",
)


def _definition(table: str, name: str) -> str:
    return op.get_bind().execute(sa.text(
        "select pg_catalog.pg_get_constraintdef(oid) from pg_catalog.pg_constraint "
        "where conrelid=cast(:table as regclass) and conname=:name"
    ), {"table": f"public.{table}", "name": name}).scalar_one()


def _replace_constraint(table: str, name: str, definition: str) -> None:
    op.execute(f"alter table public.{table} drop constraint {name}")
    op.execute(f"alter table public.{table} add constraint {name} {definition}")


def _replace_function(signature: str, old: str, new: str) -> None:
    body = op.get_bind().execute(sa.text(
        "select pg_catalog.pg_get_functiondef(cast(:signature as regprocedure))"
    ), {"signature": signature}).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError(f"atomic task import function shape changed: {signature}")
    op.execute(body.replace(old, new))


def _extend_audit_contract() -> None:
    name = "ck_audit_events_authorization_action_evidence"
    definition = _definition("audit_events", name)
    anchor = (
        "(((action_id)::text = 'project.task.create'::text) AND "
        "((permission_id)::text = 'project.task.manage'::text))"
    )
    additions = " OR ".join(
        "(((action_id)::text = "
        f"'{action}'::text) AND ((permission_id)::text = 'project.task.manage'::text))"
        for action in ("project.task.import", "project.task.import_batch.read")
    )
    if definition.count(anchor) != 2 or "project.task.import_batch.read" in definition:
        raise RuntimeError("atomic task import audit action constraint shape changed")
    _replace_constraint("audit_events", name, definition.replace(anchor, anchor + " OR " + additions))

    name = "ck_audit_events_authority_privacy_bounds"
    definition = _definition("audit_events", name)
    if "'task_import_batch'::character varying" in definition:
        raise RuntimeError("atomic task import audit target constraint already changed")
    resource_start = definition.index("resource_type IS NULL")
    target_start = definition.index("target_ref_kind IS NULL")
    addition = "('task_import_batch'::character varying)::text, "
    for start in sorted((resource_start, target_start), reverse=True):
        index = definition.index("ARRAY[", start) + len("ARRAY[")
        definition = definition[:index] + addition + definition[index:]
    _replace_constraint("audit_events", name, definition)


def _alter_tasks() -> None:
    duplicate = op.get_bind().execute(sa.text(
        "select project_id, external_task_id, count(*) from public.workstream_tasks "
        "where external_task_id is not null group by project_id, external_task_id "
        "having count(*) > 1 order by project_id, external_task_id limit 1"
    )).first()
    if duplicate is not None:
        raise RuntimeError(
            "cannot install atomic task import uniqueness with retained duplicate "
            f"project/external_task_id facts: {duplicate[0]}/{duplicate[1]}"
        )
    op.alter_column(
        "workstream_tasks", "difficulty", schema="public",
        existing_type=sa.String(50), type_=sa.String(80), existing_nullable=True,
    )
    op.create_unique_constraint(
        "uq_workstream_tasks_project_external_id",
        "workstream_tasks", ["project_id", "external_task_id"], schema="public",
    )
    _replace_function(
        "public.guard_task_management_audit()",
        "payload->>'source_type' in ('manual','markdown_import','csv_import')",
        "payload->>'source_type' in ('manual','markdown_import','csv_import','json_import')",
    )


def _create_tables() -> None:
    op.create_table(
        "task_import_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("creation_command_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(71), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("mapping_version", sa.String(80), nullable=False),
        sa.Column("manifest_digest", sa.String(71), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("metadata_label", sa.String(255), nullable=True),
        sa.Column("actor_profile_id", sa.Uuid(), nullable=False),
        sa.Column("identity_link_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_decision_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_operation_identity", sa.String(71), nullable=False),
        sa.Column("put_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("content_id", sa.Uuid(), nullable=True),
        sa.Column("replica_id", sa.Uuid(), nullable=True),
        sa.Column("verification_job_id", sa.Uuid(), nullable=True),
        sa.Column("verification_generation", sa.BigInteger(), nullable=True),
        sa.Column("verification_receipt_id", sa.Uuid(), nullable=True),
        sa.Column("operation_receipt_id", sa.Uuid(), nullable=True),
        sa.Column("observation_receipt_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_task_import_batches"),
        sa.UniqueConstraint("project_id", "sha256", "byte_count", name="uq_task_import_batch_file"),
        sa.UniqueConstraint("id", "project_id", name="uq_task_import_batch_project"),
        sa.UniqueConstraint("creation_command_receipt_id", name="uq_task_import_batch_creation_command"),
        sa.ForeignKeyConstraint(["project_id"], ["public.projects.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["actor_profile_id"], ["public.actor_profiles.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["identity_link_id", "actor_profile_id"], ["public.actor_identity_links.id", "public.actor_identity_links.actor_profile_id"], name="fk_task_import_batch_actor_link", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["authorization_decision_id"], ["public.audit_events.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["source_id", "project_id", "sha256", "byte_count", "media_type"], ["public.artifact_task_import_sources.id", "public.artifact_task_import_sources.project_id", "public.artifact_task_import_sources.sha256", "public.artifact_task_import_sources.byte_count", "public.artifact_task_import_sources.media_type"], name="fk_task_import_batch_source", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["put_attempt_id"], ["public.artifact_put_attempts.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["content_id"], ["public.artifact_contents.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["replica_id"], ["public.artifact_replicas.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["verification_job_id"], ["public.artifact_verification_jobs.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["verification_receipt_id"], ["public.artifact_verification_receipts.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["operation_receipt_id"], ["public.artifact_operation_receipts.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["observation_receipt_id"], ["public.artifact_put_observation_receipts.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.CheckConstraint("(get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128", name="ck_task_import_batches_id_uuid7"),
        sa.CheckConstraint("sha256 ~ '^sha256:[0-9a-f]{64}$'", name="ck_task_import_batches_source_hash"),
        sa.CheckConstraint("source_operation_identity ~ '^sha256:[0-9a-f]{64}$'", name="ck_task_import_batches_source_operation"),
        sa.CheckConstraint("manifest_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_task_import_batches_manifest_hash"),
        sa.CheckConstraint("byte_count between 1 and 8388608 and row_count between 1 and 500", name="ck_task_import_batches_bounds"),
        sa.CheckConstraint("media_type='application/json' and schema_version='workstream.task_import.v1' and mapping_version='workstream.task_import.draft_mapping.v1'", name="ck_task_import_batches_format"),
        sa.CheckConstraint("(status='pending' and response is null and authorization_decision_id is null and committed_at is null) or (status='committed' and response is not null and jsonb_typeof(response::jsonb)='object' and authorization_decision_id is not null and committed_at is not null and put_attempt_id is not null and content_id is not null and replica_id is not null and verification_job_id is not null and verification_generation is not null and verification_generation>0 and verification_receipt_id is not null and ((operation_receipt_id is not null and observation_receipt_id is null) or (operation_receipt_id is null and observation_receipt_id is not null)))", name="ck_task_import_batches_state_shape"),
        schema="public",
    )
    op.create_table(
        "task_import_batch_command_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_profile_id", sa.Uuid(), nullable=False),
        sa.Column("identity_link_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.String(160), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(71), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("authorization_decision_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_operation_identity", sa.String(71), nullable=False),
        sa.Column("put_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("content_id", sa.Uuid(), nullable=True),
        sa.Column("replica_id", sa.Uuid(), nullable=True),
        sa.Column("verification_job_id", sa.Uuid(), nullable=True),
        sa.Column("verification_generation", sa.BigInteger(), nullable=True),
        sa.Column("verification_receipt_id", sa.Uuid(), nullable=True),
        sa.Column("operation_receipt_id", sa.Uuid(), nullable=True),
        sa.Column("observation_receipt_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_task_import_batch_command_receipts"),
        sa.UniqueConstraint("actor_profile_id", "action_id", "idempotency_key", name="uq_task_import_command_namespace"),
        sa.ForeignKeyConstraint(["project_id"], ["public.projects.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["actor_profile_id"], ["public.actor_profiles.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["identity_link_id", "actor_profile_id"], ["public.actor_identity_links.id", "public.actor_identity_links.actor_profile_id"], name="fk_task_import_command_actor_link", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["authorization_decision_id"], ["public.audit_events.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["source_id", "project_id", "sha256", "byte_count", "media_type"], ["public.artifact_task_import_sources.id", "public.artifact_task_import_sources.project_id", "public.artifact_task_import_sources.sha256", "public.artifact_task_import_sources.byte_count", "public.artifact_task_import_sources.media_type"], name="fk_task_import_command_source", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["put_attempt_id"], ["public.artifact_put_attempts.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["content_id"], ["public.artifact_contents.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["replica_id"], ["public.artifact_replicas.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["verification_job_id"], ["public.artifact_verification_jobs.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["verification_receipt_id"], ["public.artifact_verification_receipts.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["operation_receipt_id"], ["public.artifact_operation_receipts.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["observation_receipt_id"], ["public.artifact_put_observation_receipts.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.CheckConstraint("(get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128", name="ck_task_import_batch_command_receipts_id_uuid7"),
        sa.CheckConstraint("action_id='project.task.import'", name="ck_task_import_batch_command_receipts_action"),
        sa.CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_task_import_batch_command_receipts_request_hash"),
        sa.CheckConstraint("sha256 ~ '^sha256:[0-9a-f]{64}$' and source_operation_identity ~ '^sha256:[0-9a-f]{64}$'", name="ck_task_import_batch_command_receipts_source_hash"),
        sa.CheckConstraint("byte_count between 1 and 8388608 and media_type='application/json'", name="ck_task_import_batch_command_receipts_bounds"),
        sa.CheckConstraint("(status='pending' and response is null and authorization_decision_id is null and committed_at is null) or (status='committed' and batch_id is not null and response is not null and jsonb_typeof(response::jsonb)='object' and authorization_decision_id is not null and committed_at is not null and put_attempt_id is not null and content_id is not null and replica_id is not null and verification_job_id is not null and verification_generation is not null and verification_generation>0 and verification_receipt_id is not null and ((operation_receipt_id is not null and observation_receipt_id is null) or (operation_receipt_id is null and observation_receipt_id is not null)))", name="ck_task_import_batch_command_receipts_state_shape"),
        schema="public",
    )
    op.create_foreign_key(
        "fk_task_import_batch_creation_command", "task_import_batches",
        "task_import_batch_command_receipts", ["creation_command_receipt_id"], ["id"],
        source_schema="public", referent_schema="public", ondelete="RESTRICT",
        deferrable=True, initially="DEFERRED",
    )
    op.create_foreign_key(
        "fk_task_import_command_batch", "task_import_batch_command_receipts",
        "task_import_batches", ["batch_id", "project_id"], ["id", "project_id"],
        source_schema="public", referent_schema="public", ondelete="RESTRICT",
        deferrable=True, initially="DEFERRED",
    )
    op.create_table(
        "task_import_batch_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("external_task_id", sa.String(200), nullable=False),
        sa.Column("row_digest", sa.String(71), nullable=False),
        sa.Column("create_idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("task_command_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_decision_id", sa.Uuid(), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_task_import_batch_members"),
        sa.UniqueConstraint("task_id", name="uq_task_import_member_task"),
        sa.UniqueConstraint("batch_id", "row_index", name="uq_task_import_member_row"),
        sa.UniqueConstraint("project_id", "external_task_id", name="uq_task_import_member_external_id"),
        sa.UniqueConstraint("task_command_receipt_id", name="uq_task_import_member_creation"),
        sa.ForeignKeyConstraint(["batch_id", "project_id"], ["public.task_import_batches.id", "public.task_import_batches.project_id"], name="fk_task_import_member_batch", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["task_id", "project_id"], ["public.workstream_tasks.id", "public.workstream_tasks.project_id"], name="fk_task_import_member_task", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["task_command_receipt_id"], ["public.task_command_receipts.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["authorization_decision_id"], ["public.audit_events.id"], ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
        sa.CheckConstraint("(get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128", name="ck_task_import_batch_members_id_uuid7"),
        sa.CheckConstraint("row_index between 0 and 499", name="ck_task_import_batch_members_row_index"),
        sa.CheckConstraint("row_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_task_import_batch_members_row_hash"),
        sa.CheckConstraint("jsonb_typeof(response::jsonb)='object'", name="ck_task_import_batch_members_response_shape"),
        schema="public",
    )


def _create_custody_functions() -> None:
    op.execute(r"""
create function public.task_import_binding_valid(
 expected_source_id uuid, expected_project_id uuid, expected_sha256 text,
 expected_byte_count bigint, expected_operation_identity text,
 expected_put_attempt_id uuid, expected_content_id uuid, expected_replica_id uuid,
 expected_verification_job_id uuid, expected_verification_generation bigint,
 expected_verification_receipt_id uuid, expected_operation_receipt_id uuid,
 expected_observation_receipt_id uuid
) returns boolean language sql stable set search_path=pg_catalog,public,pg_temp as $$
 select exists(
  select 1 from public.artifact_task_import_sources s
  join public.artifact_put_attempts a on a.id=expected_put_attempt_id and a.task_import_source_id=s.id
  join public.artifact_replicas r on r.id=expected_replica_id and r.id=a.replica_id
  join public.artifact_contents c on c.id=expected_content_id and c.id=r.content_id
  join public.artifact_verification_jobs j on j.id=expected_verification_job_id
    and j.originating_put_attempt_id=a.id and j.replica_id=r.id
  join public.artifact_verification_receipts v on v.id=expected_verification_receipt_id
    and v.verification_job_id=j.id and v.outcome='verified'
  where s.id=expected_source_id and s.project_id=expected_project_id and s.sha256=expected_sha256
    and s.byte_count=expected_byte_count and s.operation_identity=expected_operation_identity
    and a.producer_request_type='task_import_source' and a.logical_role='task_import_source'
    and a.project_id=s.project_id and a.sha256=s.sha256 and a.byte_count=s.byte_count
    and a.media_type=s.media_type and c.sha256=s.sha256 and c.byte_count=s.byte_count
    and r.storage_namespace_id=a.storage_namespace_id
    and r.namespace_fingerprint=a.namespace_fingerprint
    and v.execution_generation=expected_verification_generation
    and v.observed_sha256=s.sha256 and v.observed_byte_count=s.byte_count
    and ((expected_operation_receipt_id is not null and expected_observation_receipt_id is null and exists(
      select 1 from public.artifact_operation_receipts o where o.id=expected_operation_receipt_id
      and o.put_attempt_id=a.id and o.replica_id=r.id and o.request_digest=a.request_digest
      and o.provider_object_ref=r.provider_object_ref and o.logical_role='task_import_source'
      and o.outcome='stored_pending_verification')) or
     (expected_operation_receipt_id is null and expected_observation_receipt_id is not null and exists(
      select 1 from public.artifact_put_observation_receipts o where o.id=expected_observation_receipt_id
      and o.put_attempt_id=a.id and o.outcome='observed_confirmed'
      and o.observed_sha256=s.sha256 and o.expected_sha256=s.sha256
      and o.observed_byte_count=s.byte_count and o.expected_byte_count=s.byte_count)))
 )
$$
""")
    op.execute(r"""
create function public.task_import_binding_digest(
 expected_source_id uuid, expected_project_id uuid, expected_sha256 text,
 expected_byte_count bigint, expected_operation_identity text,
 expected_put_attempt_id uuid, expected_content_id uuid, expected_replica_id uuid,
 expected_verification_job_id uuid, expected_verification_generation bigint,
 expected_verification_receipt_id uuid, expected_operation_receipt_id uuid,
 expected_observation_receipt_id uuid
) returns text language sql immutable set search_path=pg_catalog,public,pg_temp as $$
 select public.external_checker_registry_digest(pg_catalog.jsonb_build_object(
  'source_id',expected_source_id,'project_id',expected_project_id,'sha256',expected_sha256,
  'byte_count',expected_byte_count,'operation_identity',expected_operation_identity,
  'put_attempt_id',expected_put_attempt_id,'content_id',expected_content_id,
  'replica_id',expected_replica_id,'verification_job_id',expected_verification_job_id,
  'verification_generation',expected_verification_generation,
  'verification_receipt_id',expected_verification_receipt_id,
  'operation_receipt_id',expected_operation_receipt_id,
  'observation_receipt_id',expected_observation_receipt_id))
$$
""")
    op.execute(r"""
create function public.task_import_authority_valid(
 expected_decision_id uuid, expected_action text, expected_batch_id uuid,
 expected_project_id uuid, expected_source_id uuid, expected_actor_id uuid,
 expected_link_id uuid, expected_sha256 text, expected_byte_count bigint,
 expected_row_count integer, expected_manifest_digest text,
 expected_source_binding_digest text, expected_idempotency_key uuid,
 expected_request_digest text
) returns boolean language sql stable set search_path=pg_catalog,public,pg_temp as $$
 select exists(select 1 from public.audit_events a where a.id=expected_decision_id
  and a.event_domain='authority' and a.event_type='SensitiveAuthorizationAllowed'
  and a.actor_ref_kind='actor_profile' and a.actor_id=expected_actor_id::text
  and a.project_id=expected_project_id and a.action_id=expected_action
  and a.permission_id='project.task.manage'
  and a.resource_type='task_import_batch' and a.resource_id=expected_batch_id::text
  and a.target_ref_kind='task_import_batch' and a.target_ref_id=expected_batch_id::text
  and a.denial_code is null and a.after_facts::jsonb=pg_catalog.jsonb_build_object(
   'allowed',true,'resource_context_digest',public.external_checker_registry_digest(
    pg_catalog.jsonb_build_object('resource_context',pg_catalog.jsonb_build_object(
     'resource_type','task_import_batch','resource_id',expected_batch_id,
     'scope_project_id',expected_project_id,'source_id',expected_source_id,
     'actor_profile_id',expected_actor_id,'identity_link_id',expected_link_id,
     'sha256',expected_sha256,'byte_count',expected_byte_count,
     'row_count',expected_row_count,'manifest_digest',expected_manifest_digest,
     'source_binding_digest',expected_source_binding_digest,
     'idempotency_key',expected_idempotency_key,'request_digest',expected_request_digest)))))
$$
""")
    op.execute(r"""
create function public.validate_task_import_batch_custody(target uuid) returns void
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare b public.task_import_batches%rowtype; cmd public.task_import_batch_command_receipts%rowtype;
        members integer; manifest jsonb; binding_digest text;
begin
 select * into b from public.task_import_batches where id=target;
 if not found then return; end if;
 if b.status<>'committed' then raise exception 'task import batch cannot remain pending' using errcode='23514'; end if;
 select * into cmd from public.task_import_batch_command_receipts where id=b.creation_command_receipt_id;
 binding_digest:=public.task_import_binding_digest(b.source_id,b.project_id,b.sha256,b.byte_count,
  b.source_operation_identity,b.put_attempt_id,b.content_id,b.replica_id,b.verification_job_id,
  b.verification_generation,b.verification_receipt_id,b.operation_receipt_id,b.observation_receipt_id);
 if not public.task_import_binding_valid(b.source_id,b.project_id,b.sha256,b.byte_count,
      b.source_operation_identity,b.put_attempt_id,b.content_id,b.replica_id,b.verification_job_id,
      b.verification_generation,b.verification_receipt_id,b.operation_receipt_id,b.observation_receipt_id)
    or cmd.id is null or cmd.batch_id is distinct from b.id or cmd.project_id is distinct from b.project_id
    or cmd.actor_profile_id is distinct from b.actor_profile_id or cmd.identity_link_id is distinct from b.identity_link_id
    or cmd.source_id is distinct from b.source_id or cmd.response::jsonb is distinct from b.response::jsonb
    or not public.task_import_authority_valid(b.authorization_decision_id,'project.task.import',b.id,b.project_id,
      b.source_id,b.actor_profile_id,b.identity_link_id,b.sha256,b.byte_count,b.row_count,b.manifest_digest,
      binding_digest,cmd.idempotency_key,cmd.request_digest) then
  raise exception 'task import batch original custody invalid' using errcode='23514';
 end if;
 select count(*) into members from public.task_import_batch_members m where m.batch_id=b.id;
 if members<>b.row_count or exists(
  select 1 from generate_series(0,b.row_count-1) i where not exists(
   select 1 from public.task_import_batch_members m where m.batch_id=b.id and m.row_index=i)) then
  raise exception 'task import batch membership incomplete' using errcode='23514';
 end if;
 if b.response::jsonb->>'batch_id' is distinct from b.id::text
    or b.response::jsonb->>'project_id' is distinct from b.project_id::text
    or b.response::jsonb->>'source_id' is distinct from b.source_id::text
    or b.response::jsonb->>'sha256' is distinct from b.sha256
    or (b.response::jsonb->>'byte_count')::bigint is distinct from b.byte_count
    or (b.response::jsonb->>'row_count')::integer is distinct from b.row_count
    or b.response::jsonb->>'schema_version' is distinct from b.schema_version
    or b.response::jsonb->>'mapping_version' is distinct from b.mapping_version
    or (b.response::jsonb->>'created_at')::timestamptz is distinct from b.created_at
    or b.response::jsonb->'label' is distinct from coalesce(to_jsonb(b.metadata_label),'null'::jsonb)
    or pg_catalog.jsonb_array_length(b.response::jsonb->'tasks')<>b.row_count then
  raise exception 'task import batch response custody invalid' using errcode='23514';
 end if;
 if exists(select 1 from public.task_import_batch_members m
  join public.workstream_tasks t on t.id=m.task_id and t.project_id=m.project_id
  join public.task_command_receipts r on r.id=m.task_command_receipt_id
  where m.batch_id=b.id and (
   m.project_id is distinct from b.project_id or m.external_task_id is distinct from t.external_task_id
   or t.source_type<>'json_import' or t.source_ref is distinct from 'task-import-source:'||b.source_id::text
   or t.source_payload_hash is distinct from b.sha256 or t.import_batch_id is distinct from b.id::text
   or t.created_by is distinct from b.actor_profile_id::text
   or r.status<>'committed' or r.action_id<>'project.task.create' or r.task_id is distinct from m.task_id
   or r.actor_profile_id is distinct from b.actor_profile_id or r.idempotency_key is distinct from m.create_idempotency_key
   or r.response is distinct from m.response or m.response::jsonb is distinct from b.response::jsonb->'tasks'->m.row_index
   or m.response::jsonb->>'id' is distinct from m.task_id::text
   or m.response::jsonb->>'project_id' is distinct from b.project_id::text
   or m.response::jsonb->>'external_task_id' is distinct from m.external_task_id
   or m.response::jsonb->>'source_type'<>'json_import'
   or m.response::jsonb->>'source_ref' is distinct from 'task-import-source:'||b.source_id::text
   or m.response::jsonb->>'source_payload_hash' is distinct from b.sha256
   or m.response::jsonb->>'import_batch_id' is distinct from b.id::text
   or m.response::jsonb->>'created_by' is distinct from b.actor_profile_id::text
   or not exists(select 1 from public.audit_events e where e.id=m.authorization_decision_id
     and e.event_domain='authority' and e.event_type='SensitiveAuthorizationAllowed'
     and e.action_id='project.task.create' and e.permission_id='project.task.manage'
     and e.actor_id=b.actor_profile_id::text and e.project_id=b.project_id)
   or not exists(select 1 from public.audit_events e where e.event_type='TaskCreated'
     and e.entity_id=m.task_id and e.event_payload::jsonb#>>'{references,authorization_decision_id}'=m.authorization_decision_id::text)
  )) then raise exception 'task import batch member custody invalid' using errcode='23514'; end if;
 select pg_catalog.jsonb_build_object(
  'schema_version',b.schema_version,'metadata',pg_catalog.jsonb_build_object('label',b.metadata_label),
  'tasks',pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
   'external_task_id',m.response::jsonb->'external_task_id','title',m.response::jsonb->'title',
   'description',m.response::jsonb->'description','task_type',m.response::jsonb->'task_type',
   'difficulty',m.response::jsonb->'difficulty','skill_tags',m.response::jsonb->'skill_tags',
   'estimated_time_minutes',m.response::jsonb->'estimated_time_minutes',
   'acceptance_criteria',m.response::jsonb->'acceptance_criteria',
   'rejection_criteria',m.response::jsonb->'rejection_criteria') order by m.row_index)) into manifest
 from public.task_import_batch_members m where m.batch_id=b.id;
 if public.external_checker_registry_digest(manifest) is distinct from b.manifest_digest
    or exists(select 1 from public.task_import_batch_members m where m.batch_id=b.id and
      m.row_digest is distinct from public.external_checker_registry_digest(pg_catalog.jsonb_build_object(
       'external_task_id',m.response::jsonb->'external_task_id','title',m.response::jsonb->'title',
       'description',m.response::jsonb->'description','task_type',m.response::jsonb->'task_type',
       'difficulty',m.response::jsonb->'difficulty','skill_tags',m.response::jsonb->'skill_tags',
       'estimated_time_minutes',m.response::jsonb->'estimated_time_minutes',
       'acceptance_criteria',m.response::jsonb->'acceptance_criteria',
       'rejection_criteria',m.response::jsonb->'rejection_criteria'))) then
  raise exception 'task import batch manifest custody invalid' using errcode='23514';
 end if;
end
$$
""")
    op.execute(r"""
create function public.validate_task_import_command_custody(target uuid) returns void
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare c public.task_import_batch_command_receipts%rowtype; b public.task_import_batches%rowtype; binding_digest text;
begin
 select * into c from public.task_import_batch_command_receipts where id=target;
 if not found then return; end if;
 if c.status<>'committed' then raise exception 'task import command cannot remain pending' using errcode='23514'; end if;
 select * into b from public.task_import_batches where id=c.batch_id;
 binding_digest:=public.task_import_binding_digest(c.source_id,c.project_id,c.sha256,c.byte_count,
  c.source_operation_identity,c.put_attempt_id,c.content_id,c.replica_id,c.verification_job_id,
  c.verification_generation,c.verification_receipt_id,c.operation_receipt_id,c.observation_receipt_id);
 if b.id is null or c.response::jsonb is distinct from b.response::jsonb
    or c.sha256 is distinct from b.sha256 or c.byte_count is distinct from b.byte_count
    or not public.task_import_binding_valid(c.source_id,c.project_id,c.sha256,c.byte_count,
      c.source_operation_identity,c.put_attempt_id,c.content_id,c.replica_id,c.verification_job_id,
      c.verification_generation,c.verification_receipt_id,c.operation_receipt_id,c.observation_receipt_id)
    or not public.task_import_authority_valid(c.authorization_decision_id,'project.task.import',b.id,c.project_id,
      c.source_id,c.actor_profile_id,c.identity_link_id,c.sha256,c.byte_count,b.row_count,b.manifest_digest,
      binding_digest,c.idempotency_key,c.request_digest) then
  raise exception 'task import command custody invalid' using errcode='23514';
 end if;
end
$$
""")


def _create_guards() -> None:
    op.execute(r"""
create function public.guard_task_import_batch_mutation() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
begin
 if tg_op='UPDATE' and old.status='pending' and new.status='committed'
    and row(new.id,new.project_id,new.source_id,new.creation_command_receipt_id,new.sha256,new.byte_count,
      new.media_type,new.schema_version,new.mapping_version,new.manifest_digest,new.row_count,new.metadata_label,
      new.actor_profile_id,new.identity_link_id,new.created_at,new.source_operation_identity)
      is not distinct from row(old.id,old.project_id,old.source_id,old.creation_command_receipt_id,old.sha256,old.byte_count,
      old.media_type,old.schema_version,old.mapping_version,old.manifest_digest,old.row_count,old.metadata_label,
      old.actor_profile_id,old.identity_link_id,old.created_at,old.source_operation_identity) then return new; end if;
 raise exception 'task import batch custody is immutable' using errcode='55000';
end
$$
""")
    op.execute(r"""
create function public.guard_task_import_command_mutation() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
begin
 if tg_op='UPDATE' and old.status='pending' and new.status='committed'
    and row(new.id,new.actor_profile_id,new.identity_link_id,new.action_id,new.idempotency_key,new.request_digest,
      new.project_id,new.source_id,new.sha256,new.byte_count,new.media_type,new.created_at,new.source_operation_identity)
      is not distinct from row(old.id,old.actor_profile_id,old.identity_link_id,old.action_id,old.idempotency_key,old.request_digest,
      old.project_id,old.source_id,old.sha256,old.byte_count,old.media_type,old.created_at,old.source_operation_identity) then return new; end if;
 raise exception 'task import command custody is immutable' using errcode='55000';
end
$$
""")
    op.execute(r"""
create function public.reject_task_import_member_mutation() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$ begin
 raise exception 'task import member custody is immutable' using errcode='55000'; end $$
""")
    op.execute(r"""
create function public.reject_task_import_truncate() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$ begin
 raise exception 'task import custody cannot be truncated' using errcode='55000'; end $$
""")
    op.execute("create trigger task_import_batches_immutable before update or delete on public.task_import_batches for each row execute function public.guard_task_import_batch_mutation()")
    op.execute("create trigger task_import_batch_commands_immutable before update or delete on public.task_import_batch_command_receipts for each row execute function public.guard_task_import_command_mutation()")
    op.execute("create trigger task_import_batch_members_immutable before update or delete on public.task_import_batch_members for each row execute function public.reject_task_import_member_mutation()")
    for table in _TABLES:
        op.execute(f"create trigger {table}_no_truncate before truncate on public.{table} for each statement execute function public.reject_task_import_truncate()")
    op.execute("create constraint trigger task_import_batch_custody after insert or update on public.task_import_batches deferrable initially deferred for each row execute function public.trigger_validate_task_import_batch()")
    op.execute("create constraint trigger task_import_command_custody after insert or update on public.task_import_batch_command_receipts deferrable initially deferred for each row execute function public.trigger_validate_task_import_command()")
    op.execute("create constraint trigger task_import_member_custody after insert or update on public.task_import_batch_members deferrable initially deferred for each row execute function public.trigger_validate_task_import_member()")


def _create_trigger_wrappers() -> None:
    op.execute(r"""
create function public.trigger_validate_task_import_batch() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare final_status text;
begin
 select status into final_status from public.task_import_batches where id=new.id;
 if not found or final_status<>'committed' then
  raise exception 'task import batch cannot remain pending' using errcode='23514';
 end if;
 if new.status='committed' then
  perform public.validate_task_import_batch_custody(new.id);
 end if;
 return new;
end $$
""")
    op.execute(r"""
create function public.trigger_validate_task_import_command() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare final_status text;
begin
 select status into final_status from public.task_import_batch_command_receipts where id=new.id;
 if not found or final_status<>'committed' then
  raise exception 'task import command cannot remain pending' using errcode='23514';
 end if;
 if new.status='committed' then
  perform public.validate_task_import_command_custody(new.id);
 end if;
 return new;
end $$
""")
    op.execute(r"""
create function public.trigger_validate_task_import_member() returns trigger
language plpgsql set search_path=pg_catalog,public,pg_temp as $$
declare parent_status text; parent_xid xid;
begin
 select status,xmin into parent_status,parent_xid
 from public.task_import_batches where id=new.batch_id;
 if not found or parent_status<>'committed'
    or parent_xid<>pg_catalog.pg_current_xact_id()::xid then
  raise exception 'task import member must be committed with its batch root' using errcode='23514';
 end if;
 return new;
end $$
""")


def upgrade() -> None:
    """Install exact batch, member, replay, ART and AUTH closure."""
    op.execute("set local search_path=pg_catalog,public,pg_temp")
    op.execute(
        "lock table public.audit_events, public.workstream_tasks, public.task_command_receipts, "
        "public.artifact_task_import_sources in access exclusive mode"
    )
    _extend_audit_contract()
    _alter_tasks()
    _create_tables()
    _create_custody_functions()
    _create_trigger_wrappers()
    _create_guards()


def downgrade() -> None:
    """Refuse removal of retained native import custody."""
    op.execute("set local search_path=pg_catalog,public,pg_temp")
    op.execute(
        "lock table public.task_import_batches, public.task_import_batch_members, "
        "public.task_import_batch_command_receipts in access exclusive mode"
    )
    retained = op.get_bind().execute(sa.text(
        "select exists(select 1 from public.task_import_batches) or "
        "exists(select 1 from public.task_import_batch_members) or "
        "exists(select 1 from public.task_import_batch_command_receipts)"
    )).scalar_one()
    if retained:
        raise RuntimeError("cannot downgrade atomic task import with retained custody")
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
