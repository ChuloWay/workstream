"""Bind canonical post-submit policies to unified projection and decision custody."""

from alembic import op
from sqlalchemy import text
from scripts.schema_baseline_sql import split_sql_statements

revision = "0020_post_submit_policy_custody"
down_revision = "0019_guide_proposal_review"
branch_labels = None
depends_on = None


def _execute(sql):
    for statement in split_sql_statements(sql):
        op.execute(statement)


def upgrade():
    _execute("""
    ALTER TABLE checker_policies ADD CONSTRAINT uq_checker_policies_scope UNIQUE(id,project_id,guide_id);

CREATE TABLE project_post_policy_operations (
	operation_id UUID NOT NULL,
	kind VARCHAR(20) NOT NULL,
	idempotency_key UUID NOT NULL,
	project_id VARCHAR(36) NOT NULL,
	guide_id VARCHAR(36) NOT NULL,
	compilation_id UUID NOT NULL,
	policy_id VARCHAR(36) NOT NULL,
	upstream_approval_operation_id UUID NOT NULL,
	target_json JSON NOT NULL,
	target_digest VARCHAR(71) NOT NULL,
	request_json JSON NOT NULL,
	request_digest VARCHAR(71) NOT NULL,
	resource_context_json JSON NOT NULL,
	resource_context_digest VARCHAR(71) NOT NULL,
	receipt_json JSON NOT NULL,
	output_digest VARCHAR(71) NOT NULL,
	actor_profile_id VARCHAR(36) NOT NULL,
	identity_link_id VARCHAR(36) NOT NULL,
	admin_role_grant_id UUID,
	service_identity VARCHAR(100),
	authorization_decision_event_id VARCHAR(36) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_project_post_policy_operations PRIMARY KEY (operation_id),
	CONSTRAINT fk_post_policy_operation_compilation_scope FOREIGN KEY(compilation_id, project_id, guide_id) REFERENCES project_guide_compilations (id, project_id, guide_id),
	CONSTRAINT fk_post_policy_operation_policy_scope FOREIGN KEY(policy_id, project_id, guide_id) REFERENCES checker_policies (id, project_id, guide_id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT fk_post_policy_operation_actor_link FOREIGN KEY(identity_link_id, actor_profile_id) REFERENCES actor_identity_links (id, actor_profile_id),
	CONSTRAINT uq_post_policy_operation_kind UNIQUE (policy_id, kind),
	CONSTRAINT uq_post_policy_operation_key UNIQUE (actor_profile_id, kind, idempotency_key),
	CONSTRAINT uq_post_policy_operation_decision UNIQUE (authorization_decision_event_id),
	CONSTRAINT ck_project_post_policy_operations_post_policy_operation_kind CHECK (kind in ('derive','approve','correction')),
	CONSTRAINT ck_project_post_policy_operations_post_policy_operation_hashes CHECK (target_digest ~ '^sha256:[0-9a-f]{64}$' and request_digest ~ '^sha256:[0-9a-f]{64}$' and resource_context_digest ~ '^sha256:[0-9a-f]{64}$' and output_digest ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT ck_project_post_policy_operations_post_policy_operation_3661 CHECK ((kind = 'derive' and service_identity = 'workstream.project.setup' and admin_role_grant_id is null) or (kind != 'derive' and service_identity is null and admin_role_grant_id is not null)),
	CONSTRAINT ck_project_post_policy_operations_post_policy_operation_sizes CHECK (octet_length(target_json::text) <= 32768 and octet_length(receipt_json::text) <= 49152 and octet_length(request_json::text) <= 49152 and octet_length(resource_context_json::text) <= 16384),
	CONSTRAINT fk_project_post_policy_operations_upstream_approval_ope_4fef FOREIGN KEY(upstream_approval_operation_id) REFERENCES project_guide_proposal_approvals (operation_id),
	CONSTRAINT fk_project_post_policy_operations_actor_profile_id_acto_e2b8 FOREIGN KEY(actor_profile_id) REFERENCES actor_profiles (id),
	CONSTRAINT fk_project_post_policy_operations_admin_role_grant_id_a_a838 FOREIGN KEY(admin_role_grant_id) REFERENCES admin_role_grants (id),
	CONSTRAINT fk_project_post_policy_operations_authorization_decisio_0e5b FOREIGN KEY(authorization_decision_event_id) REFERENCES audit_events (id)
)

;
CREATE UNIQUE INDEX uq_post_policy_projection_upstream ON project_post_policy_operations (upstream_approval_operation_id) WHERE kind = 'derive';
    ALTER TABLE checker_policies DROP CONSTRAINT ck_checker_policies_approval_provenance;
    ALTER TABLE checker_policies DROP CONSTRAINT ck_checker_policies_correction_provenance;
    ALTER TABLE checker_policies ADD COLUMN projection_operation_id uuid
      REFERENCES project_post_policy_operations(operation_id) DEFERRABLE INITIALLY DEFERRED;
    ALTER TABLE checker_policies ADD COLUMN approval_operation_id uuid
      REFERENCES project_post_policy_operations(operation_id) DEFERRABLE INITIALLY DEFERRED;
    ALTER TABLE checker_policies ADD COLUMN supersession_operation_id uuid
      REFERENCES project_post_policy_operations(operation_id) DEFERRABLE INITIALLY DEFERRED;
    CREATE UNIQUE INDEX uq_post_policy_chain_root ON checker_policies(guide_id)
      WHERE projection_operation_id IS NOT NULL AND supersedes_policy_id IS NULL;
    CREATE UNIQUE INDEX uq_post_policy_chain_successor ON checker_policies(supersedes_policy_id)
      WHERE projection_operation_id IS NOT NULL;
    """)
    _audit_vocabulary()
    _guards()


