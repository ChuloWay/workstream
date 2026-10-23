"""Replace provider attachment custody with neutral fixed-parser evidence."""

from alembic import op


revision = "0059_neutral_guide_runtime"
down_revision = "0058_compensation_unit_create"
branch_labels = None
depends_on = None


_CONFIGURATION_GUARD = r"""
CREATE OR REPLACE FUNCTION public.guard_project_guide_runtime_configuration()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
  config jsonb;
  profile jsonb;
BEGIN
  IF TG_OP='UPDATE' THEN
    IF NEW.runtime_configuration::jsonb IS DISTINCT FROM OLD.runtime_configuration::jsonb
       OR NEW.runtime_configuration_hash IS DISTINCT FROM OLD.runtime_configuration_hash THEN
      RAISE EXCEPTION 'compilation runtime configuration is immutable' USING ERRCODE='23514';
    END IF;
    IF (OLD.runtime_configuration IS NULL
        OR NOT (OLD.runtime_configuration::jsonb ? 'maximum_documents'))
       AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
      RAISE EXCEPTION 'retained compilation runtime is read only' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;

  config := NEW.runtime_configuration::jsonb;
  IF config IS NULL OR jsonb_typeof(config) IS DISTINCT FROM 'object'
     OR octet_length(config::text)>75000
     OR NOT (config ?& ARRAY[
       'capability_key','runtime_key','model_provider','model','model_api','adapter_profile',
       'instruction_id','instruction_version','instructions','instructions_sha256',
       'timeout_seconds','maximum_manifest_bytes','maximum_documents',
       'maximum_document_bytes','maximum_total_document_bytes','maximum_turns',
       'maximum_tool_calls','maximum_tool_output_characters'])
     OR config - ARRAY[
       'capability_key','runtime_key','model_provider','model','model_api','adapter_profile',
       'instruction_id','instruction_version','instructions','instructions_sha256',
       'timeout_seconds','maximum_manifest_bytes','maximum_documents',
       'maximum_document_bytes','maximum_total_document_bytes','maximum_turns',
       'maximum_tool_calls','maximum_tool_output_characters'] <> '{}'::jsonb
     OR config->>'capability_key' IS DISTINCT FROM 'project_guide_compilation'
     OR jsonb_typeof(config->'runtime_key') IS DISTINCT FROM 'string'
     OR NOT (config->>'runtime_key' ~ '^[a-z][a-z0-9_]{0,63}$')
     OR jsonb_typeof(config->'model_provider') IS DISTINCT FROM 'string'
     OR NOT (config->>'model_provider' ~ '^[a-z][a-z0-9_.-]{0,63}$')
     OR jsonb_typeof(config->'model_api') IS DISTINCT FROM 'string'
     OR NOT (config->>'model_api' ~ '^[a-z][a-z0-9_]{0,63}$')
     OR jsonb_typeof(config->'model') IS DISTINCT FROM 'string'
     OR length(config->>'model') NOT BETWEEN 1 AND 200
     OR NOT (config->>'model' ~ '^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$')
     OR NOT (((config->>'model_provider')='none' AND (config->>'model_api')='none'
              AND (config->>'model')='none')
             OR ((config->>'model_provider')<>'none' AND (config->>'model_api')<>'none'
                 AND (config->>'model')<>'none'))
     OR jsonb_typeof(config->'adapter_profile') IS DISTINCT FROM 'string'
     OR length(config->>'adapter_profile') NOT BETWEEN 2 AND 8192
     OR config->>'instruction_id' IS DISTINCT FROM 'project_guide_compilation'
     OR jsonb_typeof(config->'instruction_version') IS DISTINCT FROM 'string'
     OR length(config->>'instruction_version') NOT BETWEEN 1 AND 100
     OR config->>'instruction_version' IS DISTINCT FROM NEW.instruction_version
     OR jsonb_typeof(config->'instructions') IS DISTINCT FROM 'string'
     OR length(config->>'instructions') NOT BETWEEN 1 AND 16000
     OR NOT _guide_runtime_integer(config,'timeout_seconds',1,7200)
     OR NOT _guide_runtime_integer(config,'maximum_manifest_bytes',1024,1000000)
     OR NOT _guide_runtime_integer(config,'maximum_documents',1,100)
     OR NOT _guide_runtime_integer(config,'maximum_document_bytes',1,536870912)
     OR NOT _guide_runtime_integer(config,'maximum_total_document_bytes',1,9223372036854775807)
     OR NOT _guide_runtime_integer(config,'maximum_turns',3,100)
     OR NOT _guide_runtime_integer(config,'maximum_tool_calls',3,200)
     OR NOT _guide_runtime_integer(config,'maximum_tool_output_characters',65536,16777216)
     OR (config->>'maximum_document_bytes')::numeric
        > (config->>'maximum_total_document_bytes')::numeric THEN
    RAISE EXCEPTION 'compilation runtime configuration is invalid' USING ERRCODE='23514';
  END IF;

  BEGIN
    profile := (config->>'adapter_profile')::jsonb;
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'compilation runtime adapter profile is invalid' USING ERRCODE='23514';
  END;
  IF jsonb_typeof(profile) IS DISTINCT FROM 'object'
     OR config->>'adapter_profile' IS DISTINCT FROM
       public.project_guide_projection_canonical_json(profile)
     OR (SELECT count(*) FROM jsonb_each(profile)) > 32
     OR EXISTS (
       SELECT 1 FROM jsonb_each(profile) item
       WHERE NOT (item.key ~ '^[a-z][a-z0-9_]{0,63}$')
          OR jsonb_typeof(item.value) NOT IN ('string','number','boolean','null')
          OR (jsonb_typeof(item.value)='string'
              AND octet_length(item.value #>> '{}') > 512)
          OR (jsonb_typeof(item.value)='number'
              AND (item.value::text !~ '^-?[0-9]+$'
                   OR abs((item.value::text)::numeric) > 9007199254740991))) THEN
    RAISE EXCEPTION 'compilation runtime adapter profile is invalid' USING ERRCODE='23514';
  END IF;
  IF config->>'instructions_sha256' IS DISTINCT FROM
       ('sha256:' || encode(sha256(convert_to(config->>'instructions','UTF8')),'hex'))
     OR NEW.runtime_configuration_hash IS DISTINCT FROM
       ('sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(config),'UTF8')),'hex')) THEN
    RAISE EXCEPTION 'compilation runtime configuration hash mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
"""


