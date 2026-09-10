"""Replace extracted guide execution with exact original-document runtime custody."""

from alembic import op
import sqlalchemy as sa

from scripts.schema_baseline_sql import split_sql_statements

revision = "0016_guide_document_runtime"
down_revision = "0015_guide_runtime_configuration"
branch_labels = None
depends_on = None

# These definitions are migration-local snapshots, independent of later app models.
_INTEGER_CONFIGURATION = {
    "timeout_seconds": (1, 7200), "request_timeout_seconds": (1, 1800),
    "maximum_retries": (0, 5), "retry_backoff_multiplier": (1, 4),
    "retry_initial_delay_seconds": (1, 30), "retry_max_delay_seconds": (1, 120),
    "circuit_failure_threshold": (1, 20), "circuit_cooldown_seconds": (1, 600),
    "maximum_manifest_bytes": (1024, 1000000), "maximum_documents": (1, 100),
    "maximum_document_bytes": (1, 536870912), "maximum_total_document_bytes": (1, None),
    "maximum_turns": (3, 100), "maximum_hosted_tool_calls": (3, 200),
    "compaction_threshold_tokens": (1000, 100000), "container_expiry_minutes": (10, 60),
    "file_expiry_seconds": (3600, 7200), "cleanup_timeout_seconds": (5, 120),
}
_RETIRED_TABLES = (
    "guide_source_artifact_bindings", "guide_source_format_classifications",
    "guide_source_extraction_attempts", "guide_source_extraction_retry_budgets",
    "guide_source_extracted_contents", "guide_source_extraction_usages",
    "guide_sufficiency_report_source_usages",
)


def _execute(sql: str) -> None:
    for statement in split_sql_statements(sql):
        op.execute(statement)


def upgrade() -> None:
    """Preserve retained evidence while closing superseded write/execution paths."""
    _retain_source_columns()
    _runtime_configuration_guard()
    _resource_tables()
    _resource_guards()
    _source_custody()
    _accepted_document_evidence()


def downgrade() -> None:
    """Never drop original-document access or retained setup evidence."""
    raise RuntimeError("guide document runtime downgrade would discard retained evidence")


def _replace_function(name: str, replacements: tuple[tuple[str, str], ...]) -> None:
    definition = op.get_bind().scalar(sa.text(
        "select pg_get_functiondef(cast(:name as regprocedure))"), {"name": name + "()"})
    for before, after in replacements:
        if definition.count(before) != 1:
            raise RuntimeError("guide source custody function shape changed")
        definition = definition.replace(before, after)
    _execute(definition)