def _audit_vocabulary(reverse=False):
    connection = op.get_bind()
    name = "ck_audit_events_authority_privacy_bounds"
    connection.execute(text("LOCK TABLE audit_events IN ACCESS EXCLUSIVE MODE"))
    definition = connection.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid='audit_events'::regclass AND conname=:name"
    ), {"name": name}).scalar_one()
    anchor = "('project_guide_compilation_review_package'::character varying)::text"
    addition = ", ('project_post_submit_checker_policy_mutation'::character varying)::text"
    if definition.count(anchor) != 1 or (reverse and definition.count(anchor + addition) != 1):
        raise RuntimeError("post-policy audit vocabulary owner changed")
    definition = definition.replace(anchor + addition, anchor) if reverse else definition.replace(anchor, anchor + addition)
    connection.execute(text(f"ALTER TABLE audit_events DROP CONSTRAINT {name}"))
    connection.execute(text(f"ALTER TABLE audit_events ADD CONSTRAINT {name} {definition}"))


def _guards():
    _execute(r"""
    CREATE FUNCTION require_post_policy_operation() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE p checker_policies%rowtype; a project_guide_proposal_approvals%rowtype;
      t jsonb; r jsonb; expected jsonb; action text; e audit_events%rowtype;
      correction project_guide_proposal_corrections%rowtype;
    BEGIN
      SELECT * INTO p FROM checker_policies WHERE id=NEW.policy_id;
      SELECT * INTO a FROM project_guide_proposal_approvals WHERE operation_id=NEW.upstream_approval_operation_id;
      t := NEW.target_json::jsonb; r := NEW.receipt_json::jsonb;
      action := 'project.post_submit_checker_policy.' || CASE NEW.kind WHEN 'correction' THEN 'correction.request' ELSE NEW.kind END;
      PERFORM require_guide_proposal_target(t->'proposal',guide_proposal_hash(t->'proposal'),a.finalization_id);
      IF p.id IS NULL OR a.operation_id IS NULL OR t->'proposal' IS DISTINCT FROM a.target_json::jsonb
         OR t->'upstream' IS DISTINCT FROM a.receipt_json::jsonb
         OR t->>'upstream_output_digest' IS DISTINCT FROM a.output_digest
         OR NEW.project_id IS DISTINCT FROM a.project_id OR NEW.guide_id IS DISTINCT FROM a.guide_id
         OR NEW.compilation_id IS DISTINCT FROM a.compilation_id
         OR NEW.target_digest IS DISTINCT FROM guide_proposal_hash(t)
         OR NEW.request_digest IS DISTINCT FROM guide_proposal_hash(NEW.request_json::jsonb)
         OR NEW.output_digest IS DISTINCT FROM guide_proposal_hash(r)
         OR r->'target' IS DISTINCT FROM t OR r->>'kind' IS DISTINCT FROM NEW.kind
         OR r->>'operation_id' IS DISTINCT FROM NEW.operation_id::text
         OR t->>'policy_id' IS DISTINCT FROM p.id
         OR t->>'policy_hash' IS DISTINCT FROM p.policy_hash
         OR t->>'projection_operation_id' IS DISTINCT FROM p.projection_operation_id::text
         OR t->>'predecessor_policy_id' IS DISTINCT FROM p.supersedes_policy_id
         OR p.project_id IS DISTINCT FROM a.project_id OR p.guide_id IS DISTINCT FROM a.guide_id
         OR p.guide_version IS DISTINCT FROM t->'proposal'->>'guide_version'
         OR p.source_snapshot_id IS DISTINCT FROM t->'proposal'->>'source_snapshot_id'
         OR p.source_snapshot_hash IS DISTINCT FROM t->'proposal'->>'source_snapshot_hash'
         OR p.effective_policy_id IS DISTINCT FROM a.effective_policy_id
         OR p.pre_submit_checker_policy_id IS DISTINCT FROM a.pre_submit_policy_id
         OR p.effective_policy_hash IS DISTINCT FROM a.receipt_json->>'effective_policy_hash'
         OR p.pre_submit_checker_bundle_hash IS DISTINCT FROM a.receipt_json->>'pre_submit_bundle_hash'
         OR p.policy_hash IS DISTINCT FROM guide_proposal_hash(p.policy_body::jsonb)
         OR p.policy_body->>'catalogue_manifest_sha256' IS DISTINCT FROM t->'proposal'->>'post_catalogue_manifest_hash'
      THEN RAISE EXCEPTION 'post-policy operation lineage mismatch' USING ERRCODE='23514'; END IF;
      PERFORM 1 FROM project_guides g WHERE g.id=NEW.guide_id AND g.project_id=NEW.project_id AND g.status='draft' FOR UPDATE;
      IF NOT FOUND OR EXISTS(SELECT 1 FROM project_guide_proposal_approvals successor
          WHERE successor.prior_approval_operation_id=a.operation_id)
         OR NOT EXISTS(SELECT 1 FROM submission_artifact_policies artifact
           JOIN effective_project_submission_artifact_policies effective ON effective.id=a.effective_policy_id
           JOIN pre_submit_checker_policies pre ON pre.id=a.pre_submit_policy_id
           WHERE artifact.id=a.artifact_policy_id AND artifact.lifecycle_status='approved'
             AND effective.lifecycle_status='approved' AND pre.lifecycle_status='compiled')
         OR (SELECT max(setup_generation) FROM project_setup_runs WHERE guide_id=NEW.guide_id)
           IS DISTINCT FROM ((t->'proposal'->>'setup_generation')::bigint + CASE WHEN NEW.kind='correction' THEN 1 ELSE 0 END) THEN
        RAISE EXCEPTION 'post-policy current upstream custody missing' USING ERRCODE='23514';
      END IF;
      IF EXISTS(
        SELECT 1 FROM project_guide_compilations c,
          jsonb_array_elements(c.canonical_result::jsonb->'post_submit_bindings') binding
        WHERE c.id=NEW.compilation_id AND NOT EXISTS(
          SELECT 1 FROM jsonb_array_elements(p.policy_body::jsonb->'entries') entry
          WHERE entry->>'checker_id'=binding->>'capability_id'
            AND entry->>'definition_version'=binding->>'capability_version'
            AND entry->>'classification'='project_required'
            AND entry->'configuration'=COALESCE((SELECT jsonb_object_agg(parameter->>'name',parameter->'value')
               FROM jsonb_array_elements(binding->'parameters') parameter),'{}'::jsonb))) THEN
        RAISE EXCEPTION 'post-policy compiled required binding missing' USING ERRCODE='23514';
      END IF;
      IF EXISTS(
        SELECT 1 FROM jsonb_array_elements(p.policy_body::jsonb->'entries') entry
        WHERE entry->>'classification' IS DISTINCT FROM 'platform_default'
          AND NOT EXISTS(
            SELECT 1 FROM project_guide_compilations c,
              jsonb_array_elements(c.canonical_result::jsonb->'post_submit_bindings') binding
            WHERE c.id=NEW.compilation_id
              AND entry->>'checker_id'=binding->>'capability_id'
              AND entry->>'definition_version'=binding->>'capability_version'
              AND entry->>'classification'='project_required'
              AND entry->'configuration'=COALESCE((SELECT jsonb_object_agg(parameter->>'name',parameter->'value')
                 FROM jsonb_array_elements(binding->'parameters') parameter),'{}'::jsonb))) THEN
        RAISE EXCEPTION 'post-policy compiled selection not requested' USING ERRCODE='23514';
      END IF;
      expected := jsonb_build_object(
        'locator',jsonb_build_object('project_id',NEW.project_id,'guide_id',NEW.guide_id,
          'compilation_id',NEW.compilation_id,'actor_profile_id',NEW.actor_profile_id,
          'identity_link_id',NEW.identity_link_id,'action_id',action,'operation_id',NEW.operation_id),
        'policy_id',p.id,'finalization_id',a.finalization_id,'setup_run_id',t->'proposal'->>'setup_run_id',
        'setup_generation',t->'proposal'->'setup_generation','upstream_approval_operation_id',a.operation_id,
        'upstream_approval_output_digest',a.output_digest,'policy_hash',p.policy_hash,
        'guide_version',p.guide_version,'source_snapshot_id',p.source_snapshot_id,'source_snapshot_hash',p.source_snapshot_hash,
        'result_hash',t->'proposal'->>'result_hash','post_component_hash',t->'proposal'->'component_hashes'->>'post_submit_hash',
        'requirement_inventory_hash',t->'proposal'->'component_hashes'->>'requirement_inventory_hash',
        'catalogue_manifest_hash',t->'proposal'->>'post_catalogue_manifest_hash',
        'effective_policy_id',p.effective_policy_id,'effective_policy_hash',p.effective_policy_hash,
        'pre_submit_policy_id',p.pre_submit_checker_policy_id,'pre_submit_bundle_hash',p.pre_submit_checker_bundle_hash,
        'projection_operation_id',p.projection_operation_id,
        'lifecycle_status',CASE WHEN NEW.kind='correction' AND p.approval_operation_id IS NOT NULL THEN 'approved' ELSE 'compiled' END,
        'target_digest',NEW.target_digest,'request_digest',NEW.request_digest,'output_digest',NEW.output_digest);
      IF NEW.resource_context_json::jsonb IS DISTINCT FROM expected
         OR NEW.resource_context_digest IS DISTINCT FROM guide_proposal_hash(expected) THEN
        RAISE EXCEPTION 'post-policy resource custody mismatch' USING ERRCODE='23514';
      END IF;
      SELECT * INTO e FROM audit_events WHERE id=NEW.authorization_decision_event_id;
      IF e.id IS NULL OR e.event_domain IS DISTINCT FROM 'authority'
         OR e.event_type IS DISTINCT FROM 'SensitiveAuthorizationAllowed' OR e.denial_code IS NOT NULL
         OR e.actor_ref_kind IS DISTINCT FROM 'actor_profile' OR e.actor_id IS DISTINCT FROM NEW.actor_profile_id
         OR e.project_id IS DISTINCT FROM NEW.project_id OR e.action_id IS DISTINCT FROM action
         OR e.permission_id IS DISTINCT FROM 'project.effective_policy.manage'
         OR e.resource_type IS DISTINCT FROM 'project_post_submit_checker_policy_mutation'
         OR e.resource_id IS DISTINCT FROM p.id OR e.correlation_id IS DISTINCT FROM NEW.operation_id
         OR e.after_facts->>'allowed' IS DISTINCT FROM 'true'
         OR e.after_facts->>'resource_context_digest' IS DISTINCT FROM NEW.resource_context_digest THEN
        RAISE EXCEPTION 'post-policy authority evidence mismatch' USING ERRCODE='23514';
      END IF;
      IF NEW.kind='derive' THEN
        PERFORM 1 FROM actor_profiles actor JOIN actor_identity_links link ON link.actor_profile_id=actor.id
        WHERE actor.id=NEW.actor_profile_id AND actor.actor_kind='service' AND actor.status='active'
          AND link.id=NEW.identity_link_id AND link.status='active' AND link.subject_kind='service'
          AND actor.service_identity='workstream.project.setup' FOR SHARE OF actor,link;
        IF NOT FOUND OR NEW.service_identity IS DISTINCT FROM 'workstream.project.setup' THEN
          RAISE EXCEPTION 'post-policy current service authority missing' USING ERRCODE='23514';
        END IF;
        IF p.projection_operation_id IS DISTINCT FROM NEW.operation_id
           OR NEW.request_json::jsonb IS DISTINCT FROM jsonb_build_object(
             'selection',jsonb_build_object('project_id',NEW.project_id,'guide_id',NEW.guide_id,'compilation_id',NEW.compilation_id),
             'upstream_approval_operation_id',a.operation_id,'upstream_approval_output_digest',a.output_digest)
           OR NEW.idempotency_key IS DISTINCT FROM a.operation_id THEN
          RAISE EXCEPTION 'post-policy projection request mismatch' USING ERRCODE='23514';
        END IF;
      ELSE
        PERFORM require_guide_proposal_authority(NEW.actor_profile_id,NEW.identity_link_id,
          NEW.admin_role_grant_id,NEW.project_id,NEW.authorization_decision_event_id,action,
          'project.effective_policy.manage','project_post_submit_checker_policy_mutation',p.id,NEW.resource_context_digest);
        expected := jsonb_build_object('target',t,'idempotency_key',NEW.idempotency_key);
        IF NEW.kind='correction' THEN
          expected := expected || jsonb_build_object('reason',NEW.request_json->>'reason');
        END IF;
        IF NEW.request_json::jsonb IS DISTINCT FROM expected THEN
          RAISE EXCEPTION 'post-policy decision request mismatch' USING ERRCODE='23514';
        END IF;
      END IF;
      IF NEW.kind='approve' AND (p.approval_operation_id IS DISTINCT FROM NEW.operation_id OR p.approved_at IS NULL) THEN
        RAISE EXCEPTION 'post-policy approval output missing' USING ERRCODE='23514';
      END IF;
      IF NEW.kind='correction' THEN
        SELECT * INTO correction FROM project_guide_proposal_corrections
          WHERE operation_id=(r->'correction'->>'operation_id')::uuid;
        IF correction.operation_id IS NULL OR r->'correction' IS DISTINCT FROM correction.receipt_json::jsonb
           OR correction.target_json::jsonb IS DISTINCT FROM t->'proposal'
           OR correction.actor_profile_id IS DISTINCT FROM NEW.actor_profile_id
           OR correction.identity_link_id IS DISTINCT FROM NEW.identity_link_id
           OR correction.idempotency_key IS DISTINCT FROM NEW.idempotency_key
           OR correction.reason IS DISTINCT FROM NEW.request_json->>'reason'
           OR p.supersession_operation_id IS DISTINCT FROM NEW.operation_id THEN
          RAISE EXCEPTION 'post-policy correction custody missing' USING ERRCODE='23514';
        END IF;
      ELSIF r->'correction' IS DISTINCT FROM 'null'::jsonb THEN
        RAISE EXCEPTION 'post-policy unexpected correction receipt' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$;
    """)
    _policy_guards()