_INTEGER_HELPER = r"""
CREATE OR REPLACE FUNCTION public._guide_runtime_integer(config jsonb, key_name text,
  minimum numeric, maximum numeric) RETURNS boolean
LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,public,pg_temp AS $$
  SELECT jsonb_typeof(config->key_name)='number'
     AND config->>key_name ~ '^[0-9]+$'
     AND (config->>key_name)::numeric BETWEEN minimum AND maximum
$$
"""


_ACCESS_GUARD = r"""
CREATE OR REPLACE FUNCTION public.guard_guide_document_access()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE attempt project_guide_compilation_attempts%rowtype;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'guide document access evidence is immutable' USING ERRCODE='55000';
  END IF;
  SELECT * INTO attempt FROM project_guide_compilation_attempts
    WHERE id=NEW.attempt_id FOR UPDATE;
  IF NOT FOUND OR attempt.status <> 'compilation_provider_uncertain'
     OR NEW.manifest_sha256 IS DISTINCT FROM attempt.guide_material_hash
     OR NEW.access_method IS DISTINCT FROM 'trusted_parser'
     OR NEW.attachment_allocation_id IS NOT NULL
     OR NEW.operation IS NULL OR NEW.operation NOT IN ('read','search')
     OR NEW.parser_request_hash IS NULL
     OR NEW.parser_request_hash !~ '^sha256:[0-9a-f]{64}$'
     OR NEW.parser_response_hash IS NULL
     OR NEW.parser_response_hash !~ '^sha256:[0-9a-f]{64}$'
     OR NEW.parser_build_digest IS NULL
     OR NEW.parser_build_digest !~ '^sha256:[0-9a-f]{64}$'
     OR NEW.document_handle IS DISTINCT FROM canonical_guide_document_handle(
       attempt.setup_run_id::uuid, NEW.source_item_id::uuid, NEW.document_version_id::uuid)
     OR NOT EXISTS (
       SELECT 1 FROM guide_source_snapshot_items item
       JOIN guide_source_artifact_ingests ingest ON ingest.source_item_id=item.id
       WHERE item.id=NEW.source_item_id
         AND item.source_snapshot_id=attempt.source_snapshot_id
         AND item.source_kind='document' AND item.ingestion_adapter='upload'
         AND ingest.id=NEW.document_version_id AND ingest.sha256=NEW.sha256)
  THEN
    RAISE EXCEPTION 'guide document access lineage is invalid' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
"""