def _retain_source_columns() -> None:
    op.alter_column("project_guides", "content_markdown",
                    new_column_name="retained_content_markdown", nullable=True)
    op.alter_column("project_setup_runs", "continuation_verification_job_id",
                    new_column_name="retained_continuation_verification_job_id")
    op.alter_column("project_setup_runs", "continuation_started_at",
                    new_column_name="retained_continuation_started_at")
    op.add_column("project_setup_runs", sa.Column("documents_ready_at", sa.DateTime(timezone=True)))
    _execute("""
      alter table project_setup_runs rename constraint fk_project_setup_runs_continuation_verification_job
        to fk_project_setup_runs_retained_continuation_verification_job;
      alter index ix_project_setup_runs_continuation_verification_job_id
        rename to ix_project_setup_runs_retained_continuation_verification_job_id;
    """)
    op.drop_constraint(op.f("ck_project_setup_runs_ck_project_setup_runs_status"), "project_setup_runs", type_="check")
    op.create_check_constraint(op.f("ck_project_setup_runs_ck_project_setup_runs_status"), "project_setup_runs",
        "status in ('awaiting_documents','queued','dispatch_pending','enqueue_failed',"
        "'enqueue_identity_mismatch','running_sufficiency_agent','sufficiency_blocked',"
        "'running_policy_derivation_agent','policy_draft_ready','running_post_submit_derivation_agent',"
        "'post_submit_setup_blocked','post_submit_policy_compiled','setup_blocked','failed')")
    op.drop_constraint(op.f("ck_artifact_operation_receipts_outcome"), "artifact_operation_receipts", type_="check")
    op.create_check_constraint(op.f("ck_artifact_operation_receipts_outcome"), "artifact_operation_receipts",
        "outcome in ('stored_pending_verification','document_stored')")
    op.create_check_constraint(op.f("ck_artifact_operation_receipts_document_outcome"), "artifact_operation_receipts",
        "outcome <> 'document_stored' or guide_source_item_id is not null")
    _execute("""
      create function guard_retained_guide_source_fields() returns trigger language plpgsql as $$
      begin
        if tg_table_name='project_guides' then
          if (tg_op='INSERT' and new.retained_content_markdown is not null)
             or (tg_op='UPDATE' and new.retained_content_markdown is distinct from old.retained_content_markdown) then
            raise exception 'retained guide content is read only' using errcode='23514';
          end if;
        else
          if (tg_op='INSERT' and (new.retained_continuation_verification_job_id is not null
               or new.retained_continuation_started_at is not null))
             or (tg_op='UPDATE' and (new.retained_continuation_verification_job_id,
                  new.retained_continuation_started_at) is distinct from
                 (old.retained_continuation_verification_job_id,old.retained_continuation_started_at)) then
            raise exception 'retained guide continuation is read only' using errcode='23514';
          end if;
          if tg_op='UPDATE' and old.documents_ready_at is not null
             and new.documents_ready_at is distinct from old.documents_ready_at then
            raise exception 'guide document readiness is immutable' using errcode='23514';
          end if;
        end if;
        return new;
      end $$;
      create trigger retained_guide_content_guard before insert or update on project_guides
        for each row execute function guard_retained_guide_source_fields();
      create trigger retained_guide_continuation_guard before insert or update on project_setup_runs
        for each row execute function guard_retained_guide_source_fields();
      create function reject_retired_guide_material_write() returns trigger language plpgsql as $$
      begin raise exception 'retained guide extraction evidence is read only' using errcode='55000'; end $$;
    """)
    for table in _RETIRED_TABLES:
        _execute(f"create trigger retired_guide_material_write_guard before insert or update or delete or truncate "
                   f"on {table} for each statement execute function reject_retired_guide_material_write()")
    _replace_function("validate_guide_mutation_custody", ((
        "new.content_markdown is distinct from old.content_markdown\n                    or new.change_summary is distinct from old.change_summary",
        "new.change_summary is distinct from old.change_summary",
    ),))


def _runtime_configuration_guard() -> None:
    keys = ["capability_key", "runtime_key", "model_provider", "model", "model_api",
            "instruction_id", "instruction_version", "instructions", "instructions_sha256",
            "retry_jitter", *_INTEGER_CONFIGURATION]
    sql_keys = "array[" + ",".join("'" + key + "'" for key in keys) + "]"
    checks = []
    for key, (lower, upper) in _INTEGER_CONFIGURATION.items():
        checks.extend((f"jsonb_typeof(config->'{key}') is distinct from 'number'",
                       f"not (config->>'{key}' ~ '^[0-9]+$')",
                       f"(config->>'{key}')::numeric < {lower}"))
        if upper is not None:
            checks.append(f"(config->>'{key}')::numeric > {upper}")
    numeric_checks = " or ".join(checks)
    _execute(f"""
      create or replace function guard_project_guide_runtime_configuration() returns trigger language plpgsql as $$
      declare config jsonb;
      begin
        if tg_op='UPDATE' then
          if new.runtime_configuration::jsonb is distinct from old.runtime_configuration::jsonb
             or new.runtime_configuration_hash is distinct from old.runtime_configuration_hash then
            raise exception 'compilation runtime configuration is immutable' using errcode='23514';
          end if;
          if (old.runtime_configuration is null or not (old.runtime_configuration::jsonb ? 'maximum_documents'))
             and to_jsonb(new) is distinct from to_jsonb(old) then
            raise exception 'retained compilation runtime is read only' using errcode='23514';
          end if;
          return new;
        end if;
        config := new.runtime_configuration::jsonb;
        if config is null or jsonb_typeof(config) is distinct from 'object'
           or octet_length(config::text)>75000 or not (config ?& {sql_keys})
           or config - {sql_keys} <> '{{}}'::jsonb
           or config->>'capability_key' is distinct from 'project_guide_compilation'
           or jsonb_typeof(config->'runtime_key') is distinct from 'string'
           or not (config->>'runtime_key' ~ '^[a-z][a-z0-9_]{{0,63}}$')
           or config->>'model_provider' is distinct from 'openai'
           or config->>'model_api' is distinct from 'responses'
           or jsonb_typeof(config->'model') is distinct from 'string'
           or length(config->>'model') not between 1 and 200
           or not (config->>'model' ~ '^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$')
           or config->>'instruction_id' is distinct from 'project_guide_compilation'
           or jsonb_typeof(config->'instruction_version') is distinct from 'string'
           or length(config->>'instruction_version') not between 1 and 100
           or config->>'instruction_version' is distinct from new.instruction_version
           or jsonb_typeof(config->'instructions') is distinct from 'string'
           or length(config->>'instructions') not between 1 and 16000
           or jsonb_typeof(config->'retry_jitter') is distinct from 'boolean'
           or {numeric_checks}
           or (config->>'maximum_document_bytes')::numeric > (config->>'maximum_total_document_bytes')::numeric
           or (config->>'retry_initial_delay_seconds')::numeric > (config->>'retry_max_delay_seconds')::numeric then
          raise exception 'compilation runtime configuration is invalid' using errcode='23514';
        end if;
        if config->>'instructions_sha256' is distinct from
             ('sha256:' || encode(sha256(convert_to(config->>'instructions','UTF8')),'hex'))
           or new.runtime_configuration_hash is distinct from
             ('sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(config),'UTF8')),'hex')) then
          raise exception 'compilation runtime configuration hash mismatch' using errcode='23514';
        end if;
        return new;
      end $$;
    """)


