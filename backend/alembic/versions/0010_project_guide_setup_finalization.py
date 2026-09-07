"""Install immutable hidden setup finalization without activating authority."""

from alembic import op
import sqlalchemy as sa

revision = "0010_project_guide_setup_finalization"
down_revision = "0009_guide_compilation_projections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Bind exact receipt custody and the setup closure in one root transaction."""
    op.create_unique_constraint("uq_projection_operation_finalization_lineage",
        "project_guide_component_projection_operations",
        ["operation_id", "compilation_id", "setup_run_id", "setup_generation"])
    op.execute(r"""
CREATE TABLE project_guide_setup_finalizations (
	id UUID NOT NULL, 
	operation_id UUID NOT NULL, 
	correlation_id UUID NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	guide_id VARCHAR(36) NOT NULL, 
	guide_version VARCHAR(50) NOT NULL, 
	source_snapshot_id VARCHAR(36) NOT NULL, 
	source_snapshot_hash VARCHAR(71) NOT NULL, 
	setup_run_id VARCHAR(36) NOT NULL, 
	setup_generation BIGINT NOT NULL, 
	celery_task_id VARCHAR(155) NOT NULL, 
	source_state_digest VARCHAR(71) NOT NULL, 
	attempt_id UUID NOT NULL, 
	request_operation_id UUID NOT NULL, 
	provider_idempotency_key UUID NOT NULL, 
	compilation_id UUID NOT NULL, 
	canonical_input_hash VARCHAR(71) NOT NULL, 
	result_hash VARCHAR(71) NOT NULL, 
	result_schema_version VARCHAR(100) NOT NULL, 
	compilation_agent_name VARCHAR(100) NOT NULL, 
	compilation_agent_version VARCHAR(100) NOT NULL, 
	component_hashes JSON NOT NULL, 
	sufficiency_operation_id UUID NOT NULL, 
	sufficiency_report_id VARCHAR(36) NOT NULL, 
	sufficiency_output_digest VARCHAR(71) NOT NULL, 
	artifact_policy_operation_id UUID, 
	artifact_policy_id VARCHAR(36), 
	artifact_policy_output_digest VARCHAR(71), 
	result_classification VARCHAR(40) NOT NULL, 
	setup_outcome VARCHAR(40) NOT NULL, 
	facts_digest VARCHAR(71) NOT NULL, 
	authority_resource_digest VARCHAR(71) NOT NULL, 
	authorization_decision_event_id VARCHAR(36) NOT NULL, 
	actor_profile_id VARCHAR(36) NOT NULL, 
	identity_link_id VARCHAR(36) NOT NULL, 
	service_identity VARCHAR(160) NOT NULL, 
	action_id VARCHAR(160) NOT NULL, 
	permission_id VARCHAR(120) NOT NULL, 
	scope_type VARCHAR(16) NOT NULL, 
	scope_project_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT transaction_timestamp() NOT NULL, 
	CONSTRAINT pk_project_guide_setup_finalizations PRIMARY KEY (id), 
	CONSTRAINT fk_finalization_compilation_attempt FOREIGN KEY(compilation_id, attempt_id) REFERENCES project_guide_compilations (id, attempt_id), 
	CONSTRAINT fk_finalization_exact_attempt FOREIGN KEY(attempt_id, project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation) REFERENCES project_guide_compilation_attempts (id, project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation), 
	CONSTRAINT fk_finalization_exact_setup FOREIGN KEY(setup_run_id, project_id, guide_id, source_snapshot_id, setup_generation) REFERENCES project_setup_runs (id, project_id, guide_id, source_snapshot_id, setup_generation), 
	CONSTRAINT fk_finalization_sufficiency_lineage FOREIGN KEY(sufficiency_operation_id, compilation_id, setup_run_id, setup_generation) REFERENCES project_guide_component_projection_operations (operation_id, compilation_id, setup_run_id, setup_generation), 
	CONSTRAINT fk_finalization_policy_lineage FOREIGN KEY(artifact_policy_operation_id, compilation_id, setup_run_id, setup_generation) REFERENCES project_guide_component_projection_operations (operation_id, compilation_id, setup_run_id, setup_generation), 
	CONSTRAINT fk_finalization_actor_link FOREIGN KEY(identity_link_id, actor_profile_id) REFERENCES actor_identity_links (id, actor_profile_id), 
	CONSTRAINT uq_finalization_setup_generation UNIQUE (setup_run_id, setup_generation), 
	CONSTRAINT uq_finalization_compilation UNIQUE (compilation_id), 
	CONSTRAINT uq_finalization_operation UNIQUE (operation_id), 
	CONSTRAINT uq_finalization_decision UNIQUE (authorization_decision_event_id), 
	CONSTRAINT ck_project_guide_setup_finalizations_ck_finalization_pr_ac00 CHECK ((result_classification='guide_blocked' and setup_outcome='sufficiency_blocked' and artifact_policy_operation_id is null and artifact_policy_id is null and artifact_policy_output_digest is null) or (result_classification in ('draft_ready','draft_ready_with_warnings') and setup_outcome='policy_draft_ready' and artifact_policy_operation_id is not null and artifact_policy_id is not null and artifact_policy_output_digest is not null)), 
	CONSTRAINT ck_project_guide_setup_finalizations_ck_finalization_authority CHECK (setup_generation > 0 and service_identity='workstream.project.setup' and action_id='project.setup_run.update' and permission_id='project.guide.manage' and scope_type='project' and scope_project_id=project_id), 
	CONSTRAINT ck_project_guide_setup_finalizations_ck_finalization_hashes CHECK (source_snapshot_hash~ '^sha256:[0-9a-f]{64}$' and source_state_digest~ '^sha256:[0-9a-f]{64}$' and canonical_input_hash~ '^sha256:[0-9a-f]{64}$' and result_hash~ '^sha256:[0-9a-f]{64}$' and sufficiency_output_digest~ '^sha256:[0-9a-f]{64}$' and facts_digest~ '^sha256:[0-9a-f]{64}$' and authority_resource_digest~ '^sha256:[0-9a-f]{64}$' and (artifact_policy_output_digest is null or artifact_policy_output_digest ~ '^sha256:[0-9a-f]{64}$')), 
	CONSTRAINT ck_project_guide_setup_finalizations_ck_finalization_components CHECK (json_typeof(component_hashes)='object' and component_hashes::jsonb=jsonb_build_object('sufficiency_hash',component_hashes->>'sufficiency_hash','artifact_policy_hash',component_hashes->>'artifact_policy_hash','requirement_inventory_hash',component_hashes->>'requirement_inventory_hash','pre_submit_hash',component_hashes->>'pre_submit_hash','post_submit_hash',component_hashes->>'post_submit_hash','capability_suggestions_hash',component_hashes->>'capability_suggestions_hash','setup_notes_hash',component_hashes->>'setup_notes_hash') and coalesce((component_hashes->>'sufficiency_hash') ~ '^sha256:[0-9a-f]{64}$',false) and coalesce((component_hashes->>'artifact_policy_hash') ~ '^sha256:[0-9a-f]{64}$',false) and coalesce((component_hashes->>'requirement_inventory_hash') ~ '^sha256:[0-9a-f]{64}$',false) and coalesce((component_hashes->>'pre_submit_hash') ~ '^sha256:[0-9a-f]{64}$',false) and coalesce((component_hashes->>'post_submit_hash') ~ '^sha256:[0-9a-f]{64}$',false) and coalesce((component_hashes->>'capability_suggestions_hash') ~ '^sha256:[0-9a-f]{64}$',false) and coalesce((component_hashes->>'setup_notes_hash') ~ '^sha256:[0-9a-f]{64}$',false)), 
	CONSTRAINT fk_project_guide_setup_finalizations_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id), 
	CONSTRAINT fk_project_guide_setup_finalizations_guide_id_project_guides FOREIGN KEY(guide_id) REFERENCES project_guides (id), 
	CONSTRAINT fk_project_guide_setup_finalizations_request_operation__c6a1 FOREIGN KEY(request_operation_id) REFERENCES project_guide_compilation_request_operations (operation_id), 
	CONSTRAINT fk_project_guide_setup_finalizations_sufficiency_report_dfc6 FOREIGN KEY(sufficiency_report_id) REFERENCES guide_sufficiency_reports (id), 
	CONSTRAINT fk_project_guide_setup_finalizations_artifact_policy_id_eb23 FOREIGN KEY(artifact_policy_id) REFERENCES submission_artifact_policies (id), 
	CONSTRAINT fk_project_guide_setup_finalizations_authorization_deci_9791 FOREIGN KEY(authorization_decision_event_id) REFERENCES audit_events (id), 
	CONSTRAINT fk_project_guide_setup_finalizations_actor_profile_id_a_109b FOREIGN KEY(actor_profile_id) REFERENCES actor_profiles (id)
)

""")
    _audit_resource(add=True)
    _digests()
    _receipt_guard()
    _setup_guard()
    _deferred_custody()


