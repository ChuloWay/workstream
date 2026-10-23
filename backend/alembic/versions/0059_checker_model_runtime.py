"""Add guarded project-budgeted model-call custody for external checkers."""

from alembic import op
from sqlalchemy import text


revision = "0059_checker_model_runtime"
down_revision = "0058_compensation_unit_create"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the CHECKERS ledger before root-owned ART and AUTH extensions."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    for statement in _TABLES:
        op.execute(statement)
    for statement in _FUNCTIONS:
        op.execute(statement)
    for statement in _TRIGGERS:
        op.execute(statement)
    _upgrade_invocation_grants()
    _upgrade_art_custody()
    _upgrade_authorization_vocabulary()


def _upgrade_invocation_grants() -> None:
    """Create one-use invocation grants after their retained call-ledger parents."""
    op.execute(
        r"""
CREATE TABLE public.checker_model_invocation_grants (
 id uuid NOT NULL,
 token_hash varchar(71) NOT NULL,
 project_id uuid NOT NULL,
 checker_run_id uuid NOT NULL,
 registry_entry_id uuid NOT NULL,
 execution_facts jsonb NOT NULL,
 paid_slot jsonb NOT NULL,
 external_request_digest varchar(71) NOT NULL,
 expires_at timestamptz NOT NULL,
 issued_at timestamptz DEFAULT clock_timestamp() NOT NULL,
 authorization_evidence_id uuid NOT NULL,
 selected_request_sha256 varchar(71),
 selected_attempt_id uuid,
 consumed_at timestamptz,
 CONSTRAINT pk_checker_model_invocation_grants PRIMARY KEY(id),
 CONSTRAINT ck_checker_model_invocation_grants_id_uuid7 CHECK (
  (get_byte(uuid_send(id),6)>>4)=7 AND (get_byte(uuid_send(id),8)&192)=128),
 CONSTRAINT ck_checker_model_invocation_grants_digests CHECK (
  token_hash ~ '^sha256:[0-9a-f]{64}$' AND
  external_request_digest ~ '^sha256:[0-9a-f]{64}$' AND
  (selected_request_sha256 IS NULL OR
   selected_request_sha256 ~ '^sha256:[0-9a-f]{64}$')),
 CONSTRAINT ck_checker_model_invocation_grants_json CHECK (
  jsonb_typeof(execution_facts)='object' AND jsonb_typeof(paid_slot)='object'),
 CONSTRAINT ck_checker_model_invocation_grants_consumption CHECK (
  (consumed_at IS NULL AND selected_request_sha256 IS NULL AND
   selected_attempt_id IS NULL) OR
  (consumed_at IS NOT NULL AND selected_request_sha256 IS NOT NULL AND
   selected_attempt_id IS NOT NULL)),
 CONSTRAINT uq_checker_model_invocation_grants_token UNIQUE(token_hash),
 CONSTRAINT uq_checker_model_invocation_grants_authority
  UNIQUE(authorization_evidence_id),
 CONSTRAINT fk_checker_model_invocation_grants_project FOREIGN KEY(project_id)
  REFERENCES public.projects(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_invocation_grants_run FOREIGN KEY(checker_run_id)
  REFERENCES public.checker_runs(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_invocation_grants_registry FOREIGN KEY(registry_entry_id)
  REFERENCES public.external_checker_registry_entries(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_invocation_grants_authority
  FOREIGN KEY(authorization_evidence_id)
  REFERENCES public.audit_events(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_invocation_grants_attempt FOREIGN KEY(selected_attempt_id)
  REFERENCES public.checker_model_call_attempts(id) ON DELETE RESTRICT
)
        """
    )
    op.execute(
        r"""
CREATE INDEX ix_checker_model_invocation_grants_run
 ON public.checker_model_invocation_grants(checker_run_id)
        """
    )
    op.execute(
        r"""
CREATE FUNCTION public.guard_checker_model_invocation_grant() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE authority public.audit_events%ROWTYPE;
DECLARE task_project uuid;
DECLARE assignment_task uuid;
DECLARE assignment_project uuid;
DECLARE submission_task uuid;
DECLARE run public.checker_runs%ROWTYPE;
DECLARE registry public.external_checker_registry_entries%ROWTYPE;
DECLARE profile public.checker_model_profiles%ROWTYPE;
DECLARE attempt public.checker_model_call_attempts%ROWTYPE;
DECLARE slot public.checker_model_call_slots%ROWTYPE;
DECLARE binding_matches integer;
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'checker model invocation grants cannot be deleted'
   USING ERRCODE='55000';
 END IF;
 IF TG_OP='UPDATE' THEN
  IF OLD.consumed_at IS NOT NULL OR
     NEW.selected_request_sha256 IS NULL OR NEW.selected_attempt_id IS NULL OR
     NEW.consumed_at IS NULL OR
     (to_jsonb(NEW)-ARRAY['selected_request_sha256','selected_attempt_id','consumed_at'])
      IS DISTINCT FROM
     (to_jsonb(OLD)-ARRAY['selected_request_sha256','selected_attempt_id','consumed_at']) THEN
   RAISE EXCEPTION 'checker model invocation grant facts are immutable'
    USING ERRCODE='55000';
  END IF;
  IF OLD.expires_at<=clock_timestamp() THEN
   RAISE EXCEPTION 'checker model invocation grant expired'
    USING ERRCODE='23514';
  END IF;
  SELECT value.* INTO attempt FROM public.checker_model_call_attempts value
   WHERE value.id=NEW.selected_attempt_id FOR SHARE;
  SELECT value.* INTO slot FROM public.checker_model_call_slots value
   WHERE value.id=attempt.slot_id FOR SHARE;
  IF attempt.id IS NULL OR slot.id IS NULL OR
     attempt.request_sha256 IS DISTINCT FROM NEW.selected_request_sha256 OR
     slot.project_id IS DISTINCT FROM NEW.project_id OR
     slot.task_id IS DISTINCT FROM (NEW.execution_facts->>'task_id')::uuid OR
     slot.assignment_id IS DISTINCT FROM (NEW.paid_slot->>'assignment_id')::uuid OR
     slot.submission_id IS DISTINCT FROM (NEW.paid_slot->>'submission_id')::uuid OR
     slot.submission_version IS DISTINCT FROM
      (NEW.paid_slot->>'submission_version')::integer OR
     slot.requirement_id IS DISTINCT FROM NEW.paid_slot->>'requirement_id' OR
     slot.registry_entry_digest IS DISTINCT FROM
      NEW.paid_slot->>'registry_entry_digest' OR
     slot.configuration_sha256 IS DISTINCT FROM
      NEW.paid_slot->>'configuration_sha256' OR
     slot.profile_id IS DISTINCT FROM (NEW.paid_slot->>'profile_id')::uuid OR
     slot.profile_version IS DISTINCT FROM
      (NEW.paid_slot->>'profile_version')::integer OR
     slot.profile_digest IS DISTINCT FROM NEW.paid_slot->>'profile_digest' OR
     slot.slot_index IS DISTINCT FROM (NEW.paid_slot->>'slot_index')::integer THEN
   RAISE EXCEPTION 'checker model invocation grant attempt ancestry is invalid'
    USING ERRCODE='23514';
  END IF;
  NEW.consumed_at:=clock_timestamp();
  RETURN NEW;
 END IF;

 IF jsonb_typeof(NEW.execution_facts)<>'object' OR
    jsonb_typeof(NEW.paid_slot)<>'object' OR
    (SELECT count(*) FROM jsonb_object_keys(NEW.execution_facts))<>11 OR
    NOT NEW.execution_facts ?& ARRAY[
     'project_id','task_id','assignment_id','submission_id','submission_version',
     'evaluation_request_id','evaluation_generation','checker_run_id',
     'worker_lease_id','worker_lease_generation','worker_lease_expires_at'] OR
    (SELECT count(*) FROM jsonb_object_keys(NEW.paid_slot))<>11 OR
    NOT NEW.paid_slot ?& ARRAY[
     'project_id','assignment_id','submission_id','submission_version',
     'requirement_id','registry_entry_digest','configuration_sha256','profile_id',
     'profile_version','profile_digest','slot_index'] OR
    jsonb_typeof(NEW.execution_facts->'submission_version')<>'number' OR
    jsonb_typeof(NEW.execution_facts->'evaluation_generation')<>'number' OR
    jsonb_typeof(NEW.execution_facts->'worker_lease_generation')<>'number' OR
    jsonb_typeof(NEW.paid_slot->'submission_version')<>'number' OR
    jsonb_typeof(NEW.paid_slot->'profile_version')<>'number' OR
    jsonb_typeof(NEW.paid_slot->'slot_index')<>'number' OR
    (NEW.execution_facts->>'submission_version')::integer<=0 OR
    (NEW.execution_facts->>'evaluation_generation')::integer<=0 OR
    (NEW.execution_facts->>'worker_lease_generation')::integer<=0 OR
    (NEW.paid_slot->>'submission_version')::integer<=0 OR
    (NEW.paid_slot->>'profile_version')::integer<=0 OR
    (NEW.paid_slot->>'slot_index')::integer<>0 OR
    NEW.execution_facts->'submission_version' IS DISTINCT FROM
     to_jsonb((NEW.execution_facts->>'submission_version')::integer) OR
    NEW.execution_facts->'evaluation_generation' IS DISTINCT FROM
     to_jsonb((NEW.execution_facts->>'evaluation_generation')::integer) OR
    NEW.execution_facts->'worker_lease_generation' IS DISTINCT FROM
     to_jsonb((NEW.execution_facts->>'worker_lease_generation')::integer) OR
    NEW.paid_slot->'submission_version' IS DISTINCT FROM
     to_jsonb((NEW.paid_slot->>'submission_version')::integer) OR
    NEW.paid_slot->'profile_version' IS DISTINCT FROM
     to_jsonb((NEW.paid_slot->>'profile_version')::integer) OR
    NEW.paid_slot->'slot_index' IS DISTINCT FROM
     to_jsonb((NEW.paid_slot->>'slot_index')::integer) OR
    coalesce(NEW.paid_slot->>'requirement_id','')
     !~ '^[a-z][a-z0-9_.-]{0,99}$' OR
    coalesce(NEW.paid_slot->>'registry_entry_digest','')
     !~ '^sha256:[0-9a-f]{64}$' OR
    coalesce(NEW.paid_slot->>'configuration_sha256','')
     !~ '^sha256:[0-9a-f]{64}$' OR
    coalesce(NEW.paid_slot->>'profile_digest','')
     !~ '^sha256:[0-9a-f]{64}$' THEN
  RAISE EXCEPTION 'checker model invocation grant facts are invalid'
   USING ERRCODE='23514';
 END IF;

 SELECT * INTO authority FROM public.audit_events
  WHERE id=NEW.authorization_evidence_id FOR SHARE;
 IF authority.id IS NULL OR
    authority.event_domain IS DISTINCT FROM 'authority' OR
    authority.event_type IS DISTINCT FROM 'SensitiveAuthorizationAllowed' OR
    authority.actor_ref_kind IS DISTINCT FROM 'actor_profile' OR
    authority.action_id IS DISTINCT FROM 'checker.model_call.grant' OR
    authority.permission_id IS DISTINCT FROM 'checker.model_call.grant' OR
    authority.denial_code IS NOT NULL OR
    authority.after_facts::jsonb IS DISTINCT FROM jsonb_build_object(
     'allowed',true,
     'resource_context_digest',authority.after_facts->>'resource_context_digest') OR
    coalesce(authority.after_facts->>'resource_context_digest','')
     !~ '^sha256:[0-9a-f]{64}$' THEN
  RAISE EXCEPTION 'checker model invocation grant authority is invalid'
   USING ERRCODE='23514';
 END IF;

 PERFORM 1 FROM public.projects WHERE id=NEW.project_id FOR SHARE;
 SELECT project_id INTO task_project FROM public.workstream_tasks
  WHERE id=(NEW.execution_facts->>'task_id')::uuid FOR SHARE;
 SELECT task_id,project_id INTO assignment_task,assignment_project
  FROM public.task_assignments
  WHERE id=(NEW.execution_facts->>'assignment_id')::uuid FOR SHARE;
 SELECT task_id INTO submission_task FROM public.submissions
  WHERE id=(NEW.execution_facts->>'submission_id')::uuid AND
   version=(NEW.execution_facts->>'submission_version')::integer FOR SHARE;
 IF task_project IS DISTINCT FROM NEW.project_id OR
    assignment_task IS DISTINCT FROM (NEW.execution_facts->>'task_id')::uuid OR
    assignment_project IS DISTINCT FROM NEW.project_id OR
    submission_task IS DISTINCT FROM (NEW.execution_facts->>'task_id')::uuid THEN
  RAISE EXCEPTION 'checker model invocation grant task ancestry is invalid'
   USING ERRCODE='23514';
 END IF;

 SELECT * INTO run FROM public.checker_runs
  WHERE id=NEW.checker_run_id FOR SHARE;
 SELECT * INTO registry FROM public.external_checker_registry_entries
  WHERE id=NEW.registry_entry_id FOR SHARE;
 SELECT * INTO profile FROM public.checker_model_profiles
  WHERE id=(NEW.paid_slot->>'profile_id')::uuid AND
   profile_version=(NEW.paid_slot->>'profile_version')::integer AND
   profile_digest=NEW.paid_slot->>'profile_digest' FOR SHARE;
 NEW.issued_at:=clock_timestamp();
 IF NOT isfinite(NEW.expires_at) OR NEW.expires_at<=clock_timestamp() OR
    NEW.consumed_at IS NOT NULL OR NEW.selected_request_sha256 IS NOT NULL OR
    NEW.selected_attempt_id IS NOT NULL OR
    (NEW.execution_facts->>'project_id')::uuid IS DISTINCT FROM NEW.project_id OR
    (NEW.paid_slot->>'project_id')::uuid IS DISTINCT FROM NEW.project_id OR
    (NEW.execution_facts->>'checker_run_id')::uuid IS DISTINCT FROM NEW.checker_run_id OR
    (NEW.execution_facts->>'assignment_id')::uuid IS DISTINCT FROM
     (NEW.paid_slot->>'assignment_id')::uuid OR
    (NEW.execution_facts->>'submission_id')::uuid IS DISTINCT FROM
     (NEW.paid_slot->>'submission_id')::uuid OR
    (NEW.execution_facts->>'submission_version')::integer IS DISTINCT FROM
     (NEW.paid_slot->>'submission_version')::integer OR
    run.id IS NULL OR run.project_id IS DISTINCT FROM NEW.project_id OR
    run.task_id IS DISTINCT FROM (NEW.execution_facts->>'task_id')::uuid OR
    (run.request_json::jsonb->>'assignment_id')::uuid IS DISTINCT FROM
     (NEW.execution_facts->>'assignment_id')::uuid OR
    run.submission_id IS DISTINCT FROM (NEW.execution_facts->>'submission_id')::uuid OR
    run.submission_version IS DISTINCT FROM
     (NEW.execution_facts->>'submission_version')::integer OR
    run.evaluation_request_id IS DISTINCT FROM
     (NEW.execution_facts->>'evaluation_request_id')::uuid OR
    run.evaluation_generation IS DISTINCT FROM
     (NEW.execution_facts->>'evaluation_generation')::integer OR
    run.worker_lease_id IS DISTINCT FROM
     (NEW.execution_facts->>'worker_lease_id')::uuid OR
    run.worker_lease_generation IS DISTINCT FROM
     (NEW.execution_facts->>'worker_lease_generation')::integer OR
    run.worker_lease_expires_at IS DISTINCT FROM
     (NEW.execution_facts->>'worker_lease_expires_at')::timestamptz OR
    run.worker_lease_expires_at IS DISTINCT FROM NEW.expires_at OR
    run.status IS DISTINCT FROM 'running' OR run.phase IS DISTINCT FROM 'post_submission' OR
    registry.id IS NULL OR registry.phase IS DISTINCT FROM 'post_submit' OR
    registry.entry_digest IS DISTINCT FROM NEW.paid_slot->>'registry_entry_digest' OR
    profile.id IS NULL OR profile.project_id IS DISTINCT FROM NEW.project_id OR
    profile.registry_entry_id IS DISTINCT FROM NEW.registry_entry_id OR
    profile.registry_entry_digest IS DISTINCT FROM
     NEW.paid_slot->>'registry_entry_digest' THEN
  RAISE EXCEPTION 'checker model invocation grant execution ancestry is invalid'
   USING ERRCODE='23514';
 END IF;

 IF run.selected_post_submit_policy_sha256 IS NULL OR
    run.selected_post_submit_policy_sha256 IS DISTINCT FROM
     run.locked_post_submit_checker_policy_hash OR
    jsonb_typeof(run.selected_post_submit_policy_body)<>'object' OR
    run.selected_post_submit_policy_body->>'policy_sha256' IS DISTINCT FROM
     run.selected_post_submit_policy_sha256 OR
    jsonb_typeof(run.selected_post_submit_policy_body->'entries')<>'array' THEN
  RAISE EXCEPTION 'checker model invocation grant locked policy is invalid'
   USING ERRCODE='23514';
 END IF;
 SELECT count(*) INTO binding_matches
  FROM jsonb_array_elements(run.selected_post_submit_policy_body->'entries') binding
  WHERE binding->>'requirement_id'=NEW.paid_slot->>'requirement_id' AND
   binding->>'stage'='post_submit' AND
   binding->>'configuration_sha256'=NEW.paid_slot->>'configuration_sha256' AND
   binding->'registry'->>'registry_entry_id'=NEW.registry_entry_id::text AND
   binding->'registry'->>'entry_digest'=NEW.paid_slot->>'registry_entry_digest' AND
   binding->'configuration'->>'model_profile_id'=NEW.paid_slot->>'profile_id' AND
   binding->'configuration'->>'model_profile_version'=
    NEW.paid_slot->>'profile_version' AND
   binding->'configuration'->>'model_profile_digest'=NEW.paid_slot->>'profile_digest';
 IF binding_matches<>1 THEN
  RAISE EXCEPTION 'checker model invocation grant binding ancestry is invalid'
   USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$
        """
    )
    op.execute(
        r"""
CREATE TRIGGER checker_model_invocation_grants_guard
 BEFORE INSERT OR UPDATE OR DELETE ON public.checker_model_invocation_grants
 FOR EACH ROW EXECUTE FUNCTION public.guard_checker_model_invocation_grant()
        """
    )
    op.execute(
        r"""
CREATE TRIGGER checker_model_invocation_grants_no_truncate
 BEFORE TRUNCATE ON public.checker_model_invocation_grants
 FOR EACH STATEMENT EXECUTE FUNCTION public.guard_checker_model_no_truncate()
        """
    )


