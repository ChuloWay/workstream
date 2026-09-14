"""Fence pre-submit invocation and bind completed immutable evidence."""

from alembic import op
from sqlalchemy import text

from scripts.schema_baseline_sql import split_sql_statements

revision = "0021_pre_submit_attempts"
down_revision = "0020_post_submit_policy_custody"
branch_labels = None
depends_on = None


def _execute(sql):
    """Execute the fixed schema statements with the shared parser."""
    for statement in split_sql_statements(sql):
        op.execute(statement)


def upgrade():
    """Retain old evidence unchanged; all new evidence requires attempt custody."""
    _audit_vocabulary()
    _execute("""
CREATE TABLE pre_submit_execution_attempts (
 id varchar(36) PRIMARY KEY,
 idempotency_key varchar(36) NOT NULL,
 actor_profile_id varchar(36) NOT NULL REFERENCES actor_profiles(id) ON DELETE RESTRICT,
 identity_link_id varchar(36) NOT NULL,
 task_id varchar(36) NOT NULL,
 assignment_id varchar(36) NOT NULL,
 prepared_generation_id varchar(36) NOT NULL,
 claim_nonce varchar(36) NOT NULL,
 request_json json NOT NULL,
 request_digest varchar(71) NOT NULL,
 status varchar(16) NOT NULL,
 evidence_set_id varchar(36) REFERENCES pre_submit_evidence_sets(id) ON DELETE RESTRICT,
 created_at timestamptz DEFAULT now() NOT NULL,
 CONSTRAINT uq_pre_submit_attempt_key UNIQUE(actor_profile_id,idempotency_key),
 CONSTRAINT uq_pre_submit_attempt_evidence UNIQUE(evidence_set_id),
 CONSTRAINT fk_pre_submit_attempt_actor_link FOREIGN KEY(identity_link_id,actor_profile_id)
   REFERENCES actor_identity_links(id,actor_profile_id),
 CONSTRAINT fk_pre_submit_attempt_assignment FOREIGN KEY(assignment_id,task_id,actor_profile_id)
   REFERENCES task_assignments(id,task_id,contributor_id),
 CONSTRAINT ck_pre_submit_attempt_status CHECK (
   (status='reserved' AND evidence_set_id IS NULL) OR
   (status='completed' AND evidence_set_id IS NOT NULL)),
 CONSTRAINT ck_pre_submit_attempt_digest CHECK(request_digest ~ '^sha256:[0-9a-f]{64}$')
);
ALTER TABLE pre_submit_evidence_sets
 ADD COLUMN attempt_id varchar(36) UNIQUE REFERENCES pre_submit_execution_attempts(id) ON DELETE RESTRICT,
 ADD COLUMN attempt_request_digest varchar(71),
 ADD COLUMN packet_sha256 varchar(71),
 ADD CONSTRAINT ck_pre_submit_evidence_packet_sha256
   CHECK(packet_sha256 IS NULL OR packet_sha256 ~ '^sha256:[0-9a-f]{64}$');
ALTER TABLE pre_submit_evidence_results
 ADD COLUMN checker_order integer,
 ADD COLUMN metadata_json json;

CREATE FUNCTION guard_pre_submit_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP IN ('DELETE','TRUNCATE') THEN
   RAISE EXCEPTION 'pre-submit attempts are retained' USING ERRCODE='55000';
 END IF;
 IF TG_OP='INSERT' THEN
   IF NEW.status <> 'reserved' OR NEW.evidence_set_id IS NOT NULL
      OR NEW.created_at IS DISTINCT FROM transaction_timestamp()
      OR jsonb_typeof(NEW.request_json::jsonb) <> 'object'
      OR octet_length(NEW.request_json::text) > 32768
      OR NEW.request_digest IS DISTINCT FROM ('sha256:' || encode(sha256(convert_to(
           project_guide_projection_canonical_json(NEW.request_json::jsonb), 'UTF8')), 'hex'))
      OR NEW.request_json->>'actor_profile_id' IS DISTINCT FROM NEW.actor_profile_id
      OR NEW.request_json->>'identity_link_id' IS DISTINCT FROM NEW.identity_link_id
      OR NEW.request_json->>'task_id' IS DISTINCT FROM NEW.task_id
      OR NEW.request_json->>'assignment_id' IS DISTINCT FROM NEW.assignment_id THEN
     RAISE EXCEPTION 'invalid pre-submit reservation' USING ERRCODE='23514';
   END IF;
   RETURN NEW;
 END IF;
 IF (to_jsonb(NEW)-'status'-'evidence_set_id') IS DISTINCT FROM
    (to_jsonb(OLD)-'status'-'evidence_set_id')
    OR OLD.status <> 'reserved' OR NEW.status <> 'completed'
    OR NEW.evidence_set_id IS NULL THEN
   RAISE EXCEPTION 'pre-submit attempt transition invalid' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER pre_submit_attempt_guard BEFORE INSERT OR UPDATE OR DELETE
 ON pre_submit_execution_attempts FOR EACH ROW EXECUTE FUNCTION guard_pre_submit_attempt();
CREATE TRIGGER pre_submit_attempt_no_truncate BEFORE TRUNCATE
 ON pre_submit_execution_attempts FOR EACH STATEMENT EXECUTE FUNCTION guard_pre_submit_attempt();

CREATE FUNCTION require_pre_submit_attempt_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a pre_submit_execution_attempts; e pre_submit_evidence_sets; name text;
BEGIN
 IF TG_TABLE_NAME='pre_submit_execution_attempts' THEN
   SELECT * INTO a FROM pre_submit_execution_attempts WHERE id=NEW.id;
   IF a.status='reserved' THEN RETURN NULL; END IF;
   SELECT * INTO e FROM pre_submit_evidence_sets WHERE id=a.evidence_set_id;
 ELSE
   SELECT * INTO e FROM pre_submit_evidence_sets WHERE id=NEW.id;
   SELECT * INTO a FROM pre_submit_execution_attempts WHERE id=e.attempt_id;
 END IF;
 IF a.id IS NULL OR e.id IS NULL OR a.status <> 'completed'
    OR a.evidence_set_id IS DISTINCT FROM e.id OR e.attempt_id IS DISTINCT FROM a.id
    OR e.attempt_request_digest IS DISTINCT FROM a.request_digest
    OR e.prepared_generation_id IS DISTINCT FROM a.prepared_generation_id THEN
   RAISE EXCEPTION 'pre-submit evidence attempt mismatch' USING ERRCODE='23514';
 END IF;
 IF e.packet_sha256 IS NULL
    OR e.packet_sha256 IS DISTINCT FROM a.request_json->>'packet_sha256' THEN
   RAISE EXCEPTION 'pre-submit evidence packet mismatch' USING ERRCODE='23514';
 END IF;
 FOREACH name IN ARRAY ARRAY[
   'actor_profile_id','identity_link_id','task_id','assignment_id','project_id',
   'predecessor_submission_id','predecessor_submission_version',
   'archive_sha256','archive_byte_count','semantic_manifest_id','semantic_manifest_sha256',
   'guide_id','guide_version','source_snapshot_id','source_snapshot_sha256','locked_guide_sha256',
   'effective_policy_id','locked_artifact_policy_sha256','pre_submit_policy_id',
   'locked_checker_policy_sha256','effective_plan_sha256','catalogue_id',
   'catalogue_version','catalogue_manifest_sha256','storage_scheme'] LOOP
   IF NOT a.request_json::jsonb ? name OR
      (a.request_json::jsonb->name) IS DISTINCT FROM (to_jsonb(e)->name) THEN
     RAISE EXCEPTION 'pre-submit evidence resource mismatch' USING ERRCODE='23514';
   END IF;
 END LOOP;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER pre_submit_attempt_completion
 AFTER INSERT OR UPDATE ON pre_submit_execution_attempts DEFERRABLE INITIALLY DEFERRED
 FOR EACH ROW EXECUTE FUNCTION require_pre_submit_attempt_evidence();
CREATE CONSTRAINT TRIGGER pre_submit_evidence_attempt
 AFTER INSERT ON pre_submit_evidence_sets DEFERRABLE INITIALLY DEFERRED
 FOR EACH ROW EXECUTE FUNCTION require_pre_submit_attempt_evidence();

CREATE FUNCTION require_pre_submit_result_reconstruction() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item jsonb; seen text[] := ARRAY[]::text[];
BEGIN
 IF NEW.checker_order IS NULL OR NEW.checker_order < 0 OR NEW.metadata_json IS NULL
    OR jsonb_typeof(NEW.metadata_json::jsonb) <> 'array'
    OR octet_length(NEW.metadata_json::text) > 2048 THEN
   RAISE EXCEPTION 'pre-submit result reconstruction fields required' USING ERRCODE='23514';
 END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(NEW.metadata_json::jsonb) LOOP
   IF jsonb_typeof(item) <> 'array' OR jsonb_array_length(item) <> 2
      OR jsonb_typeof(item->0) <> 'string'
      OR item->>0 NOT IN ('entry_count','finding_count','matched_category_count')
      OR (item->>0)=ANY(seen) OR jsonb_typeof(item->1) <> 'number'
      OR (item->>1) !~ '^[0-9]+$' THEN
     RAISE EXCEPTION 'pre-submit result metadata invalid' USING ERRCODE='23514';
   END IF;
   seen := array_append(seen,item->>0);
 END LOOP;
 RETURN NEW;
END $$;
CREATE TRIGGER pre_submit_result_reconstruction BEFORE INSERT ON pre_submit_evidence_results
 FOR EACH ROW EXECUTE FUNCTION require_pre_submit_result_reconstruction();
""")