def _audit_resource(*, add: bool) -> None:
    """Extend only the audit resource vocabulary, never action availability."""
    definition = op.get_bind().execute(sa.text(
        "select pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid='audit_events'::regclass "
        "and conname='ck_audit_events_authority_privacy_bounds'"
    )).scalar_one()
    anchor = "('project_submission_artifact_policy_projection'::character varying)::text"
    token = ", ('project_guide_setup_finalization'::character varying)::text"
    if anchor not in definition:
        raise RuntimeError("audit resource constraint shape changed")
    amended = definition.replace(anchor, anchor + token, 1) if add else definition.replace(token, "", 1)
    op.execute("alter table audit_events drop constraint ck_audit_events_authority_privacy_bounds")
    op.execute("alter table audit_events add constraint ck_audit_events_authority_privacy_bounds " + amended)


def _digests() -> None:
    """Reuse canonical JSON encoding and install explicit complete digest vectors."""
    op.execute(r"""
    create function project_guide_finalization_facts(item project_guide_setup_finalizations)
    returns jsonb immutable strict language sql as $$
        select jsonb_build_object(
            'project_id', item.project_id,
            'guide_id', item.guide_id,
            'guide_version', item.guide_version,
            'source_snapshot_id', item.source_snapshot_id,
            'source_snapshot_hash', item.source_snapshot_hash,
            'setup_run_id', item.setup_run_id,
            'setup_generation', item.setup_generation,
            'celery_task_id', item.celery_task_id,
            'source_state_digest', item.source_state_digest,
            'operation_id', item.operation_id,
            'correlation_id', item.correlation_id,
            'finalization_id', item.id,
            'attempt_id', item.attempt_id,
            'request_operation_id', item.request_operation_id,
            'provider_idempotency_key', item.provider_idempotency_key,
            'compilation_id', item.compilation_id,
            'canonical_input_hash', item.canonical_input_hash,
            'result_hash', item.result_hash,
            'result_schema_version', item.result_schema_version,
            'compilation_agent_name', item.compilation_agent_name,
            'compilation_agent_version', item.compilation_agent_version,
            'component_hashes', item.component_hashes,
            'result_classification', item.result_classification,
            'setup_outcome', item.setup_outcome,
            'sufficiency_operation_id', item.sufficiency_operation_id,
            'sufficiency_report_id', item.sufficiency_report_id,
            'sufficiency_output_digest', item.sufficiency_output_digest,
            'artifact_policy_operation_id', item.artifact_policy_operation_id,
            'artifact_policy_id', item.artifact_policy_id,
            'artifact_policy_output_digest', item.artifact_policy_output_digest
        )
    $$;
    """)
    op.execute(r"""
    create function project_guide_finalization_digest(item project_guide_setup_finalizations)
    returns text immutable strict language sql as $$
      select 'sha256:' || encode(sha256(convert_to(
        project_guide_projection_canonical_json(jsonb_build_object(
          'domain','workstream.project_guide_setup_finalization.facts.v1',
          'facts',project_guide_finalization_facts(item))), 'UTF8')), 'hex')
    $$;
    """)
    op.execute(r"""
    create function project_guide_finalization_authority_digest(item project_guide_setup_finalizations)
    returns text immutable strict language sql as $$
      select 'sha256:' || encode(sha256(convert_to(
        project_guide_projection_canonical_json(jsonb_build_object(
          'domain','workstream.project_guide_setup_finalization.authority.v1',
          'facts',jsonb_build_object(
            'action_id',item.action_id,'permission_id',item.permission_id,
            'resource_type','project_guide_setup_finalization','resource_id',item.id,
            'scope_project_id',item.project_id,'actor_profile_id',item.actor_profile_id,
            'identity_link_id',item.identity_link_id,'service_identity',item.service_identity,
            'facts_digest',item.facts_digest))), 'UTF8')), 'hex')
    $$;
    """)
    op.execute(r"""
    create function project_guide_finalization_source_digest(item project_setup_runs)
    returns text stable strict language sql as $$
      select 'sha256:' || encode(sha256(convert_to(
        project_guide_projection_canonical_json(jsonb_build_object(
          'domain','workstream.project_guide_projection.source_state.v1',
          'facts',jsonb_build_object(
            'celery_task_id',item.celery_task_id,
            'continuation_started_at',case when item.continuation_started_at is null then null
              else regexp_replace(to_char(item.continuation_started_at at time zone 'UTC',
                'YYYY-MM-DD"T"HH24:MI:SS.US'), '\.000000$', '') || '+00:00' end,
            'continuation_verification_job_id',item.continuation_verification_job_id,
            'current_step',item.current_step,'error_artifact_incident_id',item.error_artifact_incident_id,
            'error_code',item.error_code,'error_summary',item.error_summary,
            'finished_at',null,'guide_id',item.guide_id,
            'guide_status',(select status from project_guides where id=item.guide_id),
            'guide_version',item.guide_version,
            'output_post_submit_checker_policy_id',item.output_post_submit_checker_policy_id,
            'output_submission_artifact_policy_id',item.output_submission_artifact_policy_id,
            'output_sufficiency_report_id',item.output_sufficiency_report_id,
            'post_submit_derivation_summary',item.post_submit_derivation_summary,
            'setup_generation',item.setup_generation,'setup_run_id',item.id,
            'source_snapshot_hash',item.source_snapshot_hash,'source_snapshot_id',item.source_snapshot_id,
            'started_at',null,'status',item.status))), 'UTF8')), 'hex')
    $$;
    """)