def _upgrade_art_custody() -> None:
    """Extend verified ART ancestry to call-stable evidence, preserving retained rows."""
    op.execute(
        r"""
ALTER TABLE artifact_put_attempts ADD COLUMN model_call_attempt_id uuid REFERENCES checker_model_call_attempts(id) ON DELETE RESTRICT
        """
    )
    op.execute(
        r"""
CREATE INDEX ix_artifact_put_attempts_model_call_attempt_id ON artifact_put_attempts (model_call_attempt_id)
        """
    )
    op.execute(
        r"""
ALTER TABLE artifact_operation_receipts ADD COLUMN model_call_attempt_id uuid REFERENCES checker_model_call_attempts(id) ON DELETE RESTRICT
        """
    )
    op.execute(
        r"""
CREATE INDEX ix_artifact_operation_receipts_model_call_attempt_id ON artifact_operation_receipts (model_call_attempt_id)
        """
    )
    op.execute(
        r"""
ALTER TABLE artifact_put_attempts DROP CONSTRAINT ck_artifact_put_attempts_producer_reference
        """
    )
    op.execute(
        r"""
ALTER TABLE artifact_put_attempts ADD CONSTRAINT ck_artifact_put_attempts_producer_reference CHECK ((producer_request_type = 'guide' and task_import_source_id is null and guide_source_item_id is not null and checker_run_id is null and model_call_attempt_id is null and task_id is null and submission_id is null and submission_version is null and logical_role is null) or (producer_request_type = 'checker_output' and task_import_source_id is null and guide_source_item_id is null and ((checker_run_id is not null and model_call_attempt_id is null) or (checker_run_id is null and model_call_attempt_id is not null and logical_role in ('model_request','model_response'))) and task_id is not null and submission_id is not null and submission_version is not null and octet_length(logical_role) between 1 and 100) or (producer_request_type = 'submission_bundle' and task_import_source_id is null and guide_source_item_id is null and checker_run_id is null and model_call_attempt_id is null and task_id is not null and submission_id is null and submission_version is null and logical_role is null) or (producer_request_type = 'task_import_source' and task_import_source_id is not null and guide_source_item_id is null and checker_run_id is null and model_call_attempt_id is null and task_id is null and submission_id is null and submission_version is null and logical_role is not distinct from 'task_import_source'))
        """
    )
    op.execute(
        r"""
ALTER TABLE artifact_operation_receipts DROP CONSTRAINT ck_artifact_operation_receipts_contract_producer_reference
        """
    )
    op.execute(
        r"""
ALTER TABLE artifact_operation_receipts ADD CONSTRAINT ck_artifact_operation_receipts_contract_producer_reference CHECK (contract_version = 2 and put_attempt_id is not null and ((guide_source_item_id is not null and checker_run_id is null and model_call_attempt_id is null and logical_role is null) or (guide_source_item_id is null and checker_run_id is not null and model_call_attempt_id is null and octet_length(logical_role) between 1 and 100) or (guide_source_item_id is null and checker_run_id is null and model_call_attempt_id is null and (logical_role is null or logical_role='task_import_source')) or (guide_source_item_id is null and checker_run_id is null and model_call_attempt_id is not null and logical_role in ('model_request','model_response'))))
        """
    )
    op.execute(
        r"""
CREATE OR REPLACE FUNCTION public.guard_artifact_receipt_producer_reference() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
        DECLARE
          attempt artifact_put_attempts%ROWTYPE;
        BEGIN
          SELECT value.* INTO attempt
          FROM public.artifact_put_attempts value
          WHERE value.id=NEW.put_attempt_id;
          IF attempt.id IS NULL
             OR (attempt.producer_request_type='guide' AND NOT (
               NEW.guide_source_item_id IS NOT NULL
               AND NEW.checker_run_id IS NULL
               AND NEW.model_call_attempt_id IS NULL
               AND NEW.logical_role IS NULL))
             OR (attempt.producer_request_type='checker_output' AND NOT (
               NEW.guide_source_item_id IS NULL
               AND (
                 (attempt.model_call_attempt_id IS NULL
                  AND NEW.checker_run_id IS NOT NULL
                  AND NEW.model_call_attempt_id IS NULL
                  AND octet_length(NEW.logical_role) BETWEEN 1 AND 100)
                 OR
                 (attempt.model_call_attempt_id IS NOT NULL
                  AND NEW.checker_run_id IS NULL
                  AND NEW.model_call_attempt_id IS NOT DISTINCT FROM attempt.model_call_attempt_id
                  AND NEW.logical_role IS NOT DISTINCT FROM attempt.logical_role
                  AND NEW.logical_role IN ('model_request','model_response')))))
             OR (attempt.producer_request_type='submission_bundle' AND NOT (
               NEW.guide_source_item_id IS NULL
               AND NEW.checker_run_id IS NULL
               AND NEW.model_call_attempt_id IS NULL
               AND NEW.logical_role IS NULL))
             OR (attempt.producer_request_type='task_import_source' AND (
               NEW.guide_source_item_id IS NOT NULL
               OR NEW.checker_run_id IS NOT NULL
               OR NEW.model_call_attempt_id IS NOT NULL
               OR NEW.logical_role IS DISTINCT FROM 'task_import_source'))
             OR attempt.producer_request_type NOT IN (
               'guide','checker_output','submission_bundle','task_import_source') THEN
            RAISE EXCEPTION 'artifact receipt producer reference mismatch'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        r"""
ALTER TABLE artifact_bindings DROP CONSTRAINT ck_artifact_bindings_checker_output_lineage
        """
    )
    op.execute(
        r"""
ALTER TABLE artifact_bindings ADD CONSTRAINT ck_artifact_bindings_checker_output_lineage CHECK ((resource_type in ('checker_run','checker_model_call') and scope_version = 1 and put_attempt_id is not null and verification_receipt_id is not null) or (resource_type not in ('checker_run','checker_model_call') and put_attempt_id is null and verification_receipt_id is null))
        """
    )
    op.execute(
        r"""
CREATE OR REPLACE FUNCTION public.guard_checker_output_put_attempt_custody() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            IF OLD.producer_request_type='checker_output'
               OR OLD.checker_output_custody_sealed THEN
              RAISE EXCEPTION 'checker output put attempt custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.checker_output_custody_sealed THEN
            IF NOT NEW.checker_output_custody_sealed
               OR (to_jsonb(NEW) - 'checker_output_custody_sealed')
                  IS DISTINCT FROM
                  (to_jsonb(OLD) - 'checker_output_custody_sealed') THEN
              RAISE EXCEPTION 'checker output put attempt custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.checker_output_custody_sealed THEN
            IF (to_jsonb(NEW) - 'checker_output_custody_sealed')
                 IS DISTINCT FROM
                 (to_jsonb(OLD) - 'checker_output_custody_sealed')
               OR NOT EXISTS (
                 SELECT 1 FROM artifact_bindings binding
                 WHERE binding.resource_type IN ('checker_run','checker_model_call')
                   AND binding.put_attempt_id=OLD.id
               ) THEN
              RAISE EXCEPTION 'checker output put attempt seal requires binding'
                USING ERRCODE='55000';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.producer_request_type='checker_output'
             OR NEW.producer_request_type='checker_output' THEN
            IF ROW(
                 NEW.id, NEW.producer_request_type, NEW.producer_type, NEW.producer_ref,
                 NEW.project_id, NEW.task_id, NEW.guide_source_item_id, NEW.checker_run_id, NEW.model_call_attempt_id,
                 NEW.submission_id, NEW.submission_version, NEW.logical_role,
                 NEW.sha256, NEW.byte_count, NEW.media_type, NEW.storage_namespace_id,
                 NEW.namespace_fingerprint, NEW.canonical_target, NEW.operation_identity,
                 NEW.request_digest, NEW.checker_request_digest, NEW.maximum_observations,
                 NEW.prepared_at, NEW.created_at
               ) IS DISTINCT FROM ROW(
                 OLD.id, OLD.producer_request_type, OLD.producer_type, OLD.producer_ref,
                 OLD.project_id, OLD.task_id, OLD.guide_source_item_id, OLD.checker_run_id, OLD.model_call_attempt_id,
                 OLD.submission_id, OLD.submission_version, OLD.logical_role,
                 OLD.sha256, OLD.byte_count, OLD.media_type, OLD.storage_namespace_id,
                 OLD.namespace_fingerprint, OLD.canonical_target, OLD.operation_identity,
                 OLD.request_digest, OLD.checker_request_digest, OLD.maximum_observations,
                 OLD.prepared_at, OLD.created_at
               ) THEN
              RAISE EXCEPTION 'checker output put attempt custody is immutable'
                USING ERRCODE='55000';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        r"""
CREATE OR REPLACE FUNCTION public.guard_checker_output_verification_job_custody() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            IF OLD.checker_output_custody_sealed THEN
              RAISE EXCEPTION 'checker output verification job custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.checker_output_custody_sealed THEN
            IF NOT NEW.checker_output_custody_sealed
               OR (to_jsonb(NEW) - 'checker_output_custody_sealed')
                  IS DISTINCT FROM
                  (to_jsonb(OLD) - 'checker_output_custody_sealed') THEN
              RAISE EXCEPTION 'checker output verification job custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.checker_output_custody_sealed THEN
            IF (to_jsonb(NEW) - 'checker_output_custody_sealed')
                 IS DISTINCT FROM
                 (to_jsonb(OLD) - 'checker_output_custody_sealed')
               OR NOT EXISTS (
                 SELECT 1
                 FROM artifact_bindings binding
                 JOIN artifact_verification_receipts receipt
                   ON receipt.id=binding.verification_receipt_id
                 WHERE binding.resource_type IN ('checker_run','checker_model_call')
                   AND receipt.verification_job_id=OLD.id
               ) THEN
              RAISE EXCEPTION 'checker output verification job seal requires binding'
                USING ERRCODE='55000';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        r"""
CREATE OR REPLACE FUNCTION public.guard_checker_output_replica_custody() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            IF OLD.checker_output_custody_sealed THEN
              RAISE EXCEPTION 'checker output replica custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.checker_output_custody_sealed THEN
            IF NOT NEW.checker_output_custody_sealed
               OR ROW(
                    NEW.id, NEW.content_id, NEW.storage_namespace_id,
                    NEW.namespace_fingerprint, NEW.adapter,
                    NEW.provider_profile, NEW.provider_object_ref
                  ) IS DISTINCT FROM ROW(
                    OLD.id, OLD.content_id, OLD.storage_namespace_id,
                    OLD.namespace_fingerprint, OLD.adapter,
                    OLD.provider_profile, OLD.provider_object_ref
                  ) THEN
              RAISE EXCEPTION 'checker output replica custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.checker_output_custody_sealed THEN
            IF (to_jsonb(NEW) - 'checker_output_custody_sealed')
                 IS DISTINCT FROM
                 (to_jsonb(OLD) - 'checker_output_custody_sealed')
               OR NOT EXISTS (
                 SELECT 1
                 FROM artifact_bindings binding
                 JOIN artifact_verification_receipts receipt
                   ON receipt.id=binding.verification_receipt_id
                 JOIN artifact_verification_jobs job
                   ON job.id=receipt.verification_job_id
                 WHERE binding.resource_type IN ('checker_run','checker_model_call')
                   AND job.replica_id=OLD.id
               ) THEN
              RAISE EXCEPTION 'checker output replica seal requires binding'
                USING ERRCODE='55000';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        r"""
CREATE OR REPLACE FUNCTION public.guard_checker_output_binding_insert() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
        DECLARE
          verification artifact_verification_receipts%ROWTYPE;
          job artifact_verification_jobs%ROWTYPE;
          replica artifact_replicas%ROWTYPE;
          attempt artifact_put_attempts%ROWTYPE;
          content artifact_contents%ROWTYPE;
          write_receipt_matches integer;
        BEGIN
          IF NEW.resource_type NOT IN ('checker_run','checker_model_call') THEN
            RETURN NEW;
          END IF;

          SELECT receipt.* INTO verification
          FROM artifact_verification_receipts receipt
          WHERE receipt.id=NEW.verification_receipt_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'checker output binding verified ancestry mismatch'
              USING ERRCODE='23514';
          END IF;

          SELECT value.* INTO job
          FROM artifact_verification_jobs value
          WHERE value.id=verification.verification_job_id
          FOR UPDATE;
          SELECT value.* INTO replica
          FROM artifact_replicas value
          WHERE value.id=job.replica_id
          FOR UPDATE;
          SELECT value.* INTO attempt
          FROM artifact_put_attempts value
          WHERE value.id=job.originating_put_attempt_id
          FOR UPDATE;
          SELECT value.* INTO content
          FROM artifact_contents value
          WHERE value.id=replica.content_id
          FOR SHARE;

          SELECT count(*) INTO write_receipt_matches
          FROM (
            SELECT receipt.id
            FROM artifact_operation_receipts receipt
            WHERE attempt.receipt_id IS NOT NULL
              AND receipt.id=attempt.receipt_id
              AND receipt.put_attempt_id=attempt.id
              AND receipt.replica_id=replica.id
              AND receipt.checker_run_id IS NOT DISTINCT FROM attempt.checker_run_id
              AND receipt.model_call_attempt_id IS NOT DISTINCT FROM attempt.model_call_attempt_id
              AND receipt.logical_role=attempt.logical_role
              AND receipt.request_digest=attempt.request_digest
              AND receipt.provider_object_ref=replica.provider_object_ref
              AND receipt.outcome='stored_pending_verification'
            UNION ALL
            SELECT receipt.id
            FROM artifact_put_observation_receipts receipt
            WHERE attempt.receipt_id IS NULL
              AND receipt.put_attempt_id=attempt.id
              AND receipt.execution_generation=attempt.execution_generation
              AND receipt.outcome='observed_confirmed'
              AND receipt.expected_sha256=attempt.sha256
              AND receipt.observed_sha256=attempt.sha256
              AND receipt.expected_byte_count=attempt.byte_count
              AND receipt.observed_byte_count=attempt.byte_count
          ) successful_write;

          IF job.id IS NULL OR replica.id IS NULL OR attempt.id IS NULL OR content.id IS NULL
             OR NEW.put_attempt_id IS DISTINCT FROM attempt.id
             OR NEW.content_id IS DISTINCT FROM content.id
             OR NEW.project_id IS DISTINCT FROM attempt.project_id
             OR NEW.resource_id IS DISTINCT FROM (
                  CASE WHEN NEW.resource_type='checker_model_call'
                  THEN attempt.model_call_attempt_id::text ELSE attempt.checker_run_id::text END
                )
             OR NEW.logical_role IS DISTINCT FROM attempt.logical_role
             OR NEW.actor_id IS DISTINCT FROM attempt.producer_ref
             OR NEW.attribution_type IS DISTINCT FROM 'service_identity'
             OR NEW.scope_version <> 1
             OR NEW.supersedes_binding_id IS NOT NULL
             OR attempt.producer_request_type <> 'checker_output'
             OR attempt.producer_type <> 'service_identity'
             OR attempt.submission_id IS NULL OR attempt.submission_version IS NULL
             OR attempt.checker_request_digest IS NULL
             OR attempt.status <> 'object_confirmed'
             OR attempt.replica_id IS DISTINCT FROM replica.id
             OR attempt.storage_namespace_id IS DISTINCT FROM replica.storage_namespace_id
             OR attempt.namespace_fingerprint IS DISTINCT FROM replica.namespace_fingerprint
             OR attempt.canonical_target IS DISTINCT FROM replica.provider_object_ref
             OR attempt.sha256 IS DISTINCT FROM content.sha256
             OR attempt.byte_count IS DISTINCT FROM content.byte_count
             OR attempt.media_type IS DISTINCT FROM content.media_type
             OR job.originating_put_attempt_id IS DISTINCT FROM attempt.id
             OR job.replica_id IS DISTINCT FROM replica.id
             OR job.status <> 'verified'
             OR job.terminal_result_code IS DISTINCT FROM 'verified'
             OR job.terminal_at IS NULL
             OR verification.outcome <> 'verified'
             OR verification.execution_generation IS DISTINCT FROM job.execution_generation
             OR verification.observed_sha256 IS DISTINCT FROM attempt.sha256
             OR verification.observed_byte_count IS DISTINCT FROM attempt.byte_count
             OR replica.verification_state <> 'verified'
             OR replica.availability_state <> 'available'
             OR replica.integrity_state <> 'valid'
             OR write_receipt_matches <> 1 THEN
            RAISE EXCEPTION 'checker output binding verified ancestry mismatch'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        r"""
CREATE OR REPLACE FUNCTION public.seal_checker_output_binding_ancestry() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
        DECLARE
          verification artifact_verification_receipts%ROWTYPE;
          job artifact_verification_jobs%ROWTYPE;
        BEGIN
          IF NEW.resource_type NOT IN ('checker_run','checker_model_call') THEN
            RETURN NEW;
          END IF;
          SELECT receipt.* INTO STRICT verification
          FROM artifact_verification_receipts receipt
          WHERE receipt.id=NEW.verification_receipt_id;
          SELECT value.* INTO STRICT job
          FROM artifact_verification_jobs value
          WHERE value.id=verification.verification_job_id;

          UPDATE artifact_verification_jobs
          SET checker_output_custody_sealed=true
          WHERE id=job.id AND NOT checker_output_custody_sealed;
          UPDATE artifact_replicas
          SET checker_output_custody_sealed=true
          WHERE id=job.replica_id AND NOT checker_output_custody_sealed;
          UPDATE artifact_put_attempts
          SET checker_output_custody_sealed=true
          WHERE id=NEW.put_attempt_id AND NOT checker_output_custody_sealed;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        r"""
CREATE FUNCTION public.guard_checker_model_artifact_ancestry() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE effect checker_model_call_attempts%ROWTYPE;
        slot checker_model_call_slots%ROWTYPE;
        profile checker_model_profiles%ROWTYPE;
BEGIN
  IF NEW.model_call_attempt_id IS NULL THEN RETURN NEW; END IF;
  SELECT * INTO STRICT effect FROM checker_model_call_attempts WHERE id=NEW.model_call_attempt_id;
  SELECT * INTO STRICT slot FROM checker_model_call_slots WHERE id=effect.slot_id;
  SELECT * INTO STRICT profile FROM checker_model_profiles
    WHERE id=slot.profile_id AND profile_version=slot.profile_version
      AND profile_digest=slot.profile_digest;
  IF ROW(NEW.project_id,NEW.task_id,NEW.submission_id,NEW.submission_version)
       IS DISTINCT FROM ROW(slot.project_id,slot.task_id,slot.submission_id,slot.submission_version)
     OR NEW.checker_run_id IS NOT NULL
     OR NEW.media_type IS DISTINCT FROM 'application/json'
     OR NEW.byte_count < 1
     OR (NEW.logical_role='model_request' AND
          (NEW.sha256 IS DISTINCT FROM effect.request_sha256
           OR NEW.byte_count > profile.maximum_request_bytes))
     OR (NEW.logical_role='model_response' AND
          (effect.state NOT IN ('dispatching','uncertain','completed','known_failed')
           OR NEW.byte_count > profile.maximum_response_bytes
           OR (effect.response_content_sha256 IS NOT NULL
                AND NEW.sha256 IS DISTINCT FROM effect.response_content_sha256)))
     OR NEW.logical_role NOT IN ('model_request','model_response') THEN
    RAISE EXCEPTION 'model artifact call ancestry mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
        """
    )
    op.execute(
        r"""
CREATE TRIGGER checker_model_artifact_ancestry BEFORE INSERT ON artifact_put_attempts
FOR EACH ROW EXECUTE FUNCTION public.guard_checker_model_artifact_ancestry()
        """
    )