def _resource_tables() -> None:
    op.create_table("project_guide_runtime_allocations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("project_guide_compilation_attempts.id"), nullable=False),
        sa.Column("manifest_sha256", sa.String(71), nullable=False),
        sa.Column("runtime_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("document_handle", sa.Uuid()),
        sa.Column("provider_id", sa.String(128)),
        sa.Column("parent_provider_id", sa.String(128)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("attempt_id", "kind", "document_handle", name="uq_guide_runtime_allocation_slot", postgresql_nulls_not_distinct=True),
        sa.CheckConstraint("kind in ('container','file','attachment')", name="ck_guide_resource_kind"),
        sa.CheckConstraint("state in ('allocating','allocated','uncertain','cleanup_failed','deleted')", name="ck_guide_resource_state"),
        sa.CheckConstraint("(kind='container' and document_handle is null and parent_provider_id is null) or "
                           "(kind='file' and document_handle is not null and parent_provider_id is null) or "
                           "(kind='attachment' and document_handle is not null and parent_provider_id is not null)", name="ck_guide_resource_scope"),
        sa.CheckConstraint("state in ('allocating','uncertain') or provider_id is not null", name="ck_guide_resource_identity"))
    op.create_index("ix_project_guide_runtime_allocations_attempt_id", "project_guide_runtime_allocations", ["attempt_id"])
    op.create_table("project_guide_document_accesses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("project_guide_compilation_attempts.id"), nullable=False),
        sa.Column("source_item_id", sa.String(36), sa.ForeignKey("guide_source_snapshot_items.id"), nullable=False),
        sa.Column("document_version_id", sa.String(36), sa.ForeignKey("guide_source_artifact_ingests.id"), nullable=False),
        sa.Column("attachment_allocation_id", sa.Uuid(), sa.ForeignKey("project_guide_runtime_allocations.id"), nullable=False),
        sa.Column("manifest_sha256", sa.String(71), nullable=False),
        sa.Column("sha256", sa.String(71), nullable=False),
        sa.Column("document_handle", sa.Uuid(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("attempt_id", "source_item_id", name="uq_guide_document_access"))
    op.create_index("ix_project_guide_document_accesses_attempt_id", "project_guide_document_accesses", ["attempt_id"])


def _resource_guards() -> None:
    _execute("""
      create function guard_guide_runtime_allocation() returns trigger language plpgsql as $$
      declare attempt project_guide_compilation_attempts%rowtype;
      begin
        if tg_op in ('DELETE','TRUNCATE') then
          raise exception 'guide runtime allocation evidence is retained' using errcode='55000';
        end if;
        select * into attempt from project_guide_compilation_attempts where id=new.attempt_id for update;
        if not found or new.manifest_sha256 is distinct from attempt.guide_material_hash
           or new.runtime_key is distinct from attempt.runtime_configuration->>'runtime_key' then
          raise exception 'guide runtime allocation scope mismatch' using errcode='23514';
        end if;
        if tg_op='INSERT' then
          if attempt.status <> 'compilation_provider_uncertain' or new.state <> 'allocating'
             or new.provider_id is not null or new.deleted_at is not null
             or new.expires_at <= new.created_at
             or not (attempt.runtime_configuration::jsonb ? 'maximum_documents') then
            raise exception 'guide runtime allocation requires fenced intent' using errcode='23514';
          end if;
          if new.kind='attachment' and not exists(select 1 from project_guide_runtime_allocations parent
              where parent.attempt_id=new.attempt_id and parent.kind='container'
                and parent.provider_id=new.parent_provider_id and parent.state='allocated') then
            raise exception 'guide runtime attachment parent mismatch' using errcode='23514';
          end if;
          return new;
        end if;
        if (to_jsonb(new)-array['state','provider_id','deleted_at']) is distinct from
           (to_jsonb(old)-array['state','provider_id','deleted_at'])
           or (old.provider_id is not null and new.provider_id is distinct from old.provider_id)
           or (old.deleted_at is not null and new.deleted_at is distinct from old.deleted_at)
           or (old.state='deleted' and to_jsonb(new) is distinct from to_jsonb(old)) then
          raise exception 'guide runtime allocation evidence is immutable' using errcode='23514';
        end if;
        if new.state <> old.state and not (
             (old.state='allocating' and new.state in ('allocated','uncertain'))
             or (old.state in ('allocated','cleanup_failed') and new.state in ('deleted','cleanup_failed'))) then
          raise exception 'guide runtime allocation transition is invalid' using errcode='23514';
        end if;
        if (old.provider_id is null and new.provider_id is not null and new.state <> 'allocated')
           or (new.state='uncertain' and new.provider_id is not null) then
          raise exception 'guide runtime allocation receipt is invalid' using errcode='23514';
        end if;
        if new.provider_id is not null and not (
             (new.kind='container' and new.provider_id ~ '^cntr_[A-Za-z0-9_-]{1,120}$')
             or (new.kind='file' and new.provider_id ~ '^file-[A-Za-z0-9_-]{1,120}$')
             or (new.kind='attachment' and new.provider_id ~ '^cfile_[A-Za-z0-9_-]{1,120}$')) then
          raise exception 'guide runtime provider identity is invalid' using errcode='23514';
        end if;
        if (new.state='deleted') <> (new.deleted_at is not null) then
          raise exception 'guide runtime deletion evidence is invalid' using errcode='23514';
        end if;
        return new;
      end $$;
      create trigger guide_runtime_allocation_guard before insert or update or delete on project_guide_runtime_allocations
        for each row execute function guard_guide_runtime_allocation();
      create trigger guide_runtime_allocation_truncate_guard before truncate on project_guide_runtime_allocations
        for each statement execute function guard_guide_runtime_allocation();
      create function guard_guide_document_access() returns trigger language plpgsql as $$
      declare attempt project_guide_compilation_attempts%rowtype;
      begin
        if tg_op <> 'INSERT' then
          raise exception 'guide document access evidence is immutable' using errcode='55000';
        end if;
        select * into attempt from project_guide_compilation_attempts where id=new.attempt_id for update;
        if not found or attempt.status <> 'compilation_provider_uncertain'
           or new.manifest_sha256 is distinct from attempt.guide_material_hash
           or not exists(select 1 from project_guide_runtime_allocations resource
             where resource.id=new.attachment_allocation_id and resource.attempt_id=new.attempt_id
               and resource.manifest_sha256=new.manifest_sha256 and resource.kind='attachment'
               and resource.document_handle=new.document_handle and resource.state='allocated')
           or not exists(select 1 from guide_source_snapshot_items item
             join guide_source_artifact_ingests ingest on ingest.source_item_id=item.id
             join artifact_put_attempts put on put.guide_source_item_id=item.id
             where item.id=new.source_item_id and item.source_snapshot_id=attempt.source_snapshot_id
               and ingest.id=new.document_version_id and ingest.sha256=new.sha256
               and put.producer_request_type='guide' and put.status='object_confirmed'
               and put.terminal_result_code in ('document_stored','document_stored_observed')
               and put.sha256=new.sha256
               and (
                 (put.terminal_result_code='document_stored' and exists(
                   select 1 from artifact_operation_receipts receipt
                   where receipt.id=put.receipt_id and receipt.put_attempt_id=put.id
                     and receipt.guide_source_item_id=item.id and receipt.replica_id=put.replica_id
                     and receipt.request_digest=put.request_digest and receipt.outcome='document_stored'))
                 or (put.terminal_result_code='document_stored_observed' and put.receipt_id is null
                   and exists(select 1 from artifact_put_observation_receipts receipt
                     where receipt.put_attempt_id=put.id and receipt.execution_generation=put.execution_generation
                       and receipt.outcome='observed_confirmed'
                       and receipt.expected_sha256=put.sha256 and receipt.observed_sha256=put.sha256
                       and receipt.expected_byte_count=put.byte_count and receipt.observed_byte_count=put.byte_count))
               )) then
          raise exception 'guide document access lineage is invalid' using errcode='23514';
        end if;
        return new;
      end $$;
      create trigger guide_document_access_guard before insert or update or delete on project_guide_document_accesses
        for each row execute function guard_guide_document_access();
      create trigger guide_document_access_truncate_guard before truncate on project_guide_document_accesses
        for each statement execute function guard_guide_document_access();
    """)


def _source_custody() -> None:
    _replace_function("guard_project_guide_setup_finalization", ((
        "(s.continuation_verification_job_id is null)<>(s.continuation_started_at is null)",
        "s.documents_ready_at is null",
    ),))
    _replace_function("guard_finalized_project_setup", ((
        "(old.continuation_verification_job_id is null)<>(old.continuation_started_at is null)",
        "old.documents_ready_at is null",
    ),))
    definition = op.get_bind().scalar(sa.text(
        "select pg_get_functiondef('project_guide_finalization_source_digest(project_setup_runs)'::regprocedure)"))
    definition = definition.replace("continuation_started_at", "documents_ready_at")
    needle = "'continuation_verification_job_id',item.continuation_verification_job_id,"
    if definition.count(needle) != 1:
        raise RuntimeError("guide source digest shape changed")
    _execute(definition.replace(needle, ""))


def _accepted_document_evidence() -> None:
    _execute("""
      create function guard_compilation_document_evidence() returns trigger language plpgsql as $$
      declare reference jsonb; ready boolean;
      begin
        if new.status='provider_result_accepted' and old.status <> new.status then
          if old.status <> 'compilation_provider_uncertain' or not exists(
              select 1 from project_guide_document_accesses where attempt_id=new.id
                and manifest_sha256=new.guide_material_hash) then
            raise exception 'compilation requires original document access evidence' using errcode='23514';
          end if;
          for reference in select refs.value from jsonb_array_elements(
              coalesce(new.canonical_result::jsonb->'findings','[]'::jsonb)
              || coalesce(new.canonical_result::jsonb->'requirements','[]'::jsonb)
              || coalesce(new.canonical_result::jsonb->'capability_suggestions','[]'::jsonb)) component,
              lateral jsonb_array_elements(coalesce(component.value->'evidence_refs','[]'::jsonb)) refs
          loop
            if not exists(select 1 from project_guide_document_accesses access
                where access.attempt_id=new.id and access.manifest_sha256=new.guide_material_hash
                  and access.source_item_id=reference->>'source_item_id'
                  and access.document_version_id=reference->>'document_version_id'
                  and access.sha256=reference->>'sha256') then
              raise exception 'compilation cites unopened document version' using errcode='23514';
            end if;
          end loop;
          ready := new.canonical_result->>'status' is distinct from 'guide_blocked';
          if ready and exists(select 1 from guide_source_snapshot_items item
              where item.source_snapshot_id=new.source_snapshot_id and not exists(
                select 1 from project_guide_document_accesses access
                  where access.attempt_id=new.id and access.source_item_id=item.id)) then
            raise exception 'ready compilation requires all assigned documents' using errcode='23514';
          end if;
          if ready and exists(select 1 from guide_source_snapshot_items item
              where item.source_snapshot_id=new.source_snapshot_id and not exists(
                select 1 from jsonb_array_elements(
                  coalesce(new.canonical_result::jsonb->'findings','[]'::jsonb)
                  || coalesce(new.canonical_result::jsonb->'requirements','[]'::jsonb)
                  || coalesce(new.canonical_result::jsonb->'capability_suggestions','[]'::jsonb)) component,
                  lateral jsonb_array_elements(coalesce(component.value->'evidence_refs','[]'::jsonb)) refs
                where refs.value->>'source_item_id'=item.id)) then
            raise exception 'ready compilation requires citations for all assigned documents' using errcode='23514';
          end if;
        end if;
        return new;
      end $$;
      create trigger compilation_document_evidence_guard before update on project_guide_compilation_attempts
        for each row execute function guard_compilation_document_evidence();
    """)