def _receipt_guard() -> None:
    """Reject direct writes whose immutable inputs or authority do not agree."""
    op.execute(r"""
    create function guard_project_guide_setup_finalization()
    returns trigger language plpgsql as $$
    declare
      c project_guide_compilations%rowtype;
      a project_guide_compilation_attempts%rowtype;
      q project_guide_compilation_request_operations%rowtype;
      s project_setup_runs%rowtype;
      g project_guides%rowtype;
      snap guide_source_snapshots%rowtype;
      sufficient project_guide_component_projection_operations%rowtype;
      policy project_guide_component_projection_operations%rowtype;
      evidence audit_events%rowtype;
      p project_guide_component_projection_operations%rowtype;
    begin
      new.created_at := transaction_timestamp();
      select * into c from project_guide_compilations where id=new.compilation_id;
      select * into a from project_guide_compilation_attempts where id=new.attempt_id;
      select * into q from project_guide_compilation_request_operations where operation_id=new.request_operation_id;
      select * into s from project_setup_runs where id=new.setup_run_id for update;
      select * into g from project_guides where id=new.guide_id;
      select * into snap from guide_source_snapshots where id=new.source_snapshot_id;
      if c.id is null or a.id is null or q.operation_id is null or s.id is null
         or g.id is null or snap.id is null
         or a.status is distinct from 'compilation_persisted'
         or a.persisted_compilation_id is distinct from c.id
         or c.attempt_id is distinct from a.id or q.attempt_id is distinct from a.id
         or new.provider_idempotency_key is distinct from a.provider_idempotency_key
         or new.canonical_input_hash is distinct from c.canonical_input_hash
         or c.canonical_input_hash is distinct from a.canonical_input_hash
         or new.result_hash is distinct from c.result_hash
         or new.component_hashes::jsonb is distinct from c.component_hashes::jsonb
         or new.result_classification is distinct from c.canonical_result->>'status'
         or new.result_schema_version is distinct from c.canonical_result->>'schema_version'
         or new.compilation_agent_name is distinct from c.canonical_result->>'agent_name'
         or new.compilation_agent_version is distinct from c.canonical_result->>'agent_version'
         or g.status is distinct from 'draft'
         or new.project_id is distinct from g.project_id
         or new.guide_version is distinct from g.version
         or new.source_snapshot_hash is distinct from snap.bundle_hash
         or snap.project_id is distinct from new.project_id
         or snap.guide_id is distinct from new.guide_id
         or snap.guide_version is distinct from new.guide_version
         or s.guide_version is distinct from new.guide_version
         or s.source_snapshot_hash is distinct from new.source_snapshot_hash
         or s.celery_task_id is distinct from new.celery_task_id
         or s.status is distinct from 'queued' or s.current_step is distinct from 'queued'
         or s.started_at is not null or s.finished_at is not null
         or s.output_sufficiency_report_id is not null or s.output_submission_artifact_policy_id is not null
         or s.output_post_submit_checker_policy_id is not null or s.post_submit_derivation_summary is not null
         or s.error_code is not null or s.error_summary is not null or s.error_artifact_incident_id is not null
         or (s.continuation_verification_job_id is null)<>(s.continuation_started_at is null)
         or new.source_state_digest is distinct from project_guide_finalization_source_digest(s)
         or c.project_id is distinct from new.project_id
         or c.guide_id is distinct from new.guide_id
         or c.guide_version is distinct from new.guide_version
         or c.source_snapshot_id is distinct from new.source_snapshot_id
         or c.source_snapshot_hash is distinct from new.source_snapshot_hash
         or c.setup_run_id is distinct from new.setup_run_id
         or c.setup_generation is distinct from new.setup_generation
         or q.project_id is distinct from new.project_id
         or q.guide_id is distinct from new.guide_id
         or q.source_snapshot_id is distinct from new.source_snapshot_id
         or q.setup_run_id is distinct from new.setup_run_id
         or q.setup_generation is distinct from new.setup_generation
         or exists(select 1 from project_guide_compilations where supersedes_compilation_id=c.id)
         or exists(select 1 from project_setup_runs where guide_id=new.guide_id
                   and setup_generation>new.setup_generation)
         or exists(select 1 from guide_source_snapshots where guide_id=new.guide_id
                   and guide_version=new.guide_version and id<>snap.id and captured_at>=snap.captured_at)
      then raise exception 'finalization compilation lineage mismatch' using errcode='23514'; end if;
      select * into sufficient from project_guide_component_projection_operations
        where operation_id=new.sufficiency_operation_id;
      select * into policy from project_guide_component_projection_operations
        where operation_id=new.artifact_policy_operation_id;
      if sufficient.operation_id is null or sufficient.component is distinct from 'guide_sufficiency'
         or sufficient.report_id is distinct from new.sufficiency_report_id
         or sufficient.output_id::text is distinct from new.sufficiency_report_id
         or sufficient.output_digest is distinct from new.sufficiency_output_digest
         or sufficient.prior_operation_id is not null or sufficient.prior_output_id is not null
         or sufficient.prior_output_digest is not null
         or sufficient.component_hash is distinct from c.component_hashes->>'sufficiency_hash'
         or sufficient.material_sha256 is distinct from a.guide_material_hash
         or sufficient.output_digest is distinct from project_guide_projection_business_digest(sufficient)
         or (select status from guide_sufficiency_reports where id=new.sufficiency_report_id)
              is distinct from (case new.result_classification when 'guide_blocked' then 'blocked'
                when 'draft_ready' then 'passed' else 'passed_with_warnings' end)
      then raise exception 'finalization sufficiency custody mismatch' using errcode='23514'; end if;
      if new.result_classification='guide_blocked' then
        if exists(select 1 from project_guide_component_projection_operations
                  where setup_run_id=new.setup_run_id and setup_generation=new.setup_generation
                    and component='submission_artifact_policy') then
          raise exception 'blocked finalization has policy custody' using errcode='23514';
        end if;
      elsif policy.operation_id is null or policy.component is distinct from 'submission_artifact_policy'
         or policy.policy_id is distinct from new.artifact_policy_id
         or policy.output_id::text is distinct from new.artifact_policy_id
         or policy.output_digest is distinct from new.artifact_policy_output_digest
         or policy.prior_operation_id is distinct from sufficient.operation_id
         or policy.prior_output_id is distinct from sufficient.output_id
         or policy.prior_output_digest is distinct from sufficient.output_digest
         or policy.component_hash is distinct from c.component_hashes->>'artifact_policy_hash'
         or policy.output_digest is distinct from project_guide_projection_business_digest(policy)
         or (select lifecycle_status from submission_artifact_policies where id=new.artifact_policy_id)
              is distinct from 'draft'
      then raise exception 'finalization policy custody mismatch' using errcode='23514'; end if;
      for p in select * from project_guide_component_projection_operations
        where operation_id in (new.sufficiency_operation_id,new.artifact_policy_operation_id)
      loop
        if p.compilation_id is distinct from c.id or p.attempt_id is distinct from a.id
           or p.request_operation_id is distinct from q.operation_id
           or p.provider_idempotency_key is distinct from new.provider_idempotency_key
           or p.project_id is distinct from new.project_id or p.guide_id is distinct from new.guide_id
           or p.guide_version is distinct from new.guide_version
           or p.source_snapshot_id is distinct from new.source_snapshot_id
           or p.source_snapshot_hash is distinct from new.source_snapshot_hash
           or p.setup_run_id is distinct from new.setup_run_id
           or p.setup_generation is distinct from new.setup_generation
           or p.celery_task_id is distinct from new.celery_task_id
           or p.source_state_digest is distinct from new.source_state_digest
           or p.result_hash is distinct from new.result_hash
           or p.result_schema_version is distinct from new.result_schema_version
           or p.compilation_agent_name is distinct from new.compilation_agent_name
           or p.compilation_agent_version is distinct from new.compilation_agent_version
        then raise exception 'finalization projection lineage mismatch' using errcode='23514'; end if;
      end loop;
      if new.facts_digest is distinct from project_guide_finalization_digest(new)
         or new.authority_resource_digest is distinct from project_guide_finalization_authority_digest(new)
      then raise exception 'finalization digest mismatch' using errcode='23514'; end if;
      select * into evidence from audit_events where id=new.authorization_decision_event_id;
      if evidence.id is null or evidence.event_domain is distinct from 'authority'
         or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
         or evidence.actor_ref_kind is distinct from 'actor_profile' or evidence.denial_code is not null
         or evidence.actor_id is distinct from new.actor_profile_id
         or evidence.action_id is distinct from new.action_id
         or evidence.permission_id is distinct from new.permission_id
         or evidence.project_id is distinct from new.project_id
         or evidence.resource_type is distinct from 'project_guide_setup_finalization'
         or evidence.resource_id is distinct from new.id::text
         or evidence.request_id is distinct from new.operation_id::text
         or evidence.correlation_id is distinct from new.correlation_id::text
         or not exists(select 1 from actor_profiles actor join actor_identity_links link
              on link.actor_profile_id=actor.id where actor.id=new.actor_profile_id
                and link.id=new.identity_link_id and actor.actor_kind='service'
                and actor.service_identity='workstream.project.setup'
                and link.subject_kind='service' and link.subject='workstream.project.setup')
         or evidence.after_facts->>'allowed' is distinct from 'true'
         or evidence.after_facts->>'resource_context_digest' is distinct from new.authority_resource_digest
      then raise exception 'finalization authority mismatch' using errcode='23514'; end if;
      return new;
    end; $$;
    """)
    op.execute("create trigger finalization_insert_guard before insert on project_guide_setup_finalizations "
               "for each row execute function guard_project_guide_setup_finalization()")
    op.execute("create trigger finalization_change_guard before update or delete on project_guide_setup_finalizations "
               "for each row execute function reject_project_guide_projection_change()")
    op.execute("create trigger finalization_truncate_guard before truncate on project_guide_setup_finalizations "
               "execute function reject_project_guide_projection_change()")