def _upgrade_authorization_vocabulary() -> None:
    """Admit exactly the new model actions and permissions in retained audit custody."""
    op.execute("LOCK TABLE public.audit_events IN ACCESS EXCLUSIVE MODE")
    name = "ck_audit_events_authorization_action_evidence"
    definition = (
        op.get_bind()
        .execute(
            text(
                "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
                "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
            ),
            {"name": name},
        )
        .scalar_one()
    )
    anchor = (
        "(((action_id)::text = 'contribution.compensation_unit.create'::text) AND "
        "((permission_id)::text = 'compensation.policy.manage'::text))"
    )
    actions = (
        ("checker.model_call.prepare", "checker.model_call.prepare"),
        ("checker.model_call.dispatch", "checker.model_call.dispatch"),
        ("checker.model_call.recover", "checker.model_call.recover"),
        ("checker.model_call.observe", "checker.model_call.observe"),
        ("checker.model_call.complete", "checker.model_call.complete"),
        ("checker.model_call.grant", "checker.model_call.grant"),
        ("project.model_profile.provision", "project.model_profile.manage"),
        ("project.model_budget.configure", "project.model_budget.manage"),
        (
            "project.model_call.recovery_child.authorize",
            "project.model_call.recovery_child.authorize",
        ),
    )
    if definition.count(anchor) != 2 or any(action in definition for action, _ in actions):
        raise RuntimeError("model-call audit action constraint shape changed")
    addition = "".join(
        f" OR (((action_id)::text = '{action}'::text) AND "
        f"((permission_id)::text = '{permission}'::text))"
        for action, permission in actions
    )
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute(
        "ALTER TABLE public.audit_events ADD CONSTRAINT "
        + name
        + " "
        + definition.replace(anchor, anchor + addition)
    )

    name = "ck_audit_events_authority_registries"
    definition = (
        op.get_bind()
        .execute(
            text(
                "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
                "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
            ),
            {"name": name},
        )
        .scalar_one()
    )
    anchor = "('task.revision.recover'::character varying)::text"
    permissions = tuple(dict.fromkeys(permission for _, permission in actions))
    if definition.count(anchor) != 1 or any(
        f"('{permission}'::character varying)::text" in definition for permission in permissions
    ):
        raise RuntimeError("model-call audit permission registry shape changed")
    addition = "".join(f", ('{permission}'::character varying)::text" for permission in permissions)
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute(
        "ALTER TABLE public.audit_events ADD CONSTRAINT "
        + name
        + " "
        + definition.replace(anchor, anchor + addition)
    )