def _policy_guards():
    _execute(r"""
    CREATE FUNCTION require_post_policy_custody() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE p checker_policies%rowtype; projection project_post_policy_operations%rowtype;
    BEGIN
      SELECT * INTO p FROM checker_policies WHERE id=NEW.id;
      SELECT * INTO projection FROM project_post_policy_operations
        WHERE operation_id=p.projection_operation_id AND policy_id=p.id AND kind='derive';
      IF projection.operation_id IS NULL THEN
        RAISE EXCEPTION 'post-policy projection receipt missing' USING ERRCODE='23514';
      END IF;
      IF (p.lifecycle_status='approved' OR p.approval_operation_id IS NOT NULL) AND (p.approved_at IS NULL OR NOT EXISTS(
          SELECT 1 FROM project_post_policy_operations WHERE operation_id=p.approval_operation_id
          AND policy_id=p.id AND kind='approve')) THEN
        RAISE EXCEPTION 'post-policy approval receipt missing' USING ERRCODE='23514';
      END IF;
      IF (p.approval_operation_id IS NULL) IS DISTINCT FROM (p.approved_at IS NULL)
         OR (p.lifecycle_status='compiled' AND p.approval_operation_id IS NOT NULL) THEN
        RAISE EXCEPTION 'post-policy approval lifecycle mismatch' USING ERRCODE='23514';
      END IF;
      IF p.lifecycle_status='superseded' THEN
        IF p.superseded_at IS NULL OR NOT EXISTS(
          SELECT 1 FROM project_post_policy_operations o WHERE o.operation_id=p.supersession_operation_id
          AND ((o.kind='correction' AND o.policy_id=p.id)
               OR (o.kind='derive' AND o.target_json->>'predecessor_policy_id'=p.id))) THEN
          RAISE EXCEPTION 'post-policy supersession receipt missing' USING ERRCODE='23514';
        END IF;
      ELSIF p.superseded_at IS NOT NULL OR p.supersession_operation_id IS NOT NULL THEN
        RAISE EXCEPTION 'post-policy supersession lifecycle mismatch' USING ERRCODE='23514';
      END IF;
      IF p.supersedes_policy_id IS NOT NULL AND NOT EXISTS(
        SELECT 1 FROM checker_policies predecessor JOIN project_post_policy_operations o ON o.operation_id=predecessor.projection_operation_id
        WHERE predecessor.id=p.supersedes_policy_id AND predecessor.project_id=p.project_id AND predecessor.guide_id=p.guide_id
          AND predecessor.lifecycle_status='superseded' AND predecessor.superseded_at IS NOT NULL
          AND (o.target_json->'proposal'->>'setup_generation')::bigint
              < (projection.target_json->'proposal'->>'setup_generation')::bigint) THEN
        RAISE EXCEPTION 'post-policy predecessor custody mismatch' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$;
    CREATE FUNCTION guard_post_policy_change() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP IN ('DELETE','TRUNCATE') THEN
        RAISE EXCEPTION 'post-policy retained evidence is immutable' USING ERRCODE='55000';
      END IF;
      IF (to_jsonb(NEW)-ARRAY['lifecycle_status','approval_operation_id','approved_at',
          'supersession_operation_id','superseded_at','supersession_kind']) IS DISTINCT FROM
         (to_jsonb(OLD)-ARRAY['lifecycle_status','approval_operation_id','approved_at',
          'supersession_operation_id','superseded_at','supersession_kind'])
         OR OLD.lifecycle_status='superseded'
         OR (OLD.lifecycle_status='approved' AND NEW.lifecycle_status!='superseded')
         OR (OLD.approval_operation_id IS NOT NULL AND
             (NEW.approval_operation_id IS DISTINCT FROM OLD.approval_operation_id OR NEW.approved_at IS DISTINCT FROM OLD.approved_at)) THEN
        RAISE EXCEPTION 'post-policy retained evidence is immutable' USING ERRCODE='55000';
      END IF;
      RETURN NEW;
    END $$;
    CREATE CONSTRAINT TRIGGER post_policy_operation_custody AFTER INSERT ON project_post_policy_operations
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_post_policy_operation();
    CREATE CONSTRAINT TRIGGER post_policy_output_custody AFTER INSERT OR UPDATE ON checker_policies
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_post_policy_custody();
    CREATE TRIGGER immutable_post_policy_operation BEFORE UPDATE OR DELETE ON project_post_policy_operations
      FOR EACH ROW EXECUTE FUNCTION reject_guide_proposal_change();
    CREATE TRIGGER immutable_post_policy_operation_truncate BEFORE TRUNCATE ON project_post_policy_operations
      EXECUTE FUNCTION reject_guide_proposal_change();
    CREATE TRIGGER immutable_post_policy_content BEFORE UPDATE OR DELETE ON checker_policies
      FOR EACH ROW EXECUTE FUNCTION guard_post_policy_change();
    CREATE TRIGGER immutable_post_policy_truncate BEFORE TRUNCATE ON checker_policies
      EXECUTE FUNCTION guard_post_policy_change();
    """)