def _setup_guard() -> None:
    """Scope closure guards to unified-owned generations and preserve exact update width."""
    op.execute(r"""
    create function guard_finalized_project_setup()
    returns trigger language plpgsql as $$
    declare
      owned boolean;
      source_digest text;
      allowed_columns text[] := array['status','current_step','output_sufficiency_report_id',
                                     'output_submission_artifact_policy_id','finished_at'];
    begin
      if tg_op='TRUNCATE' then
        if exists(select 1 from project_guide_setup_finalizations) then
          raise exception 'finalized setup is immutable' using errcode='55000'; end if;
        return null;
      end if;
      if exists(select 1 from project_guide_setup_finalizations where setup_run_id=old.id)
         and (tg_op='DELETE' or old.finished_at is not null) then
        raise exception 'finalized setup is immutable' using errcode='55000'; end if;
      if tg_op='DELETE' then return old; end if;
      select exists(select 1 from project_guide_compilations where setup_run_id=old.id)
          or exists(select 1 from project_guide_component_projection_operations where setup_run_id=old.id)
          or exists(select 1 from project_guide_setup_finalizations where setup_run_id=old.id)
        into owned;
      if not owned then return new; end if;
      if new.status in ('sufficiency_blocked','policy_draft_ready')
         or new.output_sufficiency_report_id is not null
         or new.output_submission_artifact_policy_id is not null then
        if old.status is distinct from 'queued' or old.current_step is distinct from 'queued'
           or old.celery_task_id is null
           or (old.continuation_verification_job_id is null)<>(old.continuation_started_at is null)
           or old.error_code is not null or old.error_summary is not null
           or old.error_artifact_incident_id is not null or old.started_at is not null
           or old.finished_at is not null or old.post_submit_derivation_summary is not null
           or old.output_sufficiency_report_id is not null
           or old.output_submission_artifact_policy_id is not null
           or old.output_post_submit_checker_policy_id is not null
           or (to_jsonb(new)-allowed_columns) is distinct from (to_jsonb(old)-allowed_columns)
           or new.status not in ('sufficiency_blocked','policy_draft_ready')
           or new.output_sufficiency_report_id is null
           or new.current_step is distinct from (case new.status
              when 'sufficiency_blocked' then 'guide_sufficiency'
              else 'submission_artifact_policy_derivation' end)
           or (new.status='sufficiency_blocked' and new.output_submission_artifact_policy_id is not null)
           or (new.status='policy_draft_ready' and new.output_submission_artifact_policy_id is null)
        then raise exception 'invalid finalization setup transition' using errcode='23514'; end if;
        source_digest := project_guide_finalization_source_digest(old);
        if exists(select 1 from project_guide_component_projection_operations where setup_run_id=old.id
                    and source_state_digest is distinct from source_digest)
           or exists(select 1 from project_guide_setup_finalizations where setup_run_id=old.id
                    and source_state_digest is distinct from source_digest)
        then raise exception 'finalization source state mismatch' using errcode='23514'; end if;
        new.finished_at := transaction_timestamp();
      end if;
      return new;
    end; $$;
    """)
    op.execute("create trigger finalization_setup_change_guard before update or delete on project_setup_runs "
               "for each row execute function guard_finalized_project_setup()")
    op.execute("create trigger finalization_setup_truncate_guard before truncate on project_setup_runs "
               "execute function guard_finalized_project_setup()")