def downgrade() -> None:
    """Refuse removal of retained paid-call and budget evidence."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


_TABLES = (
    r"""
CREATE TABLE public.checker_model_profiles (
 id uuid NOT NULL,
 project_id uuid NOT NULL,
 profile_version integer NOT NULL,
 profile_digest varchar(71) NOT NULL,
 registry_entry_id uuid NOT NULL,
 registry_entry_digest varchar(71) NOT NULL,
 provider varchar(160) NOT NULL,
 api varchar(160) NOT NULL,
 model_snapshot varchar(160) NOT NULL,
 generation_settings jsonb NOT NULL,
 maximum_request_bytes integer NOT NULL,
 maximum_output_bytes integer NOT NULL,
 maximum_response_bytes integer NOT NULL,
 maximum_input_tokens integer NOT NULL,
 maximum_output_tokens integer NOT NULL,
 deadline_ms integer NOT NULL,
 call_slots integer NOT NULL,
 pricing_policy_id uuid NOT NULL,
 pricing_policy_version integer NOT NULL,
 pricing_policy_digest varchar(71) NOT NULL,
 uncached_input_rate bigint NOT NULL,
 cached_input_rate bigint NOT NULL,
 output_rate bigint NOT NULL,
 operation_id uuid NOT NULL,
 actor_profile_id uuid NOT NULL,
 authorization_evidence_id uuid NOT NULL,
 created_at timestamptz DEFAULT clock_timestamp() NOT NULL,
 CONSTRAINT pk_checker_model_profiles PRIMARY KEY(id),
 CONSTRAINT ck_checker_model_profiles_id_uuid7 CHECK (
  (get_byte(uuid_send(id),6)>>4)=7 AND (get_byte(uuid_send(id),8)&192)=128),
 CONSTRAINT ck_checker_model_profiles_digests CHECK (
  profile_digest ~ '^sha256:[0-9a-f]{64}$' AND
  registry_entry_digest ~ '^sha256:[0-9a-f]{64}$' AND
  pricing_policy_digest ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT ck_checker_model_profiles_identifiers CHECK (
  provider='openai_responses' AND api='responses.v1' AND
  model_snapshot ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$'),
 CONSTRAINT ck_checker_model_profiles_settings CHECK (
  generation_settings = jsonb_build_object(
   'reasoning_effort',generation_settings->>'reasoning_effort',
   'text_verbosity',generation_settings->>'text_verbosity') AND
  generation_settings->>'reasoning_effort' IN
   ('none','minimal','low','medium','high','xhigh','max') AND
  generation_settings->>'text_verbosity' IN ('low','medium','high')),
 CONSTRAINT ck_checker_model_profiles_bounds CHECK (
  profile_version>0 AND pricing_policy_version>0 AND call_slots=1 AND
  maximum_request_bytes BETWEEN 1 AND 1048576 AND
  maximum_output_bytes BETWEEN 1 AND 1048576 AND
  maximum_response_bytes BETWEEN 1 AND 1048576 AND
  maximum_response_bytes >= 6 * maximum_output_bytes + 4096 AND
  maximum_input_tokens BETWEEN 1 AND 10000000 AND
  maximum_output_tokens BETWEEN 1 AND 10000000 AND
  deadline_ms BETWEEN 100 AND 3600000 AND
  uncached_input_rate>=0 AND cached_input_rate>=0 AND output_rate>=0 AND
  greatest(uncached_input_rate,cached_input_rate,output_rate)>0 AND
  maximum_input_tokens::numeric *
   greatest(uncached_input_rate,cached_input_rate)::numeric +
   maximum_output_tokens::numeric * output_rate::numeric BETWEEN 1 AND 9000000000000000000),
 CONSTRAINT uq_checker_model_profiles_version UNIQUE(project_id,profile_version),
 CONSTRAINT uq_checker_model_profiles_identity UNIQUE(id,profile_version,profile_digest),
 CONSTRAINT uq_checker_model_profiles_digest UNIQUE(profile_digest),
 CONSTRAINT uq_checker_model_profiles_operation UNIQUE(operation_id),
 CONSTRAINT uq_checker_model_profiles_authority UNIQUE(authorization_evidence_id),
 CONSTRAINT fk_checker_model_profiles_project FOREIGN KEY(project_id)
  REFERENCES public.projects(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_profiles_registry FOREIGN KEY(registry_entry_id)
  REFERENCES public.external_checker_registry_entries(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_profiles_actor FOREIGN KEY(actor_profile_id)
  REFERENCES public.actor_profiles(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_profiles_authority FOREIGN KEY(authorization_evidence_id)
  REFERENCES public.audit_events(id) ON DELETE RESTRICT
)
""",
    r"""
CREATE TABLE public.checker_model_budget_configurations (
 id uuid NOT NULL,
 project_id uuid NOT NULL,
 configuration_version integer NOT NULL,
 configuration_digest varchar(71) NOT NULL,
 lifetime_limit_nanodollars bigint NOT NULL,
 operation_id uuid NOT NULL,
 actor_profile_id uuid NOT NULL,
 authorization_evidence_id uuid NOT NULL,
 created_at timestamptz DEFAULT clock_timestamp() NOT NULL,
 CONSTRAINT pk_checker_model_budget_configurations PRIMARY KEY(id),
 CONSTRAINT ck_checker_model_budget_configurations_id_uuid7 CHECK (
  (get_byte(uuid_send(id),6)>>4)=7 AND (get_byte(uuid_send(id),8)&192)=128),
 CONSTRAINT ck_checker_model_budget_configurations_values CHECK (
  configuration_version>0 AND lifetime_limit_nanodollars>0 AND
  configuration_digest ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT uq_checker_model_budget_configurations_version
  UNIQUE(project_id,configuration_version),
 CONSTRAINT uq_checker_model_budget_configurations_identity
  UNIQUE(id,project_id,configuration_version,configuration_digest),
 CONSTRAINT uq_checker_model_budget_configurations_attempt_identity
  UNIQUE(id,configuration_version,configuration_digest),
 CONSTRAINT uq_checker_model_budget_configurations_id_project UNIQUE(id,project_id),
 CONSTRAINT uq_checker_model_budget_configurations_digest UNIQUE(configuration_digest),
 CONSTRAINT uq_checker_model_budget_configurations_operation UNIQUE(operation_id),
 CONSTRAINT uq_checker_model_budget_configurations_authority
  UNIQUE(authorization_evidence_id),
 CONSTRAINT fk_checker_model_budget_configurations_project FOREIGN KEY(project_id)
  REFERENCES public.projects(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_budget_configurations_actor FOREIGN KEY(actor_profile_id)
  REFERENCES public.actor_profiles(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_budget_configurations_authority
  FOREIGN KEY(authorization_evidence_id)
  REFERENCES public.audit_events(id) ON DELETE RESTRICT
)
""",
    r"""
CREATE TABLE public.checker_model_budget_accounts (
 project_id uuid NOT NULL,
 current_configuration_id uuid NOT NULL,
 lifetime_reserved_nanodollars bigint DEFAULT 0 NOT NULL,
 lifetime_settled_nanodollars bigint DEFAULT 0 NOT NULL,
 CONSTRAINT pk_checker_model_budget_accounts PRIMARY KEY(project_id),
 CONSTRAINT uq_checker_model_budget_accounts_configuration
  UNIQUE(current_configuration_id),
 CONSTRAINT ck_checker_model_budget_accounts_values CHECK (
  lifetime_reserved_nanodollars>=0 AND lifetime_settled_nanodollars>=0 AND
  lifetime_reserved_nanodollars::numeric+lifetime_settled_nanodollars::numeric
   <=9000000000000000000),
 CONSTRAINT fk_checker_model_budget_accounts_project FOREIGN KEY(project_id)
  REFERENCES public.projects(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_budget_accounts_configuration
  FOREIGN KEY(current_configuration_id,project_id)
  REFERENCES public.checker_model_budget_configurations(id,project_id)
  ON DELETE RESTRICT
)
""",
    r"""
CREATE TABLE public.checker_model_call_slots (
 id uuid NOT NULL,
 project_id uuid NOT NULL,
 task_id uuid NOT NULL,
 assignment_id uuid NOT NULL,
 submission_id uuid NOT NULL,
 submission_version integer NOT NULL,
 requirement_id varchar(100) NOT NULL,
 registry_entry_digest varchar(71) NOT NULL,
 configuration_sha256 varchar(71) NOT NULL,
 profile_id uuid NOT NULL,
 profile_version integer NOT NULL,
 profile_digest varchar(71) NOT NULL,
 slot_index integer NOT NULL,
 first_request_sha256 varchar(71) NOT NULL,
 created_at timestamptz DEFAULT clock_timestamp() NOT NULL,
 CONSTRAINT pk_checker_model_call_slots PRIMARY KEY(id),
 CONSTRAINT ck_checker_model_call_slots_id_uuid7 CHECK (
  (get_byte(uuid_send(id),6)>>4)=7 AND (get_byte(uuid_send(id),8)&192)=128),
 CONSTRAINT ck_checker_model_call_slots_values CHECK (
  submission_version>0 AND profile_version>0 AND slot_index=0 AND
  requirement_id ~ '^[a-z][a-z0-9_.-]{0,99}$' AND
  registry_entry_digest ~ '^sha256:[0-9a-f]{64}$' AND
  configuration_sha256 ~ '^sha256:[0-9a-f]{64}$' AND
  profile_digest ~ '^sha256:[0-9a-f]{64}$' AND
  first_request_sha256 ~ '^sha256:[0-9a-f]{64}$'),
 CONSTRAINT uq_checker_model_call_slots_stable_identity UNIQUE(
  project_id,assignment_id,submission_id,submission_version,requirement_id,
  registry_entry_digest,configuration_sha256,profile_id,profile_version,
  profile_digest,slot_index),
 CONSTRAINT fk_checker_model_call_slots_project FOREIGN KEY(project_id)
  REFERENCES public.projects(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_slots_task_project FOREIGN KEY(task_id,project_id)
  REFERENCES public.workstream_tasks(id,project_id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_slots_assignment FOREIGN KEY(assignment_id)
  REFERENCES public.task_assignments(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_slots_submission FOREIGN KEY(
  submission_id,task_id,submission_version)
  REFERENCES public.submissions(id,task_id,version) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_slots_profile FOREIGN KEY(
  profile_id,profile_version,profile_digest)
  REFERENCES public.checker_model_profiles(id,profile_version,profile_digest)
  ON DELETE RESTRICT
)
""",
    r"""
CREATE TABLE public.checker_model_call_attempts (
 id uuid NOT NULL,
 slot_id uuid NOT NULL,
 attempt_number integer NOT NULL,
 internal_call_request_id uuid NOT NULL,
 parent_attempt_id uuid,
 request_sha256 varchar(71) NOT NULL,
 state varchar(32) NOT NULL,
 prepared_authorization_evidence_id uuid NOT NULL,
 request_binding_id uuid,
 request_content_id uuid,
 request_put_attempt_id uuid,
 request_verification_receipt_id uuid,
 request_content_sha256 varchar(71),
 request_byte_count integer,
 budget_configuration_id uuid,
 budget_configuration_version integer,
 budget_configuration_digest varchar(71),
 reserved_nanodollars bigint,
 dispatch_authorization_evidence_id uuid,
 provider_response_id varchar(256),
 response_binding_id uuid,
 response_content_id uuid,
 response_put_attempt_id uuid,
 response_verification_receipt_id uuid,
 response_content_sha256 varchar(71),
 response_byte_count integer,
 input_tokens integer,
 cached_input_tokens integer,
 output_tokens integer,
 reasoning_tokens integer,
 settled_nanodollars bigint,
 settlement_authorization_evidence_id uuid,
 settled_at timestamptz,
 no_effect_proof_id uuid,
 no_effect_proof_digest varchar(71),
 no_effect_observed_at timestamptz,
 terminal_authorization_evidence_id uuid,
 uncertainty_digest varchar(71),
 observation_authorization_evidence_id uuid,
 prepared_at timestamptz DEFAULT clock_timestamp() NOT NULL,
 dispatched_at timestamptz,
 terminal_at timestamptz,
 CONSTRAINT pk_checker_model_call_attempts PRIMARY KEY(id),
 CONSTRAINT ck_checker_model_call_attempts_id_uuid7 CHECK (
  (get_byte(uuid_send(id),6)>>4)=7 AND (get_byte(uuid_send(id),8)&192)=128),
 CONSTRAINT ck_checker_model_call_attempts_internal_id_uuid7 CHECK (
  (get_byte(uuid_send(internal_call_request_id),6)>>4)=7 AND
  (get_byte(uuid_send(internal_call_request_id),8)&192)=128),
 CONSTRAINT ck_checker_model_call_attempts_values CHECK (
  attempt_number>0 AND request_sha256 ~ '^sha256:[0-9a-f]{64}$' AND
  state IN ('prepared','dispatching','uncertain','completed','known_failed','known_no_effect') AND
  (provider_response_id IS NULL OR
   provider_response_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$') AND
  (reserved_nanodollars IS NULL OR reserved_nanodollars>0) AND
  (settled_nanodollars IS NULL OR settled_nanodollars>=0)),
 CONSTRAINT uq_checker_model_call_attempts_number UNIQUE(slot_id,attempt_number),
 CONSTRAINT uq_checker_model_call_attempts_internal_request UNIQUE(internal_call_request_id),
 CONSTRAINT uq_checker_model_call_attempts_prepare_authority
  UNIQUE(prepared_authorization_evidence_id),
 CONSTRAINT uq_checker_model_call_attempts_dispatch_authority
  UNIQUE(dispatch_authorization_evidence_id),
 CONSTRAINT uq_checker_model_call_attempts_observation_authority
  UNIQUE(observation_authorization_evidence_id),
 CONSTRAINT uq_checker_model_call_attempts_terminal_authority
  UNIQUE(terminal_authorization_evidence_id),
 CONSTRAINT uq_checker_model_call_attempts_settlement_authority
  UNIQUE(settlement_authorization_evidence_id),
 CONSTRAINT fk_checker_model_call_attempts_slot FOREIGN KEY(slot_id)
  REFERENCES public.checker_model_call_slots(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_parent FOREIGN KEY(parent_attempt_id)
  REFERENCES public.checker_model_call_attempts(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_budget FOREIGN KEY(
  budget_configuration_id,budget_configuration_version,budget_configuration_digest)
  REFERENCES public.checker_model_budget_configurations(
   id,configuration_version,configuration_digest) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_prepare_authority
  FOREIGN KEY(prepared_authorization_evidence_id)
  REFERENCES public.audit_events(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_dispatch_authority
  FOREIGN KEY(dispatch_authorization_evidence_id)
  REFERENCES public.audit_events(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_observation_authority
  FOREIGN KEY(observation_authorization_evidence_id)
  REFERENCES public.audit_events(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_terminal_authority
  FOREIGN KEY(terminal_authorization_evidence_id)
  REFERENCES public.audit_events(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_settlement_authority
  FOREIGN KEY(settlement_authorization_evidence_id)
  REFERENCES public.audit_events(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_request_binding FOREIGN KEY(request_binding_id)
  REFERENCES public.artifact_bindings(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_request_content FOREIGN KEY(request_content_id)
  REFERENCES public.artifact_contents(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_request_put FOREIGN KEY(request_put_attempt_id)
  REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_request_verification
  FOREIGN KEY(request_verification_receipt_id)
  REFERENCES public.artifact_verification_receipts(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_response_binding FOREIGN KEY(response_binding_id)
  REFERENCES public.artifact_bindings(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_response_content FOREIGN KEY(response_content_id)
  REFERENCES public.artifact_contents(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_response_put FOREIGN KEY(response_put_attempt_id)
  REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_attempts_response_verification
  FOREIGN KEY(response_verification_receipt_id)
  REFERENCES public.artifact_verification_receipts(id) ON DELETE RESTRICT
)
""",
    r"""
CREATE TABLE public.checker_model_call_recoveries (
 id uuid NOT NULL,
 attempt_id uuid NOT NULL,
 checker_run_id uuid NOT NULL,
 worker_lease_id uuid NOT NULL,
 worker_lease_generation integer NOT NULL,
 authorization_evidence_id uuid NOT NULL,
 created_at timestamptz DEFAULT clock_timestamp() NOT NULL,
 CONSTRAINT pk_checker_model_call_recoveries PRIMARY KEY(id),
 CONSTRAINT ck_checker_model_call_recoveries_id_uuid7 CHECK (
  (get_byte(uuid_send(id),6)>>4)=7 AND (get_byte(uuid_send(id),8)&192)=128),
 CONSTRAINT ck_checker_model_call_recoveries_generation CHECK(worker_lease_generation>0),
 CONSTRAINT uq_checker_model_call_recoveries_attachment UNIQUE(
  attempt_id,checker_run_id,worker_lease_id,worker_lease_generation),
 CONSTRAINT uq_checker_model_call_recoveries_authority UNIQUE(authorization_evidence_id),
 CONSTRAINT fk_checker_model_call_recoveries_attempt FOREIGN KEY(attempt_id)
  REFERENCES public.checker_model_call_attempts(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_recoveries_run FOREIGN KEY(checker_run_id)
  REFERENCES public.checker_runs(id) ON DELETE RESTRICT,
 CONSTRAINT fk_checker_model_call_recoveries_authority FOREIGN KEY(authorization_evidence_id)
  REFERENCES public.audit_events(id) ON DELETE RESTRICT
)
""",
)


_FUNCTIONS = (
    r"""
CREATE FUNCTION public.checker_model_canonical_json(value jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE encoded text;
BEGIN
 CASE pg_catalog.jsonb_typeof(value)
  WHEN 'object' THEN
   SELECT '{'||coalesce(pg_catalog.string_agg(
    pg_catalog.to_json(item_key)::text||':'||public.checker_model_canonical_json(item_value),
    ',' ORDER BY item_key COLLATE "C"),'')||'}' INTO encoded
   FROM pg_catalog.jsonb_each(value) AS items(item_key,item_value);
   RETURN encoded;
  WHEN 'array' THEN
   SELECT '['||coalesce(pg_catalog.string_agg(
    public.checker_model_canonical_json(item_value),',' ORDER BY item_order),'')||']'
   INTO encoded FROM pg_catalog.jsonb_array_elements(value) WITH ORDINALITY
    AS items(item_value,item_order);
   RETURN encoded;
  ELSE RETURN value::text;
 END CASE;
END $$
""",
    r"""
CREATE FUNCTION public.checker_model_json_digest(value jsonb) RETURNS varchar
LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT 'sha256:'||pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
  public.checker_model_canonical_json(value),'UTF8')),'hex')
$$
""",
    r"""
CREATE FUNCTION public.checker_model_profile_authority_digest(
 r public.checker_model_profiles
) RETURNS varchar LANGUAGE sql IMMUTABLE STRICT
SET search_path=pg_catalog,public,pg_temp AS $$
 WITH facts(value) AS (SELECT pg_catalog.jsonb_build_object(
  'operation_id',r.operation_id,'actor_profile_id',r.actor_profile_id,
  'spec',pg_catalog.jsonb_build_object(
   'project_id',r.project_id,'profile_version',r.profile_version,
   'registry_entry_id',r.registry_entry_id,
   'registry_entry_digest',r.registry_entry_digest,'provider',r.provider,
   'api',r.api,'model_snapshot',r.model_snapshot,'settings',r.generation_settings,
   'maximum_request_bytes',r.maximum_request_bytes,
   'maximum_output_bytes',r.maximum_output_bytes,
   'maximum_response_bytes',r.maximum_response_bytes,
   'maximum_input_tokens',r.maximum_input_tokens,
   'maximum_output_tokens',r.maximum_output_tokens,'deadline_ms',r.deadline_ms,
   'call_slots',r.call_slots,'pricing',pg_catalog.jsonb_build_object(
    'pricing_policy_id',r.pricing_policy_id,
    'pricing_policy_version',r.pricing_policy_version,
    'pricing_policy_digest',r.pricing_policy_digest,
    'uncached_input_nanodollars_per_token',r.uncached_input_rate,
    'cached_input_nanodollars_per_token',r.cached_input_rate,
    'output_nanodollars_per_token',r.output_rate)),
  'profile_digest',r.profile_digest))
 SELECT public.checker_model_json_digest(pg_catalog.jsonb_build_object(
  'resource_context',pg_catalog.jsonb_build_object(
   'resource_type','project_model_administration','resource_id',r.operation_id,
   'project_id',r.project_id,'actor_profile_id',r.actor_profile_id,
   'action_id','project.model_profile.provision','facts',facts.value,
   'facts_digest',public.checker_model_json_digest(pg_catalog.jsonb_build_object(
    'action','project.model_profile.provision','facts',facts.value))))) FROM facts
$$
""",
    r"""
CREATE FUNCTION public.checker_model_budget_authority_digest(
 r public.checker_model_budget_configurations
) RETURNS varchar LANGUAGE sql IMMUTABLE STRICT
SET search_path=pg_catalog,public,pg_temp AS $$
 WITH facts(value) AS (SELECT pg_catalog.jsonb_build_object(
  'operation_id',r.operation_id,'actor_profile_id',r.actor_profile_id,
  'spec',pg_catalog.jsonb_build_object('project_id',r.project_id,
   'configuration_version',r.configuration_version,
   'lifetime_limit_nanodollars',r.lifetime_limit_nanodollars),
  'configuration_digest',r.configuration_digest))
 SELECT public.checker_model_json_digest(pg_catalog.jsonb_build_object(
  'resource_context',pg_catalog.jsonb_build_object(
   'resource_type','project_model_administration','resource_id',r.operation_id,
   'project_id',r.project_id,'actor_profile_id',r.actor_profile_id,
   'action_id','project.model_budget.configure','facts',facts.value,
   'facts_digest',public.checker_model_json_digest(pg_catalog.jsonb_build_object(
    'action','project.model_budget.configure','facts',facts.value))))) FROM facts
$$
""",
    r"""
CREATE FUNCTION public.guard_checker_model_profile() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE expected_version integer;
DECLARE authority public.audit_events%ROWTYPE;
DECLARE registry_digest varchar;
DECLARE registry_phase varchar;
BEGIN
 IF TG_OP<>'INSERT' THEN
  RAISE EXCEPTION 'checker model profiles are immutable' USING ERRCODE='55000';
 END IF;
 IF NEW.profile_digest<>public.checker_model_json_digest(
   pg_catalog.jsonb_build_object(
    'project_id',NEW.project_id,'profile_version',NEW.profile_version,
    'registry_entry_id',NEW.registry_entry_id,
    'registry_entry_digest',NEW.registry_entry_digest,
    'provider',NEW.provider,'api',NEW.api,
    'model_snapshot',NEW.model_snapshot,'settings',NEW.generation_settings,
    'maximum_request_bytes',NEW.maximum_request_bytes,
    'maximum_output_bytes',NEW.maximum_output_bytes,
    'maximum_response_bytes',NEW.maximum_response_bytes,
    'maximum_input_tokens',NEW.maximum_input_tokens,
    'maximum_output_tokens',NEW.maximum_output_tokens,
    'deadline_ms',NEW.deadline_ms,'call_slots',NEW.call_slots,
    'pricing',pg_catalog.jsonb_build_object(
     'pricing_policy_id',NEW.pricing_policy_id,
     'pricing_policy_version',NEW.pricing_policy_version,
     'pricing_policy_digest',NEW.pricing_policy_digest,
     'uncached_input_nanodollars_per_token',NEW.uncached_input_rate,
     'cached_input_nanodollars_per_token',NEW.cached_input_rate,
     'output_nanodollars_per_token',NEW.output_rate))) THEN
  RAISE EXCEPTION 'checker model profile digest is invalid' USING ERRCODE='23514';
 END IF;
 SELECT * INTO authority FROM public.audit_events
  WHERE id=NEW.authorization_evidence_id FOR SHARE;
 IF authority.id IS NULL OR authority.event_domain<>'authority' OR
    authority.event_type<>'SensitiveAuthorizationAllowed' OR
    authority.actor_ref_kind<>'actor_profile' OR
    authority.actor_id<>NEW.actor_profile_id::text OR
    authority.action_id<>'project.model_profile.provision' OR
    authority.permission_id<>'project.model_profile.manage' OR
    authority.denial_code IS NOT NULL OR
    authority.after_facts::jsonb<>pg_catalog.jsonb_build_object(
     'allowed',true,'resource_context_digest',
     public.checker_model_profile_authority_digest(NEW)) THEN
  RAISE EXCEPTION 'checker model profile authority is invalid' USING ERRCODE='23514';
 END IF;
 SELECT entry_digest,phase INTO registry_digest,registry_phase
  FROM public.external_checker_registry_entries WHERE id=NEW.registry_entry_id FOR SHARE;
 IF registry_digest IS DISTINCT FROM NEW.registry_entry_digest OR
    registry_phase IS DISTINCT FROM 'post_submit' THEN
  RAISE EXCEPTION 'checker model profile registry binding is invalid' USING ERRCODE='23514';
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('checker-model-profile:'||NEW.project_id,0));
 SELECT coalesce(max(profile_version),0)+1 INTO expected_version
  FROM public.checker_model_profiles WHERE project_id=NEW.project_id;
 IF NEW.profile_version<>expected_version THEN
  RAISE EXCEPTION 'checker model profile version is not sequential' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$
""",
    r"""
CREATE FUNCTION public.guard_checker_model_budget_configuration() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE account public.checker_model_budget_accounts%ROWTYPE;
DECLARE current_version integer;
DECLARE authority public.audit_events%ROWTYPE;
BEGIN
 IF TG_OP<>'INSERT' THEN
  RAISE EXCEPTION 'checker model budget configurations are immutable' USING ERRCODE='55000';
 END IF;
 IF NEW.configuration_digest<>public.checker_model_json_digest(
   pg_catalog.jsonb_build_object(
    'project_id',NEW.project_id,
    'configuration_version',NEW.configuration_version,
    'lifetime_limit_nanodollars',NEW.lifetime_limit_nanodollars)) THEN
  RAISE EXCEPTION 'checker model budget configuration digest is invalid'
   USING ERRCODE='23514';
 END IF;
 SELECT * INTO authority FROM public.audit_events
  WHERE id=NEW.authorization_evidence_id FOR SHARE;
 IF authority.id IS NULL OR authority.event_domain<>'authority' OR
    authority.event_type<>'SensitiveAuthorizationAllowed' OR
    authority.actor_ref_kind<>'actor_profile' OR
    authority.actor_id<>NEW.actor_profile_id::text OR
    authority.action_id<>'project.model_budget.configure' OR
    authority.permission_id<>'project.model_budget.manage' OR
    authority.denial_code IS NOT NULL OR
    authority.after_facts::jsonb<>pg_catalog.jsonb_build_object(
     'allowed',true,'resource_context_digest',
     public.checker_model_budget_authority_digest(NEW)) THEN
  RAISE EXCEPTION 'checker model budget authority is invalid' USING ERRCODE='23514';
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('checker-model-budget:'||NEW.project_id,0));
 SELECT * INTO account FROM public.checker_model_budget_accounts
  WHERE project_id=NEW.project_id FOR UPDATE;
 IF account.project_id IS NULL THEN
  IF NEW.configuration_version<>1 THEN
   RAISE EXCEPTION 'initial checker model budget version must be one' USING ERRCODE='23514';
  END IF;
 ELSE
  SELECT configuration_version INTO current_version
   FROM public.checker_model_budget_configurations
   WHERE id=account.current_configuration_id;
  IF NEW.configuration_version<>current_version+1 OR
     NEW.lifetime_limit_nanodollars<
      account.lifetime_reserved_nanodollars+account.lifetime_settled_nanodollars THEN
   RAISE EXCEPTION 'invalid checker model budget adjustment' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$
""",
    r"""
CREATE FUNCTION public.guard_checker_model_budget_account() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE chosen public.checker_model_budget_configurations%ROWTYPE;
DECLARE prior public.checker_model_budget_configurations%ROWTYPE;
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'checker model budget accounts cannot be deleted' USING ERRCODE='55000';
 END IF;
 SELECT * INTO chosen FROM public.checker_model_budget_configurations
  WHERE id=NEW.current_configuration_id AND project_id=NEW.project_id FOR SHARE;
 IF chosen.id IS NULL OR
    NEW.lifetime_reserved_nanodollars+NEW.lifetime_settled_nanodollars>
     chosen.lifetime_limit_nanodollars THEN
  RAISE EXCEPTION 'checker model budget ceiling exceeded' USING ERRCODE='23514';
 END IF;
 IF TG_OP='INSERT' THEN
  IF chosen.configuration_version<>1 OR NEW.lifetime_reserved_nanodollars<>0 OR
     NEW.lifetime_settled_nanodollars<>0 THEN
   RAISE EXCEPTION 'invalid initial checker model budget account' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
 END IF;
 IF NEW.project_id<>OLD.project_id THEN
  RAISE EXCEPTION 'checker model budget project is immutable' USING ERRCODE='55000';
 END IF;
 IF NEW.current_configuration_id<>OLD.current_configuration_id THEN
  SELECT * INTO prior FROM public.checker_model_budget_configurations
   WHERE id=OLD.current_configuration_id FOR SHARE;
  IF ROW(NEW.lifetime_reserved_nanodollars,NEW.lifetime_settled_nanodollars)
      IS DISTINCT FROM
     ROW(OLD.lifetime_reserved_nanodollars,OLD.lifetime_settled_nanodollars) OR
     chosen.configuration_version<>prior.configuration_version+1 THEN
   RAISE EXCEPTION 'invalid checker model budget pointer transition' USING ERRCODE='23514';
  END IF;
 ELSIF NOT (
   (NEW.lifetime_reserved_nanodollars>OLD.lifetime_reserved_nanodollars AND
    NEW.lifetime_settled_nanodollars=OLD.lifetime_settled_nanodollars) OR
   (NEW.lifetime_reserved_nanodollars<OLD.lifetime_reserved_nanodollars AND
    NEW.lifetime_settled_nanodollars>=OLD.lifetime_settled_nanodollars AND
    NEW.lifetime_settled_nanodollars-OLD.lifetime_settled_nanodollars<=
     OLD.lifetime_reserved_nanodollars-NEW.lifetime_reserved_nanodollars)
  ) THEN
  RAISE EXCEPTION 'invalid checker model budget counter transition' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$
""",
    r"""
CREATE FUNCTION public.guard_checker_model_call_slot() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE assignment_task uuid;
DECLARE assignment_project uuid;
DECLARE profile public.checker_model_profiles%ROWTYPE;
BEGIN
 IF TG_OP<>'INSERT' THEN
  RAISE EXCEPTION 'checker model call slots are immutable' USING ERRCODE='55000';
 END IF;
 SELECT task_id,project_id INTO assignment_task,assignment_project
  FROM public.task_assignments WHERE id=NEW.assignment_id FOR SHARE;
 SELECT * INTO profile FROM public.checker_model_profiles WHERE
  id=NEW.profile_id AND profile_version=NEW.profile_version AND
  profile_digest=NEW.profile_digest FOR SHARE;
 IF assignment_task IS DISTINCT FROM NEW.task_id OR
    assignment_project IS DISTINCT FROM NEW.project_id OR profile.id IS NULL OR
    profile.project_id<>NEW.project_id OR
    profile.registry_entry_digest<>NEW.registry_entry_digest THEN
  RAISE EXCEPTION 'invalid checker model call slot ownership' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$
""",
    r"""
CREATE FUNCTION public.guard_checker_model_call_attempt() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE slot public.checker_model_call_slots%ROWTYPE;
DECLARE profile public.checker_model_profiles%ROWTYPE;
DECLARE budget public.checker_model_budget_configurations%ROWTYPE;
DECLARE account public.checker_model_budget_accounts%ROWTYPE;
DECLARE parent public.checker_model_call_attempts%ROWTYPE;
DECLARE maximum_reservation numeric;
DECLARE exact_cost numeric;
DECLARE request_complete boolean;
DECLARE response_complete boolean;
DECLARE usage_complete boolean;
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'checker model call attempts cannot be deleted' USING ERRCODE='55000';
 END IF;
 SELECT * INTO slot FROM public.checker_model_call_slots WHERE id=NEW.slot_id FOR SHARE;
 SELECT * INTO profile FROM public.checker_model_profiles WHERE id=slot.profile_id FOR SHARE;
 IF slot.id IS NULL OR profile.id IS NULL OR NEW.request_sha256<>slot.first_request_sha256 THEN
  RAISE EXCEPTION 'invalid checker model call attempt ownership' USING ERRCODE='23514';
 END IF;
 maximum_reservation := profile.maximum_input_tokens::numeric *
  greatest(profile.uncached_input_rate,profile.cached_input_rate)::numeric +
  profile.maximum_output_tokens::numeric * profile.output_rate::numeric;
 request_complete := NEW.request_binding_id IS NOT NULL AND NEW.request_content_id IS NOT NULL AND
  NEW.request_put_attempt_id IS NOT NULL AND NEW.request_verification_receipt_id IS NOT NULL AND
  NEW.request_content_sha256=NEW.request_sha256 AND
  NEW.request_byte_count BETWEEN 1 AND profile.maximum_request_bytes;
 response_complete := NEW.response_binding_id IS NOT NULL AND NEW.response_content_id IS NOT NULL AND
  NEW.response_put_attempt_id IS NOT NULL AND NEW.response_verification_receipt_id IS NOT NULL AND
  NEW.response_content_sha256 ~ '^sha256:[0-9a-f]{64}$' AND
  NEW.response_byte_count BETWEEN 1 AND profile.maximum_response_bytes;
 usage_complete := NEW.input_tokens IS NOT NULL AND NEW.cached_input_tokens IS NOT NULL AND
  NEW.output_tokens IS NOT NULL AND NEW.reasoning_tokens IS NOT NULL AND
  NEW.input_tokens BETWEEN 0 AND profile.maximum_input_tokens AND
  NEW.cached_input_tokens BETWEEN 0 AND NEW.input_tokens AND
  NEW.output_tokens BETWEEN 0 AND profile.maximum_output_tokens AND
  NEW.reasoning_tokens BETWEEN 0 AND NEW.output_tokens;
 IF usage_complete THEN
  exact_cost := (NEW.input_tokens-NEW.cached_input_tokens)::numeric *
   profile.uncached_input_rate::numeric + NEW.cached_input_tokens::numeric *
   profile.cached_input_rate::numeric + NEW.output_tokens::numeric *
   profile.output_rate::numeric;
 END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.attempt_number=1 THEN
   IF NEW.parent_attempt_id IS NOT NULL THEN
    RAISE EXCEPTION 'initial checker model attempt cannot have a parent' USING ERRCODE='23514';
   END IF;
  ELSE
   SELECT * INTO parent FROM public.checker_model_call_attempts
    WHERE id=NEW.parent_attempt_id FOR SHARE;
   IF parent.id IS NULL OR parent.slot_id<>NEW.slot_id OR
      parent.attempt_number+1<>NEW.attempt_number OR
      parent.attempt_number<>(SELECT max(attempt_number)
       FROM public.checker_model_call_attempts WHERE slot_id=NEW.slot_id) OR
      NOT (parent.state='known_no_effect' OR
       (parent.state='known_failed' AND parent.settled_nanodollars IS NOT NULL AND
        parent.settlement_authorization_evidence_id IS NOT NULL)) THEN
    RAISE EXCEPTION 'invalid checker model child attempt' USING ERRCODE='23514';
   END IF;
  END IF;
 ELSIF ROW(NEW.slot_id,NEW.attempt_number,NEW.internal_call_request_id,
             NEW.parent_attempt_id,NEW.request_sha256,
             NEW.prepared_authorization_evidence_id,NEW.prepared_at)
       IS DISTINCT FROM
       ROW(OLD.slot_id,OLD.attempt_number,OLD.internal_call_request_id,
             OLD.parent_attempt_id,OLD.request_sha256,
             OLD.prepared_authorization_evidence_id,OLD.prepared_at) THEN
  RAISE EXCEPTION 'checker model call attempt identity is immutable' USING ERRCODE='55000';
 END IF;
 IF TG_OP='UPDATE' AND OLD.state<>'prepared' AND
    ROW(NEW.request_binding_id,NEW.request_content_id,NEW.request_put_attempt_id,
        NEW.request_verification_receipt_id,NEW.request_content_sha256,
        NEW.request_byte_count,NEW.budget_configuration_id,
        NEW.budget_configuration_version,NEW.budget_configuration_digest,
        NEW.reserved_nanodollars,NEW.dispatch_authorization_evidence_id,
        NEW.dispatched_at)
    IS DISTINCT FROM
    ROW(OLD.request_binding_id,OLD.request_content_id,OLD.request_put_attempt_id,
        OLD.request_verification_receipt_id,OLD.request_content_sha256,
        OLD.request_byte_count,OLD.budget_configuration_id,
        OLD.budget_configuration_version,OLD.budget_configuration_digest,
        OLD.reserved_nanodollars,OLD.dispatch_authorization_evidence_id,
        OLD.dispatched_at) THEN
  RAISE EXCEPTION 'checker model dispatch facts are immutable' USING ERRCODE='55000';
 END IF;
 IF NEW.state='prepared' THEN
  IF TG_OP='UPDATE' OR NEW.request_binding_id IS NOT NULL OR
     NEW.request_content_id IS NOT NULL OR NEW.request_put_attempt_id IS NOT NULL OR
     NEW.request_verification_receipt_id IS NOT NULL OR
     NEW.request_content_sha256 IS NOT NULL OR NEW.request_byte_count IS NOT NULL OR
     NEW.budget_configuration_id IS NOT NULL OR
     NEW.budget_configuration_version IS NOT NULL OR
     NEW.budget_configuration_digest IS NOT NULL OR
     NEW.reserved_nanodollars IS NOT NULL OR
     NEW.dispatch_authorization_evidence_id IS NOT NULL OR
	    NEW.dispatched_at IS NOT NULL OR NEW.provider_response_id IS NOT NULL OR
	    NEW.response_binding_id IS NOT NULL OR NEW.response_content_id IS NOT NULL OR
	    NEW.response_put_attempt_id IS NOT NULL OR
	    NEW.response_verification_receipt_id IS NOT NULL OR
	    NEW.response_content_sha256 IS NOT NULL OR NEW.response_byte_count IS NOT NULL OR
	    NEW.input_tokens IS NOT NULL OR NEW.cached_input_tokens IS NOT NULL OR
	    NEW.output_tokens IS NOT NULL OR NEW.reasoning_tokens IS NOT NULL OR
	    NEW.settled_nanodollars IS NOT NULL OR
	    NEW.settlement_authorization_evidence_id IS NOT NULL OR NEW.settled_at IS NOT NULL OR
	    NEW.no_effect_proof_id IS NOT NULL OR NEW.no_effect_proof_digest IS NOT NULL OR
	    NEW.no_effect_observed_at IS NOT NULL OR
     NEW.terminal_authorization_evidence_id IS NOT NULL OR
     NEW.uncertainty_digest IS NOT NULL OR
     NEW.observation_authorization_evidence_id IS NOT NULL OR NEW.terminal_at IS NOT NULL THEN
   RAISE EXCEPTION 'invalid prepared checker model call' USING ERRCODE='23514';
  END IF;
 ELSE
  SELECT * INTO budget FROM public.checker_model_budget_configurations WHERE
   id=NEW.budget_configuration_id AND
   configuration_version=NEW.budget_configuration_version AND
   configuration_digest=NEW.budget_configuration_digest FOR SHARE;
  SELECT * INTO account FROM public.checker_model_budget_accounts
   WHERE project_id=slot.project_id FOR SHARE;
  IF NOT request_complete OR budget.id IS NULL OR budget.project_id<>slot.project_id OR
     (TG_OP='UPDATE' AND OLD.state='prepared' AND
      account.current_configuration_id IS DISTINCT FROM budget.id) OR
	     NEW.reserved_nanodollars IS NULL OR
	     NEW.reserved_nanodollars::numeric<>maximum_reservation OR
     NEW.dispatch_authorization_evidence_id IS NULL OR NEW.dispatched_at IS NULL THEN
   RAISE EXCEPTION 'invalid dispatched checker model call' USING ERRCODE='23514';
  END IF;
 END IF;
 IF NEW.state='dispatching' THEN
  IF NEW.provider_response_id IS NOT NULL OR NEW.uncertainty_digest IS NOT NULL OR
     NEW.observation_authorization_evidence_id IS NOT NULL OR
	    NEW.response_binding_id IS NOT NULL OR NEW.response_content_id IS NOT NULL OR
	    NEW.response_put_attempt_id IS NOT NULL OR
	    NEW.response_verification_receipt_id IS NOT NULL OR
	    NEW.response_content_sha256 IS NOT NULL OR NEW.response_byte_count IS NOT NULL OR
	    NEW.input_tokens IS NOT NULL OR NEW.cached_input_tokens IS NOT NULL OR
	    NEW.output_tokens IS NOT NULL OR NEW.reasoning_tokens IS NOT NULL OR
	    NEW.settled_nanodollars IS NOT NULL OR
	    NEW.settlement_authorization_evidence_id IS NOT NULL OR NEW.settled_at IS NOT NULL OR
	    NEW.no_effect_proof_id IS NOT NULL OR NEW.no_effect_proof_digest IS NOT NULL OR
	    NEW.no_effect_observed_at IS NOT NULL OR
	    NEW.terminal_authorization_evidence_id IS NOT NULL OR NEW.terminal_at IS NOT NULL THEN
   RAISE EXCEPTION 'invalid dispatching checker model call' USING ERRCODE='23514';
  END IF;
 ELSIF NEW.state='uncertain' THEN
  IF NEW.uncertainty_digest !~ '^sha256:[0-9a-f]{64}$' OR
     NEW.observation_authorization_evidence_id IS NULL OR
	    NEW.response_binding_id IS NOT NULL OR NEW.response_content_id IS NOT NULL OR
	    NEW.response_put_attempt_id IS NOT NULL OR
	    NEW.response_verification_receipt_id IS NOT NULL OR
	    NEW.response_content_sha256 IS NOT NULL OR NEW.response_byte_count IS NOT NULL OR
	    NEW.input_tokens IS NOT NULL OR NEW.cached_input_tokens IS NOT NULL OR
	    NEW.output_tokens IS NOT NULL OR NEW.reasoning_tokens IS NOT NULL OR
	    NEW.settled_nanodollars IS NOT NULL OR
	    NEW.settlement_authorization_evidence_id IS NOT NULL OR NEW.settled_at IS NOT NULL OR
	    NEW.no_effect_proof_id IS NOT NULL OR NEW.no_effect_proof_digest IS NOT NULL OR
	    NEW.no_effect_observed_at IS NOT NULL OR
	    NEW.terminal_authorization_evidence_id IS NOT NULL OR NEW.terminal_at IS NOT NULL THEN
   RAISE EXCEPTION 'invalid uncertain checker model call' USING ERRCODE='23514';
  END IF;
 ELSIF NEW.state='completed' THEN
  IF NEW.provider_response_id IS NULL OR NOT response_complete OR NOT usage_complete OR
	    NEW.settled_nanodollars IS NULL OR NEW.settled_nanodollars::numeric<>exact_cost OR
     NEW.terminal_authorization_evidence_id IS NULL OR NEW.terminal_at IS NULL OR
	    NEW.no_effect_proof_id IS NOT NULL OR NEW.no_effect_proof_digest IS NOT NULL OR
	    NEW.no_effect_observed_at IS NOT NULL OR
     NEW.settlement_authorization_evidence_id IS NOT NULL OR NEW.settled_at IS NOT NULL THEN
   RAISE EXCEPTION 'invalid completed checker model call' USING ERRCODE='23514';
  END IF;
 ELSIF NEW.state='known_failed' THEN
  IF NEW.provider_response_id IS NULL OR NOT response_complete OR
     NEW.terminal_authorization_evidence_id IS NULL OR NEW.terminal_at IS NULL OR
     NEW.no_effect_proof_id IS NOT NULL OR
	    NOT usage_complete OR NEW.settled_nanodollars IS NULL OR
	    NEW.settled_nanodollars::numeric<>exact_cost OR
     NEW.settlement_authorization_evidence_id IS NULL OR NEW.settled_at IS NULL THEN
   RAISE EXCEPTION 'invalid known-failed checker model call' USING ERRCODE='23514';
  END IF;
 ELSIF NEW.state='known_no_effect' THEN
  IF NEW.provider_response_id IS NOT NULL OR NEW.response_binding_id IS NOT NULL OR
     NEW.response_content_id IS NOT NULL OR NEW.response_put_attempt_id IS NOT NULL OR
     NEW.response_verification_receipt_id IS NOT NULL OR
     NEW.response_content_sha256 IS NOT NULL OR NEW.response_byte_count IS NOT NULL OR
     NEW.input_tokens IS NOT NULL OR NEW.cached_input_tokens IS NOT NULL OR
     NEW.output_tokens IS NOT NULL OR NEW.reasoning_tokens IS NOT NULL OR
     NEW.settled_nanodollars IS NOT NULL OR
     NEW.settlement_authorization_evidence_id IS NOT NULL OR NEW.settled_at IS NOT NULL OR
     NEW.no_effect_proof_id IS NULL OR
     NEW.no_effect_proof_digest !~ '^sha256:[0-9a-f]{64}$' OR
     NEW.no_effect_observed_at IS NULL OR
     NEW.terminal_authorization_evidence_id IS NULL OR NEW.terminal_at IS NULL THEN
   RAISE EXCEPTION 'invalid no-effect checker model call' USING ERRCODE='23514';
  END IF;
 END IF;
 IF TG_OP='UPDATE' AND OLD.state='uncertain' AND
    (NEW.uncertainty_digest IS DISTINCT FROM OLD.uncertainty_digest OR
     NEW.observation_authorization_evidence_id IS DISTINCT FROM
      OLD.observation_authorization_evidence_id OR
     (OLD.provider_response_id IS NOT NULL AND
      NEW.provider_response_id IS DISTINCT FROM OLD.provider_response_id)) THEN
  RAISE EXCEPTION 'checker model uncertainty facts are immutable' USING ERRCODE='55000';
 END IF;
 IF TG_OP='UPDATE' AND OLD.state='known_failed' AND
    ROW(NEW.provider_response_id,NEW.response_binding_id,NEW.response_content_id,
        NEW.response_put_attempt_id,NEW.response_verification_receipt_id,
        NEW.response_content_sha256,NEW.response_byte_count,
        NEW.no_effect_proof_id,NEW.no_effect_proof_digest,NEW.no_effect_observed_at,
        NEW.terminal_authorization_evidence_id,NEW.terminal_at,
        NEW.uncertainty_digest,NEW.observation_authorization_evidence_id)
    IS DISTINCT FROM
    ROW(OLD.provider_response_id,OLD.response_binding_id,OLD.response_content_id,
        OLD.response_put_attempt_id,OLD.response_verification_receipt_id,
        OLD.response_content_sha256,OLD.response_byte_count,
        OLD.no_effect_proof_id,OLD.no_effect_proof_digest,OLD.no_effect_observed_at,
        OLD.terminal_authorization_evidence_id,OLD.terminal_at,
        OLD.uncertainty_digest,OLD.observation_authorization_evidence_id) THEN
  RAISE EXCEPTION 'checker model terminal facts are immutable' USING ERRCODE='55000';
 END IF;
 IF TG_OP='UPDATE' AND NOT (
   (OLD.state='prepared' AND NEW.state='dispatching') OR
   (OLD.state='dispatching' AND NEW.state IN
    ('uncertain','completed','known_failed','known_no_effect')) OR
   (OLD.state='uncertain' AND NEW.state IN ('completed','known_failed','known_no_effect'))
  ) THEN
  RAISE EXCEPTION 'invalid checker model call state transition' USING ERRCODE='55000';
 END IF;
 RETURN NEW;
END $$
""",
    r"""
CREATE FUNCTION public.guard_checker_model_recovery() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_OP<>'INSERT' THEN
  RAISE EXCEPTION 'checker model recovery attachments are immutable' USING ERRCODE='55000';
 END IF;
 RETURN NEW;
END $$
""",
    r"""
CREATE FUNCTION public.reconcile_checker_model_budget() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE target_project uuid;
DECLARE account public.checker_model_budget_accounts%ROWTYPE;
DECLARE calculated_reserved numeric;
DECLARE calculated_settled numeric;
BEGIN
 IF TG_TABLE_NAME='checker_model_budget_accounts' THEN
  target_project:=coalesce(NEW.project_id,OLD.project_id);
 ELSE
  SELECT project_id INTO target_project FROM public.checker_model_call_slots
   WHERE id=coalesce(NEW.slot_id,OLD.slot_id);
 END IF;
 SELECT * INTO account FROM public.checker_model_budget_accounts
  WHERE project_id=target_project;
 SELECT coalesce(sum(CASE WHEN
    a.state IN ('dispatching','uncertain')
   THEN a.reserved_nanodollars ELSE 0 END),0),
  coalesce(sum(CASE WHEN a.state='completed' OR
    (a.state='known_failed' AND a.settled_nanodollars IS NOT NULL)
   THEN a.settled_nanodollars ELSE 0 END),0)
 INTO calculated_reserved,calculated_settled
 FROM public.checker_model_call_attempts a
 JOIN public.checker_model_call_slots s ON s.id=a.slot_id
 WHERE s.project_id=target_project;
 IF account.project_id IS NULL OR
    account.lifetime_reserved_nanodollars::numeric<>calculated_reserved OR
    account.lifetime_settled_nanodollars::numeric<>calculated_settled THEN
  RAISE EXCEPTION 'checker model budget conservation failed' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$
""",
    r"""
CREATE FUNCTION public.guard_checker_model_no_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'checker model ledger cannot be truncated' USING ERRCODE='55000';
END $$
""",
)


_TRIGGERS = (
    "CREATE TRIGGER checker_model_profiles_guard BEFORE INSERT OR UPDATE OR DELETE "
    "ON public.checker_model_profiles FOR EACH ROW "
    "EXECUTE FUNCTION public.guard_checker_model_profile()",
    "CREATE TRIGGER checker_model_budget_configurations_guard BEFORE INSERT OR UPDATE OR DELETE "
    "ON public.checker_model_budget_configurations FOR EACH ROW "
    "EXECUTE FUNCTION public.guard_checker_model_budget_configuration()",
    "CREATE TRIGGER checker_model_budget_accounts_guard BEFORE INSERT OR UPDATE OR DELETE "
    "ON public.checker_model_budget_accounts FOR EACH ROW "
    "EXECUTE FUNCTION public.guard_checker_model_budget_account()",
    "CREATE TRIGGER checker_model_call_slots_guard BEFORE INSERT OR UPDATE OR DELETE "
    "ON public.checker_model_call_slots FOR EACH ROW "
    "EXECUTE FUNCTION public.guard_checker_model_call_slot()",
    "CREATE TRIGGER checker_model_call_attempts_guard BEFORE INSERT OR UPDATE OR DELETE "
    "ON public.checker_model_call_attempts FOR EACH ROW "
    "EXECUTE FUNCTION public.guard_checker_model_call_attempt()",
    "CREATE TRIGGER checker_model_call_recoveries_guard BEFORE INSERT OR UPDATE OR DELETE "
    "ON public.checker_model_call_recoveries FOR EACH ROW "
    "EXECUTE FUNCTION public.guard_checker_model_recovery()",
    "CREATE CONSTRAINT TRIGGER checker_model_budget_account_reconcile "
    "AFTER INSERT OR UPDATE OR DELETE ON public.checker_model_budget_accounts "
    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
    "EXECUTE FUNCTION public.reconcile_checker_model_budget()",
    "CREATE CONSTRAINT TRIGGER checker_model_call_attempt_reconcile "
    "AFTER INSERT OR UPDATE OR DELETE ON public.checker_model_call_attempts "
    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
    "EXECUTE FUNCTION public.reconcile_checker_model_budget()",
    *(
        "CREATE TRIGGER "
        + table
        + "_no_truncate BEFORE TRUNCATE ON public."
        + table
        + " FOR EACH STATEMENT EXECUTE FUNCTION public.guard_checker_model_no_truncate()"
        for table in (
            "checker_model_profiles",
            "checker_model_budget_configurations",
            "checker_model_budget_accounts",
            "checker_model_call_slots",
            "checker_model_call_attempts",
            "checker_model_call_recoveries",
        )
    ),
)