_ALLOCATION_GUARD = r"""
CREATE OR REPLACE FUNCTION public.guard_guide_runtime_allocation()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
  IF TG_OP IN ('DELETE','TRUNCATE') THEN
    RAISE EXCEPTION 'guide runtime allocation evidence is retained' USING ERRCODE='55000';
  END IF;
  IF TG_OP='INSERT' THEN
    RAISE EXCEPTION 'guide runtime allocation path is removed' USING ERRCODE='23514';
  END IF;
  IF (to_jsonb(NEW)-ARRAY['state','deleted_at'])
       IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','deleted_at'])
     OR (OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS DISTINCT FROM OLD.deleted_at)
     OR (OLD.state='deleted' AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD)) THEN
    RAISE EXCEPTION 'guide runtime allocation evidence is immutable' USING ERRCODE='23514';
  END IF;
  IF NEW.state <> OLD.state AND NOT (
       OLD.state IN ('allocated','cleanup_failed')
       AND NEW.state IN ('deleted','cleanup_failed')) THEN
    RAISE EXCEPTION 'guide runtime allocation transition is invalid' USING ERRCODE='23514';
  END IF;
  IF (NEW.state='deleted') <> (NEW.deleted_at IS NOT NULL) THEN
    RAISE EXCEPTION 'guide runtime deletion evidence is invalid' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
"""


def upgrade() -> None:
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM public.project_guide_compilation_attempts
            WHERE status IN ('compilation_reserved','provider_result_accepted')
              AND runtime_configuration->>'model_provider' IS DISTINCT FROM 'none'
              AND NOT (runtime_configuration::jsonb ? 'adapter_profile')) THEN
            RAISE EXCEPTION
              'old inferred guide attempt requires removed runtime recovery before upgrade';
          END IF;
        END $$
        """
    )
    op.execute(
        "ALTER TABLE public.project_guide_document_accesses "
        "ADD COLUMN access_method varchar(32), ADD COLUMN operation varchar(16), "
        "ADD COLUMN parser_request_hash varchar(71), "
        "ADD COLUMN parser_response_hash varchar(71), "
        "ADD COLUMN parser_build_digest varchar(71)"
    )
    op.execute(
        "ALTER TABLE public.project_guide_document_accesses "
        "DISABLE TRIGGER guide_document_access_guard"
    )
    op.execute(
        "UPDATE public.project_guide_document_accesses SET access_method="
        "CASE WHEN attachment_allocation_id IS NULL THEN 'direct_original' "
        "ELSE 'provider_attachment' END"
    )
    op.execute(
        "ALTER TABLE public.project_guide_document_accesses "
        "ENABLE TRIGGER guide_document_access_guard"
    )
    op.execute(
        "ALTER TABLE public.project_guide_document_accesses "
        "ALTER COLUMN access_method SET NOT NULL, "
        "DROP CONSTRAINT uq_guide_document_access, "
        "ADD CONSTRAINT uq_guide_document_parser_request "
        "UNIQUE(attempt_id,parser_request_hash), "
        "ADD CONSTRAINT ck_guide_document_access_evidence CHECK ("
        "(access_method='provider_attachment' AND attachment_allocation_id IS NOT NULL "
        "AND operation IS NULL AND parser_request_hash IS NULL "
        "AND parser_response_hash IS NULL AND parser_build_digest IS NULL) OR "
        "(access_method='direct_original' AND attachment_allocation_id IS NULL "
        "AND operation IS NULL AND parser_request_hash IS NULL "
        "AND parser_response_hash IS NULL AND parser_build_digest IS NULL) OR "
        "(access_method='trusted_parser' AND attachment_allocation_id IS NULL "
        "AND operation IS NOT NULL AND operation IN ('read','search') "
        "AND parser_request_hash IS NOT NULL "
        "AND parser_request_hash ~ '^sha256:[0-9a-f]{64}$' "
        "AND parser_response_hash IS NOT NULL "
        "AND parser_response_hash ~ '^sha256:[0-9a-f]{64}$' "
        "AND parser_build_digest IS NOT NULL "
        "AND parser_build_digest ~ '^sha256:[0-9a-f]{64}$'))"
    )
    op.execute(_INTEGER_HELPER)
    op.execute(_CONFIGURATION_GUARD)
    op.execute(_ACCESS_GUARD)
    op.execute(_ALLOCATION_GUARD)


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