def _deferred_custody() -> None:
    """Require both custody directions at commit after receipt-then-transition writes."""
    op.execute(r"""
    create function validate_project_setup_finalization_custody()
    returns trigger language plpgsql as $$
    declare s project_setup_runs%rowtype;
    declare receipt project_guide_setup_finalizations%rowtype;
    declare selected_setup text;
    declare owned boolean;
    begin
      if tg_table_name='project_setup_runs' then selected_setup := new.id::text;
      else selected_setup := new.setup_run_id; end if;
      select * into s from project_setup_runs where id=selected_setup;
      select * into receipt from project_guide_setup_finalizations where setup_run_id=selected_setup;
      select exists(select 1 from project_guide_compilations where setup_run_id=selected_setup)
          or exists(select 1 from project_guide_component_projection_operations where setup_run_id=selected_setup)
          or receipt.id is not null into owned;
      if not owned then return null; end if;
      if receipt.id is null then
        if s.status in ('sufficiency_blocked','policy_draft_ready')
           or s.output_sufficiency_report_id is not null or s.output_submission_artifact_policy_id is not null
        then raise exception 'setup finalization receipt missing' using errcode='23514'; end if;
      elsif s.id is null or s.project_id is distinct from receipt.project_id
         or s.guide_id is distinct from receipt.guide_id or s.guide_version is distinct from receipt.guide_version
         or s.source_snapshot_id is distinct from receipt.source_snapshot_id
         or s.source_snapshot_hash is distinct from receipt.source_snapshot_hash
         or s.setup_generation is distinct from receipt.setup_generation
         or s.celery_task_id is distinct from receipt.celery_task_id
         or s.status is distinct from receipt.setup_outcome
         or s.current_step is distinct from (case receipt.setup_outcome when 'sufficiency_blocked'
              then 'guide_sufficiency' else 'submission_artifact_policy_derivation' end)
         or s.output_sufficiency_report_id is distinct from receipt.sufficiency_report_id
         or s.output_submission_artifact_policy_id is distinct from receipt.artifact_policy_id
         or s.finished_at is distinct from receipt.created_at
         or s.output_post_submit_checker_policy_id is not null
         or s.post_submit_derivation_summary is not null or s.started_at is not null
         or s.error_code is not null or s.error_summary is not null or s.error_artifact_incident_id is not null
      then raise exception 'setup finalization custody mismatch' using errcode='23514'; end if;
      return null;
    end; $$;
    """)
    for table in ("project_guide_setup_finalizations", "project_setup_runs"):
        condition = (
            "when (new.status in ('sufficiency_blocked','policy_draft_ready') "
            "or new.output_sufficiency_report_id is not null "
            "or new.output_submission_artifact_policy_id is not null) "
            if table == "project_setup_runs" else ""
        )
        op.execute(f"create constraint trigger finalization_atomic_custody after insert or update on {table} "
                   "deferrable initially deferred for each row " + condition +
                   "execute function validate_project_setup_finalization_custody()")


def downgrade() -> None:
    """Remove only empty finalization custody; never delete immutable history."""
    if op.get_bind().execute(sa.text("select exists(select 1 from project_guide_setup_finalizations)")).scalar_one():
        raise RuntimeError("finalization custody is non-empty")
    for trigger in ("finalization_atomic_custody", "finalization_setup_change_guard", "finalization_setup_truncate_guard"):
        op.execute(f"drop trigger {trigger} on project_setup_runs")
    op.execute("drop function project_guide_finalization_authority_digest(project_guide_setup_finalizations)")
    op.execute("drop function project_guide_finalization_digest(project_guide_setup_finalizations)")
    op.execute("drop function project_guide_finalization_facts(project_guide_setup_finalizations)")
    op.execute("drop function project_guide_finalization_source_digest(project_setup_runs)")
    op.drop_table("project_guide_setup_finalizations")
    op.execute("drop function validate_project_setup_finalization_custody()")
    op.execute("drop function guard_finalized_project_setup()")
    op.execute("drop function guard_project_guide_setup_finalization()")
    op.drop_constraint("uq_projection_operation_finalization_lineage",
                       "project_guide_component_projection_operations", type_="unique")
    _audit_resource(add=False)
