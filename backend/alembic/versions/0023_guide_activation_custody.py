"""Bind complete guide activation to the existing mutation ledger and exact authority."""

from alembic import op
from sqlalchemy import text
from scripts.schema_baseline_sql import split_sql_statements

revision = "0023_guide_activation_custody"
down_revision = "0022_adapter_binding_audit_resource"
branch_labels = None
depends_on = None


def _execute(sql):
    for statement in split_sql_statements(sql):
        op.execute(statement)


def _replace(name, old, new, *, reverse=False):
    definition = op.get_bind().scalar(text(f"SELECT pg_get_functiondef('{name}()'::regprocedure)"))
    before, after = (new, old) if reverse else (old, new)
    if definition.count(before) != 1:
        raise RuntimeError(f"{name} custody shape changed")
    op.execute(definition.replace(before, after))


def _audit(*, reverse=False):
    connection = op.get_bind()
    connection.execute(text("LOCK TABLE audit_events IN ACCESS EXCLUSIVE MODE"))
    name = "ck_audit_events_authority_privacy_bounds"
    definition = connection.scalar(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid='audit_events'::regclass AND conname=:name"), {"name": name})
    anchor = "('contribution_policy'::character varying)::text"
    token = ", ('project_guide_activation'::character varying)::text"
    if definition.count(anchor) != 1 or definition.count(token) != int(reverse):
        raise RuntimeError("activation audit vocabulary shape changed")
    amended = definition.replace(token, "") if reverse else definition.replace(anchor, anchor + token)
    op.execute(f"ALTER TABLE audit_events DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE audit_events ADD CONSTRAINT {name} {amended}")


def _guide_authority_shape(*, reverse=False):
    name = "ck_project_guides_guide_mutation_authority_shape"
    definition = op.get_bind().scalar(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid='project_guides'::regclass AND conname=:name"), {"name": name})
    anchor = "('project.guide.update'::character varying)::text"
    token = ", ('project.guide.activate'::character varying)::text"
    if definition.count(anchor) != 1 or definition.count(token) != int(reverse):
        raise RuntimeError("guide mutation authority shape changed")
    amended = definition.replace(token, "") if reverse else definition.replace(anchor, anchor + token)
    op.execute(f"ALTER TABLE project_guides DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE project_guides ADD CONSTRAINT {name} {amended}")


_BRANCH = """
          if tg_table_name='guide_mutation_idempotency_records' then
            if new.action_id='project.guide.activate' then
              perform require_guide_activation_custody(new.operation_id, true);
              return null;
            end if;
          elsif tg_table_name='project_guides' then
            if tg_op='UPDATE' and old.status='active' and new.status='superseded' then
              perform require_guide_activation_predecessor(new.id, old.mutation_generation, new.superseded_at);
              return null;
            end if;
            if new.activation_operation_id is not null then
              perform require_guide_activation_custody(new.activation_operation_id,
                tg_op='UPDATE' and old.status='draft' and new.status='active');
              return null;
            end if;
          end if;
          """
_MARKER = "if tg_table_name='guide_mutation_idempotency_records' then"
_PROJECT_INSERT = "if tg_op = 'INSERT' and new.creation_action_id is null then"
_PROJECT_DRAFT = """if tg_op = 'INSERT' and new.status is distinct from 'draft' then
              raise exception 'new projects must be draft' using errcode='23514';
            end if;
            """ + _PROJECT_INSERT
_IMMUTABLE = "if new is not distinct from old then return new; end if;"
_ACTIVATION_IMMUTABLE = """if old.action_id='project.guide.activate' and old.status='committed' then
            raise exception 'guide activation operation is immutable' using errcode='55000';
          end if;
          if (new.activation_facts_json::jsonb,new.activation_authority_json::jsonb)
             is distinct from (old.activation_facts_json::jsonb,old.activation_authority_json::jsonb) then
            raise exception 'activation commitments are immutable' using errcode='55000';
          end if;
          """ + _IMMUTABLE


def upgrade():
    _execute("""
      ALTER TABLE guide_mutation_idempotency_records ADD COLUMN activation_facts_json json;
      ALTER TABLE guide_mutation_idempotency_records ADD COLUMN activation_authority_json json;
      ALTER TABLE guide_mutation_idempotency_records ADD CONSTRAINT uq_guide_mutation_operation_resource
        UNIQUE(operation_id,project_id,resource_id);
      ALTER TABLE guide_mutation_idempotency_records DROP CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_action;
      ALTER TABLE guide_mutation_idempotency_records ADD CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_action CHECK(
        action_id IN ('project.guide.create','project.guide.update','project.guide_source_snapshot.create','project.guide.activate'));
      ALTER TABLE guide_mutation_idempotency_records ADD CONSTRAINT ck_guide_mutation_idempotency_records_activation_evidence_shape CHECK(
        (action_id='project.guide.activate' AND activation_facts_json IS NOT NULL AND activation_authority_json IS NOT NULL)
        OR (action_id<>'project.guide.activate' AND activation_facts_json IS NULL AND activation_authority_json IS NULL));
      CREATE UNIQUE INDEX uq_guide_activation_audit_decision ON guide_mutation_idempotency_records
        ((activation_authority_json->>'authorization_decision_event_id')) WHERE action_id='project.guide.activate';
      ALTER TABLE project_guides ADD COLUMN contribution_policy_id uuid;
      ALTER TABLE project_guides ADD COLUMN contribution_policy_version_id uuid;
      ALTER TABLE project_guides ADD COLUMN activation_operation_id uuid;
      ALTER TABLE project_guides ADD CONSTRAINT fk_project_guides_contribution_policy
        FOREIGN KEY(contribution_policy_version_id,contribution_policy_id,project_id)
        REFERENCES contribution_policy_versions(id,contribution_policy_id,project_id);
      ALTER TABLE project_guides ADD CONSTRAINT fk_project_guides_activation_operation
        FOREIGN KEY(activation_operation_id,project_id,id)
        REFERENCES guide_mutation_idempotency_records(operation_id,project_id,resource_id);
      ALTER TABLE project_guides ADD CONSTRAINT ck_project_guides_activation_binding_shape CHECK(
        (contribution_policy_id IS NULL AND contribution_policy_version_id IS NULL AND activation_operation_id IS NULL)
        OR (contribution_policy_id IS NOT NULL AND contribution_policy_version_id IS NOT NULL AND activation_operation_id IS NOT NULL));
    """)
    _audit()
    _guide_authority_shape()
    _guards()
    _replace("validate_guide_mutation_custody", _MARKER, _BRANCH + _MARKER)
    _replace("guard_guide_mutation_idempotency", _IMMUTABLE, _ACTIVATION_IMMUTABLE)
    _replace("validate_project_create_custody", _PROJECT_INSERT, _PROJECT_DRAFT)


def _guards():
    _execute(r"""
      CREATE OR REPLACE FUNCTION guard_guide_lineage_and_lifecycle() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP='INSERT' THEN
          IF NEW.status IS DISTINCT FROM 'draft' OR NEW.activation_operation_id IS NOT NULL
             OR NEW.contribution_policy_id IS NOT NULL OR NEW.contribution_policy_version_id IS NOT NULL
             OR NEW.approved_by IS NOT NULL OR NEW.effective_at IS NOT NULL OR NEW.superseded_at IS NOT NULL THEN
            RAISE EXCEPTION 'new guides must be draft and unbound' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END IF;
        IF (NEW.id,NEW.project_id,NEW.version) IS DISTINCT FROM (OLD.id,OLD.project_id,OLD.version) THEN
          RAISE EXCEPTION 'guide lineage is immutable' USING ERRCODE='55000';
        END IF;
        IF OLD.status='draft' AND NEW.status='active' AND
           NEW.mutation_generation IS DISTINCT FROM OLD.mutation_generation+1 THEN
          RAISE EXCEPTION 'guide activation generation mismatch' USING ERRCODE='23514';
        END IF;
        IF OLD.activation_operation_id IS NULL AND NEW.activation_operation_id IS NOT NULL
           AND NOT (OLD.status='draft' AND NEW.status='active') THEN
          RAISE EXCEPTION 'binding requires draft guide activation' USING ERRCODE='23514';
        END IF;
        IF OLD.activation_operation_id IS NOT NULL AND
           (NEW.activation_operation_id,NEW.contribution_policy_id,NEW.contribution_policy_version_id,
            NEW.mutation_generation,NEW.approved_by,NEW.effective_at,
            NEW.last_mutated_by_actor_profile_id,NEW.last_mutated_via_identity_link_id,
            NEW.last_mutated_by_admin_role_grant_id,NEW.last_mutation_action_id,
            NEW.last_mutation_scope_type,NEW.last_mutation_scope_project_id,NEW.last_authorization_decision_event_id)
           IS DISTINCT FROM
           (OLD.activation_operation_id,OLD.contribution_policy_id,OLD.contribution_policy_version_id,
            OLD.mutation_generation,OLD.approved_by,OLD.effective_at,
            OLD.last_mutated_by_actor_profile_id,OLD.last_mutated_via_identity_link_id,
            OLD.last_mutated_by_admin_role_grant_id,OLD.last_mutation_action_id,
            OLD.last_mutation_scope_type,OLD.last_mutation_scope_project_id,OLD.last_authorization_decision_event_id) THEN
          RAISE EXCEPTION 'guide activation binding is immutable' USING ERRCODE='55000';
        END IF;
        IF NEW.status='active' AND (NEW.activation_operation_id IS NULL OR NEW.contribution_policy_id IS NULL
           OR NEW.contribution_policy_version_id IS NULL OR NEW.effective_at IS NULL OR NEW.approved_by IS NULL
           OR NEW.superseded_at IS NOT NULL) THEN
          RAISE EXCEPTION 'active guide requires complete activation binding' USING ERRCODE='23514';
        END IF;
        IF NEW.status='draft' AND (NEW.activation_operation_id IS NOT NULL OR NEW.contribution_policy_id IS NOT NULL
           OR NEW.contribution_policy_version_id IS NOT NULL OR NEW.effective_at IS NOT NULL
           OR NEW.approved_by IS NOT NULL OR NEW.superseded_at IS NOT NULL) THEN
          RAISE EXCEPTION 'draft guide must remain unbound' USING ERRCODE='23514';
        END IF;
        IF (NEW.status,NEW.approved_by,NEW.effective_at,NEW.superseded_at)
            IS DISTINCT FROM (OLD.status,OLD.approved_by,OLD.effective_at,OLD.superseded_at) THEN
          IF NOT ((OLD.status='draft' AND NEW.status='active') OR
              (OLD.status='active' AND NEW.status='superseded' AND NEW.superseded_at IS NOT NULL
               AND NEW.approved_by IS NOT DISTINCT FROM OLD.approved_by
               AND NEW.effective_at IS NOT DISTINCT FROM OLD.effective_at)) THEN
            RAISE EXCEPTION 'invalid guide activation lifecycle transition' USING ERRCODE='23514';
          END IF;
        END IF;
        RETURN NEW;
      END $$;
      DROP TRIGGER guide_lineage_lifecycle_guard ON project_guides;
      CREATE TRIGGER guide_lineage_lifecycle_guard BEFORE INSERT OR UPDATE ON project_guides
        FOR EACH ROW EXECUTE FUNCTION guard_guide_lineage_and_lifecycle();

      CREATE FUNCTION require_guide_activation_custody(operation uuid, new_binding boolean) RETURNS void LANGUAGE plpgsql AS $$
      DECLARE r guide_mutation_idempotency_records%rowtype; g project_guides%rowtype;
        post project_post_policy_operations%rowtype; upstream project_guide_proposal_approvals%rowtype;
        f jsonb; a jsonb; receipt jsonb; command jsonb; target jsonb; locator jsonb; con jsonb;
      BEGIN
        SELECT * INTO r FROM guide_mutation_idempotency_records WHERE operation_id=operation;
        SELECT * INTO g FROM project_guides WHERE id=r.resource_id;
        f:=r.activation_facts_json::jsonb; a:=r.activation_authority_json::jsonb;
        receipt:=r.response_json::jsonb; command:=receipt->'command';
        target:=command->'target'; locator:=f->'locator'; con:=receipt->'contribution';
        IF jsonb_typeof(receipt) IS DISTINCT FROM 'object'
           OR jsonb_typeof(command) IS DISTINCT FROM 'object'
           OR jsonb_typeof(con) IS DISTINCT FROM 'object' THEN
          RAISE EXCEPTION 'guide activation immutable custody mismatch' USING ERRCODE='23514';
        END IF;
        IF (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(receipt) k)
           IS DISTINCT FROM ARRAY['activation_generation','command','contribution','effective_at','operation_id','prior_project_status'] THEN
          RAISE EXCEPTION 'guide activation receipt shape mismatch' USING ERRCODE='23514';
        END IF;
        IF (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(command) k)
           IS DISTINCT FROM ARRAY['contribution_policy_id','contribution_policy_version_id','expected_previous_active_guide_generation','expected_previous_active_guide_id','guide_mutation_generation','idempotency_key','post_approval_operation_id','post_approval_output_digest','review','revision','target'] THEN
          RAISE EXCEPTION 'guide activation receipt shape mismatch' USING ERRCODE='23514';
        END IF;
        IF (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(con) k)
           IS DISTINCT FROM ARRAY['adapter_binding_ids','contribution_policy_id','contribution_policy_version_id','project_id','purpose','rules_and_definitions_digest','version_number'] THEN
          RAISE EXCEPTION 'guide activation receipt shape mismatch' USING ERRCODE='23514';
        END IF;
        IF r.id IS NULL OR r.action_id IS DISTINCT FROM 'project.guide.activate'
           OR r.status IS DISTINCT FROM 'committed' OR r.setup_run_id IS NOT NULL
           OR g.id IS NULL OR g.project_id IS DISTINCT FROM r.project_id
           OR g.status NOT IN ('active','superseded') OR g.activation_operation_id IS DISTINCT FROM r.operation_id
           OR r.request_digest IS DISTINCT FROM guide_proposal_hash(command)
           OR r.resource_context_digest IS DISTINCT FROM guide_proposal_hash(f)
           OR f IS DISTINCT FROM jsonb_build_object('locator',locator,'receipt',receipt)
           OR locator IS DISTINCT FROM jsonb_build_object('project_id',r.project_id,'guide_id',g.id,
                'actor_profile_id',r.actor_profile_id,'identity_link_id',r.identity_link_id,
                'operation_id',r.operation_id::text,'action_id','project.guide.activate')
           OR receipt->>'operation_id' IS DISTINCT FROM r.operation_id::text
           OR command->>'idempotency_key' IS DISTINCT FROM r.idempotency_key::text
           OR (receipt->>'activation_generation')::integer IS DISTINCT FROM r.operation_generation
           OR r.operation_generation IS DISTINCT FROM (command->>'guide_mutation_generation')::integer+1
           OR g.mutation_generation IS DISTINCT FROM r.operation_generation
           OR g.effective_at IS DISTINCT FROM (receipt->>'effective_at')::timestamptz
           OR g.approved_by IS DISTINCT FROM r.actor_profile_id
           OR g.contribution_policy_id::text IS DISTINCT FROM command->>'contribution_policy_id'
           OR g.contribution_policy_version_id::text IS DISTINCT FROM command->>'contribution_policy_version_id'
           OR con->>'project_id' IS DISTINCT FROM r.project_id
           OR con->>'contribution_policy_id' IS DISTINCT FROM g.contribution_policy_id::text
           OR con->>'contribution_policy_version_id' IS DISTINCT FROM g.contribution_policy_version_id::text
           OR con->>'purpose' IS DISTINCT FROM 'guide_activation'
           OR target->'proposal'->>'project_id' IS DISTINCT FROM r.project_id
           OR target->'proposal'->>'guide_id' IS DISTINCT FROM g.id
           OR target->'proposal'->>'guide_version' IS DISTINCT FROM g.version
           OR (receipt->>'prior_project_status' IS DISTINCT FROM 'draft'
               AND receipt->>'prior_project_status' IS DISTINCT FROM 'active') THEN
          RAISE EXCEPTION 'guide activation immutable custody mismatch' USING ERRCODE='23514';
        END IF;
        IF (g.selected_review_policy_id,g.selected_review_policy_generation,g.selected_review_policy_hash,
            g.selected_revision_policy_id,g.selected_revision_policy_generation,g.selected_revision_policy_hash)
           IS DISTINCT FROM (command->'review'->>'policy_id',(command->'review'->>'generation')::integer,
            command->'review'->>'policy_hash',command->'revision'->>'policy_id',
            (command->'revision'->>'generation')::integer,command->'revision'->>'policy_hash')
           OR a IS DISTINCT FROM jsonb_build_object('actor_profile_id',r.actor_profile_id,
               'identity_link_id',r.identity_link_id,'admin_role_grant_id',g.last_mutated_by_admin_role_grant_id::text,
               'authorization_decision_event_id',g.last_authorization_decision_event_id,
               'action_id','project.guide.activate','permission_id','project.guide.manage',
               'scope_project_id',r.project_id,'resource_context_digest',r.resource_context_digest)
           OR (g.last_mutated_by_actor_profile_id,g.last_mutated_via_identity_link_id,g.last_mutation_action_id,
               g.last_mutation_scope_type,g.last_mutation_scope_project_id) IS DISTINCT FROM
              (r.actor_profile_id,r.identity_link_id,'project.guide.activate','project',r.project_id) THEN
          RAISE EXCEPTION 'guide activation selector or authority mismatch' USING ERRCODE='23514';
        END IF;
        IF new_binding THEN
          IF NOT EXISTS(SELECT 1 FROM guide_mutation_idempotency_records
              WHERE operation_id=operation AND xmin=pg_current_xact_id()::text::xid) THEN
            RAISE EXCEPTION 'activation requires this transaction operation' USING ERRCODE='23514';
          END IF;
          SELECT * INTO post FROM project_post_policy_operations
            WHERE operation_id=(command->>'post_approval_operation_id')::uuid AND kind='approve';
          SELECT * INTO upstream FROM project_guide_proposal_approvals
            WHERE operation_id=(target->'upstream'->>'operation_id')::uuid;
          IF post.operation_id IS NULL OR upstream.operation_id IS NULL
             OR post.target_json::jsonb IS DISTINCT FROM target
             OR post.output_digest IS DISTINCT FROM command->>'post_approval_output_digest'
             OR upstream.receipt_json::jsonb IS DISTINCT FROM target->'upstream'
             OR upstream.output_digest IS DISTINCT FROM target->>'upstream_output_digest'
             OR NOT EXISTS(SELECT 1 FROM checker_policies p WHERE p.id=post.policy_id
                  AND p.lifecycle_status='approved' AND p.approval_operation_id=post.operation_id)
             OR NOT EXISTS(SELECT 1 FROM submission_artifact_policies p WHERE p.id=upstream.artifact_policy_id
                  AND p.lifecycle_status='approved')
             OR NOT EXISTS(SELECT 1 FROM projects WHERE id=g.project_id AND status='active')
             OR NOT EXISTS(SELECT 1 FROM review_policies p WHERE p.id=g.selected_review_policy_id
                  AND p.semantics_status='complete' AND p.human_review_required=true)
             OR NOT EXISTS(SELECT 1 FROM revision_policies p WHERE p.id=g.selected_revision_policy_id
                  AND p.semantics_status='complete')
             OR (SELECT max(setup_generation) FROM project_setup_runs WHERE guide_id=g.id)
                  IS DISTINCT FROM (target->'proposal'->>'setup_generation')::integer
             OR NOT EXISTS(SELECT 1 FROM contribution_policy_versions v JOIN contribution_policies p
                  ON p.id=v.contribution_policy_id AND p.project_id=v.project_id
                  WHERE v.id=g.contribution_policy_version_id AND v.project_id=g.project_id
                    AND v.contribution_policy_id=g.contribution_policy_id AND v.status='published'
                    AND p.status='active' AND p.current_published_version_id=v.id
                    AND v.version_number=(con->>'version_number')::integer) THEN
            RAISE EXCEPTION 'guide activation approved generation unavailable' USING ERRCODE='23514';
          END IF;
          IF command->>'expected_previous_active_guide_id' IS NOT NULL THEN
            IF NOT EXISTS(SELECT 1 FROM project_guides prior
              WHERE prior.id=command->>'expected_previous_active_guide_id' AND prior.id<>g.id
                AND prior.project_id=g.project_id AND prior.status='superseded'
                AND prior.mutation_generation IS NOT DISTINCT FROM
                  (command->>'expected_previous_active_guide_generation')::integer
                AND prior.superseded_at=g.effective_at) THEN
              RAISE EXCEPTION 'guide activation predecessor mismatch' USING ERRCODE='23514';
            END IF;
          ELSIF command->>'expected_previous_active_guide_generation' IS NOT NULL THEN
            RAISE EXCEPTION 'guide activation predecessor shape mismatch' USING ERRCODE='23514';
          END IF;
          PERFORM require_guide_proposal_authority(r.actor_profile_id,r.identity_link_id,
            g.last_mutated_by_admin_role_grant_id,r.project_id,g.last_authorization_decision_event_id,
            'project.guide.activate','project.guide.manage','project_guide_activation',g.id,r.resource_context_digest);
        END IF;
      END $$;

      CREATE FUNCTION require_guide_activation_predecessor(prior_id text, prior_generation integer, superseded timestamptz)
        RETURNS void LANGUAGE plpgsql AS $$
      DECLARE operation uuid;
      BEGIN
        SELECT r.operation_id INTO operation FROM guide_mutation_idempotency_records r
          JOIN project_guides g ON g.activation_operation_id=r.operation_id AND g.project_id=r.project_id
          JOIN project_guides prior ON prior.id=prior_id AND prior.project_id=g.project_id
          WHERE r.action_id='project.guide.activate' AND r.status='committed'
            AND r.response_json->'command'->>'expected_previous_active_guide_id'=prior_id
            AND (r.response_json->'command'->>'expected_previous_active_guide_generation')::integer
                IS NOT DISTINCT FROM prior_generation
            AND g.effective_at=superseded AND g.status='active';
        IF operation IS NULL THEN
          RAISE EXCEPTION 'guide supersession requires exact successor activation' USING ERRCODE='23514';
        END IF;
        PERFORM require_guide_activation_custody(operation,true);
      END $$;

      CREATE FUNCTION require_project_activation_custody() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE operation uuid;
      BEGIN
        IF OLD.status='draft' AND NEW.status='active' THEN
          SELECT r.operation_id INTO operation FROM guide_mutation_idempotency_records r
            JOIN project_guides g ON g.activation_operation_id=r.operation_id AND g.project_id=r.project_id
            WHERE g.project_id=NEW.id AND g.status='active' AND r.action_id='project.guide.activate'
              AND r.status='committed' AND r.response_json->>'prior_project_status'='draft';
          IF operation IS NULL THEN
            RAISE EXCEPTION 'project activation requires exact guide custody' USING ERRCODE='23514';
          END IF;
          PERFORM require_guide_activation_custody(operation,true);
        END IF;
        RETURN NULL;
      END $$;
      CREATE CONSTRAINT TRIGGER project_activation_custody AFTER UPDATE OF status ON projects
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_project_activation_custody();
    """)


_PRIOR_GUIDE_GUARD = "CREATE OR REPLACE FUNCTION public.guard_guide_lineage_and_lifecycle() RETURNS trigger\n    LANGUAGE plpgsql\n    AS $$ begin\n          if (new.id,new.project_id,new.version)\n             is distinct from (old.id,old.project_id,old.version) then\n            raise exception 'guide identity and lineage are immutable' using errcode='23514';\n          end if;\n          if (new.status,new.approved_by,new.effective_at,new.superseded_at)\n             is distinct from (old.status,old.approved_by,old.effective_at,old.superseded_at) then\n            raise exception 'guide lifecycle mutation requires activation authority'\n              using errcode='23514';\n          end if;\n          return new;\n        end $$;"


def downgrade():
    connection = op.get_bind()
    if connection.scalar(text("SELECT EXISTS(SELECT 1 FROM guide_mutation_idempotency_records "
            "WHERE action_id='project.guide.activate') OR EXISTS(SELECT 1 FROM audit_events "
            "WHERE resource_type='project_guide_activation')")):
        raise RuntimeError("guide activation evidence prevents downgrade")
    _replace("validate_guide_mutation_custody", _MARKER, _BRANCH + _MARKER, reverse=True)
    _replace("guard_guide_mutation_idempotency", _IMMUTABLE, _ACTIVATION_IMMUTABLE, reverse=True)
    _replace("validate_project_create_custody", _PROJECT_INSERT, _PROJECT_DRAFT, reverse=True)
    _audit(reverse=True)
    _guide_authority_shape(reverse=True)
    _execute(_PRIOR_GUIDE_GUARD)
    _execute("""
      DROP TRIGGER project_activation_custody ON projects;
      DROP FUNCTION require_project_activation_custody();
      DROP FUNCTION require_guide_activation_predecessor(text,integer,timestamptz);
      DROP FUNCTION require_guide_activation_custody(uuid,boolean);
      DROP TRIGGER guide_lineage_lifecycle_guard ON project_guides;
      CREATE TRIGGER guide_lineage_lifecycle_guard BEFORE UPDATE ON project_guides
        FOR EACH ROW EXECUTE FUNCTION guard_guide_lineage_and_lifecycle();
      ALTER TABLE project_guides DROP CONSTRAINT fk_project_guides_activation_operation;
      ALTER TABLE project_guides DROP CONSTRAINT fk_project_guides_contribution_policy;
      ALTER TABLE project_guides DROP CONSTRAINT ck_project_guides_activation_binding_shape;
      ALTER TABLE project_guides DROP COLUMN activation_operation_id;
      ALTER TABLE project_guides DROP COLUMN contribution_policy_id;
      ALTER TABLE project_guides DROP COLUMN contribution_policy_version_id;
      DROP INDEX uq_guide_activation_audit_decision;
      ALTER TABLE guide_mutation_idempotency_records DROP CONSTRAINT ck_guide_mutation_idempotency_records_activation_evidence_shape;
      ALTER TABLE guide_mutation_idempotency_records DROP CONSTRAINT uq_guide_mutation_operation_resource;
      ALTER TABLE guide_mutation_idempotency_records DROP CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_action;
      ALTER TABLE guide_mutation_idempotency_records ADD CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_action CHECK(
        action_id IN ('project.guide.create','project.guide.update','project.guide_source_snapshot.create'));
      ALTER TABLE guide_mutation_idempotency_records DROP COLUMN activation_facts_json;
      ALTER TABLE guide_mutation_idempotency_records DROP COLUMN activation_authority_json;
    """)