def downgrade():
    connection = op.get_bind()
    connection.execute(text("LOCK TABLE checker_policies,project_post_policy_operations IN ACCESS EXCLUSIVE MODE"))
    if connection.execute(text("SELECT EXISTS(SELECT 1 FROM project_post_policy_operations)")).scalar_one():
        raise RuntimeError("retained post-policy evidence prevents downgrade")
    _execute("""
    DROP TRIGGER immutable_post_policy_truncate ON checker_policies;
    DROP TRIGGER immutable_post_policy_content ON checker_policies;
    DROP TRIGGER post_policy_output_custody ON checker_policies;
    DROP TRIGGER post_policy_operation_custody ON project_post_policy_operations;
    DROP FUNCTION guard_post_policy_change();
    DROP FUNCTION require_post_policy_custody();
    DROP FUNCTION require_post_policy_operation();
    DROP INDEX uq_post_policy_chain_root;
    DROP INDEX uq_post_policy_chain_successor;
    ALTER TABLE checker_policies DROP COLUMN supersession_operation_id;
    ALTER TABLE checker_policies DROP COLUMN approval_operation_id;
    ALTER TABLE checker_policies DROP COLUMN projection_operation_id;
    DROP TABLE project_post_policy_operations;
    ALTER TABLE checker_policies DROP CONSTRAINT uq_checker_policies_scope;
    ALTER TABLE checker_policies ADD CONSTRAINT ck_checker_policies_approval_provenance CHECK (
      lifecycle_status!='approved' OR (approved_by_role IN ('admin','project_manager') AND approved_by_actor IS NOT NULL AND approved_at IS NOT NULL));
    ALTER TABLE checker_policies ADD CONSTRAINT ck_checker_policies_correction_provenance CHECK (
      lifecycle_status!='superseded' OR (superseded_at IS NOT NULL AND superseded_by_role IN ('admin','project_manager')
        AND superseded_by_actor IS NOT NULL AND supersession_kind IN ('correction_requested','upstream_policy_changed')
        AND supersession_reason IS NOT NULL AND length(btrim(supersession_reason))>0));
    """)
    _audit_vocabulary(reverse=True)