def _audit_vocabulary(*, reverse: bool = False) -> None:
    """Record the already registered fixed-service action without changing authority."""
    connection = op.get_bind()
    connection.execute(text("LOCK TABLE audit_events IN ACCESS EXCLUSIVE MODE"))
    additions = (
        (
            "ck_audit_events_authority_privacy_bounds",
            "('project_guide_setup_finalization'::character varying)::text",
            ", ('pre_submit_checker_input'::character varying)::text",
            1,
        ),
    )
    for name, anchor, addition, count in additions:
        definition = connection.execute(text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='audit_events'::regclass AND conname=:name"
        ), {"name": name}).scalar_one()
        if definition.count(anchor) != count or (reverse and definition.count(anchor + addition) != count):
            raise RuntimeError("pre-submit materializer audit vocabulary changed")
        definition = (definition.replace(anchor + addition, anchor) if reverse
                      else definition.replace(anchor, anchor + addition))
        _execute("ALTER TABLE audit_events DROP CONSTRAINT " + name)
        _execute("ALTER TABLE audit_events ADD CONSTRAINT " + name + " " + definition)


def downgrade():
    """Refuse removal of retained attempt or newly captured result evidence."""
    connection = op.get_bind()
    if connection.scalar(text(
        "SELECT EXISTS(SELECT 1 FROM audit_events "
        "WHERE resource_type='pre_submit_checker_input' "
        "OR action_id='artifact.pre_submit.checker_input.materialize')"
    )):
        raise RuntimeError("retained pre-submit authority evidence prevents downgrade")
    if connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pre_submit_execution_attempts)")):
        raise RuntimeError("retained pre-submit attempts prevent downgrade")
    if connection.scalar(text(
        "SELECT EXISTS(SELECT 1 FROM pre_submit_evidence_results "
        "WHERE metadata_json IS NOT NULL OR checker_order IS NOT NULL)"
    )):
        raise RuntimeError("retained pre-submit result details prevent downgrade")
    _execute("""
DROP TRIGGER pre_submit_result_reconstruction ON pre_submit_evidence_results;
DROP FUNCTION require_pre_submit_result_reconstruction();
DROP TRIGGER pre_submit_evidence_attempt ON pre_submit_evidence_sets;
DROP TRIGGER pre_submit_attempt_completion ON pre_submit_execution_attempts;
DROP FUNCTION require_pre_submit_attempt_evidence();
ALTER TABLE pre_submit_evidence_results DROP COLUMN checker_order, DROP COLUMN metadata_json;
ALTER TABLE pre_submit_evidence_sets DROP COLUMN attempt_id, DROP COLUMN attempt_request_digest,
 DROP COLUMN packet_sha256;
DROP TABLE pre_submit_execution_attempts;
DROP FUNCTION guard_pre_submit_attempt();
""")
    _audit_vocabulary(reverse=True)
