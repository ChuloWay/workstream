CREATE FUNCTION public.authority_event_facts_are_safe(event_name text, before_state json, after_state json, envelope_project_id text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    AS $$
        begin
          if not (event_name='AuthorityInvalidationRequested'
                  and before_state is not null
                  and after_state is not null
                  and coalesce(before_state::jsonb ? 'future_obligation', false)
                  and coalesce(after_state::jsonb ? 'future_obligation', false))
             and ((before_state is not null and not authority_facts_are_safe(before_state))
               or (after_state is not null and not authority_facts_are_safe(after_state))) then
            return false;
          end if;
          case event_name
            when 'ActorProfileProvisioned' then return before_state is null and after_state::jsonb =
              '{"status":"active","subject_kind":"human","provisioning_method":"automatic_first_access"}'::jsonb;
            when 'ServiceActorProvisioned' then return before_state is null and after_state::jsonb =
              '{"status":"active","subject_kind":"service","provisioning_method":"manual_service_provisioning"}'::jsonb;
            when 'ActorIdentityLinked' then return before_state is null and after_state::jsonb in (
              '{"status":"active","subject_kind":"human"}'::jsonb,
              '{"status":"active","subject_kind":"service"}'::jsonb);
            when 'ActorIdentityLinkRevoked' then return before_state::jsonb='{"status":"active"}'::jsonb and after_state::jsonb='{"status":"revoked"}'::jsonb;
            when 'ActorIdentityLinkReactivated' then return before_state::jsonb='{"status":"revoked"}'::jsonb and after_state::jsonb='{"status":"active"}'::jsonb;
            when 'ActorProfileSuspended' then return before_state::jsonb='{"status":"active"}'::jsonb and after_state::jsonb='{"status":"suspended"}'::jsonb;
            when 'ActorProfileReactivated' then return before_state::jsonb='{"status":"suspended"}'::jsonb and after_state::jsonb='{"status":"active"}'::jsonb;
            when 'ActorProfileDeactivated' then return before_state::jsonb in ('{"status":"active"}'::jsonb,'{"status":"suspended"}'::jsonb) and after_state::jsonb='{"status":"deactivated"}'::jsonb;
            when 'InitialAccessAdministratorBootstrapped' then return before_state is null and authority_grant_facts_are_safe(after_state,array['access_administrator'],'active',true,null);
            when 'AdminRoleGrantIssued' then return before_state is null and authority_grant_facts_are_safe(after_state,array['access_administrator','operator','project_manager','finance_authority','audit_authority'],'active',true,envelope_project_id);
            when 'ProjectRoleGrantIssued' then return before_state is null and authority_grant_facts_are_safe(after_state,array['submitter','reviewer'],'active',true,envelope_project_id);
            when 'AdminRoleGrantRevoked','ProjectRoleGrantRevoked' then
              return authority_grant_facts_are_safe(before_state,
                case when event_name='AdminRoleGrantRevoked' then array['access_administrator','operator','project_manager','finance_authority','audit_authority'] else array['submitter','reviewer'] end,
                'active',true,envelope_project_id)
                and authority_grant_facts_are_safe(after_state,
                case when event_name='AdminRoleGrantRevoked' then array['access_administrator','operator','project_manager','finance_authority','audit_authority'] else array['submitter','reviewer'] end,
                'revoked',false,envelope_project_id)
                and before_state->>'role'=after_state->>'role'
                and before_state->>'scope_type'=after_state->>'scope_type'
                and coalesce(before_state->>'scope_id','')=coalesce(after_state->>'scope_id','');
            when 'ProjectRoleQualificationSnapshotCaptured' then return before_state is null and after_state::jsonb='{"status":"captured"}'::jsonb;
            when 'AdminRoleGrantIssueDenied','LastAccessAdministratorOperationDenied' then return before_state is null and after_state is null;
            when 'SensitiveAuthorizationAllowed' then
              return before_state is null and (
                after_state::jsonb = '{"allowed": true}'::jsonb or (
                  after_state::jsonb->'allowed' = 'true'::jsonb
                  and after_state::jsonb ? 'resource_context_digest'
                  and (select count(*) from json_each(after_state)) = 2
                )
              );
            when 'SensitiveAuthorizationDenied' then
              return before_state is null and (
                after_state::jsonb = '{"allowed": false}'::jsonb or (
                  after_state::jsonb->'allowed' = 'false'::jsonb
                  and after_state::jsonb ? 'resource_context_digest'
                  and (select count(*) from json_each(after_state)) = 2
                )
              );
            when 'AuthorityInvalidationRequested' then return
              (before_state::jsonb = '{"effective": true}'::jsonb
                and after_state::jsonb = '{"effective": false}'::jsonb)
              or (before_state::jsonb = '{"effective": false}'::jsonb
                and after_state::jsonb = '{"effective": true}'::jsonb)
              or (
                jsonb_typeof(before_state::jsonb)='object'
                and jsonb_typeof(after_state::jsonb)='object'
                and (select count(*) from jsonb_object_keys(before_state::jsonb))=5
                and (select count(*) from jsonb_object_keys(after_state::jsonb))=5
                and before_state::jsonb ?& array['effective','role','scope_type','scope_id','future_obligation']
                and after_state::jsonb ?& array['effective','role','scope_type','scope_id','future_obligation']
                and before_state::jsonb->'effective'='true'::jsonb
                and after_state::jsonb->'effective'='false'::jsonb
                and jsonb_typeof(before_state::jsonb->'role')='string'
                and jsonb_typeof(before_state::jsonb->'scope_type')='string'
                and jsonb_typeof(before_state::jsonb->'scope_id')='string'
                and jsonb_typeof(before_state::jsonb->'future_obligation')='string'
                and (before_state::jsonb - 'effective')=(after_state::jsonb - 'effective')
                and before_state::jsonb->>'scope_type'='project'
                and before_state::jsonb->>'scope_id'=envelope_project_id
                and ((before_state::jsonb->>'role'='submitter' and before_state::jsonb->>'future_obligation'='auth13_assignment')
                  or (before_state::jsonb->>'role'='reviewer' and before_state::jsonb->>'future_obligation'='rev_reviewer_obligation'))
              );
            else return false;
          end case;
        end $$;
CREATE FUNCTION public.authority_facts_are_safe(facts json) RETURNS boolean
    LANGUAGE sql IMMUTABLE STRICT
    AS $_$
          select json_typeof(facts) = 'object'
            and (select count(*) = count(distinct key) and count(*) <= 8 from json_each(facts))
            and not exists (
              select 1 from json_each(facts) item
              where item.key not in (
                'status', 'subject_kind', 'provisioning_method', 'role',
                'scope_type', 'scope_id', 'effective', 'allowed',
                'resource_context_digest'
              )
              or case item.key
                when 'status' then item.value #>> '{}' not in (
                  'active', 'suspended', 'deactivated', 'revoked', 'captured'
                )
                when 'subject_kind' then item.value #>> '{}' not in ('human', 'service')
                when 'provisioning_method' then item.value #>> '{}' not in (
                  'automatic_first_access', 'manual_service_provisioning'
                )
                when 'role' then item.value #>> '{}' not in (
                  'access_administrator', 'operator', 'project_manager',
                  'finance_authority', 'audit_authority', 'submitter', 'reviewer', 'both'
                )
                when 'scope_type' then item.value #>> '{}' not in ('system', 'project')
                when 'scope_id' then (item.value #>> '{}') !~
                  '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                when 'effective' then json_typeof(item.value) <> 'boolean'
                when 'allowed' then json_typeof(item.value) <> 'boolean'
                when 'resource_context_digest' then (item.value #>> '{}') !~
                  '^sha256:[0-9a-f]{64}$'
                else true
              end
            )
        $_$;
CREATE FUNCTION public.authority_grant_facts_are_safe(facts json, roles text[], expected_status text, expected_effective boolean, envelope_project_id text) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    AS $$
          select authority_facts_are_safe(facts)
            and facts->>'role' = any(roles)
            and facts->>'status' = expected_status
            and (facts->>'effective')::boolean = expected_effective
            and (
              (
                facts->>'scope_type' = 'system'
                and envelope_project_id is null
                and not facts::jsonb ? 'scope_id'
                and facts->>'role' not in ('submitter', 'reviewer', 'both')
                and (select count(*) from json_each(facts)) = 4
              ) or (
                facts->>'scope_type' = 'project'
                and envelope_project_id is not null
                and facts->>'scope_id' = envelope_project_id
                and facts->>'role' not in ('access_administrator', 'operator')
                and (select count(*) from json_each(facts)) = 5
              )
            )
        $$;
CREATE FUNCTION public.canonical_guide_document_handle(run_id uuid, source_id uuid, ingest_id uuid) RETURNS uuid
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $$
        select encode(substring(sha256(convert_to('workstream.guide-document-handle.v1:' ||
          run_id::text || ':' || source_id::text || ':' || ingest_id::text, 'UTF8')) from 1 for 16), 'hex')::uuid
      $$;
CREATE FUNCTION public.check_outbox_delivery_projection() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare e outbox_events%rowtype; a outbox_delivery_attempts%rowtype;
                receipt jsonb; attempt_total bigint;
        begin
          select * into e from outbox_events where event_id = new.event_id;
          select count(*) into attempt_total from outbox_delivery_attempts where event_id = e.event_id;
          if attempt_total <> e.claim_generation or exists (
            select 1 from outbox_delivery_attempts x where x.event_id = e.event_id and
            (x.claim_generation > e.claim_generation or x.project_id <> e.project_id or
             x.payload_digest <> e.payload_digest or x.claimed_at < e.occurred_at or
             (x.claim_generation < e.claim_generation and x.stage <> 'completed'))
          ) then raise exception 'outbox delivery custody does not match event' using errcode='23514'; end if;
          if e.claim_generation = 0 then return null; end if;
          select * into a from outbox_delivery_attempts where event_id=e.event_id
            and claim_generation=e.claim_generation;
          if not found then
            raise exception 'outbox delivery custody missing' using errcode='23514';
          end if;
          if e.delivery_state = 'claimed' then
            if a.stage not in ('claimed','invoked') or
               (e.claim_owner,e.claimed_at,e.claim_expires_at,e.last_attempt_at) is distinct from
               (a.claim_owner,a.claimed_at,a.claim_expires_at,a.claimed_at) then
              raise exception 'outbox claim custody mismatch' using errcode='23514'; end if;
          else
            receipt := a.outcome_json::jsonb;
            if a.stage <> 'completed' or e.last_attempt_at is distinct from a.claimed_at or
               (e.delivery_state,e.last_error_code,e.next_attempt_at,e.finalized_at) is distinct from
               (receipt->>'delivery_state',receipt->>'error_code',
                (receipt->>'next_attempt_at')::timestamptz,(receipt->>'finalized_at')::timestamptz) then
              raise exception 'outbox outcome custody mismatch' using errcode='23514'; end if;
          end if;
          return null;
        end $$;
CREATE FUNCTION public.enforce_compensation_binding_lifecycle() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if (new.id,new.project_id,new.instrument_type,new.adapter_actor_id,new.route_key,
              new.created_by,new.created_at,new.retired_by,new.retired_at)
             is distinct from
             (old.id,old.project_id,old.instrument_type,old.adapter_actor_id,old.route_key,
              old.created_by,old.created_at,old.retired_by,old.retired_at) then
            raise exception 'compensation binding identity is immutable' using errcode='55000';
          end if;
          if old.status='active' and new.status='suspended'
             and new.binding_lifecycle_version=old.binding_lifecycle_version+1
             and new.suspended_by is not null
             and new.resumed_by is null and new.resumed_at is null then
            new.suspended_at := clock_timestamp();
            return new;
          end if;
          if old.status='suspended' and new.status='active'
             and new.binding_lifecycle_version=old.binding_lifecycle_version+1
             and new.suspended_by is null and new.suspended_at is null
             and new.resumed_by is not null then
            new.resumed_at := clock_timestamp();
            return new;
          end if;
          raise exception 'invalid compensation binding lifecycle transition' using errcode='23514';
        end;
        $$;
CREATE FUNCTION public.guard_actor_identity_link_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='DELETE' then raise exception 'actor identity links are immutable history' using errcode='55000'; end if;
          if (new.id,new.actor_profile_id,new.issuer,new.subject,new.subject_kind,new.linked_by,new.linked_at)
             is distinct from (old.id,old.actor_profile_id,old.issuer,old.subject,old.subject_kind,old.linked_by,old.linked_at) then
            raise exception 'actor identity link anchor is immutable' using errcode='55000';
          end if;
          if new.status=old.status and
             (new.revoked_by,new.revoked_at,new.revoked_reason,new.reactivated_by,new.reactivated_at,new.reactivation_reason)
             is distinct from
             (old.revoked_by,old.revoked_at,old.revoked_reason,old.reactivated_by,old.reactivated_at,old.reactivation_reason) then
            raise exception 'identity link attribution requires a transition' using errcode='23514';
          end if;
          if old.status='active' and new.status='revoked' and
             (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is distinct from
             (old.reactivated_by,old.reactivated_at,old.reactivation_reason) then
            raise exception 'invalid identity link revocation attribution' using errcode='23514';
          end if;
          if old.status='revoked' and new.status='active' and
             ((new.revoked_by,new.revoked_at,new.revoked_reason) is distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from
                 (old.reactivated_by,old.reactivated_at,old.reactivation_reason)) then
            raise exception 'invalid identity link reactivation attribution' using errcode='23514';
          end if;
          if new.status <> old.status and not (
             (old.status='active' and new.status='revoked') or
             (old.status='revoked' and new.status='active')) then
            raise exception 'invalid identity link lifecycle transition' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_actor_profile_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='DELETE' then raise exception 'actor profiles are immutable history' using errcode='55000'; end if;
          if (new.id,new.actor_kind,new.provisioning_method,new.service_identity,new.created_by,new.created_at)
             is distinct from (old.id,old.actor_kind,old.provisioning_method,old.service_identity,old.created_by,old.created_at) then
            raise exception 'actor profile identity is immutable' using errcode='55000';
          end if;
          if old.status='deactivated' and new.status <> 'deactivated' then
            raise exception 'deactivated actor is terminal' using errcode='23514';
          end if;
          if new.status = old.status and
             (new.suspended_by,new.suspended_at,new.suspension_reason,new.reactivated_by,new.reactivated_at,new.reactivation_reason,
              new.deactivated_by,new.deactivated_at,new.deactivation_reason) is distinct from
             (old.suspended_by,old.suspended_at,old.suspension_reason,old.reactivated_by,old.reactivated_at,old.reactivation_reason,
              old.deactivated_by,old.deactivated_at,old.deactivation_reason) then
            raise exception 'actor lifecycle attribution requires a transition' using errcode='23514';
          end if;
          if old.status='active' and new.status='suspended' and
             (new.reactivated_by,new.reactivated_at,new.reactivation_reason,new.deactivated_by,new.deactivated_at,new.deactivation_reason)
             is distinct from
             (old.reactivated_by,old.reactivated_at,old.reactivation_reason,old.deactivated_by,old.deactivated_at,old.deactivation_reason) then
            raise exception 'invalid actor suspension attribution' using errcode='23514';
          end if;
          if old.status='suspended' and new.status='active' and
             ((new.suspended_by,new.suspended_at,new.suspension_reason) is distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from (null,null,null)
              or (new.reactivated_by,new.reactivated_at,new.reactivation_reason) is not distinct from
                 (old.reactivated_by,old.reactivated_at,old.reactivation_reason)
              or (new.deactivated_by,new.deactivated_at,new.deactivation_reason) is distinct from
                 (old.deactivated_by,old.deactivated_at,old.deactivation_reason)) then
            raise exception 'invalid actor reactivation attribution' using errcode='23514';
          end if;
          if new.status='deactivated' and old.status in ('active','suspended') and
             (new.suspended_by,new.suspended_at,new.suspension_reason,new.reactivated_by,new.reactivated_at,new.reactivation_reason)
             is distinct from
             (old.suspended_by,old.suspended_at,old.suspension_reason,old.reactivated_by,old.reactivated_at,old.reactivation_reason) then
            raise exception 'invalid actor deactivation attribution' using errcode='23514';
          end if;
          if new.status <> old.status and not (
             (old.status='active' and new.status in ('suspended','deactivated')) or
             (old.status='suspended' and new.status in ('active','deactivated'))) then
            raise exception 'invalid actor lifecycle transition' using errcode='23514';
          end if;
          new.updated_at = statement_timestamp(); return new;
        end $$;
CREATE FUNCTION public.guard_admin_role_grant() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare target_kind text; authorizer admin_role_grants%rowtype;
                bootstrap_done boolean;
        begin
          if tg_op='DELETE' then raise exception 'admin role grants are immutable' using errcode='55000'; end if;
          if tg_op='INSERT' then
            select actor_kind into target_kind from actor_profiles where id=new.target_actor_profile_id;
            if target_kind is distinct from 'human' then raise exception 'admin role target must be human' using errcode='23514'; end if;
            new.granted_at := clock_timestamp();
            if new.granted_by_system_principal is not null then
              if new.role <> 'access_administrator' or new.scope_type <> 'system' then raise exception 'invalid bootstrap grant' using errcode='23514'; end if;
              select bootstrap_completed into bootstrap_done from authority_control where id=1 for update;
              if bootstrap_done is distinct from false
                 or exists(select 1 from admin_role_grants where granted_by_system_principal='workstream:system:bootstrap') then
                raise exception 'bootstrap already completed' using errcode='23514';
              end if;
            else
              select * into authorizer from admin_role_grants where id=new.granted_by_admin_role_grant_id;
              if not found or authorizer.target_actor_profile_id <> new.granted_by_actor_profile_id
                 or authorizer.role <> 'access_administrator' or authorizer.scope_type <> 'system'
                 or authorizer.status <> 'active' then raise exception 'invalid admin grant attribution' using errcode='23514'; end if;
            end if;
            return new;
          end if;
          if old.status <> 'active' or old.version <> 1 or new.status <> 'revoked' or new.version <> 2
             or (new.id,new.target_actor_profile_id,new.role,new.scope_type,new.scope_project_id,
                 new.granted_by_actor_profile_id,new.granted_by_system_principal,
                 new.granted_by_admin_role_grant_id,new.grant_reason,new.granted_at)
                is distinct from
                (old.id,old.target_actor_profile_id,old.role,old.scope_type,old.scope_project_id,
                 old.granted_by_actor_profile_id,old.granted_by_system_principal,
                 old.granted_by_admin_role_grant_id,old.grant_reason,old.granted_at) then
            raise exception 'invalid admin role grant transition' using errcode='23514';
          end if;
          select * into authorizer from admin_role_grants where id=new.revoked_by_admin_role_grant_id;
          if not found or authorizer.target_actor_profile_id <> new.revoked_by_actor_profile_id
             or authorizer.role <> 'access_administrator' or authorizer.scope_type <> 'system'
             or authorizer.status <> 'active' then raise exception 'invalid admin revoke attribution' using errcode='23514'; end if;
          new.revoked_at := clock_timestamp(); return new;
        end $$;
CREATE FUNCTION public.guard_artifact_receipt_producer_reference() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare request_type text;
        begin
          select producer_request_type into request_type
          from artifact_put_attempts where id = new.put_attempt_id;
          if request_type is null
             or (request_type = 'guide' and not (
                 new.guide_source_item_id is not null and new.checker_run_id is null
                 and new.logical_role is null))
             or (request_type = 'checker_output' and not (
                 new.guide_source_item_id is null and new.checker_run_id is not null
                 and octet_length(new.logical_role) between 1 and 100))
             or (request_type = 'submission_bundle' and not (
                 new.guide_source_item_id is null and new.checker_run_id is null
                 and new.logical_role is null))
          then
            raise exception 'artifact receipt producer reference mismatch'
              using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_assignment_release_authority() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
        declare d audit_events%rowtype; refs jsonb; facts jsonb; target jsonb; digest text;
        begin
          if new.event_type <> 'TaskAssignmentAuthorityRevoked' then return new; end if;
          refs := new.event_payload->'references';
          digest := new.event_payload->>'authorization_resource_digest';
          facts := new.event_payload::jsonb->'assignment_invalidation_facts';
          target := facts->'target';
          select * into d from audit_events where id::text=refs->>'authorization_decision_id';
          if not found or not coalesce(
            new.event_domain='legacy_lifecycle' and new.auth_source='local_lifecycle'
            and new.entity_type='task' and new.is_dev_auth=false
            and new.from_status in ('claimed','in_progress') and new.to_status='ready'
            and new.reason='lifecycle_state_changed'
            and digest ~ '^sha256:[0-9a-f]{64}$'
            and new.event_payload::jsonb=jsonb_build_object('references',refs,'authorization_resource_digest',digest,
              'assignment_invalidation_facts',facts)
            and target=jsonb_build_object('project_id',refs->>'project_id','task_id',new.entity_id,
              'assignment_id',refs->>'assignment_id','contributor_id',target->>'contributor_id',
              'authority_invalidation_event_id',refs->>'authority_invalidation_event_id')
            and jsonb_typeof(facts)='object'
            and octet_length(convert_to(project_guide_projection_canonical_json(facts),'UTF8'))<=4096
            and facts=jsonb_build_object('target',target,'cause_event_id',facts->'cause_event_id',
              'delivery_event_id',facts->'delivery_event_id','delivery_generation',facts->'delivery_generation',
              'cause_digest',facts->'cause_digest','invocation_digest',facts->'invocation_digest',
              'task_status',facts->'task_status','locked_context_hash',facts->'locked_context_hash')
            and jsonb_typeof(facts->'delivery_generation')='number'
            and (facts->>'delivery_generation') ~ '^[1-9][0-9]*$'
            and (facts->>'delivery_generation')::numeric <= 2147483647
            and not exists(select 1 from jsonb_each(target) f where jsonb_typeof(f.value)<>'string'
              or (f.value#>>'{}') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
            and not exists(select 1 from jsonb_each(facts) f where f.key in ('cause_event_id','delivery_event_id')
              and (jsonb_typeof(f.value)<>'string' or (f.value#>>'{}') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'))
            and not exists(select 1 from jsonb_each(facts) f where f.key in ('cause_digest','invocation_digest','locked_context_hash')
              and (jsonb_typeof(f.value)<>'string' or (f.value#>>'{}') !~ '^sha256:[0-9a-f]{64}$'))
            and facts->>'task_status'=new.from_status
            and digest='sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(
              jsonb_build_object('resource_context',jsonb_build_object(
                'resource_type','task_authority','resource_id',new.entity_id,
                'scope_project_id',refs->>'project_id','facts',facts))), 'UTF8')), 'hex')
            and refs=jsonb_build_object(
              'project_id',refs->>'project_id','task_id',new.entity_id,
              'assignment_id',refs->>'assignment_id',
              'authority_invalidation_event_id',refs->>'authority_invalidation_event_id',
              'authorization_decision_id',d.id)
            and d.event_domain='authority' and d.event_type='SensitiveAuthorizationAllowed'
            and d.action_id='task.assignment.authority_reconcile'
            and d.permission_id='task.assignment.authority_reconcile'
            and d.actor_id=new.actor_id and d.actor_ref_kind='actor_profile'
            and d.resource_type='task' and d.resource_id=new.entity_id::text
            and d.project_id::text=refs->>'project_id'
            and d.request_id::text=facts->>'delivery_event_id'
            and d.correlation_id::text=refs->>'authority_invalidation_event_id'
            and d.after_facts::jsonb=jsonb_build_object('allowed',true,'resource_context_digest',digest)
            and exists(select 1 from actor_profiles p where p.id::text=d.actor_id
              and p.actor_kind='service' and p.service_identity='workstream.task.assignment_reconciler')
            and exists(select 1 from task_assignments a where a.id::text=refs->>'assignment_id'
              and a.task_id=new.entity_id and a.project_id=d.project_id
              and a.contributor_id::text=target->>'contributor_id')
            and exists(select 1 from audit_events cause where cause.id::text=refs->>'authority_invalidation_event_id'
              and cause.event_domain='authority' and cause.event_type='AuthorityInvalidationRequested'
              and cause.invalidation_cause_event_id::text=facts->>'cause_event_id'),
            false
          ) then raise exception 'assignment release authority mismatch'; end if;
          return new;
        end $_$;
CREATE FUNCTION public.guard_authority_control() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op in ('INSERT','DELETE') then raise exception 'authority control is immutable' using errcode='55000'; end if;
          if old.id <> 1 or old.bootstrap_completed or old.version <> 0
             or new.id <> 1 or not new.bootstrap_completed or new.version <> 1
             or new.bootstrap_grant_id is null or new.created_at is distinct from old.created_at then
            raise exception 'invalid authority control transition' using errcode='23514';
          end if;
          new.updated_at := clock_timestamp(); return new;
        end $$;
CREATE FUNCTION public.guard_authority_idempotency_record() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
declare success_count integer; invalidation_count integer; success_id uuid;
        qualification_row audit_events%rowtype; success_row audit_events%rowtype;
        grant_row project_role_grants%rowtype;
        snapshot_row project_role_qualification_snapshots%rowtype;
begin
  if tg_op = 'INSERT' then
    if new.status <> 'pending' then raise exception 'idempotency must begin pending' using errcode='23514'; end if;
    new.created_at := statement_timestamp(); new.committed_at := null; return new;
  elsif tg_op = 'DELETE' then
    raise exception 'authority idempotency records are immutable' using errcode='55000';
  end if;
  if old.status <> 'pending' or new.status <> 'committed'
     or (new.id,new.idempotency_key,new.actor_ref_kind,new.actor_ref,new.operation,
         new.request_digest,new.created_at) is distinct from
        (old.id,old.idempotency_key,old.actor_ref_kind,old.actor_ref,old.operation,
         old.request_digest,old.created_at) then
    raise exception 'invalid authority idempotency transition' using errcode='23514';
  end if;
  select count(*), min(id::text)::uuid into success_count, success_id from audit_events
  where event_domain='authority' and idempotency_reference=new.id
    and event_type <> 'AuthorityInvalidationRequested';
  select count(*) into invalidation_count from audit_events
  where event_domain='authority' and idempotency_reference=new.id
    and event_type='AuthorityInvalidationRequested';
  if new.operation='project_role_grant.issue' then
    if success_count <> 2 or invalidation_count <> 0
       or (select count(*) from audit_events where idempotency_reference=new.id
             and event_type='ProjectRoleQualificationSnapshotCaptured') <> 1
       or (select count(*) from audit_events where idempotency_reference=new.id
             and event_type='ProjectRoleGrantIssued') <> 1 then
      raise exception 'project role issue evidence pair required' using errcode='23514';
    end if;
    select * into qualification_row from audit_events where idempotency_reference=new.id
      and event_type='ProjectRoleQualificationSnapshotCaptured';
    select * into success_row from audit_events where idempotency_reference=new.id
      and event_type='ProjectRoleGrantIssued';
    select * into grant_row from project_role_grants where id=success_row.resource_id::uuid;
    select * into snapshot_row from project_role_qualification_snapshots
      where id=qualification_row.resource_id::uuid;
    if not found or grant_row.id is null or snapshot_row.id is null
       or grant_row.qualification_snapshot_id <> snapshot_row.id
       or grant_row.project_id <> snapshot_row.project_id
       or grant_row.actor_profile_id <> snapshot_row.actor_profile_id
       or grant_row.role <> snapshot_row.requested_role
       or qualification_row.project_id is distinct from grant_row.project_id
       or success_row.project_id is distinct from grant_row.project_id
       or qualification_row.target_actor_ref is distinct from grant_row.actor_profile_id::text
       or success_row.target_actor_ref is distinct from grant_row.actor_profile_id::text
       or qualification_row.request_id is distinct from success_row.request_id
       or qualification_row.correlation_id is distinct from success_row.correlation_id
       or qualification_row.actor_ref_kind is distinct from success_row.actor_ref_kind
       or qualification_row.actor_id is distinct from success_row.actor_id
       or qualification_row.permission_id is distinct from success_row.permission_id
       or qualification_row.matched_grant_id is distinct from success_row.matched_grant_id then
      raise exception 'project role issue evidence mismatch' using errcode='23514';
    end if;
  else
    if success_count <> 1 or invalidation_count <> 1 then
      raise exception 'authority evidence pair required' using errcode='23514';
    end if;
    select * into success_row from audit_events where id=success_id;
  end if;
  if success_row.resource_type <> new.response_resource_type
     or success_row.resource_id <> new.response_resource_id::text then
    raise exception 'authority response does not match evidence' using errcode='23514';
  end if;
  new.committed_at := statement_timestamp(); return new;
end $$;
CREATE FUNCTION public.guard_compensation_binding_lifecycle_event() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          binding project_compensation_adapter_bindings%rowtype;
          prior compensation_adapter_binding_lifecycle_events%rowtype;
          preceding compensation_adapter_binding_lifecycle_events%rowtype;
        begin
          select * into binding from project_compensation_adapter_bindings
            where id=new.adapter_binding_id;
          if not found or binding.project_id<>new.project_id
             or binding.status<>new.to_status
             or binding.binding_lifecycle_version<>new.to_lifecycle_version then
            raise exception 'invalid compensation binding lifecycle event' using errcode='23514';
          end if;
          if (new.event_type='created' and binding.created_by<>new.actor_profile_id)
             or (new.event_type='suspended' and binding.suspended_by<>new.actor_profile_id)
             or (new.event_type='resumed' and binding.resumed_by<>new.actor_profile_id) then
            raise exception 'compensation binding lifecycle attribution mismatch'
              using errcode='23514';
          end if;
          new.occurred_at := clock_timestamp();
          select * into preceding from compensation_adapter_binding_lifecycle_events
            where adapter_binding_id=new.adapter_binding_id
            order by to_lifecycle_version desc limit 1;
          if new.event_type='created' then
            if found then
              raise exception 'created event must be first' using errcode='23514';
            end if;
          elsif not found or preceding.to_lifecycle_version<>new.from_lifecycle_version
                or preceding.to_status<>new.from_status then
            raise exception 'lifecycle event is not contiguous' using errcode='23514';
          end if;
          if new.event_type='resumed' then
            select * into prior from compensation_adapter_binding_lifecycle_events
              where id=new.prior_suspension_event_id;
            if not found or prior.adapter_binding_id<>new.adapter_binding_id
               or prior.event_type<>'suspended'
               or prior.id<>preceding.id
               or prior.to_lifecycle_version<>new.from_lifecycle_version then
              raise exception 'invalid prior suspension event' using errcode='23514';
            end if;
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_compilation_document_evidence() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
                  and access.source_item_id::text=reference->>'source_item_id'
                  and access.document_version_id::text=reference->>'document_version_id'
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
                where refs.value->>'source_item_id'=item.id::text)) then
            raise exception 'ready compilation requires citations for all assigned documents' using errcode='23514';
          end if;
        end if;
        return new;
      end $$;
CREATE FUNCTION public.guard_compilation_projection_business_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          if tg_table_name='guide_sufficiency_reports' and exists(
            select 1 from project_guide_component_projection_operations
              where report_id=old.id
          ) and ((to_jsonb(new)-'warnings_acknowledged_by_role'-'warnings_acknowledged_by_actor'
                   -'warnings_acknowledged_at'-'acknowledgement_note'
                   -'warnings_acknowledged_by_actor_profile_id'
                   -'warnings_acknowledged_via_identity_link_id'
                   -'warnings_acknowledged_by_admin_role_grant_id'
                   -'warning_acknowledgement_scope_type'
                   -'warning_acknowledgement_scope_project_id'
                   -'warning_acknowledgement_action_id'
                   -'warning_acknowledgement_decision_event_id') is distinct from
                  (to_jsonb(old)-'warnings_acknowledged_by_role'-'warnings_acknowledged_by_actor'
                   -'warnings_acknowledged_at'-'acknowledgement_note'
                   -'warnings_acknowledged_by_actor_profile_id'
                   -'warnings_acknowledged_via_identity_link_id'
                   -'warnings_acknowledged_by_admin_role_grant_id'
                   -'warning_acknowledgement_scope_type'
                   -'warning_acknowledgement_scope_project_id'
                   -'warning_acknowledgement_action_id'
                   -'warning_acknowledgement_decision_event_id')) then
            raise exception 'projected sufficiency content is immutable' using errcode='55000';
          end if;
          if tg_table_name='submission_artifact_policies' and exists(
            select 1 from project_guide_component_projection_operations
              where policy_id=old.id
          ) and ((to_jsonb(new)-'lifecycle_status'-'approved_by_role'-'approved_by_actor'
                   -'approved_by_actor_profile_id'-'approved_via_identity_link_id'
                   -'approved_by_admin_role_grant_id'-'approval_scope_type'
                   -'approval_scope_project_id'-'approval_action_id'
                   -'approval_decision_event_id'-'approved_at'-'supersedes_policy_id'
                   -'superseded_at'-'updated_at') is distinct from
                  (to_jsonb(old)-'lifecycle_status'-'approved_by_role'-'approved_by_actor'
                   -'approved_by_actor_profile_id'-'approved_via_identity_link_id'
                   -'approved_by_admin_role_grant_id'-'approval_scope_type'
                   -'approval_scope_project_id'-'approval_action_id'
                   -'approval_decision_event_id'-'approved_at'-'supersedes_policy_id'
                   -'superseded_at'-'updated_at')) then
            raise exception 'projected policy content is immutable' using errcode='55000';
          end if;
          return new;
        end; $$;
CREATE FUNCTION public.guard_compilation_projection_source_usage_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          if exists(
            select 1 from project_guide_component_projection_operations
              where report_id=new.report_id
          ) then raise exception 'projected source usage is immutable'
            using errcode='55000';
          end if;
          return new;
        end; $$;
CREATE FUNCTION public.guard_contribution_policy_children() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare old_parent_status text;
        declare new_parent_status text;
        begin
          if tg_op in ('UPDATE','DELETE') then
            select status into old_parent_status from contribution_policy_versions
            where id=old.contribution_policy_version_id for update;
          end if;
          if tg_op in ('INSERT','UPDATE') then
            select status into new_parent_status from contribution_policy_versions
            where id=new.contribution_policy_version_id for update;
          end if;
          if old_parent_status in ('published','retired')
             or new_parent_status in ('published','retired') then
            raise exception 'published contribution policy rules and definitions are immutable'
              using errcode='55000';
          end if;
          return case when tg_op='DELETE' then old else new end;
        end;
        $$;
CREATE FUNCTION public.guard_contribution_policy_event_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          policy contribution_policies%rowtype;
          version contribution_policy_versions%rowtype;
          prior_version_number integer;
          custody contribution_policy_transition_custody%rowtype;
        begin
          select * into policy from contribution_policies where id=new.contribution_policy_id;
          select * into version from contribution_policy_versions
            where id=new.contribution_policy_version_id;
          if policy.id is null or version.id is null
             or policy.project_id is distinct from new.project_id
             or version.project_id is distinct from new.project_id
             or version.contribution_policy_id is distinct from new.contribution_policy_id
             or version.version_number is distinct from new.version_number
             or version.status is distinct from new.to_version_status
             or policy.status is distinct from new.to_policy_status then
            raise exception 'invalid contribution policy lifecycle event' using errcode='23514';
          end if;
          if new.prior_current_version_id is not null then
            select version_number into prior_version_number from contribution_policy_versions
              where id=new.prior_current_version_id;
          end if;
          if new.prior_current_version_number is distinct from prior_version_number then
            raise exception 'contribution policy event prior version mismatch'
              using errcode='23514';
          end if;
          if new.event_type in ('draft_created','draft_updated') then
            if new.prior_current_version_id is distinct from policy.current_published_version_id
               or (new.event_type='draft_created' and version.version_number=1
                   and (new.from_policy_status is not null or policy.status <> 'draft'))
               or (new.event_type='draft_created' and version.version_number>1
                   and (new.from_policy_status <> 'active' or policy.status <> 'active'))
               or (new.event_type='draft_updated'
                   and new.from_policy_status is distinct from policy.status) then
              raise exception 'contribution policy event prior state mismatch'
                using errcode='23514';
            end if;
            new.occurred_at := clock_timestamp();
          else
            select * into custody from contribution_policy_transition_custody
              where operation_id=new.publication_custody_operation_id;
            if custody.operation_id is null
               or custody.operation_id is distinct from new.operation_id
               or custody.event_type is distinct from new.event_type then
              raise exception 'contribution policy event custody mismatch'
                using errcode='23514';
            end if;
            new.occurred_at := custody.occurred_at;
          end if;
          if (new.event_type='draft_created'
                 and version.created_by is distinct from new.actor_profile_id)
             or (new.event_type='draft_updated'
                 and version.last_updated_by is distinct from new.actor_profile_id)
             or (new.event_type='published'
                 and version.published_by is distinct from new.actor_profile_id)
             or (new.event_type='retired'
                 and version.retired_by is distinct from new.actor_profile_id) then
            raise exception 'contribution policy event attribution mismatch'
              using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_contribution_policy_row_transition() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare custody contribution_policy_transition_custody%rowtype;
        begin
          if old.id is distinct from new.id
             or old.project_id is distinct from new.project_id
             or old.name is distinct from new.name
             or old.created_by is distinct from new.created_by
             or old.created_at is distinct from new.created_at then
            raise exception 'immutable contribution policy identity changed'
              using errcode='55000';
          end if;
          if old.status='retired'
             or (old.status in ('active','retired') and
                 new.last_transition_operation_id is not distinct from
                   old.last_transition_operation_id) then
            raise exception 'final contribution policy row is immutable'
              using errcode='55000';
          end if;
          if old.status is distinct from new.status
             or old.current_published_version_id is distinct from
                  new.current_published_version_id
             or old.last_transition_operation_id is distinct from
                  new.last_transition_operation_id then
            select * into custody from contribution_policy_transition_custody
              where operation_id=new.last_transition_operation_id;
            if custody.operation_id is null
               or custody.contribution_policy_id is distinct from new.id
               or custody.project_id is distinct from new.project_id
               or (new.status='active' and (
                    custody.event_type <> 'published'
                    or new.current_published_version_id is distinct from
                         custody.contribution_policy_version_id
                    or new.retired_by is not null or new.retired_at is not null))
               or (new.status='retired' and (
                    custody.event_type <> 'retired'
                    or new.retired_by is distinct from custody.actor_profile_id
                    or new.retired_at is distinct from custody.occurred_at)) then
              raise exception 'invalid contribution policy row transition'
                using errcode='23514';
            end if;
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_contribution_policy_transition_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          policy contribution_policies%rowtype;
          target contribution_policy_versions%rowtype;
          prior contribution_policy_versions%rowtype;
          event_count integer;
          accepted_count integer;
          review_count integer;
          invalid_rule_count integer;
        begin
          select * into policy from contribution_policies
            where id=new.contribution_policy_id;
          select * into target from contribution_policy_versions
            where id=new.contribution_policy_version_id;
          select count(*) into event_count
            from contribution_policy_lifecycle_events e
            where e.publication_custody_operation_id=new.operation_id
              and e.operation_id=new.operation_id
              and e.request_digest=new.request_digest
              and e.event_type=new.event_type
              and e.actor_profile_id=new.actor_profile_id
              and e.project_id=new.project_id
              and e.contribution_policy_id=new.contribution_policy_id
              and e.contribution_policy_version_id=new.contribution_policy_version_id
              and e.prior_current_version_id is not distinct from new.prior_current_version_id
              and e.occurred_at=new.occurred_at;
          if event_count <> 1
             or policy.last_transition_operation_id is distinct from new.operation_id
             or target.last_transition_operation_id is distinct from new.operation_id then
            raise exception 'invalid contribution policy transition custody'
              using errcode='23514';
          end if;
          if new.event_type='published' then
            if policy.status is distinct from 'active'
               or policy.current_published_version_id is distinct from target.id
               or target.status is distinct from 'published'
               or target.published_by is distinct from new.actor_profile_id
               or target.published_at is distinct from new.occurred_at then
              raise exception 'invalid contribution policy publication custody'
                using errcode='23514';
            end if;
            select count(*) filter (where contribution_type='accepted_submission'),
                   count(*) filter (where contribution_type='completed_review')
              into accepted_count, review_count from contribution_rules
              where contribution_policy_version_id=target.id;
            if accepted_count <> 1 or review_count <> 1 then
              raise exception 'incomplete contribution policy graph'
                using errcode='23514';
            end if;
            select count(*) into invalid_rule_count from contribution_rules r
              where r.contribution_policy_version_id=target.id and (
                (r.compensation_mode='unpaid' and exists (
                  select 1 from contribution_award_definitions d
                  where d.contribution_rule_id=r.id))
                or (r.compensation_mode='compensated' and (
                  select count(*) from contribution_award_definitions d
                  where d.contribution_rule_id=r.id) not between 1 and 2));
            if invalid_rule_count <> 0 then
              raise exception 'incomplete contribution policy definitions'
                using errcode='23514';
            end if;
            if new.prior_current_version_id is not null then
              select * into prior from contribution_policy_versions
                where id=new.prior_current_version_id;
              if prior.status is distinct from 'retired'
                 or prior.last_transition_operation_id is distinct from new.operation_id
                 or prior.retired_by is distinct from new.actor_profile_id
                 or prior.retired_at is distinct from new.occurred_at then
                raise exception 'invalid replacement publication custody'
                  using errcode='23514';
              end if;
            end if;
          else
            if policy.status is distinct from 'retired'
               or policy.current_published_version_id is distinct from target.id
               or policy.retired_by is distinct from new.actor_profile_id
               or policy.retired_at is distinct from new.occurred_at
               or target.status is distinct from 'retired'
               or target.retired_by is distinct from new.actor_profile_id
               or target.retired_at is distinct from new.occurred_at then
              raise exception 'invalid contribution policy retirement custody'
                using errcode='23514';
            end if;
          end if;
          return null;
        end;
        $$;
CREATE FUNCTION public.guard_contribution_policy_version_content() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='DELETE' and old.status in ('published','retired') then
            raise exception 'published contribution policy versions are immutable'
              using errcode='55000';
          end if;
          if tg_op='UPDATE' and old.status='retired' then
            raise exception 'retired contribution policy versions are immutable'
              using errcode='55000';
          end if;
          if tg_op='UPDATE' and old.status='published' and not (
            new.status='retired'
            and new.id=old.id
            and new.contribution_policy_id=old.contribution_policy_id
            and new.project_id=old.project_id
            and new.version_number=old.version_number
            and new.created_by=old.created_by
            and new.created_at=old.created_at
            and new.published_by=old.published_by
            and new.published_at=old.published_at
            and new.retired_by is not null
            and new.retired_at is not null
          ) then
            raise exception 'published contribution policy version content is immutable'
              using errcode='55000';
          end if;
          return case when tg_op='DELETE' then old else new end;
        end;
        $$;
CREATE FUNCTION public.guard_contribution_policy_version_row_transition() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare custody contribution_policy_transition_custody%rowtype;
        begin
          if old.id is distinct from new.id
             or old.contribution_policy_id is distinct from new.contribution_policy_id
             or old.project_id is distinct from new.project_id
             or old.version_number is distinct from new.version_number
             or old.created_by is distinct from new.created_by
             or old.created_at is distinct from new.created_at then
            raise exception 'immutable contribution policy version identity changed'
              using errcode='55000';
          end if;
          if old.status='retired'
             or (old.status='published' and new.status<>'retired') then
            raise exception 'final contribution policy version row is immutable'
              using errcode='55000';
          end if;
          if old.status is distinct from new.status
             or old.last_transition_operation_id is distinct from
                  new.last_transition_operation_id then
            select * into custody from contribution_policy_transition_custody
              where operation_id=new.last_transition_operation_id;
            if custody.operation_id is null
               or (custody.contribution_policy_version_id is distinct from new.id
                   and not (custody.event_type='published'
                            and custody.prior_current_version_id is not distinct from new.id
                            and new.status='retired'))
               or custody.contribution_policy_id is distinct from new.contribution_policy_id
               or custody.project_id is distinct from new.project_id
               or (new.status='published' and (
                    custody.event_type <> 'published'
                    or new.published_by is distinct from custody.actor_profile_id
                    or new.published_at is distinct from custody.occurred_at))
               or (new.status='retired' and (
                    not ((custody.event_type='retired'
                          and custody.contribution_policy_version_id=new.id)
                         or (custody.event_type='published'
                             and custody.prior_current_version_id=new.id))
                    or
                    new.retired_by is distinct from custody.actor_profile_id
                    or new.retired_at is distinct from custody.occurred_at)) then
              raise exception 'invalid contribution policy version row transition'
                using errcode='23514';
            end if;
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_finalized_project_setup() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
           or old.documents_ready_at is null
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
CREATE FUNCTION public.guard_guide_document_access() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      declare attempt project_guide_compilation_attempts%rowtype;
      begin
        if tg_op <> 'INSERT' then
          raise exception 'guide document access evidence is immutable' using errcode='55000';
        end if;
        select * into attempt from project_guide_compilation_attempts where id=new.attempt_id for update;
        if not found or attempt.status <> 'compilation_provider_uncertain'
           or new.manifest_sha256 is distinct from attempt.guide_material_hash
           or not exists(select 1 from project_guide_runtime_allocations resource
             join project_guide_runtime_allocations file on file.id=resource.source_file_allocation_id
             join project_guide_runtime_allocations container on container.id=resource.container_allocation_id
             where resource.id=new.attachment_allocation_id and resource.attempt_id=new.attempt_id
               and resource.manifest_sha256=new.manifest_sha256 and resource.kind='attachment'
               and resource.document_handle=new.document_handle and resource.state='allocated'
               and file.attempt_id=new.attempt_id and file.manifest_sha256=new.manifest_sha256
               and file.kind='file' and file.state='allocated' and file.document_handle=new.document_handle
               and file.source_item_id=new.source_item_id and file.document_version_id=new.document_version_id
               and file.sha256=new.sha256
               and container.attempt_id=new.attempt_id and container.kind='container' and container.state='allocated'
               and container.provider_id=resource.parent_provider_id) then
          raise exception 'guide document access lineage is invalid' using errcode='23514';
        end if;
        return new;
      end $$;
CREATE FUNCTION public.guard_guide_lineage_and_lifecycle() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
CREATE FUNCTION public.guard_guide_mutation_idempotency() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          if tg_op='INSERT' then
            if new.status<>'pending' then raise exception 'guide mutation must begin pending' using errcode='23514'; end if;
            return new;
          elsif tg_op='DELETE' then
            raise exception 'guide mutation custody is immutable' using errcode='55000';
          end if;
          if old.action_id='project.guide.activate' and old.status='committed' then
            raise exception 'guide activation operation is immutable' using errcode='55000';
          end if;
          if (new.activation_facts_json::jsonb,new.activation_authority_json::jsonb)
             is distinct from (old.activation_facts_json::jsonb,old.activation_authority_json::jsonb) then
            raise exception 'activation commitments are immutable' using errcode='55000';
          end if;
          if new is not distinct from old then return new; end if;
          if old.status<>'pending' or new.status<>'committed'
             or (new.id,new.actor_profile_id,new.identity_link_id,new.action_id,new.idempotency_key,
                 new.request_digest,new.resource_context_digest,new.operation_id,new.project_id,new.resource_id,
                 new.operation_generation,new.created_at)
                is distinct from
                (old.id,old.actor_profile_id,old.identity_link_id,old.action_id,old.idempotency_key,
                 old.request_digest,old.resource_context_digest,old.operation_id,old.project_id,old.resource_id,
                 old.operation_generation,old.created_at) then
            raise exception 'invalid guide mutation custody transition' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_guide_runtime_allocation() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
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
          if new.kind='file' then
            if new.document_handle is distinct from canonical_guide_document_handle(
                attempt.setup_run_id::uuid, new.source_item_id::uuid, new.document_version_id::uuid) then
              raise exception 'guide runtime canonical handle mismatch' using errcode='23514';
            end if;
            if not exists(select 1 from guide_source_snapshot_items item
              join guide_source_artifact_ingests ingest on ingest.source_item_id=item.id
              join artifact_put_attempts put on put.id=new.put_attempt_id
              join artifact_replicas replica on replica.id=put.replica_id
              join artifact_contents content on content.id=replica.content_id
              join artifact_storage_namespaces namespace on namespace.id=replica.storage_namespace_id
              where item.id=new.source_item_id and item.source_snapshot_id=attempt.source_snapshot_id
                and item.source_kind='document' and item.ingestion_adapter='upload' and item.media_type=new.media_type
                and ingest.id=new.document_version_id and ingest.sha256=new.sha256
                and ingest.byte_count=new.byte_count and ingest.media_type=new.media_type
                and put.guide_source_item_id=item.id and put.project_id=attempt.project_id
                and put.producer_request_type='guide' and put.logical_role is null and put.status='object_confirmed'
                and put.sha256=new.sha256 and put.byte_count=new.byte_count and put.media_type=new.media_type
                and put.storage_namespace_id=new.storage_namespace_id and put.namespace_fingerprint=new.namespace_fingerprint
                and replica.id=new.replica_id and replica.content_id=new.content_id
                and replica.storage_namespace_id=new.storage_namespace_id and replica.namespace_fingerprint=new.namespace_fingerprint
                and replica.integrity_state <> 'invalid' and replica.availability_state in ('unknown','available')
                and content.sha256=new.sha256 and content.byte_count=new.byte_count and content.media_type=new.media_type
                and namespace.namespace_fingerprint=new.namespace_fingerprint
                and namespace.adapter=replica.adapter and namespace.provider_profile=replica.provider_profile
                and (
                  (put.terminal_result_code='document_stored' and exists(
                    select 1 from artifact_operation_receipts receipt
                    where receipt.id=put.receipt_id and receipt.put_attempt_id=put.id
                      and receipt.guide_source_item_id=item.id and receipt.replica_id=replica.id
                      and receipt.request_digest=put.request_digest
                      and receipt.provider_object_ref=replica.provider_object_ref and receipt.outcome='document_stored'))
                  or (put.terminal_result_code='document_stored_observed' and put.receipt_id is null and exists(
                    select 1 from artifact_put_observation_receipts receipt
                    where receipt.put_attempt_id=put.id and receipt.execution_generation=put.execution_generation
                      and receipt.outcome='observed_confirmed'
                      and receipt.expected_sha256=put.sha256 and receipt.observed_sha256=put.sha256
                      and receipt.expected_byte_count=put.byte_count and receipt.observed_byte_count=put.byte_count))
                )) then
              raise exception 'guide runtime file source lineage mismatch' using errcode='23514';
            end if;
          end if;
          if new.kind='attachment' and not exists(select 1 from project_guide_runtime_allocations parent
              join project_guide_runtime_allocations file on file.id=new.source_file_allocation_id
              where parent.id=new.container_allocation_id and parent.attempt_id=new.attempt_id
                and parent.manifest_sha256=new.manifest_sha256 and parent.kind='container'
                and parent.provider_id=new.parent_provider_id and parent.state='allocated'
                and file.attempt_id=new.attempt_id and file.manifest_sha256=new.manifest_sha256
                and file.kind='file' and file.state='allocated' and file.document_handle=new.document_handle) then
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
      end $_$;
CREATE FUNCTION public.guard_iso_4217_currency_codes() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'ISO 4217 currency-code registry is migration-owned and immutable'
            using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.guard_outbox_delivery_attempt() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op in ('DELETE','TRUNCATE') then
            raise exception 'outbox delivery custody cannot be removed' using errcode='55000';
          elsif tg_op = 'INSERT' then
            if new.stage <> 'claimed' or new.claimed_at > clock_timestamp()
               or new.claim_expires_at <= clock_timestamp() then
              raise exception 'outbox delivery must begin claimed' using errcode='23514';
            end if;
          else
            if (new.event_id,new.claim_generation,new.project_id,new.payload_digest,new.claim_owner,
                new.claimed_at,new.claim_expires_at) is distinct from
               (old.event_id,old.claim_generation,old.project_id,old.payload_digest,old.claim_owner,
                old.claimed_at,old.claim_expires_at) or old.stage = 'completed' then
              raise exception 'outbox delivery custody is immutable' using errcode='55000';
            end if;
            if not ((old.stage = 'claimed' and new.stage in ('invoked','completed')) or
                    (old.stage = 'invoked' and new.stage = 'completed')) or
               (old.stage = 'claimed' and new.stage = 'completed' and new.invoked_at is not null) or
               (old.stage = 'invoked' and new.invoked_at is distinct from old.invoked_at) then
              raise exception 'illegal outbox custody transition' using errcode='23514';
            end if;
          end if;
          if new.stage = 'invoked' and (new.invoked_at > clock_timestamp()
             or new.claim_expires_at <= clock_timestamp()) then
            raise exception 'outbox invocation lease is not current' using errcode='23514';
          end if;
          if new.stage = 'completed' and
             (new.outcome_json::jsonb->>'receipt_completed_at')::timestamptz > clock_timestamp() then
            raise exception 'outbox completion cannot be in the future' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_outbox_event() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare event_time timestamptz;
        begin
          if tg_op = 'TRUNCATE' then
            raise exception 'outbox events cannot be truncated' using errcode='55000';
          elsif tg_op = 'DELETE' then
            raise exception 'outbox events cannot be deleted' using errcode='55000';
          elsif tg_op = 'INSERT' then
            event_time := statement_timestamp();
            new.producer := 'workstream';
            new.occurred_at := event_time;
            new.delivery_state := 'pending';
            new.attempt_count := 0;
            new.next_attempt_at := event_time;
            new.claim_owner := null;
            new.claim_generation := 0;
            new.claimed_at := null;
            new.claim_expires_at := null;
            new.last_attempt_at := null;
            new.last_error_code := null;
            new.finalized_at := null;
            new.archived_at := null;
            return new;
          end if;
          if (new.event_id, new.event_type, new.event_version, new.producer,
              new.aggregate_type, new.aggregate_id, new.project_id,
              new.correlation_id, new.causation_event_id, new.idempotency_key,
              new.payload, new.payload_digest, new.occurred_at)
             is distinct from
             (old.event_id, old.event_type, old.event_version, old.producer,
              old.aggregate_type, old.aggregate_id, old.project_id,
              old.correlation_id, old.causation_event_id, old.idempotency_key,
              old.payload, old.payload_digest, old.occurred_at) then
            raise exception 'outbox event envelope is immutable' using errcode='55000';
          end if;
          if new.attempt_count < old.attempt_count
             or new.claim_generation < old.claim_generation
             or new.attempt_count <> new.claim_generation then
            raise exception 'outbox counters cannot regress' using errcode='23514';
          end if;
          if old.archived_at is not null and
             (new.delivery_state, new.attempt_count, new.next_attempt_at,
              new.claim_owner, new.claim_generation, new.claimed_at,
              new.claim_expires_at, new.last_attempt_at, new.last_error_code,
              new.finalized_at, new.archived_at)
             is distinct from
             (old.delivery_state, old.attempt_count, old.next_attempt_at,
              old.claim_owner, old.claim_generation, old.claimed_at,
              old.claim_expires_at, old.last_attempt_at, old.last_error_code,
              old.finalized_at, old.archived_at) then
            raise exception 'archived outbox event is closed' using errcode='55000';
          end if;
          if old.delivery_state in ('pending', 'retryable')
             and new.delivery_state = 'claimed' then
            if new.attempt_count <> old.attempt_count + 1
               or new.claim_generation <> old.claim_generation + 1
               or new.last_error_code is distinct from old.last_error_code then
              raise exception 'outbox claim generation must increment once' using errcode='23514';
            end if;
          elsif old.delivery_state = 'claimed'
                and new.delivery_state in ('retryable','acknowledged','dead_letter','cancelled') then
            if new.attempt_count <> old.attempt_count
               or new.claim_generation <> old.claim_generation
               or new.last_attempt_at is distinct from old.last_attempt_at then
              raise exception 'outbox outcome cannot change claim generation' using errcode='23514';
            end if;
          elsif old.delivery_state = 'dead_letter'
                and new.delivery_state = 'retryable' and old.archived_at is null then
            if new.attempt_count <> old.attempt_count
               or new.claim_generation <> old.claim_generation
               or new.last_attempt_at is distinct from old.last_attempt_at
               or new.last_error_code is distinct from old.last_error_code then
              raise exception 'outbox requeue cannot change claim generation' using errcode='23514';
            end if;
          elsif old.delivery_state in ('pending','retryable')
                and new.delivery_state = 'cancelled' then
            if new.attempt_count <> old.attempt_count
               or new.claim_generation <> old.claim_generation
               or new.last_attempt_at is distinct from old.last_attempt_at
               or new.last_error_code is distinct from old.last_error_code then
              raise exception 'outbox cancellation cannot change claim generation' using errcode='23514';
            end if;
          elsif old.delivery_state in ('pending','retryable')
                and new.delivery_state = old.delivery_state then
            if (new.attempt_count, new.claim_owner, new.claim_generation,
                new.claimed_at, new.claim_expires_at, new.last_attempt_at,
                new.last_error_code, new.finalized_at, new.archived_at)
               is distinct from
               (old.attempt_count, old.claim_owner, old.claim_generation,
                old.claimed_at, old.claim_expires_at, old.last_attempt_at,
                old.last_error_code, old.finalized_at, old.archived_at) then
              raise exception 'outbox eligibility update changed unrelated state' using errcode='23514';
            end if;
          elsif old.delivery_state in ('acknowledged','dead_letter','cancelled')
                and new.delivery_state = old.delivery_state then
            if (new.attempt_count, new.next_attempt_at, new.claim_owner,
                new.claim_generation, new.claimed_at, new.claim_expires_at,
                new.last_attempt_at, new.last_error_code, new.finalized_at)
               is distinct from
               (old.attempt_count, old.next_attempt_at, old.claim_owner,
                old.claim_generation, old.claimed_at, old.claim_expires_at,
                old.last_attempt_at, old.last_error_code, old.finalized_at)
               or (old.archived_at is not null and new.archived_at is distinct from old.archived_at)
               or (old.archived_at is null and new.archived_at is null) then
              raise exception 'terminal outbox event permits archival only' using errcode='23514';
            end if;
          else
            raise exception 'illegal outbox delivery transition' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_policy_mutation_replay() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='INSERT' then
            if new.status<>'pending' then
              raise exception 'policy mutation must begin pending' using errcode='23514';
            end if;
            return new;
          elsif tg_op='DELETE' then
            raise exception 'policy mutation replay is immutable' using errcode='55000';
          elsif new is not distinct from old then
            return new;
          elsif old.status='pending' and new.status='committed'
             and (new.id,new.actor_profile_id,new.identity_link_id,new.action_id,
                  new.idempotency_key,new.request_digest,new.policy_hash,
                  new.resource_context_digest,
                  new.operation_id,new.project_id,new.guide_id,new.policy_id,
                  new.policy_generation,new.created_at)
                 is not distinct from
                 (old.id,old.actor_profile_id,old.identity_link_id,old.action_id,
                  old.idempotency_key,old.request_digest,old.policy_hash,
                  old.resource_context_digest,
                  old.operation_id,old.project_id,old.guide_id,old.policy_id,
                  old.policy_generation,old.created_at) then
            return new;
          end if;
          raise exception 'policy mutation replay is immutable' using errcode='23514';
        end $$;
CREATE FUNCTION public.guard_post_policy_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
CREATE FUNCTION public.guard_pre_submit_attempt() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
      OR NEW.request_json->>'actor_profile_id' IS DISTINCT FROM NEW.actor_profile_id::text
      OR NEW.request_json->>'identity_link_id' IS DISTINCT FROM NEW.identity_link_id::text
      OR NEW.request_json->>'task_id' IS DISTINCT FROM NEW.task_id::text
      OR NEW.request_json->>'assignment_id' IS DISTINCT FROM NEW.assignment_id::text THEN
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
CREATE FUNCTION public.guard_pre_submit_evidence_result_membership() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare parent_created_at timestamptz; expected_count integer; current_count integer;
        begin
          select created_at, result_count into parent_created_at, expected_count
            from pre_submit_evidence_sets where id=new.evidence_set_id for key share;
          select count(*) into current_count from pre_submit_evidence_results
            where evidence_set_id=new.evidence_set_id;
          if parent_created_at is null
             or parent_created_at <> transaction_timestamp()
             or current_count >= expected_count then
            raise exception 'pre-submit evidence result membership is closed'
              using errcode='55000';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_pre_submit_evidence_results_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'pre_submit_evidence_results rows are immutable' using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.guard_pre_submit_evidence_set_creation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if new.created_at is distinct from transaction_timestamp() then
            raise exception 'pre-submit evidence creation timestamp is invalid'
              using errcode='55000';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_pre_submit_evidence_sets_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'pre_submit_evidence_sets rows are immutable' using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.guard_project_compensation_units() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op in ('UPDATE','DELETE') then
            raise exception 'project compensation-unit lifecycle behavior is deferred'
              using errcode='55000';
          end if;
          if new.status <> 'active' then
            raise exception 'project compensation units must begin active'
              using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_project_create_idempotency() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op = 'INSERT' then
            if new.status <> 'pending' or new.committed_at is not null then
              raise exception 'project create reservation must begin pending' using errcode='23514';
            end if;
            return new;
          elsif tg_op = 'DELETE' then
            raise exception 'project create reservations are immutable' using errcode='55000';
          end if;
          if new is not distinct from old then
            return new;
          end if;
          if old.status <> 'pending' or new.status <> 'committed'
             or (new.id, new.actor_profile_id, new.identity_link_id, new.action_id,
                 new.idempotency_key, new.request_digest, new.operation_id,
                 new.project_id, new.operation_generation, new.created_at)
                is distinct from
                (old.id, old.actor_profile_id, old.identity_link_id, old.action_id,
                 old.idempotency_key, old.request_digest, old.operation_id,
                 old.project_id, old.operation_generation, old.created_at) then
            raise exception 'invalid project create reservation transition' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_project_guide_compilation_attempt_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if row(new.project_id,new.guide_id,new.guide_version,new.source_snapshot_id,
            new.source_snapshot_hash,new.setup_run_id,new.setup_generation,
            new.canonical_input_hash,new.guide_material_hash,new.pre_catalogue_id,
            new.pre_catalogue_version,new.pre_catalogue_schema_version,
            new.pre_catalogue_manifest_hash,new.post_catalogue_id,new.post_catalogue_version,
            new.post_catalogue_schema_version,new.post_catalogue_manifest_hash,
            new.agent_identity,new.agent_version,new.instruction_version,
            new.provider_idempotency_key)
          is distinct from row(old.project_id,old.guide_id,old.guide_version,old.source_snapshot_id,
            old.source_snapshot_hash,old.setup_run_id,old.setup_generation,
            old.canonical_input_hash,old.guide_material_hash,old.pre_catalogue_id,
            old.pre_catalogue_version,old.pre_catalogue_schema_version,
            old.pre_catalogue_manifest_hash,old.post_catalogue_id,old.post_catalogue_version,
            old.post_catalogue_schema_version,old.post_catalogue_manifest_hash,
            old.agent_identity,old.agent_version,old.instruction_version,
            old.provider_idempotency_key) then raise exception 'compilation attempt identity is immutable'; end if;
          if old.status in ('compilation_persisted','compilation_invalid_terminal') then raise exception 'terminal compilation attempt is immutable'; end if;
          if new.reserved_at is distinct from old.reserved_at then
            raise exception 'compilation reservation timestamp is immutable';
          end if;
          if new.provider_uncertain_at is distinct from old.provider_uncertain_at and
            not (old.status='compilation_reserved' and new.status='compilation_provider_uncertain') then
            raise exception 'provider uncertainty timestamp is immutable';
          end if;
          if new.accepted_at is distinct from old.accepted_at and
            not (old.status in ('compilation_reserved','compilation_provider_uncertain') and new.status='provider_result_accepted') then
            raise exception 'accepted timestamp is immutable';
          end if;
          if new.terminal_at is distinct from old.terminal_at and
            not (old.status in ('compilation_reserved','compilation_provider_uncertain') and new.status='compilation_invalid_terminal') then
            raise exception 'terminal timestamp is immutable';
          end if;
          if row(new.persisted_at,new.persisted_compilation_id) is distinct from
            row(old.persisted_at,old.persisted_compilation_id) and
            not (old.status='provider_result_accepted' and new.status='compilation_persisted') then
            raise exception 'persisted custody is immutable';
          end if;
          if old.status='provider_result_accepted' and row(new.canonical_result::jsonb,new.result_hash,new.component_hashes::jsonb,new.accepted_at)
            is distinct from row(old.canonical_result::jsonb,old.result_hash,old.component_hashes::jsonb,old.accepted_at) then
            raise exception 'accepted compilation result is immutable';
          end if;
          if not ((old.status='compilation_reserved' and new.status in ('compilation_provider_uncertain','provider_result_accepted','compilation_invalid_terminal')) or
                  (old.status='compilation_provider_uncertain' and new.status in ('provider_result_accepted','compilation_invalid_terminal')) or
                  (old.status='provider_result_accepted' and new.status='compilation_persisted')) then
            raise exception 'invalid compilation attempt transition';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_project_guide_compilation_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare predecessor_generation bigint;
        declare source_attempt project_guide_compilation_attempts%rowtype;
        begin
          select * into source_attempt from project_guide_compilation_attempts
            where id=new.attempt_id for update;
          if source_attempt.id is null or source_attempt.status <> 'provider_result_accepted' or
            row(new.project_id,new.guide_id,new.guide_version,new.source_snapshot_id,
              new.source_snapshot_hash,new.setup_run_id,new.setup_generation,
              new.canonical_input_hash,new.guide_material_hash,
              new.pre_catalogue_manifest_hash,new.post_catalogue_manifest_hash,
              new.agent_identity,new.agent_version,new.instruction_version,
              new.canonical_result::jsonb,new.result_hash,new.component_hashes::jsonb)
            is distinct from
            row(source_attempt.project_id,source_attempt.guide_id,
              source_attempt.guide_version,source_attempt.source_snapshot_id,
              source_attempt.source_snapshot_hash,source_attempt.setup_run_id,
              source_attempt.setup_generation,source_attempt.canonical_input_hash,
              source_attempt.guide_material_hash,source_attempt.pre_catalogue_manifest_hash,
              source_attempt.post_catalogue_manifest_hash,source_attempt.agent_identity,
              source_attempt.agent_version,source_attempt.instruction_version,
              source_attempt.canonical_result::jsonb,source_attempt.result_hash,
              source_attempt.component_hashes::jsonb) then
            raise exception 'compilation does not match its accepted attempt';
          end if;
          if not exists(
            select 1 from audit_events event
            join actor_profiles profile on profile.id=new.created_by_actor_profile_id
            join actor_identity_links link on link.id=new.created_via_identity_link_id
              and link.actor_profile_id=profile.id
            where event.id=new.authorization_decision_event_id
              and event.event_domain='authority'
              and event.event_type='SensitiveAuthorizationAllowed'
              and event.denial_code is null
              and event.actor_id=new.created_by_actor_profile_id::text
              and event.permission_id='project.guide_compilation.execute'
              and event.action_id='project.guide_compilation.execute'
              and event.project_id=new.project_id
              and event.resource_type='project_guide_compilation_attempt'
              and event.resource_id=new.attempt_id::text
              and event.after_facts->>'allowed'='true'
              and event.after_facts->>'resource_context_digest'=
                new.authorization_resource_context_digest
              and profile.actor_kind='service' and profile.status='active'
              and profile.service_identity='workstream.project.setup'
              and link.subject_kind='service' and link.status='active'
              and event.actor_ref_kind='actor_profile'
          ) then
            raise exception 'compilation authorization evidence is invalid';
          end if;
          if new.supersedes_compilation_id is null then return new; end if;
          select setup_generation into predecessor_generation
            from project_guide_compilations
            where id=new.supersedes_compilation_id
              and project_id=new.project_id and guide_id=new.guide_id;
          if predecessor_generation is null or predecessor_generation >= new.setup_generation then
            raise exception 'compilation generation must strictly advance';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_project_guide_compilation_request_operation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          attempt project_guide_compilation_attempts%rowtype;
          event audit_events%rowtype;
          grant_row admin_role_grants%rowtype;
        begin
          select * into attempt from project_guide_compilation_attempts
            where id=new.attempt_id;
          select * into event from audit_events
            where id=new.authorization_decision_event_id;
          select * into grant_row from admin_role_grants
            where id=event.matched_grant_id::uuid;
          if attempt.id is null or event.id is null then
            raise exception 'guide compilation request references are invalid'
              using errcode='23514';
          end if;
          if new.request_facts_digest is distinct from
                project_guide_compilation_request_facts_digest(new, attempt) then
            raise exception 'guide compilation request facts digest is invalid'
              using errcode='23514';
          end if;
          if new.request_trigger = 'automatic_source_ready' then
            perform require_automatic_compilation_origin(new.project_id, new.guide_id,
              new.source_snapshot_id, new.setup_run_id, new.setup_generation,
              new.source_mutation_operation_id, new.source_authorization_decision_event_id);
            if event.event_domain is distinct from 'authority'
               or event.event_type is distinct from 'SensitiveAuthorizationAllowed'
               or event.action_id is distinct from 'project.guide_compilation.request_automatic'
               or event.permission_id is distinct from 'project.guide_compilation.execute'
               or event.resource_type is distinct from 'project_guide_compilation_request'
               or event.resource_id is distinct from new.operation_id::text
               or event.project_id is distinct from new.project_id
               or event.actor_id is distinct from new.actor_profile_id::text
               or event.actor_ref_kind is distinct from 'actor_profile'
               or event.matched_grant_id is not null
               or event.after_facts->>'allowed' is distinct from 'true' then
              raise exception 'automatic compilation request audit event is invalid' using errcode='23514';
            end if;
            perform 1 from actor_identity_links l join actor_profiles a on a.id=l.actor_profile_id
              where l.id=new.identity_link_id and l.actor_profile_id=new.actor_profile_id
              and l.status='active' and l.subject_kind='service' and a.status='active'
              and a.actor_kind='service' and a.service_identity='workstream.project.setup'
              for update of l,a;
            if not found then
              raise exception 'automatic compilation service authority is invalid' using errcode='23514';
            end if;
            if event.after_facts->>'resource_context_digest' is distinct from
              ('sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(
                jsonb_build_object(
                  'action_id','project.guide_compilation.request_automatic',
                  'permission_id','project.guide_compilation.execute',
                  'resource_type','project_guide_compilation_request',
                  'resource_id',new.operation_id::text,'scope_project_id',new.project_id,
                  'actor_profile_id',new.actor_profile_id,'identity_link_id',new.identity_link_id,
                  'service_identity','workstream.project.setup',
                  'request_facts_digest',new.request_facts_digest,
                  'trigger',new.request_trigger,
                  'source_mutation_operation_id',new.source_mutation_operation_id::text,
                  'source_authorization_decision_event_id',new.source_authorization_decision_event_id
                )), 'UTF8')), 'hex')) then
              raise exception 'automatic compilation request authority digest is invalid' using errcode='23514';
            end if;
            return new;
          end if;
          if new.request_trigger is distinct from 'project_manager'
             or grant_row.id is null then
            raise exception 'guide compilation request trigger is invalid' using errcode='23514';
          end if;
          if event.event_domain is distinct from 'authority'
             or event.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or event.action_id is distinct from 'project.guide_compilation.request'
             or event.permission_id is distinct from 'project.guide_compilation.request'
             or event.resource_type is distinct from 'project_guide_compilation_request'
             or event.resource_id is distinct from new.operation_id::text
             or event.project_id is distinct from new.project_id
             or event.actor_id is distinct from new.actor_profile_id::text
             or event.actor_ref_kind is distinct from 'actor_profile'
             or event.after_facts->>'allowed' is distinct from 'true' then
            raise exception 'guide compilation request audit event is invalid'
              using errcode='23514';
          end if;
          if grant_row.target_actor_profile_id is distinct from new.actor_profile_id
             or grant_row.role is distinct from 'project_manager'
             or grant_row.status is distinct from 'active'
             or grant_row.scope_type is distinct from 'project'
             or grant_row.scope_project_id is distinct from new.project_id then
            raise exception 'guide compilation request grant is invalid'
              using errcode='23514';
          end if;
          if event.after_facts->>'resource_context_digest' is distinct from
                project_guide_compilation_request_authority_digest(new, grant_row) then
            raise exception 'guide compilation request authority digest is invalid'
              using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_project_guide_component_projection_operation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare evidence audit_events%rowtype;
        begin
          select * into evidence from audit_events
            where id=new.authorization_decision_event_id;
          if new.output_digest is distinct from
                project_guide_projection_business_digest(new) then
            raise exception 'projection business custody is invalid'
              using errcode='23514';
          end if;
          if new.facts_digest is distinct from
                project_guide_projection_facts_digest(new)
             or new.authority_resource_digest is distinct from
                project_guide_projection_authority_digest(new) then
            raise exception 'projection digest custody is invalid'
              using errcode='23514';
          end if;
          if evidence.id is null
             or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.action_id is distinct from new.action_id
             or evidence.permission_id is distinct from new.permission_id
             or evidence.resource_id is distinct from new.operation_id::text
             or evidence.request_id is null
             or evidence.correlation_id is distinct from new.correlation_id
             or evidence.project_id is distinct from new.project_id
             or evidence.actor_id is distinct from new.actor_profile_id::text
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                  is distinct from new.authority_resource_digest
             or new.service_identity is distinct from 'workstream.project.setup'
             or (new.component='guide_sufficiency' and
                 (new.action_id is distinct from 'project.guide_sufficiency.run'
                  or new.permission_id is distinct from 'project.guide.manage'
                  or evidence.resource_type is distinct from
                     'project_guide_sufficiency_projection'))
             or (new.component='submission_artifact_policy' and
                 (new.action_id is distinct from
                     'project.submission_artifact_policy.derive'
                  or new.permission_id is distinct from
                     'project.effective_policy.manage'
                  or evidence.resource_type is distinct from
                     'project_submission_artifact_policy_projection')) then
            raise exception 'projection authority custody is invalid'
              using errcode='23514';
          end if;
          return new;
        end; $$;
CREATE FUNCTION public.guard_project_guide_policy_selection() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          if old.status in ('active','superseded') and (
            new.selected_review_policy_id is distinct from old.selected_review_policy_id or
            new.selected_review_policy_generation is distinct from
              old.selected_review_policy_generation or
            new.selected_review_policy_hash is distinct from old.selected_review_policy_hash or
            new.selected_revision_policy_id is distinct from old.selected_revision_policy_id or
            new.selected_revision_policy_generation is distinct from
              old.selected_revision_policy_generation or
            new.selected_revision_policy_hash is distinct from old.selected_revision_policy_hash
          ) then
            raise exception 'active guide policy selection is immutable' using errcode='55000';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_project_guide_runtime_configuration() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
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
           or octet_length(config::text)>75000 or not (config ?& array['capability_key','runtime_key','model_provider','model','model_api','instruction_id','instruction_version','instructions','instructions_sha256','retry_jitter','timeout_seconds','request_timeout_seconds','maximum_retries','retry_backoff_multiplier','retry_initial_delay_seconds','retry_max_delay_seconds','circuit_failure_threshold','circuit_cooldown_seconds','maximum_manifest_bytes','maximum_documents','maximum_document_bytes','maximum_total_document_bytes','maximum_turns','maximum_hosted_tool_calls','compaction_threshold_tokens','container_expiry_minutes','file_expiry_seconds','cleanup_timeout_seconds'])
           or config - array['capability_key','runtime_key','model_provider','model','model_api','instruction_id','instruction_version','instructions','instructions_sha256','retry_jitter','timeout_seconds','request_timeout_seconds','maximum_retries','retry_backoff_multiplier','retry_initial_delay_seconds','retry_max_delay_seconds','circuit_failure_threshold','circuit_cooldown_seconds','maximum_manifest_bytes','maximum_documents','maximum_document_bytes','maximum_total_document_bytes','maximum_turns','maximum_hosted_tool_calls','compaction_threshold_tokens','container_expiry_minutes','file_expiry_seconds','cleanup_timeout_seconds'] <> '{}'::jsonb
           or config->>'capability_key' is distinct from 'project_guide_compilation'
           or jsonb_typeof(config->'runtime_key') is distinct from 'string'
           or not (config->>'runtime_key' ~ '^[a-z][a-z0-9_]{0,63}$')
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
           or jsonb_typeof(config->'timeout_seconds') is distinct from 'number' or not (config->>'timeout_seconds' ~ '^[0-9]+$') or (config->>'timeout_seconds')::numeric < 1 or (config->>'timeout_seconds')::numeric > 7200 or jsonb_typeof(config->'request_timeout_seconds') is distinct from 'number' or not (config->>'request_timeout_seconds' ~ '^[0-9]+$') or (config->>'request_timeout_seconds')::numeric < 1 or (config->>'request_timeout_seconds')::numeric > 1800 or jsonb_typeof(config->'maximum_retries') is distinct from 'number' or not (config->>'maximum_retries' ~ '^[0-9]+$') or (config->>'maximum_retries')::numeric < 0 or (config->>'maximum_retries')::numeric > 5 or jsonb_typeof(config->'retry_backoff_multiplier') is distinct from 'number' or not (config->>'retry_backoff_multiplier' ~ '^[0-9]+$') or (config->>'retry_backoff_multiplier')::numeric < 1 or (config->>'retry_backoff_multiplier')::numeric > 4 or jsonb_typeof(config->'retry_initial_delay_seconds') is distinct from 'number' or not (config->>'retry_initial_delay_seconds' ~ '^[0-9]+$') or (config->>'retry_initial_delay_seconds')::numeric < 1 or (config->>'retry_initial_delay_seconds')::numeric > 30 or jsonb_typeof(config->'retry_max_delay_seconds') is distinct from 'number' or not (config->>'retry_max_delay_seconds' ~ '^[0-9]+$') or (config->>'retry_max_delay_seconds')::numeric < 1 or (config->>'retry_max_delay_seconds')::numeric > 120 or jsonb_typeof(config->'circuit_failure_threshold') is distinct from 'number' or not (config->>'circuit_failure_threshold' ~ '^[0-9]+$') or (config->>'circuit_failure_threshold')::numeric < 1 or (config->>'circuit_failure_threshold')::numeric > 20 or jsonb_typeof(config->'circuit_cooldown_seconds') is distinct from 'number' or not (config->>'circuit_cooldown_seconds' ~ '^[0-9]+$') or (config->>'circuit_cooldown_seconds')::numeric < 1 or (config->>'circuit_cooldown_seconds')::numeric > 600 or jsonb_typeof(config->'maximum_manifest_bytes') is distinct from 'number' or not (config->>'maximum_manifest_bytes' ~ '^[0-9]+$') or (config->>'maximum_manifest_bytes')::numeric < 1024 or (config->>'maximum_manifest_bytes')::numeric > 1000000 or jsonb_typeof(config->'maximum_documents') is distinct from 'number' or not (config->>'maximum_documents' ~ '^[0-9]+$') or (config->>'maximum_documents')::numeric < 1 or (config->>'maximum_documents')::numeric > 100 or jsonb_typeof(config->'maximum_document_bytes') is distinct from 'number' or not (config->>'maximum_document_bytes' ~ '^[0-9]+$') or (config->>'maximum_document_bytes')::numeric < 1 or (config->>'maximum_document_bytes')::numeric > 536870912 or jsonb_typeof(config->'maximum_total_document_bytes') is distinct from 'number' or not (config->>'maximum_total_document_bytes' ~ '^[0-9]+$') or (config->>'maximum_total_document_bytes')::numeric < 1 or jsonb_typeof(config->'maximum_turns') is distinct from 'number' or not (config->>'maximum_turns' ~ '^[0-9]+$') or (config->>'maximum_turns')::numeric < 3 or (config->>'maximum_turns')::numeric > 100 or jsonb_typeof(config->'maximum_hosted_tool_calls') is distinct from 'number' or not (config->>'maximum_hosted_tool_calls' ~ '^[0-9]+$') or (config->>'maximum_hosted_tool_calls')::numeric < 3 or (config->>'maximum_hosted_tool_calls')::numeric > 200 or jsonb_typeof(config->'compaction_threshold_tokens') is distinct from 'number' or not (config->>'compaction_threshold_tokens' ~ '^[0-9]+$') or (config->>'compaction_threshold_tokens')::numeric < 1000 or (config->>'compaction_threshold_tokens')::numeric > 100000 or jsonb_typeof(config->'container_expiry_minutes') is distinct from 'number' or not (config->>'container_expiry_minutes' ~ '^[0-9]+$') or (config->>'container_expiry_minutes')::numeric < 10 or (config->>'container_expiry_minutes')::numeric > 60 or jsonb_typeof(config->'file_expiry_seconds') is distinct from 'number' or not (config->>'file_expiry_seconds' ~ '^[0-9]+$') or (config->>'file_expiry_seconds')::numeric < 3600 or (config->>'file_expiry_seconds')::numeric > 7200 or jsonb_typeof(config->'cleanup_timeout_seconds') is distinct from 'number' or not (config->>'cleanup_timeout_seconds' ~ '^[0-9]+$') or (config->>'cleanup_timeout_seconds')::numeric < 5 or (config->>'cleanup_timeout_seconds')::numeric > 120
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
      end $_$;
CREATE FUNCTION public.guard_project_guide_setup_finalization() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
         or s.documents_ready_at is null
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
         or sufficient.output_id is distinct from new.sufficiency_report_id
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
         or policy.output_id is distinct from new.artifact_policy_id
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
         or evidence.actor_id is distinct from new.actor_profile_id::text
         or evidence.action_id is distinct from new.action_id
         or evidence.permission_id is distinct from new.permission_id
         or evidence.project_id is distinct from new.project_id
         or evidence.resource_type is distinct from 'project_guide_setup_finalization'
         or evidence.resource_id is distinct from new.id::text::text
         or evidence.request_id is null
         or evidence.correlation_id is distinct from new.correlation_id
         or not exists(select 1 from actor_profiles actor join actor_identity_links link
              on link.actor_profile_id=actor.id where actor.id=new.actor_profile_id
                and link.id=new.identity_link_id and actor.actor_kind='service'
                and actor.service_identity='workstream.project.setup'
                and link.subject_kind='service' and actor.status='active' and link.status='active')
         or evidence.after_facts->>'allowed' is distinct from 'true'
         or evidence.after_facts->>'resource_context_digest' is distinct from new.authority_resource_digest
      then raise exception 'finalization authority mismatch' using errcode='23514'; end if;
      return new;
    end; $$;
CREATE FUNCTION public.guard_project_guide_task_examples() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      begin
        if tg_op in ('DELETE','TRUNCATE') then
          raise exception 'guide source evidence cannot be deleted' using errcode='55000';
        end if;
        if tg_op='UPDATE' then
          if new.task_examples::jsonb is distinct from old.task_examples::jsonb
             or new.task_examples_hash is distinct from old.task_examples_hash then
            raise exception 'guide task examples are immutable' using errcode='23514';
          end if;
          return new;
        end if;
        if not project_guide_task_examples_valid(new.task_examples::jsonb)
           or new.task_examples_hash is distinct from project_guide_task_examples_hash(new.task_examples::jsonb) then
          raise exception 'guide task examples are invalid' using errcode='23514';
        end if;
        return new;
      end $$;
CREATE FUNCTION public.guard_project_role_grant_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='INSERT' then new.granted_at := clock_timestamp(); return new; end if;
          if tg_op='DELETE' then raise exception 'project-role grants are immutable history' using errcode='55000'; end if;
          if (new.id,new.project_id,new.actor_profile_id,new.role,new.grant_method,
              new.qualification_snapshot_id,new.granted_by_actor_profile_id,
              new.granted_by_admin_role_grant_id,new.grant_reason,new.granted_at)
             is distinct from
             (old.id,old.project_id,old.actor_profile_id,old.role,old.grant_method,
              old.qualification_snapshot_id,old.granted_by_actor_profile_id,
              old.granted_by_admin_role_grant_id,old.grant_reason,old.granted_at)
             or old.status<>'active' or old.version<>1 or new.status<>'revoked' or new.version<>2
             or new.revoked_by_actor_profile_id is null or new.revoked_by_admin_role_grant_id is null
             or new.revoked_reason is null then
            raise exception 'invalid project-role grant history transition' using errcode='23514';
          end if;
          new.revoked_at := clock_timestamp();
          return new;
        end $$;
CREATE FUNCTION public.guard_project_role_snapshot_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op='INSERT' then new.captured_at := clock_timestamp(); return new; end if;
          raise exception 'project-role qualification snapshots are immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.guard_published_contribution_policy_graph() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare version_status text;
        begin
          if TG_OP='DELETE' then
            select status into version_status from contribution_policy_versions
              where id=old.contribution_policy_version_id;
          else
            select status into version_status from contribution_policy_versions
              where id=new.contribution_policy_version_id;
          end if;
          if version_status in ('published','retired') then
            raise exception 'published contribution policy graph is immutable'
              using errcode='55000';
          end if;
          if TG_OP='DELETE' then
            return old;
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_retained_guide_source_fields() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
CREATE FUNCTION public.guard_review_admission_record() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          task_project uuid;
          checker_row checker_runs%rowtype;
        begin
          if tg_op='DELETE' then
            raise exception 'review admission records cannot be deleted' using errcode='55000';
          end if;
          if tg_op='INSERT' and new.status <> 'pending' then
            raise exception 'review admission must begin pending' using errcode='23514';
          end if;
          if tg_op='INSERT' then
            new.created_at := statement_timestamp();
          end if;
          if tg_op='UPDATE' then
            if (new.id,new.idempotency_key,new.operation_id,new.request_digest,new.project_id,
                new.task_id,new.submission_id,new.submission_version,
                new.admitting_checker_run_id,new.created_at)
               is distinct from
               (old.id,old.idempotency_key,old.operation_id,old.request_digest,old.project_id,
                old.task_id,old.submission_id,old.submission_version,
                old.admitting_checker_run_id,old.created_at) then
              raise exception 'review admission identity is immutable' using errcode='55000';
            end if;
            if old.status <> 'pending' or new.status <> 'committed' then
              raise exception 'invalid review admission transition' using errcode='23514';
            end if;
          end if;
          select project_id into task_project from workstream_tasks where id=new.task_id;
          if task_project is null or task_project <> new.project_id then
            raise exception 'review admission task project mismatch' using errcode='23514';
          end if;
          select * into checker_row from checker_runs where id=new.admitting_checker_run_id;
          if not found or checker_row.task_id <> new.task_id
             or checker_row.submission_id <> new.submission_id
             or checker_row.submission_version <> new.submission_version then
            raise exception 'review admission checker lineage mismatch' using errcode='23514';
          end if;
          if new.status='committed' and (
             checker_row.status <> 'completed'
             or checker_row.routing_recommendation <> 'allow_review'
             or checker_row.is_current_for_submission is not true) then
            raise exception 'review admission checker is not admissible' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_review_lease() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          actor_type text;
          policy_status text;
        begin
          if tg_op='DELETE' then
            raise exception 'review leases cannot be deleted' using errcode='55000';
          end if;
          if tg_op='INSERT' then
            if new.status <> 'active' then
              raise exception 'review lease must begin active' using errcode='23514';
            end if;
            new.claimed_at := statement_timestamp();
            new.closed_at := null;
            new.close_reason := null;
          else
            if old.status <> 'active' then
              raise exception 'terminal review leases are immutable' using errcode='55000';
            end if;
            if (new.id,new.review_queue_entry_id,new.project_id,new.task_id,new.submission_id,
                new.submission_version,new.reviewer_id,
                new.reviewer_contribution_policy_version_id,new.attempt_generation,
                new.claimed_at,new.expires_at)
               is distinct from
               (old.id,old.review_queue_entry_id,old.project_id,old.task_id,old.submission_id,
                old.submission_version,old.reviewer_id,
                old.reviewer_contribution_policy_version_id,old.attempt_generation,
                old.claimed_at,old.expires_at) then
              raise exception 'review lease identity is immutable' using errcode='55000';
            end if;
            if new.status='active' then
              raise exception 'review lease update must close attempt' using errcode='23514';
            end if;
          end if;
          select actor_kind into actor_type from actor_profiles where id=new.reviewer_id;
          if actor_type is distinct from 'human' then
            raise exception 'review lease reviewer must be human' using errcode='23514';
          end if;
          if tg_op='INSERT' then
            select status into policy_status from contribution_policy_versions
             where id=new.reviewer_contribution_policy_version_id and project_id=new.project_id;
            if policy_status is distinct from 'published' then
              raise exception 'review lease policy version must be published' using errcode='23514';
            end if;
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_review_policies_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'review_policies rows are immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.guard_review_queue_entry() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          task_project uuid;
          checker_row checker_runs%rowtype;
        begin
          if tg_op='DELETE' then
            raise exception 'review queue entries cannot be deleted' using errcode='55000';
          end if;
          if tg_op='INSERT' then
            if new.queue_state <> 'pending' then
              raise exception 'review queue must begin pending' using errcode='23514';
            end if;
            new.first_queued_at := statement_timestamp();
            new.available_since := new.first_queued_at;
            new.routing_generation := 1;
            new.lifecycle_generation := 1;
            new.created_at := new.first_queued_at;
          end if;
          if tg_op='UPDATE' then
            if (new.id,new.project_id,new.task_id,new.submission_id,new.submission_version,
                new.admitting_checker_run_id,new.first_queued_at,new.created_at)
               is distinct from
               (old.id,old.project_id,old.task_id,old.submission_id,old.submission_version,
                old.admitting_checker_run_id,old.first_queued_at,old.created_at) then
              raise exception 'review queue identity is immutable' using errcode='55000';
            end if;
            if old.queue_state='closed' and new.queue_state <> 'closed' then
              raise exception 'closed review queue entries cannot reopen' using errcode='23514';
            end if;
            if new.routing_generation < old.routing_generation
               or new.lifecycle_generation < old.lifecycle_generation then
              raise exception 'review queue generations cannot decrease' using errcode='23514';
            end if;
          end if;
          if new.preferred_reviewer_id is not null and not exists(
            select 1 from actor_profiles where id=new.preferred_reviewer_id and actor_kind='human'
          ) then
            raise exception 'preferred reviewer must be human' using errcode='23514';
          end if;
          if tg_op='UPDATE' then return new; end if;
          select project_id into task_project from workstream_tasks where id=new.task_id;
          if task_project is null or task_project <> new.project_id then
            raise exception 'review queue task project mismatch' using errcode='23514';
          end if;
          select * into checker_row from checker_runs where id=new.admitting_checker_run_id;
          if not found or checker_row.task_id <> new.task_id
             or checker_row.submission_id <> new.submission_id
             or checker_row.submission_version <> new.submission_version then
            raise exception 'review queue checker lineage mismatch' using errcode='23514';
          end if;
          if checker_row.status <> 'completed' or checker_row.routing_recommendation <> 'allow_review'
             or checker_row.is_current_for_submission is not true then
            raise exception 'review queue checker is not admissible' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.guard_revision_policies_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'revision_policies rows are immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.guard_service_identity_migration_evidence() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'service identity migration evidence is immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.guard_submission_bundle_admission_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin raise exception 'submission bundle admissions cannot be removed' using errcode='55000'; end; $$;
CREATE FUNCTION public.guard_submission_bundle_admission_lineage() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if row(old.durable_intent_id, old.pre_submit_evidence_set_id, old.put_attempt_id,
                 old.artifact_content_id, old.verified_replica_id, old.verification_receipt_id,
                 old.put_operation_receipt_id, old.put_observation_receipt_id,
                 old.actor_profile_id, old.identity_link_id, old.project_id, old.task_id,
                 old.assignment_id, old.predecessor_submission_id,
                 old.predecessor_submission_version,
                 old.locked_policy_context_hash,
                 old.semantic_manifest_id, old.semantic_manifest_sha256, old.archive_sha256,
                 old.archive_byte_count, old.ready_at, old.created_at)
             is distinct from
             row(new.durable_intent_id, new.pre_submit_evidence_set_id, new.put_attempt_id,
                 new.artifact_content_id, new.verified_replica_id, new.verification_receipt_id,
                 new.put_operation_receipt_id, new.put_observation_receipt_id,
                 new.actor_profile_id, new.identity_link_id, new.project_id, new.task_id,
                 new.assignment_id, new.predecessor_submission_id,
                 new.predecessor_submission_version,
                 new.locked_policy_context_hash,
                 new.semantic_manifest_id, new.semantic_manifest_sha256, new.archive_sha256,
                 new.archive_byte_count, new.ready_at, new.created_at)
          then
            raise exception 'submission bundle admission lineage is immutable' using errcode='55000';
          end if;
          if old.status <> 'ready' or new.status not in ('consumed','stale') then
            raise exception 'invalid submission bundle admission transition' using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_submission_bundle_admission_verified_lineage() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare matches integer;
        begin
          select count(*) into matches
          from submission_bundle_durable_intents intent
          join pre_submit_evidence_sets evidence
            on evidence.id=intent.pre_submit_evidence_set_id
          join artifact_put_attempts attempt on attempt.id=intent.put_attempt_id
          join artifact_replicas replica on replica.id=attempt.replica_id
          join artifact_contents content on content.id=replica.content_id
          join artifact_verification_jobs job
            on job.originating_put_attempt_id=attempt.id and job.replica_id=replica.id
          join artifact_verification_receipts verification
            on verification.verification_job_id=job.id
          where intent.id=new.durable_intent_id
            and evidence.id=new.pre_submit_evidence_set_id
            and attempt.id=new.put_attempt_id
            and content.id=new.artifact_content_id
            and replica.id=new.verified_replica_id
            and verification.id=new.verification_receipt_id
            and attempt.producer_request_type='submission_bundle'
            and attempt.producer_type='actor_profile'
            and attempt.producer_ref=evidence.actor_profile_id::text
            and attempt.project_id=evidence.project_id
            and attempt.task_id=evidence.task_id
            and attempt.media_type='application/zip'
            and content.media_type='application/zip'
            and attempt.status='object_confirmed'
            and evidence.terminal_status='passed' and evidence.eligible
            and replica.verification_state='verified'
            and replica.availability_state='available'
            and replica.integrity_state='valid'
            and verification.outcome='verified'
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
            and new.archive_sha256=evidence.archive_sha256
            and new.archive_byte_count=evidence.archive_byte_count
            and ((new.put_operation_receipt_id is not null and exists (
                  select 1 from artifact_operation_receipts receipt
                  where receipt.id=new.put_operation_receipt_id
                    and receipt.put_attempt_id=attempt.id and receipt.replica_id=replica.id
                    and receipt.outcome='stored_pending_verification'))
              or (new.put_observation_receipt_id is not null and exists (
                  select 1 from artifact_put_observation_receipts observation
                  where observation.id=new.put_observation_receipt_id
                    and observation.put_attempt_id=attempt.id
                    and observation.outcome='observed_confirmed'
                    and observation.observed_sha256=attempt.sha256
                    and observation.observed_byte_count=attempt.byte_count)));
          if matches <> 1 then
            raise exception 'submission bundle admission verified lineage mismatch'
              using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_submission_bundle_durable_intent_put_attempt() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare request_type text;
        begin
          select producer_request_type into request_type
          from artifact_put_attempts
          where id = new.put_attempt_id
          for share;
          if request_type is distinct from 'submission_bundle' then
            raise exception 'submission bundle durable intent requires submission_bundle put attempt'
              using errcode='23514';
          end if;
          return new;
        end;
        $$;
CREATE FUNCTION public.guard_submission_bundle_durable_intents_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'submission_bundle_durable_intents rows are immutable'
            using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.guard_task_management_audit() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
declare refs jsonb; payload jsonb; decision audit_events%rowtype; expected_action text; facts jsonb; digest text;
begin
  if new.event_type not in ('TaskCreated','TaskScreened','TaskReleased') then return new; end if;
  payload := new.event_payload::jsonb; refs := payload->'references';
  facts := payload->'manager_authority_facts'; digest := payload->>'authorization_resource_digest';
  expected_action := case new.event_type when 'TaskCreated' then 'project.task.create'
    when 'TaskScreened' then 'project.task.screen' else 'project.task.release' end;
  select * into decision from audit_events where id::text=refs->>'authorization_decision_id';
  if not found or not coalesce(
    new.event_domain='legacy_lifecycle' and new.auth_source='local_lifecycle'
    and new.entity_type='task' and new.is_dev_auth=false
    and refs=jsonb_build_object('project_id',refs->>'project_id','task_id',new.entity_id,
                               'authorization_decision_id',decision.id)
    and decision.event_domain='authority' and decision.event_type='SensitiveAuthorizationAllowed'
    and decision.action_id=expected_action and decision.permission_id='project.task.manage'
    and decision.actor_id=new.actor_id and decision.project_id::text=refs->>'project_id'
    and decision.resource_type='project' and decision.resource_id=refs->>'project_id'
    and exists(select 1 from workstream_tasks t where t.id=new.entity_id
      and t.project_id::text=refs->>'project_id' and t.status=new.to_status
      and (new.event_type<>'TaskCreated' or t.source_type=payload->>'source_type'))
    and facts=jsonb_build_object('resource_type','task_authority','resource_id',new.entity_id,
      'scope_project_id',refs->>'project_id','actor_profile_id',new.actor_id,
      'identity_link_id',facts->'identity_link_id','task_status',coalesce(new.from_status,'draft'),
      'assigned_to',null,'assignment_id',null,'assignment_contributor_id',null,
      'locked_context_hash',facts->'locked_context_hash','reason',facts->'reason',
      'idempotency_key',facts->'idempotency_key','replay_assignment_id',null,
      'request_digest',facts->'request_digest','replay_command_id',null)
    and octet_length(convert_to(project_guide_projection_canonical_json(facts),'UTF8'))<=4096
    and (facts->>'identity_link_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    and (facts->>'locked_context_hash') ~ '^sha256:[0-9a-f]{64}$'
    and exists(select 1 from actor_identity_links l where l.id::text=facts->>'identity_link_id' and l.actor_profile_id::text=new.actor_id)
    and (new.reason is not distinct from case when new.event_type='TaskCreated' then null
      when nullif(btrim(facts->>'reason'),'') is null then 'lifecycle_state_changed' else facts->>'reason' end)
    and (new.event_type<>'TaskCreated' or facts->'reason'='null'::jsonb)
    and exists(select 1 from task_command_receipts r where r.actor_profile_id::text=new.actor_id
      and r.action_id=expected_action and r.idempotency_key::text=facts->>'idempotency_key'
      and r.task_id=new.entity_id and r.request_digest=facts->>'request_digest' and r.status='pending')
    and digest='sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(
      jsonb_build_object('resource_context',jsonb_strip_nulls(facts))), 'UTF8')), 'hex')
    and decision.after_facts::jsonb=jsonb_build_object('allowed',true,'resource_context_digest',digest)
    and ((new.event_type='TaskCreated' and new.from_status is null and new.to_status='draft'
          and payload=jsonb_build_object('references',refs,'source_type',payload->'source_type',
            'manager_authority_facts',facts,'authorization_resource_digest',digest)
          and payload->>'source_type' in ('manual','markdown_import','csv_import'))
         or (new.event_type in ('TaskScreened','TaskReleased')
             and ((new.event_type='TaskScreened' and new.from_status='draft' and new.to_status='screening')
               or (new.event_type='TaskReleased' and new.from_status='screening' and new.to_status='ready'
                   and btrim(new.reason)<>''))
             and exists(select 1 from workstream_tasks t where t.id=new.entity_id and
              (payload - array['references','manager_authority_facts','authorization_resource_digest']) = jsonb_build_object('locked_guide_version', to_jsonb(t)->'locked_guide_version', 'locked_guide_source_snapshot_id', to_jsonb(t)->'locked_guide_source_snapshot_id', 'locked_guide_source_snapshot_hash', to_jsonb(t)->'locked_guide_source_snapshot_hash', 'locked_effective_project_submission_artifact_policy_id', to_jsonb(t)->'locked_effective_project_submission_artifact_policy_id', 'locked_effective_project_submission_artifact_policy_hash', to_jsonb(t)->'locked_effective_project_submission_artifact_policy_hash', 'locked_pre_submit_checker_policy_id', to_jsonb(t)->'locked_pre_submit_checker_policy_id', 'locked_pre_submit_checker_bundle_hash', to_jsonb(t)->'locked_pre_submit_checker_bundle_hash', 'locked_post_submit_checker_policy_id', to_jsonb(t)->'locked_post_submit_checker_policy_id', 'locked_post_submit_checker_policy_version', to_jsonb(t)->'locked_post_submit_checker_policy_version', 'locked_post_submit_checker_policy_hash', to_jsonb(t)->'locked_post_submit_checker_policy_hash', 'locked_review_policy_id', to_jsonb(t)->'locked_review_policy_id', 'locked_review_policy_generation', to_jsonb(t)->'locked_review_policy_generation', 'locked_review_policy_hash', to_jsonb(t)->'locked_review_policy_hash', 'locked_revision_policy_id', to_jsonb(t)->'locked_revision_policy_id', 'locked_revision_policy_generation', to_jsonb(t)->'locked_revision_policy_generation', 'locked_revision_policy_hash', to_jsonb(t)->'locked_revision_policy_hash', 'locked_contribution_policy_version_id', to_jsonb(t)->'locked_contribution_policy_version_id'))
             and (payload - array['references','manager_authority_facts','authorization_resource_digest']) = jsonb_build_object('locked_guide_version', payload->'locked_guide_version', 'locked_guide_source_snapshot_id', payload->'locked_guide_source_snapshot_id', 'locked_guide_source_snapshot_hash', payload->'locked_guide_source_snapshot_hash', 'locked_effective_project_submission_artifact_policy_id', payload->'locked_effective_project_submission_artifact_policy_id', 'locked_effective_project_submission_artifact_policy_hash', payload->'locked_effective_project_submission_artifact_policy_hash', 'locked_pre_submit_checker_policy_id', payload->'locked_pre_submit_checker_policy_id', 'locked_pre_submit_checker_bundle_hash', payload->'locked_pre_submit_checker_bundle_hash', 'locked_post_submit_checker_policy_id', payload->'locked_post_submit_checker_policy_id', 'locked_post_submit_checker_policy_version', payload->'locked_post_submit_checker_policy_version', 'locked_post_submit_checker_policy_hash', payload->'locked_post_submit_checker_policy_hash', 'locked_review_policy_id', payload->'locked_review_policy_id', 'locked_review_policy_generation', payload->'locked_review_policy_generation', 'locked_review_policy_hash', payload->'locked_review_policy_hash', 'locked_revision_policy_id', payload->'locked_revision_policy_id', 'locked_revision_policy_generation', payload->'locked_revision_policy_generation', 'locked_revision_policy_hash', payload->'locked_revision_policy_hash', 'locked_contribution_policy_version_id', payload->'locked_contribution_policy_version_id')
             and jsonb_typeof(payload->'locked_guide_version')='string' and btrim((payload->>'locked_guide_version'))<>''
             and (payload->>'locked_guide_source_snapshot_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and (payload->>'locked_guide_source_snapshot_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_effective_project_submission_artifact_policy_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and (payload->>'locked_effective_project_submission_artifact_policy_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_pre_submit_checker_policy_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and (payload->>'locked_pre_submit_checker_bundle_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_post_submit_checker_policy_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and jsonb_typeof(payload->'locked_post_submit_checker_policy_version')='string' and btrim((payload->>'locked_post_submit_checker_policy_version'))<>''
             and (payload->>'locked_post_submit_checker_policy_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_review_policy_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and jsonb_typeof(payload->'locked_review_policy_generation')='number' and (payload->>'locked_review_policy_generation') ~ '^[1-9][0-9]*$'
             and (payload->>'locked_review_policy_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_revision_policy_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             and jsonb_typeof(payload->'locked_revision_policy_generation')='number' and (payload->>'locked_revision_policy_generation') ~ '^[1-9][0-9]*$'
             and (payload->>'locked_revision_policy_hash') ~ '^sha256:[0-9a-f]{64}$'
             and (payload->>'locked_contribution_policy_version_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')), false) then
    raise exception 'task management audit mismatch' using errcode='23514';
  end if;
  return new;
end $_$;
CREATE FUNCTION public.guide_proposal_hash(value jsonb) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
        SELECT 'sha256:' || encode(sha256(convert_to(
          project_guide_projection_canonical_json(value), 'UTF8')), 'hex')
      $$;
CREATE FUNCTION public.guide_proposal_resource(target jsonb, operation text, actor uuid, link uuid, action text, request_digest text, output_digest text, prior_id uuid, prior_digest text) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    AS $$
        SELECT jsonb_build_object(
          'locator', jsonb_build_object('project_id',target->>'project_id','guide_id',target->>'guide_id',
            'compilation_id',target->>'compilation_id','actor_profile_id',actor,'identity_link_id',link,
            'action_id',action,'operation_id',operation),
          'finalization_id',target->>'finalization_id','artifact_policy_id',target->'artifact_policy_id',
          'setup_run_id',target->>'setup_run_id','setup_generation',target->'setup_generation',
          'target_digest',guide_proposal_hash(target),'request_digest',request_digest,
          'output_digest',output_digest,'current_approval_operation_id',prior_id,
          'current_approval_output_digest',prior_digest)
      $$;
CREATE FUNCTION public.outbox_delivery_outcome_valid(body text, digest text, claimed timestamp with time zone, expires timestamp with time zone, invoked timestamp with time zone) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    AS $$
        declare value jsonb; completed timestamptz; final_time timestamptz;
                retry_time timestamptz; outcome_state text; code text; unknown boolean;
        begin
          value := body::jsonb;
          if jsonb_typeof(value) <> 'object' or
             (select array_agg(k order by k) from jsonb_object_keys(value) k) <>
             array['delivery_state','error_code','finalized_at','invocation_unknown',
                   'invoked_at','next_attempt_at','receipt_completed_at'] or
             body <> project_guide_projection_canonical_json(value) or
             digest <> 'sha256:' || encode(sha256(convert_to(body, 'UTF8')), 'hex') or
             jsonb_typeof(value->'delivery_state') <> 'string' or
             jsonb_typeof(value->'invocation_unknown') <> 'boolean' or
             jsonb_typeof(value->'receipt_completed_at') <> 'string' then return false; end if;
          if (value->>'receipt_completed_at') is null or
             jsonb_typeof(value->'error_code') not in ('null','string') or
             jsonb_typeof(value->'finalized_at') not in ('null','string') or
             jsonb_typeof(value->'next_attempt_at') not in ('null','string') or
             jsonb_typeof(value->'invoked_at') not in ('null','string') then return false; end if;
          completed := (value->>'receipt_completed_at')::timestamptz;
          final_time := (value->>'finalized_at')::timestamptz;
          retry_time := (value->>'next_attempt_at')::timestamptz;
          outcome_state := value->>'delivery_state'; code := value->>'error_code';
          unknown := (value->>'invocation_unknown')::boolean;
          if completed < claimed or (invoked is not null and completed < invoked)
             or (value->>'invoked_at')::timestamptz is distinct from invoked then return false; end if;
          if invoked is null and (completed < expires or code not in
             ('LEASE_EXPIRED_BEFORE_INVOKE','ATTEMPTS_EXHAUSTED')) then return false; end if;
          if invoked is not null and not unknown and completed >= expires then return false; end if;
          if retry_time > completed + interval '1 day' then return false; end if;
          if unknown then
            return invoked is not null and outcome_state = 'dead_letter'
              and code = 'INVOKE_OUTCOME_UNKNOWN' and retry_time is null and final_time = completed;
          elsif outcome_state = 'acknowledged' then
            return invoked is not null and code is null and retry_time is null
              and final_time = completed;
          elsif outcome_state = 'retryable' then
            return final_time is null and retry_time > completed and
              ((invoked is null and code = 'LEASE_EXPIRED_BEFORE_INVOKE') or
               (invoked is not null and code = 'RETRY_REQUESTED'));
          elsif outcome_state = 'dead_letter' then
            return retry_time is null and final_time = completed and
              (code = 'ATTEMPTS_EXHAUSTED' or (invoked is not null and code = 'HANDLER_REJECTED'));
          end if;
          return false;
        exception when others then return false;
        end $$;
CREATE TABLE public.outbox_delivery_attempts (
    event_id uuid NOT NULL,
    claim_generation bigint NOT NULL,
    project_id uuid NOT NULL,
    payload_digest character varying(71) NOT NULL,
    claim_owner character varying(120) NOT NULL,
    claimed_at timestamp with time zone NOT NULL,
    claim_expires_at timestamp with time zone NOT NULL,
    stage character varying(16) NOT NULL,
    invoked_at timestamp with time zone,
    outcome_json character varying(2048),
    outcome_digest character varying(71),
    claim_decision_event_id uuid NOT NULL,
    invoke_decision_event_id uuid,
    finalize_decision_event_id uuid,
    CONSTRAINT ck_outbox_delivery_attempts_generation CHECK (((claim_generation >= 1) AND (claim_generation <= 2147483647))),
    CONSTRAINT ck_outbox_delivery_attempts_lease CHECK (((claim_expires_at > claimed_at) AND (claim_expires_at <= (claimed_at + '01:00:00'::interval)))),
    CONSTRAINT ck_outbox_delivery_attempts_outcome CHECK (((outcome_json IS NULL) OR COALESCE(public.outbox_delivery_outcome_valid((outcome_json)::text, (outcome_digest)::text, claimed_at, claim_expires_at, invoked_at), false))),
    CONSTRAINT ck_outbox_delivery_attempts_owner CHECK (((claim_owner)::text ~ '^[A-Za-z0-9._:-]{1,120}$'::text)),
    CONSTRAINT ck_outbox_delivery_attempts_payload_digest CHECK (((payload_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_outbox_delivery_attempts_phase_decisions CHECK (((((stage)::text = 'claimed'::text) AND (invoke_decision_event_id IS NULL) AND (finalize_decision_event_id IS NULL)) OR (((stage)::text = 'invoked'::text) AND (invoke_decision_event_id IS NOT NULL) AND (finalize_decision_event_id IS NULL)) OR (((stage)::text = 'completed'::text) AND (finalize_decision_event_id IS NOT NULL) AND (((invoked_at IS NULL) AND (invoke_decision_event_id IS NULL)) OR ((invoked_at IS NOT NULL) AND (invoke_decision_event_id IS NOT NULL)))))),
    CONSTRAINT ck_outbox_delivery_attempts_stage_shape CHECK (((((stage)::text = 'claimed'::text) AND (invoked_at IS NULL) AND (outcome_json IS NULL) AND (outcome_digest IS NULL)) OR (((stage)::text = 'invoked'::text) AND (invoked_at IS NOT NULL) AND (invoked_at >= claimed_at) AND (invoked_at < claim_expires_at) AND (outcome_json IS NULL) AND (outcome_digest IS NULL)) OR (((stage)::text = 'completed'::text) AND (outcome_json IS NOT NULL) AND (outcome_digest IS NOT NULL) AND ((invoked_at IS NULL) OR ((invoked_at >= claimed_at) AND (invoked_at < claim_expires_at))))))
);
CREATE FUNCTION public.outbox_dispatch_authority_digest(a public.outbox_delivery_attempts, phase text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
          select 'sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(
            jsonb_build_object(
              'domain','workstream.authorization.outbox_dispatch',
              'action_id','outbox.dispatch','permission_id','outbox.dispatch',
              'service_identity','workstream.outbox.dispatcher',
              'resource_type','outbox_event','resource_id',a.event_id::text,
              'scope_project_id',a.project_id,
              'facts',jsonb_build_object(
                'phase',phase,'event_id',a.event_id::text,'project_id',a.project_id,
                'payload_digest',a.payload_digest,'claim_generation',a.claim_generation,
                'claim_owner',a.claim_owner,'claimed_at',outbox_dispatch_utc(a.claimed_at),
                'claim_expires_at',outbox_dispatch_utc(a.claim_expires_at),
                'outcome_digest',case when phase='finalize' then a.outcome_digest else null end
              )
            )), 'UTF8')), 'hex')
        $$;
CREATE FUNCTION public.outbox_dispatch_utc(value timestamp with time zone) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
          select to_char(value at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') ||
            case when value = date_trunc('second', value) then ''
              else to_char(value at time zone 'UTC', '.US') end || '+00:00'
        $$;
CREATE TABLE public.admin_role_grants (
    id uuid NOT NULL,
    target_actor_profile_id uuid NOT NULL,
    role character varying(40) NOT NULL,
    scope_type character varying(16) NOT NULL,
    scope_project_id uuid,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    version smallint DEFAULT '1'::smallint NOT NULL,
    granted_by_actor_profile_id uuid,
    granted_by_system_principal character varying(100),
    granted_by_admin_role_grant_id uuid,
    grant_reason text NOT NULL,
    granted_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    revoked_by_actor_profile_id uuid,
    revoked_by_admin_role_grant_id uuid,
    revoked_reason text,
    revoked_at timestamp with time zone,
    CONSTRAINT ck_admin_role_grants_grant_attribution CHECK (((((granted_by_system_principal)::text = 'workstream:system:bootstrap'::text) AND (granted_by_actor_profile_id IS NULL) AND (granted_by_admin_role_grant_id IS NULL)) OR ((granted_by_system_principal IS NULL) AND (granted_by_actor_profile_id IS NOT NULL) AND (granted_by_admin_role_grant_id IS NOT NULL)))),
    CONSTRAINT ck_admin_role_grants_grant_reason CHECK (((octet_length(grant_reason) >= 1) AND (octet_length(grant_reason) <= 500))),
    CONSTRAINT ck_admin_role_grants_lifecycle CHECK (((((status)::text = 'active'::text) AND (version = 1) AND (revoked_by_actor_profile_id IS NULL) AND (revoked_by_admin_role_grant_id IS NULL) AND (revoked_reason IS NULL) AND (revoked_at IS NULL)) OR (((status)::text = 'revoked'::text) AND (version = 2) AND (revoked_by_actor_profile_id IS NOT NULL) AND (revoked_by_admin_role_grant_id IS NOT NULL) AND (revoked_reason IS NOT NULL) AND ((octet_length(revoked_reason) >= 1) AND (octet_length(revoked_reason) <= 500)) AND (revoked_at IS NOT NULL)))),
    CONSTRAINT ck_admin_role_grants_role CHECK (((role)::text = ANY (ARRAY[('access_administrator'::character varying)::text, ('operator'::character varying)::text, ('project_manager'::character varying)::text, ('finance_authority'::character varying)::text, ('audit_authority'::character varying)::text]))),
    CONSTRAINT ck_admin_role_grants_role_scope CHECK (((((scope_type)::text = 'system'::text) AND (scope_project_id IS NULL)) OR (((scope_type)::text = 'project'::text) AND (scope_project_id IS NOT NULL) AND ((role)::text <> ALL (ARRAY[('access_administrator'::character varying)::text, ('operator'::character varying)::text]))))),
    CONSTRAINT ck_admin_role_grants_scope_type CHECK (((scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text])))
);
CREATE TABLE public.project_guide_compilation_request_operations (
    operation_id uuid NOT NULL,
    request_id uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    setup_run_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    expected_predecessor_compilation_id uuid,
    request_facts_digest character varying(71) NOT NULL,
    attempt_id uuid NOT NULL,
    authorization_decision_event_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    request_trigger character varying(32) NOT NULL,
    source_mutation_operation_id uuid,
    source_authorization_decision_event_id uuid,
    CONSTRAINT ck_project_guide_compilation_request_operations_ck_comp_3034 CHECK (((request_facts_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_project_guide_compilation_request_operations_ck_comp_6f72 CHECK (((((request_trigger)::text = 'project_manager'::text) AND (source_mutation_operation_id IS NULL) AND (source_authorization_decision_event_id IS NULL)) OR (((request_trigger)::text = 'automatic_source_ready'::text) AND (source_mutation_operation_id IS NOT NULL) AND (source_authorization_decision_event_id IS NOT NULL)))),
    CONSTRAINT ck_project_guide_compilation_request_operations_ck_comp_bbca CHECK ((setup_generation > 0))
);
CREATE FUNCTION public.project_guide_compilation_request_authority_digest(op public.project_guide_compilation_request_operations, grant_row public.admin_role_grants) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
          select 'sha256:' || encode(sha256(convert_to(
            '{"action_id":"project.guide_compilation.request",' ||
            '"actor_profile_id":' || to_json(op.actor_profile_id)::text || ',' ||
            '"identity_link_id":' || to_json(op.identity_link_id)::text || ',' ||
            '"permission_id":"project.guide_compilation.request",' ||
            '"project_manager_grant_id":' || to_json(grant_row.id::text)::text || ',' ||
            '"request_facts_digest":' || to_json(op.request_facts_digest)::text || ',' ||
            '"resource_id":' || to_json(op.operation_id::text)::text || ',' ||
            '"resource_type":"project_guide_compilation_request",' ||
            '"scope_project_id":' || to_json(op.project_id)::text || '}',
            'UTF8')), 'hex')
        $$;
CREATE TABLE public.project_guide_compilation_attempts (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    setup_run_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    canonical_input_hash character varying(71) NOT NULL,
    guide_material_hash character varying(71) NOT NULL,
    pre_catalogue_id character varying(160) NOT NULL,
    pre_catalogue_version character varying(100) NOT NULL,
    pre_catalogue_schema_version character varying(160) NOT NULL,
    pre_catalogue_manifest_hash character varying(71) NOT NULL,
    post_catalogue_id character varying(160) NOT NULL,
    post_catalogue_version character varying(100) NOT NULL,
    post_catalogue_schema_version character varying(160) NOT NULL,
    post_catalogue_manifest_hash character varying(71) NOT NULL,
    agent_identity character varying(100) NOT NULL,
    agent_version character varying(100) NOT NULL,
    instruction_version character varying(100) NOT NULL,
    provider_idempotency_key uuid NOT NULL,
    status character varying(32) NOT NULL,
    canonical_result json,
    result_hash character varying(71),
    component_hashes json,
    failure_code character varying(100),
    persisted_compilation_id uuid,
    reserved_at timestamp with time zone DEFAULT now() NOT NULL,
    provider_uncertain_at timestamp with time zone,
    accepted_at timestamp with time zone,
    terminal_at timestamp with time zone,
    persisted_at timestamp with time zone,
    runtime_configuration json,
    runtime_configuration_hash character varying(71),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_00d8 CHECK ((((source_snapshot_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((canonical_input_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((guide_material_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((pre_catalogue_manifest_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((post_catalogue_manifest_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_31c4 CHECK (((component_hashes IS NULL) OR ((json_typeof(component_hashes) = 'object'::text) AND ((component_hashes)::jsonb = jsonb_build_object('sufficiency_hash', (component_hashes ->> 'sufficiency_hash'::text), 'artifact_policy_hash', (component_hashes ->> 'artifact_policy_hash'::text), 'requirement_inventory_hash', (component_hashes ->> 'requirement_inventory_hash'::text), 'pre_submit_hash', (component_hashes ->> 'pre_submit_hash'::text), 'post_submit_hash', (component_hashes ->> 'post_submit_hash'::text), 'capability_suggestions_hash', (component_hashes ->> 'capability_suggestions_hash'::text), 'setup_notes_hash', (component_hashes ->> 'setup_notes_hash'::text))) AND COALESCE(((component_hashes ->> 'sufficiency_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'artifact_policy_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'requirement_inventory_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'pre_submit_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'post_submit_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'capability_suggestions_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'setup_notes_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false)))),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_444c CHECK (((((status)::text = 'compilation_reserved'::text) AND (provider_uncertain_at IS NULL) AND (accepted_at IS NULL) AND (terminal_at IS NULL) AND (persisted_at IS NULL) AND (canonical_result IS NULL) AND (result_hash IS NULL) AND (component_hashes IS NULL) AND (failure_code IS NULL) AND (persisted_compilation_id IS NULL)) OR (((status)::text = 'compilation_provider_uncertain'::text) AND (provider_uncertain_at IS NOT NULL) AND (accepted_at IS NULL) AND (terminal_at IS NULL) AND (persisted_at IS NULL) AND (canonical_result IS NULL) AND (result_hash IS NULL) AND (component_hashes IS NULL) AND (failure_code IS NULL) AND (persisted_compilation_id IS NULL)) OR (((status)::text = 'provider_result_accepted'::text) AND (accepted_at IS NOT NULL) AND (terminal_at IS NULL) AND (persisted_at IS NULL) AND (canonical_result IS NOT NULL) AND (result_hash IS NOT NULL) AND (component_hashes IS NOT NULL) AND (failure_code IS NULL) AND (persisted_compilation_id IS NULL)) OR (((status)::text = 'compilation_persisted'::text) AND (accepted_at IS NOT NULL) AND (persisted_at IS NOT NULL) AND (terminal_at IS NULL) AND (canonical_result IS NOT NULL) AND (result_hash IS NOT NULL) AND (component_hashes IS NOT NULL) AND (failure_code IS NULL) AND (persisted_compilation_id IS NOT NULL)) OR (((status)::text = 'compilation_invalid_terminal'::text) AND (terminal_at IS NOT NULL) AND (accepted_at IS NULL) AND (persisted_at IS NULL) AND (canonical_result IS NULL) AND (result_hash IS NULL) AND (component_hashes IS NULL) AND (persisted_compilation_id IS NULL) AND ((failure_code)::text = ANY (ARRAY[('schema_invalid'::character varying)::text, ('unsafe_text'::character varying)::text, ('hash_mismatch'::character varying)::text, ('context_mismatch'::character varying)::text]))))),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_513e CHECK ((setup_generation > 0)),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_6057 CHECK (((canonical_result IS NULL) OR (octet_length((canonical_result)::text) <= 4194304))),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_6609 CHECK (((result_hash IS NULL) OR ((result_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_project_guide_compilation_attempts_ck_compilation_at_6c82 CHECK (((status)::text = ANY (ARRAY[('compilation_reserved'::character varying)::text, ('compilation_provider_uncertain'::character varying)::text, ('provider_result_accepted'::character varying)::text, ('compilation_invalid_terminal'::character varying)::text, ('compilation_persisted'::character varying)::text])))
);
CREATE FUNCTION public.project_guide_compilation_request_facts_digest(op public.project_guide_compilation_request_operations, attempt public.project_guide_compilation_attempts) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
          select 'sha256:' || encode(sha256(convert_to(
            '{"domain":"workstream.project_guide_compilation.facts.v1","facts":{' ||
            '"agent_identity":' || to_json(attempt.agent_identity)::text || ',' ||
            '"agent_version":' || to_json(attempt.agent_version)::text || ',' ||
            '"canonical_input_hash":' || to_json(attempt.canonical_input_hash)::text || ',' ||
            '"expected_predecessor_compilation_id":' ||
              coalesce(to_json(op.expected_predecessor_compilation_id::text)::text, 'null') || ',' ||
            '"guide_id":' || to_json(op.guide_id)::text || ',' ||
            '"guide_material_hash":' || to_json(attempt.guide_material_hash)::text || ',' ||
            '"guide_version":' || to_json(attempt.guide_version)::text || ',' ||
            '"idempotency_key":' || to_json(op.idempotency_key::text)::text || ',' ||
            '"instruction_version":' || to_json(attempt.instruction_version)::text || ',' ||
            '"operation_id":' || to_json(op.operation_id::text)::text || ',' ||
            '"post_catalogue_id":' || to_json(attempt.post_catalogue_id)::text || ',' ||
            '"post_catalogue_manifest_hash":' || to_json(attempt.post_catalogue_manifest_hash)::text || ',' ||
            '"post_catalogue_schema_version":' || to_json(attempt.post_catalogue_schema_version)::text || ',' ||
            '"post_catalogue_version":' || to_json(attempt.post_catalogue_version)::text || ',' ||
            '"pre_catalogue_id":' || to_json(attempt.pre_catalogue_id)::text || ',' ||
            '"pre_catalogue_manifest_hash":' || to_json(attempt.pre_catalogue_manifest_hash)::text || ',' ||
            '"pre_catalogue_schema_version":' || to_json(attempt.pre_catalogue_schema_version)::text || ',' ||
            '"pre_catalogue_version":' || to_json(attempt.pre_catalogue_version)::text || ',' ||
            '"project_id":' || to_json(op.project_id)::text || ',' ||
            '"request_id":' || to_json(op.request_id::text)::text || ',' ||
            '"setup_generation":' || op.setup_generation::text || ',' ||
            '"setup_run_id":' || to_json(op.setup_run_id)::text || ',' ||
            '"source_snapshot_hash":' || to_json(attempt.source_snapshot_hash)::text || ',' ||
            '"source_snapshot_id":' || to_json(op.source_snapshot_id)::text || '}}',
            'UTF8')), 'hex')
        $$;
CREATE TABLE public.project_guide_setup_finalizations (
    id uuid NOT NULL,
    operation_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    setup_run_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    celery_task_id character varying(155) NOT NULL,
    source_state_digest character varying(71) NOT NULL,
    attempt_id uuid NOT NULL,
    request_operation_id uuid NOT NULL,
    provider_idempotency_key uuid NOT NULL,
    compilation_id uuid NOT NULL,
    canonical_input_hash character varying(71) NOT NULL,
    result_hash character varying(71) NOT NULL,
    result_schema_version character varying(100) NOT NULL,
    compilation_agent_name character varying(100) NOT NULL,
    compilation_agent_version character varying(100) NOT NULL,
    component_hashes json NOT NULL,
    sufficiency_operation_id uuid NOT NULL,
    sufficiency_report_id uuid NOT NULL,
    sufficiency_output_digest character varying(71) NOT NULL,
    artifact_policy_operation_id uuid,
    artifact_policy_id uuid,
    artifact_policy_output_digest character varying(71),
    result_classification character varying(40) NOT NULL,
    setup_outcome character varying(40) NOT NULL,
    facts_digest character varying(71) NOT NULL,
    authority_resource_digest character varying(71) NOT NULL,
    authorization_decision_event_id uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    service_identity character varying(160) NOT NULL,
    action_id character varying(160) NOT NULL,
    permission_id character varying(120) NOT NULL,
    scope_type character varying(16) NOT NULL,
    scope_project_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT transaction_timestamp() NOT NULL,
    CONSTRAINT ck_project_guide_setup_finalizations_ck_finalization_authority CHECK (((setup_generation > 0) AND ((service_identity)::text = 'workstream.project.setup'::text) AND ((action_id)::text = 'project.setup_run.update'::text) AND ((permission_id)::text = 'project.guide.manage'::text) AND ((scope_type)::text = 'project'::text) AND ((scope_project_id)::text = (project_id)::text))),
    CONSTRAINT ck_project_guide_setup_finalizations_ck_finalization_components CHECK (((json_typeof(component_hashes) = 'object'::text) AND ((component_hashes)::jsonb = jsonb_build_object('sufficiency_hash', (component_hashes ->> 'sufficiency_hash'::text), 'artifact_policy_hash', (component_hashes ->> 'artifact_policy_hash'::text), 'requirement_inventory_hash', (component_hashes ->> 'requirement_inventory_hash'::text), 'pre_submit_hash', (component_hashes ->> 'pre_submit_hash'::text), 'post_submit_hash', (component_hashes ->> 'post_submit_hash'::text), 'capability_suggestions_hash', (component_hashes ->> 'capability_suggestions_hash'::text), 'setup_notes_hash', (component_hashes ->> 'setup_notes_hash'::text))) AND COALESCE(((component_hashes ->> 'sufficiency_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'artifact_policy_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'requirement_inventory_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'pre_submit_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'post_submit_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'capability_suggestions_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'setup_notes_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false))),
    CONSTRAINT ck_project_guide_setup_finalizations_ck_finalization_hashes CHECK ((((source_snapshot_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((source_state_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((canonical_input_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((result_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((sufficiency_output_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((facts_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((authority_resource_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((artifact_policy_output_digest IS NULL) OR ((artifact_policy_output_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)))),
    CONSTRAINT ck_project_guide_setup_finalizations_ck_finalization_pr_ac00 CHECK (((((result_classification)::text = 'guide_blocked'::text) AND ((setup_outcome)::text = 'sufficiency_blocked'::text) AND (artifact_policy_operation_id IS NULL) AND (artifact_policy_id IS NULL) AND (artifact_policy_output_digest IS NULL)) OR (((result_classification)::text = ANY ((ARRAY['draft_ready'::character varying, 'draft_ready_with_warnings'::character varying])::text[])) AND ((setup_outcome)::text = 'policy_draft_ready'::text) AND (artifact_policy_operation_id IS NOT NULL) AND (artifact_policy_id IS NOT NULL) AND (artifact_policy_output_digest IS NOT NULL))))
);
CREATE FUNCTION public.project_guide_finalization_authority_digest(item public.project_guide_setup_finalizations) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
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
CREATE FUNCTION public.project_guide_finalization_digest(item public.project_guide_setup_finalizations) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
      select 'sha256:' || encode(sha256(convert_to(
        project_guide_projection_canonical_json(jsonb_build_object(
          'domain','workstream.project_guide_setup_finalization.facts.v1',
          'facts',project_guide_finalization_facts(item))), 'UTF8')), 'hex')
    $$;
CREATE FUNCTION public.project_guide_finalization_facts(item public.project_guide_setup_finalizations) RETURNS jsonb
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
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
CREATE TABLE public.project_setup_runs (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    celery_task_id character varying(155),
    status character varying(50) NOT NULL,
    current_step character varying(100) NOT NULL,
    output_sufficiency_report_id uuid,
    output_submission_artifact_policy_id uuid,
    error_code character varying(100),
    error_summary text,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    output_post_submit_checker_policy_id uuid,
    post_submit_derivation_summary json,
    setup_generation bigint NOT NULL,
    authorized_by_actor_profile_id uuid,
    authorized_via_identity_link_id uuid,
    authorized_by_admin_role_grant_id uuid,
    authorization_scope_type character varying(16),
    authorization_scope_project_id uuid,
    authorization_action_id character varying(160),
    authorization_decision_event_id uuid,
    error_artifact_incident_id uuid,
    retained_continuation_verification_job_id uuid,
    retained_continuation_started_at timestamp with time zone,
    documents_ready_at timestamp with time zone,
    CONSTRAINT ck_project_setup_runs_ck_project_setup_runs_generation_positive CHECK ((setup_generation > 0)),
    CONSTRAINT ck_project_setup_runs_ck_project_setup_runs_status CHECK (((status)::text = ANY ((ARRAY['awaiting_documents'::character varying, 'correction_requested'::character varying, 'queued'::character varying, 'dispatch_pending'::character varying, 'enqueue_failed'::character varying, 'enqueue_identity_mismatch'::character varying, 'running_sufficiency_agent'::character varying, 'sufficiency_blocked'::character varying, 'running_policy_derivation_agent'::character varying, 'policy_draft_ready'::character varying, 'running_post_submit_derivation_agent'::character varying, 'post_submit_setup_blocked'::character varying, 'post_submit_policy_compiled'::character varying, 'setup_blocked'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT ck_project_setup_runs_setup_run_authority_shape CHECK ((((authorized_by_actor_profile_id IS NULL) AND (authorized_via_identity_link_id IS NULL) AND (authorized_by_admin_role_grant_id IS NULL) AND (authorization_scope_type IS NULL) AND (authorization_scope_project_id IS NULL) AND (authorization_action_id IS NULL) AND (authorization_decision_event_id IS NULL)) OR ((authorized_by_actor_profile_id IS NOT NULL) AND (authorized_via_identity_link_id IS NOT NULL) AND (authorized_by_admin_role_grant_id IS NOT NULL) AND ((authorization_scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text])) AND ((((authorization_scope_type)::text = 'system'::text) AND (authorization_scope_project_id IS NULL)) OR (((authorization_scope_type)::text = 'project'::text) AND ((authorization_scope_project_id)::text = (project_id)::text))) AND (((authorization_action_id)::text = 'project.guide_source_snapshot.create'::text) OR ((authorization_action_id)::text = 'project.guide_compilation.correction.request'::text)) AND (authorization_decision_event_id IS NOT NULL))))
);
CREATE FUNCTION public.project_guide_finalization_source_digest(item public.project_setup_runs) RETURNS text
    LANGUAGE sql STABLE STRICT
    AS $_$
      select 'sha256:' || encode(sha256(convert_to(
        project_guide_projection_canonical_json(jsonb_build_object(
          'domain','workstream.project_guide_projection.source_state.v1',
          'facts',jsonb_build_object(
            'celery_task_id',item.celery_task_id,
            'documents_ready_at',case when item.documents_ready_at is null then null
              else regexp_replace(to_char(item.documents_ready_at at time zone 'UTC',
                'YYYY-MM-DD"T"HH24:MI:SS.US'), '\.000000$', '') || '+00:00' end,

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
    $_$;
CREATE TABLE public.project_guide_component_projection_operations (
    operation_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    component character varying(40) NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    setup_run_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    celery_task_id character varying(155) NOT NULL,
    source_state_digest character varying(71) NOT NULL,
    attempt_id uuid NOT NULL,
    request_operation_id uuid NOT NULL,
    provider_idempotency_key uuid NOT NULL,
    compilation_id uuid NOT NULL,
    result_hash character varying(71) NOT NULL,
    component_hash character varying(71) NOT NULL,
    result_schema_version character varying(100) NOT NULL,
    compilation_agent_name character varying(100) NOT NULL,
    compilation_agent_version character varying(100) NOT NULL,
    material_sha256 character varying(71),
    material_byte_count bigint NOT NULL,
    prior_operation_id uuid,
    prior_output_id uuid,
    prior_output_digest character varying(71),
    output_id uuid NOT NULL,
    report_id uuid,
    policy_id uuid,
    output_digest character varying(71) NOT NULL,
    facts_digest character varying(71) NOT NULL,
    authority_resource_digest character varying(71) NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    service_identity character varying(160) NOT NULL,
    action_id character varying(160) NOT NULL,
    permission_id character varying(120) NOT NULL,
    authorization_decision_event_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_guide_component_projection_operations_ck_pro_3806 CHECK (((component)::text = ANY ((ARRAY['guide_sufficiency'::character varying, 'submission_artifact_policy'::character varying])::text[]))),
    CONSTRAINT ck_project_guide_component_projection_operations_ck_pro_3fc4 CHECK ((((source_snapshot_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((source_state_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((result_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((component_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((output_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((facts_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((authority_resource_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((material_sha256 IS NULL) OR ((material_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)))),
    CONSTRAINT ck_project_guide_component_projection_operations_ck_pro_9b04 CHECK (((setup_generation > 0) AND (material_byte_count >= 0))),
    CONSTRAINT ck_project_guide_component_projection_operations_ck_pro_eef5 CHECK (((((component)::text = 'guide_sufficiency'::text) AND (prior_operation_id IS NULL) AND (prior_output_id IS NULL) AND (prior_output_digest IS NULL) AND (report_id IS NOT NULL) AND (policy_id IS NULL) AND (material_sha256 IS NOT NULL)) OR (((component)::text = 'submission_artifact_policy'::text) AND (prior_operation_id IS NOT NULL) AND (prior_output_id IS NOT NULL) AND (prior_output_digest IS NOT NULL) AND (report_id IS NULL) AND (policy_id IS NOT NULL) AND (material_sha256 IS NULL))))
);
CREATE FUNCTION public.project_guide_projection_authority_digest(item public.project_guide_component_projection_operations) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
          select 'sha256:' || encode(sha256(convert_to(
            '{"domain":' || to_json(case
              when item.component='guide_sufficiency' then
                'workstream.project_guide_sufficiency_projection.authority.v1'
              else
                'workstream.project_submission_artifact_policy_projection.authority.v1'
              end)::text || ',"facts":{' ||
            '"action_id":' || to_json(item.action_id)::text || ',' ||
            '"actor_profile_id":' || to_json(item.actor_profile_id)::text || ',' ||
            '"facts_digest":' || to_json(item.facts_digest)::text || ',' ||
            '"identity_link_id":' || to_json(item.identity_link_id)::text || ',' ||
            '"permission_id":' || to_json(item.permission_id)::text || ',' ||
            '"resource_id":' || to_json(item.operation_id::text)::text || ',' ||
            '"resource_type":' || to_json(case
              when item.component='guide_sufficiency' then
                'project_guide_sufficiency_projection'
              else 'project_submission_artifact_policy_projection' end)::text || ',' ||
            '"scope_project_id":' || to_json(item.project_id)::text || ',' ||
            '"service_identity":' || to_json(item.service_identity)::text || '}}',
            'UTF8')), 'hex')
        $$;
CREATE FUNCTION public.project_guide_projection_business_digest(item public.project_guide_component_projection_operations) RETURNS text
    LANGUAGE plpgsql STABLE STRICT
    AS $$
        declare payload jsonb;
        declare output_domain text;
        begin
          if item.component='guide_sufficiency' then
            output_domain := 'workstream.project_guide_sufficiency_projection.output.v1';
            select jsonb_build_object(
              'id', report.id,
              'project_id', report.project_id,
              'guide_id', report.guide_id,
              'guide_version', report.guide_version,
              'source_snapshot_id', report.source_snapshot_id,
              'source_snapshot_hash', report.source_snapshot_hash,
              'status', report.status,
              'findings', report.findings::jsonb,
              'summary', report.summary,
              'agent_name', report.agent_name,
              'agent_version', report.agent_version,
              'project_setup_run_id', report.project_setup_run_id,
              'setup_generation', report.setup_generation,
              'agent_material_sha256', report.agent_material_sha256,
              'agent_material_byte_count', report.agent_material_byte_count,
              'created_by', report.created_by
            ) into payload from guide_sufficiency_reports report
              where report.id=item.report_id;
          elsif item.component='submission_artifact_policy' then
            output_domain :=
              'workstream.project_submission_artifact_policy_projection.output.v1';
            select jsonb_build_object(
              'id', policy.id,
              'project_id', policy.project_id,
              'guide_id', policy.guide_id,
              'guide_version', policy.guide_version,
              'source_snapshot_id', policy.source_snapshot_id,
              'source_snapshot_hash', policy.source_snapshot_hash,
              'policy_version', policy.policy_version,
              'lifecycle_status', policy.lifecycle_status,
              'policy_body', policy.policy_body::jsonb,
              'policy_hash', policy.policy_hash,
              'derivation_source', policy.derivation_source,
              'source_material_refs', policy.source_material_refs::jsonb,
              'derivation_agent_name', policy.derivation_agent_name,
              'derivation_agent_version', policy.derivation_agent_version,
              'created_by', policy.created_by,
              'change_summary', policy.change_summary
            ) into payload from submission_artifact_policies policy
              where policy.id=item.policy_id;
          end if;
          if payload is null then
            return null;
          end if;
          return 'sha256:' || encode(sha256(convert_to(
            project_guide_projection_canonical_json(jsonb_build_object(
              'domain', output_domain,
              'facts', payload
            )), 'UTF8')), 'hex');
        end; $$;
CREATE FUNCTION public.project_guide_projection_canonical_json(value jsonb) RETURNS text
    LANGUAGE plpgsql IMMUTABLE STRICT
    AS $$
        declare encoded text;
        begin
          case jsonb_typeof(value)
            when 'object' then
              select '{' || coalesce(string_agg(
                to_json(item_key)::text || ':' ||
                  project_guide_projection_canonical_json(item_value),
                ',' order by item_key collate "C"
              ), '') || '}' into encoded
                from jsonb_each(value) as items(item_key, item_value);
              return encoded;
            when 'array' then
              select '[' || coalesce(string_agg(
                project_guide_projection_canonical_json(item_value),
                ',' order by item_order
              ), '') || ']' into encoded
                from jsonb_array_elements(value) with ordinality
                  as items(item_value, item_order);
              return encoded;
            else
              return value::text;
          end case;
        end; $$;
CREATE FUNCTION public.project_guide_projection_facts_digest(item public.project_guide_component_projection_operations) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
          select 'sha256:' || encode(sha256(convert_to(
            case when item.component='guide_sufficiency' then
              '{"domain":"workstream.project_guide_sufficiency_projection.facts.v1","facts":{' ||
              '"attempt_id":' || to_json(item.attempt_id::text)::text || ',' ||
              '"celery_task_id":' || to_json(item.celery_task_id)::text || ',' ||
              '"compilation_agent_name":' || to_json(item.compilation_agent_name)::text || ',' ||
              '"compilation_agent_version":' || to_json(item.compilation_agent_version)::text || ',' ||
              '"compilation_id":' || to_json(item.compilation_id::text)::text || ',' ||
              '"component_hash":' || to_json(item.component_hash)::text || ',' ||
              '"guide_id":' || to_json(item.guide_id)::text || ',' ||
              '"guide_version":' || to_json(item.guide_version)::text || ',' ||
              '"material_byte_count":' || item.material_byte_count::text || ',' ||
              '"material_sha256":' || to_json(item.material_sha256)::text || ',' ||
              '"project_id":' || to_json(item.project_id)::text || ',' ||
              '"provider_idempotency_key":' ||
                to_json(item.provider_idempotency_key::text)::text || ',' ||
              '"report_content_digest":' || to_json(item.output_digest)::text || ',' ||
              '"report_id":' || to_json(item.output_id::text)::text || ',' ||
              '"request_operation_id":' ||
                to_json(item.request_operation_id::text)::text || ',' ||
              '"result_hash":' || to_json(item.result_hash)::text || ',' ||
              '"result_schema_version":' || to_json(item.result_schema_version)::text || ',' ||
              '"setup_generation":' || item.setup_generation::text || ',' ||
              '"setup_run_id":' || to_json(item.setup_run_id)::text || ',' ||
              '"source_snapshot_hash":' || to_json(item.source_snapshot_hash)::text || ',' ||
              '"source_snapshot_id":' || to_json(item.source_snapshot_id)::text || ',' ||
              '"source_state_digest":' || to_json(item.source_state_digest)::text || '}}'
            else
              '{"domain":"workstream.project_submission_artifact_policy_projection.facts.v1","facts":{' ||
              '"attempt_id":' || to_json(item.attempt_id::text)::text || ',' ||
              '"celery_task_id":' || to_json(item.celery_task_id)::text || ',' ||
              '"compilation_agent_name":' || to_json(item.compilation_agent_name)::text || ',' ||
              '"compilation_agent_version":' || to_json(item.compilation_agent_version)::text || ',' ||
              '"compilation_id":' || to_json(item.compilation_id::text)::text || ',' ||
              '"component_hash":' || to_json(item.component_hash)::text || ',' ||
              '"guide_id":' || to_json(item.guide_id)::text || ',' ||
              '"guide_version":' || to_json(item.guide_version)::text || ',' ||
              '"policy_content_digest":' || to_json(item.output_digest)::text || ',' ||
              '"policy_id":' || to_json(item.output_id::text)::text || ',' ||
              '"prior_operation_id":' || to_json(item.prior_operation_id::text)::text || ',' ||
              '"project_id":' || to_json(item.project_id)::text || ',' ||
              '"provider_idempotency_key":' ||
                to_json(item.provider_idempotency_key::text)::text || ',' ||
              '"request_operation_id":' ||
                to_json(item.request_operation_id::text)::text || ',' ||
              '"result_hash":' || to_json(item.result_hash)::text || ',' ||
              '"result_schema_version":' || to_json(item.result_schema_version)::text || ',' ||
              '"setup_generation":' || item.setup_generation::text || ',' ||
              '"setup_run_id":' || to_json(item.setup_run_id)::text || ',' ||
              '"source_snapshot_hash":' || to_json(item.source_snapshot_hash)::text || ',' ||
              '"source_snapshot_id":' || to_json(item.source_snapshot_id)::text || ',' ||
              '"source_state_digest":' || to_json(item.source_state_digest)::text || ',' ||
              '"sufficiency_report_digest":' || to_json(item.prior_output_digest)::text || ',' ||
              '"sufficiency_report_id":' || to_json(item.prior_output_id::text)::text || '}}'
            end,
            'UTF8')), 'hex')
        $$;
CREATE FUNCTION public.project_guide_task_examples_hash(examples jsonb) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$
        select 'sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(
          jsonb_build_object('domain','workstream.project_guide.task_examples','task_examples',examples)
        ),'UTF8')),'hex')
      $$;
CREATE FUNCTION public.project_guide_task_examples_valid(examples jsonb) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    AS $$
      declare item jsonb; label jsonb; whitespace text;
      begin
        if examples is null or jsonb_typeof(examples) is distinct from 'array' then return false; end if;
        if jsonb_array_length(examples) not between 1 and 100
           or octet_length(convert_to(project_guide_projection_canonical_json(examples),'UTF8')) > 131072
           then return false; end if;
        select string_agg(chr(code),'') into whitespace from unnest(array[
          9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,
          8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288]) code;
        for item in select value from jsonb_array_elements(examples) loop
          if jsonb_typeof(item) is distinct from 'object'
             or not (item ?& array['content','title','labels'])
             or item - array['content','title','labels'] <> '{}'::jsonb
             or jsonb_typeof(item->'content') is distinct from 'string'
             or length(item->>'content') not between 1 and 65536
             or btrim(item->>'content',whitespace) = ''
             or (item->'title' <> 'null'::jsonb and (
                jsonb_typeof(item->'title') is distinct from 'string' or length(item->>'title') > 500))
             or jsonb_typeof(item->'labels') is distinct from 'array'
             then return false; end if;
          if jsonb_array_length(item->'labels') > 20 then return false; end if;
          for label in select value from jsonb_array_elements(item->'labels') loop
            if jsonb_typeof(label) is distinct from 'string'
               or length(label #>> '{}') not between 1 and 100 then return false; end if;
          end loop;
        end loop;
        return true;
      end $$;
CREATE FUNCTION public.project_role_availability_is_safe(value jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE STRICT
    AS $$
          select jsonb_typeof(value)='object' and
            (select count(*)=3 from jsonb_object_keys(value)) and
            value ?& array['availability','reference_ids','unavailable_reason'] and
            project_role_reference_array_is_safe(value->'reference_ids',false) and (
              (value->>'availability'='available' and jsonb_array_length(value->'reference_ids')>0
                and value->'unavailable_reason'='null'::jsonb) or
              (value->>'availability'='unavailable' and jsonb_array_length(value->'reference_ids')=0
                and value->>'unavailable_reason' in ('not_collected','source_unavailable','no_record'))
            )
        $$;
CREATE FUNCTION public.project_role_reason_is_safe(value text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE STRICT
    AS $$
        declare point integer; index integer;
        begin
          if octet_length(value) not between 1 and 500 or value <> btrim(value, (E' \t\n\r\f\013'||chr(28)||chr(29)||chr(30)||chr(31)||chr(133)||chr(160)||chr(5760)||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||chr(8197)||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)||chr(8233)||chr(8239)||chr(8287)||chr(12288))) then return false; end if;
          for index in 1..char_length(value) loop
            point := ascii(substr(value,index,1));
            if point between 0 and 31 or point between 127 and 159
               or point in (173,1536,1537,1538,1539,1757,1807,6068,6069,6070,6071,6072,6073,6158,8203,8204,8205,8206,8207,8234,8235,8236,8237,8238,8288,8289,8290,8291,8292,8293,8294,8295,8296,8297,8298,8299,8300,8301,8302,8303,65279) then
              return false;
            end if;
          end loop;
          return true;
        end $$;
CREATE FUNCTION public.project_role_reference_array_is_safe(value jsonb, uuid_only boolean) RETURNS boolean
    LANGUAGE sql IMMUTABLE STRICT
    AS $_$
          select jsonb_typeof(value)='array' and jsonb_array_length(value)<=20
            and not exists (
              select 1 from jsonb_array_elements(value) item
              where jsonb_typeof(item)<>'string' or
                case when uuid_only then not (item #>> '{}') ~
                  '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                else not project_role_reference_token_is_safe(item #>> '{}') end
            )
        $_$;
CREATE FUNCTION public.project_role_reference_token_is_safe(value text) RETURNS boolean
    LANGUAGE sql IMMUTABLE STRICT
    AS $_$
          select value ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$' and strpos(value, '://')=0
        $_$;
CREATE FUNCTION public.protect_assignment_contribution_stamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE task_stamp uuid;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT locked_contribution_policy_version_id INTO task_stamp FROM workstream_tasks
        WHERE id=NEW.task_id AND project_id=NEW.project_id FOR SHARE;
        IF task_stamp IS NULL OR task_stamp IS DISTINCT FROM
           NEW.submitter_contribution_policy_version_id THEN
            RAISE EXCEPTION 'assignment contribution stamp differs from task';
        END IF;
    ELSIF ROW(NEW.id, NEW.task_id, NEW.project_id, NEW.contributor_id,
              NEW.submitter_contribution_policy_version_id) IS DISTINCT FROM
              ROW(OLD.id, OLD.task_id, OLD.project_id, OLD.contributor_id,
                  OLD.submitter_contribution_policy_version_id) THEN
        RAISE EXCEPTION 'assignment contribution identity is immutable';
    END IF;
    RETURN NEW;
END $$;
CREATE FUNCTION public.protect_guide_proposal_content() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      DECLARE permitted text[];
      BEGIN
        IF tg_table_name='submission_artifact_policies' THEN
          IF old.derivation_source IS DISTINCT FROM 'unified_compilation' THEN RETURN new; END IF;
          permitted:=ARRAY['lifecycle_status','approved_by_role','approved_by_actor','approved_at',
            'approved_by_actor_profile_id','approved_via_identity_link_id','approved_by_admin_role_grant_id',
            'approval_scope_type','approval_scope_project_id','approval_action_id','approval_decision_event_id',
            'supersedes_policy_id','superseded_at','updated_at'];
          IF old.approval_action_id IS NOT NULL THEN
            permitted:=ARRAY['lifecycle_status','superseded_at','updated_at'];
          END IF;
        ELSE
          IF old.creation_action_id IS DISTINCT FROM 'project.submission_artifact_policy.approve' THEN RETURN new; END IF;
          permitted:=ARRAY['lifecycle_status','superseded_at','updated_at'];
        END IF;
        IF (to_jsonb(new)-permitted) IS DISTINCT FROM (to_jsonb(old)-permitted) THEN
          RAISE EXCEPTION 'unified proposal content is immutable' USING ERRCODE='23514';
        END IF;
        RETURN new;
      END $$;
CREATE FUNCTION public.protect_submission_contribution_stamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF ROW(NEW.id, NEW.task_id, NEW.task_assignment_id, NEW.contributor_id, NEW.contribution_policy_version_id)
       IS DISTINCT FROM ROW(OLD.id, OLD.task_id, OLD.task_assignment_id, OLD.contributor_id, OLD.contribution_policy_version_id)
       OR (OLD.submission_bundle_admission_id IS NOT NULL AND
           ROW(NEW.task_assignment_id, NEW.submission_bundle_admission_id,
               NEW.artifact_binding_id, NEW.artifact_content_id) IS DISTINCT FROM
           ROW(OLD.task_assignment_id, OLD.submission_bundle_admission_id,
               OLD.artifact_binding_id, OLD.artifact_content_id)) THEN
        RAISE EXCEPTION 'submission contribution identity is immutable';
    END IF;
    RETURN NEW;
END $$;
CREATE FUNCTION public.protect_submission_policy_approval_provenance() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if old.approval_action_id is not null and
             (new.approved_by_actor_profile_id,new.approved_via_identity_link_id,
              new.approved_by_admin_role_grant_id,new.approval_scope_type,
              new.approval_scope_project_id,new.approval_action_id,
              new.approval_decision_event_id)
             is distinct from
             (old.approved_by_actor_profile_id,old.approved_via_identity_link_id,
              old.approved_by_admin_role_grant_id,old.approval_scope_type,
              old.approval_scope_project_id,old.approval_action_id,
              old.approval_decision_event_id) then
            raise exception 'submission-policy approval provenance is immutable'
              using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.protect_submission_policy_creation_provenance() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if old.creation_action_id is not null and
             (new.created_by_actor_profile_id,new.created_via_identity_link_id,
              new.created_by_admin_role_grant_id,new.created_by_service_identity,
              new.creation_scope_type,new.creation_scope_project_id,
              new.creation_action_id,new.creation_decision_event_id)
             is distinct from
             (old.created_by_actor_profile_id,old.created_via_identity_link_id,
              old.created_by_admin_role_grant_id,old.created_by_service_identity,
              old.creation_scope_type,old.creation_scope_project_id,
              old.creation_action_id,old.creation_decision_event_id) then
            raise exception 'submission-policy creation provenance is immutable'
              using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.protect_submission_policy_output_provenance() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if old.creation_action_id is not null and
             (new.created_by_actor_profile_id,new.created_via_identity_link_id,
              new.created_by_admin_role_grant_id,new.creation_scope_type,
              new.creation_scope_project_id,new.creation_action_id,
              new.creation_decision_event_id)
             is distinct from
             (old.created_by_actor_profile_id,old.created_via_identity_link_id,
              old.created_by_admin_role_grant_id,old.creation_scope_type,
              old.creation_scope_project_id,old.creation_action_id,
              old.creation_decision_event_id) then
            raise exception 'submission-policy output provenance is immutable'
              using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.protect_task_command_receipt() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            IF TG_OP <> 'UPDATE' THEN
                RAISE EXCEPTION 'task command receipts cannot be removed' USING ERRCODE='23514';
            END IF;
            IF NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
            IF OLD.status <> 'pending' OR NEW.status <> 'committed' OR
               ROW(NEW.id, NEW.actor_profile_id, NEW.action_id, NEW.idempotency_key,
                   NEW.request_digest, NEW.task_id, NEW.created_at) IS DISTINCT FROM
               ROW(OLD.id, OLD.actor_profile_id, OLD.action_id, OLD.idempotency_key,
                   OLD.request_digest, OLD.task_id, OLD.created_at) THEN
                RAISE EXCEPTION 'task command receipt is immutable' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
CREATE FUNCTION public.protect_task_contribution_stamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'draft' OR NEW.locked_contribution_policy_version_id IS NOT NULL THEN
            RAISE EXCEPTION 'task contribution stamp requires initial screening';
        END IF;
    ELSIF NEW.locked_contribution_policy_version_id IS DISTINCT FROM
          OLD.locked_contribution_policy_version_id THEN
        IF OLD.locked_contribution_policy_version_id IS NOT NULL OR
           OLD.status <> 'draft' OR NEW.status <> 'screening' OR
           NEW.locked_contribution_policy_version_id IS NULL THEN
            RAISE EXCEPTION 'task contribution stamp is immutable';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE FUNCTION public.reject_admin_role_grant_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
             begin raise exception 'admin role grants are immutable' using errcode='55000'; end $$;
CREATE FUNCTION public.reject_artifact_fact_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
            raise exception '% rows are immutable', tg_table_name;
        end;
        $$;
CREATE FUNCTION public.reject_audit_event_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'audit events are append-only' using errcode = '55000';
        end
        $$;
CREATE FUNCTION public.reject_authority_control_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
             begin raise exception 'authority control is immutable' using errcode='55000'; end $$;
CREATE FUNCTION public.reject_authority_idempotency_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'authority idempotency records are immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_compensation_binding_lifecycle_event_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'compensation binding lifecycle events are immutable'
            using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.reject_compilation_projection_business_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          if tg_table_name='guide_sufficiency_reports' and exists(
            select 1 from project_guide_component_projection_operations where report_id=old.id
          ) then raise exception 'projected sufficiency content is immutable' using errcode='55000';
          end if;
          if tg_table_name='submission_artifact_policies' and exists(
            select 1 from project_guide_component_projection_operations where policy_id=old.id
          ) then raise exception 'projected policy content is immutable' using errcode='55000';
          end if;
          if tg_table_name='guide_sufficiency_report_source_usages' and exists(
            select 1 from project_guide_component_projection_operations where report_id=old.report_id
          ) then raise exception 'projected source usage is immutable' using errcode='55000';
          end if;
          if tg_table_name='guide_sufficiency_report_source_usages'
             and tg_op='UPDATE' and exists(
               select 1 from project_guide_component_projection_operations
                 where report_id=new.report_id
             ) then raise exception 'projected source usage is immutable'
               using errcode='55000';
          end if;
          if tg_op='UPDATE' then return new; end if;
          return old;
        end; $$;
CREATE FUNCTION public.reject_compilation_projection_business_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          if tg_table_name='guide_sufficiency_reports' and exists(
            select 1 from project_guide_component_projection_operations
              where report_id is not null
          ) then raise exception 'projected sufficiency content is immutable'
            using errcode='55000';
          end if;
          if tg_table_name='submission_artifact_policies' and exists(
            select 1 from project_guide_component_projection_operations
              where policy_id is not null
          ) then raise exception 'projected policy content is immutable'
            using errcode='55000';
          end if;
          if tg_table_name='guide_sufficiency_report_source_usages' and exists(
            select 1 from project_guide_component_projection_operations
              where report_id is not null
          ) then raise exception 'projected source usage is immutable'
            using errcode='55000';
          end if;
          return null;
        end; $$;
CREATE FUNCTION public.reject_contribution_policy_event_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'contribution policy lifecycle events are immutable'
            using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.reject_contribution_policy_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'contribution policy persistence cannot be truncated'
            using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.reject_guide_mutation_idempotency_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'guide mutation custody is immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_guide_proposal_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      BEGIN RAISE EXCEPTION 'guide proposal operation is immutable' USING ERRCODE='55000'; END $$;
CREATE FUNCTION public.reject_guide_source_snapshot_item_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'guide source snapshot items are immutable' using errcode='23514';
        end $$;
CREATE FUNCTION public.reject_pending_authority_idempotency() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          if exists(select 1 from authority_idempotency_records where id=new.id and status='pending') then
            raise exception 'pending authority idempotency cannot commit' using errcode='23514';
          end if; return null;
        end $$;
CREATE FUNCTION public.reject_policy_mutation_replay_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'policy mutation replay is immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_project_create_idempotency_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'project create reservations are immutable' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_project_guide_compilation_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin raise exception 'compilation custody is append-only'; end $$;
CREATE FUNCTION public.reject_project_guide_compilation_request_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'guide compilation request custody is immutable'
            using errcode='55000';
        end;
        $$;
CREATE FUNCTION public.reject_project_guide_projection_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'project guide projection custody is immutable'
            using errcode='55000';
        end; $$;
CREATE FUNCTION public.reject_project_role_history_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin raise exception 'project-role history cannot be truncated' using errcode='55000'; end $$;
CREATE FUNCTION public.reject_retired_guide_material_write() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      begin raise exception 'retained guide extraction evidence is read only' using errcode='55000'; end $$;
CREATE FUNCTION public.reject_review_lease_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'review leases cannot be truncated' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_review_queue_foundation_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'review queue foundation cannot be truncated' using errcode='55000';
        end $$;
CREATE FUNCTION public.reject_submission_policy_replay_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op = 'DELETE' then
            raise exception 'submission-policy replay rows cannot be deleted';
          end if;
          if old.status = 'reserved' and new.status = 'pending'
             and old.service_identity = 'workstream.project.setup'
             and old.action_id = 'project.submission_artifact_policy.derive'
             and (new.id,new.actor_profile_id,new.identity_link_id,new.service_identity,
                  new.action_id,new.idempotency_key,new.operation_id,new.project_id,
                  new.guide_id,new.source_snapshot_id,new.policy_id,new.setup_run_id,
                  new.setup_generation,new.setup_task_id,new.correlation_id,new.created_at,
                  new.response_json::text,new.committed_policy_id,new.committed_effective_policy_id,
                  new.committed_pre_submit_policy_id,new.committed_at)
                 is not distinct from
                 (old.id,old.actor_profile_id,old.identity_link_id,old.service_identity,
                  old.action_id,old.idempotency_key,old.operation_id,old.project_id,
                  old.guide_id,old.source_snapshot_id,old.policy_id,old.setup_run_id,
                  old.setup_generation,old.setup_task_id,old.correlation_id,old.created_at,
                  old.response_json::text,old.committed_policy_id,old.committed_effective_policy_id,
                  old.committed_pre_submit_policy_id,old.committed_at)
          then
            return new;
          end if;
          if old.status <> 'pending' or new.status <> 'committed'
             or (new.id,new.actor_profile_id,new.identity_link_id,new.service_identity,
                 new.action_id,new.idempotency_key,new.request_digest,
                 new.resource_context_digest,new.resource_context_json::text,new.operation_id,
                 new.project_id,new.guide_id,new.source_snapshot_id,new.policy_id,
                 new.setup_run_id,new.setup_generation,new.setup_task_id,
                 new.correlation_id,new.created_at)
                is distinct from
                (old.id,old.actor_profile_id,old.identity_link_id,old.service_identity,
                 old.action_id,old.idempotency_key,old.request_digest,
                 old.resource_context_digest,old.resource_context_json::text,old.operation_id,
                 old.project_id,old.guide_id,old.source_snapshot_id,old.policy_id,
                 old.setup_run_id,old.setup_generation,old.setup_task_id,
                 old.correlation_id,old.created_at)
          then
            raise exception 'invalid submission-policy replay mutation';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.reject_submission_policy_replay_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ begin
          raise exception 'submission-policy replay rows cannot be truncated';
        end $$;
CREATE FUNCTION public.reject_sufficiency_replay_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if tg_op = 'DELETE' then
            raise exception 'guide sufficiency replay rows are append-only';
          end if;
          if old.status = 'committed' or new.status <> 'committed'
             or (new.id,new.actor_profile_id,new.identity_link_id,new.action_id,
                 new.idempotency_key,new.request_digest,
                 new.resource_context_digest,
                 new.operation_id,new.project_id,new.guide_id,new.source_snapshot_id,
                 new.setup_run_id,new.setup_generation,new.created_at)
                is distinct from
                (old.id,old.actor_profile_id,old.identity_link_id,old.action_id,
                 old.idempotency_key,old.request_digest,
                 old.resource_context_digest,
                 old.operation_id,old.project_id,old.guide_id,old.source_snapshot_id,
                 old.setup_run_id,old.setup_generation,old.created_at)
          then
            raise exception 'invalid guide sufficiency replay mutation';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.reject_sufficiency_replay_truncate() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          raise exception 'guide sufficiency replay rows are append-only';
        end $$;
CREATE FUNCTION public.require_automatic_compilation_origin(requested_project uuid, requested_guide uuid, requested_snapshot uuid, requested_setup uuid, requested_generation bigint, source_operation uuid, source_event uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
declare
  guide project_guides%rowtype;
  snapshot guide_source_snapshots%rowtype;
  setup project_setup_runs%rowtype;
  mutation guide_mutation_idempotency_records%rowtype;
  event audit_events%rowtype;
begin
  select * into guide from project_guides where id=requested_guide for update;
  select * into snapshot from guide_source_snapshots where id=requested_snapshot for update;
  select * into setup from project_setup_runs where id=requested_setup for update;
  select * into mutation from guide_mutation_idempotency_records where operation_id=source_operation;
  select * into event from audit_events where id=source_event;
  if guide.id is null or snapshot.id is null or setup.id is null or mutation.id is null or event.id is null
     or guide.project_id is distinct from requested_project or guide.status is distinct from 'draft'
     or snapshot.project_id is distinct from requested_project or snapshot.guide_id is distinct from guide.id
     or snapshot.guide_version is distinct from guide.version
     or setup.project_id is distinct from requested_project or setup.guide_id is distinct from guide.id
     or setup.guide_version is distinct from guide.version
     or setup.source_snapshot_id is distinct from snapshot.id
     or setup.source_snapshot_hash is distinct from snapshot.bundle_hash
     or setup.setup_generation is distinct from requested_generation
     or exists(select 1 from guide_source_snapshots s where s.guide_id=guide.id
          and s.id<>snapshot.id and s.captured_at>=snapshot.captured_at)
     or exists(select 1 from project_setup_runs r where r.guide_id=guide.id
          and r.source_snapshot_id=snapshot.id and (r.created_at,r.id)>(setup.created_at,setup.id)) then
    raise exception 'automatic compilation origin lineage is invalid' using errcode='23514';
  end if;
  if mutation.action_id is distinct from 'project.guide_source_snapshot.create'
     or mutation.status is distinct from 'committed'
     or mutation.project_id is distinct from requested_project
     or mutation.resource_id is distinct from snapshot.id
     or mutation.setup_run_id is distinct from setup.id
     or mutation.operation_generation is distinct from snapshot.creation_generation
     or mutation.actor_profile_id is distinct from snapshot.created_by_actor_profile_id
     or mutation.identity_link_id is distinct from snapshot.created_via_identity_link_id
     or mutation.actor_profile_id is distinct from setup.authorized_by_actor_profile_id
     or mutation.identity_link_id is distinct from setup.authorized_via_identity_link_id
     or snapshot.authorization_decision_event_id is distinct from source_event
     or setup.authorization_decision_event_id is distinct from source_event
     or snapshot.creation_action_id is distinct from mutation.action_id
     or setup.authorization_action_id is distinct from mutation.action_id
     or snapshot.created_by_admin_role_grant_id is null
     or setup.authorized_by_admin_role_grant_id is distinct from snapshot.created_by_admin_role_grant_id
     or setup.authorization_scope_type is distinct from snapshot.creation_scope_type
     or setup.authorization_scope_project_id is distinct from snapshot.creation_scope_project_id then
    raise exception 'automatic compilation source operation is invalid' using errcode='23514';
  end if;
  if event.event_domain is distinct from 'authority'
     or event.event_type is distinct from 'SensitiveAuthorizationAllowed'
     or event.action_id is distinct from mutation.action_id
     or event.permission_id is distinct from 'project.guide.manage'
     or event.resource_type is distinct from 'project'
     or event.resource_id is distinct from requested_project::text
     or event.project_id is distinct from requested_project
     or event.actor_id is distinct from mutation.actor_profile_id::text
     or event.actor_ref_kind is distinct from 'actor_profile'
     or event.matched_grant_id is distinct from snapshot.created_by_admin_role_grant_id::text
     or event.after_facts->>'allowed' is distinct from 'true'
     or event.after_facts->>'resource_context_digest' is distinct from mutation.resource_context_digest then
    raise exception 'automatic compilation source authorization is invalid' using errcode='23514';
  end if;
end;
$$;
CREATE FUNCTION public.require_compensation_binding_lifecycle_event() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if not exists (
            select 1 from compensation_adapter_binding_lifecycle_events e
            where e.adapter_binding_id=new.id
              and e.project_id=new.project_id
              and e.to_status=new.status
              and e.to_lifecycle_version=new.binding_lifecycle_version
          ) then
            raise exception 'compensation binding transition requires lifecycle event'
              using errcode='23514';
          end if;
          return null;
        end;
        $$;
CREATE FUNCTION public.require_guide_activation_custody(operation uuid, new_binding boolean) RETURNS void
    LANGUAGE plpgsql
    AS $_$
      DECLARE r guide_mutation_idempotency_records%rowtype; g project_guides%rowtype;
        post project_post_policy_operations%rowtype; upstream project_guide_proposal_approvals%rowtype;
        f jsonb; a jsonb; receipt jsonb; command jsonb; target jsonb; locator jsonb; con jsonb; selection jsonb;
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
        FOR selection IN SELECT command->'review' UNION ALL SELECT command->'revision' LOOP
          IF jsonb_typeof(selection) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION 'guide activation nested receipt shape mismatch' USING ERRCODE='23514';
          END IF;
          IF (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(selection) k)
               IS DISTINCT FROM ARRAY['generation','policy_hash','policy_id']
             OR jsonb_typeof(selection->'generation') IS DISTINCT FROM 'number'
             OR (selection->>'generation') !~ '^[1-9][0-9]*$'
             OR (selection->>'policy_hash') !~ '^sha256:[0-9a-f]{64}$' THEN
            RAISE EXCEPTION 'guide activation nested receipt shape mismatch' USING ERRCODE='23514';
          END IF;
        END LOOP;
        IF jsonb_typeof(con->'adapter_binding_ids') IS DISTINCT FROM 'array'
           OR jsonb_typeof(con->'rules_and_definitions_digest') IS DISTINCT FROM 'string'
           OR (con->>'rules_and_definitions_digest') !~ '^sha256:[0-9a-f]{64}$'
           OR jsonb_typeof(con->'version_number') IS DISTINCT FROM 'number'
           OR (con->>'version_number') !~ '^[1-9][0-9]*$'
           OR jsonb_typeof(command->'guide_mutation_generation') IS DISTINCT FROM 'number'
           OR (command->>'guide_mutation_generation') !~ '^[1-9][0-9]*$'
           OR jsonb_typeof(receipt->'activation_generation') IS DISTINCT FROM 'number'
           OR (receipt->>'activation_generation') !~ '^[1-9][0-9]*$'
           OR jsonb_typeof(receipt->'effective_at') IS DISTINCT FROM 'string'
           OR (receipt->>'effective_at') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
           OR (command->'expected_previous_active_guide_generation' <> 'null'::jsonb AND
               (jsonb_typeof(command->'expected_previous_active_guide_generation') IS DISTINCT FROM 'number'
                OR (command->>'expected_previous_active_guide_generation') !~ '^[1-9][0-9]*$'))
           OR (command->'expected_previous_active_guide_id' = 'null'::jsonb
               AND command->'expected_previous_active_guide_generation' <> 'null'::jsonb) THEN
          RAISE EXCEPTION 'guide activation nested receipt shape mismatch' USING ERRCODE='23514';
        END IF;
        IF EXISTS (SELECT 1 FROM jsonb_array_elements(con->'adapter_binding_ids') item
            WHERE jsonb_typeof(item) IS DISTINCT FROM 'string'
               OR (item #>> '{}') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') THEN
          RAISE EXCEPTION 'guide activation nested receipt shape mismatch' USING ERRCODE='23514';
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
                'operation_id',locator->>'operation_id','action_id','project.guide.activate')
           OR receipt->>'operation_id' IS DISTINCT FROM r.operation_id::text
           OR command->>'idempotency_key' IS DISTINCT FROM r.idempotency_key::text
           OR (receipt->>'activation_generation')::integer IS DISTINCT FROM r.operation_generation
           OR r.operation_generation IS DISTINCT FROM (command->>'guide_mutation_generation')::integer+1
           OR g.mutation_generation IS DISTINCT FROM r.operation_generation
           OR g.effective_at IS DISTINCT FROM (receipt->>'effective_at')::timestamptz
           OR g.approved_by IS DISTINCT FROM r.actor_profile_id::text
           OR g.contribution_policy_id::text IS DISTINCT FROM command->>'contribution_policy_id'
           OR g.contribution_policy_version_id::text IS DISTINCT FROM command->>'contribution_policy_version_id'
           OR con->>'project_id' IS DISTINCT FROM r.project_id::text
           OR con->>'contribution_policy_id' IS DISTINCT FROM g.contribution_policy_id::text
           OR con->>'contribution_policy_version_id' IS DISTINCT FROM g.contribution_policy_version_id::text
           OR con->>'purpose' IS DISTINCT FROM 'guide_activation'
           OR target->'proposal'->>'project_id' IS DISTINCT FROM r.project_id::text
           OR target->'proposal'->>'guide_id' IS DISTINCT FROM g.id::text
           OR target->'proposal'->>'guide_version' IS DISTINCT FROM g.version
           OR (receipt->>'prior_project_status' IS DISTINCT FROM 'draft'
               AND receipt->>'prior_project_status' IS DISTINCT FROM 'active') THEN
          RAISE EXCEPTION 'guide activation immutable custody mismatch' USING ERRCODE='23514';
        END IF;
        IF (g.selected_review_policy_id::text,g.selected_review_policy_generation,g.selected_review_policy_hash,
            g.selected_revision_policy_id::text,g.selected_revision_policy_generation,g.selected_revision_policy_hash)
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
              WHERE prior.id::text=command->>'expected_previous_active_guide_id' AND prior.id<>g.id
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
            'project.guide.activate','project.guide.manage','project_guide_activation',g.id,
            locator->>'operation_id',r.resource_context_digest);
        END IF;
      END $_$;
CREATE FUNCTION public.require_guide_activation_predecessor(prior_id uuid, prior_generation integer, superseded timestamp with time zone) RETURNS void
    LANGUAGE plpgsql
    AS $$
      DECLARE operation uuid;
      BEGIN
        SELECT r.operation_id INTO operation FROM guide_mutation_idempotency_records r
          JOIN project_guides g ON g.activation_operation_id=r.operation_id AND g.project_id=r.project_id
          JOIN project_guides prior ON prior.id=prior_id AND prior.project_id=g.project_id
          WHERE r.action_id='project.guide.activate' AND r.status='committed'
            AND r.response_json->'command'->>'expected_previous_active_guide_id'=prior_id::text
            AND (r.response_json->'command'->>'expected_previous_active_guide_generation')::integer
                IS NOT DISTINCT FROM prior_generation
            AND g.effective_at=superseded AND g.status='active';
        IF operation IS NULL THEN
          RAISE EXCEPTION 'guide supersession requires exact successor activation' USING ERRCODE='23514';
        END IF;
        PERFORM require_guide_activation_custody(operation,true);
      END $$;
CREATE FUNCTION public.require_guide_document_creation_pair() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    DECLARE
      guide_key uuid;
      root_row guide_mutation_idempotency_records%rowtype;
      source_row guide_mutation_idempotency_records%rowtype;
      guide_row project_guides%rowtype;
      snapshot_row guide_source_snapshots%rowtype;
      setup_row project_setup_runs%rowtype;
      expected_documents jsonb;
    BEGIN
      IF TG_TABLE_NAME = 'project_guides' THEN
        guide_key := NEW.id;
      ELSIF TG_TABLE_NAME = 'guide_source_snapshots' THEN
        guide_key := NEW.guide_id;
      ELSE
        IF NEW.action_id = 'project.guide.create' THEN
          guide_key := NEW.resource_id;
        ELSIF NEW.action_id = 'project.guide_source_snapshot.create' THEN
          SELECT guide_id INTO guide_key FROM guide_source_snapshots WHERE id=NEW.resource_id;
        ELSE RETURN NULL;
        END IF;
      END IF;
      SELECT * INTO guide_row FROM project_guides WHERE id=guide_key;
      SELECT * INTO root_row FROM guide_mutation_idempotency_records
        WHERE resource_id=guide_key AND action_id='project.guide.create';
      SELECT * INTO snapshot_row FROM guide_source_snapshots WHERE guide_id=guide_key;
      SELECT * INTO source_row FROM guide_mutation_idempotency_records
        WHERE resource_id=snapshot_row.id AND action_id='project.guide_source_snapshot.create';
      SELECT * INTO setup_row FROM project_setup_runs WHERE id=source_row.setup_run_id;
      IF guide_row.id IS NULL OR root_row.id IS NULL OR source_row.id IS NULL
         OR snapshot_row.id IS NULL OR setup_row.id IS NULL
         OR (SELECT count(*) FROM guide_source_snapshots WHERE guide_id=guide_key) <> 1
         OR (SELECT count(*) FROM guide_mutation_idempotency_records
             WHERE resource_id=guide_key AND action_id='project.guide.create') <> 1
         OR (SELECT count(*) FROM guide_mutation_idempotency_records
             WHERE resource_id=snapshot_row.id AND action_id='project.guide_source_snapshot.create') <> 1
         OR root_row.status <> 'committed' OR source_row.status <> 'committed'
         OR root_row.operation_generation <> 1 OR source_row.operation_generation <> 1
         OR snapshot_row.creation_generation <> 1
         OR (root_row.actor_profile_id,root_row.identity_link_id,root_row.project_id,root_row.idempotency_key)
            IS DISTINCT FROM
            (source_row.actor_profile_id,source_row.identity_link_id,source_row.project_id,source_row.idempotency_key)
         OR root_row.project_id IS DISTINCT FROM guide_row.project_id
         OR (snapshot_row.project_id,snapshot_row.guide_version)
            IS DISTINCT FROM (guide_row.project_id,guide_row.version)
         OR (setup_row.project_id,setup_row.guide_id,setup_row.guide_version,
             setup_row.source_snapshot_id,setup_row.source_snapshot_hash)
            IS DISTINCT FROM (guide_row.project_id,guide_row.id,guide_row.version,
                              snapshot_row.id,snapshot_row.bundle_hash)
         OR root_row.response_json::jsonb->'setup'->>'id' IS DISTINCT FROM setup_row.id::text
         OR root_row.response_json::jsonb->'setup'->>'status' IS DISTINCT FROM 'awaiting_documents'
         OR setup_row.status IS DISTINCT FROM 'awaiting_documents'
         OR setup_row.current_step IS DISTINCT FROM 'awaiting_documents'
         OR setup_row.documents_ready_at IS NOT NULL
         OR setup_row.celery_task_id IS NOT NULL
      THEN
        RAISE EXCEPTION 'guide document creation pair is invalid' USING ERRCODE='23514';
      END IF;
      SELECT jsonb_agg(jsonb_build_object(
        'document_id',id,'label',source_label,'media_type',media_type,'order',item_order
      ) ORDER BY item_order) INTO expected_documents
      FROM guide_source_snapshot_items WHERE source_snapshot_id=snapshot_row.id;
      IF expected_documents IS NULL
         OR root_row.response_json::jsonb->'documents' IS DISTINCT FROM expected_documents THEN
        RAISE EXCEPTION 'guide document creation response is invalid' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$;
CREATE FUNCTION public.require_guide_proposal_approval() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      DECLARE a project_guide_proposal_approvals%rowtype;
        r submission_policy_mutation_idempotency_records%rowtype;
        p submission_artifact_policies%rowtype;
        e effective_project_submission_artifact_policies%rowtype;
        pre pre_submit_checker_policies%rowtype;
        projection project_guide_component_projection_operations%rowtype;
        expected_receipt jsonb; warning_hashes jsonb;
        successor project_guide_proposal_approvals%rowtype;
        prior project_guide_proposal_approvals%rowtype;
      BEGIN
        IF tg_table_name='project_guide_proposal_approvals' THEN a:=new;
        ELSIF tg_table_name='submission_artifact_policies' THEN
          IF new.lifecycle_status NOT IN ('approved','superseded') THEN
            IF EXISTS(SELECT 1 FROM project_guide_proposal_approvals WHERE artifact_policy_id=new.id) THEN
              RAISE EXCEPTION 'approved proposal lifecycle cannot revert' USING ERRCODE='23514';
            END IF;
            RETURN NULL;
          END IF;
          IF new.derivation_source IS DISTINCT FROM 'unified_compilation' THEN
            IF tg_op='UPDATE' AND old.lifecycle_status='draft' AND new.lifecycle_status='superseded'
               AND old.approved_at IS NULL AND new.approved_at IS NULL
               AND NOT EXISTS(SELECT 1 FROM project_guide_proposal_approvals WHERE artifact_policy_id=new.id) THEN
              RETURN NULL; -- Existing mutation custody must prove the exact draft replacement.
            END IF;
            IF tg_op='INSERT' OR old.lifecycle_status IS DISTINCT FROM new.lifecycle_status THEN
              RAISE EXCEPTION 'approval requires a unified proposal' USING ERRCODE='23514';
            END IF;
            RETURN NULL;
          END IF;
          SELECT * INTO a FROM project_guide_proposal_approvals WHERE artifact_policy_id=new.id;
        ELSIF tg_table_name='submission_policy_mutation_idempotency_records' THEN
          IF new.action_id<>'project.submission_artifact_policy.approve' OR new.status<>'committed' THEN RETURN NULL; END IF;
          SELECT * INTO a FROM project_guide_proposal_approvals WHERE operation_id=new.operation_id;
        ELSE
          IF new.creation_action_id IS DISTINCT FROM 'project.submission_artifact_policy.approve' THEN RETURN NULL; END IF;
          IF tg_table_name='effective_project_submission_artifact_policies' THEN
            SELECT * INTO a FROM project_guide_proposal_approvals WHERE effective_policy_id=new.id;
          ELSE
            SELECT * INTO a FROM project_guide_proposal_approvals WHERE pre_submit_policy_id=new.id;
          END IF;
        END IF;
        IF a.operation_id IS NULL THEN
          RAISE EXCEPTION 'immutable proposal approval operation missing' USING ERRCODE='23514';
        END IF;
        PERFORM require_guide_proposal_target(a.target_json::jsonb,a.target_digest,a.finalization_id);
        SELECT * INTO r FROM submission_policy_mutation_idempotency_records WHERE operation_id=a.operation_id;
        SELECT * INTO p FROM submission_artifact_policies WHERE id=a.artifact_policy_id;
        SELECT * INTO e FROM effective_project_submission_artifact_policies WHERE id=a.effective_policy_id;
        SELECT * INTO pre FROM pre_submit_checker_policies WHERE id=a.pre_submit_policy_id;
        SELECT * INTO projection FROM project_guide_component_projection_operations WHERE policy_id=p.id;
        IF r.id IS NULL OR r.status IS DISTINCT FROM 'committed'
           OR r.action_id IS DISTINCT FROM 'project.submission_artifact_policy.approve'
           OR r.actor_profile_id IS DISTINCT FROM a.actor_profile_id
           OR r.identity_link_id IS DISTINCT FROM a.identity_link_id
           OR r.project_id IS DISTINCT FROM a.project_id OR r.guide_id IS DISTINCT FROM a.guide_id
           OR r.source_snapshot_id::text IS DISTINCT FROM a.target_json->>'source_snapshot_id'
           OR r.setup_generation IS DISTINCT FROM (a.target_json->>'setup_generation')::bigint
           OR r.request_digest IS DISTINCT FROM a.request_digest
           OR r.resource_context_digest IS DISTINCT FROM a.resource_context_digest
           OR guide_proposal_hash(r.resource_context_json::jsonb) IS DISTINCT FROM a.resource_context_digest
           OR r.resource_context_json->>'target_digest' IS DISTINCT FROM a.target_digest
           OR r.resource_context_json->>'output_digest' IS DISTINCT FROM a.output_digest
           OR r.resource_context_json->>'request_digest' IS DISTINCT FROM a.request_digest
           OR r.committed_policy_id IS DISTINCT FROM p.id
           OR r.committed_effective_policy_id IS DISTINCT FROM e.id
           OR r.committed_pre_submit_policy_id IS DISTINCT FROM pre.id
           OR p.id IS NULL OR e.id IS NULL OR pre.id IS NULL OR projection.operation_id IS NULL
           OR (p.project_id,p.guide_id,e.project_id,e.guide_id,pre.project_id,pre.guide_id)
              IS DISTINCT FROM (a.project_id,a.guide_id,a.project_id,a.guide_id,a.project_id,a.guide_id)
           OR p.id::text IS DISTINCT FROM a.target_json->>'artifact_policy_id'
           OR p.policy_hash IS DISTINCT FROM a.target_json->>'artifact_policy_hash'
           OR a.compilation_id::text IS DISTINCT FROM a.target_json->>'compilation_id'
           OR projection.operation_id::text IS DISTINCT FROM a.target_json->>'artifact_projection_operation_id'
           OR projection.output_digest IS DISTINCT FROM a.target_json->>'artifact_projection_output_digest'
           OR p.derivation_source IS DISTINCT FROM 'unified_compilation'
           OR e.submission_artifact_policy_id IS DISTINCT FROM p.id
           OR e.submission_artifact_policy_hash IS DISTINCT FROM p.policy_hash
           OR pre.effective_policy_id IS DISTINCT FROM e.id
           OR pre.effective_policy_hash IS DISTINCT FROM e.effective_policy_hash
           OR guide_proposal_hash(e.effective_policy::jsonb) IS DISTINCT FROM e.effective_policy_hash
           OR guide_proposal_hash(pre.compiled_bundle::jsonb) IS DISTINCT FROM pre.compiled_bundle_hash
           OR guide_proposal_hash(a.effective_pre_submit_plan::jsonb) IS DISTINCT FROM a.effective_pre_submit_plan_hash
           OR guide_proposal_hash(a.receipt_json::jsonb) IS DISTINCT FROM a.output_digest
           OR r.response_json::jsonb IS DISTINCT FROM a.receipt_json::jsonb THEN
          RAISE EXCEPTION 'proposal approval reservation or output custody mismatch' USING ERRCODE='23514';
        END IF;
        SELECT coalesce(jsonb_agg(digest ORDER BY digest),'[]'::jsonb) INTO warning_hashes
          FROM (SELECT guide_proposal_hash(finding) AS digest FROM project_guide_compilations c,
                jsonb_array_elements(c.canonical_result::jsonb->'findings') AS finding
                WHERE c.id=a.compilation_id AND finding->>'severity'='warning') warnings;
        expected_receipt:=jsonb_build_object('operation_id',a.operation_id,'target_digest',a.target_digest,
          'artifact_policy_id',p.id,'effective_policy_id',e.id,'effective_policy_hash',e.effective_policy_hash,
          'pre_submit_policy_id',pre.id,'pre_submit_bundle_hash',pre.compiled_bundle_hash,
          'effective_pre_submit_plan_hash',a.effective_pre_submit_plan_hash,
          'acknowledged_warning_hashes',warning_hashes);
        IF a.receipt_json::jsonb IS DISTINCT FROM expected_receipt THEN
          RAISE EXCEPTION 'proposal approval receipt mismatch' USING ERRCODE='23514';
        END IF;
        SELECT * INTO prior FROM project_guide_proposal_approvals WHERE operation_id=a.prior_approval_operation_id;
        IF r.resource_context_json::jsonb IS DISTINCT FROM guide_proposal_resource(
             a.target_json::jsonb,r.resource_context_json->'locator'->>'operation_id',a.actor_profile_id,a.identity_link_id,
             'project.submission_artifact_policy.approve',a.request_digest,a.output_digest,
             prior.operation_id,prior.output_digest)
           OR a.request_digest IS DISTINCT FROM guide_proposal_hash(jsonb_build_object(
             'target',a.target_json::jsonb,'idempotency_key',r.idempotency_key,
             'acknowledged_warning_hashes',warning_hashes,
             'expected_previous_approval_operation_id',prior.operation_id,
             'expected_previous_approval_output_digest',prior.output_digest))
           OR a.effective_pre_submit_plan::jsonb->'lineage' IS DISTINCT FROM jsonb_build_object(
             'project_id',a.project_id,'guide_id',a.guide_id,
             'guide_version',a.target_json->>'guide_version',
             'source_snapshot_id',a.target_json->>'source_snapshot_id',
             'source_snapshot_hash',a.target_json->>'source_snapshot_hash',
             'effective_policy_id',e.id,'effective_policy_hash',e.effective_policy_hash,
             'pre_submit_policy_id',pre.id,'pre_submit_policy_bundle_hash',pre.compiled_bundle_hash)
           OR a.effective_pre_submit_plan::jsonb->'catalogue' IS DISTINCT FROM jsonb_build_object(
             'id',a.target_json->>'pre_catalogue_id','version',a.target_json->>'pre_catalogue_version',
             'schema_version',a.target_json->>'pre_catalogue_schema_version',
             'manifest_sha256',a.target_json->>'pre_catalogue_manifest_hash') THEN
          RAISE EXCEPTION 'proposal approval request or plan binding mismatch' USING ERRCODE='23514';
        END IF;
        SELECT * INTO successor FROM project_guide_proposal_approvals WHERE prior_approval_operation_id=a.operation_id;
        IF p.lifecycle_status='superseded' THEN
          IF successor.operation_id IS NULL OR successor.project_id<>a.project_id OR successor.guide_id<>a.guide_id
             OR e.lifecycle_status IS DISTINCT FROM 'superseded' OR pre.lifecycle_status IS DISTINCT FROM 'superseded'
             OR p.superseded_at IS NULL OR e.superseded_at IS DISTINCT FROM p.superseded_at
             OR pre.superseded_at IS DISTINCT FROM p.superseded_at
             OR NOT EXISTS(SELECT 1 FROM submission_artifact_policies next WHERE next.id=successor.artifact_policy_id
                           AND next.supersedes_policy_id=p.id)
             OR NOT EXISTS(SELECT 1 FROM effective_project_submission_artifact_policies next WHERE next.id=successor.effective_policy_id
                           AND next.supersedes_effective_policy_id=e.id)
             OR NOT EXISTS(SELECT 1 FROM pre_submit_checker_policies next WHERE next.id=successor.pre_submit_policy_id
                           AND next.supersedes_pre_submit_checker_policy_id=pre.id) THEN
            RAISE EXCEPTION 'proposal supersession requires exact successor approval' USING ERRCODE='23514';
          END IF;
        ELSIF p.lifecycle_status IS DISTINCT FROM 'approved' OR e.lifecycle_status IS DISTINCT FROM 'approved'
           OR pre.lifecycle_status IS DISTINCT FROM 'compiled' OR successor.operation_id IS NOT NULL THEN
          RAISE EXCEPTION 'proposal approval lifecycle mismatch' USING ERRCODE='23514';
        END IF;
        SELECT * INTO prior FROM project_guide_proposal_approvals WHERE operation_id=a.prior_approval_operation_id;
        IF (a.prior_approval_operation_id IS NOT NULL AND
            (prior.operation_id IS NULL OR prior.project_id<>a.project_id OR prior.guide_id<>a.guide_id
             OR (prior.target_json->>'setup_generation')::bigint >= (a.target_json->>'setup_generation')::bigint))
           OR p.supersedes_policy_id IS DISTINCT FROM prior.artifact_policy_id
           OR e.supersedes_effective_policy_id IS DISTINCT FROM prior.effective_policy_id
           OR pre.supersedes_pre_submit_checker_policy_id IS DISTINCT FROM prior.pre_submit_policy_id THEN
          RAISE EXCEPTION 'proposal prior approval mismatch' USING ERRCODE='23514';
        END IF;
        IF a.prior_approval_operation_id IS NOT NULL AND NOT EXISTS(
          SELECT 1 FROM submission_artifact_policies prior_policy
          JOIN effective_project_submission_artifact_policies prior_effective
            ON prior_effective.id=prior.effective_policy_id
          JOIN pre_submit_checker_policies prior_pre ON prior_pre.id=prior.pre_submit_policy_id
          WHERE prior_policy.id=prior.artifact_policy_id
            AND prior_policy.lifecycle_status='superseded'
            AND prior_effective.lifecycle_status='superseded'
            AND prior_pre.lifecycle_status='superseded'
            AND prior_policy.superseded_at IS NOT NULL
            AND prior_effective.superseded_at=prior_policy.superseded_at
            AND prior_pre.superseded_at=prior_policy.superseded_at
        ) THEN
          RAISE EXCEPTION 'proposal prior approval is not superseded' USING ERRCODE='23514';
        END IF;
        IF tg_table_name='project_guide_proposal_approvals' THEN
          IF NOT EXISTS(SELECT 1 FROM project_guides g WHERE g.id=a.guide_id AND g.status='draft')
             OR (SELECT max(setup_generation) FROM project_setup_runs WHERE guide_id=a.guide_id)
                IS DISTINCT FROM (a.target_json->>'setup_generation')::bigint THEN
            RAISE EXCEPTION 'proposal approval target is no longer current' USING ERRCODE='23514';
          END IF;
          IF p.lifecycle_status IS DISTINCT FROM 'approved' OR e.lifecycle_status IS DISTINCT FROM 'approved'
             OR pre.lifecycle_status IS DISTINCT FROM 'compiled'
             OR project_guide_projection_business_digest(projection) IS DISTINCT FROM a.approved_policy_output_digest THEN
            RAISE EXCEPTION 'proposal approval lifecycle mismatch' USING ERRCODE='23514';
          END IF;
          PERFORM require_guide_proposal_authority(a.actor_profile_id,a.identity_link_id,a.admin_role_grant_id,
            a.project_id,a.authorization_decision_event_id,'project.submission_artifact_policy.approve',
            'project.effective_policy.manage','project_submission_artifact_policy_mutation',p.id,
            r.resource_context_json->'locator'->>'operation_id',a.resource_context_digest);
        END IF;
        RETURN NULL;
      END $$;
CREATE FUNCTION public.require_guide_proposal_authority(actor uuid, link uuid, role_grant uuid, project uuid, decision uuid, action text, permission text, resource_kind text, resource uuid, selector text, digest text) RETURNS void
    LANGUAGE plpgsql
    AS $$
      DECLARE evidence audit_events%rowtype;
      BEGIN
        PERFORM 1 FROM actor_profiles a JOIN actor_identity_links l ON l.actor_profile_id=a.id
          JOIN admin_role_grants g ON g.target_actor_profile_id=a.id
          WHERE a.id=actor AND a.status='active' AND a.actor_kind='human'
            AND l.id=link AND l.status='active' AND l.subject_kind='human'
            AND g.id=role_grant AND g.status='active' AND g.role='project_manager'
            AND g.scope_type='project' AND g.scope_project_id=project FOR SHARE OF a,l,g;
        IF NOT FOUND THEN
          RAISE EXCEPTION 'guide proposal current authority missing' USING ERRCODE='23514';
        END IF;
        SELECT * INTO evidence FROM audit_events WHERE id=decision;
        IF evidence.id IS NULL OR evidence.event_domain IS DISTINCT FROM 'authority'
           OR evidence.event_type IS DISTINCT FROM 'SensitiveAuthorizationAllowed'
           OR evidence.denial_code IS NOT NULL OR evidence.actor_ref_kind IS DISTINCT FROM 'actor_profile'
           OR evidence.actor_id IS DISTINCT FROM actor::text OR evidence.matched_grant_id IS DISTINCT FROM role_grant::text
           OR evidence.project_id IS DISTINCT FROM project OR evidence.action_id IS DISTINCT FROM action
           OR evidence.permission_id IS DISTINCT FROM permission OR evidence.resource_type IS DISTINCT FROM resource_kind
           OR evidence.resource_id IS DISTINCT FROM resource::text OR evidence.target_ref_kind IS DISTINCT FROM 'project'
           OR evidence.target_ref_id IS DISTINCT FROM project::text
           OR evidence.request_id IS NULL
           OR evidence.correlation_id::text IS DISTINCT FROM selector
           OR evidence.after_facts->>'allowed' IS DISTINCT FROM 'true'
           OR evidence.after_facts->>'resource_context_digest' IS DISTINCT FROM digest THEN
          RAISE EXCEPTION 'guide proposal authority evidence mismatch' USING ERRCODE='23514';
        END IF;
      END $$;
CREATE FUNCTION public.require_guide_proposal_correction() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      DECLARE c project_guide_proposal_corrections%rowtype;
        source project_setup_runs%rowtype; successor project_setup_runs%rowtype; expected jsonb;
        prior project_guide_proposal_approvals%rowtype;
      BEGIN
        IF tg_table_name='project_guide_proposal_corrections' THEN c:=new;
        ELSE
          SELECT * INTO c FROM project_guide_proposal_corrections WHERE successor_setup_run_id=new.id;
          IF c.operation_id IS NULL AND new.status<>'correction_requested' THEN RETURN NULL; END IF;
        END IF;
        IF c.operation_id IS NULL THEN
          RAISE EXCEPTION 'guide correction operation missing' USING ERRCODE='23514';
        END IF;
        PERFORM require_guide_proposal_target(c.target_json::jsonb,c.target_digest,c.finalization_id);
        SELECT * INTO source FROM project_setup_runs WHERE id::text=c.target_json->>'setup_run_id';
        SELECT * INTO successor FROM project_setup_runs WHERE id=c.successor_setup_run_id;
        IF source.id IS NULL OR successor.id IS NULL
           OR (successor.project_id,successor.guide_id,successor.guide_version,successor.source_snapshot_id,successor.source_snapshot_hash)
              IS DISTINCT FROM (source.project_id,source.guide_id,source.guide_version,source.source_snapshot_id,source.source_snapshot_hash)
           OR (c.project_id,c.guide_id,c.compilation_id::text) IS DISTINCT FROM
              (source.project_id,source.guide_id,c.target_json->>'compilation_id')
           OR successor.setup_generation IS DISTINCT FROM source.setup_generation+1
           OR c.successor_setup_generation IS DISTINCT FROM successor.setup_generation
           OR source.documents_ready_at IS NULL OR successor.documents_ready_at IS DISTINCT FROM source.documents_ready_at
           OR guide_proposal_hash(c.resource_context_json::jsonb) IS DISTINCT FROM c.resource_context_digest
           OR c.resource_context_json->>'target_digest' IS DISTINCT FROM c.target_digest
           OR c.resource_context_json->>'request_digest' IS DISTINCT FROM c.request_digest
           OR c.resource_context_json->>'output_digest' IS DISTINCT FROM c.output_digest
           OR guide_proposal_hash(c.receipt_json::jsonb) IS DISTINCT FROM c.output_digest
           OR guide_proposal_hash(jsonb_build_object('target',c.target_json::jsonb,
               'idempotency_key',c.idempotency_key,'reason',c.reason)) IS DISTINCT FROM c.request_digest
           OR guide_proposal_hash(jsonb_build_object('operation_id',c.operation_id,
               'predecessor_compilation_id',c.compilation_id,'predecessor_result_hash',c.target_json->>'result_hash',
               'target_digest',c.target_digest,'reason',c.reason)) IS DISTINCT FROM c.feedback_hash THEN
          RAISE EXCEPTION 'guide correction successor custody mismatch' USING ERRCODE='23514';
        END IF;
        SELECT * INTO prior FROM project_guide_proposal_approvals
          WHERE operation_id=(c.resource_context_json->>'current_approval_operation_id')::uuid;
        IF (prior.operation_id IS NOT NULL AND (prior.project_id<>c.project_id OR prior.guide_id<>c.guide_id))
           OR c.resource_context_json::jsonb IS DISTINCT FROM guide_proposal_resource(
             c.target_json::jsonb,c.resource_context_json->'locator'->>'operation_id',c.actor_profile_id,c.identity_link_id,
             'project.guide_compilation.correction.request',c.request_digest,c.output_digest,
             prior.operation_id,prior.output_digest) THEN
          RAISE EXCEPTION 'guide correction resource binding mismatch' USING ERRCODE='23514';
        END IF;
        expected:=jsonb_build_object('operation_id',c.operation_id,'target_digest',c.target_digest,
          'successor_setup_run_id',successor.id,'successor_setup_generation',successor.setup_generation,
          'feedback_hash',c.feedback_hash,'status','correction_requested');
        IF c.receipt_json::jsonb IS DISTINCT FROM expected THEN
          RAISE EXCEPTION 'guide correction receipt mismatch' USING ERRCODE='23514';
        END IF;
        IF tg_table_name='project_guide_proposal_corrections' THEN
          IF NOT EXISTS(SELECT 1 FROM project_guides g WHERE g.id=c.guide_id AND g.status='draft')
             OR (SELECT max(setup_generation) FROM project_setup_runs WHERE guide_id=c.guide_id)
                IS DISTINCT FROM successor.setup_generation THEN
            RAISE EXCEPTION 'guide correction target is no longer current' USING ERRCODE='23514';
          END IF;
          IF successor.error_code IS NOT NULL OR successor.error_artifact_incident_id IS NOT NULL
             OR successor.status IS DISTINCT FROM 'correction_requested'
             OR successor.current_step IS DISTINCT FROM 'correction_requested'
             OR successor.celery_task_id IS NOT NULL OR successor.started_at IS NOT NULL
             OR successor.finished_at IS NOT NULL OR successor.output_sufficiency_report_id IS NOT NULL
             OR successor.output_submission_artifact_policy_id IS NOT NULL
             OR successor.output_post_submit_checker_policy_id IS NOT NULL THEN
            RAISE EXCEPTION 'guide correction initial successor shape mismatch' USING ERRCODE='23514';
          END IF;
          PERFORM require_guide_proposal_authority(c.actor_profile_id,c.identity_link_id,c.admin_role_grant_id,
            c.project_id,c.authorization_decision_event_id,'project.guide_compilation.correction.request',
            'project.guide_compilation.request','project_guide_compilation_correction',c.operation_id,
            c.resource_context_json->'locator'->>'operation_id',c.resource_context_digest);
        END IF;
        IF successor.status<>'correction_requested' AND NOT EXISTS(
          SELECT 1 FROM project_guide_compilation_request_operations r
          JOIN project_guide_compilation_attempts a ON a.id=r.attempt_id
          WHERE r.setup_run_id=successor.id AND r.setup_generation=successor.setup_generation
            AND r.project_id=c.project_id AND r.guide_id=c.guide_id
            AND r.request_trigger='project_manager'
            AND r.expected_predecessor_compilation_id=c.compilation_id
            AND a.setup_run_id=successor.id AND a.runtime_configuration IS NOT NULL
        ) THEN
          RAISE EXCEPTION 'correction successor requires human compilation request' USING ERRCODE='23514';
        END IF;
        RETURN NULL;
      END $$;
CREATE FUNCTION public.require_guide_proposal_target(target jsonb, digest text, final_id uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
      DECLARE expected jsonb;
      BEGIN
        SELECT jsonb_build_object(
          'project_id',f.project_id,'guide_id',f.guide_id,'guide_version',f.guide_version,
          'compilation_id',f.compilation_id,'source_snapshot_id',f.source_snapshot_id,
          'source_snapshot_hash',f.source_snapshot_hash,'setup_run_id',f.setup_run_id,
          'setup_generation',f.setup_generation,'finalization_id',f.id,
          'finalization_facts_digest',f.facts_digest,'result_hash',f.result_hash,
          'component_hashes',f.component_hashes::jsonb,
          'pre_catalogue_id',a.pre_catalogue_id,'pre_catalogue_version',a.pre_catalogue_version,
          'pre_catalogue_schema_version',a.pre_catalogue_schema_version,
          'pre_catalogue_manifest_hash',a.pre_catalogue_manifest_hash,
          'post_catalogue_id',a.post_catalogue_id,'post_catalogue_version',a.post_catalogue_version,
          'post_catalogue_schema_version',a.post_catalogue_schema_version,
          'post_catalogue_manifest_hash',a.post_catalogue_manifest_hash,
          'artifact_policy_id',f.artifact_policy_id,'artifact_policy_hash',p.policy_hash,
          'artifact_projection_operation_id',f.artifact_policy_operation_id,
          'artifact_projection_output_digest',f.artifact_policy_output_digest
        ) INTO expected FROM project_guide_setup_finalizations f
        JOIN project_guide_compilations c ON c.id=f.compilation_id AND c.attempt_id=f.attempt_id
        JOIN project_guide_compilation_attempts a ON a.id=c.attempt_id
        LEFT JOIN submission_artifact_policies p ON p.id=f.artifact_policy_id
        WHERE f.id=final_id;
        IF expected IS NULL OR target IS DISTINCT FROM expected
           OR digest IS DISTINCT FROM guide_proposal_hash(expected) THEN
          RAISE EXCEPTION 'guide proposal target custody mismatch' USING ERRCODE='23514';
        END IF;
      END $$;
CREATE FUNCTION public.require_human_actor_profile_reference() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare referenced_id uuid; referenced_kind text;
        begin
          if tg_nargs <> 1 or tg_argv[0] is null
             or not (to_jsonb(new) ? tg_argv[0]) then
            raise exception 'human actor reference trigger is misconfigured'
              using errcode='55000';
          end if;
          referenced_id := (to_jsonb(new) ->> tg_argv[0])::uuid;
          if referenced_id is null then return new; end if;
          select profile.actor_kind into referenced_kind
          from public.actor_profiles profile where profile.id=referenced_id;
          if not found then return new; end if;
          if referenced_kind <> 'human' then
            raise exception 'actor reference must identify a human profile'
              using errcode='23514', constraint='require_human_actor_profile_reference';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.require_outbox_phase_authority() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare phase text; decision_id uuid; previous_id uuid; e audit_events%rowtype;
                actor actor_profiles%rowtype; link actor_identity_links%rowtype;
        begin
          foreach phase in array array['claim','invoke','finalize'] loop
            decision_id := (to_jsonb(new)->>(phase || '_decision_event_id'))::uuid;
            previous_id := case when tg_op='UPDATE' then (to_jsonb(old)->>(phase || '_decision_event_id'))::uuid else null end;
            if previous_id is not null and decision_id is distinct from previous_id then
              raise exception 'outbox phase authority is immutable' using errcode='55000';
            end if;
            if decision_id is null then continue; end if;
            select * into e from audit_events where id=decision_id;
            if e.id is null or e.event_domain is distinct from 'authority'
               or e.event_type is distinct from 'SensitiveAuthorizationAllowed'
               or e.entity_type is distinct from 'authorization_decision'
               or e.entity_id is distinct from e.id or e.actor_ref_kind is distinct from 'actor_profile'
               or e.denial_code is not null or e.matched_grant_id is not null
               or e.action_id is distinct from 'outbox.dispatch'
               or e.permission_id is distinct from 'outbox.dispatch'
               or e.project_id is distinct from new.project_id
               or e.resource_type is distinct from 'outbox_event'
               or e.resource_id is distinct from new.event_id::text
               or e.target_ref_kind is distinct from 'project'
               or e.target_ref_id is distinct from new.project_id::text
               or e.after_facts->>'allowed' is distinct from 'true'
               or e.after_facts->>'resource_context_digest' is distinct from outbox_dispatch_authority_digest(new,phase) then
              raise exception 'outbox phase authority evidence mismatch' using errcode='23514';
            end if;
            select * into actor from actor_profiles where id::text=e.actor_id;
            select * into link from actor_identity_links where actor_profile_id::text=e.actor_id;
            if actor.id is null or actor.actor_kind is distinct from 'service'
               or actor.service_identity is distinct from 'workstream.outbox.dispatcher'
               or link.id is null or link.subject_kind is distinct from 'service' then
              raise exception 'outbox phase authority identity mismatch' using errcode='23514';
            end if;
            if previous_id is null and (actor.status is distinct from 'active' or link.status is distinct from 'active') then
              raise exception 'outbox current dispatcher authority missing' using errcode='23514';
            end if;
          end loop;
          return new;
        end $$;
CREATE FUNCTION public.require_post_policy_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
               OR (o.kind='derive' AND o.target_json->>'predecessor_policy_id'=p.id::text))) THEN
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
CREATE FUNCTION public.require_post_policy_operation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
         OR t->>'policy_id' IS DISTINCT FROM p.id::text
         OR t->>'policy_hash' IS DISTINCT FROM p.policy_hash
         OR t->>'projection_operation_id' IS DISTINCT FROM p.projection_operation_id::text
         OR t->>'predecessor_policy_id' IS DISTINCT FROM p.supersedes_policy_id::text
         OR p.project_id IS DISTINCT FROM a.project_id OR p.guide_id IS DISTINCT FROM a.guide_id
         OR p.guide_version IS DISTINCT FROM t->'proposal'->>'guide_version'
         OR p.source_snapshot_id::text IS DISTINCT FROM t->'proposal'->>'source_snapshot_id'
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
          'identity_link_id',NEW.identity_link_id,'action_id',action,'operation_id',
          NEW.resource_context_json->'locator'->>'operation_id'),
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
         OR e.actor_ref_kind IS DISTINCT FROM 'actor_profile' OR e.actor_id IS DISTINCT FROM NEW.actor_profile_id::text
         OR e.project_id IS DISTINCT FROM NEW.project_id OR e.action_id IS DISTINCT FROM action
         OR e.permission_id IS DISTINCT FROM 'project.effective_policy.manage'
         OR e.resource_type IS DISTINCT FROM 'project_post_submit_checker_policy_mutation'
         OR e.resource_id IS DISTINCT FROM p.id::text OR e.request_id IS NULL
         OR e.correlation_id::text IS DISTINCT FROM NEW.resource_context_json->'locator'->>'operation_id'
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
          'project.effective_policy.manage','project_post_submit_checker_policy_mutation',p.id,
          NEW.resource_context_json->'locator'->>'operation_id',NEW.resource_context_digest);
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
CREATE FUNCTION public.require_pre_submit_attempt_evidence() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
CREATE FUNCTION public.require_pre_submit_result_reconstruction() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
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
END $_$;
CREATE FUNCTION public.require_project_activation_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
CREATE FUNCTION public.require_submission_contribution_stamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE assignment_stamp uuid;
BEGIN
    SELECT submitter_contribution_policy_version_id INTO assignment_stamp
    FROM task_assignments WHERE id=NEW.task_assignment_id AND task_id=NEW.task_id
        AND contributor_id=NEW.contributor_id FOR SHARE;
    IF assignment_stamp IS NULL OR assignment_stamp IS DISTINCT FROM
       NEW.contribution_policy_version_id THEN
        RAISE EXCEPTION 'submission contribution stamp differs from assignment';
    END IF;
    RETURN NEW;
END $$;
CREATE FUNCTION public.set_authority_audit_database_time() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if new.event_domain = 'authority' then
            if new.invalidation_cause_event_id is not null and not exists (
              select 1 from audit_events
              where id = new.invalidation_cause_event_id and event_domain = 'authority'
            ) then
              raise exception 'invalid authority invalidation cause' using errcode = '23503';
            end if;
            new.occurred_at = statement_timestamp();
          else
            new.occurred_at = null;
          end if;
          return new;
        end
        $$;
CREATE FUNCTION public.validate_artifact_binding_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare predecessor artifact_bindings%rowtype;
        begin
            if new.scope_version = 1 then
                return new;
            end if;
            select * into predecessor
              from artifact_bindings where id = new.supersedes_binding_id;
            if not found
               or predecessor.project_id != new.project_id
               or predecessor.resource_type != new.resource_type
               or predecessor.resource_id != new.resource_id
               or predecessor.logical_role != new.logical_role
               or predecessor.scope_version + 1 != new.scope_version then
                raise exception 'artifact binding predecessor is invalid';
            end if;
            return new;
        end;
        $$;
CREATE FUNCTION public.validate_artifact_recovery_attempt() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          source_row artifact_verification_jobs%rowtype;
          retry_row artifact_verification_jobs%rowtype;
          expected_parent uuid;
        begin
          if tg_op = 'DELETE' then
            raise exception 'artifact recovery attempts are append-only' using errcode='55000';
          end if;
          if tg_op = 'UPDATE' and (
            to_jsonb(new) - array['status','terminal_result_code','terminal_audit_event_id',
              'terminal_at','cas_version','updated_at']
            is distinct from
            to_jsonb(old) - array['status','terminal_result_code','terminal_audit_event_id',
              'terminal_at','cas_version','updated_at']
          ) then
            raise exception 'artifact recovery identity is immutable' using errcode='55000';
          end if;
          select * into source_row from artifact_verification_jobs
            where id=new.source_verification_job_id;
          select * into retry_row from artifact_verification_jobs
            where id=new.retry_verification_job_id;
          if source_row.id is null or retry_row.id is null
             or source_row.status <> 'provider_unavailable'
             or source_row.terminal_result_code <> 'provider_unavailable'
             or source_row.terminal_at is null or source_row.next_run_at is not null
             or source_row.executor_id is not null
             or source_row.attempt_count < source_row.maximum_attempts
             or retry_row.parent_verification_job_id <> source_row.id
             or retry_row.originating_put_attempt_id <> source_row.originating_put_attempt_id
             or retry_row.replica_id <> source_row.replica_id then
            raise exception 'invalid artifact recovery verification lineage' using errcode='23514';
          end if;
          if (tg_op = 'INSERT' and (retry_row.status <> 'pending' or retry_row.attempt_count <> 0))
             or (tg_op = 'UPDATE' and (
               retry_row.status <> new.terminal_result_code or retry_row.terminal_at is null
             )) then
            raise exception 'invalid artifact recovery retry state' using errcode='23514';
          end if;
          select id into expected_parent from artifact_recovery_attempts
            where retry_verification_job_id=source_row.id;
          if new.parent_recovery_attempt_id is distinct from expected_parent then
            raise exception 'invalid artifact recovery parent chain' using errcode='23514';
          end if;
          if not exists (
            select 1 from audit_events where id=new.initiation_audit_event_id
              and entity_type='artifact_recovery_attempt' and entity_id=new.id
              and event_type='ArtifactRecoveryInitiated'
          ) then
            raise exception 'invalid artifact recovery initiation audit' using errcode='23514';
          end if;
          if new.terminal_audit_event_id is not null and not exists (
            select 1 from audit_events where id=new.terminal_audit_event_id
              and entity_type='artifact_recovery_attempt' and entity_id=new.id
              and event_type='ArtifactRecoveryCompleted'
          ) then
            raise exception 'invalid artifact recovery terminal audit' using errcode='23514';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.validate_artifact_verification_lineage() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if (
            old.parent_verification_job_id is not null
            or exists(
              select 1 from artifact_recovery_attempts
              where source_verification_job_id = old.id
                 or retry_verification_job_id = old.id
            )
          ) and (
            old.originating_put_attempt_id is distinct from new.originating_put_attempt_id
            or old.replica_id is distinct from new.replica_id
            or old.parent_verification_job_id is distinct from new.parent_verification_job_id
          ) then
            raise exception 'artifact verification lineage is immutable' using errcode='55000';
          end if;
          return new;
        end $$;
CREATE FUNCTION public.validate_bootstrap_authority_state() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare control authority_control%rowtype;
                bootstrap_count bigint;
                referenced_bootstrap boolean;
        begin
          select * into control from authority_control where id=1;
          if not found then
            raise exception 'bootstrap grant/control invariant violated' using errcode='23514';
          end if;
          select count(*) into bootstrap_count from admin_role_grants
          where granted_by_system_principal='workstream:system:bootstrap';
          referenced_bootstrap := exists(
            select 1 from admin_role_grants
            where id=control.bootstrap_grant_id
              and granted_by_system_principal='workstream:system:bootstrap'
          );
          if (not control.bootstrap_completed and
              (control.bootstrap_grant_id is not null or control.version <> 0 or bootstrap_count <> 0))
             or (control.bootstrap_completed and
              (control.bootstrap_grant_id is null or control.version <> 1
               or bootstrap_count <> 1 or not referenced_bootstrap)) then
            raise exception 'bootstrap grant/control invariant violated' using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_canonical_actor_link() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare profile_row actor_profiles%rowtype; link_count integer;
        begin
          if tg_table_name='actor_profiles' then
            select count(*) into link_count from actor_identity_links where actor_profile_id=new.id;
            if link_count <> 1 then raise exception 'actor profile requires exactly one identity link' using errcode='23514'; end if;
            if not exists(select 1 from actor_identity_links where actor_profile_id=new.id and subject_kind=new.actor_kind) then
              raise exception 'actor and identity kind mismatch' using errcode='23514';
            end if;
          else
            select * into profile_row from actor_profiles where id=new.actor_profile_id;
            if not found or profile_row.actor_kind <> new.subject_kind then
              raise exception 'actor and identity kind mismatch' using errcode='23514';
            end if;
          end if; return new;
        end $$;
CREATE FUNCTION public.validate_contribution_policy_graph() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        begin
          if exists (
            select 1 from contribution_policy_versions v
            where v.status in ('published','retired') and (
              (select count(*) from contribution_rules r
               where r.contribution_policy_version_id=v.id
                 and r.contribution_type='accepted_submission') <> 1
              or
              (select count(*) from contribution_rules r
               where r.contribution_policy_version_id=v.id
                 and r.contribution_type='completed_review') <> 1
              or exists (
                select 1 from contribution_rules r
                where r.contribution_policy_version_id=v.id and (
                  (r.compensation_mode='unpaid' and
                    (select count(*) from contribution_award_definitions d
                     where d.contribution_rule_id=r.id) <> 0)
                  or
                  (r.compensation_mode='compensated' and
                    (select count(*) from contribution_award_definitions d
                     where d.contribution_rule_id=r.id) not between 1 and 2)
                )
              )
            )
          ) then
            raise exception 'published contribution policy graph is incomplete'
              using errcode='23514';
          end if;
          if exists (
            select 1 from contribution_policies p
            left join contribution_policy_versions v
              on v.id=p.current_published_version_id
             and v.contribution_policy_id=p.id
             and v.project_id=p.project_id
            where p.status='active' and (v.id is null or v.status <> 'published')
          ) then
            raise exception 'active contribution policy selector is invalid'
              using errcode='23514';
          end if;
          return null;
        end;
        $$;
CREATE FUNCTION public.validate_guide_mutation_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare reservation guide_mutation_idempotency_records%rowtype;
                evidence audit_events%rowtype;
                actor_id uuid; link_id uuid; grant_id uuid; action_value text;
                scope_type text; scope_project uuid; decision_id uuid;
                product_project uuid; product_resource uuid; product_generation integer;
        begin

          if tg_table_name='project_setup_runs' then
            if new.authorization_action_id='project.guide_compilation.correction.request' then
              if not exists(select 1 from project_guide_proposal_corrections c
                 where c.successor_setup_run_id=new.id and c.project_id=new.project_id
                   and c.guide_id=new.guide_id and c.successor_setup_generation=new.setup_generation
                   and c.actor_profile_id=new.authorized_by_actor_profile_id
                   and c.identity_link_id=new.authorized_via_identity_link_id
                   and c.admin_role_grant_id=new.authorized_by_admin_role_grant_id
                   and c.authorization_decision_event_id=new.authorization_decision_event_id
                   and new.authorization_scope_type='project'
                   and new.authorization_scope_project_id=new.project_id) then
                raise exception 'correction setup source custody mismatch' using errcode='23514';
              end if;
              return null;
            end if;
          end if;

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
          if tg_table_name='guide_mutation_idempotency_records' then
            select * into reservation from guide_mutation_idempotency_records where id=new.id;
            if reservation.status<>'committed' then
              raise exception 'pending guide mutation custody cannot commit' using errcode='23514';
            end if;
            if reservation.action_id in ('project.guide.create','project.guide.update') then
              select last_mutated_by_actor_profile_id,last_mutated_via_identity_link_id,
                     last_mutated_by_admin_role_grant_id,last_mutation_action_id,
                     last_mutation_scope_type,last_mutation_scope_project_id,
                     last_authorization_decision_event_id,project_id,id,mutation_generation
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_resource,product_generation
                from project_guides where id=reservation.resource_id;
            else
              select created_by_actor_profile_id,created_via_identity_link_id,
                     created_by_admin_role_grant_id,creation_action_id,
                     creation_scope_type,creation_scope_project_id,
                     authorization_decision_event_id,project_id,id,creation_generation
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_resource,product_generation
                from guide_source_snapshots where id=reservation.resource_id;
            end if;
          elsif tg_table_name='project_guides' then
            if tg_op='UPDATE'
               and (new.change_summary is distinct from old.change_summary)
               and (new.mutation_generation is not distinct from old.mutation_generation
                    or new.last_authorization_decision_event_id
                       is not distinct from old.last_authorization_decision_event_id) then
              raise exception 'guide content mutation requires fresh custody' using errcode='23514';
            end if;
            if new.mutation_generation is null then
              if tg_op='INSERT' then
                raise exception 'new guides require mutation authority' using errcode='23514';
              end if;
              return null;
            end if;
            actor_id:=new.last_mutated_by_actor_profile_id;
            link_id:=new.last_mutated_via_identity_link_id;
            grant_id:=new.last_mutated_by_admin_role_grant_id;
            action_value:=new.last_mutation_action_id;
            scope_type:=new.last_mutation_scope_type;
            scope_project:=new.last_mutation_scope_project_id;
            decision_id:=new.last_authorization_decision_event_id;
            product_project:=new.project_id; product_resource:=new.id;
            product_generation:=new.mutation_generation;
            select * into reservation from guide_mutation_idempotency_records
              where resource_id=new.id and action_id=new.last_mutation_action_id
                and operation_generation=new.mutation_generation and status='committed';
          elsif tg_table_name='guide_source_snapshots' then
            if tg_op='UPDATE'
               and (new.project_id,new.guide_id,new.guide_version,
                    new.manifest_schema_version,new.manifest_json::jsonb,new.bundle_hash,new.captured_by)
                   is distinct from
                   (old.project_id,old.guide_id,old.guide_version,
                    old.manifest_schema_version,old.manifest_json::jsonb,old.bundle_hash,old.captured_by) then
              raise exception 'guide source snapshot content is immutable' using errcode='23514';
            end if;
            if new.creation_generation is null then
              raise exception 'new source snapshots require creation authority' using errcode='23514';
            end if;
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            action_value:=new.creation_action_id;
            scope_type:=new.creation_scope_type;
            scope_project:=new.creation_scope_project_id;
            decision_id:=new.authorization_decision_event_id;
            product_project:=new.project_id; product_resource:=new.id;
            product_generation:=new.creation_generation;
            select * into reservation from guide_mutation_idempotency_records
              where resource_id=new.id and action_id='project.guide_source_snapshot.create'
                and operation_generation=new.creation_generation and status='committed';
          else
            if new.authorization_action_id is null then return null; end if;
            actor_id:=new.authorized_by_actor_profile_id;
            link_id:=new.authorized_via_identity_link_id;
            grant_id:=new.authorized_by_admin_role_grant_id;
            action_value:=new.authorization_action_id;
            scope_type:=new.authorization_scope_type;
            scope_project:=new.authorization_scope_project_id;
            decision_id:=new.authorization_decision_event_id;
            product_project:=new.project_id; product_resource:=new.source_snapshot_id;
            select * into reservation from guide_mutation_idempotency_records
              where setup_run_id=new.id and action_id='project.guide_source_snapshot.create'
                and status='committed';
            product_generation:=reservation.operation_generation;
          end if;
          if reservation.id is null or product_resource is null
             or reservation.actor_profile_id is distinct from actor_id
             or reservation.identity_link_id is distinct from link_id
             or reservation.action_id is distinct from action_value
             or reservation.project_id is distinct from product_project
             or reservation.resource_id is distinct from product_resource
             or reservation.operation_generation is distinct from product_generation
             or scope_type not in ('system','project')
             or (scope_type='project' and scope_project is distinct from product_project)
             or (scope_type='system' and scope_project is not null) then
            raise exception 'guide mutation custody mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events where id=decision_id;
          if evidence.id is null
             or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from actor_id::text
             or evidence.matched_grant_id is distinct from grant_id::text
             or evidence.permission_id is distinct from 'project.guide.manage'
             or evidence.action_id is distinct from action_value
             or evidence.resource_type is distinct from 'project'
             or evidence.resource_id is distinct from product_project::text
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from product_project::text
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'guide mutation evidence mismatch' using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_guide_source_snapshot_items() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare expected jsonb; actual jsonb; reservation guide_mutation_idempotency_records%rowtype;
        begin
          select snapshot.manifest_json::jsonb->'items' into expected
            from guide_source_snapshots snapshot where snapshot.id=new.source_snapshot_id;
          if expected is null then
            raise exception 'guide source snapshot item parent is unavailable' using errcode='23514';
          end if;
          select coalesce(jsonb_agg(jsonb_build_object(
                   'item_id',id,'item_order',item_order,'source_kind',source_kind,
                   'source_label',source_label,'ingestion_adapter',ingestion_adapter,
                   'media_type',media_type) order by item_order),'[]'::jsonb)
            into actual from guide_source_snapshot_items
            where source_snapshot_id=new.source_snapshot_id;
          if actual is distinct from expected then
            raise exception 'guide source snapshot items do not match manifest' using errcode='23514';
          end if;
          select r.* into reservation from guide_mutation_idempotency_records r
            join guide_source_snapshots s on s.id=r.resource_id
            where s.id=new.source_snapshot_id
              and r.action_id='project.guide_source_snapshot.create'
              and r.operation_generation=s.creation_generation and r.status='committed';
          if reservation.id is null then
            raise exception 'guide source snapshot item custody mismatch' using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_guide_task_example_source_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      declare source_guide project_guides%rowtype; source_snapshot guide_source_snapshots%rowtype; manifest jsonb;
      begin
        if tg_table_name='guide_source_snapshots' then
          if tg_op='UPDATE' then return new; end if;
          select * into source_guide from project_guides
            where id=new.guide_id and project_id=new.project_id and version=new.guide_version;
          manifest := new.manifest_json::jsonb;
          if source_guide.id is null or not project_guide_task_examples_valid(source_guide.task_examples::jsonb)
             or new.manifest_schema_version is distinct from 'guide_source_snapshot.task_examples'
             or manifest->>'schema_version' is distinct from new.manifest_schema_version
             or manifest->>'task_examples_hash' is distinct from source_guide.task_examples_hash
             or manifest->'task_examples_count' is distinct from to_jsonb(jsonb_array_length(source_guide.task_examples::jsonb))
             or new.bundle_hash is distinct from ('sha256:' || encode(sha256(convert_to(
                project_guide_projection_canonical_json(manifest),'UTF8')),'hex')) then
            raise exception 'guide snapshot task example lineage mismatch' using errcode='23514';
          end if;
        else
          select * into source_snapshot from guide_source_snapshots where id=new.source_snapshot_id;
          if source_snapshot.id is null or
             (source_snapshot.project_id,source_snapshot.guide_id,source_snapshot.guide_version,source_snapshot.bundle_hash)
             is distinct from (new.project_id,new.guide_id,new.guide_version,new.source_snapshot_hash) then
            raise exception 'guide setup snapshot ownership mismatch' using errcode='23514';
          end if;
        end if;
        return new;
      end $$;
CREATE FUNCTION public.validate_guide_task_examples_create_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      declare reservation guide_mutation_idempotency_records%rowtype; resource jsonb; expected text;
      begin
        select * into reservation from guide_mutation_idempotency_records
          where resource_id=new.id and action_id='project.guide.create' and operation_generation=1
            and status='committed';
        if reservation.id is null then
          raise exception 'guide example creation custody missing' using errcode='23514';
        end if;
        resource := jsonb_build_object(
          'resource_type','project_guide_mutation','resource_id',new.id,
          'operation_id',reservation.operation_id,'scope_project_id',new.project_id,
          'guide_id',new.id,'target_kind','create','guide_exists',false,'operation_generation',1,
          'request_digest',reservation.request_digest,'task_examples_hash',new.task_examples_hash,
          'task_examples_count',jsonb_array_length(new.task_examples::jsonb));
        expected := 'sha256:' || encode(sha256(convert_to(project_guide_projection_canonical_json(
          jsonb_build_object('resource_context',resource)),'UTF8')),'hex');
        if reservation.resource_context_digest is distinct from expected
           or reservation.response_json::jsonb->'task_examples' is distinct from new.task_examples::jsonb
           or reservation.response_json::jsonb->>'task_examples_hash' is distinct from new.task_examples_hash then
          raise exception 'guide example creation commitment mismatch' using errcode='23514';
        end if;
        return null;
      end $$;
CREATE FUNCTION public.validate_linked_authority_event() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare record_row authority_idempotency_records%rowtype;
                cause_row audit_events%rowtype; expected_permission text;
                expected_resource text; expected_invalidation_resource text;
                expected_invalidation_id text; valid_success boolean;
        begin
          if new.event_domain <> 'authority' then return new; end if;
          valid_success := new.event_type in (
            'ServiceActorProvisioned','AdminRoleGrantIssued','AdminRoleGrantRevoked',
            'ProjectRoleQualificationSnapshotCaptured','ProjectRoleGrantIssued','ProjectRoleGrantRevoked',
            'ActorProfileSuspended','ActorProfileReactivated','ActorProfileDeactivated',
            'ActorIdentityLinkRevoked','ActorIdentityLinkReactivated');
          if not valid_success and new.event_type <> 'AuthorityInvalidationRequested' then
            if new.idempotency_reference is not null then
              raise exception 'invalid authority idempotency event' using errcode='23514';
            end if; return new;
          end if;
          if new.idempotency_reference is null then
            raise exception 'authority event requires idempotency reference' using errcode='23514';
          end if;
          select * into record_row from authority_idempotency_records
          where id=new.idempotency_reference and actor_ref_kind=new.actor_ref_kind and actor_ref=new.actor_id;
          if not found then raise exception 'invalid authority idempotency reference' using errcode='23503'; end if;
          if record_row.status <> 'pending' then raise exception 'committed authority idempotency is closed' using errcode='23514'; end if;
          expected_permission := case record_row.operation
            when 'service_actor.create' then 'actor.service.provision'
            when 'admin_role_grant.issue' then 'admin_role.grant'
            when 'admin_role_grant.revoke' then 'admin_role.revoke'
            when 'project_role_grant.issue' then 'project.role_grant.manage'
            when 'project_role_grant.revoke' then 'project.role_grant.manage'
            when 'actor_profile.suspend' then 'actor.profile.suspend'
            when 'actor_profile.reactivate' then 'actor.profile.reactivate'
            when 'actor_profile.deactivate' then 'actor.profile.deactivate'
            when 'actor_identity_link.revoke' then 'actor.identity_link.revoke'
            when 'actor_identity_link.reactivate' then 'actor.identity_link.reactivate' end;
          expected_resource := case
            when record_row.operation='service_actor.create' or record_row.operation like 'actor_profile.%' then 'actor_profile'
            when record_row.operation like 'admin_role_grant.%' then 'admin_role_grant'
            when record_row.operation like 'project_role_grant.%' then 'project_role_grant'
            else 'actor_identity_link' end;
          if new.permission_id <> expected_permission or new.resource_id is null then
            raise exception 'authority event does not match operation' using errcode='23514';
          end if;
          if new.event_type='ProjectRoleQualificationSnapshotCaptured' then
            if record_row.operation <> 'project_role_grant.issue'
               or new.resource_type <> 'qualification_snapshot'
               or new.entity_type <> 'qualification_snapshot'
               or new.entity_id::text <> new.resource_id
               or new.target_ref_kind is distinct from 'qualification_snapshot'
               or new.target_ref_id is distinct from new.resource_id
               or new.invalidation_cause_event_id is not null
               or new.invalidation_target_kind is not null
               or new.invalidation_target_ref is not null
               or exists(select 1 from audit_events where idempotency_reference=record_row.id) then
              raise exception 'invalid project role qualification evidence' using errcode='23514';
            end if;
          elsif record_row.operation='project_role_grant.issue'
                and new.event_type='ProjectRoleGrantIssued' then
            select * into cause_row from audit_events
            where idempotency_reference=record_row.id
              and event_type='ProjectRoleQualificationSnapshotCaptured';
            if not found
               or (select count(*) from audit_events where idempotency_reference=record_row.id) <> 1
               or cause_row.request_id is distinct from new.request_id
               or cause_row.correlation_id is distinct from new.correlation_id
               or cause_row.actor_ref_kind is distinct from new.actor_ref_kind
               or cause_row.actor_id is distinct from new.actor_id
               or cause_row.permission_id is distinct from new.permission_id
               or cause_row.project_id is distinct from new.project_id
               or cause_row.target_actor_ref_kind is distinct from new.target_actor_ref_kind
               or cause_row.target_actor_ref is distinct from new.target_actor_ref
               or cause_row.matched_grant_id is distinct from new.matched_grant_id
               or new.resource_type <> 'project_role_grant'
               or new.entity_type <> 'project_role_grant'
               or new.entity_id::text <> new.resource_id
               or new.target_ref_kind is distinct from 'project_role_grant'
               or new.target_ref_id is distinct from new.resource_id
               or new.invalidation_cause_event_id is not null
               or new.invalidation_target_kind is not null
               or new.invalidation_target_ref is not null then
              raise exception 'invalid project role issue evidence' using errcode='23514';
            end if;
          elsif record_row.operation='project_role_grant.revoke'
                and new.event_type='AuthorityInvalidationRequested' then
            select * into cause_row from audit_events where id=new.invalidation_cause_event_id;
            if not found or cause_row.event_type <> 'ProjectRoleGrantRevoked'
               or cause_row.idempotency_reference is distinct from record_row.id
               or cause_row.actor_ref_kind is distinct from new.actor_ref_kind
               or cause_row.actor_id is distinct from new.actor_id
               or cause_row.permission_id is distinct from new.permission_id
               or cause_row.request_id is distinct from new.request_id
               or cause_row.correlation_id is distinct from new.correlation_id
               or cause_row.project_id is distinct from new.project_id
               or cause_row.target_actor_ref_kind is distinct from 'actor_profile'
               or cause_row.target_actor_ref_kind is distinct from new.target_actor_ref_kind
               or cause_row.target_actor_ref is distinct from new.target_actor_ref
               or cause_row.resource_type <> 'project_role_grant'
               or cause_row.target_ref_kind <> 'project_role_grant'
               or cause_row.target_ref_id is distinct from cause_row.resource_id
               or new.resource_type <> 'project_role_grant'
               or new.resource_id is distinct from cause_row.resource_id
               or new.target_ref_kind is distinct from 'project_role_grant'
               or new.target_ref_id is distinct from cause_row.resource_id
               or new.invalidation_target_kind <> 'project_role_grant'
               or new.invalidation_target_ref is distinct from cause_row.resource_id
               or new.entity_type <> 'authority_invalidation' or new.entity_id <> new.id
               or new.before_facts::jsonb->>'effective' <> 'true'
               or new.after_facts::jsonb->>'effective' <> 'false'
               or new.before_facts::jsonb->>'role' not in ('submitter','reviewer')
               or new.before_facts::jsonb->>'role' is distinct from new.after_facts::jsonb->>'role'
               or new.before_facts::jsonb->>'scope_type' <> 'project'
               or new.before_facts::jsonb->>'scope_id' is distinct from new.project_id::text
               or new.before_facts::jsonb->>'scope_id' is distinct from new.after_facts::jsonb->>'scope_id'
               or new.before_facts::jsonb->>'future_obligation' is distinct from new.after_facts::jsonb->>'future_obligation'
               or (new.before_facts::jsonb->>'role'='submitter' and new.before_facts::jsonb->>'future_obligation'<>'auth13_assignment')
               or (new.before_facts::jsonb->>'role'='reviewer' and new.before_facts::jsonb->>'future_obligation'<>'rev_reviewer_obligation') then
              raise exception 'invalid project role revoke invalidation' using errcode='23514';
            end if;
          elsif record_row.operation='project_role_grant.issue'
                and new.event_type='AuthorityInvalidationRequested' then
            raise exception 'project role issue forbids invalidation' using errcode='23514';
          elsif new.event_type='AuthorityInvalidationRequested' then
            select * into cause_row from audit_events where id=new.invalidation_cause_event_id;
            expected_invalidation_resource := case when record_row.operation in ('admin_role_grant.issue','admin_role_grant.revoke','actor_identity_link.revoke','actor_identity_link.reactivate') then 'actor_profile' else expected_resource end;
            expected_invalidation_id := case when record_row.operation in ('admin_role_grant.issue','admin_role_grant.revoke','actor_identity_link.revoke','actor_identity_link.reactivate') then cause_row.target_actor_ref else cause_row.resource_id end;
            if not found or cause_row.idempotency_reference is distinct from record_row.id
               or cause_row.actor_ref_kind is distinct from new.actor_ref_kind
               or cause_row.actor_id is distinct from new.actor_id
               or cause_row.permission_id is distinct from new.permission_id
               or cause_row.resource_type is distinct from expected_resource
               or new.resource_type is distinct from expected_invalidation_resource
               or new.resource_id is distinct from expected_invalidation_id
               or new.invalidation_target_kind is distinct from expected_invalidation_resource
               or new.invalidation_target_ref is distinct from expected_invalidation_id
               or cause_row.target_ref_kind is distinct from cause_row.resource_type
               or cause_row.target_ref_id is distinct from cause_row.resource_id
               or cause_row.request_id is distinct from new.request_id
               or cause_row.correlation_id is distinct from new.correlation_id
               or cause_row.project_id is distinct from new.project_id
               or new.entity_type <> 'authority_invalidation' or new.entity_id <> new.id
               or (record_row.operation in ('admin_role_grant.issue','admin_role_grant.revoke','actor_identity_link.revoke','actor_identity_link.reactivate') and (cause_row.target_actor_ref_kind <> 'actor_profile' or cause_row.target_actor_ref is null))
               or (record_row.operation in ('admin_role_grant.issue','actor_profile.reactivate','actor_identity_link.reactivate') and
                   (new.before_facts::jsonb <> '{"effective": false}'::jsonb or new.after_facts::jsonb <> '{"effective": true}'::jsonb))
               or (record_row.operation not in ('admin_role_grant.issue','actor_profile.reactivate','actor_identity_link.reactivate') and
                   (new.before_facts::jsonb <> '{"effective": true}'::jsonb or new.after_facts::jsonb <> '{"effective": false}'::jsonb))
               or not (
                 (record_row.operation='service_actor.create' and cause_row.event_type='ServiceActorProvisioned') or
                 (record_row.operation='admin_role_grant.issue' and cause_row.event_type='AdminRoleGrantIssued') or
                 (record_row.operation='admin_role_grant.revoke' and cause_row.event_type='AdminRoleGrantRevoked') or
                 (record_row.operation='project_role_grant.issue' and cause_row.event_type in ('ProjectRoleGrantIssued')) or
                 (record_row.operation='project_role_grant.revoke' and cause_row.event_type='ProjectRoleGrantRevoked') or
                 (record_row.operation='actor_profile.suspend' and cause_row.event_type='ActorProfileSuspended') or
                 (record_row.operation='actor_profile.reactivate' and cause_row.event_type='ActorProfileReactivated') or
                 (record_row.operation='actor_profile.deactivate' and cause_row.event_type='ActorProfileDeactivated') or
                 (record_row.operation='actor_identity_link.revoke' and cause_row.event_type='ActorIdentityLinkRevoked') or
                 (record_row.operation='actor_identity_link.reactivate' and cause_row.event_type='ActorIdentityLinkReactivated')) then
              raise exception 'invalid linked authority cause' using errcode='23514';
            end if;
          else
            if new.resource_type <> expected_resource or new.entity_type <> expected_resource
               or new.entity_id::text <> new.resource_id or new.target_ref_kind is distinct from expected_resource
               or new.target_ref_id is distinct from new.resource_id
               or new.invalidation_cause_event_id is not null
               or new.invalidation_target_kind is not null or new.invalidation_target_ref is not null
               or not (
                 (record_row.operation='service_actor.create' and new.event_type='ServiceActorProvisioned') or
                 (record_row.operation='admin_role_grant.issue' and new.event_type='AdminRoleGrantIssued') or
                 (record_row.operation='admin_role_grant.revoke' and new.event_type='AdminRoleGrantRevoked') or
                 (record_row.operation='project_role_grant.issue' and new.event_type in ('ProjectRoleGrantIssued')) or
                 (record_row.operation='project_role_grant.revoke' and new.event_type='ProjectRoleGrantRevoked') or
                 (record_row.operation='actor_profile.suspend' and new.event_type='ActorProfileSuspended') or
                 (record_row.operation='actor_profile.reactivate' and new.event_type='ActorProfileReactivated') or
                 (record_row.operation='actor_profile.deactivate' and new.event_type='ActorProfileDeactivated') or
                 (record_row.operation='actor_identity_link.revoke' and new.event_type='ActorIdentityLinkRevoked') or
                 (record_row.operation='actor_identity_link.reactivate' and new.event_type='ActorIdentityLinkReactivated')) then
              raise exception 'authority success event does not match operation' using errcode='23514';
            end if;
          end if; return new;
        end $$;
CREATE FUNCTION public.validate_policy_mutation_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare reservation policy_mutation_idempotency_records%rowtype;
                evidence audit_events%rowtype;
                actor_id uuid; link_id uuid; grant_id uuid; action_value text;
                scope_type text; scope_project uuid; decision_id uuid;
                product_project uuid; product_guide uuid; product_id uuid;
                product_generation integer;
                product_hash text; predecessor_id uuid; predecessor_hash text;
                selector_id uuid; selector_generation integer; selector_hash text;
                predecessor_valid boolean;
        begin
          if tg_table_name='policy_mutation_idempotency_records' then
            select * into reservation from policy_mutation_idempotency_records where id=new.id;
            if reservation.status<>'committed' then
              raise exception 'pending policy mutation custody cannot commit' using errcode='23514';
            end if;
            if reservation.action_id='project.review_policy.update' then
              select created_by_actor_profile_id,created_via_identity_link_id,
                     created_by_admin_role_grant_id,creation_action_id,
                     creation_scope_type,creation_scope_project_id,
                     authorization_decision_event_id,p.project_id,g.id,p.id,
                     p.policy_generation,p.policy_hash,p.supersedes_policy_id,
                     p.predecessor_policy_hash,g.selected_review_policy_id,
                     g.selected_review_policy_generation,g.selected_review_policy_hash
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_guide,product_id,product_generation,
                     product_hash,predecessor_id,predecessor_hash,selector_id,
                     selector_generation,selector_hash
                from review_policies p join project_guides g
                  on g.project_id=p.project_id and g.version=p.guide_version
                where p.id=reservation.policy_id and g.id=reservation.guide_id;
            else
              select created_by_actor_profile_id,created_via_identity_link_id,
                     created_by_admin_role_grant_id,creation_action_id,
                     creation_scope_type,creation_scope_project_id,
                     authorization_decision_event_id,p.project_id,g.id,p.id,
                     p.policy_generation,p.policy_hash,p.supersedes_policy_id,
                     p.predecessor_policy_hash,g.selected_revision_policy_id,
                     g.selected_revision_policy_generation,g.selected_revision_policy_hash
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_guide,product_id,product_generation,
                     product_hash,predecessor_id,predecessor_hash,selector_id,
                     selector_generation,selector_hash
                from revision_policies p join project_guides g
                  on g.project_id=p.project_id and g.version=p.guide_version
                where p.id=reservation.policy_id and g.id=reservation.guide_id;
            end if;
          else
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            action_value:=new.creation_action_id;
            scope_type:=new.creation_scope_type;
            scope_project:=new.creation_scope_project_id;
            decision_id:=new.authorization_decision_event_id;
            product_project:=new.project_id; product_id:=new.id;
            product_generation:=new.policy_generation; product_hash:=new.policy_hash;
            predecessor_id:=new.supersedes_policy_id;
            predecessor_hash:=new.predecessor_policy_hash;
            if tg_table_name='review_policies' then
              select g.id,g.selected_review_policy_id,g.selected_review_policy_generation,
                     g.selected_review_policy_hash
                into product_guide,selector_id,selector_generation,selector_hash
                from project_guides g
                where g.project_id=new.project_id and g.version=new.guide_version;
            else
              select g.id,g.selected_revision_policy_id,g.selected_revision_policy_generation,
                     g.selected_revision_policy_hash
                into product_guide,selector_id,selector_generation,selector_hash
                from project_guides g
                where g.project_id=new.project_id and g.version=new.guide_version;
            end if;
            select r.* into reservation from policy_mutation_idempotency_records r
              where r.policy_id=new.id and r.action_id=new.creation_action_id
                and r.policy_generation=new.policy_generation and r.status='committed';
          end if;
          if reservation.id is null or product_id is null
             or reservation.actor_profile_id is distinct from actor_id
             or reservation.identity_link_id is distinct from link_id
             or reservation.action_id is distinct from action_value
             or reservation.project_id is distinct from product_project
             or reservation.guide_id is distinct from product_guide
             or reservation.policy_id is distinct from product_id
             or reservation.policy_generation is distinct from product_generation
             or reservation.policy_hash is distinct from product_hash
             or selector_id is distinct from product_id
             or selector_generation is distinct from product_generation
             or selector_hash is distinct from product_hash
             or scope_type not in ('system','project')
             or (scope_type='project' and scope_project is distinct from product_project)
             or (scope_type='system' and scope_project is not null) then
            raise exception 'policy mutation custody mismatch' using errcode='23514';
          end if;
          if product_generation=1 then
            predecessor_valid:=predecessor_id is null and predecessor_hash is null;
          elsif reservation.action_id='project.review_policy.update' then
            select exists(select 1 from review_policies prior
              where prior.id=predecessor_id and prior.project_id=product_project
                and prior.guide_version=(select version from project_guides where id=product_guide)
                and prior.policy_generation=product_generation-1
                and prior.policy_hash=predecessor_hash) into predecessor_valid;
          else
            select exists(select 1 from revision_policies prior
              where prior.id=predecessor_id and prior.project_id=product_project
                and prior.guide_version=(select version from project_guides where id=product_guide)
                and prior.policy_generation=product_generation-1
                and prior.policy_hash=predecessor_hash) into predecessor_valid;
          end if;
          if predecessor_valid is not true then
            raise exception 'policy mutation lineage mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events where id=decision_id;
          if evidence.id is null or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from actor_id::text
             or evidence.matched_grant_id is distinct from grant_id::text
             or evidence.permission_id is distinct from 'project.review_policy.manage'
             or evidence.action_id is distinct from action_value
             or evidence.resource_type is distinct from 'project'
             or evidence.resource_id is distinct from product_project::text
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from product_project::text
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'policy mutation evidence mismatch' using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_project_create_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
        declare project_row projects%rowtype; reservation project_create_idempotency_records%rowtype;
                evidence audit_events%rowtype;
        begin
          if tg_table_name = 'projects' then
            if tg_op = 'INSERT' and new.status is distinct from 'draft' then
              raise exception 'new projects must be draft' using errcode='23514';
            end if;
            if tg_op = 'INSERT' and new.creation_action_id is null then
              raise exception 'new projects require creation authority' using errcode='23514';
            end if;
            if new.creation_action_id is null then return null; end if;
            project_row := new;
            select * into reservation from project_create_idempotency_records
              where project_id=project_row.id and status='committed';
          else
            select * into reservation from project_create_idempotency_records
              where id=new.id;
            if reservation.status <> 'committed' then
              raise exception 'pending project create reservation cannot commit' using errcode='23514';
            end if;
            select * into project_row from projects where id=reservation.project_id;
          end if;
          if project_row.id is null or reservation.id is null
             or project_row.created_by_actor_profile_id
                is distinct from reservation.actor_profile_id
             or project_row.created_via_identity_link_id
                is distinct from reservation.identity_link_id
             or project_row.creation_action_id is distinct from reservation.action_id then
            raise exception 'project create custody mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events
            where id=project_row.authorization_decision_event_id;
          if evidence.id is null
             or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from project_row.created_by_actor_profile_id::text
             or evidence.matched_grant_id
                is distinct from project_row.created_by_admin_role_grant_id::text
             or evidence.permission_id is distinct from 'project.create'
             or evidence.action_id is distinct from 'project.create'
             or evidence.resource_type is distinct from 'project_create_operation'
             or evidence.resource_id is distinct from reservation.operation_id::text
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from project_row.id::text
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or coalesce(
                  evidence.after_facts->>'resource_context_digest'
                    !~ '^sha256:[0-9a-f]{64}$',
                  true
                ) then
            raise exception 'project create evidence mismatch' using errcode='23514';
          end if;
          return null;
        end $_$;
CREATE FUNCTION public.validate_project_setup_finalization_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    declare s project_setup_runs%rowtype;
    declare receipt project_guide_setup_finalizations%rowtype;
    declare selected_setup uuid;
    declare owned boolean;
    begin
      if tg_table_name='project_setup_runs' then selected_setup := new.id;
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
CREATE FUNCTION public.validate_review_active_lease() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          queue_row review_queue_entries%rowtype;
          active_count integer;
        begin
          if tg_table_name='review_queue_entries' then
            queue_row := new;
          else
            select * into queue_row from review_queue_entries
             where id=coalesce(new.review_queue_entry_id,old.review_queue_entry_id);
          end if;
          if not found and tg_table_name='review_leases' then
            raise exception 'review lease queue is missing' using errcode='23514';
          end if;
          select count(*) into active_count from review_leases
           where review_queue_entry_id=queue_row.id and status='active';
          if queue_row.queue_state='leased' then
            if queue_row.active_lease_id is null or active_count <> 1 or not exists(
              select 1 from review_leases where id=queue_row.active_lease_id
               and review_queue_entry_id=queue_row.id and status='active'
            ) then
              raise exception 'leased queue must identify its active lease' using errcode='23514';
            end if;
          elsif queue_row.active_lease_id is not null or active_count <> 0 then
            raise exception 'non-leased queue cannot retain an active lease' using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_submission_policy_authority_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare reservation submission_policy_mutation_idempotency_records%rowtype;
                evidence audit_events%rowtype;
                actor_id uuid; link_id uuid; grant_id uuid; service_id varchar;
                action_value varchar; decision_id uuid; product_project uuid;
                product_id uuid; approval_outputs_valid boolean;
        begin
          if tg_table_name='submission_policy_mutation_idempotency_records' then
            if new.status='pending' then return null; end if;
            reservation:=new;
            select project_id,id,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approved_by_actor_profile_id else created_by_actor_profile_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approved_via_identity_link_id else created_via_identity_link_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approved_by_admin_role_grant_id
                        else created_by_admin_role_grant_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then null else created_by_service_identity end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approval_action_id else creation_action_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approval_decision_event_id else creation_decision_event_id end
              into product_project,product_id,actor_id,link_id,grant_id,service_id,
                   action_value,decision_id
              from submission_artifact_policies where id=reservation.committed_policy_id;
            if reservation.action_id='project.submission_artifact_policy.approve' then
              select exists(
                select 1
                  from submission_artifact_policies s
                  join project_guide_proposal_approvals approval
                    on approval.operation_id=reservation.operation_id and approval.artifact_policy_id=s.id
                  join effective_project_submission_artifact_policies e
                    on e.id=reservation.committed_effective_policy_id
                   and e.submission_artifact_policy_id=s.id
                   and e.submission_artifact_policy_hash=s.policy_hash
                  join pre_submit_checker_policies p
                    on p.id=reservation.committed_pre_submit_policy_id
                   and p.project_id=e.project_id
                  where s.id=reservation.committed_policy_id
                    and s.id=reservation.policy_id
                    and s.guide_id=reservation.guide_id
                    and s.source_snapshot_id=reservation.source_snapshot_id
                    and s.guide_version=approval.target_json->>'guide_version'
                    and s.policy_hash=approval.target_json->>'artifact_policy_hash'
                    and e.effective_policy_hash=
                        approval.receipt_json->>'effective_policy_hash'
                    and p.compiled_bundle_hash=
                        approval.receipt_json->>'pre_submit_bundle_hash'
                    and e.project_id=reservation.project_id
                    and e.guide_id=s.guide_id and p.guide_id=s.guide_id
                    and e.guide_version=s.guide_version
                    and p.guide_version=s.guide_version
                    and e.source_snapshot_id=s.source_snapshot_id
                    and p.source_snapshot_id=s.source_snapshot_id
                    and e.source_snapshot_hash=s.source_snapshot_hash
                    and p.source_snapshot_hash=s.source_snapshot_hash
                    and e.submission_artifact_policy_id=reservation.committed_policy_id
                    and p.effective_policy_id=e.id
                    and p.effective_policy_hash=e.effective_policy_hash
                    and e.created_by_actor_profile_id=reservation.actor_profile_id
                    and p.created_by_actor_profile_id=reservation.actor_profile_id
                    and e.created_via_identity_link_id=reservation.identity_link_id
                    and p.created_via_identity_link_id=reservation.identity_link_id
                    and e.created_by_admin_role_grant_id=grant_id
                    and p.created_by_admin_role_grant_id=grant_id
                    and e.creation_scope_project_id=reservation.project_id
                    and p.creation_scope_project_id=reservation.project_id
                    and e.creation_action_id=reservation.action_id
                    and p.creation_action_id=reservation.action_id
                    and e.creation_decision_event_id=decision_id
                    and p.creation_decision_event_id=decision_id
              ) into approval_outputs_valid;
              if approval_outputs_valid is not true then
                raise exception 'submission-policy approval output custody mismatch'
                  using errcode='23514';
              end if;
            end if;
          elsif tg_table_name='submission_artifact_policies' then
            if new.creation_action_id is null and new.approval_action_id is null then
              if new.created_by_actor_profile_id is not null
                 or new.created_via_identity_link_id is not null
                 or new.created_by_admin_role_grant_id is not null
                 or new.created_by_service_identity is not null
                 or new.creation_scope_type is not null
                 or new.creation_scope_project_id is not null
                 or new.creation_decision_event_id is not null
                 or new.approved_by_actor_profile_id is not null
                 or new.approved_via_identity_link_id is not null
                 or new.approved_by_admin_role_grant_id is not null
                 or new.approval_scope_type is not null
                 or new.approval_scope_project_id is not null
                 or new.approval_decision_event_id is not null then
                raise exception 'partial submission-policy provenance'
                  using errcode='23514';
              end if;
              return null;
            end if;
            if new.approval_action_id is not null then
              select * into reservation from submission_policy_mutation_idempotency_records
                where committed_policy_id=new.id and action_id=new.approval_action_id
                  and status='committed';
              actor_id:=new.approved_by_actor_profile_id;
              link_id:=new.approved_via_identity_link_id;
              grant_id:=new.approved_by_admin_role_grant_id;
              service_id:=null; action_value:=new.approval_action_id;
              decision_id:=new.approval_decision_event_id;
            else
              select * into reservation from submission_policy_mutation_idempotency_records
                where committed_policy_id=new.id and action_id=new.creation_action_id
                  and status='committed';
              actor_id:=new.created_by_actor_profile_id;
              link_id:=new.created_via_identity_link_id;
              grant_id:=new.created_by_admin_role_grant_id;
              service_id:=new.created_by_service_identity;
              action_value:=new.creation_action_id;
              decision_id:=new.creation_decision_event_id;
            end if;
            product_project:=new.project_id; product_id:=new.id;
          elsif tg_table_name='effective_project_submission_artifact_policies' then
            if new.creation_action_id is null then
              if new.created_by_actor_profile_id is not null
                 or new.created_via_identity_link_id is not null
                 or new.created_by_admin_role_grant_id is not null
                 or new.creation_scope_type is not null
                 or new.creation_scope_project_id is not null
                 or new.creation_decision_event_id is not null then
                raise exception 'partial effective-policy provenance'
                  using errcode='23514';
              end if;
              return null;
            end if;
            select * into reservation from submission_policy_mutation_idempotency_records
              where committed_effective_policy_id=new.id and status='committed';
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            service_id:=null; action_value:=new.creation_action_id;
            decision_id:=new.creation_decision_event_id;
            product_project:=new.project_id; product_id:=reservation.committed_policy_id;
          else
            if new.creation_action_id is null then
              if new.created_by_actor_profile_id is not null
                 or new.created_via_identity_link_id is not null
                 or new.created_by_admin_role_grant_id is not null
                 or new.creation_scope_type is not null
                 or new.creation_scope_project_id is not null
                 or new.creation_decision_event_id is not null then
                raise exception 'partial pre-submit-policy provenance'
                  using errcode='23514';
              end if;
              return null;
            end if;
            select * into reservation from submission_policy_mutation_idempotency_records
              where committed_pre_submit_policy_id=new.id and status='committed';
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            service_id:=null; action_value:=new.creation_action_id;
            decision_id:=new.creation_decision_event_id;
            product_project:=new.project_id; product_id:=reservation.committed_policy_id;
          end if;
          if reservation.id is null or product_id is null
             or reservation.actor_profile_id is distinct from actor_id
             or reservation.identity_link_id is distinct from link_id
             or reservation.action_id is distinct from action_value
             or reservation.project_id is distinct from product_project
             or reservation.committed_policy_id is distinct from product_id
             or reservation.service_identity is distinct from service_id then
            raise exception 'submission-policy mutation custody mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events where id=decision_id;
          if evidence.id is null or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from actor_id::text
             or evidence.matched_grant_id is distinct from grant_id::text
             or evidence.permission_id is distinct from 'project.effective_policy.manage'
             or evidence.action_id is distinct from action_value
             or evidence.resource_type
                is distinct from 'project_submission_artifact_policy_mutation'
             or evidence.resource_id is distinct from product_id::text
             or evidence.project_id is distinct from reservation.project_id
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from reservation.project_id::text
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'submission-policy authorization evidence mismatch'
              using errcode='23514';
          end if;
          return null;
        end $$;
CREATE FUNCTION public.validate_submission_policy_creation_custody() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        declare
          reservation submission_policy_mutation_idempotency_records%rowtype;
          evidence audit_events%rowtype;
          projection project_guide_component_projection_operations%rowtype;
        begin
          if new.creation_action_id is null then
            if new.created_by_actor_profile_id is not null
               or new.created_via_identity_link_id is not null
               or new.created_by_admin_role_grant_id is not null
               or new.created_by_service_identity is not null
               or new.creation_scope_type is not null
               or new.creation_scope_project_id is not null
               or new.creation_decision_event_id is not null then
              raise exception 'partial submission-policy creation provenance'
                using errcode='23514';
            end if;
            return null;
          end if;

          if new.derivation_source='unified_compilation' then
            select * into projection
              from project_guide_component_projection_operations
              where policy_id=new.id
                and component='submission_artifact_policy';
            if projection.operation_id is null
               or projection.output_id is distinct from new.id
               or projection.project_id is distinct from new.project_id
               or projection.guide_id is distinct from new.guide_id
               or projection.guide_version is distinct from new.guide_version
               or projection.source_snapshot_id is distinct from new.source_snapshot_id
               or projection.source_snapshot_hash is distinct from new.source_snapshot_hash
               or projection.actor_profile_id
                    is distinct from new.created_by_actor_profile_id
               or projection.identity_link_id
                    is distinct from new.created_via_identity_link_id
               or projection.service_identity
                    is distinct from new.created_by_service_identity
               or projection.action_id is distinct from new.creation_action_id
               or projection.permission_id is distinct from
                    'project.effective_policy.manage'
               or projection.authorization_decision_event_id
                    is distinct from new.creation_decision_event_id then
              raise exception 'submission-policy projection custody mismatch'
                using errcode='23514';
            end if;
            return null;
          end if;

          select * into reservation from submission_policy_mutation_idempotency_records
            where committed_policy_id=new.id and action_id=new.creation_action_id
              and status='committed';
          if reservation.id is null
             or reservation.actor_profile_id
                is distinct from new.created_by_actor_profile_id
             or reservation.identity_link_id
                is distinct from new.created_via_identity_link_id
             or reservation.service_identity
                is distinct from new.created_by_service_identity
             or reservation.project_id is distinct from new.project_id
             or reservation.policy_id is distinct from new.id
             or reservation.guide_id is distinct from new.guide_id
             or reservation.source_snapshot_id is distinct from new.source_snapshot_id
             or reservation.resource_context_json->>'guide_version'
                is distinct from new.guide_version then
            raise exception 'submission-policy creation custody mismatch'
              using errcode='23514';
          end if;
          select * into evidence from audit_events
            where id=new.creation_decision_event_id;
          if evidence.id is null
             or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from new.created_by_actor_profile_id::text
             or evidence.matched_grant_id
                is distinct from new.created_by_admin_role_grant_id::text
             or evidence.permission_id is distinct from
                'project.effective_policy.manage'
             or evidence.action_id is distinct from new.creation_action_id
             or evidence.resource_type is distinct from
                'project_submission_artifact_policy_mutation'
             or evidence.resource_id is distinct from new.id::text
             or evidence.project_id is distinct from reservation.project_id
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from reservation.project_id::text
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'submission-policy creation evidence mismatch'
              using errcode='23514';
          end if;
          return null;
        end; $$;
CREATE TABLE public.actor_identity_links (
    id uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    issuer character varying(200) NOT NULL,
    subject character varying(200) NOT NULL,
    subject_kind character varying(16) NOT NULL,
    status character varying(16) NOT NULL,
    linked_by character varying(120) NOT NULL,
    linked_at timestamp with time zone DEFAULT now() NOT NULL,
    last_verified_at timestamp with time zone,
    revoked_by character varying(120),
    revoked_at timestamp with time zone,
    revoked_reason character varying(500),
    reactivated_by character varying(120),
    reactivated_at timestamp with time zone,
    reactivation_reason character varying(500),
    CONSTRAINT ck_actor_identity_links_human_verified CHECK ((((subject_kind)::text = 'service'::text) OR (last_verified_at IS NOT NULL))),
    CONSTRAINT ck_actor_identity_links_id_uuid CHECK (((id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)),
    CONSTRAINT ck_actor_identity_links_issuer CHECK (((length(btrim((issuer)::text)) >= 1) AND (length(btrim((issuer)::text)) <= 200))),
    CONSTRAINT ck_actor_identity_links_lifecycle_reason_bounds CHECK ((((revoked_reason IS NULL) OR (((revoked_reason)::text = btrim((revoked_reason)::text, (((((((((((((((((((((((((((chr(32) || chr(9)) || chr(10)) || chr(12)) || chr(11)) || chr(28)) || chr(29)) || chr(30)) || chr(31)) || chr(133)) || chr(160)) || chr(5760)) || chr(8192)) || chr(8193)) || chr(8194)) || chr(8195)) || chr(8196)) || chr(8197)) || chr(8198)) || chr(8199)) || chr(8200)) || chr(8201)) || chr(8202)) || chr(8232)) || chr(8233)) || chr(8239)) || chr(8287)) || chr(12288)))) AND ((octet_length((revoked_reason)::text) >= 1) AND (octet_length((revoked_reason)::text) <= 500)))) AND ((reactivation_reason IS NULL) OR (((reactivation_reason)::text = btrim((reactivation_reason)::text, (((((((((((((((((((((((((((chr(32) || chr(9)) || chr(10)) || chr(12)) || chr(11)) || chr(28)) || chr(29)) || chr(30)) || chr(31)) || chr(133)) || chr(160)) || chr(5760)) || chr(8192)) || chr(8193)) || chr(8194)) || chr(8195)) || chr(8196)) || chr(8197)) || chr(8198)) || chr(8199)) || chr(8200)) || chr(8201)) || chr(8202)) || chr(8232)) || chr(8233)) || chr(8239)) || chr(8287)) || chr(12288)))) AND ((octet_length((reactivation_reason)::text) >= 1) AND (octet_length((reactivation_reason)::text) <= 500)))))),
    CONSTRAINT ck_actor_identity_links_reactivation_fields CHECK ((((reactivated_by IS NULL) AND (reactivated_at IS NULL) AND (reactivation_reason IS NULL)) OR ((reactivated_by IS NOT NULL) AND (reactivated_at IS NOT NULL) AND (reactivation_reason IS NOT NULL)))),
    CONSTRAINT ck_actor_identity_links_revocation_fields CHECK (((((status)::text = 'active'::text) AND (revoked_by IS NULL) AND (revoked_at IS NULL) AND (revoked_reason IS NULL)) OR (((status)::text = 'revoked'::text) AND (revoked_by IS NOT NULL) AND (revoked_at IS NOT NULL) AND (revoked_reason IS NOT NULL)))),
    CONSTRAINT ck_actor_identity_links_status CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('revoked'::character varying)::text]))),
    CONSTRAINT ck_actor_identity_links_subject CHECK (((length(btrim((subject)::text)) >= 1) AND (length(btrim((subject)::text)) <= 200))),
    CONSTRAINT ck_actor_identity_links_subject_kind CHECK (((subject_kind)::text = ANY (ARRAY[('human'::character varying)::text, ('service'::character varying)::text])))
);
CREATE TABLE public.actor_profile_migration_state (
    id integer NOT NULL,
    schema_version integer NOT NULL,
    classified_count integer NOT NULL,
    source_row_set_sha256 character varying(64) NOT NULL,
    manifest_sha256 character varying(64),
    envelope_sha256 character varying(64),
    migrated_at timestamp with time zone DEFAULT now() NOT NULL,
    service_identity_mapped_count integer NOT NULL,
    service_identity_source_row_set_sha256 character varying(64) NOT NULL,
    service_identity_manifest_sha256 character varying(64),
    service_identity_envelope_sha256 character varying(64),
    service_identity_database_binding character varying(76) NOT NULL,
    CONSTRAINT ck_actor_profile_migration_state_evidence CHECK ((((classified_count = 0) AND (manifest_sha256 IS NULL) AND (envelope_sha256 IS NULL)) OR ((classified_count > 0) AND (manifest_sha256 IS NOT NULL) AND (envelope_sha256 IS NOT NULL)))),
    CONSTRAINT ck_actor_profile_migration_state_service_identity_evidence CHECK (((service_identity_mapped_count >= 0) AND (service_identity_mapped_count <= 7) AND ((service_identity_source_row_set_sha256)::text ~ '^[0-9a-f]{64}$'::text) AND ((service_identity_database_binding)::text ~ '^postgres-v1:[0-9a-f]{64}$'::text) AND (((service_identity_mapped_count = 0) AND (service_identity_manifest_sha256 IS NULL) AND (service_identity_envelope_sha256 IS NULL)) OR ((service_identity_mapped_count >= 1) AND (service_identity_mapped_count <= 7) AND ((service_identity_manifest_sha256)::text ~ '^[0-9a-f]{64}$'::text) AND ((service_identity_envelope_sha256)::text ~ '^[0-9a-f]{64}$'::text))))),
    CONSTRAINT ck_actor_profile_migration_state_singleton CHECK (((id = 1) AND (schema_version = 1) AND (classified_count >= 0)))
);
CREATE SEQUENCE public.actor_profile_migration_state_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.actor_profile_migration_state_id_seq OWNED BY public.actor_profile_migration_state.id;
CREATE TABLE public.actor_profiles (
    id uuid NOT NULL,
    actor_kind character varying(16) NOT NULL,
    status character varying(16) NOT NULL,
    provisioning_method character varying(32) NOT NULL,
    display_name character varying(200),
    contact_email character varying(320),
    created_by character varying(120) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone,
    suspended_by character varying(120),
    suspended_at timestamp with time zone,
    suspension_reason character varying(500),
    deactivated_by character varying(120),
    deactivated_at timestamp with time zone,
    deactivation_reason character varying(500),
    service_identity character varying(80),
    reactivated_by character varying(120),
    reactivated_at timestamp with time zone,
    reactivation_reason character varying(500),
    CONSTRAINT ck_actor_profiles_actor_kind CHECK (((actor_kind)::text = ANY (ARRAY[('human'::character varying)::text, ('service'::character varying)::text]))),
    CONSTRAINT ck_actor_profiles_id_uuid CHECK (((id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)),
    CONSTRAINT ck_actor_profiles_kind_provisioning CHECK (((((actor_kind)::text = 'human'::text) AND ((provisioning_method)::text = 'automatic_first_access'::text)) OR (((actor_kind)::text = 'service'::text) AND ((provisioning_method)::text = 'manual_service_provisioning'::text)))),
    CONSTRAINT ck_actor_profiles_kind_service_identity CHECK (((((actor_kind)::text = 'human'::text) AND (service_identity IS NULL)) OR (((actor_kind)::text = 'service'::text) AND ((service_identity)::text = ANY (ARRAY[('workstream.artifact.verifier'::character varying)::text, ('workstream.artifact.put_resolver'::character varying)::text, ('workstream.artifact.scheduler'::character varying)::text, ('workstream.artifact.binding'::character varying)::text, ('workstream.artifact.guide_reader'::character varying)::text, ('workstream.artifact.materializer'::character varying)::text, ('workstream.artifact.checker_output'::character varying)::text, ('workstream.project.setup'::character varying)::text, ('workstream.review.preference_expiry'::character varying)::text, ('workstream.review.lease_expiry'::character varying)::text, ('workstream.review.authority_invalidation_reconciliation'::character varying)::text, ('workstream.review.reconciliation'::character varying)::text, ('workstream.review.artifact_reference_reconciliation'::character varying)::text, ('workstream.review.projection'::character varying)::text, ('workstream.compensation.adapter'::character varying)::text, ('workstream.outbox.dispatcher'::character varying)::text, ('workstream.task.assignment_reconciler'::character varying)::text]))))),
    CONSTRAINT ck_actor_profiles_lifecycle_fields CHECK (((((status)::text = 'active'::text) AND (suspended_by IS NULL) AND (suspended_at IS NULL) AND (suspension_reason IS NULL) AND (deactivated_by IS NULL) AND (deactivated_at IS NULL) AND (deactivation_reason IS NULL)) OR (((status)::text = 'suspended'::text) AND (suspended_by IS NOT NULL) AND (suspended_at IS NOT NULL) AND (suspension_reason IS NOT NULL) AND (deactivated_by IS NULL) AND (deactivated_at IS NULL) AND (deactivation_reason IS NULL)) OR (((status)::text = 'deactivated'::text) AND (deactivated_by IS NOT NULL) AND (deactivated_at IS NOT NULL) AND (deactivation_reason IS NOT NULL)))),
    CONSTRAINT ck_actor_profiles_lifecycle_reason_bounds CHECK ((((suspension_reason IS NULL) OR (((suspension_reason)::text = btrim((suspension_reason)::text, (((((((((((((((((((((((((((chr(32) || chr(9)) || chr(10)) || chr(12)) || chr(11)) || chr(28)) || chr(29)) || chr(30)) || chr(31)) || chr(133)) || chr(160)) || chr(5760)) || chr(8192)) || chr(8193)) || chr(8194)) || chr(8195)) || chr(8196)) || chr(8197)) || chr(8198)) || chr(8199)) || chr(8200)) || chr(8201)) || chr(8202)) || chr(8232)) || chr(8233)) || chr(8239)) || chr(8287)) || chr(12288)))) AND ((octet_length((suspension_reason)::text) >= 1) AND (octet_length((suspension_reason)::text) <= 500)))) AND ((reactivation_reason IS NULL) OR (((reactivation_reason)::text = btrim((reactivation_reason)::text, (((((((((((((((((((((((((((chr(32) || chr(9)) || chr(10)) || chr(12)) || chr(11)) || chr(28)) || chr(29)) || chr(30)) || chr(31)) || chr(133)) || chr(160)) || chr(5760)) || chr(8192)) || chr(8193)) || chr(8194)) || chr(8195)) || chr(8196)) || chr(8197)) || chr(8198)) || chr(8199)) || chr(8200)) || chr(8201)) || chr(8202)) || chr(8232)) || chr(8233)) || chr(8239)) || chr(8287)) || chr(12288)))) AND ((octet_length((reactivation_reason)::text) >= 1) AND (octet_length((reactivation_reason)::text) <= 500)))) AND ((deactivation_reason IS NULL) OR (((deactivation_reason)::text = btrim((deactivation_reason)::text, (((((((((((((((((((((((((((chr(32) || chr(9)) || chr(10)) || chr(12)) || chr(11)) || chr(28)) || chr(29)) || chr(30)) || chr(31)) || chr(133)) || chr(160)) || chr(5760)) || chr(8192)) || chr(8193)) || chr(8194)) || chr(8195)) || chr(8196)) || chr(8197)) || chr(8198)) || chr(8199)) || chr(8200)) || chr(8201)) || chr(8202)) || chr(8232)) || chr(8233)) || chr(8239)) || chr(8287)) || chr(12288)))) AND ((octet_length((deactivation_reason)::text) >= 1) AND (octet_length((deactivation_reason)::text) <= 500)))))),
    CONSTRAINT ck_actor_profiles_provisioning_method CHECK (((provisioning_method)::text = ANY (ARRAY[('automatic_first_access'::character varying)::text, ('manual_service_provisioning'::character varying)::text]))),
    CONSTRAINT ck_actor_profiles_reactivation_fields CHECK ((((reactivated_by IS NULL) AND (reactivated_at IS NULL) AND (reactivation_reason IS NULL)) OR ((reactivated_by IS NOT NULL) AND (reactivated_at IS NOT NULL) AND (reactivation_reason IS NOT NULL)))),
    CONSTRAINT ck_actor_profiles_status CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('suspended'::character varying)::text, ('deactivated'::character varying)::text])))
);
CREATE TABLE public.api_rate_control_counters (
    control_scope character varying(32) NOT NULL,
    key_digest bytea NOT NULL,
    window_started_at timestamp with time zone NOT NULL,
    window_expires_at timestamp with time zone NOT NULL,
    request_count bigint NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_api_rate_control_counters_digest_length CHECK ((octet_length(key_digest) = 32)),
    CONSTRAINT ck_api_rate_control_counters_request_count CHECK (((request_count >= 1) AND (request_count <= '9223372036854775807'::bigint))),
    CONSTRAINT ck_api_rate_control_counters_scope_token CHECK (((control_scope)::text = ANY (ARRAY[('first_access'::character varying)::text, ('admin_mutation'::character varying)::text, ('authorization_read'::character varying)::text]))),
    CONSTRAINT ck_api_rate_control_counters_window_order CHECK ((window_started_at < window_expires_at))
);
CREATE TABLE public.artifact_admission_charges (
    id uuid NOT NULL,
    scope_type character varying(20) NOT NULL,
    scope_id character varying(120) NOT NULL,
    sha256 character varying(71) NOT NULL,
    byte_count bigint NOT NULL,
    producer_type character varying(30) NOT NULL,
    producer_ref character varying(120) NOT NULL,
    creating_operation_identity character varying(71) NOT NULL,
    state character varying(20) DEFAULT 'provisional'::character varying NOT NULL,
    cas_version bigint DEFAULT '0'::bigint NOT NULL,
    reserved_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    released_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifact_admission_charges_byte_count_nonnegative CHECK ((byte_count >= 0)),
    CONSTRAINT ck_artifact_admission_charges_cas_nonnegative CHECK ((cas_version >= 0)),
    CONSTRAINT ck_artifact_admission_charges_completed_timestamp CHECK ((((state)::text = 'completed'::text) = (completed_at IS NOT NULL))),
    CONSTRAINT ck_artifact_admission_charges_operation_identity_shape CHECK (((creating_operation_identity)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_admission_charges_producer_type CHECK (((producer_type)::text = ANY (ARRAY[('actor_profile'::character varying)::text, ('service_identity'::character varying)::text]))),
    CONSTRAINT ck_artifact_admission_charges_released_timestamp CHECK ((((state)::text = 'released'::text) = (released_at IS NOT NULL))),
    CONSTRAINT ck_artifact_admission_charges_sha256_shape CHECK (((sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_admission_charges_state CHECK (((state)::text = ANY (ARRAY[('provisional'::character varying)::text, ('completed'::character varying)::text, ('released'::character varying)::text])))
);
CREATE TABLE public.artifact_admission_scopes (
    scope_type character varying(20) NOT NULL,
    scope_id character varying(120) NOT NULL,
    limit_bytes bigint NOT NULL,
    counted_bytes bigint DEFAULT '0'::bigint NOT NULL,
    cas_version bigint DEFAULT '0'::bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifact_admission_scopes_cas_nonnegative CHECK ((cas_version >= 0)),
    CONSTRAINT ck_artifact_admission_scopes_counted_bytes_within_limit CHECK (((counted_bytes >= 0) AND (counted_bytes <= limit_bytes))),
    CONSTRAINT ck_artifact_admission_scopes_limit_positive CHECK ((limit_bytes > 0)),
    CONSTRAINT ck_artifact_admission_scopes_scope_id_bounds CHECK (((octet_length((scope_id)::text) >= 1) AND (octet_length((scope_id)::text) <= 120))),
    CONSTRAINT ck_artifact_admission_scopes_scope_type CHECK (((scope_type)::text = ANY (ARRAY[('deployment'::character varying)::text, ('project'::character varying)::text, ('producer'::character varying)::text, ('task'::character varying)::text])))
);
CREATE TABLE public.artifact_bindings (
    id uuid NOT NULL,
    content_id uuid NOT NULL,
    project_id uuid NOT NULL,
    resource_type character varying(80) NOT NULL,
    resource_id character varying(100) NOT NULL,
    logical_role character varying(100) NOT NULL,
    scope_version integer NOT NULL,
    actor_id character varying(100) NOT NULL,
    attribution_type character varying(30) NOT NULL,
    supersedes_binding_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifact_bindings_scope_version_positive CHECK ((scope_version > 0)),
    CONSTRAINT ck_artifact_bindings_scope_version_predecessor CHECK ((((scope_version = 1) AND (supersedes_binding_id IS NULL)) OR ((scope_version > 1) AND (supersedes_binding_id IS NOT NULL))))
);
CREATE TABLE public.artifact_contents (
    id uuid NOT NULL,
    sha256 character varying(71) NOT NULL,
    byte_count integer NOT NULL,
    media_type character varying(200),
    normalized_display_name character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifact_contents_byte_count_nonnegative CHECK ((byte_count >= 0)),
    CONSTRAINT ck_artifact_contents_sha256_shape CHECK (((sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text))
);
CREATE TABLE public.artifact_operation_receipts (
    id uuid NOT NULL,
    replica_id uuid NOT NULL,
    operation character varying(30) NOT NULL,
    idempotency_key character varying(200) NOT NULL,
    request_digest character varying(71) NOT NULL,
    provider_object_ref character varying(1024) NOT NULL,
    replayed boolean NOT NULL,
    outcome character varying(30) NOT NULL,
    attempt_number integer NOT NULL,
    correlation_id character varying(100) NOT NULL,
    details json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    contract_version integer DEFAULT 1 NOT NULL,
    put_attempt_id uuid NOT NULL,
    guide_source_item_id uuid,
    checker_run_id uuid,
    logical_role character varying(100),
    CONSTRAINT ck_artifact_operation_receipts_attempt_positive CHECK ((attempt_number > 0)),
    CONSTRAINT ck_artifact_operation_receipts_contract_producer_reference CHECK (((contract_version = 2) AND (put_attempt_id IS NOT NULL) AND (((guide_source_item_id IS NOT NULL) AND (checker_run_id IS NULL) AND (logical_role IS NULL)) OR ((guide_source_item_id IS NULL) AND (checker_run_id IS NOT NULL) AND ((octet_length((logical_role)::text) >= 1) AND (octet_length((logical_role)::text) <= 100))) OR ((guide_source_item_id IS NULL) AND (checker_run_id IS NULL) AND (logical_role IS NULL))))),
    CONSTRAINT ck_artifact_operation_receipts_document_outcome CHECK ((((outcome)::text <> 'document_stored'::text) OR (guide_source_item_id IS NOT NULL))),
    CONSTRAINT ck_artifact_operation_receipts_operation CHECK (((operation)::text = 'put'::text)),
    CONSTRAINT ck_artifact_operation_receipts_outcome CHECK (((outcome)::text = ANY ((ARRAY['stored_pending_verification'::character varying, 'document_stored'::character varying])::text[]))),
    CONSTRAINT ck_artifact_operation_receipts_request_digest_shape CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))
);
CREATE TABLE public.artifact_put_attempt_charges (
    attempt_id uuid NOT NULL,
    charge_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.artifact_put_attempts (
    id uuid NOT NULL,
    producer_request_type character varying(30) NOT NULL,
    producer_type character varying(30) NOT NULL,
    producer_ref character varying(120) NOT NULL,
    project_id uuid NOT NULL,
    task_id uuid,
    guide_source_item_id uuid,
    checker_run_id uuid,
    logical_role character varying(100),
    sha256 character varying(71) NOT NULL,
    byte_count bigint NOT NULL,
    media_type character varying(255) NOT NULL,
    storage_namespace_id character varying(20) NOT NULL,
    namespace_fingerprint character varying(71) NOT NULL,
    canonical_target character varying(1024) NOT NULL,
    operation_identity character varying(71) NOT NULL,
    request_digest character varying(71) NOT NULL,
    status character varying(40) DEFAULT 'prepared'::character varying NOT NULL,
    next_run_at timestamp with time zone,
    executor_id uuid,
    lease_expires_at timestamp with time zone,
    execution_generation bigint DEFAULT '0'::bigint NOT NULL,
    terminal_result_code character varying(100),
    replica_id uuid,
    receipt_id uuid,
    cas_version bigint DEFAULT '0'::bigint NOT NULL,
    prepared_at timestamp with time zone DEFAULT now() NOT NULL,
    terminal_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    execution_mode character varying(20),
    observation_count bigint DEFAULT '0'::bigint NOT NULL,
    maximum_observations bigint DEFAULT '5'::bigint NOT NULL,
    CONSTRAINT ck_artifact_put_attempts_byte_count_nonnegative CHECK ((byte_count >= 0)),
    CONSTRAINT ck_artifact_put_attempts_canonical_target_shape CHECK (((canonical_target)::text ~ '^sha256/[0-9a-f]{2}/[0-9a-f]{62}$'::text)),
    CONSTRAINT ck_artifact_put_attempts_execution_mode CHECK (((execution_mode IS NULL) OR ((execution_mode)::text = ANY (ARRAY[('caller_put'::character varying)::text, ('observation'::character varying)::text])))),
    CONSTRAINT ck_artifact_put_attempts_executor_lease_pair CHECK (((executor_id IS NULL) = (lease_expires_at IS NULL))),
    CONSTRAINT ck_artifact_put_attempts_inflight_fence CHECK ((((status)::text = 'put_in_flight'::text) = (executor_id IS NOT NULL))),
    CONSTRAINT ck_artifact_put_attempts_observation_counts CHECK (((observation_count >= 0) AND (maximum_observations > 0))),
    CONSTRAINT ck_artifact_put_attempts_operation_identity_shape CHECK (((operation_identity)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_put_attempts_prepared_execution_inactive CHECK ((((status)::text <> 'prepared'::text) OR ((next_run_at IS NULL) AND (executor_id IS NULL) AND (lease_expires_at IS NULL) AND (execution_generation = 0) AND (terminal_result_code IS NULL) AND (terminal_at IS NULL) AND (replica_id IS NULL) AND (receipt_id IS NULL)))),
    CONSTRAINT ck_artifact_put_attempts_producer_identity CHECK (((((producer_request_type)::text = 'guide'::text) AND ((producer_type)::text = 'actor_profile'::text) AND ((producer_ref)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'::text)) OR (((producer_request_type)::text = 'checker_output'::text) AND ((producer_type)::text = 'service_identity'::text) AND ((producer_ref)::text = 'workstream.artifact.checker_output'::text)) OR (((producer_request_type)::text = 'submission_bundle'::text) AND ((producer_type)::text = 'actor_profile'::text) AND ((producer_ref)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'::text)))),
    CONSTRAINT ck_artifact_put_attempts_producer_reference CHECK (((((producer_request_type)::text = 'guide'::text) AND (guide_source_item_id IS NOT NULL) AND (checker_run_id IS NULL) AND (task_id IS NULL) AND (logical_role IS NULL)) OR (((producer_request_type)::text = 'checker_output'::text) AND (guide_source_item_id IS NULL) AND (checker_run_id IS NOT NULL) AND (task_id IS NOT NULL) AND ((octet_length((logical_role)::text) >= 1) AND (octet_length((logical_role)::text) <= 100))) OR (((producer_request_type)::text = 'submission_bundle'::text) AND (guide_source_item_id IS NULL) AND (checker_run_id IS NULL) AND (task_id IS NOT NULL) AND (logical_role IS NULL)))),
    CONSTRAINT ck_artifact_put_attempts_producer_request_type CHECK (((producer_request_type)::text = ANY (ARRAY[('guide'::character varying)::text, ('checker_output'::character varying)::text, ('submission_bundle'::character varying)::text]))),
    CONSTRAINT ck_artifact_put_attempts_producer_type CHECK (((producer_type)::text = ANY (ARRAY[('actor_profile'::character varying)::text, ('service_identity'::character varying)::text]))),
    CONSTRAINT ck_artifact_put_attempts_request_digest_shape CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_put_attempts_sha256_shape CHECK (((sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_put_attempts_status CHECK (((status)::text = ANY (ARRAY[('prepared'::character varying)::text, ('put_in_flight'::character varying)::text, ('acknowledgement_unknown'::character varying)::text, ('object_confirmed'::character varying)::text, ('absent_replay_required'::character varying)::text, ('integrity_mismatch'::character varying)::text, ('provider_unavailable'::character varying)::text, ('conflict'::character varying)::text]))),
    CONSTRAINT ck_artifact_put_attempts_unavailable_exhausted CHECK ((((status)::text <> 'provider_unavailable'::text) OR ((observation_count >= maximum_observations) AND (next_run_at IS NULL) AND (terminal_at IS NOT NULL)))),
    CONSTRAINT ck_artifact_put_attempts_versions_nonnegative CHECK (((execution_generation >= 0) AND (cas_version >= 0)))
);
CREATE TABLE public.artifact_put_observation_receipts (
    id uuid NOT NULL,
    put_attempt_id uuid NOT NULL,
    execution_generation bigint NOT NULL,
    outcome character varying(40) NOT NULL,
    expected_sha256 character varying(71) NOT NULL,
    expected_byte_count bigint NOT NULL,
    observed_sha256 character varying(71),
    observed_byte_count bigint,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT ck_artifact_put_observation_receipts_expected_sha256 CHECK (((expected_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_put_observation_receipts_expected_size CHECK ((expected_byte_count >= 0)),
    CONSTRAINT ck_artifact_put_observation_receipts_observed_facts CHECK ((((outcome)::text = ANY (ARRAY[('observed_confirmed'::character varying)::text, ('observed_integrity_mismatch'::character varying)::text])) = ((observed_sha256 IS NOT NULL) AND (observed_byte_count IS NOT NULL)))),
    CONSTRAINT ck_artifact_put_observation_receipts_observed_sha256 CHECK (((observed_sha256 IS NULL) OR ((observed_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_artifact_put_observation_receipts_observed_size CHECK (((observed_byte_count IS NULL) OR (observed_byte_count >= 0))),
    CONSTRAINT ck_artifact_put_observation_receipts_outcome CHECK (((outcome)::text = ANY (ARRAY[('observed_confirmed'::character varying)::text, ('observed_missing'::character varying)::text, ('observed_integrity_mismatch'::character varying)::text, ('conflict'::character varying)::text])))
);
CREATE TABLE public.artifact_recovery_attempts (
    id uuid NOT NULL,
    requester_actor_profile_id uuid NOT NULL,
    requester_identity_link_id uuid NOT NULL,
    authorization_request_id uuid NOT NULL,
    authorization_correlation_id uuid NOT NULL,
    project_id uuid NOT NULL,
    task_id uuid,
    submission_id uuid,
    source_verification_job_id uuid NOT NULL,
    retry_verification_job_id uuid NOT NULL,
    parent_recovery_attempt_id uuid,
    recovery_class character varying(40) NOT NULL,
    reason character varying(1000) NOT NULL,
    client_idempotency_key character varying(200) NOT NULL,
    request_digest character varying(71) NOT NULL,
    status character varying(20) DEFAULT 'requested'::character varying NOT NULL,
    terminal_result_code character varying(40),
    initiation_audit_event_id uuid NOT NULL,
    terminal_audit_event_id uuid,
    cas_version bigint DEFAULT '0'::bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    terminal_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT ck_artifact_recovery_attempts_cas_nonnegative CHECK ((cas_version >= 0)),
    CONSTRAINT ck_artifact_recovery_attempts_distinct_jobs CHECK (((source_verification_job_id)::text <> (retry_verification_job_id)::text)),
    CONSTRAINT ck_artifact_recovery_attempts_recovery_class CHECK (((recovery_class)::text = 'provider_observation'::text)),
    CONSTRAINT ck_artifact_recovery_attempts_request_digest CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_recovery_attempts_status CHECK (((status)::text = ANY (ARRAY[('requested'::character varying)::text, ('succeeded'::character varying)::text, ('failed'::character varying)::text]))),
    CONSTRAINT ck_artifact_recovery_attempts_terminal_result CHECK (((((status)::text = 'succeeded'::text) AND ((terminal_result_code)::text = 'verified'::text)) OR (((status)::text = 'failed'::text) AND ((terminal_result_code)::text = ANY (ARRAY[('provider_unavailable'::character varying)::text, ('missing'::character varying)::text, ('integrity_mismatch'::character varying)::text, ('conflict'::character varying)::text]))) OR ((status)::text = 'requested'::text))),
    CONSTRAINT ck_artifact_recovery_attempts_terminal_shape CHECK (((((status)::text = 'requested'::text) AND (terminal_result_code IS NULL) AND (terminal_at IS NULL) AND (terminal_audit_event_id IS NULL)) OR (((status)::text = ANY (ARRAY[('succeeded'::character varying)::text, ('failed'::character varying)::text])) AND (terminal_result_code IS NOT NULL) AND (terminal_at IS NOT NULL) AND (terminal_audit_event_id IS NOT NULL))))
);
CREATE TABLE public.artifact_replicas (
    id uuid NOT NULL,
    content_id uuid NOT NULL,
    adapter character varying(50) NOT NULL,
    provider_object_ref character varying(1024) NOT NULL,
    verification_state character varying(30) NOT NULL,
    availability_state character varying(30) NOT NULL,
    integrity_state character varying(30) NOT NULL,
    last_reconciled_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    storage_namespace_id character varying(20) NOT NULL,
    namespace_fingerprint character varying(71) NOT NULL,
    provider_profile character varying(100) NOT NULL,
    CONSTRAINT ck_artifact_replicas_availability_state CHECK (((availability_state)::text = ANY (ARRAY[('unknown'::character varying)::text, ('available'::character varying)::text, ('unavailable'::character varying)::text]))),
    CONSTRAINT ck_artifact_replicas_fingerprint_shape CHECK (((namespace_fingerprint)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_replicas_integrity_state CHECK (((integrity_state)::text = ANY (ARRAY[('unknown'::character varying)::text, ('valid'::character varying)::text, ('invalid'::character varying)::text]))),
    CONSTRAINT ck_artifact_replicas_verification_state CHECK (((verification_state)::text = ANY (ARRAY[('pending'::character varying)::text, ('verified'::character varying)::text, ('missing'::character varying)::text, ('integrity_mismatch'::character varying)::text])))
);
CREATE TABLE public.artifact_storage_namespaces (
    id character varying(20) NOT NULL,
    backend character varying(50) NOT NULL,
    adapter character varying(50) NOT NULL,
    provider_profile character varying(100) NOT NULL,
    namespace_descriptor json NOT NULL,
    namespace_fingerprint character varying(71) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_artifact_storage_namespaces_fingerprint_shape CHECK (((namespace_fingerprint)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_artifact_storage_namespaces_singleton_id CHECK (((id)::text = 'primary'::text))
);
CREATE TABLE public.artifact_verification_jobs (
    id uuid NOT NULL,
    originating_put_attempt_id uuid NOT NULL,
    replica_id uuid NOT NULL,
    status character varying(40) DEFAULT 'pending'::character varying NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    maximum_attempts integer NOT NULL,
    next_run_at timestamp with time zone,
    executor_id uuid,
    lease_expires_at timestamp with time zone,
    execution_generation bigint DEFAULT '0'::bigint NOT NULL,
    cas_version bigint DEFAULT '0'::bigint NOT NULL,
    terminal_result_code character varying(100),
    terminal_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    parent_verification_job_id uuid,
    CONSTRAINT ck_artifact_verification_jobs_attempts CHECK (((attempt_count >= 0) AND (maximum_attempts > 0))),
    CONSTRAINT ck_artifact_verification_jobs_fence_pair CHECK (((executor_id IS NULL) = (lease_expires_at IS NULL))),
    CONSTRAINT ck_artifact_verification_jobs_running_fence CHECK ((((status)::text = 'running'::text) = (executor_id IS NOT NULL))),
    CONSTRAINT ck_artifact_verification_jobs_status CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('running'::character varying)::text, ('verified'::character varying)::text, ('missing'::character varying)::text, ('integrity_mismatch'::character varying)::text, ('provider_unavailable'::character varying)::text, ('conflict'::character varying)::text]))),
    CONSTRAINT ck_artifact_verification_jobs_unavailable_retryability CHECK ((((status)::text <> 'provider_unavailable'::text) OR (((next_run_at IS NOT NULL) AND (terminal_at IS NULL) AND (attempt_count < maximum_attempts)) OR ((next_run_at IS NULL) AND (terminal_at IS NOT NULL) AND (attempt_count >= maximum_attempts))))),
    CONSTRAINT ck_artifact_verification_jobs_versions CHECK (((execution_generation >= 0) AND (cas_version >= 0)))
);
CREATE TABLE public.artifact_verification_receipts (
    id uuid NOT NULL,
    verification_job_id uuid NOT NULL,
    execution_generation bigint NOT NULL,
    outcome character varying(40) NOT NULL,
    observed_sha256 character varying(71),
    observed_byte_count bigint,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT ck_artifact_verification_receipts_observed_facts CHECK ((((outcome)::text = ANY (ARRAY[('verified'::character varying)::text, ('integrity_mismatch'::character varying)::text])) = ((observed_sha256 IS NOT NULL) AND (observed_byte_count IS NOT NULL)))),
    CONSTRAINT ck_artifact_verification_receipts_observed_sha256 CHECK (((observed_sha256 IS NULL) OR ((observed_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_artifact_verification_receipts_observed_size CHECK (((observed_byte_count IS NULL) OR (observed_byte_count >= 0))),
    CONSTRAINT ck_artifact_verification_receipts_outcome CHECK (((outcome)::text = ANY (ARRAY[('verified'::character varying)::text, ('missing'::character varying)::text, ('integrity_mismatch'::character varying)::text, ('conflict'::character varying)::text])))
);
CREATE TABLE public.audit_events (
    id uuid NOT NULL,
    entity_type character varying(80) NOT NULL,
    entity_id uuid NOT NULL,
    event_type character varying(100) NOT NULL,
    from_status character varying(30),
    to_status character varying(30),
    actor_id character varying(100) NOT NULL,
    external_subject character varying(200),
    external_issuer character varying(200),
    actor_roles json NOT NULL,
    claim_snapshot json NOT NULL,
    auth_source character varying(30) NOT NULL,
    is_dev_auth boolean NOT NULL,
    reason text,
    event_payload json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    event_domain character varying(24) DEFAULT 'legacy_lifecycle'::character varying NOT NULL,
    event_version integer,
    occurred_at timestamp with time zone,
    actor_ref_kind character varying(32),
    request_id uuid,
    correlation_id uuid,
    target_actor_ref_kind character varying(32),
    target_actor_ref character varying(100),
    matched_grant_id character varying(100),
    permission_id character varying(120),
    project_id uuid,
    resource_type character varying(80),
    resource_id character varying(100),
    target_ref_kind character varying(32),
    target_ref_id character varying(100),
    denial_code character varying(80),
    idempotency_reference uuid,
    invalidation_cause_event_id uuid,
    invalidation_target_kind character varying(32),
    invalidation_target_ref character varying(100),
    before_facts json,
    after_facts json,
    action_id character varying(160),
    CONSTRAINT ck_audit_events_authority_privacy_bounds CHECK ((((event_domain)::text <> 'authority'::text) OR (((id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text) AND ((entity_type)::text = ANY (ARRAY[('actor_profile'::character varying)::text, ('actor_identity_link'::character varying)::text, ('admin_role_grant'::character varying)::text, ('qualification_snapshot'::character varying)::text, ('project_role_grant'::character varying)::text, ('authorization_decision'::character varying)::text, ('authority_invalidation'::character varying)::text])) AND ((entity_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text) AND ((((actor_ref_kind)::text = ANY (ARRAY[('legacy_actor'::character varying)::text, ('actor_profile'::character varying)::text])) AND ((actor_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) OR (((actor_ref_kind)::text = 'system_principal'::text) AND ((actor_id)::text = 'workstream:system:bootstrap'::text))) AND ((target_actor_ref IS NULL) OR (((target_actor_ref_kind)::text = 'actor_profile'::text) AND ((target_actor_ref)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text))) AND ((matched_grant_id IS NULL) OR ((matched_grant_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) AND ((project_id IS NULL) OR ((project_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) AND ((resource_type IS NULL) OR ((resource_type)::text = ANY (ARRAY[('actor_profile'::character varying)::text, ('actor_identity_link'::character varying)::text, ('admin_role_grant'::character varying)::text, ('project'::character varying)::text, ('qualification_snapshot'::character varying)::text, ('project_role_grant'::character varying)::text, ('task'::character varying)::text, ('submission'::character varying)::text, ('review'::character varying)::text, ('contribution'::character varying)::text, ('compensation_award'::character varying)::text, ('compensation_delivery'::character varying)::text, ('operations'::character varying)::text, ('audit_event'::character varying)::text, ('project_create_operation'::character varying)::text, ('project_submission_artifact_policy_mutation'::character varying)::text, ('project_guide_compilation_attempt'::character varying)::text, ('project_guide_compilation_request'::character varying)::text, ('project_guide_sufficiency_projection'::character varying)::text, ('project_submission_artifact_policy_projection'::character varying)::text, ('project_guide_setup_finalization'::character varying)::text, ('pre_submit_checker_input'::character varying)::text, ('project_guide_compilation_review_package'::character varying)::text, ('project_post_submit_checker_policy_mutation'::character varying)::text, ('project_guide_compilation_correction'::character varying)::text, ('contribution_policy'::character varying)::text, ('outbox_event'::character varying)::text, ('project_guide_activation'::character varying)::text, ('compensation_adapter_binding'::character varying)::text]))) AND ((resource_id IS NULL) OR ((resource_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) AND ((target_ref_kind IS NULL) OR (((target_ref_kind)::text = ANY (ARRAY[('actor_profile'::character varying)::text, ('actor_identity_link'::character varying)::text, ('admin_role_grant'::character varying)::text, ('qualification_snapshot'::character varying)::text, ('project_role_grant'::character varying)::text, ('project'::character varying)::text])) AND ((target_ref_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) OR (((target_ref_kind)::text = 'permission_registry'::text) AND ((target_ref_id)::text = ANY (ARRAY[('actor.profile.read_self'::character varying)::text, ('actor.profile.update_self'::character varying)::text, ('actor.profile.read_any'::character varying)::text, ('actor.profile.suspend'::character varying)::text, ('actor.profile.reactivate'::character varying)::text, ('actor.profile.deactivate'::character varying)::text, ('actor.identity_link.read'::character varying)::text, ('actor.identity_link.revoke'::character varying)::text, ('actor.identity_link.reactivate'::character varying)::text, ('actor.service.provision'::character varying)::text, ('admin_role.read'::character varying)::text, ('admin_role.grant'::character varying)::text, ('admin_role.revoke'::character varying)::text, ('project.create'::character varying)::text, ('project.read'::character varying)::text, ('project.update'::character varying)::text, ('project.archive'::character varying)::text, ('project.guide.manage'::character varying)::text, ('project.effective_policy.manage'::character varying)::text, ('project.task.manage'::character varying)::text, ('project.review_policy.manage'::character varying)::text, ('project.role_grant.read'::character varying)::text, ('project.role_grant.manage'::character varying)::text, ('project.setup_diagnostic.read'::character varying)::text, ('project.effective_policy.read'::character varying)::text, ('task.queue.read'::character varying)::text, ('task.claim'::character varying)::text, ('submission.create'::character varying)::text, ('submission.read_own'::character varying)::text, ('submission.read_for_review'::character varying)::text, ('review.queue.read'::character varying)::text, ('review.queue.inspect'::character varying)::text, ('review.claim'::character varying)::text, ('review.release'::character varying)::text, ('review.decline_preference'::character varying)::text, ('review.decision'::character varying)::text, ('review.lease.force_release'::character varying)::text, ('review.chain.read'::character varying)::text, ('contribution.read_self'::character varying)::text, ('contribution.read_project'::character varying)::text, ('compensation.policy.manage'::character varying)::text, ('compensation.adapter_binding.manage'::character varying)::text, ('compensation.award.read'::character varying)::text, ('compensation.delivery.reconcile'::character varying)::text, ('operations.status.read'::character varying)::text, ('operations.timer.run'::character varying)::text, ('operations.reconcile.run'::character varying)::text, ('operations.outbox.retry'::character varying)::text, ('operations.projection.rebuild'::character varying)::text, ('audit.read'::character varying)::text, ('audit.export'::character varying)::text, ('operations.task.start_override'::character varying)::text, ('operations.submission_gate.repair'::character varying)::text, ('operations.checker.retry'::character varying)::text, ('artifact.binding.read'::character varying)::text, ('artifact.replica.read'::character varying)::text, ('artifact.receipt.read'::character varying)::text, ('artifact.verification_job.read'::character varying)::text, ('artifact.verification_job.retry'::character varying)::text, ('artifact.recovery_attempt.read'::character varying)::text, ('artifact.audit.read'::character varying)::text, ('artifact.guide_source.ingest'::character varying)::text, ('artifact.binding.create'::character varying)::text, ('artifact.review_packet.materialize'::character varying)::text, ('artifact.verification.execute'::character varying)::text, ('artifact.pending_work.scan'::character varying)::text, ('artifact.put_attempt.resolve'::character varying)::text, ('artifact.guide_source.read'::character varying)::text, ('artifact.checker_input.materialize'::character varying)::text, ('artifact.checker_output.write'::character varying)::text, ('review.queue.override'::character varying)::text, ('project.guide_compilation.request'::character varying)::text, ('project.guide_compilation.execute'::character varying)::text])))) AND ((invalidation_target_kind IS NULL) OR (((invalidation_target_kind)::text = ANY (ARRAY[('actor_profile'::character varying)::text, ('actor_identity_link'::character varying)::text, ('admin_role_grant'::character varying)::text, ('qualification_snapshot'::character varying)::text, ('project_role_grant'::character varying)::text])) AND ((invalidation_target_ref)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)) OR (((invalidation_target_kind)::text = 'permission_registry'::text) AND ((invalidation_target_ref)::text = ANY (ARRAY[('actor.profile.read_self'::character varying)::text, ('actor.profile.update_self'::character varying)::text, ('actor.profile.read_any'::character varying)::text, ('actor.profile.suspend'::character varying)::text, ('actor.profile.reactivate'::character varying)::text, ('actor.profile.deactivate'::character varying)::text, ('actor.identity_link.read'::character varying)::text, ('actor.identity_link.revoke'::character varying)::text, ('actor.identity_link.reactivate'::character varying)::text, ('actor.service.provision'::character varying)::text, ('admin_role.read'::character varying)::text, ('admin_role.grant'::character varying)::text, ('admin_role.revoke'::character varying)::text, ('project.create'::character varying)::text, ('project.read'::character varying)::text, ('project.update'::character varying)::text, ('project.archive'::character varying)::text, ('project.guide.manage'::character varying)::text, ('project.effective_policy.manage'::character varying)::text, ('project.task.manage'::character varying)::text, ('project.review_policy.manage'::character varying)::text, ('project.role_grant.read'::character varying)::text, ('project.role_grant.manage'::character varying)::text, ('project.setup_diagnostic.read'::character varying)::text, ('project.effective_policy.read'::character varying)::text, ('task.queue.read'::character varying)::text, ('task.claim'::character varying)::text, ('submission.create'::character varying)::text, ('submission.read_own'::character varying)::text, ('submission.read_for_review'::character varying)::text, ('review.queue.read'::character varying)::text, ('review.queue.inspect'::character varying)::text, ('review.claim'::character varying)::text, ('review.release'::character varying)::text, ('review.decline_preference'::character varying)::text, ('review.decision'::character varying)::text, ('review.lease.force_release'::character varying)::text, ('review.chain.read'::character varying)::text, ('contribution.read_self'::character varying)::text, ('contribution.read_project'::character varying)::text, ('compensation.policy.manage'::character varying)::text, ('compensation.adapter_binding.manage'::character varying)::text, ('compensation.award.read'::character varying)::text, ('compensation.delivery.reconcile'::character varying)::text, ('operations.status.read'::character varying)::text, ('operations.timer.run'::character varying)::text, ('operations.reconcile.run'::character varying)::text, ('operations.outbox.retry'::character varying)::text, ('operations.projection.rebuild'::character varying)::text, ('audit.read'::character varying)::text, ('audit.export'::character varying)::text, ('operations.task.start_override'::character varying)::text, ('operations.submission_gate.repair'::character varying)::text, ('operations.checker.retry'::character varying)::text, ('artifact.binding.read'::character varying)::text, ('artifact.replica.read'::character varying)::text, ('artifact.receipt.read'::character varying)::text, ('artifact.verification_job.read'::character varying)::text, ('artifact.verification_job.retry'::character varying)::text, ('artifact.recovery_attempt.read'::character varying)::text, ('artifact.audit.read'::character varying)::text, ('artifact.guide_source.ingest'::character varying)::text, ('artifact.binding.create'::character varying)::text, ('artifact.review_packet.materialize'::character varying)::text, ('artifact.verification.execute'::character varying)::text, ('artifact.pending_work.scan'::character varying)::text, ('artifact.put_attempt.resolve'::character varying)::text, ('artifact.guide_source.read'::character varying)::text, ('artifact.checker_input.materialize'::character varying)::text, ('artifact.checker_output.write'::character varying)::text, ('review.queue.override'::character varying)::text, ('project.guide_compilation.request'::character varying)::text, ('project.guide_compilation.execute'::character varying)::text])))) AND (((entity_type)::text <> ALL (ARRAY[('authorization_decision'::character varying)::text, ('authority_invalidation'::character varying)::text])) OR ((entity_id)::text = (id)::text)) AND (((resource_type)::text <> 'project'::text) OR (resource_id IS NULL) OR ((project_id IS NOT NULL) AND ((resource_id)::text = (project_id)::text)))))),
    CONSTRAINT ck_audit_events_authority_registries CHECK ((((event_domain)::text <> 'authority'::text) OR ((reason IS NOT NULL) AND ((((event_type)::text = 'ActorProfileProvisioned'::text) AND (reason = 'automatic_first_access'::text)) OR (((event_type)::text = 'ServiceActorProvisioned'::text) AND (reason = 'manual_service_provisioning'::text)) OR (((event_type)::text = 'ActorIdentityLinked'::text) AND (reason = 'identity_lifecycle_change'::text)) OR (((event_type)::text = 'ActorIdentityLinkRevoked'::text) AND (reason = 'identity_lifecycle_change'::text)) OR (((event_type)::text = 'ActorIdentityLinkReactivated'::text) AND (reason = 'identity_lifecycle_change'::text)) OR (((event_type)::text = 'ActorProfileSuspended'::text) AND (reason = ANY (ARRAY['security_response'::text, 'administrative_correction'::text]))) OR (((event_type)::text = 'ActorProfileReactivated'::text) AND (reason = 'administrative_correction'::text)) OR (((event_type)::text = 'ActorProfileDeactivated'::text) AND (reason = ANY (ARRAY['security_response'::text, 'administrative_correction'::text]))) OR (((event_type)::text = 'InitialAccessAdministratorBootstrapped'::text) AND (reason = 'initial_access_bootstrap'::text)) OR (((event_type)::text = 'AdminRoleGrantIssued'::text) AND (reason = 'authority_assignment'::text)) OR (((event_type)::text = 'AdminRoleGrantRevoked'::text) AND (reason = 'authority_revocation'::text)) OR (((event_type)::text = 'AdminRoleGrantIssueDenied'::text) AND (reason = 'authorization_policy_denial'::text)) OR (((event_type)::text = 'LastAccessAdministratorOperationDenied'::text) AND (reason = 'authorization_policy_denial'::text)) OR (((event_type)::text = 'ProjectRoleQualificationSnapshotCaptured'::text) AND (reason = 'qualification_evidence_captured'::text)) OR (((event_type)::text = 'ProjectRoleGrantIssued'::text) AND (reason = 'authority_assignment'::text)) OR (((event_type)::text = 'ProjectRoleGrantRevoked'::text) AND (reason = 'authority_revocation'::text)) OR (((event_type)::text = 'SensitiveAuthorizationAllowed'::text) AND (reason = 'authorization_evaluation'::text)) OR (((event_type)::text = 'SensitiveAuthorizationDenied'::text) AND (reason = 'authorization_evaluation'::text)) OR (((event_type)::text = 'AuthorityInvalidationRequested'::text) AND (reason = 'authority_state_changed'::text))) AND ((permission_id IS NULL) OR ((permission_id)::text = ANY (ARRAY[('actor.profile.read_self'::character varying)::text, ('outbox.dispatch'::character varying)::text, ('task.assignment.authority_reconcile'::character varying)::text, ('actor.profile.update_self'::character varying)::text, ('actor.profile.read_any'::character varying)::text, ('actor.profile.suspend'::character varying)::text, ('actor.profile.reactivate'::character varying)::text, ('actor.profile.deactivate'::character varying)::text, ('actor.identity_link.read'::character varying)::text, ('actor.identity_link.revoke'::character varying)::text, ('actor.identity_link.reactivate'::character varying)::text, ('actor.service.provision'::character varying)::text, ('admin_role.read'::character varying)::text, ('admin_role.grant'::character varying)::text, ('admin_role.revoke'::character varying)::text, ('project.create'::character varying)::text, ('project.read'::character varying)::text, ('project.update'::character varying)::text, ('project.archive'::character varying)::text, ('project.guide.manage'::character varying)::text, ('project.effective_policy.manage'::character varying)::text, ('project.task.manage'::character varying)::text, ('project.review_policy.manage'::character varying)::text, ('project.role_grant.read'::character varying)::text, ('project.role_grant.manage'::character varying)::text, ('project.setup_diagnostic.read'::character varying)::text, ('project.effective_policy.read'::character varying)::text, ('task.queue.read'::character varying)::text, ('task.claim'::character varying)::text, ('submission.create'::character varying)::text, ('submission.read_own'::character varying)::text, ('submission.read_for_review'::character varying)::text, ('review.queue.read'::character varying)::text, ('review.queue.inspect'::character varying)::text, ('review.claim'::character varying)::text, ('review.release'::character varying)::text, ('review.decline_preference'::character varying)::text, ('review.decision'::character varying)::text, ('review.lease.force_release'::character varying)::text, ('review.chain.read'::character varying)::text, ('contribution.read_self'::character varying)::text, ('contribution.read_project'::character varying)::text, ('compensation.policy.manage'::character varying)::text, ('compensation.adapter_binding.manage'::character varying)::text, ('compensation.award.read'::character varying)::text, ('compensation.delivery.reconcile'::character varying)::text, ('operations.status.read'::character varying)::text, ('operations.timer.run'::character varying)::text, ('operations.reconcile.run'::character varying)::text, ('operations.outbox.retry'::character varying)::text, ('operations.projection.rebuild'::character varying)::text, ('audit.read'::character varying)::text, ('audit.export'::character varying)::text, ('operations.task.start_override'::character varying)::text, ('operations.submission_gate.repair'::character varying)::text, ('operations.checker.retry'::character varying)::text, ('artifact.binding.read'::character varying)::text, ('artifact.replica.read'::character varying)::text, ('artifact.receipt.read'::character varying)::text, ('artifact.verification_job.read'::character varying)::text, ('artifact.verification_job.retry'::character varying)::text, ('artifact.recovery_attempt.read'::character varying)::text, ('artifact.audit.read'::character varying)::text, ('artifact.guide_source.ingest'::character varying)::text, ('artifact.binding.create'::character varying)::text, ('artifact.review_packet.materialize'::character varying)::text, ('artifact.verification.execute'::character varying)::text, ('artifact.pending_work.scan'::character varying)::text, ('artifact.put_attempt.resolve'::character varying)::text, ('artifact.guide_source.read'::character varying)::text, ('artifact.checker_input.materialize'::character varying)::text, ('artifact.checker_output.write'::character varying)::text, ('review.queue.override'::character varying)::text, ('project.guide_compilation.execute'::character varying)::text, ('project.guide_compilation.request'::character varying)::text]))) AND ((denial_code IS NULL) OR ((denial_code)::text = ANY (ARRAY[('required_scope_missing'::character varying)::text, ('unsupported_subject_kind'::character varying)::text, ('service_actor_not_provisioned'::character varying)::text, ('identity_link_revoked'::character varying)::text, ('actor_suspended'::character varying)::text, ('actor_deactivated'::character varying)::text, ('permission_not_granted'::character varying)::text, ('scope_not_authorized'::character varying)::text, ('self_grant_forbidden'::character varying)::text, ('self_role_revoke_forbidden'::character varying)::text, ('resource_guard_denied'::character varying)::text, ('actor_not_found'::character varying)::text, ('grant_not_found'::character varying)::text, ('resource_not_found'::character varying)::text, ('actor_already_suspended'::character varying)::text, ('actor_not_suspended'::character varying)::text, ('actor_deactivated_terminal'::character varying)::text, ('last_access_administrator'::character varying)::text, ('admin_role_grant_exists'::character varying)::text, ('project_role_grant_exists'::character varying)::text, ('identity_link_conflict'::character varying)::text, ('project_role_grant_already_revoked'::character varying)::text, ('project_role_grant_replay_state_changed'::character varying)::text, ('identity_link_already_revoked'::character varying)::text, ('identity_link_not_revoked'::character varying)::text, ('resource_project_mismatch'::character varying)::text, ('idempotency_mismatch'::character varying)::text, ('invalid_role_scope'::character varying)::text, ('invalid_project_role'::character varying)::text, ('qualification_snapshot_invalid'::character varying)::text])))))),
    CONSTRAINT ck_audit_events_authority_tokens CHECK ((((event_domain)::text <> 'authority'::text) OR ((event_type)::text = ANY (ARRAY[('ActorProfileProvisioned'::character varying)::text, ('ServiceActorProvisioned'::character varying)::text, ('ActorIdentityLinked'::character varying)::text, ('ActorIdentityLinkRevoked'::character varying)::text, ('ActorIdentityLinkReactivated'::character varying)::text, ('ActorProfileSuspended'::character varying)::text, ('ActorProfileReactivated'::character varying)::text, ('ActorProfileDeactivated'::character varying)::text, ('InitialAccessAdministratorBootstrapped'::character varying)::text, ('AdminRoleGrantIssued'::character varying)::text, ('AdminRoleGrantRevoked'::character varying)::text, ('AdminRoleGrantIssueDenied'::character varying)::text, ('LastAccessAdministratorOperationDenied'::character varying)::text, ('ProjectRoleQualificationSnapshotCaptured'::character varying)::text, ('ProjectRoleGrantIssued'::character varying)::text, ('ProjectRoleGrantReplaced'::character varying)::text, ('ProjectRoleGrantRevoked'::character varying)::text, ('SensitiveAuthorizationAllowed'::character varying)::text, ('SensitiveAuthorizationDenied'::character varying)::text, ('AuthorityInvalidationRequested'::character varying)::text])))),
    CONSTRAINT ck_audit_events_authorization_action_evidence CHECK (((((event_domain)::text = 'legacy_lifecycle'::text) AND (action_id IS NULL)) OR (((event_domain)::text = 'authority'::text) AND ((action_id IS NULL) OR (((event_type)::text = ANY (ARRAY[('SensitiveAuthorizationAllowed'::character varying)::text, ('SensitiveAuthorizationDenied'::character varying)::text])) AND (permission_id IS NOT NULL) AND ((((action_id)::text = 'actor.profile.read_self'::text) AND ((permission_id)::text = 'actor.profile.read_self'::text)) OR (((action_id)::text = 'outbox.dispatch'::text) AND ((permission_id)::text = 'outbox.dispatch'::text)) OR (((action_id)::text = 'task.assignment.authority_reconcile'::text) AND ((permission_id)::text = 'task.assignment.authority_reconcile'::text)) OR (((action_id)::text = 'compensation.adapter_binding.read'::text) AND ((permission_id)::text = 'compensation.adapter_binding.manage'::text)) OR (((action_id)::text = 'compensation.adapter_binding.create'::text) AND ((permission_id)::text = 'compensation.adapter_binding.manage'::text)) OR (((action_id)::text = 'compensation.adapter_binding.suspend'::text) AND ((permission_id)::text = 'compensation.adapter_binding.manage'::text)) OR (((action_id)::text = 'compensation.adapter_binding.resume'::text) AND ((permission_id)::text = 'compensation.adapter_binding.manage'::text)) OR (((action_id)::text = 'contribution.policy.read'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text)) OR (((action_id)::text = 'contribution.policy.create_draft'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text)) OR (((action_id)::text = 'contribution.policy.update_draft'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text)) OR (((action_id)::text = 'contribution.policy.publish'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text)) OR (((action_id)::text = 'contribution.policy.retire'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text)) OR (((action_id)::text = 'actor.profile.update_self'::text) AND ((permission_id)::text = 'actor.profile.update_self'::text)) OR (((action_id)::text = 'operations.task.start_override'::text) AND ((permission_id)::text = 'operations.task.start_override'::text)) OR (((action_id)::text = 'task.claim'::text) AND ((permission_id)::text = 'task.claim'::text)) OR (((action_id)::text = 'task.start'::text) AND ((permission_id)::text = 'task.claim'::text)) OR (((action_id)::text = 'task.work_context.read'::text) AND ((permission_id)::text = 'task.queue.read'::text)) OR (((action_id)::text = 'project.task.work_context.read'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'project.task.create'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'project.task.screen'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'project.task.release'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'operations.submission_gate.repair'::text) AND ((permission_id)::text = 'operations.submission_gate.repair'::text)) OR (((action_id)::text = 'operations.checker.retry'::text) AND ((permission_id)::text = 'operations.checker.retry'::text)) OR (((action_id)::text = 'submission.create'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'review.queue.read'::text) AND ((permission_id)::text = 'review.queue.read'::text)) OR (((action_id)::text = 'review.queue.inspect'::text) AND ((permission_id)::text = 'review.queue.inspect'::text)) OR (((action_id)::text = 'review.claim'::text) AND ((permission_id)::text = 'review.claim'::text)) OR (((action_id)::text = 'review.release'::text) AND ((permission_id)::text = 'review.release'::text)) OR (((action_id)::text = 'review.decline_preference'::text) AND ((permission_id)::text = 'review.decline_preference'::text)) OR (((action_id)::text = 'review.preference_expiry.run'::text) AND ((permission_id)::text = 'operations.timer.run'::text)) OR (((action_id)::text = 'review.lease_expiry.run'::text) AND ((permission_id)::text = 'operations.timer.run'::text)) OR (((action_id)::text = 'review.context.read'::text) AND ((permission_id)::text = 'submission.read_for_review'::text)) OR (((action_id)::text = 'review.chain.read'::text) AND ((permission_id)::text = 'review.chain.read'::text)) OR (((action_id)::text = 'review.finding_evidence.ingest'::text) AND ((permission_id)::text = 'review.decision'::text)) OR (((action_id)::text = 'review.decision'::text) AND ((permission_id)::text = 'review.decision'::text)) OR (((action_id)::text = 'review.finding_response_evidence.ingest'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'review.lease.force_release'::text) AND ((permission_id)::text = 'review.lease.force_release'::text)) OR (((action_id)::text = 'review.queue.routing.override'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.queue.routing.correct'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.queue.close'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.reconcile.run'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.artifact_reference.reconcile'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.projection.rebuild'::text) AND ((permission_id)::text = 'operations.projection.rebuild'::text)) OR (((action_id)::text = 'review.revision_context.repair'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'review.revision_obligation.close'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'review.revision_context.legacy_close'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.lifecycle.activation.manage'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'artifact.binding.read'::text) AND ((permission_id)::text = 'artifact.binding.read'::text)) OR (((action_id)::text = 'artifact.replica.read'::text) AND ((permission_id)::text = 'artifact.replica.read'::text)) OR (((action_id)::text = 'artifact.receipt.read'::text) AND ((permission_id)::text = 'artifact.receipt.read'::text)) OR (((action_id)::text = 'artifact.verification_job.read'::text) AND ((permission_id)::text = 'artifact.verification_job.read'::text)) OR (((action_id)::text = 'artifact.verification_job.retry'::text) AND ((permission_id)::text = 'artifact.verification_job.retry'::text)) OR (((action_id)::text = 'artifact.recovery_attempt.read'::text) AND ((permission_id)::text = 'artifact.recovery_attempt.read'::text)) OR (((action_id)::text = 'artifact.audit.read'::text) AND ((permission_id)::text = 'artifact.audit.read'::text)) OR (((action_id)::text = 'operations.artifact_storage_admission.read'::text) AND ((permission_id)::text = 'operations.status.read'::text)) OR (((action_id)::text = 'artifact.guide_source.ingest'::text) AND ((permission_id)::text = 'artifact.guide_source.ingest'::text)) OR (((action_id)::text = 'artifact.submission_bundle.prepare'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'artifact.review_packet.materialize'::text) AND ((permission_id)::text = 'artifact.review_packet.materialize'::text)) OR (((action_id)::text = 'artifact.review_evidence.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.guide_source.read'::text) AND ((permission_id)::text = 'artifact.guide_source.read'::text)) OR (((action_id)::text = 'artifact.guide_source.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.submission.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.checker_output.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.verification.execute'::text) AND ((permission_id)::text = 'artifact.verification.execute'::text)) OR (((action_id)::text = 'artifact.pending_work.scan'::text) AND ((permission_id)::text = 'artifact.pending_work.scan'::text)) OR (((action_id)::text = 'artifact.put_attempt.resolve'::text) AND ((permission_id)::text = 'artifact.put_attempt.resolve'::text)) OR (((action_id)::text = 'artifact.pre_submit.checker_input.materialize'::text) AND ((permission_id)::text = 'artifact.checker_input.materialize'::text)) OR (((action_id)::text = 'artifact.post_submit.checker_input.materialize'::text) AND ((permission_id)::text = 'artifact.checker_input.materialize'::text)) OR (((action_id)::text = 'artifact.checker_output.write'::text) AND ((permission_id)::text = 'artifact.checker_output.write'::text)) OR (((action_id)::text = 'authorization.permission_catalogue.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'authorization.admin_role_definitions.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'admin_role_grant.list'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'actor.admin_role_grant_history.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'admin_role_grant.issue'::text) AND ((permission_id)::text = 'admin_role.grant'::text)) OR (((action_id)::text = 'admin_role_grant.revoke'::text) AND ((permission_id)::text = 'admin_role.revoke'::text)) OR (((action_id)::text = 'admin_role_grant.bootstrap'::text) AND ((permission_id)::text = 'admin_role.grant'::text)) OR (((action_id)::text = 'actor.profile.read'::text) AND ((permission_id)::text = 'actor.profile.read_any'::text)) OR (((action_id)::text = 'actor.profile.suspend'::text) AND ((permission_id)::text = 'actor.profile.suspend'::text)) OR (((action_id)::text = 'actor.profile.reactivate'::text) AND ((permission_id)::text = 'actor.profile.reactivate'::text)) OR (((action_id)::text = 'actor.profile.deactivate'::text) AND ((permission_id)::text = 'actor.profile.deactivate'::text)) OR (((action_id)::text = 'actor.identity_link.read'::text) AND ((permission_id)::text = 'actor.identity_link.read'::text)) OR (((action_id)::text = 'actor.identity_link.revoke'::text) AND ((permission_id)::text = 'actor.identity_link.revoke'::text)) OR (((action_id)::text = 'actor.identity_link.reactivate'::text) AND ((permission_id)::text = 'actor.identity_link.reactivate'::text)) OR (((action_id)::text = 'actor.service.provision'::text) AND ((permission_id)::text = 'actor.service.provision'::text)) OR (((action_id)::text = 'project.contributor_candidate.list'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project_role_grant.list'::text) AND ((permission_id)::text = 'project.role_grant.read'::text)) OR (((action_id)::text = 'project_role_grant.read'::text) AND ((permission_id)::text = 'project.role_grant.read'::text)) OR (((action_id)::text = 'project_role_grant.issue'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project_role_grant.revoke'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project.read'::text) AND ((permission_id)::text = 'project.read'::text)) OR (((action_id)::text = 'actor.authorization_context.read'::text) AND ((permission_id)::text = 'actor.profile.read_self'::text)) OR (((action_id)::text = 'project.setup_run.read'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.list'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.read'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.list'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy_setup.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.effective_submission_artifact_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.pre_submit_checker_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.active_guide.read'::text) AND ((permission_id)::text = 'project.read'::text)) OR (((action_id)::text = 'project.create'::text) AND ((permission_id)::text = 'project.create'::text)) OR (((action_id)::text = 'project.guide.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide.update'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_source_snapshot.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.review_policy.update'::text) AND ((permission_id)::text = 'project.review_policy.manage'::text)) OR (((action_id)::text = 'project.revision_policy.update'::text) AND ((permission_id)::text = 'project.review_policy.manage'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_sufficiency.run'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_compilation.execute'::text) AND ((permission_id)::text = 'project.guide_compilation.execute'::text)) OR (((action_id)::text = 'project.guide_compilation.request_automatic'::text) AND ((permission_id)::text = 'project.guide_compilation.execute'::text)) OR (((action_id)::text = 'project.guide_compilation.request'::text) AND ((permission_id)::text = 'project.guide_compilation.request'::text)) OR (((action_id)::text = 'project.guide_compilation.correction.request'::text) AND ((permission_id)::text = 'project.guide_compilation.request'::text)) OR (((action_id)::text = 'project.guide_compilation.review_package.read'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_sufficiency.warnings.acknowledge'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.create'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.derive'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.update'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.approve'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.approve'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.correction.request'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.derive'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.setup_run.update'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide.activate'::text) AND ((permission_id)::text = 'project.guide.manage'::text))))) AND ((permission_id IS NULL) OR ((permission_id)::text <> ALL (ARRAY[('operations.task.start_override'::character varying)::text, ('operations.submission_gate.repair'::character varying)::text, ('operations.checker.retry'::character varying)::text, ('artifact.binding.read'::character varying)::text, ('artifact.replica.read'::character varying)::text, ('artifact.receipt.read'::character varying)::text, ('artifact.verification_job.read'::character varying)::text, ('artifact.verification_job.retry'::character varying)::text, ('artifact.recovery_attempt.read'::character varying)::text, ('artifact.audit.read'::character varying)::text, ('artifact.guide_source.ingest'::character varying)::text, ('artifact.binding.create'::character varying)::text, ('artifact.review_packet.materialize'::character varying)::text, ('artifact.verification.execute'::character varying)::text, ('artifact.pending_work.scan'::character varying)::text, ('artifact.put_attempt.resolve'::character varying)::text, ('artifact.guide_source.read'::character varying)::text, ('artifact.checker_input.materialize'::character varying)::text, ('artifact.checker_output.write'::character varying)::text, ('review.queue.override'::character varying)::text, ('project.setup_diagnostic.read'::character varying)::text, ('project.effective_policy.read'::character varying)::text, ('project.guide_compilation.request'::character varying)::text, ('project.guide_compilation.execute'::character varying)::text])) OR ((action_id IS NOT NULL) AND ((((action_id)::text = 'actor.profile.read_self'::text) AND ((permission_id)::text = 'actor.profile.read_self'::text)) OR (((action_id)::text = 'outbox.dispatch'::text) AND ((permission_id)::text = 'outbox.dispatch'::text)) OR (((action_id)::text = 'task.assignment.authority_reconcile'::text) AND ((permission_id)::text = 'task.assignment.authority_reconcile'::text)) OR (((action_id)::text = 'compensation.adapter_binding.read'::text) AND ((permission_id)::text = 'compensation.adapter_binding.manage'::text)) OR (((action_id)::text = 'compensation.adapter_binding.create'::text) AND ((permission_id)::text = 'compensation.adapter_binding.manage'::text)) OR (((action_id)::text = 'compensation.adapter_binding.suspend'::text) AND ((permission_id)::text = 'compensation.adapter_binding.manage'::text)) OR (((action_id)::text = 'compensation.adapter_binding.resume'::text) AND ((permission_id)::text = 'compensation.adapter_binding.manage'::text)) OR (((action_id)::text = 'contribution.policy.read'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text)) OR (((action_id)::text = 'contribution.policy.create_draft'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text)) OR (((action_id)::text = 'contribution.policy.update_draft'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text)) OR (((action_id)::text = 'contribution.policy.publish'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text)) OR (((action_id)::text = 'contribution.policy.retire'::text) AND ((permission_id)::text = 'compensation.policy.manage'::text)) OR (((action_id)::text = 'actor.profile.update_self'::text) AND ((permission_id)::text = 'actor.profile.update_self'::text)) OR (((action_id)::text = 'operations.task.start_override'::text) AND ((permission_id)::text = 'operations.task.start_override'::text)) OR (((action_id)::text = 'task.claim'::text) AND ((permission_id)::text = 'task.claim'::text)) OR (((action_id)::text = 'task.start'::text) AND ((permission_id)::text = 'task.claim'::text)) OR (((action_id)::text = 'task.work_context.read'::text) AND ((permission_id)::text = 'task.queue.read'::text)) OR (((action_id)::text = 'project.task.work_context.read'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'project.task.create'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'project.task.screen'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'project.task.release'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'operations.submission_gate.repair'::text) AND ((permission_id)::text = 'operations.submission_gate.repair'::text)) OR (((action_id)::text = 'operations.checker.retry'::text) AND ((permission_id)::text = 'operations.checker.retry'::text)) OR (((action_id)::text = 'submission.create'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'review.queue.read'::text) AND ((permission_id)::text = 'review.queue.read'::text)) OR (((action_id)::text = 'review.queue.inspect'::text) AND ((permission_id)::text = 'review.queue.inspect'::text)) OR (((action_id)::text = 'review.claim'::text) AND ((permission_id)::text = 'review.claim'::text)) OR (((action_id)::text = 'review.release'::text) AND ((permission_id)::text = 'review.release'::text)) OR (((action_id)::text = 'review.decline_preference'::text) AND ((permission_id)::text = 'review.decline_preference'::text)) OR (((action_id)::text = 'review.preference_expiry.run'::text) AND ((permission_id)::text = 'operations.timer.run'::text)) OR (((action_id)::text = 'review.lease_expiry.run'::text) AND ((permission_id)::text = 'operations.timer.run'::text)) OR (((action_id)::text = 'review.context.read'::text) AND ((permission_id)::text = 'submission.read_for_review'::text)) OR (((action_id)::text = 'review.chain.read'::text) AND ((permission_id)::text = 'review.chain.read'::text)) OR (((action_id)::text = 'review.finding_evidence.ingest'::text) AND ((permission_id)::text = 'review.decision'::text)) OR (((action_id)::text = 'review.decision'::text) AND ((permission_id)::text = 'review.decision'::text)) OR (((action_id)::text = 'review.finding_response_evidence.ingest'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'review.lease.force_release'::text) AND ((permission_id)::text = 'review.lease.force_release'::text)) OR (((action_id)::text = 'review.queue.routing.override'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.queue.routing.correct'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.queue.close'::text) AND ((permission_id)::text = 'review.queue.override'::text)) OR (((action_id)::text = 'review.reconcile.run'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.artifact_reference.reconcile'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.projection.rebuild'::text) AND ((permission_id)::text = 'operations.projection.rebuild'::text)) OR (((action_id)::text = 'review.revision_context.repair'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'review.revision_obligation.close'::text) AND ((permission_id)::text = 'project.task.manage'::text)) OR (((action_id)::text = 'review.revision_context.legacy_close'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'review.lifecycle.activation.manage'::text) AND ((permission_id)::text = 'operations.reconcile.run'::text)) OR (((action_id)::text = 'artifact.binding.read'::text) AND ((permission_id)::text = 'artifact.binding.read'::text)) OR (((action_id)::text = 'artifact.replica.read'::text) AND ((permission_id)::text = 'artifact.replica.read'::text)) OR (((action_id)::text = 'artifact.receipt.read'::text) AND ((permission_id)::text = 'artifact.receipt.read'::text)) OR (((action_id)::text = 'artifact.verification_job.read'::text) AND ((permission_id)::text = 'artifact.verification_job.read'::text)) OR (((action_id)::text = 'artifact.verification_job.retry'::text) AND ((permission_id)::text = 'artifact.verification_job.retry'::text)) OR (((action_id)::text = 'artifact.recovery_attempt.read'::text) AND ((permission_id)::text = 'artifact.recovery_attempt.read'::text)) OR (((action_id)::text = 'artifact.audit.read'::text) AND ((permission_id)::text = 'artifact.audit.read'::text)) OR (((action_id)::text = 'operations.artifact_storage_admission.read'::text) AND ((permission_id)::text = 'operations.status.read'::text)) OR (((action_id)::text = 'artifact.guide_source.ingest'::text) AND ((permission_id)::text = 'artifact.guide_source.ingest'::text)) OR (((action_id)::text = 'artifact.submission_bundle.prepare'::text) AND ((permission_id)::text = 'submission.create'::text)) OR (((action_id)::text = 'artifact.review_packet.materialize'::text) AND ((permission_id)::text = 'artifact.review_packet.materialize'::text)) OR (((action_id)::text = 'artifact.review_evidence.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.guide_source.read'::text) AND ((permission_id)::text = 'artifact.guide_source.read'::text)) OR (((action_id)::text = 'artifact.guide_source.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.submission.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.checker_output.binding.create'::text) AND ((permission_id)::text = 'artifact.binding.create'::text)) OR (((action_id)::text = 'artifact.verification.execute'::text) AND ((permission_id)::text = 'artifact.verification.execute'::text)) OR (((action_id)::text = 'artifact.pending_work.scan'::text) AND ((permission_id)::text = 'artifact.pending_work.scan'::text)) OR (((action_id)::text = 'artifact.put_attempt.resolve'::text) AND ((permission_id)::text = 'artifact.put_attempt.resolve'::text)) OR (((action_id)::text = 'artifact.pre_submit.checker_input.materialize'::text) AND ((permission_id)::text = 'artifact.checker_input.materialize'::text)) OR (((action_id)::text = 'artifact.post_submit.checker_input.materialize'::text) AND ((permission_id)::text = 'artifact.checker_input.materialize'::text)) OR (((action_id)::text = 'artifact.checker_output.write'::text) AND ((permission_id)::text = 'artifact.checker_output.write'::text)) OR (((action_id)::text = 'authorization.permission_catalogue.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'authorization.admin_role_definitions.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'admin_role_grant.list'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'actor.admin_role_grant_history.read'::text) AND ((permission_id)::text = 'admin_role.read'::text)) OR (((action_id)::text = 'admin_role_grant.issue'::text) AND ((permission_id)::text = 'admin_role.grant'::text)) OR (((action_id)::text = 'admin_role_grant.revoke'::text) AND ((permission_id)::text = 'admin_role.revoke'::text)) OR (((action_id)::text = 'admin_role_grant.bootstrap'::text) AND ((permission_id)::text = 'admin_role.grant'::text)) OR (((action_id)::text = 'actor.profile.read'::text) AND ((permission_id)::text = 'actor.profile.read_any'::text)) OR (((action_id)::text = 'actor.profile.suspend'::text) AND ((permission_id)::text = 'actor.profile.suspend'::text)) OR (((action_id)::text = 'actor.profile.reactivate'::text) AND ((permission_id)::text = 'actor.profile.reactivate'::text)) OR (((action_id)::text = 'actor.profile.deactivate'::text) AND ((permission_id)::text = 'actor.profile.deactivate'::text)) OR (((action_id)::text = 'actor.identity_link.read'::text) AND ((permission_id)::text = 'actor.identity_link.read'::text)) OR (((action_id)::text = 'actor.identity_link.revoke'::text) AND ((permission_id)::text = 'actor.identity_link.revoke'::text)) OR (((action_id)::text = 'actor.identity_link.reactivate'::text) AND ((permission_id)::text = 'actor.identity_link.reactivate'::text)) OR (((action_id)::text = 'actor.service.provision'::text) AND ((permission_id)::text = 'actor.service.provision'::text)) OR (((action_id)::text = 'project.contributor_candidate.list'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project_role_grant.list'::text) AND ((permission_id)::text = 'project.role_grant.read'::text)) OR (((action_id)::text = 'project_role_grant.read'::text) AND ((permission_id)::text = 'project.role_grant.read'::text)) OR (((action_id)::text = 'project_role_grant.issue'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project_role_grant.revoke'::text) AND ((permission_id)::text = 'project.role_grant.manage'::text)) OR (((action_id)::text = 'project.read'::text) AND ((permission_id)::text = 'project.read'::text)) OR (((action_id)::text = 'actor.authorization_context.read'::text) AND ((permission_id)::text = 'actor.profile.read_self'::text)) OR (((action_id)::text = 'project.setup_run.read'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.list'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.read'::text) AND ((permission_id)::text = 'project.setup_diagnostic.read'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.list'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy_setup.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.effective_submission_artifact_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.pre_submit_checker_policy.read'::text) AND ((permission_id)::text = 'project.effective_policy.read'::text)) OR (((action_id)::text = 'project.active_guide.read'::text) AND ((permission_id)::text = 'project.read'::text)) OR (((action_id)::text = 'project.create'::text) AND ((permission_id)::text = 'project.create'::text)) OR (((action_id)::text = 'project.guide.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide.update'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_source_snapshot.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.review_policy.update'::text) AND ((permission_id)::text = 'project.review_policy.manage'::text)) OR (((action_id)::text = 'project.revision_policy.update'::text) AND ((permission_id)::text = 'project.review_policy.manage'::text)) OR (((action_id)::text = 'project.guide_sufficiency_report.create'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_sufficiency.run'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_compilation.execute'::text) AND ((permission_id)::text = 'project.guide_compilation.execute'::text)) OR (((action_id)::text = 'project.guide_compilation.request_automatic'::text) AND ((permission_id)::text = 'project.guide_compilation.execute'::text)) OR (((action_id)::text = 'project.guide_compilation.request'::text) AND ((permission_id)::text = 'project.guide_compilation.request'::text)) OR (((action_id)::text = 'project.guide_compilation.correction.request'::text) AND ((permission_id)::text = 'project.guide_compilation.request'::text)) OR (((action_id)::text = 'project.guide_compilation.review_package.read'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide_sufficiency.warnings.acknowledge'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.create'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.derive'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.update'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.submission_artifact_policy.approve'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.approve'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.correction.request'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.post_submit_checker_policy.derive'::text) AND ((permission_id)::text = 'project.effective_policy.manage'::text)) OR (((action_id)::text = 'project.setup_run.update'::text) AND ((permission_id)::text = 'project.guide.manage'::text)) OR (((action_id)::text = 'project.guide.activate'::text) AND ((permission_id)::text = 'project.guide.manage'::text)))))))),
    CONSTRAINT ck_audit_events_domain_shape CHECK (((((event_domain)::text = 'legacy_lifecycle'::text) AND (event_version IS NULL) AND (occurred_at IS NULL) AND (actor_ref_kind IS NULL) AND (request_id IS NULL) AND (correlation_id IS NULL) AND (target_actor_ref_kind IS NULL) AND (target_actor_ref IS NULL) AND (matched_grant_id IS NULL) AND (permission_id IS NULL) AND (project_id IS NULL) AND (resource_type IS NULL) AND (resource_id IS NULL) AND (target_ref_kind IS NULL) AND (target_ref_id IS NULL) AND (denial_code IS NULL) AND (idempotency_reference IS NULL) AND (invalidation_cause_event_id IS NULL) AND (invalidation_target_kind IS NULL) AND (invalidation_target_ref IS NULL) AND (before_facts IS NULL) AND (after_facts IS NULL) AND (external_subject IS NOT NULL) AND (external_issuer IS NOT NULL)) OR (((event_domain)::text = 'authority'::text) AND (event_version = 1) AND (occurred_at IS NOT NULL) AND ((actor_ref_kind)::text = ANY (ARRAY[('legacy_actor'::character varying)::text, ('actor_profile'::character varying)::text, ('system_principal'::character varying)::text])) AND (request_id IS NOT NULL) AND (correlation_id IS NOT NULL) AND (from_status IS NULL) AND (to_status IS NULL) AND (reason IS NOT NULL) AND (external_subject IS NULL) AND (external_issuer IS NULL) AND ((actor_roles)::jsonb = '[]'::jsonb) AND ((claim_snapshot)::jsonb = '{}'::jsonb) AND ((auth_source)::text = 'local_authority'::text) AND (is_dev_auth = false) AND ((event_payload)::jsonb = '{}'::jsonb)))),
    CONSTRAINT ck_audit_events_fact_bounds CHECK ((((event_domain)::text <> 'authority'::text) OR (((before_facts IS NULL) OR (octet_length((before_facts)::text) <= 4096)) AND ((after_facts IS NULL) OR (octet_length((after_facts)::text) <= 4096)) AND COALESCE(public.authority_event_facts_are_safe((event_type)::text, before_facts, after_facts, (project_id)::text), false)))),
    CONSTRAINT ck_audit_events_foundation_shapes CHECK ((((event_domain)::text <> 'authority'::text) OR ((event_type)::text <> ALL (ARRAY[('SensitiveAuthorizationAllowed'::character varying)::text, ('SensitiveAuthorizationDenied'::character varying)::text, ('AuthorityInvalidationRequested'::character varying)::text, ('AdminRoleGrantIssueDenied'::character varying)::text, ('LastAccessAdministratorOperationDenied'::character varying)::text])) OR (((event_type)::text = ANY (ARRAY[('AdminRoleGrantIssueDenied'::character varying)::text, ('LastAccessAdministratorOperationDenied'::character varying)::text])) AND (denial_code IS NOT NULL)) OR (((event_type)::text = 'SensitiveAuthorizationAllowed'::text) AND (permission_id IS NOT NULL) AND (denial_code IS NULL) AND (invalidation_cause_event_id IS NULL) AND (invalidation_target_kind IS NULL)) OR (((event_type)::text = 'SensitiveAuthorizationDenied'::text) AND (permission_id IS NOT NULL) AND (denial_code IS NOT NULL) AND (invalidation_cause_event_id IS NULL) AND (invalidation_target_kind IS NULL) AND (idempotency_reference IS NULL)) OR (((event_type)::text = 'AuthorityInvalidationRequested'::text) AND (invalidation_cause_event_id IS NOT NULL) AND (invalidation_target_kind IS NOT NULL) AND (denial_code IS NULL)))),
    CONSTRAINT ck_audit_events_reference_pairs CHECK ((((target_actor_ref_kind IS NULL) = (target_actor_ref IS NULL)) AND ((resource_type IS NOT NULL) OR (resource_id IS NULL)) AND ((target_ref_kind IS NULL) = (target_ref_id IS NULL)) AND ((invalidation_target_kind IS NULL) = (invalidation_target_ref IS NULL)) AND ((invalidation_cause_event_id IS NULL) OR ((invalidation_cause_event_id)::text <> (id)::text))))
);
CREATE TABLE public.authority_control (
    id smallint NOT NULL,
    bootstrap_completed boolean DEFAULT false NOT NULL,
    bootstrap_grant_id uuid,
    version smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_authority_control_bootstrap_state CHECK ((((bootstrap_completed = false) AND (bootstrap_grant_id IS NULL) AND (version = 0)) OR ((bootstrap_completed = true) AND (bootstrap_grant_id IS NOT NULL) AND (version = 1)))),
    CONSTRAINT ck_authority_control_singleton CHECK ((id = 1))
);
CREATE SEQUENCE public.authority_control_id_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.authority_control_id_seq OWNED BY public.authority_control.id;
CREATE TABLE public.authority_idempotency_records (
    id uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    actor_ref_kind character varying(32) NOT NULL,
    actor_ref character varying(100) NOT NULL,
    operation character varying(48) NOT NULL,
    request_digest character varying(71) NOT NULL,
    status character varying(16) NOT NULL,
    response_resource_type character varying(32),
    response_resource_id uuid,
    response_resource_version bigint,
    response_http_status smallint,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_authority_idempotency_records_actor_kind CHECK (((actor_ref_kind)::text = ANY (ARRAY[('legacy_actor'::character varying)::text, ('actor_profile'::character varying)::text, ('system_principal'::character varying)::text]))),
    CONSTRAINT ck_authority_idempotency_records_actor_reference CHECK (((((actor_ref_kind)::text = 'system_principal'::text) AND ((actor_ref)::text = 'workstream:system:bootstrap'::text)) OR (((actor_ref_kind)::text <> 'system_principal'::text) AND ((actor_ref)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)))),
    CONSTRAINT ck_authority_idempotency_records_operation CHECK (((operation)::text = ANY (ARRAY[('service_actor.create'::character varying)::text, ('admin_role_grant.issue'::character varying)::text, ('admin_role_grant.revoke'::character varying)::text, ('project_role_grant.issue'::character varying)::text, ('project_role_grant.revoke'::character varying)::text, ('actor_profile.suspend'::character varying)::text, ('actor_profile.reactivate'::character varying)::text, ('actor_profile.deactivate'::character varying)::text, ('actor_identity_link.revoke'::character varying)::text, ('actor_identity_link.reactivate'::character varying)::text]))),
    CONSTRAINT ck_authority_idempotency_records_request_digest CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_authority_idempotency_records_response_status CHECK (((response_http_status IS NULL) OR ((((operation)::text = ANY (ARRAY[('service_actor.create'::character varying)::text, ('admin_role_grant.issue'::character varying)::text, ('project_role_grant.issue'::character varying)::text])) AND (response_http_status = 201)) OR (((operation)::text <> ALL (ARRAY[('service_actor.create'::character varying)::text, ('admin_role_grant.issue'::character varying)::text, ('project_role_grant.issue'::character varying)::text])) AND (response_http_status = 200))))),
    CONSTRAINT ck_authority_idempotency_records_response_type CHECK (((((operation)::text = 'service_actor.create'::text) AND ((response_resource_type IS NULL) OR ((response_resource_type)::text = 'actor_profile'::text))) OR (((operation)::text ~~ 'admin_role_grant.%'::text) AND ((response_resource_type IS NULL) OR ((response_resource_type)::text = 'admin_role_grant'::text))) OR (((operation)::text ~~ 'project_role_grant.%'::text) AND ((response_resource_type IS NULL) OR ((response_resource_type)::text = 'project_role_grant'::text))) OR (((operation)::text ~~ 'actor_profile.%'::text) AND ((response_resource_type IS NULL) OR ((response_resource_type)::text = 'actor_profile'::text))) OR (((operation)::text ~~ 'actor_identity_link.%'::text) AND ((response_resource_type IS NULL) OR ((response_resource_type)::text = 'actor_identity_link'::text))))),
    CONSTRAINT ck_authority_idempotency_records_response_version CHECK (((response_resource_version IS NULL) OR (response_resource_version > 0))),
    CONSTRAINT ck_authority_idempotency_records_state_shape CHECK (((((status)::text = 'pending'::text) AND (response_resource_type IS NULL) AND (response_resource_id IS NULL) AND (response_resource_version IS NULL) AND (response_http_status IS NULL) AND (committed_at IS NULL)) OR (((status)::text = 'committed'::text) AND (response_resource_type IS NOT NULL) AND (response_resource_id IS NOT NULL) AND (response_http_status IS NOT NULL) AND (committed_at IS NOT NULL)))),
    CONSTRAINT ck_authority_idempotency_records_status CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('committed'::character varying)::text])))
);
CREATE TABLE public.checker_policies (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    required_checkers json NOT NULL,
    warning_checkers json NOT NULL,
    blocking_severities json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    policy_hash character varying(71),
    policy_body json,
    guide_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    effective_policy_id uuid NOT NULL,
    effective_policy_hash character varying(71) NOT NULL,
    pre_submit_checker_policy_id uuid NOT NULL,
    pre_submit_checker_bundle_hash character varying(71) NOT NULL,
    lifecycle_status character varying(30) NOT NULL,
    approved_by_role character varying(50),
    approved_by_actor character varying(100),
    approved_at timestamp with time zone,
    created_by character varying(100) NOT NULL,
    supersedes_policy_id uuid,
    superseded_at timestamp with time zone,
    superseded_by_role character varying(50),
    superseded_by_actor character varying(100),
    supersession_kind character varying(50),
    supersession_reason text,
    projection_operation_id uuid,
    approval_operation_id uuid,
    supersession_operation_id uuid,
    CONSTRAINT ck_checker_policies_lifecycle_status CHECK (((lifecycle_status)::text = ANY (ARRAY[('compiled'::character varying)::text, ('approved'::character varying)::text, ('superseded'::character varying)::text]))),
    CONSTRAINT ck_checker_policies_policy_hash_shape CHECK (((policy_hash IS NULL) OR ((policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text)))
);
CREATE TABLE public.checker_results (
    id uuid NOT NULL,
    checker_run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    submission_id uuid NOT NULL,
    checker_name character varying(100) NOT NULL,
    status character varying(30) NOT NULL,
    severity character varying(30) NOT NULL,
    blocks_review boolean NOT NULL,
    message text NOT NULL,
    worker_message text,
    worker_suggested_fix text,
    worker_evidence_refs json NOT NULL,
    worker_visible boolean NOT NULL,
    metadata json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.checker_runs (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    submission_id uuid NOT NULL,
    submission_version integer NOT NULL,
    trigger_source character varying(50) NOT NULL,
    status character varying(30) NOT NULL,
    routing_recommendation character varying(50) NOT NULL,
    outcome_source character varying(50) NOT NULL,
    triggered_by character varying(100) NOT NULL,
    triggered_by_subject character varying(200) NOT NULL,
    triggered_by_issuer character varying(200) NOT NULL,
    trigger_auth_source character varying(30) NOT NULL,
    trigger_reason text,
    audit_event_id uuid,
    attempt_number integer NOT NULL,
    supersedes_checker_run_id uuid,
    is_current_for_submission boolean NOT NULL,
    locked_guide_version character varying(50) NOT NULL,
    locked_payment_policy_version character varying(50),
    package_hash character varying(128) NOT NULL,
    artifact_hash_manifest json NOT NULL,
    artifact_manifest_hash character varying(128) NOT NULL,
    passed_count integer NOT NULL,
    warning_count integer NOT NULL,
    failed_count integer NOT NULL,
    blocking_count integer NOT NULL,
    queued_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    failure_code character varying(100),
    failure_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    locked_post_submit_checker_policy_id uuid,
    locked_post_submit_checker_policy_version character varying(50),
    locked_post_submit_checker_policy_hash character varying(71),
    locked_post_submit_checker_policy_body json,
    locked_review_policy_id uuid NOT NULL,
    locked_review_policy_generation integer NOT NULL,
    locked_review_policy_hash character varying(71) NOT NULL,
    locked_revision_policy_id uuid NOT NULL,
    locked_revision_policy_generation integer NOT NULL,
    locked_revision_policy_hash character varying(71) NOT NULL,
    CONSTRAINT ck_checker_runs_post_submit_policy_lock_complete CHECK (((locked_post_submit_checker_policy_id IS NOT NULL) AND (locked_post_submit_checker_policy_version IS NOT NULL) AND (locked_post_submit_checker_policy_hash IS NOT NULL) AND (locked_post_submit_checker_policy_body IS NOT NULL)))
);
CREATE TABLE public.compensation_adapter_binding_lifecycle_events (
    id uuid NOT NULL,
    operation_id uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    project_id uuid NOT NULL,
    adapter_binding_id uuid NOT NULL,
    event_type character varying(16) NOT NULL,
    actor_profile_id uuid NOT NULL,
    from_status character varying(16),
    to_status character varying(16) NOT NULL,
    from_lifecycle_version integer NOT NULL,
    to_lifecycle_version integer NOT NULL,
    prior_suspension_event_id uuid,
    occurred_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_compensation_adapter_binding_lifecycle_events_ck_com_5a9c CHECK (((((event_type)::text = 'created'::text) AND (from_status IS NULL) AND ((to_status)::text = 'active'::text) AND (from_lifecycle_version = 0) AND (to_lifecycle_version = 1) AND (prior_suspension_event_id IS NULL)) OR (((event_type)::text = 'suspended'::text) AND ((from_status)::text = 'active'::text) AND ((to_status)::text = 'suspended'::text) AND (from_lifecycle_version > 0) AND (to_lifecycle_version = (from_lifecycle_version + 1)) AND (prior_suspension_event_id IS NULL)) OR (((event_type)::text = 'resumed'::text) AND ((from_status)::text = 'suspended'::text) AND ((to_status)::text = 'active'::text) AND (from_lifecycle_version > 0) AND (to_lifecycle_version = (from_lifecycle_version + 1)) AND (prior_suspension_event_id IS NOT NULL)))),
    CONSTRAINT ck_compensation_adapter_binding_lifecycle_events_ck_com_9ab0 CHECK (((event_type)::text = ANY ((ARRAY['created'::character varying, 'suspended'::character varying, 'resumed'::character varying])::text[]))),
    CONSTRAINT ck_compensation_adapter_binding_lifecycle_events_ck_com_d58f CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))
);
CREATE TABLE public.contribution_award_definitions (
    id uuid NOT NULL,
    contribution_rule_id uuid NOT NULL,
    contribution_policy_version_id uuid NOT NULL,
    project_id uuid NOT NULL,
    contribution_type character varying(32) NOT NULL,
    instrument_type character varying(32) NOT NULL,
    unit_code character varying(32) NOT NULL,
    quantity numeric NOT NULL,
    adapter_binding_id uuid NOT NULL,
    CONSTRAINT ck_contribution_award_definitions_contribution_type CHECK (((contribution_type)::text = ANY (ARRAY[('accepted_submission'::character varying)::text, ('completed_review'::character varying)::text]))),
    CONSTRAINT ck_contribution_award_definitions_instrument_type CHECK (((instrument_type)::text = ANY (ARRAY[('money'::character varying)::text, ('project_points'::character varying)::text]))),
    CONSTRAINT ck_contribution_award_definitions_project_points_whole CHECK ((((instrument_type)::text <> 'project_points'::text) OR (scale(quantity) = 0))),
    CONSTRAINT ck_contribution_award_definitions_quantity_exact_bounds CHECK (((quantity > (0)::numeric) AND (quantity < '100000000000000000000'::numeric) AND ((scale(quantity) >= 0) AND (scale(quantity) <= 18))))
);
CREATE TABLE public.contribution_policies (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    name character varying(200) NOT NULL,
    status character varying(16) DEFAULT 'draft'::character varying NOT NULL,
    current_published_version_id uuid,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    retired_by uuid,
    retired_at timestamp with time zone,
    last_transition_operation_id uuid,
    CONSTRAINT ck_contribution_policies_lifecycle_shape CHECK (((((status)::text = 'draft'::text) AND (current_published_version_id IS NULL) AND (retired_by IS NULL) AND (retired_at IS NULL)) OR (((status)::text = 'active'::text) AND (current_published_version_id IS NOT NULL) AND (retired_by IS NULL) AND (retired_at IS NULL)) OR (((status)::text = 'retired'::text) AND (current_published_version_id IS NOT NULL) AND (retired_by IS NOT NULL) AND (retired_at IS NOT NULL)))),
    CONSTRAINT ck_contribution_policies_name CHECK (((char_length(btrim((name)::text)) >= 1) AND (char_length(btrim((name)::text)) <= 200))),
    CONSTRAINT ck_contribution_policies_retirement_timestamp CHECK (((retired_at IS NULL) OR (retired_at >= created_at))),
    CONSTRAINT ck_contribution_policies_status CHECK (((status)::text = ANY (ARRAY[('draft'::character varying)::text, ('active'::character varying)::text, ('retired'::character varying)::text])))
);
CREATE TABLE public.contribution_policy_lifecycle_events (
    id uuid NOT NULL,
    operation_id uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    event_type character varying(24) NOT NULL,
    actor_profile_id uuid NOT NULL,
    project_id uuid NOT NULL,
    contribution_policy_id uuid NOT NULL,
    contribution_policy_version_id uuid NOT NULL,
    version_number integer NOT NULL,
    prior_current_version_id uuid,
    prior_current_version_number integer,
    from_policy_status character varying(16),
    to_policy_status character varying(16) NOT NULL,
    from_version_status character varying(16),
    to_version_status character varying(16) NOT NULL,
    occurred_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    publication_custody_operation_id uuid,
    CONSTRAINT ck_contribution_policy_lifecycle_events_ck_contribution_3c7d CHECK (((event_type)::text = ANY ((ARRAY['draft_created'::character varying, 'draft_updated'::character varying, 'published'::character varying, 'retired'::character varying])::text[]))),
    CONSTRAINT ck_contribution_policy_lifecycle_events_ck_contribution_4519 CHECK (((((event_type)::text = 'draft_created'::text) AND (from_version_status IS NULL) AND ((to_version_status)::text = 'draft'::text)) OR (((event_type)::text = 'draft_updated'::text) AND ((from_version_status)::text = 'draft'::text) AND ((to_version_status)::text = 'draft'::text)) OR (((event_type)::text = 'published'::text) AND ((from_version_status)::text = 'draft'::text) AND ((to_version_status)::text = 'published'::text)) OR (((event_type)::text = 'retired'::text) AND ((from_version_status)::text = 'published'::text) AND ((to_version_status)::text = 'retired'::text)))),
    CONSTRAINT ck_contribution_policy_lifecycle_events_ck_contribution_8115 CHECK (((((event_type)::text = ANY ((ARRAY['draft_created'::character varying, 'draft_updated'::character varying])::text[])) AND (publication_custody_operation_id IS NULL)) OR (((event_type)::text = ANY ((ARRAY['published'::character varying, 'retired'::character varying])::text[])) AND (publication_custody_operation_id = operation_id)))),
    CONSTRAINT ck_contribution_policy_lifecycle_events_ck_contribution_fca0 CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))
);
CREATE TABLE public.contribution_policy_transition_custody (
    id uuid NOT NULL,
    operation_id uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    event_type character varying(24) NOT NULL,
    actor_profile_id uuid NOT NULL,
    project_id uuid NOT NULL,
    contribution_policy_id uuid NOT NULL,
    contribution_policy_version_id uuid NOT NULL,
    prior_current_version_id uuid,
    occurred_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ck_contribution_policy_transition_custody_ck_contributi_003a CHECK (((event_type)::text = ANY ((ARRAY['published'::character varying, 'retired'::character varying])::text[]))),
    CONSTRAINT ck_contribution_policy_transition_custody_ck_contributi_11cd CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))
);
CREATE TABLE public.contribution_policy_versions (
    id uuid NOT NULL,
    contribution_policy_id uuid NOT NULL,
    project_id uuid NOT NULL,
    version_number integer NOT NULL,
    status character varying(16) DEFAULT 'draft'::character varying NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    published_by uuid,
    published_at timestamp with time zone,
    retired_by uuid,
    retired_at timestamp with time zone,
    last_updated_by uuid,
    last_updated_at timestamp with time zone,
    last_transition_operation_id uuid,
    CONSTRAINT ck_contribution_policy_versions_lifecycle_shape CHECK (((((status)::text = 'draft'::text) AND (published_by IS NULL) AND (published_at IS NULL) AND (retired_by IS NULL) AND (retired_at IS NULL)) OR (((status)::text = 'published'::text) AND (published_by IS NOT NULL) AND (published_at IS NOT NULL) AND (retired_by IS NULL) AND (retired_at IS NULL)) OR (((status)::text = 'retired'::text) AND (published_by IS NOT NULL) AND (published_at IS NOT NULL) AND (retired_by IS NOT NULL) AND (retired_at IS NOT NULL)))),
    CONSTRAINT ck_contribution_policy_versions_lifecycle_timestamps CHECK ((((published_at IS NULL) OR (published_at >= created_at)) AND ((retired_at IS NULL) OR (retired_at >= published_at)))),
    CONSTRAINT ck_contribution_policy_versions_status CHECK (((status)::text = ANY (ARRAY[('draft'::character varying)::text, ('published'::character varying)::text, ('retired'::character varying)::text]))),
    CONSTRAINT ck_contribution_policy_versions_version_number_positive CHECK ((version_number > 0))
);
CREATE TABLE public.contribution_rules (
    id uuid NOT NULL,
    contribution_policy_version_id uuid NOT NULL,
    project_id uuid NOT NULL,
    contribution_type character varying(32) NOT NULL,
    compensation_mode character varying(16) NOT NULL,
    CONSTRAINT ck_contribution_rules_compensation_mode CHECK (((compensation_mode)::text = ANY (ARRAY[('unpaid'::character varying)::text, ('compensated'::character varying)::text]))),
    CONSTRAINT ck_contribution_rules_contribution_type CHECK (((contribution_type)::text = ANY (ARRAY[('accepted_submission'::character varying)::text, ('completed_review'::character varying)::text])))
);
CREATE TABLE public.effective_project_submission_artifact_policies (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    submission_artifact_policy_id uuid NOT NULL,
    submission_artifact_policy_hash character varying(71) NOT NULL,
    lifecycle_status character varying(30) NOT NULL,
    merge_algorithm_version character varying(50) NOT NULL,
    effective_policy json NOT NULL,
    effective_policy_hash character varying(71) NOT NULL,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    supersedes_effective_policy_id uuid,
    superseded_at timestamp with time zone,
    created_by_actor_profile_id uuid,
    created_via_identity_link_id uuid,
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_scope_project_id uuid,
    creation_action_id character varying(160),
    creation_decision_event_id uuid,
    CONSTRAINT ck_effective_project_submission_artifact_policies_ck_ef_7be7 CHECK (((lifecycle_status)::text = ANY (ARRAY[('approved'::character varying)::text, ('superseded'::character varying)::text]))),
    CONSTRAINT ck_effective_project_submission_artifact_policies_ck_ef_bd4e CHECK ((((created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (creation_scope_type IS NULL) AND (creation_scope_project_id IS NULL) AND (creation_action_id IS NULL) AND (creation_decision_event_id IS NULL)) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND (creation_scope_type IS NOT NULL) AND (creation_action_id IS NOT NULL) AND ((creation_scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text])) AND (creation_scope_project_id IS NOT NULL) AND ((creation_scope_project_id)::text = (project_id)::text) AND ((creation_action_id)::text = 'project.submission_artifact_policy.approve'::text) AND (creation_decision_event_id IS NOT NULL))))
);
CREATE TABLE public.evidence_items (
    id uuid NOT NULL,
    submission_id uuid NOT NULL,
    type character varying(50) NOT NULL,
    label character varying(200) NOT NULL,
    uri character varying(1000),
    hash character varying(128),
    size_bytes integer,
    locked_at timestamp with time zone,
    metadata json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.guide_mutation_idempotency_records (
    id uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    action_id character varying(160) NOT NULL,
    idempotency_key uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    resource_context_digest character varying(71) NOT NULL,
    operation_id uuid NOT NULL,
    project_id uuid NOT NULL,
    resource_id uuid NOT NULL,
    operation_generation integer NOT NULL,
    status character varying(16) NOT NULL,
    response_json json,
    setup_run_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    committed_at timestamp with time zone,
    activation_facts_json json,
    activation_authority_json json,
    CONSTRAINT ck_guide_mutation_idempotency_records_activation_evidence_shape CHECK (((((action_id)::text = 'project.guide.activate'::text) AND (activation_facts_json IS NOT NULL) AND (activation_authority_json IS NOT NULL)) OR (((action_id)::text <> 'project.guide.activate'::text) AND (activation_facts_json IS NULL) AND (activation_authority_json IS NULL)))),
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_6506 CHECK ((operation_generation > 0)),
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_9402 CHECK (((((status)::text = 'pending'::text) AND (response_json IS NULL) AND (committed_at IS NULL) AND (setup_run_id IS NULL)) OR (((status)::text = 'committed'::text) AND (response_json IS NOT NULL) AND (committed_at IS NOT NULL)))),
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_action CHECK (((action_id)::text = ANY ((ARRAY['project.guide.create'::character varying, 'project.guide.update'::character varying, 'project.guide_source_snapshot.create'::character varying, 'project.guide.activate'::character varying])::text[]))),
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_b397 CHECK (((resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_e32d CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_mutation_idempotency_records_ck_guide_mutation_status CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('committed'::character varying)::text])))
);
CREATE TABLE public.guide_source_artifact_bindings (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_item_id uuid NOT NULL,
    project_setup_run_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    content_id uuid NOT NULL,
    verified_replica_id uuid NOT NULL,
    logical_role character varying(100) NOT NULL,
    supersedes_binding_id uuid,
    created_by_service character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_artifact_bindings_ck_guide_bindings_gen_b5fe CHECK ((setup_generation > 0)),
    CONSTRAINT ck_guide_source_artifact_bindings_ck_guide_bindings_role CHECK (((logical_role)::text = 'guide_source_original'::text))
);
CREATE TABLE public.guide_source_artifact_incidents (
    id uuid NOT NULL,
    binding_id uuid NOT NULL,
    content_id uuid NOT NULL,
    verified_replica_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    code character varying(40) NOT NULL,
    observed_sha256 character varying(71),
    observed_byte_count bigint,
    bounded_facts json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_artifact_incidents_ck_guide_incidents_code CHECK (((code)::text = ANY (ARRAY[('missing'::character varying)::text, ('changed'::character varying)::text, ('truncated'::character varying)::text, ('unavailable'::character varying)::text, ('stale'::character varying)::text, ('conflict'::character varying)::text]))),
    CONSTRAINT ck_guide_source_artifact_incidents_ck_guide_source_arti_621b CHECK (((observed_sha256 IS NULL) OR ((observed_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_guide_source_artifact_incidents_ck_guide_source_arti_92fa CHECK (((observed_byte_count IS NULL) OR (observed_byte_count >= 0)))
);
CREATE TABLE public.guide_source_artifact_ingests (
    id uuid NOT NULL,
    source_item_id uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    sha256 character varying(71) NOT NULL,
    byte_count bigint NOT NULL,
    media_type character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_artifact_ingests_ck_guide_source_artifa_2958 CHECK ((byte_count >= 0)),
    CONSTRAINT ck_guide_source_artifact_ingests_ck_guide_source_artifa_64cb CHECK (((sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text))
);
CREATE TABLE public.guide_source_extracted_contents (
    id uuid NOT NULL,
    content_id uuid NOT NULL,
    detected_format character varying(40) NOT NULL,
    extractor_name character varying(100) NOT NULL,
    extractor_version character varying(40) NOT NULL,
    policy_version character varying(80) NOT NULL,
    source_sha256 character varying(71) NOT NULL,
    source_byte_count bigint NOT NULL,
    status character varying(40) NOT NULL,
    output_sha256 character varying(71) NOT NULL,
    canonical_output text NOT NULL,
    omission_facts json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_extracted_contents_ck_guide_extracted_c_1b91 CHECK (((output_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_source_extracted_contents_ck_guide_extracted_c_54b5 CHECK ((octet_length(canonical_output) <= 4194304)),
    CONSTRAINT ck_guide_source_extracted_contents_ck_guide_extracted_c_988f CHECK (((source_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_source_extracted_contents_ck_guide_extracted_c_a759 CHECK (((status)::text = 'extracted'::text)),
    CONSTRAINT ck_guide_source_extracted_contents_ck_guide_extracted_c_fb79 CHECK ((source_byte_count >= 0))
);
CREATE TABLE public.guide_source_extraction_attempts (
    id uuid NOT NULL,
    binding_id uuid NOT NULL,
    content_id uuid NOT NULL,
    classification_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    detected_format character varying(40) NOT NULL,
    extractor_name character varying(100) NOT NULL,
    extractor_version character varying(40) NOT NULL,
    policy_version character varying(80) NOT NULL,
    attempt_number bigint NOT NULL,
    status character varying(40) NOT NULL,
    error_code character varying(80),
    bounded_facts json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_extraction_attempts_ck_guide_extraction_3927 CHECK ((attempt_number > 0)),
    CONSTRAINT ck_guide_source_extraction_attempts_ck_guide_extraction_940d CHECK ((((status)::text = 'extracted'::text) = (error_code IS NULL))),
    CONSTRAINT ck_guide_source_extraction_attempts_ck_guide_extraction_ff6d CHECK (((status)::text = ANY (ARRAY[('extracted'::character varying)::text, ('unsupported'::character varying)::text, ('ambiguous'::character varying)::text, ('malformed'::character varying)::text, ('limit_exceeded'::character varying)::text, ('parser_failure'::character varying)::text, ('cancelled'::character varying)::text, ('artifact_incident'::character varying)::text])))
);
CREATE TABLE public.guide_source_extraction_retry_budgets (
    binding_id uuid NOT NULL,
    content_id uuid NOT NULL,
    classification_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    policy_version character varying(80) NOT NULL,
    claimed_slots integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_extraction_retry_budgets_ck_guide_extra_99c3 CHECK (((claimed_slots >= 1) AND (claimed_slots <= 2)))
);
CREATE TABLE public.guide_source_extraction_usages (
    id uuid NOT NULL,
    extracted_content_id uuid NOT NULL,
    extraction_attempt_id uuid NOT NULL,
    attempt_status character varying(40) NOT NULL,
    binding_id uuid NOT NULL,
    content_id uuid NOT NULL,
    source_item_id uuid NOT NULL,
    project_setup_run_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_extraction_usages_ck_guide_extraction_u_a2fd CHECK (((attempt_status)::text = 'extracted'::text))
);
CREATE TABLE public.guide_source_format_classifications (
    id uuid NOT NULL,
    binding_id uuid NOT NULL,
    content_id uuid NOT NULL,
    verified_replica_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    sha256 character varying(71) NOT NULL,
    byte_count bigint NOT NULL,
    media_type character varying(255) NOT NULL,
    detected_format character varying(40) NOT NULL,
    status character varying(40) NOT NULL,
    detector_name character varying(100) NOT NULL,
    detector_version character varying(40) NOT NULL,
    classification_facts json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_guide_source_format_classifications_ck_guide_classif_8737 CHECK (((status)::text = ANY (ARRAY[('classified'::character varying)::text, ('unsupported'::character varying)::text, ('ambiguous'::character varying)::text, ('malformed'::character varying)::text, ('limit_exceeded'::character varying)::text]))),
    CONSTRAINT ck_guide_source_format_classifications_ck_guide_source__0dd2 CHECK (((sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_source_format_classifications_ck_guide_source__7235 CHECK ((byte_count >= 0))
);
CREATE TABLE public.guide_source_snapshot_items (
    id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    item_order integer NOT NULL,
    source_kind character varying(50) NOT NULL,
    source_label text NOT NULL,
    ingestion_adapter character varying(100) NOT NULL,
    media_type character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.guide_source_snapshots (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    manifest_schema_version character varying(50) NOT NULL,
    manifest_json json NOT NULL,
    bundle_hash character varying(71) NOT NULL,
    captured_by character varying(100) NOT NULL,
    captured_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by_actor_profile_id uuid,
    created_via_identity_link_id uuid,
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_scope_project_id uuid,
    creation_action_id character varying(160),
    authorization_decision_event_id uuid,
    creation_generation integer,
    CONSTRAINT ck_guide_source_snapshots_source_snapshot_creation_auth_2f3e CHECK ((((creation_generation IS NULL) AND (created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (creation_scope_type IS NULL) AND (creation_scope_project_id IS NULL) AND (creation_action_id IS NULL) AND (authorization_decision_event_id IS NULL)) OR ((creation_generation > 0) AND (created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND ((creation_scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text])) AND ((((creation_scope_type)::text = 'system'::text) AND (creation_scope_project_id IS NULL)) OR (((creation_scope_type)::text = 'project'::text) AND ((creation_scope_project_id)::text = (project_id)::text))) AND ((creation_action_id)::text = 'project.guide_source_snapshot.create'::text) AND (authorization_decision_event_id IS NOT NULL))))
);
CREATE TABLE public.guide_sufficiency_mutation_idempotency_records (
    id uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    action_id character varying(160) NOT NULL,
    idempotency_key uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    resource_context_digest character varying(71) NOT NULL,
    operation_id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    report_id uuid,
    setup_run_id uuid,
    setup_generation bigint NOT NULL,
    status character varying(16) NOT NULL,
    response_json json,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_ck_su_1033 CHECK ((setup_generation > 0)),
    CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_ck_su_177a CHECK ((((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_ck_su_6651 CHECK (((action_id)::text = ANY (ARRAY[('project.guide_sufficiency_report.create'::character varying)::text, ('project.guide_sufficiency.run'::character varying)::text, ('project.guide_sufficiency.warnings.acknowledge'::character varying)::text]))),
    CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_ck_su_87dd CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('committed'::character varying)::text]))),
    CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_ck_su_e7f6 CHECK (((((status)::text = 'pending'::text) AND (response_json IS NULL) AND (committed_at IS NULL)) OR (((status)::text = 'committed'::text) AND (response_json IS NOT NULL) AND (committed_at IS NOT NULL) AND ((((action_id)::text = 'project.guide_sufficiency.run'::text) AND ((setup_run_id IS NOT NULL) OR (report_id IS NOT NULL))) OR (((action_id)::text <> 'project.guide_sufficiency.run'::text) AND (report_id IS NOT NULL))))))
);
CREATE TABLE public.guide_sufficiency_report_source_usages (
    id uuid NOT NULL,
    report_id uuid NOT NULL,
    item_order integer NOT NULL,
    source_item_id uuid NOT NULL,
    binding_id uuid NOT NULL,
    content_id uuid NOT NULL,
    extraction_usage_id uuid NOT NULL,
    extraction_attempt_id uuid NOT NULL,
    extracted_content_id uuid NOT NULL,
    project_setup_run_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    canonical_output_sha256 character varying(71) NOT NULL,
    CONSTRAINT ck_guide_sufficiency_report_source_usages_ck_sufficienc_2983 CHECK ((setup_generation > 0)),
    CONSTRAINT ck_guide_sufficiency_report_source_usages_ck_sufficienc_8148 CHECK (((canonical_output_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_guide_sufficiency_report_source_usages_ck_sufficienc_eb12 CHECK ((item_order >= 0))
);
CREATE TABLE public.guide_sufficiency_reports (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    status character varying(30) NOT NULL,
    findings json NOT NULL,
    summary text,
    agent_name character varying(100),
    agent_version character varying(50),
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    warnings_acknowledged_by_role character varying(50),
    warnings_acknowledged_by_actor character varying(100),
    warnings_acknowledged_at timestamp with time zone,
    acknowledgement_note text,
    project_setup_run_id uuid,
    setup_generation bigint,
    agent_material_sha256 character varying(71),
    agent_material_byte_count bigint,
    created_by_actor_profile_id uuid,
    created_via_identity_link_id uuid,
    created_by_admin_role_grant_id uuid,
    created_by_service_identity character varying(160),
    creation_scope_type character varying(16),
    creation_scope_project_id uuid,
    creation_action_id character varying(160),
    authorization_decision_event_id uuid,
    warnings_acknowledged_by_actor_profile_id uuid,
    warnings_acknowledged_via_identity_link_id uuid,
    warnings_acknowledged_by_admin_role_grant_id uuid,
    warning_acknowledgement_scope_type character varying(16),
    warning_acknowledgement_scope_project_id uuid,
    warning_acknowledgement_action_id character varying(160),
    warning_acknowledgement_decision_event_id uuid,
    CONSTRAINT ck_guide_sufficiency_ack_authority_shape CHECK ((((warnings_acknowledged_by_actor_profile_id IS NULL) AND (warnings_acknowledged_via_identity_link_id IS NULL) AND (warnings_acknowledged_by_admin_role_grant_id IS NULL) AND (warning_acknowledgement_scope_type IS NULL) AND (warning_acknowledgement_scope_project_id IS NULL) AND (warning_acknowledgement_action_id IS NULL) AND (warning_acknowledgement_decision_event_id IS NULL)) OR ((warnings_acknowledged_by_actor_profile_id IS NOT NULL) AND (warnings_acknowledged_via_identity_link_id IS NOT NULL) AND (warnings_acknowledged_by_admin_role_grant_id IS NOT NULL) AND ((warning_acknowledgement_scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text])) AND (warning_acknowledgement_scope_project_id IS NOT NULL) AND ((warning_acknowledgement_action_id)::text = 'project.guide_sufficiency.warnings.acknowledge'::text) AND (warning_acknowledgement_decision_event_id IS NOT NULL)))),
    CONSTRAINT ck_guide_sufficiency_creation_authority_shape CHECK ((((created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (created_by_service_identity IS NULL) AND (creation_scope_type IS NULL) AND (creation_scope_project_id IS NULL) AND (creation_action_id IS NULL) AND (authorization_decision_event_id IS NULL)) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (creation_scope_project_id IS NOT NULL) AND ((creation_action_id)::text = ANY (ARRAY[('project.guide_sufficiency_report.create'::character varying)::text, ('project.guide_sufficiency.run'::character varying)::text])) AND (authorization_decision_event_id IS NOT NULL) AND (((created_by_admin_role_grant_id IS NOT NULL) AND (created_by_service_identity IS NULL) AND ((creation_scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text]))) OR ((created_by_admin_role_grant_id IS NULL) AND ((created_by_service_identity)::text = 'workstream.project.setup'::text) AND ((creation_scope_type)::text = 'service'::text) AND ((creation_action_id)::text = 'project.guide_sufficiency.run'::text) AND (project_setup_run_id IS NOT NULL) AND (setup_generation IS NOT NULL) AND (agent_material_sha256 IS NOT NULL) AND (agent_material_byte_count IS NOT NULL)))))),
    CONSTRAINT ck_guide_sufficiency_reports_ck_guide_sufficiency_repor_31bb CHECK (((agent_material_byte_count IS NULL) OR (agent_material_byte_count >= 0))),
    CONSTRAINT ck_guide_sufficiency_reports_ck_guide_sufficiency_repor_3e43 CHECK (((setup_generation IS NULL) OR (setup_generation > 0))),
    CONSTRAINT ck_guide_sufficiency_reports_ck_guide_sufficiency_repor_4640 CHECK ((((project_setup_run_id IS NULL) AND (setup_generation IS NULL) AND (agent_material_sha256 IS NULL) AND (agent_material_byte_count IS NULL)) OR ((project_setup_run_id IS NOT NULL) AND (setup_generation IS NOT NULL) AND (agent_material_sha256 IS NOT NULL) AND (agent_material_byte_count IS NOT NULL)))),
    CONSTRAINT ck_guide_sufficiency_reports_ck_guide_sufficiency_repor_841c CHECK (((status)::text = ANY (ARRAY[('passed'::character varying)::text, ('blocked'::character varying)::text, ('passed_with_warnings'::character varying)::text]))),
    CONSTRAINT ck_guide_sufficiency_reports_ck_guide_sufficiency_repor_b3ec CHECK (((agent_material_sha256 IS NULL) OR ((agent_material_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)))
);
CREATE TABLE public.iso_4217_currency_codes (
    code character varying(3) NOT NULL,
    CONSTRAINT ck_iso_4217_currency_codes_code CHECK (((code)::text ~ '^[A-Z]{3}$'::text))
);
CREATE TABLE public.legacy_actor_identities (
    actor_id character varying(100) NOT NULL,
    external_subject character varying(200) NOT NULL,
    external_issuer character varying(200) NOT NULL,
    display_name character varying(200),
    email character varying(320),
    last_seen_roles json NOT NULL,
    last_claim_snapshot json NOT NULL,
    auth_source character varying(50) NOT NULL,
    is_dev_auth boolean NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.legacy_workflow_eligibility (
    id uuid NOT NULL,
    actor_id character varying(100) NOT NULL,
    profile_type character varying(50) NOT NULL,
    status character varying(30) NOT NULL,
    skill_tags json NOT NULL,
    scope_type character varying(50) NOT NULL,
    scope_id character varying(100) NOT NULL,
    profile_metadata json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_legacy_workflow_eligibility_profile_type CHECK (((profile_type)::text = ANY (ARRAY[('worker'::character varying)::text, ('reviewer'::character varying)::text, ('admin'::character varying)::text, ('project_manager'::character varying)::text, ('project_owner'::character varying)::text]))),
    CONSTRAINT ck_legacy_workflow_eligibility_status CHECK (((status)::text = ANY (ARRAY[('observed'::character varying)::text, ('active'::character varying)::text, ('disabled'::character varying)::text])))
);
CREATE TABLE public.outbox_events (
    event_id uuid NOT NULL,
    event_type character varying(128) NOT NULL,
    event_version smallint NOT NULL,
    producer character varying(32) DEFAULT 'workstream'::character varying NOT NULL,
    aggregate_type character varying(64) NOT NULL,
    aggregate_id uuid NOT NULL,
    project_id uuid NOT NULL,
    correlation_id character varying(200) NOT NULL,
    causation_event_id uuid,
    idempotency_key character varying(200) NOT NULL,
    payload jsonb NOT NULL,
    payload_digest character varying(71) NOT NULL,
    occurred_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    delivery_state character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT statement_timestamp(),
    claim_owner character varying(120),
    claim_generation bigint DEFAULT '0'::bigint NOT NULL,
    claimed_at timestamp with time zone,
    claim_expires_at timestamp with time zone,
    last_attempt_at timestamp with time zone,
    last_error_code character varying(80),
    finalized_at timestamp with time zone,
    archived_at timestamp with time zone,
    CONSTRAINT ck_outbox_events_aggregate_type CHECK (((aggregate_type)::text ~ '^[a-z][a-z0-9_]{0,63}$'::text)),
    CONSTRAINT ck_outbox_events_claim_owner CHECK (((claim_owner IS NULL) OR ((claim_owner)::text ~ '^[A-Za-z0-9._:-]{1,120}$'::text))),
    CONSTRAINT ck_outbox_events_correlation_id CHECK (((correlation_id)::text ~ '^[A-Za-z0-9._:-]{1,200}$'::text)),
    CONSTRAINT ck_outbox_events_delivery_counters CHECK (((attempt_count >= 0) AND (claim_generation >= 0) AND (attempt_count = claim_generation))),
    CONSTRAINT ck_outbox_events_delivery_state CHECK (((delivery_state)::text = ANY (ARRAY[('pending'::character varying)::text, ('claimed'::character varying)::text, ('retryable'::character varying)::text, ('acknowledged'::character varying)::text, ('dead_letter'::character varying)::text, ('cancelled'::character varying)::text]))),
    CONSTRAINT ck_outbox_events_delivery_state_shape CHECK (((((delivery_state)::text = 'pending'::text) AND (attempt_count = 0) AND (next_attempt_at IS NOT NULL) AND (claim_owner IS NULL) AND (claimed_at IS NULL) AND (claim_expires_at IS NULL) AND (last_attempt_at IS NULL) AND (last_error_code IS NULL) AND (finalized_at IS NULL) AND (archived_at IS NULL)) OR (((delivery_state)::text = 'claimed'::text) AND (attempt_count > 0) AND (next_attempt_at IS NULL) AND (claim_owner IS NOT NULL) AND (claimed_at IS NOT NULL) AND (claim_expires_at IS NOT NULL) AND (last_attempt_at = claimed_at) AND (finalized_at IS NULL) AND (archived_at IS NULL)) OR (((delivery_state)::text = 'retryable'::text) AND (attempt_count > 0) AND (next_attempt_at IS NOT NULL) AND (claim_owner IS NULL) AND (claimed_at IS NULL) AND (claim_expires_at IS NULL) AND (last_attempt_at IS NOT NULL) AND (last_error_code IS NOT NULL) AND (finalized_at IS NULL) AND (archived_at IS NULL)) OR (((delivery_state)::text = 'acknowledged'::text) AND (attempt_count > 0) AND (next_attempt_at IS NULL) AND (claim_owner IS NULL) AND (claimed_at IS NULL) AND (claim_expires_at IS NULL) AND (last_attempt_at IS NOT NULL) AND (finalized_at IS NOT NULL)) OR (((delivery_state)::text = 'dead_letter'::text) AND (attempt_count > 0) AND (next_attempt_at IS NULL) AND (claim_owner IS NULL) AND (claimed_at IS NULL) AND (claim_expires_at IS NULL) AND (last_attempt_at IS NOT NULL) AND (last_error_code IS NOT NULL) AND (finalized_at IS NOT NULL)) OR (((delivery_state)::text = 'cancelled'::text) AND (next_attempt_at IS NULL) AND (claim_owner IS NULL) AND (claimed_at IS NULL) AND (claim_expires_at IS NULL) AND (finalized_at IS NOT NULL) AND (attempt_count = 0) AND (last_attempt_at IS NULL) AND (last_error_code IS NULL)))),
    CONSTRAINT ck_outbox_events_delivery_timestamps CHECK ((((next_attempt_at IS NULL) OR (next_attempt_at >= occurred_at)) AND ((claimed_at IS NULL) OR (claimed_at >= occurred_at)) AND ((last_attempt_at IS NULL) OR (last_attempt_at >= occurred_at)) AND ((claim_expires_at IS NULL) OR (claim_expires_at > claimed_at)) AND ((finalized_at IS NULL) OR (finalized_at >= occurred_at)) AND ((finalized_at IS NULL) OR (last_attempt_at IS NULL) OR (finalized_at >= last_attempt_at)) AND ((archived_at IS NULL) OR (archived_at >= finalized_at)))),
    CONSTRAINT ck_outbox_events_error_code CHECK (((last_error_code IS NULL) OR ((last_error_code)::text ~ '^[A-Z][A-Z0-9_]{0,79}$'::text))),
    CONSTRAINT ck_outbox_events_event_type CHECK (((event_type)::text ~ '^[A-Za-z][A-Za-z0-9._:-]{0,127}$'::text)),
    CONSTRAINT ck_outbox_events_event_version CHECK (((event_version >= 1) AND (event_version <= 32767))),
    CONSTRAINT ck_outbox_events_idempotency_key CHECK (((idempotency_key)::text ~ '^[A-Za-z0-9._:-]{1,200}$'::text)),
    CONSTRAINT ck_outbox_events_payload_digest CHECK (((payload_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_outbox_events_payload_shape CHECK (((jsonb_typeof(payload) = 'object'::text) AND (octet_length((payload)::text) <= 262144))),
    CONSTRAINT ck_outbox_events_producer CHECK (((producer)::text = 'workstream'::text)),
    CONSTRAINT ck_outbox_events_project_id CHECK (((project_id)::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text))
);
CREATE TABLE public.payment_policies (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    base_amount numeric(12,2),
    currency character varying(20),
    payout_type character varying(50),
    revision_payment_rule text,
    rejection_payment_rule text,
    accepted_payment_rule text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.policy_mutation_idempotency_records (
    id uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    action_id character varying(160) NOT NULL,
    idempotency_key uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    policy_hash character varying(71) NOT NULL,
    resource_context_digest character varying(71) NOT NULL,
    operation_id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    policy_id uuid NOT NULL,
    policy_generation integer NOT NULL,
    status character varying(16) NOT NULL,
    response_json json,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_policy_mutation_idempotency_records_ck_policy_mutati_26aa CHECK (((((status)::text = 'pending'::text) AND (response_json IS NULL) AND (committed_at IS NULL)) OR (((status)::text = 'committed'::text) AND (response_json IS NOT NULL) AND (committed_at IS NOT NULL)))),
    CONSTRAINT ck_policy_mutation_idempotency_records_ck_policy_mutati_595e CHECK ((((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_policy_mutation_idempotency_records_ck_policy_mutati_7f7f CHECK (((action_id)::text = ANY (ARRAY[('project.review_policy.update'::character varying)::text, ('project.revision_policy.update'::character varying)::text]))),
    CONSTRAINT ck_policy_mutation_idempotency_records_ck_policy_mutati_8b22 CHECK ((policy_generation > 0)),
    CONSTRAINT ck_policy_mutation_idempotency_records_ck_policy_mutati_dc05 CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('committed'::character varying)::text])))
);
CREATE TABLE public.pre_submit_checker_policies (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    effective_policy_id uuid NOT NULL,
    effective_policy_hash character varying(71) NOT NULL,
    lifecycle_status character varying(30) NOT NULL,
    compiler_version character varying(50),
    compiled_bundle json,
    compiled_bundle_hash character varying(71),
    checker_names json NOT NULL,
    checker_configs json NOT NULL,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    supersedes_pre_submit_checker_policy_id uuid,
    superseded_at timestamp with time zone,
    created_by_actor_profile_id uuid,
    created_via_identity_link_id uuid,
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_scope_project_id uuid,
    creation_action_id character varying(160),
    creation_decision_event_id uuid,
    CONSTRAINT ck_pre_submit_checker_policies_ck_pre_submit_checker_po_5010 CHECK ((((lifecycle_status)::text <> 'compiled'::text) OR ((compiler_version IS NOT NULL) AND (compiled_bundle IS NOT NULL) AND (compiled_bundle_hash IS NOT NULL) AND ((compiled_bundle_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text)))),
    CONSTRAINT ck_pre_submit_checker_policies_ck_pre_submit_checker_po_a935 CHECK (((lifecycle_status)::text = ANY (ARRAY[('pending_compilation'::character varying)::text, ('compiled'::character varying)::text, ('superseded'::character varying)::text]))),
    CONSTRAINT ck_pre_submit_checker_policies_ck_pre_submit_policy_aut_90fc CHECK ((((created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (creation_scope_type IS NULL) AND (creation_scope_project_id IS NULL) AND (creation_action_id IS NULL) AND (creation_decision_event_id IS NULL)) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND (creation_scope_type IS NOT NULL) AND (creation_action_id IS NOT NULL) AND ((creation_scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text])) AND (creation_scope_project_id IS NOT NULL) AND ((creation_scope_project_id)::text = (project_id)::text) AND ((creation_action_id)::text = 'project.submission_artifact_policy.approve'::text) AND (creation_decision_event_id IS NOT NULL))))
);
CREATE TABLE public.pre_submit_evidence_results (
    id uuid NOT NULL,
    evidence_set_id uuid NOT NULL,
    result_order integer NOT NULL,
    schema_version character varying(80) NOT NULL,
    dispatch_authority character varying(160) NOT NULL,
    definition_id character varying(160) NOT NULL,
    definition_version character varying(40) NOT NULL,
    public_name character varying(160) NOT NULL,
    source character varying(160) NOT NULL,
    phase character varying(40) NOT NULL,
    classification character varying(40) NOT NULL,
    severity character varying(16) NOT NULL,
    status character varying(40) NOT NULL,
    failure_code character varying(160),
    message_code character varying(160) NOT NULL,
    effective_plan_sha256 character varying(71) NOT NULL,
    rule_instance_id character varying(71),
    locked_policy_sha256 character varying(71) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    checker_order integer,
    metadata_json json,
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_cla_b0de CHECK (((classification)::text = ANY (ARRAY[('mandatory_security'::character varying)::text, ('mandatory_integrity'::character varying)::text, ('mandatory_accountability'::character varying)::text, ('advisory'::character varying)::text]))),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_cla_f04e CHECK (((((classification)::text = 'advisory'::text) AND ((severity)::text = 'warning'::text)) OR (((classification)::text <> 'advisory'::text) AND ((severity)::text = 'blocking'::text)))),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_order CHECK ((result_order >= 0)),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_phase CHECK (((phase)::text = ANY (ARRAY[('custody'::character varying)::text, ('identity'::character varying)::text, ('materialization'::character varying)::text, ('default_policy'::character varying)::text, ('project_policy'::character varying)::text]))),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_plan_sha256 CHECK (((effective_plan_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_pol_cef4 CHECK (((locked_policy_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_rul_321f CHECK (((((phase)::text = 'project_policy'::text) AND (rule_instance_id IS NOT NULL) AND ((rule_instance_id)::text ~ '^sha256:[0-9a-f]{64}$'::text)) OR (((phase)::text <> 'project_policy'::text) AND (rule_instance_id IS NULL)))),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_severity CHECK (((severity)::text = ANY (ARRAY[('blocking'::character varying)::text, ('warning'::character varying)::text]))),
    CONSTRAINT ck_pre_submit_evidence_results_ck_pre_submit_result_status CHECK (((status)::text = ANY (ARRAY[('passed'::character varying)::text, ('warning'::character varying)::text, ('advisory_disabled'::character varying)::text, ('dependency_not_run'::character varying)::text, ('failed'::character varying)::text]))),
    CONSTRAINT ck_pre_submit_evidence_results_result_failure_shape CHECK (((((status)::text = 'failed'::text) AND (failure_code IS NOT NULL)) OR (((status)::text <> 'failed'::text) AND (failure_code IS NULL))))
);
CREATE TABLE public.pre_submit_evidence_sets (
    id uuid NOT NULL,
    operation_identity character varying(71) NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    project_id uuid NOT NULL,
    task_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    predecessor_submission_id uuid,
    predecessor_submission_version integer,
    prepared_generation_id uuid NOT NULL,
    archive_sha256 character varying(71) NOT NULL,
    archive_byte_count bigint NOT NULL,
    semantic_manifest_id uuid NOT NULL,
    semantic_manifest_sha256 character varying(71) NOT NULL,
    guide_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_snapshot_sha256 character varying(71) NOT NULL,
    locked_guide_sha256 character varying(71) NOT NULL,
    effective_policy_id uuid NOT NULL,
    locked_artifact_policy_sha256 character varying(71) NOT NULL,
    pre_submit_policy_id uuid NOT NULL,
    locked_checker_policy_sha256 character varying(71) NOT NULL,
    effective_plan_sha256 character varying(71) NOT NULL,
    catalogue_id character varying(160) NOT NULL,
    catalogue_version character varying(40) NOT NULL,
    catalogue_manifest_sha256 character varying(71) NOT NULL,
    storage_scheme character varying(16) NOT NULL,
    terminal_status character varying(16) NOT NULL,
    eligible boolean NOT NULL,
    result_count integer NOT NULL,
    result_manifest_sha256 character varying(71) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    locked_policy_context_hash character varying(71) NOT NULL,
    attempt_id uuid,
    attempt_request_digest character varying(71),
    packet_sha256 character varying(71),
    CONSTRAINT ck_pre_submit_evidence_packet_sha256 CHECK (((packet_sha256 IS NULL) OR ((packet_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_arch_8e95 CHECK (((archive_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_archive_size CHECK ((archive_byte_count >= 0)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_arti_16f8 CHECK (((locked_artifact_policy_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_cata_ffcb CHECK (((catalogue_manifest_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_chec_765d CHECK (((locked_checker_policy_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_guide_sha256 CHECK (((locked_guide_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_mani_7268 CHECK (((semantic_manifest_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_oper_f617 CHECK (((operation_identity)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_plan_sha256 CHECK (((effective_plan_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_pred_bd87 CHECK ((((predecessor_submission_id IS NULL) AND (predecessor_submission_version IS NULL)) OR ((predecessor_submission_id IS NOT NULL) AND (predecessor_submission_version IS NOT NULL)))),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_resu_0b46 CHECK (((result_manifest_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_result_count CHECK ((result_count > 0)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_sour_982b CHECK (((source_snapshot_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_stat_1ae6 CHECK (((((terminal_status)::text = 'passed'::text) AND eligible) OR (((terminal_status)::text = 'blocked'::text) AND (NOT eligible)))),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_stor_022c CHECK (((storage_scheme)::text = ANY (ARRAY[('local'::character varying)::text, ('s3'::character varying)::text]))),
    CONSTRAINT ck_pre_submit_evidence_sets_ck_pre_submit_evidence_term_a512 CHECK (((terminal_status)::text = ANY (ARRAY[('passed'::character varying)::text, ('blocked'::character varying)::text]))),
    CONSTRAINT ck_pre_submit_evidence_sets_policy_context_sha256 CHECK (((locked_policy_context_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text))
);
CREATE TABLE public.pre_submit_execution_attempts (
    id uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    task_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    prepared_generation_id uuid NOT NULL,
    claim_nonce uuid NOT NULL,
    request_json json NOT NULL,
    request_digest character varying(71) NOT NULL,
    status character varying(16) NOT NULL,
    evidence_set_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_pre_submit_attempt_digest CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pre_submit_attempt_status CHECK (((((status)::text = 'reserved'::text) AND (evidence_set_id IS NULL)) OR (((status)::text = 'completed'::text) AND (evidence_set_id IS NOT NULL))))
);
CREATE TABLE public.project_compensation_adapter_bindings (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    instrument_type character varying(32) NOT NULL,
    adapter_actor_id uuid NOT NULL,
    route_key character varying(120) NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    binding_lifecycle_version integer DEFAULT 1 NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    suspended_by uuid,
    suspended_at timestamp with time zone,
    retired_by uuid,
    retired_at timestamp with time zone,
    resumed_by uuid,
    resumed_at timestamp with time zone,
    CONSTRAINT ck_project_compensation_adapter_bindings_ck_project_com_1870 CHECK ((binding_lifecycle_version > 0)),
    CONSTRAINT ck_project_compensation_adapter_bindings_ck_project_com_3372 CHECK (((instrument_type)::text = ANY (ARRAY[('money'::character varying)::text, ('project_points'::character varying)::text]))),
    CONSTRAINT ck_project_compensation_adapter_bindings_ck_project_com_6958 CHECK (((route_key)::text ~ '^[A-Za-z][A-Za-z0-9._:-]{0,119}$'::text)),
    CONSTRAINT ck_project_compensation_adapter_bindings_ck_project_com_f32d CHECK (((route_key)::text !~~ '%..%'::text)),
    CONSTRAINT ck_project_compensation_adapter_bindings_lifecycle_shape CHECK (((((status)::text = 'active'::text) AND (suspended_by IS NULL) AND (suspended_at IS NULL) AND (((binding_lifecycle_version = 1) AND (resumed_by IS NULL) AND (resumed_at IS NULL)) OR ((binding_lifecycle_version > 1) AND (resumed_by IS NOT NULL) AND (resumed_at IS NOT NULL))) AND (retired_by IS NULL) AND (retired_at IS NULL)) OR (((status)::text = 'suspended'::text) AND (binding_lifecycle_version > 1) AND (suspended_by IS NOT NULL) AND (suspended_at IS NOT NULL) AND (resumed_by IS NULL) AND (resumed_at IS NULL) AND (retired_by IS NULL) AND (retired_at IS NULL)))),
    CONSTRAINT ck_project_compensation_adapter_bindings_lifecycle_timestamps CHECK ((((suspended_at IS NULL) OR (suspended_at >= created_at)) AND ((resumed_at IS NULL) OR (resumed_at >= created_at)) AND ((retired_at IS NULL) OR (retired_at >= created_at)) AND ((retired_at IS NULL) OR (suspended_at IS NULL) OR (retired_at >= suspended_at)))),
    CONSTRAINT ck_project_compensation_adapter_bindings_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'suspended'::character varying])::text[])))
);
CREATE TABLE public.project_compensation_units (
    project_id uuid NOT NULL,
    instrument_type character varying(32) NOT NULL,
    unit_code character varying(32) NOT NULL,
    iso_currency_code character varying(3),
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    retired_by uuid,
    retired_at timestamp with time zone,
    CONSTRAINT ck_project_compensation_units_instrument_type CHECK (((instrument_type)::text = ANY (ARRAY[('money'::character varying)::text, ('project_points'::character varying)::text]))),
    CONSTRAINT ck_project_compensation_units_lifecycle_shape CHECK (((((status)::text = 'active'::text) AND (retired_by IS NULL) AND (retired_at IS NULL)) OR (((status)::text = 'retired'::text) AND (retired_by IS NOT NULL) AND (retired_at IS NOT NULL)))),
    CONSTRAINT ck_project_compensation_units_retirement_time CHECK (((retired_at IS NULL) OR (retired_at >= created_at))),
    CONSTRAINT ck_project_compensation_units_status CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('retired'::character varying)::text]))),
    CONSTRAINT ck_project_compensation_units_unit_identity CHECK (((((instrument_type)::text = 'money'::text) AND (iso_currency_code IS NOT NULL) AND ((unit_code)::text = (iso_currency_code)::text)) OR (((instrument_type)::text = 'project_points'::text) AND (iso_currency_code IS NULL) AND ((unit_code)::text ~ '^[A-Za-z][A-Za-z0-9._:-]{0,31}$'::text))))
);
CREATE TABLE public.project_create_idempotency_records (
    id uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    action_id character varying(160) NOT NULL,
    idempotency_key uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    operation_id uuid NOT NULL,
    project_id uuid NOT NULL,
    operation_generation integer NOT NULL,
    status character varying(16) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_project_create_idempotency_records_ck_project_create_0a41 CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_project_create_idempotency_records_ck_project_create_100d CHECK ((operation_generation = 1)),
    CONSTRAINT ck_project_create_idempotency_records_ck_project_create_3aa0 CHECK (((((status)::text = 'pending'::text) AND (committed_at IS NULL)) OR (((status)::text = 'committed'::text) AND (committed_at IS NOT NULL)))),
    CONSTRAINT ck_project_create_idempotency_records_ck_project_create_action CHECK (((action_id)::text = 'project.create'::text)),
    CONSTRAINT ck_project_create_idempotency_records_ck_project_create_status CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('committed'::character varying)::text])))
);
CREATE TABLE public.project_guide_compilations (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    setup_run_id uuid NOT NULL,
    setup_generation bigint NOT NULL,
    canonical_input_hash character varying(71) NOT NULL,
    guide_material_hash character varying(71) NOT NULL,
    pre_catalogue_manifest_hash character varying(71) NOT NULL,
    post_catalogue_manifest_hash character varying(71) NOT NULL,
    agent_identity character varying(100) NOT NULL,
    agent_version character varying(100) NOT NULL,
    instruction_version character varying(100) NOT NULL,
    canonical_result json NOT NULL,
    result_hash character varying(71) NOT NULL,
    component_hashes json NOT NULL,
    supersedes_compilation_id uuid,
    created_by_actor_profile_id uuid NOT NULL,
    created_via_identity_link_id uuid NOT NULL,
    created_by_service_identity character varying(160) NOT NULL,
    creation_action_id character varying(160) NOT NULL,
    authorization_decision_event_id uuid NOT NULL,
    authorization_resource_context_digest character varying(71) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_guide_compilations_ck_project_guide_compilat_8a51 CHECK (((setup_generation > 0) AND ((created_by_service_identity)::text = 'workstream.project.setup'::text) AND ((creation_action_id)::text = 'project.guide_compilation.execute'::text))),
    CONSTRAINT ck_project_guide_compilations_ck_project_guide_compilat_9cd9 CHECK ((((source_snapshot_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((canonical_input_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((guide_material_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((pre_catalogue_manifest_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((post_catalogue_manifest_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((result_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_project_guide_compilations_ck_project_guide_compilat_d554 CHECK (((authorization_resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_project_guide_compilations_ck_project_guide_compilat_dafe CHECK (((octet_length((canonical_result)::text) <= 4194304) AND (json_typeof(component_hashes) = 'object'::text) AND ((component_hashes)::jsonb = jsonb_build_object('sufficiency_hash', (component_hashes ->> 'sufficiency_hash'::text), 'artifact_policy_hash', (component_hashes ->> 'artifact_policy_hash'::text), 'requirement_inventory_hash', (component_hashes ->> 'requirement_inventory_hash'::text), 'pre_submit_hash', (component_hashes ->> 'pre_submit_hash'::text), 'post_submit_hash', (component_hashes ->> 'post_submit_hash'::text), 'capability_suggestions_hash', (component_hashes ->> 'capability_suggestions_hash'::text), 'setup_notes_hash', (component_hashes ->> 'setup_notes_hash'::text))) AND COALESCE(((component_hashes ->> 'sufficiency_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'artifact_policy_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'requirement_inventory_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'pre_submit_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'post_submit_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'capability_suggestions_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false) AND COALESCE(((component_hashes ->> 'setup_notes_hash'::text) ~ '^sha256:[0-9a-f]{64}$'::text), false)))
);
CREATE TABLE public.project_guide_document_accesses (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    source_item_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    attachment_allocation_id uuid NOT NULL,
    manifest_sha256 character varying(71) NOT NULL,
    sha256 character varying(71) NOT NULL,
    document_handle uuid NOT NULL,
    opened_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.project_guide_proposal_approvals (
    operation_id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    compilation_id uuid NOT NULL,
    finalization_id uuid NOT NULL,
    target_json json NOT NULL,
    target_digest character varying(71) NOT NULL,
    request_digest character varying(71) NOT NULL,
    resource_context_digest character varying(71) NOT NULL,
    output_digest character varying(71) NOT NULL,
    receipt_json json NOT NULL,
    artifact_policy_id uuid NOT NULL,
    effective_policy_id uuid NOT NULL,
    pre_submit_policy_id uuid NOT NULL,
    approved_policy_output_digest character varying(71) NOT NULL,
    effective_pre_submit_plan json NOT NULL,
    effective_pre_submit_plan_hash character varying(71) NOT NULL,
    prior_approval_operation_id uuid,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    admin_role_grant_id uuid NOT NULL,
    authorization_decision_event_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_guide_proposal_approvals_ck_proposal_approva_1f0e CHECK ((((target_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((output_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((approved_policy_output_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((effective_pre_submit_plan_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_project_guide_proposal_approvals_ck_proposal_approval_sizes CHECK (((octet_length((target_json)::text) <= 16384) AND (octet_length((receipt_json)::text) <= 32768) AND (octet_length((effective_pre_submit_plan)::text) <= 4194304)))
);
CREATE TABLE public.project_guide_proposal_corrections (
    operation_id uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    compilation_id uuid NOT NULL,
    finalization_id uuid NOT NULL,
    target_json json NOT NULL,
    target_digest character varying(71) NOT NULL,
    request_digest character varying(71) NOT NULL,
    resource_context_digest character varying(71) NOT NULL,
    resource_context_json json NOT NULL,
    output_digest character varying(71) NOT NULL,
    receipt_json json NOT NULL,
    reason text NOT NULL,
    feedback_hash character varying(71) NOT NULL,
    successor_setup_run_id uuid NOT NULL,
    successor_setup_generation bigint NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    admin_role_grant_id uuid NOT NULL,
    authorization_decision_event_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_guide_proposal_corrections_ck_proposal_corre_0b4a CHECK ((successor_setup_generation > 1)),
    CONSTRAINT ck_project_guide_proposal_corrections_ck_proposal_corre_ac60 CHECK ((((length(btrim(reason)) >= 1) AND (length(btrim(reason)) <= 4000)) AND (octet_length(reason) <= 16000) AND (octet_length((target_json)::text) <= 16384))),
    CONSTRAINT ck_project_guide_proposal_corrections_ck_proposal_corre_c4cb CHECK ((((target_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((feedback_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text)))
);
CREATE TABLE public.project_guide_runtime_allocations (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    manifest_sha256 character varying(71) NOT NULL,
    runtime_key character varying(64) NOT NULL,
    kind character varying(16) NOT NULL,
    state character varying(20) NOT NULL,
    document_handle uuid,
    provider_id character varying(128),
    parent_provider_id character varying(128),
    source_file_allocation_id uuid,
    container_allocation_id uuid,
    source_item_id uuid,
    document_version_id uuid,
    put_attempt_id uuid,
    content_id uuid,
    replica_id uuid,
    storage_namespace_id character varying(20),
    namespace_fingerprint character varying(71),
    sha256 character varying(71),
    byte_count bigint,
    media_type character varying(255),
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_project_guide_runtime_allocations_ck_guide_resource__e7c6 CHECK ((((((kind)::text = 'file'::text) AND (num_nonnulls(source_item_id, document_version_id, put_attempt_id, content_id, replica_id, storage_namespace_id, namespace_fingerprint, sha256, byte_count, media_type) = 10)) OR (((kind)::text = ANY ((ARRAY['container'::character varying, 'attachment'::character varying])::text[])) AND (num_nonnulls(source_item_id, document_version_id, put_attempt_id, content_id, replica_id, storage_namespace_id, namespace_fingerprint, sha256, byte_count, media_type) = 0))) AND ((((kind)::text = 'attachment'::text) AND (source_file_allocation_id IS NOT NULL) AND (container_allocation_id IS NOT NULL)) OR (((kind)::text = ANY ((ARRAY['container'::character varying, 'file'::character varying])::text[])) AND (source_file_allocation_id IS NULL) AND (container_allocation_id IS NULL))))),
    CONSTRAINT ck_project_guide_runtime_allocations_ck_guide_resource_identity CHECK ((((state)::text = ANY ((ARRAY['allocating'::character varying, 'uncertain'::character varying])::text[])) OR (provider_id IS NOT NULL))),
    CONSTRAINT ck_project_guide_runtime_allocations_ck_guide_resource_kind CHECK (((kind)::text = ANY ((ARRAY['container'::character varying, 'file'::character varying, 'attachment'::character varying])::text[]))),
    CONSTRAINT ck_project_guide_runtime_allocations_ck_guide_resource_scope CHECK (((((kind)::text = 'container'::text) AND (document_handle IS NULL) AND (parent_provider_id IS NULL)) OR (((kind)::text = 'file'::text) AND (document_handle IS NOT NULL) AND (parent_provider_id IS NULL)) OR (((kind)::text = 'attachment'::text) AND (document_handle IS NOT NULL) AND (parent_provider_id IS NOT NULL)))),
    CONSTRAINT ck_project_guide_runtime_allocations_ck_guide_resource_state CHECK (((state)::text = ANY ((ARRAY['allocating'::character varying, 'allocated'::character varying, 'uncertain'::character varying, 'cleanup_failed'::character varying, 'deleted'::character varying])::text[])))
);
CREATE TABLE public.project_guides (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    version character varying(50) NOT NULL,
    status character varying(30) NOT NULL,
    retained_content_markdown text,
    approved_by character varying(100),
    effective_at timestamp with time zone,
    change_summary text,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    superseded_at timestamp with time zone,
    last_mutated_by_actor_profile_id uuid,
    last_mutated_via_identity_link_id uuid,
    last_mutated_by_admin_role_grant_id uuid,
    last_mutation_scope_type character varying(16),
    last_mutation_scope_project_id uuid,
    last_mutation_action_id character varying(160),
    last_authorization_decision_event_id uuid,
    mutation_generation integer,
    selected_review_policy_id uuid,
    selected_review_policy_hash character varying(71),
    selected_revision_policy_id uuid,
    selected_revision_policy_hash character varying(71),
    selected_review_policy_generation integer,
    selected_revision_policy_generation integer,
    task_examples json,
    task_examples_hash character varying(71),
    contribution_policy_id uuid,
    contribution_policy_version_id uuid,
    activation_operation_id uuid,
    CONSTRAINT ck_project_guides_activation_binding_shape CHECK ((((contribution_policy_id IS NULL) AND (contribution_policy_version_id IS NULL) AND (activation_operation_id IS NULL)) OR ((contribution_policy_id IS NOT NULL) AND (contribution_policy_version_id IS NOT NULL) AND (activation_operation_id IS NOT NULL)))),
    CONSTRAINT ck_project_guides_active_policy_selection_required CHECK ((((status)::text <> ALL (ARRAY[('active'::character varying)::text, ('superseded'::character varying)::text])) OR ((selected_review_policy_id IS NOT NULL) AND (selected_review_policy_generation IS NOT NULL) AND (selected_review_policy_hash IS NOT NULL) AND (selected_revision_policy_id IS NOT NULL) AND (selected_revision_policy_generation IS NOT NULL) AND (selected_revision_policy_hash IS NOT NULL)))),
    CONSTRAINT ck_project_guides_guide_mutation_authority_shape CHECK ((((mutation_generation IS NULL) AND (last_mutated_by_actor_profile_id IS NULL) AND (last_mutated_via_identity_link_id IS NULL) AND (last_mutated_by_admin_role_grant_id IS NULL) AND (last_mutation_scope_type IS NULL) AND (last_mutation_scope_project_id IS NULL) AND (last_mutation_action_id IS NULL) AND (last_authorization_decision_event_id IS NULL)) OR ((mutation_generation > 0) AND (last_mutated_by_actor_profile_id IS NOT NULL) AND (last_mutated_via_identity_link_id IS NOT NULL) AND (last_mutated_by_admin_role_grant_id IS NOT NULL) AND ((last_mutation_scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text])) AND ((((last_mutation_scope_type)::text = 'system'::text) AND (last_mutation_scope_project_id IS NULL)) OR (((last_mutation_scope_type)::text = 'project'::text) AND ((last_mutation_scope_project_id)::text = (project_id)::text))) AND ((last_mutation_action_id)::text = ANY (ARRAY[('project.guide.create'::character varying)::text, ('project.guide.update'::character varying)::text, ('project.guide.activate'::character varying)::text, ('project.guide_source_snapshot.create'::character varying)::text])) AND (last_authorization_decision_event_id IS NOT NULL)))),
    CONSTRAINT ck_project_guides_policy_selection_shape CHECK (((((selected_review_policy_id IS NULL) AND (selected_review_policy_generation IS NULL) AND (selected_review_policy_hash IS NULL)) OR ((selected_review_policy_id IS NOT NULL) AND (selected_review_policy_generation IS NOT NULL) AND (selected_review_policy_hash IS NOT NULL))) AND (((selected_revision_policy_id IS NULL) AND (selected_revision_policy_generation IS NULL) AND (selected_revision_policy_hash IS NULL)) OR ((selected_revision_policy_id IS NOT NULL) AND (selected_revision_policy_generation IS NOT NULL) AND (selected_revision_policy_hash IS NOT NULL))))),
    CONSTRAINT ck_project_guides_task_examples_commitment_shape CHECK ((((task_examples IS NULL) AND (task_examples_hash IS NULL)) OR ((task_examples IS NOT NULL) AND (task_examples_hash IS NOT NULL) AND ((task_examples_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text))))
);
CREATE TABLE public.project_post_policy_operations (
    operation_id uuid NOT NULL,
    kind character varying(20) NOT NULL,
    idempotency_key uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    compilation_id uuid NOT NULL,
    policy_id uuid NOT NULL,
    upstream_approval_operation_id uuid NOT NULL,
    target_json json NOT NULL,
    target_digest character varying(71) NOT NULL,
    request_json json NOT NULL,
    request_digest character varying(71) NOT NULL,
    resource_context_json json NOT NULL,
    resource_context_digest character varying(71) NOT NULL,
    receipt_json json NOT NULL,
    output_digest character varying(71) NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    admin_role_grant_id uuid,
    service_identity character varying(100),
    authorization_decision_event_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_post_policy_operations_post_policy_operation_3661 CHECK (((((kind)::text = 'derive'::text) AND ((service_identity)::text = 'workstream.project.setup'::text) AND (admin_role_grant_id IS NULL)) OR (((kind)::text <> 'derive'::text) AND (service_identity IS NULL) AND (admin_role_grant_id IS NOT NULL)))),
    CONSTRAINT ck_project_post_policy_operations_post_policy_operation_hashes CHECK ((((target_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((output_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_project_post_policy_operations_post_policy_operation_kind CHECK (((kind)::text = ANY ((ARRAY['derive'::character varying, 'approve'::character varying, 'correction'::character varying])::text[]))),
    CONSTRAINT ck_project_post_policy_operations_post_policy_operation_sizes CHECK (((octet_length((target_json)::text) <= 32768) AND (octet_length((receipt_json)::text) <= 49152) AND (octet_length((request_json)::text) <= 49152) AND (octet_length((resource_context_json)::text) <= 16384)))
);
CREATE TABLE public.project_role_grants (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    role character varying(24) NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    version smallint DEFAULT '1'::smallint NOT NULL,
    grant_method character varying(16) DEFAULT 'manual'::character varying NOT NULL,
    qualification_snapshot_id uuid NOT NULL,
    granted_by_actor_profile_id uuid NOT NULL,
    granted_by_admin_role_grant_id uuid NOT NULL,
    grant_reason text NOT NULL,
    granted_at timestamp with time zone DEFAULT now() NOT NULL,
    revoked_by_actor_profile_id uuid,
    revoked_by_admin_role_grant_id uuid,
    revoked_reason text,
    revoked_at timestamp with time zone,
    CONSTRAINT ck_project_role_grants_grant_method CHECK (((grant_method)::text = 'manual'::text)),
    CONSTRAINT ck_project_role_grants_lifecycle CHECK (((((status)::text = 'active'::text) AND (version = 1) AND (revoked_by_actor_profile_id IS NULL) AND (revoked_by_admin_role_grant_id IS NULL) AND (revoked_reason IS NULL) AND (revoked_at IS NULL)) OR (((status)::text = 'revoked'::text) AND (version = 2) AND (revoked_by_actor_profile_id IS NOT NULL) AND (revoked_by_admin_role_grant_id IS NOT NULL) AND (revoked_reason IS NOT NULL) AND (revoked_at IS NOT NULL)))),
    CONSTRAINT ck_project_role_grants_reason CHECK ((public.project_role_reason_is_safe(grant_reason) AND ((revoked_reason IS NULL) OR public.project_role_reason_is_safe(revoked_reason)))),
    CONSTRAINT ck_project_role_grants_role CHECK (((role)::text = ANY (ARRAY[('submitter'::character varying)::text, ('reviewer'::character varying)::text])))
);
CREATE TABLE public.project_role_qualification_snapshots (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    requested_role character varying(24) NOT NULL,
    skills_snapshot jsonb NOT NULL,
    reputation_snapshot jsonb NOT NULL,
    prior_project_work_refs jsonb NOT NULL,
    external_expertise_refs jsonb NOT NULL,
    captured_by_actor_profile_id uuid NOT NULL,
    captured_by_admin_role_grant_id uuid NOT NULL,
    captured_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_role_qualification_snapshots_availability CHECK ((public.project_role_availability_is_safe(skills_snapshot) AND public.project_role_availability_is_safe(reputation_snapshot))),
    CONSTRAINT ck_project_role_qualification_snapshots_external_expertise_refs CHECK (public.project_role_reference_array_is_safe(external_expertise_refs, false)),
    CONSTRAINT ck_project_role_qualification_snapshots_prior_work_refs CHECK (public.project_role_reference_array_is_safe(prior_project_work_refs, true)),
    CONSTRAINT ck_project_role_qualification_snapshots_role CHECK (((requested_role)::text = ANY (ARRAY[('submitter'::character varying)::text, ('reviewer'::character varying)::text])))
);
CREATE TABLE public.projects (
    id uuid NOT NULL,
    name character varying(200) NOT NULL,
    slug character varying(120) NOT NULL,
    description text,
    status character varying(30) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by_actor_profile_id uuid,
    created_via_identity_link_id uuid,
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_action_id character varying(160),
    authorization_decision_event_id uuid,
    CONSTRAINT ck_projects_creation_authority_shape CHECK ((((created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (creation_scope_type IS NULL) AND (creation_action_id IS NULL) AND (authorization_decision_event_id IS NULL)) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND ((creation_scope_type)::text = 'system'::text) AND ((creation_action_id)::text = 'project.create'::text) AND (authorization_decision_event_id IS NOT NULL))))
);
CREATE TABLE public.review_admission_idempotency_records (
    id uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    operation_id uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    project_id uuid NOT NULL,
    task_id uuid NOT NULL,
    submission_id uuid NOT NULL,
    submission_version integer NOT NULL,
    admitting_checker_run_id uuid NOT NULL,
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    review_queue_entry_id uuid,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_review_admission_idempotency_records_ck_review_admis_2b6d CHECK ((submission_version > 0)),
    CONSTRAINT ck_review_admission_idempotency_records_ck_review_admis_4cd5 CHECK (((((status)::text = 'pending'::text) AND (review_queue_entry_id IS NULL) AND (committed_at IS NULL)) OR (((status)::text = 'committed'::text) AND (review_queue_entry_id IS NOT NULL) AND (committed_at IS NOT NULL)))),
    CONSTRAINT ck_review_admission_idempotency_records_ck_review_admis_88bf CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_review_admission_idempotency_records_ck_review_admis_b8b8 CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('committed'::character varying)::text])))
);
CREATE TABLE public.review_leases (
    id uuid NOT NULL,
    review_queue_entry_id uuid NOT NULL,
    project_id uuid NOT NULL,
    task_id uuid NOT NULL,
    submission_id uuid NOT NULL,
    submission_version integer NOT NULL,
    reviewer_id uuid NOT NULL,
    reviewer_contribution_policy_version_id uuid NOT NULL,
    attempt_generation integer NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    claimed_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    closed_at timestamp with time zone,
    close_reason character varying(32),
    CONSTRAINT ck_review_leases_attempt_generation_positive CHECK ((attempt_generation > 0)),
    CONSTRAINT ck_review_leases_closure_after_claim CHECK (((closed_at IS NULL) OR (closed_at >= claimed_at))),
    CONSTRAINT ck_review_leases_expiry_after_claim CHECK ((expires_at > claimed_at)),
    CONSTRAINT ck_review_leases_lifecycle_shape CHECK (((((status)::text = 'active'::text) AND (closed_at IS NULL) AND (close_reason IS NULL)) OR (((status)::text = 'consumed'::text) AND (closed_at IS NOT NULL) AND ((close_reason)::text = 'review_recorded'::text)) OR (((status)::text = 'released'::text) AND (closed_at IS NOT NULL) AND ((close_reason)::text = 'manual_release'::text)) OR (((status)::text = 'expired'::text) AND (closed_at IS NOT NULL) AND ((close_reason)::text = 'lease_expired'::text)) OR (((status)::text = 'revoked'::text) AND (closed_at IS NOT NULL) AND ((close_reason)::text = ANY (ARRAY[('grant_revoked'::character varying)::text, ('admin_override'::character varying)::text]))))),
    CONSTRAINT ck_review_leases_status CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('consumed'::character varying)::text, ('released'::character varying)::text, ('expired'::character varying)::text, ('revoked'::character varying)::text])))
);
CREATE TABLE public.review_policies (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    requires_second_review boolean NOT NULL,
    allowed_decisions json NOT NULL,
    minimum_finding_fields json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    policy_generation integer NOT NULL,
    policy_hash character varying(71) NOT NULL,
    semantics_status character varying(24) NOT NULL,
    supersedes_policy_id uuid,
    review_preference_window_seconds integer,
    review_lease_duration_seconds integer,
    max_active_review_leases_per_reviewer integer,
    self_review_allowed boolean,
    reject_policy character varying(32),
    finding_evidence_requirement character varying(32),
    predecessor_policy_hash character varying(71),
    created_by_actor_profile_id uuid,
    created_via_identity_link_id uuid,
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_scope_project_id uuid,
    creation_action_id character varying(160),
    authorization_decision_event_id uuid,
    human_review_required boolean NOT NULL,
    semantics_format character varying(2) DEFAULT 'v2'::character varying NOT NULL,
    CONSTRAINT ck_review_policies_review_policy_authority_shape CHECK ((((semantics_status)::text = 'legacy_incomplete'::text) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND ((creation_scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text])) AND ((creation_action_id)::text = 'project.review_policy.update'::text) AND (authorization_decision_event_id IS NOT NULL)))),
    CONSTRAINT ck_review_policies_review_policy_identity_shape CHECK (((policy_generation > 0) AND ((policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((semantics_status)::text = ANY (ARRAY[('complete'::character varying)::text, ('legacy_incomplete'::character varying)::text])))),
    CONSTRAINT ck_review_policies_review_policy_predecessor_shape CHECK ((((supersedes_policy_id IS NULL) AND (predecessor_policy_hash IS NULL) AND (policy_generation = 1)) OR ((supersedes_policy_id IS NOT NULL) AND ((predecessor_policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND (policy_generation > 1)) OR ((semantics_status)::text = 'legacy_incomplete'::text))),
    CONSTRAINT ck_review_policies_review_policy_semantics_format CHECK ((((semantics_format)::text = ANY ((ARRAY['v1'::character varying, 'v2'::character varying])::text[])) AND (((semantics_format)::text <> 'v1'::text) OR human_review_required))),
    CONSTRAINT ck_review_policies_review_policy_semantics_shape CHECK ((((semantics_status)::text = 'legacy_incomplete'::text) OR ((review_preference_window_seconds > 0) AND (review_lease_duration_seconds > 0) AND (max_active_review_leases_per_reviewer = 1) AND (self_review_allowed = false) AND ((reject_policy)::text = 'close_task'::text) AND ((finding_evidence_requirement)::text = ANY (ARRAY[('optional'::character varying)::text, ('required_for_blocking'::character varying)::text, ('required_for_all'::character varying)::text])))))
);
CREATE TABLE public.review_queue_entries (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    task_id uuid NOT NULL,
    submission_id uuid NOT NULL,
    submission_version integer NOT NULL,
    admitting_checker_run_id uuid NOT NULL,
    queue_state character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    routing_mode character varying(16) NOT NULL,
    routing_reason character varying(32) NOT NULL,
    first_queued_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    available_since timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    preferred_reviewer_id uuid,
    preference_expires_at timestamp with time zone,
    closed_at timestamp with time zone,
    closed_reason character varying(32),
    routing_generation integer DEFAULT 1 NOT NULL,
    lifecycle_generation integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    active_lease_id uuid,
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_availab_d484 CHECK ((available_since >= first_queued_at)),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_generat_38b7 CHECK (((routing_generation > 0) AND (lifecycle_generation > 0))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_lifecycle_shape CHECK (((((queue_state)::text = 'pending'::text) AND (active_lease_id IS NULL) AND (closed_at IS NULL) AND (closed_reason IS NULL)) OR (((queue_state)::text = 'leased'::text) AND (active_lease_id IS NOT NULL) AND (closed_at IS NULL) AND (closed_reason IS NULL)) OR (((queue_state)::text = 'closed'::text) AND (active_lease_id IS NULL) AND (closed_at IS NOT NULL) AND ((closed_reason)::text = ANY (ARRAY[('review_recorded'::character varying)::text, ('task_closed'::character varying)::text, ('admin_cancelled'::character varying)::text])) AND (closed_at >= first_queued_at)))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_queue_state CHECK (((queue_state)::text = ANY (ARRAY[('pending'::character varying)::text, ('leased'::character varying)::text, ('closed'::character varying)::text]))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_routing_mode CHECK (((routing_mode)::text = ANY (ARRAY[('open'::character varying)::text, ('preferred'::character varying)::text]))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_routing_reason CHECK (((routing_reason)::text = ANY (ARRAY[('first_submission'::character varying)::text, ('revision_return'::character varying)::text, ('admin_assignment'::character varying)::text]))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_routing_shape CHECK (((((routing_mode)::text = 'open'::text) AND (preferred_reviewer_id IS NULL) AND (preference_expires_at IS NULL)) OR (((routing_mode)::text = 'preferred'::text) AND (preferred_reviewer_id IS NOT NULL) AND (preference_expires_at IS NOT NULL) AND (preference_expires_at > first_queued_at)))),
    CONSTRAINT ck_review_queue_entries_ck_review_queue_entries_submiss_2f6b CHECK ((submission_version > 0))
);
CREATE TABLE public.revision_policies (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    max_revision_rounds integer NOT NULL,
    revision_deadline_hours integer NOT NULL,
    allowed_resubmission_states json NOT NULL,
    reviewer_reassignment_rule text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    policy_generation integer NOT NULL,
    policy_hash character varying(71) NOT NULL,
    semantics_status character varying(24) NOT NULL,
    supersedes_policy_id uuid,
    predecessor_policy_hash character varying(71),
    created_by_actor_profile_id uuid,
    created_via_identity_link_id uuid,
    created_by_admin_role_grant_id uuid,
    creation_scope_type character varying(16),
    creation_scope_project_id uuid,
    creation_action_id character varying(160),
    authorization_decision_event_id uuid,
    CONSTRAINT ck_revision_policies_revision_policy_authority_shape CHECK ((((semantics_status)::text = 'legacy_incomplete'::text) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (created_by_admin_role_grant_id IS NOT NULL) AND ((creation_scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text])) AND ((creation_action_id)::text = 'project.revision_policy.update'::text) AND (authorization_decision_event_id IS NOT NULL)))),
    CONSTRAINT ck_revision_policies_revision_policy_identity_shape CHECK (((policy_generation > 0) AND ((policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((semantics_status)::text = ANY (ARRAY[('complete'::character varying)::text, ('legacy_incomplete'::character varying)::text])))),
    CONSTRAINT ck_revision_policies_revision_policy_predecessor_shape CHECK ((((supersedes_policy_id IS NULL) AND (predecessor_policy_hash IS NULL) AND (policy_generation = 1)) OR ((supersedes_policy_id IS NOT NULL) AND ((predecessor_policy_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND (policy_generation > 1)) OR ((semantics_status)::text = 'legacy_incomplete'::text))),
    CONSTRAINT ck_revision_policies_revision_policy_semantics_shape CHECK ((((semantics_status)::text = 'legacy_incomplete'::text) OR ((max_revision_rounds > 0) AND (revision_deadline_hours > 0))))
);
CREATE TABLE public.submission_artifact_policies (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    guide_version character varying(50) NOT NULL,
    source_snapshot_id uuid NOT NULL,
    source_snapshot_hash character varying(71) NOT NULL,
    policy_version character varying(50) NOT NULL,
    lifecycle_status character varying(30) NOT NULL,
    policy_body json NOT NULL,
    policy_hash character varying(71) NOT NULL,
    derivation_source character varying(100) NOT NULL,
    source_material_refs json NOT NULL,
    derivation_agent_name character varying(100),
    derivation_agent_version character varying(50),
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    approved_by_role character varying(50),
    approved_by_actor character varying(100),
    approved_at timestamp with time zone,
    supersedes_policy_id uuid,
    superseded_at timestamp with time zone,
    change_summary text,
    created_by_actor_profile_id uuid,
    created_via_identity_link_id uuid,
    created_by_admin_role_grant_id uuid,
    created_by_service_identity character varying(160),
    creation_scope_type character varying(16),
    creation_scope_project_id uuid,
    creation_action_id character varying(160),
    creation_decision_event_id uuid,
    approved_by_actor_profile_id uuid,
    approved_via_identity_link_id uuid,
    approved_by_admin_role_grant_id uuid,
    approval_scope_type character varying(16),
    approval_scope_project_id uuid,
    approval_action_id character varying(160),
    approval_decision_event_id uuid,
    CONSTRAINT ck_submission_artifact_policies_ck_submission_artifact__20ca CHECK (((lifecycle_status)::text = ANY (ARRAY[('draft'::character varying)::text, ('approved'::character varying)::text, ('superseded'::character varying)::text]))),
    CONSTRAINT ck_submission_artifact_policies_ck_submission_artifact__52ca CHECK ((((lifecycle_status)::text <> 'approved'::text) OR (((approved_by_role)::text = ANY (ARRAY[('admin'::character varying)::text, ('project_manager'::character varying)::text])) AND (approved_by_actor IS NOT NULL) AND (approved_at IS NOT NULL)))),
    CONSTRAINT ck_submission_artifact_policies_ck_submission_policy_ap_0e4d CHECK ((((approved_by_actor_profile_id IS NULL) AND (approved_via_identity_link_id IS NULL) AND (approved_by_admin_role_grant_id IS NULL) AND (approval_scope_type IS NULL) AND (approval_scope_project_id IS NULL) AND (approval_action_id IS NULL) AND (approval_decision_event_id IS NULL)) OR ((approved_by_actor_profile_id IS NOT NULL) AND (approved_via_identity_link_id IS NOT NULL) AND (approved_by_admin_role_grant_id IS NOT NULL) AND (approval_scope_type IS NOT NULL) AND (approval_action_id IS NOT NULL) AND ((approval_scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text])) AND (approval_scope_project_id IS NOT NULL) AND ((approval_scope_project_id)::text = (project_id)::text) AND ((approval_action_id)::text = 'project.submission_artifact_policy.approve'::text) AND (approval_decision_event_id IS NOT NULL)))),
    CONSTRAINT ck_submission_artifact_policies_ck_submission_policy_cr_0629 CHECK ((((created_by_actor_profile_id IS NULL) AND (created_via_identity_link_id IS NULL) AND (created_by_admin_role_grant_id IS NULL) AND (created_by_service_identity IS NULL) AND (creation_scope_type IS NULL) AND (creation_scope_project_id IS NULL) AND (creation_action_id IS NULL) AND (creation_decision_event_id IS NULL)) OR ((created_by_actor_profile_id IS NOT NULL) AND (created_via_identity_link_id IS NOT NULL) AND (creation_scope_type IS NOT NULL) AND (creation_action_id IS NOT NULL) AND (creation_scope_project_id IS NOT NULL) AND ((creation_scope_project_id)::text = (project_id)::text) AND (creation_decision_event_id IS NOT NULL) AND ((creation_action_id)::text = ANY (ARRAY[('project.submission_artifact_policy.create'::character varying)::text, ('project.submission_artifact_policy.derive'::character varying)::text, ('project.submission_artifact_policy.update'::character varying)::text])) AND (((created_by_admin_role_grant_id IS NOT NULL) AND (created_by_service_identity IS NULL) AND ((creation_scope_type)::text = ANY (ARRAY[('system'::character varying)::text, ('project'::character varying)::text]))) OR ((created_by_admin_role_grant_id IS NULL) AND (created_by_service_identity IS NOT NULL) AND ((created_by_service_identity)::text = 'workstream.project.setup'::text) AND ((creation_scope_type)::text = 'service'::text) AND ((creation_action_id)::text = 'project.submission_artifact_policy.derive'::text))))))
);
CREATE TABLE public.submission_bundle_admissions (
    id uuid NOT NULL,
    durable_intent_id uuid NOT NULL,
    pre_submit_evidence_set_id uuid NOT NULL,
    put_attempt_id uuid NOT NULL,
    artifact_content_id uuid NOT NULL,
    verified_replica_id uuid NOT NULL,
    verification_receipt_id uuid NOT NULL,
    put_operation_receipt_id uuid,
    put_observation_receipt_id uuid,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    project_id uuid NOT NULL,
    task_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    predecessor_submission_id uuid,
    predecessor_submission_version integer,
    locked_policy_context_hash character varying(71) NOT NULL,
    semantic_manifest_id uuid NOT NULL,
    semantic_manifest_sha256 character varying(71) NOT NULL,
    archive_sha256 character varying(71) NOT NULL,
    archive_byte_count bigint NOT NULL,
    status character varying(16) DEFAULT 'ready'::character varying NOT NULL,
    ready_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    consumed_by_submission_id uuid,
    stale_at timestamp with time zone,
    stale_reason character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    consumed_by_submission_version integer,
    CONSTRAINT ck_submission_bundle_admissions_archive_sha256 CHECK (((archive_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_submission_bundle_admissions_archive_size CHECK ((archive_byte_count >= 0)),
    CONSTRAINT ck_submission_bundle_admissions_manifest_sha256 CHECK (((semantic_manifest_sha256)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_submission_bundle_admissions_policy_context_hash CHECK (((locked_policy_context_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_submission_bundle_admissions_predecessor_shape CHECK (((predecessor_submission_id IS NULL) = (predecessor_submission_version IS NULL))),
    CONSTRAINT ck_submission_bundle_admissions_status CHECK (((status)::text = ANY (ARRAY[('ready'::character varying)::text, ('consumed'::character varying)::text, ('stale'::character varying)::text]))),
    CONSTRAINT ck_submission_bundle_admissions_terminal_shape CHECK (((((status)::text = 'ready'::text) AND (consumed_at IS NULL) AND (consumed_by_submission_id IS NULL) AND (consumed_by_submission_version IS NULL) AND (stale_at IS NULL) AND (stale_reason IS NULL)) OR (((status)::text = 'consumed'::text) AND (consumed_at IS NOT NULL) AND (consumed_by_submission_id IS NOT NULL) AND (consumed_by_submission_version > 0) AND (stale_at IS NULL) AND (stale_reason IS NULL)) OR (((status)::text = 'stale'::text) AND (consumed_at IS NULL) AND (consumed_by_submission_id IS NULL) AND (consumed_by_submission_version IS NULL) AND (stale_at IS NOT NULL) AND ((octet_length((stale_reason)::text) >= 1) AND (octet_length((stale_reason)::text) <= 500))))),
    CONSTRAINT ck_submission_bundle_admissions_write_receipt_shape CHECK (((((put_operation_receipt_id IS NOT NULL))::integer + ((put_observation_receipt_id IS NOT NULL))::integer) = 1))
);
CREATE TABLE public.submission_bundle_durable_intents (
    id uuid NOT NULL,
    pre_submit_evidence_set_id uuid NOT NULL,
    put_attempt_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.submission_policy_mutation_idempotency_records (
    id uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    identity_link_id uuid NOT NULL,
    service_identity character varying(160),
    action_id character varying(160) NOT NULL,
    idempotency_key uuid,
    request_digest character varying(71) NOT NULL,
    resource_context_digest character varying(71) NOT NULL,
    resource_context_json json NOT NULL,
    operation_id uuid NOT NULL,
    project_id uuid NOT NULL,
    guide_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    policy_id uuid NOT NULL,
    setup_run_id uuid,
    setup_generation bigint NOT NULL,
    setup_task_id uuid,
    correlation_id uuid,
    status character varying(16) NOT NULL,
    response_json json,
    committed_policy_id uuid,
    committed_effective_policy_id uuid,
    committed_pre_submit_policy_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_0119 CHECK ((((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND ((resource_context_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_0dbe CHECK (((action_id)::text = ANY (ARRAY[('project.submission_artifact_policy.create'::character varying)::text, ('project.submission_artifact_policy.derive'::character varying)::text, ('project.submission_artifact_policy.update'::character varying)::text, ('project.submission_artifact_policy.approve'::character varying)::text]))),
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_2b53 CHECK ((setup_generation > 0)),
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_58d4 CHECK (((((status)::text = ANY (ARRAY[('reserved'::character varying)::text, ('pending'::character varying)::text])) AND (response_json IS NULL) AND (committed_at IS NULL) AND (committed_policy_id IS NULL) AND (committed_effective_policy_id IS NULL) AND (committed_pre_submit_policy_id IS NULL)) OR (((status)::text = 'committed'::text) AND (response_json IS NOT NULL) AND (committed_at IS NOT NULL) AND (committed_policy_id IS NOT NULL) AND ((((action_id)::text = 'project.submission_artifact_policy.approve'::text) AND (committed_effective_policy_id IS NOT NULL) AND (committed_pre_submit_policy_id IS NOT NULL)) OR (((action_id)::text <> 'project.submission_artifact_policy.approve'::text) AND (committed_effective_policy_id IS NULL) AND (committed_pre_submit_policy_id IS NULL)))))),
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_a824 CHECK (((status)::text = ANY (ARRAY[('reserved'::character varying)::text, ('pending'::character varying)::text, ('committed'::character varying)::text]))),
    CONSTRAINT ck_submission_policy_mutation_idempotency_records_ck_su_b357 CHECK ((((service_identity IS NULL) AND (idempotency_key IS NOT NULL) AND (setup_run_id IS NULL) AND (setup_task_id IS NULL) AND (correlation_id IS NULL)) OR ((service_identity IS NOT NULL) AND ((service_identity)::text = 'workstream.project.setup'::text) AND (idempotency_key IS NULL) AND ((action_id)::text = 'project.submission_artifact_policy.derive'::text) AND (setup_run_id IS NOT NULL) AND (setup_task_id IS NOT NULL) AND (correlation_id IS NOT NULL))))
);
CREATE TABLE public.submissions (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    contributor_id uuid NOT NULL,
    version integer NOT NULL,
    status character varying(30) NOT NULL,
    summary text NOT NULL,
    package_uri character varying(1000),
    package_hash character varying(128),
    artifact_hash_manifest json NOT NULL,
    worker_attestation text NOT NULL,
    locked_guide_version character varying(50) NOT NULL,
    locked_payment_policy_version character varying(50),
    submitted_at timestamp with time zone DEFAULT now() NOT NULL,
    locked_at timestamp with time zone,
    supersedes_submission_id uuid,
    locked_guide_source_snapshot_id uuid,
    locked_guide_source_snapshot_hash character varying(71),
    locked_effective_project_submission_artifact_policy_id uuid,
    locked_effective_project_submission_artifact_policy_hash character varying(71),
    locked_pre_submit_checker_policy_id uuid,
    locked_pre_submit_checker_bundle_hash character varying(71),
    locked_post_submit_checker_policy_id uuid,
    locked_post_submit_checker_policy_version character varying(50),
    locked_post_submit_checker_policy_hash character varying(71),
    locked_post_submit_checker_policy_body json,
    locked_review_policy_id uuid NOT NULL,
    locked_review_policy_generation integer NOT NULL,
    locked_review_policy_hash character varying(71) NOT NULL,
    locked_revision_policy_id uuid NOT NULL,
    locked_revision_policy_generation integer NOT NULL,
    locked_revision_policy_hash character varying(71) NOT NULL,
    task_assignment_id uuid NOT NULL,
    submission_bundle_admission_id uuid,
    artifact_binding_id uuid,
    artifact_content_id uuid,
    contribution_policy_version_id uuid NOT NULL,
    CONSTRAINT ck_submissions_artifact_lineage_shape CHECK ((((submission_bundle_admission_id IS NULL) AND (artifact_binding_id IS NULL) AND (artifact_content_id IS NULL)) OR ((submission_bundle_admission_id IS NOT NULL) AND (artifact_binding_id IS NOT NULL) AND (artifact_content_id IS NOT NULL)))),
    CONSTRAINT ck_submissions_post_submit_policy_lock_complete CHECK (((locked_post_submit_checker_policy_id IS NOT NULL) AND (locked_post_submit_checker_policy_version IS NOT NULL) AND (locked_post_submit_checker_policy_hash IS NOT NULL) AND (locked_post_submit_checker_policy_body IS NOT NULL)))
);
CREATE TABLE public.task_assignments (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    contributor_id uuid NOT NULL,
    assigned_by character varying(100) NOT NULL,
    assigned_at timestamp with time zone DEFAULT now() NOT NULL,
    accepted_at timestamp with time zone,
    released_at timestamp with time zone,
    status character varying(30) NOT NULL,
    project_id uuid NOT NULL,
    submitter_contribution_policy_version_id uuid NOT NULL
);
CREATE TABLE public.task_command_receipts (
    id uuid NOT NULL,
    actor_profile_id uuid NOT NULL,
    action_id character varying(160) NOT NULL,
    idempotency_key uuid NOT NULL,
    request_digest character varying(71) NOT NULL,
    task_id uuid NOT NULL,
    status character varying(16) NOT NULL,
    assignment_id uuid,
    contributor_id uuid,
    locked_context_hash character varying(71),
    response jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    committed_at timestamp with time zone,
    CONSTRAINT ck_task_command_receipts_task_command_action CHECK (((action_id)::text = ANY ((ARRAY['task.claim'::character varying, 'task.start'::character varying, 'operations.task.start_override'::character varying, 'project.task.create'::character varying, 'project.task.screen'::character varying, 'project.task.release'::character varying])::text[]))),
    CONSTRAINT ck_task_command_receipts_task_command_contributor CHECK ((((status)::text = 'pending'::text) OR ((action_id)::text = ANY ((ARRAY['project.task.create'::character varying, 'project.task.screen'::character varying, 'project.task.release'::character varying])::text[])) OR (((action_id)::text = 'operations.task.start_override'::text) AND ((actor_profile_id)::text <> (contributor_id)::text)) OR (((action_id)::text = ANY ((ARRAY['task.claim'::character varying, 'task.start'::character varying])::text[])) AND ((actor_profile_id)::text = (contributor_id)::text)))),
    CONSTRAINT ck_task_command_receipts_task_command_request_digest CHECK (((request_digest)::text ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_task_command_receipts_task_command_state_shape CHECK (((((status)::text = 'pending'::text) AND (assignment_id IS NULL) AND (contributor_id IS NULL) AND (locked_context_hash IS NULL) AND (response IS NULL) AND (committed_at IS NULL)) OR (((status)::text = 'committed'::text) AND ((((action_id)::text = ANY ((ARRAY['task.claim'::character varying, 'task.start'::character varying, 'operations.task.start_override'::character varying])::text[])) AND (assignment_id IS NOT NULL) AND (contributor_id IS NOT NULL)) OR (((action_id)::text = ANY ((ARRAY['project.task.create'::character varying, 'project.task.screen'::character varying, 'project.task.release'::character varying])::text[])) AND (assignment_id IS NULL) AND (contributor_id IS NULL))) AND (locked_context_hash IS NOT NULL) AND ((locked_context_hash)::text ~ '^sha256:[0-9a-f]{64}$'::text) AND (response IS NOT NULL) AND (jsonb_typeof(response) = 'object'::text) AND (committed_at IS NOT NULL))))
);
CREATE TABLE public.workstream_tasks (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    locked_guide_version character varying(50),
    locked_payment_policy_version character varying(50),
    source_type character varying(50) NOT NULL,
    source_ref character varying(500),
    source_payload_hash character varying(128),
    import_batch_id character varying(100),
    external_task_id character varying(200),
    title character varying(300) NOT NULL,
    description text NOT NULL,
    task_type character varying(100),
    difficulty character varying(50),
    skill_tags json NOT NULL,
    estimated_time_minutes integer,
    base_amount numeric(12,2),
    currency character varying(20),
    payout_type character varying(50),
    status character varying(30) NOT NULL,
    acceptance_criteria text,
    rejection_criteria text,
    deadline_at timestamp with time zone,
    created_by character varying(100) NOT NULL,
    assigned_to character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    locked_guide_source_snapshot_id uuid,
    locked_guide_source_snapshot_hash character varying(71),
    locked_effective_project_submission_artifact_policy_id uuid,
    locked_effective_project_submission_artifact_policy_hash character varying(71),
    locked_pre_submit_checker_policy_id uuid,
    locked_pre_submit_checker_bundle_hash character varying(71),
    locked_post_submit_checker_policy_id uuid,
    locked_post_submit_checker_policy_version character varying(50),
    locked_post_submit_checker_policy_hash character varying(71),
    locked_post_submit_checker_policy_body json,
    locked_review_policy_id uuid,
    locked_review_policy_generation integer,
    locked_review_policy_hash character varying(71),
    locked_revision_policy_id uuid,
    locked_revision_policy_generation integer,
    locked_revision_policy_hash character varying(71),
    locked_contribution_policy_version_id uuid,
    CONSTRAINT ck_workstream_tasks_contribution_policy_guide_required CHECK (((locked_contribution_policy_version_id IS NULL) OR (locked_guide_version IS NOT NULL))),
    CONSTRAINT ck_workstream_tasks_contribution_policy_required CHECK ((((status)::text = 'draft'::text) OR (locked_contribution_policy_version_id IS NOT NULL))),
    CONSTRAINT ck_workstream_tasks_post_submit_policy_lock_complete CHECK ((((status)::text = 'draft'::text) OR ((locked_post_submit_checker_policy_id IS NOT NULL) AND (locked_post_submit_checker_policy_version IS NOT NULL) AND (locked_post_submit_checker_policy_hash IS NOT NULL) AND (locked_post_submit_checker_policy_body IS NOT NULL)))),
    CONSTRAINT ck_workstream_tasks_review_revision_policy_lock_required CHECK ((((status)::text = 'draft'::text) OR ((locked_review_policy_id IS NOT NULL) AND (locked_review_policy_generation IS NOT NULL) AND (locked_review_policy_hash IS NOT NULL) AND (locked_revision_policy_id IS NOT NULL) AND (locked_revision_policy_generation IS NOT NULL) AND (locked_revision_policy_hash IS NOT NULL)))),
    CONSTRAINT ck_workstream_tasks_review_revision_policy_lock_shape CHECK ((((locked_review_policy_id IS NULL) AND (locked_review_policy_generation IS NULL) AND (locked_review_policy_hash IS NULL) AND (locked_revision_policy_id IS NULL) AND (locked_revision_policy_generation IS NULL) AND (locked_revision_policy_hash IS NULL)) OR ((locked_review_policy_id IS NOT NULL) AND (locked_review_policy_generation IS NOT NULL) AND (locked_review_policy_hash IS NOT NULL) AND (locked_revision_policy_id IS NOT NULL) AND (locked_revision_policy_generation IS NOT NULL) AND (locked_revision_policy_hash IS NOT NULL))))
);
ALTER TABLE ONLY public.actor_profile_migration_state ALTER COLUMN id SET DEFAULT nextval('public.actor_profile_migration_state_id_seq'::regclass);
ALTER TABLE ONLY public.authority_control ALTER COLUMN id SET DEFAULT nextval('public.authority_control_id_seq'::regclass);
ALTER TABLE ONLY public.compensation_adapter_binding_lifecycle_events
    ADD CONSTRAINT binding_version UNIQUE (adapter_binding_id, to_lifecycle_version);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT grant_reference UNIQUE (id, actor_profile_id, project_id, requested_role);
ALTER TABLE ONLY public.compensation_adapter_binding_lifecycle_events
    ADD CONSTRAINT operation_id UNIQUE (operation_id);
ALTER TABLE ONLY public.actor_identity_links
    ADD CONSTRAINT pk_actor_identity_links PRIMARY KEY (id);
ALTER TABLE ONLY public.actor_profile_migration_state
    ADD CONSTRAINT pk_actor_profile_migration_state PRIMARY KEY (id);
ALTER TABLE ONLY public.actor_profiles
    ADD CONSTRAINT pk_actor_profiles PRIMARY KEY (id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT pk_admin_role_grants PRIMARY KEY (id);
ALTER TABLE ONLY public.api_rate_control_counters
    ADD CONSTRAINT pk_api_rate_control_counters PRIMARY KEY (control_scope, key_digest);
ALTER TABLE ONLY public.artifact_admission_charges
    ADD CONSTRAINT pk_artifact_admission_charges PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_admission_scopes
    ADD CONSTRAINT pk_artifact_admission_scopes PRIMARY KEY (scope_type, scope_id);
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT pk_artifact_bindings PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_contents
    ADD CONSTRAINT pk_artifact_contents PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT pk_artifact_operation_receipts PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_put_attempt_charges
    ADD CONSTRAINT pk_artifact_put_attempt_charges PRIMARY KEY (attempt_id, charge_id);
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT pk_artifact_put_attempts PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_put_observation_receipts
    ADD CONSTRAINT pk_artifact_put_observation_receipts PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT pk_artifact_recovery_attempts PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_replicas
    ADD CONSTRAINT pk_artifact_replicas PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_storage_namespaces
    ADD CONSTRAINT pk_artifact_storage_namespaces PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_verification_jobs
    ADD CONSTRAINT pk_artifact_verification_jobs PRIMARY KEY (id);
ALTER TABLE ONLY public.artifact_verification_receipts
    ADD CONSTRAINT pk_artifact_verification_receipts PRIMARY KEY (id);
ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT pk_audit_events PRIMARY KEY (id);
ALTER TABLE ONLY public.authority_control
    ADD CONSTRAINT pk_authority_control PRIMARY KEY (id);
ALTER TABLE ONLY public.authority_idempotency_records
    ADD CONSTRAINT pk_authority_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT pk_checker_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.checker_results
    ADD CONSTRAINT pk_checker_results PRIMARY KEY (id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT pk_checker_runs PRIMARY KEY (id);
ALTER TABLE ONLY public.compensation_adapter_binding_lifecycle_events
    ADD CONSTRAINT pk_compensation_adapter_binding_lifecycle_events PRIMARY KEY (id);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT pk_contribution_award_definitions PRIMARY KEY (id);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT pk_contribution_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.contribution_policy_lifecycle_events
    ADD CONSTRAINT pk_contribution_policy_lifecycle_events PRIMARY KEY (id);
ALTER TABLE ONLY public.contribution_policy_transition_custody
    ADD CONSTRAINT pk_contribution_policy_transition_custody PRIMARY KEY (id);
ALTER TABLE ONLY public.contribution_policy_transition_custody ADD CONSTRAINT uq_contribution_policy_custody_operation UNIQUE (operation_id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT pk_contribution_policy_versions PRIMARY KEY (id);
ALTER TABLE ONLY public.contribution_rules
    ADD CONSTRAINT pk_contribution_rules PRIMARY KEY (id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT pk_effective_project_submission_artifact_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.evidence_items
    ADD CONSTRAINT pk_evidence_items PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT pk_guide_mutation_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT pk_guide_source_artifact_bindings PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_artifact_incidents
    ADD CONSTRAINT pk_guide_source_artifact_incidents PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_artifact_ingests
    ADD CONSTRAINT pk_guide_source_artifact_ingests PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_extracted_contents
    ADD CONSTRAINT pk_guide_source_extracted_contents PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_extraction_attempts
    ADD CONSTRAINT pk_guide_source_extraction_attempts PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_extraction_retry_budgets
    ADD CONSTRAINT pk_guide_source_extraction_retry_budgets PRIMARY KEY (binding_id);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT pk_guide_source_extraction_usages PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_format_classifications
    ADD CONSTRAINT pk_guide_source_format_classifications PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_snapshot_items
    ADD CONSTRAINT pk_guide_source_snapshot_items PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT pk_guide_source_snapshots PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT pk_guide_sufficiency_mutation_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_sufficiency_report_source_usages
    ADD CONSTRAINT pk_guide_sufficiency_report_source_usages PRIMARY KEY (id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT pk_guide_sufficiency_reports PRIMARY KEY (id);
ALTER TABLE ONLY public.iso_4217_currency_codes
    ADD CONSTRAINT pk_iso_4217_currency_codes PRIMARY KEY (code);
ALTER TABLE ONLY public.legacy_actor_identities
    ADD CONSTRAINT pk_legacy_actor_identities PRIMARY KEY (actor_id);
ALTER TABLE ONLY public.legacy_workflow_eligibility
    ADD CONSTRAINT pk_legacy_workflow_eligibility PRIMARY KEY (id);
ALTER TABLE ONLY public.outbox_delivery_attempts
    ADD CONSTRAINT pk_outbox_delivery_attempts PRIMARY KEY (event_id, claim_generation);
ALTER TABLE ONLY public.outbox_events
    ADD CONSTRAINT pk_outbox_events PRIMARY KEY (event_id);
ALTER TABLE ONLY public.payment_policies
    ADD CONSTRAINT pk_payment_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT pk_policy_mutation_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT pk_pre_submit_checker_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.pre_submit_evidence_results
    ADD CONSTRAINT pk_pre_submit_evidence_results PRIMARY KEY (id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT pk_pre_submit_evidence_sets PRIMARY KEY (id);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT pk_project_compensation_adapter_bindings PRIMARY KEY (id);
ALTER TABLE ONLY public.project_compensation_units
    ADD CONSTRAINT pk_project_compensation_units PRIMARY KEY (project_id, instrument_type, unit_code);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT pk_project_create_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT pk_project_guide_compilation_attempts PRIMARY KEY (id);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT pk_project_guide_compilation_request_operations PRIMARY KEY (operation_id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT pk_project_guide_compilations PRIMARY KEY (id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT pk_project_guide_component_projection_operations PRIMARY KEY (operation_id);
ALTER TABLE ONLY public.project_guide_document_accesses
    ADD CONSTRAINT pk_project_guide_document_accesses PRIMARY KEY (id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT pk_project_guide_proposal_approvals PRIMARY KEY (operation_id);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT pk_project_guide_proposal_corrections PRIMARY KEY (operation_id);
ALTER TABLE ONLY public.project_guide_runtime_allocations
    ADD CONSTRAINT pk_project_guide_runtime_allocations PRIMARY KEY (id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT pk_project_guide_setup_finalizations PRIMARY KEY (id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT pk_project_guides PRIMARY KEY (id);
ALTER TABLE ONLY public.project_post_policy_operations
    ADD CONSTRAINT pk_project_post_policy_operations PRIMARY KEY (operation_id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT pk_project_role_grants PRIMARY KEY (id);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT pk_project_role_qualification_snapshots PRIMARY KEY (id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT pk_project_setup_runs PRIMARY KEY (id);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT pk_projects PRIMARY KEY (id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT pk_review_admission_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT pk_review_leases PRIMARY KEY (id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT pk_review_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT pk_review_queue_entries PRIMARY KEY (id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT pk_revision_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT pk_submission_artifact_policies PRIMARY KEY (id);
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT pk_submission_bundle_admissions PRIMARY KEY (id);
ALTER TABLE ONLY public.submission_bundle_durable_intents
    ADD CONSTRAINT pk_submission_bundle_durable_intents PRIMARY KEY (id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT pk_submission_policy_mutation_idempotency_records PRIMARY KEY (id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT pk_submissions PRIMARY KEY (id);
ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT pk_task_assignments PRIMARY KEY (id);
ALTER TABLE ONLY public.task_command_receipts
    ADD CONSTRAINT pk_task_command_receipts PRIMARY KEY (id);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT pk_workstream_tasks PRIMARY KEY (id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT pre_submit_evidence_sets_attempt_id_key UNIQUE (attempt_id);
ALTER TABLE ONLY public.pre_submit_execution_attempts
    ADD CONSTRAINT pre_submit_execution_attempts_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.actor_profiles
    ADD CONSTRAINT service_identity UNIQUE (service_identity);
ALTER TABLE ONLY public.actor_identity_links
    ADD CONSTRAINT uq_actor_identity_links_actor_profile UNIQUE (actor_profile_id);
ALTER TABLE ONLY public.actor_identity_links
    ADD CONSTRAINT uq_actor_identity_links_external_identity UNIQUE (issuer, subject);
ALTER TABLE ONLY public.actor_identity_links
    ADD CONSTRAINT uq_actor_identity_links_id_profile UNIQUE (id, actor_profile_id);
ALTER TABLE ONLY public.artifact_admission_charges
    ADD CONSTRAINT uq_artifact_admission_charge_scope_content UNIQUE (scope_type, scope_id, sha256, byte_count);
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT uq_artifact_binding_scope_version UNIQUE (project_id, resource_type, resource_id, logical_role, scope_version);
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT uq_artifact_binding_supersedes UNIQUE (supersedes_binding_id);
ALTER TABLE ONLY public.artifact_contents
    ADD CONSTRAINT uq_artifact_content_digest_size UNIQUE (sha256, byte_count);
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT uq_artifact_put_attempt_operation UNIQUE (operation_identity);
ALTER TABLE ONLY public.artifact_put_observation_receipts
    ADD CONSTRAINT uq_artifact_put_observation_fence UNIQUE (put_attempt_id, execution_generation);
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT uq_artifact_receipt_put_attempt UNIQUE (put_attempt_id);
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT uq_artifact_recovery_idempotency UNIQUE (requester_actor_profile_id, source_verification_job_id, recovery_class, client_idempotency_key);
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT uq_artifact_recovery_retry_job UNIQUE (retry_verification_job_id);
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT uq_artifact_recovery_source_job UNIQUE (source_verification_job_id);
ALTER TABLE ONLY public.artifact_replicas
    ADD CONSTRAINT uq_artifact_replica_provider_object UNIQUE (storage_namespace_id, provider_object_ref);
ALTER TABLE ONLY public.artifact_replicas
    ADD CONSTRAINT uq_artifact_replicas_id_content UNIQUE (id, content_id);
ALTER TABLE ONLY public.artifact_storage_namespaces
    ADD CONSTRAINT uq_artifact_storage_namespace_fingerprint UNIQUE (namespace_fingerprint);
ALTER TABLE ONLY public.artifact_storage_namespaces
    ADD CONSTRAINT uq_artifact_storage_namespace_id_fingerprint UNIQUE (id, namespace_fingerprint);
ALTER TABLE ONLY public.artifact_verification_receipts
    ADD CONSTRAINT uq_artifact_verification_fence UNIQUE (verification_job_id, execution_generation);
ALTER TABLE ONLY public.artifact_verification_jobs
    ADD CONSTRAINT uq_artifact_verification_parent UNIQUE (parent_verification_job_id);
ALTER TABLE ONLY public.authority_idempotency_records
    ADD CONSTRAINT uq_authority_idempotency_records_actor_reference UNIQUE (id, actor_ref_kind, actor_ref);
ALTER TABLE ONLY public.authority_idempotency_records
    ADD CONSTRAINT uq_authority_idempotency_records_replay_namespace UNIQUE (actor_ref_kind, actor_ref, operation, idempotency_key);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT uq_checker_policies_id_version_hash UNIQUE (id, guide_version, policy_hash);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT uq_checker_policies_scope UNIQUE (id, project_id, guide_id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT uq_checker_runs_submission_attempt UNIQUE (submission_id, attempt_number);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT uq_compensation_binding_ownership UNIQUE (id, project_id, instrument_type);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT uq_compilation_attempt_exact_request UNIQUE (id, project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT uq_compilation_attempt_provider_key UNIQUE (provider_idempotency_key);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT uq_compilation_attempt_setup_generation UNIQUE (setup_run_id, setup_generation);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT uq_compilation_request_actor_key UNIQUE (actor_profile_id, idempotency_key);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT uq_compilation_request_actor_request UNIQUE (actor_profile_id, request_id);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT uq_compilation_request_attempt UNIQUE (attempt_id);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT uq_compilation_request_authorization_event UNIQUE (authorization_decision_event_id);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT uq_contribution_award_definition_instrument UNIQUE (contribution_rule_id, instrument_type);
ALTER TABLE ONLY public.contribution_policy_lifecycle_events
    ADD CONSTRAINT uq_contribution_policy_event_operation UNIQUE (operation_id);
ALTER TABLE ONLY public.contribution_policy_lifecycle_events
    ADD CONSTRAINT uq_contribution_policy_event_publication_custody UNIQUE (publication_custody_operation_id);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT uq_contribution_policy_ownership UNIQUE (id, project_id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT uq_contribution_policy_version_number UNIQUE (contribution_policy_id, version_number);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT uq_contribution_policy_version_ownership UNIQUE (id, contribution_policy_id, project_id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT uq_contribution_policy_version_project UNIQUE (id, project_id);
ALTER TABLE ONLY public.contribution_rules
    ADD CONSTRAINT uq_contribution_rule_ownership UNIQUE (id, contribution_policy_version_id, project_id, contribution_type);
ALTER TABLE ONLY public.contribution_rules
    ADD CONSTRAINT uq_contribution_rule_type UNIQUE (contribution_policy_version_id, contribution_type);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT uq_effective_project_submission_artifact_policies_id_hash UNIQUE (id, effective_policy_hash);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT uq_finalization_compilation UNIQUE (compilation_id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT uq_finalization_decision UNIQUE (authorization_decision_event_id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT uq_finalization_operation UNIQUE (operation_id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT uq_finalization_setup_generation UNIQUE (setup_run_id, setup_generation);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT uq_guide_bindings_exact_read UNIQUE (id, content_id, verified_replica_id, setup_generation);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT uq_guide_bindings_extraction_attempt_lineage UNIQUE (id, content_id, setup_generation);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT uq_guide_bindings_extraction_lineage UNIQUE (id, content_id, source_item_id, project_setup_run_id, setup_generation);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT uq_guide_bindings_item_generation UNIQUE (source_item_id, setup_generation);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT uq_guide_bindings_supersedes UNIQUE (supersedes_binding_id);
ALTER TABLE ONLY public.guide_source_format_classifications
    ADD CONSTRAINT uq_guide_classifications_binding UNIQUE (binding_id);
ALTER TABLE ONLY public.guide_source_format_classifications
    ADD CONSTRAINT uq_guide_classifications_extraction_lineage UNIQUE (id, binding_id, content_id, setup_generation);
ALTER TABLE ONLY public.project_guide_document_accesses
    ADD CONSTRAINT uq_guide_document_access UNIQUE (attempt_id, source_item_id);
ALTER TABLE ONLY public.guide_source_extracted_contents
    ADD CONSTRAINT uq_guide_extracted_contents_exact_usage UNIQUE (id, content_id);
ALTER TABLE ONLY public.guide_source_extracted_contents
    ADD CONSTRAINT uq_guide_extracted_contents_identity UNIQUE (content_id, detected_format, extractor_name, extractor_version, policy_version);
ALTER TABLE ONLY public.guide_source_extraction_attempts
    ADD CONSTRAINT uq_guide_extraction_attempts UNIQUE (binding_id, policy_version, attempt_number);
ALTER TABLE ONLY public.guide_source_extraction_attempts
    ADD CONSTRAINT uq_guide_extraction_attempts_exact_usage UNIQUE (id, binding_id, content_id, setup_generation, status);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT uq_guide_extraction_usages UNIQUE (binding_id, extracted_content_id);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT uq_guide_extraction_usages_exact_provenance UNIQUE (id, source_item_id, binding_id, content_id, extraction_attempt_id, extracted_content_id, project_setup_run_id, setup_generation);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT uq_guide_mutation_operation_identity UNIQUE (operation_id);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT uq_guide_mutation_operation_resource UNIQUE (operation_id, project_id, resource_id);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT uq_guide_mutation_replay_namespace UNIQUE (actor_profile_id, action_id, idempotency_key);
ALTER TABLE ONLY public.project_guide_runtime_allocations
    ADD CONSTRAINT uq_guide_runtime_allocation_slot UNIQUE NULLS NOT DISTINCT (attempt_id, kind, document_handle);
ALTER TABLE ONLY public.guide_source_artifact_ingests
    ADD CONSTRAINT uq_guide_source_artifact_ingests_source_item_id UNIQUE (source_item_id);
ALTER TABLE ONLY public.guide_source_snapshot_items
    ADD CONSTRAINT uq_guide_source_snapshot_items_exact_lineage UNIQUE (id, source_snapshot_id);
ALTER TABLE ONLY public.guide_source_snapshot_items
    ADD CONSTRAINT uq_guide_source_snapshot_items_snapshot_order UNIQUE (source_snapshot_id, item_order);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT uq_guide_source_snapshots_exact_lineage UNIQUE (id, project_id, guide_id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT uq_guide_source_snapshots_id_hash UNIQUE (id, bundle_hash);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT uq_guide_source_snapshots_project_version_hash UNIQUE (project_id, guide_version, bundle_hash);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT uq_guides_project_version_contribution UNIQUE (project_id, version, contribution_policy_version_id);
ALTER TABLE ONLY public.legacy_actor_identities
    ADD CONSTRAINT uq_legacy_actor_identities_external_identity UNIQUE (external_issuer, external_subject);
ALTER TABLE ONLY public.legacy_workflow_eligibility
    ADD CONSTRAINT uq_legacy_workflow_eligibility_actor_type_scope UNIQUE (actor_id, profile_type, scope_type, scope_id);
ALTER TABLE ONLY public.outbox_delivery_attempts
    ADD CONSTRAINT uq_outbox_delivery_attempts_claim_decision_event_id UNIQUE (claim_decision_event_id);
ALTER TABLE ONLY public.outbox_delivery_attempts
    ADD CONSTRAINT uq_outbox_delivery_attempts_finalize_decision_event_id UNIQUE (finalize_decision_event_id);
ALTER TABLE ONLY public.outbox_delivery_attempts
    ADD CONSTRAINT uq_outbox_delivery_attempts_invoke_decision_event_id UNIQUE (invoke_decision_event_id);
ALTER TABLE ONLY public.outbox_events
    ADD CONSTRAINT uq_outbox_events_idempotency_key UNIQUE (idempotency_key);
ALTER TABLE ONLY public.payment_policies
    ADD CONSTRAINT uq_payment_policies_project_version UNIQUE (project_id, guide_version);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT uq_policy_mutation_operation_identity UNIQUE (operation_id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT uq_policy_mutation_replay_namespace UNIQUE (actor_profile_id, action_id, idempotency_key);
ALTER TABLE ONLY public.project_post_policy_operations
    ADD CONSTRAINT uq_post_policy_operation_decision UNIQUE (authorization_decision_event_id);
ALTER TABLE ONLY public.project_post_policy_operations
    ADD CONSTRAINT uq_post_policy_operation_key UNIQUE (actor_profile_id, kind, idempotency_key);
ALTER TABLE ONLY public.project_post_policy_operations
    ADD CONSTRAINT uq_post_policy_operation_kind UNIQUE (policy_id, kind);
ALTER TABLE ONLY public.pre_submit_execution_attempts
    ADD CONSTRAINT uq_pre_submit_attempt_evidence UNIQUE (evidence_set_id);
ALTER TABLE ONLY public.pre_submit_execution_attempts
    ADD CONSTRAINT uq_pre_submit_attempt_key UNIQUE (actor_profile_id, idempotency_key);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT uq_pre_submit_checker_policies_id_compiled_bundle_hash UNIQUE (id, compiled_bundle_hash);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT uq_pre_submit_evidence_operation UNIQUE (operation_identity);
ALTER TABLE ONLY public.pre_submit_evidence_results
    ADD CONSTRAINT uq_pre_submit_result_definition UNIQUE (evidence_set_id, definition_id);
ALTER TABLE ONLY public.pre_submit_evidence_results
    ADD CONSTRAINT uq_pre_submit_result_order UNIQUE (evidence_set_id, result_order);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT uq_project_create_operation_identity UNIQUE (operation_id);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT uq_project_create_project_identity UNIQUE (project_id);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT uq_project_create_replay_namespace UNIQUE (actor_profile_id, action_id, idempotency_key);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT uq_project_guide_compilation_attempt UNIQUE (attempt_id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT uq_project_guide_compilation_id_attempt UNIQUE (id, attempt_id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT uq_project_guide_compilation_predecessor UNIQUE (supersedes_compilation_id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT uq_project_guide_compilation_scope UNIQUE (id, project_id, guide_id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT uq_project_guides_id_project_version UNIQUE (id, project_id, version);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT uq_project_guides_project_version UNIQUE (project_id, version);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT uq_project_setup_runs_exact_generation UNIQUE (id, project_id, guide_id, source_snapshot_id, setup_generation);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT uq_project_setup_runs_guide_generation UNIQUE (guide_id, setup_generation);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT uq_projection_operation_compilation_component UNIQUE (compilation_id, component);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT uq_projection_operation_decision_event UNIQUE (authorization_decision_event_id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT uq_projection_operation_finalization_lineage UNIQUE (operation_id, compilation_id, setup_run_id, setup_generation);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT uq_projection_operation_output UNIQUE (output_id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT uq_projection_operation_setup_component UNIQUE (setup_run_id, setup_generation, component);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT uq_projects_slug UNIQUE (slug);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT uq_proposal_approval_artifact UNIQUE (artifact_policy_id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT uq_proposal_approval_decision UNIQUE (authorization_decision_event_id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT uq_proposal_approval_effective UNIQUE (effective_policy_id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT uq_proposal_approval_finalization UNIQUE (finalization_id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT uq_proposal_approval_pre UNIQUE (pre_submit_policy_id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT uq_proposal_approval_prior UNIQUE (prior_approval_operation_id);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT uq_proposal_correction_decision UNIQUE (authorization_decision_event_id);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT uq_proposal_correction_key UNIQUE (actor_profile_id, idempotency_key);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT uq_proposal_correction_predecessor UNIQUE (finalization_id);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT uq_proposal_correction_successor UNIQUE (successor_setup_run_id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT uq_review_admission_checker_run UNIQUE (admitting_checker_run_id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT uq_review_admission_operation UNIQUE (operation_id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT uq_review_admission_replay_key UNIQUE (idempotency_key);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT uq_review_lease_attempt UNIQUE (review_queue_entry_id, attempt_generation);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT uq_review_lease_queue_identity UNIQUE (review_queue_entry_id, id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT uq_review_policies_project_version_generation UNIQUE (project_id, guide_version, policy_generation);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT uq_review_policy_lineage UNIQUE (id, policy_generation, policy_hash);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT uq_review_policy_scoped_lineage UNIQUE (project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT uq_review_queue_admission_identity UNIQUE (id, project_id, task_id, submission_id, submission_version, admitting_checker_run_id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT uq_review_queue_lease_lineage UNIQUE (id, project_id, task_id, submission_id, submission_version);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT uq_review_queue_submission UNIQUE (submission_id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT uq_revision_policies_project_version_generation UNIQUE (project_id, guide_version, policy_generation);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT uq_revision_policy_lineage UNIQUE (id, policy_generation, policy_hash);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT uq_revision_policy_scoped_lineage UNIQUE (project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT uq_submission_artifact_policies_id_hash UNIQUE (id, policy_hash);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT uq_submission_artifact_policies_project_version_policy UNIQUE (project_id, guide_version, policy_version);
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT uq_submission_bundle_admission_evidence UNIQUE (pre_submit_evidence_set_id);
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT uq_submission_bundle_admission_intent UNIQUE (durable_intent_id);
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT uq_submission_bundle_admission_verification UNIQUE (verification_receipt_id);
ALTER TABLE ONLY public.submission_bundle_durable_intents
    ADD CONSTRAINT uq_submission_bundle_intent_evidence UNIQUE (pre_submit_evidence_set_id);
ALTER TABLE ONLY public.submission_bundle_durable_intents
    ADD CONSTRAINT uq_submission_bundle_intent_put_attempt UNIQUE (put_attempt_id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT uq_submission_policy_operation_identity UNIQUE (operation_id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT uq_submissions_artifact_binding_id UNIQUE (artifact_binding_id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT uq_submissions_id_locked_post_submit_policy_hash UNIQUE (id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT uq_submissions_id_task_version UNIQUE (id, task_id, version);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT uq_submissions_id_version UNIQUE (id, version);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT uq_submissions_task_version UNIQUE (task_id, version);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT uq_sufficiency_mutation_operation_identity UNIQUE (operation_id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT uq_sufficiency_mutation_replay_namespace UNIQUE (actor_profile_id, idempotency_key);
ALTER TABLE ONLY public.guide_sufficiency_report_source_usages
    ADD CONSTRAINT uq_sufficiency_report_extraction_usage UNIQUE (report_id, extraction_usage_id);
ALTER TABLE ONLY public.guide_sufficiency_report_source_usages
    ADD CONSTRAINT uq_sufficiency_report_item_order UNIQUE (report_id, item_order);
ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT uq_task_assignments_id_task_contributor UNIQUE (id, task_id, contributor_id);
ALTER TABLE ONLY public.task_command_receipts
    ADD CONSTRAINT uq_task_command_namespace UNIQUE (actor_profile_id, action_id, idempotency_key);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_effective_policy_hash UNIQUE (id, locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_guide UNIQUE (id, locked_guide_version);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_payment_policy UNIQUE (id, locked_payment_policy_version);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_post_submit_policy_hash UNIQUE (id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_pre_submit_checker_hash UNIQUE (id, locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_review_policy UNIQUE (id, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_revision_policy UNIQUE (id, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_locked_source_snapshot_hash UNIQUE (id, locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT uq_workstream_tasks_id_project UNIQUE (id, project_id);
CREATE INDEX ix_actor_identity_links_issuer_subject_status ON public.actor_identity_links USING btree (issuer, subject, status);
CREATE INDEX ix_actor_profiles_last_seen_at ON public.actor_profiles USING btree (last_seen_at);
CREATE INDEX ix_actor_profiles_status_actor_kind ON public.actor_profiles USING btree (status, actor_kind);
CREATE INDEX ix_admin_role_grants_effective_candidate ON public.admin_role_grants USING btree (target_actor_profile_id, status, scope_type, scope_project_id);
CREATE INDEX ix_admin_role_grants_final_access_admin ON public.admin_role_grants USING btree (role, status) WHERE (((role)::text = 'access_administrator'::text) AND ((status)::text = 'active'::text) AND ((scope_type)::text = 'system'::text));
CREATE INDEX ix_admin_role_grants_history ON public.admin_role_grants USING btree (target_actor_profile_id, granted_at, id);
CREATE INDEX ix_api_rate_control_counters_window_expires_at ON public.api_rate_control_counters USING btree (window_expires_at);
CREATE INDEX ix_artifact_bindings_content_id ON public.artifact_bindings USING btree (content_id);
CREATE INDEX ix_artifact_bindings_project_id ON public.artifact_bindings USING btree (project_id);
CREATE INDEX ix_artifact_bindings_scope ON public.artifact_bindings USING btree (project_id, resource_type, resource_id, logical_role, scope_version DESC);
CREATE INDEX ix_artifact_bindings_supersedes_binding_id ON public.artifact_bindings USING btree (supersedes_binding_id);
CREATE INDEX ix_artifact_contents_sha256 ON public.artifact_contents USING btree (sha256);
CREATE INDEX ix_artifact_operation_receipts_put_attempt_id ON public.artifact_operation_receipts USING btree (put_attempt_id);
CREATE INDEX ix_artifact_operation_receipts_replica_id ON public.artifact_operation_receipts USING btree (replica_id);
CREATE INDEX ix_artifact_put_attempts_checker_run_id ON public.artifact_put_attempts USING btree (checker_run_id);
CREATE INDEX ix_artifact_put_attempts_guide_source_item_id ON public.artifact_put_attempts USING btree (guide_source_item_id);
CREATE INDEX ix_artifact_put_attempts_next_run_at ON public.artifact_put_attempts USING btree (next_run_at);
CREATE INDEX ix_artifact_put_attempts_project_id ON public.artifact_put_attempts USING btree (project_id);
CREATE INDEX ix_artifact_put_attempts_receipt_id ON public.artifact_put_attempts USING btree (receipt_id);
CREATE INDEX ix_artifact_put_attempts_replica_id ON public.artifact_put_attempts USING btree (replica_id);
CREATE INDEX ix_artifact_put_attempts_status ON public.artifact_put_attempts USING btree (status);
CREATE INDEX ix_artifact_put_attempts_task_id ON public.artifact_put_attempts USING btree (task_id);
CREATE INDEX ix_artifact_put_observation_receipts_put_attempt_id ON public.artifact_put_observation_receipts USING btree (put_attempt_id);
CREATE INDEX ix_artifact_recovery_attempts_parent_recovery_attempt_id ON public.artifact_recovery_attempts USING btree (parent_recovery_attempt_id);
CREATE INDEX ix_artifact_recovery_attempts_project_id ON public.artifact_recovery_attempts USING btree (project_id);
CREATE INDEX ix_artifact_recovery_attempts_requester_actor_profile_id ON public.artifact_recovery_attempts USING btree (requester_actor_profile_id);
CREATE INDEX ix_artifact_recovery_attempts_submission_id ON public.artifact_recovery_attempts USING btree (submission_id);
CREATE INDEX ix_artifact_recovery_attempts_task_id ON public.artifact_recovery_attempts USING btree (task_id);
CREATE INDEX ix_artifact_replicas_content_id ON public.artifact_replicas USING btree (content_id);
CREATE INDEX ix_artifact_replicas_storage_namespace_id ON public.artifact_replicas USING btree (storage_namespace_id);
CREATE INDEX ix_artifact_verification_jobs_next_run_at ON public.artifact_verification_jobs USING btree (next_run_at);
CREATE INDEX ix_artifact_verification_jobs_originating_put_attempt_id ON public.artifact_verification_jobs USING btree (originating_put_attempt_id);
CREATE INDEX ix_artifact_verification_jobs_parent_verification_job_id ON public.artifact_verification_jobs USING btree (parent_verification_job_id);
CREATE INDEX ix_artifact_verification_jobs_replica_id ON public.artifact_verification_jobs USING btree (replica_id);
CREATE INDEX ix_artifact_verification_jobs_status ON public.artifact_verification_jobs USING btree (status);
CREATE INDEX ix_artifact_verification_receipts_verification_job_id ON public.artifact_verification_receipts USING btree (verification_job_id);
CREATE INDEX ix_audit_events_actor_id ON public.audit_events USING btree (actor_id);
CREATE INDEX ix_audit_events_actor_ref ON public.audit_events USING btree (actor_ref_kind, actor_id);
CREATE INDEX ix_audit_events_correlation_id ON public.audit_events USING btree (correlation_id);
CREATE INDEX ix_audit_events_entity_id ON public.audit_events USING btree (entity_id);
CREATE INDEX ix_audit_events_entity_type ON public.audit_events USING btree (entity_type);
CREATE INDEX ix_audit_events_event_type ON public.audit_events USING btree (event_type);
CREATE INDEX ix_audit_events_occurred_at ON public.audit_events USING btree (occurred_at);
CREATE INDEX ix_audit_events_project_id ON public.audit_events USING btree (project_id);
CREATE INDEX ix_audit_events_request_id ON public.audit_events USING btree (request_id);
CREATE INDEX ix_checker_policies_effective_policy_hash ON public.checker_policies USING btree (effective_policy_hash);
CREATE INDEX ix_checker_policies_effective_policy_id ON public.checker_policies USING btree (effective_policy_id);
CREATE INDEX ix_checker_policies_guide_id ON public.checker_policies USING btree (guide_id);
CREATE INDEX ix_checker_policies_pre_submit_checker_bundle_hash ON public.checker_policies USING btree (pre_submit_checker_bundle_hash);
CREATE INDEX ix_checker_policies_pre_submit_checker_policy_id ON public.checker_policies USING btree (pre_submit_checker_policy_id);
CREATE INDEX ix_checker_policies_project_id ON public.checker_policies USING btree (project_id);
CREATE INDEX ix_checker_policies_source_snapshot_id ON public.checker_policies USING btree (source_snapshot_id);
CREATE INDEX ix_checker_policies_supersedes_policy_id ON public.checker_policies USING btree (supersedes_policy_id);
CREATE INDEX ix_checker_results_checker_name ON public.checker_results USING btree (checker_name);
CREATE INDEX ix_checker_results_checker_run_id ON public.checker_results USING btree (checker_run_id);
CREATE INDEX ix_checker_results_submission_id ON public.checker_results USING btree (submission_id);
CREATE INDEX ix_checker_results_task_id ON public.checker_results USING btree (task_id);
CREATE INDEX ix_checker_results_worker_visible ON public.checker_results USING btree (worker_visible);
CREATE INDEX ix_checker_runs_audit_event_id ON public.checker_runs USING btree (audit_event_id);
CREATE INDEX ix_checker_runs_locked_post_submit_policy_hash ON public.checker_runs USING btree (locked_post_submit_checker_policy_hash);
CREATE INDEX ix_checker_runs_routing_recommendation ON public.checker_runs USING btree (routing_recommendation);
CREATE INDEX ix_checker_runs_status ON public.checker_runs USING btree (status);
CREATE INDEX ix_checker_runs_submission_id ON public.checker_runs USING btree (submission_id);
CREATE INDEX ix_checker_runs_supersedes_checker_run_id ON public.checker_runs USING btree (supersedes_checker_run_id);
CREATE INDEX ix_checker_runs_task_id ON public.checker_runs USING btree (task_id);
CREATE INDEX ix_compensation_binding_adapter_actor ON public.project_compensation_adapter_bindings USING btree (adapter_actor_id, status, id);
CREATE INDEX ix_compensation_binding_event_binding ON public.compensation_adapter_binding_lifecycle_events USING btree (adapter_binding_id, to_lifecycle_version);
CREATE INDEX ix_effective_psap_effective_hash ON public.effective_project_submission_artifact_policies USING btree (effective_policy_hash);
CREATE INDEX ix_effective_psap_guide ON public.effective_project_submission_artifact_policies USING btree (guide_id);
CREATE INDEX ix_effective_psap_lifecycle ON public.effective_project_submission_artifact_policies USING btree (lifecycle_status);
CREATE INDEX ix_effective_psap_project ON public.effective_project_submission_artifact_policies USING btree (project_id);
CREATE INDEX ix_effective_psap_source_snapshot ON public.effective_project_submission_artifact_policies USING btree (source_snapshot_id);
CREATE INDEX ix_effective_psap_submission_policy ON public.effective_project_submission_artifact_policies USING btree (submission_artifact_policy_id);
CREATE INDEX ix_evidence_items_submission_id ON public.evidence_items USING btree (submission_id);
CREATE INDEX ix_evidence_items_type ON public.evidence_items USING btree (type);
CREATE INDEX ix_guide_source_artifact_bindings_content_id ON public.guide_source_artifact_bindings USING btree (content_id);
CREATE INDEX ix_guide_source_artifact_bindings_guide_id ON public.guide_source_artifact_bindings USING btree (guide_id);
CREATE INDEX ix_guide_source_artifact_bindings_project_id ON public.guide_source_artifact_bindings USING btree (project_id);
CREATE INDEX ix_guide_source_artifact_bindings_project_setup_run_id ON public.guide_source_artifact_bindings USING btree (project_setup_run_id);
CREATE INDEX ix_guide_source_artifact_bindings_source_item_id ON public.guide_source_artifact_bindings USING btree (source_item_id);
CREATE INDEX ix_guide_source_artifact_bindings_source_snapshot_id ON public.guide_source_artifact_bindings USING btree (source_snapshot_id);
CREATE INDEX ix_guide_source_artifact_bindings_supersedes_binding_id ON public.guide_source_artifact_bindings USING btree (supersedes_binding_id);
CREATE INDEX ix_guide_source_artifact_bindings_verified_replica_id ON public.guide_source_artifact_bindings USING btree (verified_replica_id);
CREATE INDEX ix_guide_source_artifact_incidents_binding_id ON public.guide_source_artifact_incidents USING btree (binding_id);
CREATE INDEX ix_guide_source_artifact_incidents_content_id ON public.guide_source_artifact_incidents USING btree (content_id);
CREATE INDEX ix_guide_source_artifact_incidents_verified_replica_id ON public.guide_source_artifact_incidents USING btree (verified_replica_id);
CREATE INDEX ix_guide_source_artifact_ingests_actor_profile_id ON public.guide_source_artifact_ingests USING btree (actor_profile_id);
CREATE UNIQUE INDEX ix_guide_source_artifact_ingests_source_item_id ON public.guide_source_artifact_ingests USING btree (source_item_id);
CREATE INDEX ix_guide_source_extracted_contents_content_id ON public.guide_source_extracted_contents USING btree (content_id);
CREATE INDEX ix_guide_source_extraction_attempts_binding_id ON public.guide_source_extraction_attempts USING btree (binding_id);
CREATE INDEX ix_guide_source_extraction_attempts_content_id ON public.guide_source_extraction_attempts USING btree (content_id);
CREATE INDEX ix_guide_source_extraction_usages_binding_id ON public.guide_source_extraction_usages USING btree (binding_id);
CREATE INDEX ix_guide_source_extraction_usages_content_id ON public.guide_source_extraction_usages USING btree (content_id);
CREATE INDEX ix_guide_source_extraction_usages_extracted_content_id ON public.guide_source_extraction_usages USING btree (extracted_content_id);
CREATE INDEX ix_guide_source_extraction_usages_project_setup_run_id ON public.guide_source_extraction_usages USING btree (project_setup_run_id);
CREATE INDEX ix_guide_source_extraction_usages_source_item_id ON public.guide_source_extraction_usages USING btree (source_item_id);
CREATE INDEX ix_guide_source_format_classifications_binding_id ON public.guide_source_format_classifications USING btree (binding_id);
CREATE INDEX ix_guide_source_format_classifications_content_id ON public.guide_source_format_classifications USING btree (content_id);
CREATE INDEX ix_guide_source_format_classifications_verified_replica_id ON public.guide_source_format_classifications USING btree (verified_replica_id);
CREATE INDEX ix_guide_source_snapshot_items_source_snapshot_id ON public.guide_source_snapshot_items USING btree (source_snapshot_id);
CREATE INDEX ix_guide_source_snapshots_bundle_hash ON public.guide_source_snapshots USING btree (bundle_hash);
CREATE INDEX ix_guide_source_snapshots_guide_id ON public.guide_source_snapshots USING btree (guide_id);
CREATE INDEX ix_guide_source_snapshots_project_id ON public.guide_source_snapshots USING btree (project_id);
CREATE INDEX ix_guide_sufficiency_reports_guide_id ON public.guide_sufficiency_reports USING btree (guide_id);
CREATE INDEX ix_guide_sufficiency_reports_project_id ON public.guide_sufficiency_reports USING btree (project_id);
CREATE INDEX ix_guide_sufficiency_reports_project_setup_run_id ON public.guide_sufficiency_reports USING btree (project_setup_run_id);
CREATE INDEX ix_guide_sufficiency_reports_source_snapshot_id ON public.guide_sufficiency_reports USING btree (source_snapshot_id);
CREATE INDEX ix_guide_sufficiency_reports_status ON public.guide_sufficiency_reports USING btree (status);
CREATE INDEX ix_legacy_workflow_eligibility_actor_id ON public.legacy_workflow_eligibility USING btree (actor_id);
CREATE INDEX ix_legacy_workflow_eligibility_profile_type ON public.legacy_workflow_eligibility USING btree (profile_type);
CREATE INDEX ix_legacy_workflow_eligibility_status ON public.legacy_workflow_eligibility USING btree (status);
CREATE INDEX ix_outbox_events_aggregate ON public.outbox_events USING btree (aggregate_type, aggregate_id, occurred_at, event_id);
CREATE INDEX ix_outbox_events_eligible ON public.outbox_events USING btree (event_type, delivery_state, next_attempt_at, occurred_at, event_id) WHERE ((delivery_state)::text = ANY (ARRAY[('pending'::character varying)::text, ('retryable'::character varying)::text]));
CREATE INDEX ix_outbox_events_expired_claims ON public.outbox_events USING btree (claim_expires_at, event_id) WHERE ((delivery_state)::text = 'claimed'::text);
CREATE INDEX ix_outbox_events_project_drain ON public.outbox_events USING btree (project_id, delivery_state, occurred_at, event_id);
CREATE INDEX ix_outbox_events_retention ON public.outbox_events USING btree (finalized_at, event_id) WHERE (((delivery_state)::text = ANY (ARRAY[('acknowledged'::character varying)::text, ('dead_letter'::character varying)::text, ('cancelled'::character varying)::text])) AND (archived_at IS NULL));
CREATE INDEX ix_payment_policies_project_id ON public.payment_policies USING btree (project_id);
CREATE INDEX ix_policy_mutation_custody_lookup ON public.policy_mutation_idempotency_records USING btree (policy_id, action_id, policy_generation, status);
CREATE INDEX ix_pre_submit_checker_compiled_hash ON public.pre_submit_checker_policies USING btree (compiled_bundle_hash);
CREATE INDEX ix_pre_submit_checker_effective ON public.pre_submit_checker_policies USING btree (effective_policy_id);
CREATE INDEX ix_pre_submit_checker_effective_hash ON public.pre_submit_checker_policies USING btree (effective_policy_hash);
CREATE INDEX ix_pre_submit_checker_guide ON public.pre_submit_checker_policies USING btree (guide_id);
CREATE INDEX ix_pre_submit_checker_lifecycle ON public.pre_submit_checker_policies USING btree (lifecycle_status);
CREATE INDEX ix_pre_submit_checker_project ON public.pre_submit_checker_policies USING btree (project_id);
CREATE INDEX ix_pre_submit_checker_source_snapshot ON public.pre_submit_checker_policies USING btree (source_snapshot_id);
CREATE INDEX ix_pre_submit_evidence_results_evidence_set_id ON public.pre_submit_evidence_results USING btree (evidence_set_id);
CREATE INDEX ix_pre_submit_evidence_sets_actor_profile_id ON public.pre_submit_evidence_sets USING btree (actor_profile_id);
CREATE INDEX ix_pre_submit_evidence_sets_project_id ON public.pre_submit_evidence_sets USING btree (project_id);
CREATE INDEX ix_pre_submit_evidence_sets_task_id ON public.pre_submit_evidence_sets USING btree (task_id);
CREATE INDEX ix_project_guide_compilation_attempts_guide_id ON public.project_guide_compilation_attempts USING btree (guide_id);
CREATE INDEX ix_project_guide_compilation_attempts_project_id ON public.project_guide_compilation_attempts USING btree (project_id);
CREATE INDEX ix_project_guide_compilation_attempts_setup_run_id ON public.project_guide_compilation_attempts USING btree (setup_run_id);
CREATE INDEX ix_project_guide_compilation_attempts_source_snapshot_id ON public.project_guide_compilation_attempts USING btree (source_snapshot_id);
CREATE INDEX ix_project_guide_compilations_guide_id ON public.project_guide_compilations USING btree (guide_id);
CREATE INDEX ix_project_guide_compilations_project_id ON public.project_guide_compilations USING btree (project_id);
CREATE INDEX ix_project_guide_compilations_setup_run_id ON public.project_guide_compilations USING btree (setup_run_id);
CREATE INDEX ix_project_guide_compilations_source_snapshot_id ON public.project_guide_compilations USING btree (source_snapshot_id);
CREATE INDEX ix_project_guide_document_accesses_attempt_id ON public.project_guide_document_accesses USING btree (attempt_id);
CREATE INDEX ix_project_guide_runtime_allocations_attempt_id ON public.project_guide_runtime_allocations USING btree (attempt_id);
CREATE INDEX ix_project_guides_project_id ON public.project_guides USING btree (project_id);
CREATE INDEX ix_project_guides_status ON public.project_guides USING btree (status);
CREATE INDEX ix_project_role_grants_actor_role_status ON public.project_role_grants USING btree (actor_profile_id, role, status);
CREATE INDEX ix_project_role_grants_project_actor_role_status ON public.project_role_grants USING btree (project_id, actor_profile_id, role, status);
CREATE INDEX ix_project_role_qualification_snapshots_history ON public.project_role_qualification_snapshots USING btree (project_id, actor_profile_id, requested_role, captured_at);
CREATE INDEX ix_project_setup_runs_celery_task_id ON public.project_setup_runs USING btree (celery_task_id);
CREATE INDEX ix_project_setup_runs_error_artifact_incident_id ON public.project_setup_runs USING btree (error_artifact_incident_id);
CREATE INDEX ix_project_setup_runs_guide_id ON public.project_setup_runs USING btree (guide_id);
CREATE INDEX ix_project_setup_runs_output_post_submit_checker_policy_id ON public.project_setup_runs USING btree (output_post_submit_checker_policy_id);
CREATE INDEX ix_project_setup_runs_output_submission_artifact_policy_id ON public.project_setup_runs USING btree (output_submission_artifact_policy_id);
CREATE INDEX ix_project_setup_runs_output_sufficiency_report_id ON public.project_setup_runs USING btree (output_sufficiency_report_id);
CREATE INDEX ix_project_setup_runs_project_id ON public.project_setup_runs USING btree (project_id);
CREATE INDEX ix_project_setup_runs_retained_continuation_verification_job_id ON public.project_setup_runs USING btree (retained_continuation_verification_job_id);
CREATE INDEX ix_project_setup_runs_source_snapshot_id ON public.project_setup_runs USING btree (source_snapshot_id);
CREATE INDEX ix_project_setup_runs_status ON public.project_setup_runs USING btree (status);
CREATE INDEX ix_projects_slug ON public.projects USING btree (slug);
CREATE INDEX ix_projects_status ON public.projects USING btree (status);
CREATE INDEX ix_review_admission_submission ON public.review_admission_idempotency_records USING btree (submission_id, status, created_at, id);
CREATE INDEX ix_review_lease_expiry ON public.review_leases USING btree (status, expires_at, id);
CREATE INDEX ix_review_policies_project_id ON public.review_policies USING btree (project_id);
CREATE INDEX ix_review_queue_preference ON public.review_queue_entries USING btree (preferred_reviewer_id, queue_state, preference_expires_at, id);
CREATE INDEX ix_review_queue_selection ON public.review_queue_entries USING btree (project_id, queue_state, routing_mode, first_queued_at, id);
CREATE INDEX ix_revision_policies_project_id ON public.revision_policies USING btree (project_id);
CREATE INDEX ix_submission_artifact_policies_guide_id ON public.submission_artifact_policies USING btree (guide_id);
CREATE INDEX ix_submission_artifact_policies_lifecycle_status ON public.submission_artifact_policies USING btree (lifecycle_status);
CREATE INDEX ix_submission_artifact_policies_policy_hash ON public.submission_artifact_policies USING btree (policy_hash);
CREATE INDEX ix_submission_artifact_policies_project_id ON public.submission_artifact_policies USING btree (project_id);
CREATE INDEX ix_submission_artifact_policies_source_snapshot_id ON public.submission_artifact_policies USING btree (source_snapshot_id);
CREATE INDEX ix_submission_bundle_admissions_actor_profile_id ON public.submission_bundle_admissions USING btree (actor_profile_id);
CREATE INDEX ix_submission_bundle_admissions_artifact_content_id ON public.submission_bundle_admissions USING btree (artifact_content_id);
CREATE INDEX ix_submission_bundle_admissions_pre_submit_evidence_set_id ON public.submission_bundle_admissions USING btree (pre_submit_evidence_set_id);
CREATE INDEX ix_submission_bundle_admissions_project_id ON public.submission_bundle_admissions USING btree (project_id);
CREATE INDEX ix_submission_bundle_admissions_status ON public.submission_bundle_admissions USING btree (status);
CREATE INDEX ix_submission_bundle_admissions_task_id ON public.submission_bundle_admissions USING btree (task_id);
CREATE INDEX ix_submission_bundle_durable_intents_pre_submit_evidence_set_id ON public.submission_bundle_durable_intents USING btree (pre_submit_evidence_set_id);
CREATE INDEX ix_submission_bundle_durable_intents_put_attempt_id ON public.submission_bundle_durable_intents USING btree (put_attempt_id);
CREATE INDEX ix_submissions_artifact_content_id ON public.submissions USING btree (artifact_content_id);
CREATE INDEX ix_submissions_contributor_id ON public.submissions USING btree (contributor_id);
CREATE INDEX ix_submissions_locked_effective_policy_hash ON public.submissions USING btree (locked_effective_project_submission_artifact_policy_hash);
CREATE INDEX ix_submissions_locked_post_submit_policy_hash ON public.submissions USING btree (locked_post_submit_checker_policy_hash);
CREATE INDEX ix_submissions_locked_pre_submit_checker_hash ON public.submissions USING btree (locked_pre_submit_checker_bundle_hash);
CREATE INDEX ix_submissions_locked_source_snapshot ON public.submissions USING btree (locked_guide_source_snapshot_id);
CREATE INDEX ix_submissions_status ON public.submissions USING btree (status);
CREATE UNIQUE INDEX ix_submissions_submission_bundle_admission_id ON public.submissions USING btree (submission_bundle_admission_id);
CREATE INDEX ix_submissions_supersedes_submission_id ON public.submissions USING btree (supersedes_submission_id);
CREATE INDEX ix_submissions_task_assignment_id ON public.submissions USING btree (task_assignment_id);
CREATE INDEX ix_submissions_task_id ON public.submissions USING btree (task_id);
CREATE INDEX ix_sufficiency_report_source_usage_report_id ON public.guide_sufficiency_report_source_usages USING btree (report_id);
CREATE INDEX ix_task_assignments_contributor_id ON public.task_assignments USING btree (contributor_id);
CREATE INDEX ix_task_assignments_status ON public.task_assignments USING btree (status);
CREATE INDEX ix_task_assignments_task_id ON public.task_assignments USING btree (task_id);
CREATE INDEX ix_workstream_tasks_assigned_to ON public.workstream_tasks USING btree (assigned_to);
CREATE INDEX ix_workstream_tasks_locked_effective_policy_hash ON public.workstream_tasks USING btree (locked_effective_project_submission_artifact_policy_hash);
CREATE INDEX ix_workstream_tasks_locked_post_submit_policy_hash ON public.workstream_tasks USING btree (locked_post_submit_checker_policy_hash);
CREATE INDEX ix_workstream_tasks_locked_pre_submit_checker_hash ON public.workstream_tasks USING btree (locked_pre_submit_checker_bundle_hash);
CREATE INDEX ix_workstream_tasks_locked_source_snapshot ON public.workstream_tasks USING btree (locked_guide_source_snapshot_id);
CREATE INDEX ix_workstream_tasks_project_id ON public.workstream_tasks USING btree (project_id);
CREATE INDEX ix_workstream_tasks_status ON public.workstream_tasks USING btree (status);
CREATE UNIQUE INDEX uq_admin_role_grants_active_project ON public.admin_role_grants USING btree (target_actor_profile_id, role, scope_project_id) WHERE (((status)::text = 'active'::text) AND ((scope_type)::text = 'project'::text));
CREATE UNIQUE INDEX uq_admin_role_grants_active_system ON public.admin_role_grants USING btree (target_actor_profile_id, role) WHERE (((status)::text = 'active'::text) AND ((scope_type)::text = 'system'::text));
CREATE UNIQUE INDEX uq_artifact_verification_initial_origin ON public.artifact_verification_jobs USING btree (originating_put_attempt_id) WHERE (parent_verification_job_id IS NULL);
CREATE UNIQUE INDEX uq_checker_policies_current_project_version ON public.checker_policies USING btree (project_id, guide_version) WHERE ((lifecycle_status)::text = ANY (ARRAY[('compiled'::character varying)::text, ('approved'::character varying)::text]));
CREATE UNIQUE INDEX uq_checker_runs_current_per_submission ON public.checker_runs USING btree (submission_id) WHERE (is_current_for_submission = true);
CREATE UNIQUE INDEX uq_compensation_binding_active_project_instrument ON public.project_compensation_adapter_bindings USING btree (project_id, instrument_type) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_contribution_policy_active_project ON public.contribution_policies USING btree (project_id) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_guide_activation_audit_decision ON public.guide_mutation_idempotency_records USING btree (((activation_authority_json ->> 'authorization_decision_event_id'::text))) WHERE ((action_id)::text = 'project.guide.activate'::text);
CREATE UNIQUE INDEX uq_guide_sufficiency_reports_diagnostic_snapshot ON public.guide_sufficiency_reports USING btree (source_snapshot_id) WHERE (project_setup_run_id IS NULL);
CREATE UNIQUE INDEX uq_guide_sufficiency_reports_verified_snapshot ON public.guide_sufficiency_reports USING btree (source_snapshot_id, setup_generation) WHERE (project_setup_run_id IS NOT NULL);
CREATE UNIQUE INDEX uq_post_policy_chain_root ON public.checker_policies USING btree (guide_id) WHERE ((projection_operation_id IS NOT NULL) AND (supersedes_policy_id IS NULL));
CREATE UNIQUE INDEX uq_post_policy_chain_successor ON public.checker_policies USING btree (supersedes_policy_id) WHERE (projection_operation_id IS NOT NULL);
CREATE UNIQUE INDEX uq_post_policy_projection_upstream ON public.project_post_policy_operations USING btree (upstream_approval_operation_id) WHERE ((kind)::text = 'derive'::text);
CREATE UNIQUE INDEX uq_project_guide_compilation_root ON public.project_guide_compilations USING btree (project_id, guide_id) WHERE (supersedes_compilation_id IS NULL);
CREATE UNIQUE INDEX uq_project_guides_one_active_per_project ON public.project_guides USING btree (project_id) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_project_role_grants_active_exact_role ON public.project_role_grants USING btree (project_id, actor_profile_id, role) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_proposal_approval_root_guide ON public.project_guide_proposal_approvals USING btree (guide_id) WHERE (prior_approval_operation_id IS NULL);
CREATE UNIQUE INDEX uq_review_lease_active_queue ON public.review_leases USING btree (review_queue_entry_id) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_review_lease_active_reviewer ON public.review_leases USING btree (reviewer_id) WHERE ((status)::text = 'active'::text);
CREATE UNIQUE INDEX uq_submission_bundle_admission_consumer ON public.submission_bundle_admissions USING btree (consumed_by_submission_id) WHERE (consumed_by_submission_id IS NOT NULL);
CREATE UNIQUE INDEX uq_submission_policy_committed_policy_action ON public.submission_policy_mutation_idempotency_records USING btree (committed_policy_id, action_id) WHERE ((status)::text = 'committed'::text);
CREATE UNIQUE INDEX uq_submission_policy_human_replay_namespace ON public.submission_policy_mutation_idempotency_records USING btree (actor_profile_id, idempotency_key) WHERE (service_identity IS NULL);
CREATE UNIQUE INDEX uq_submission_policy_service_replay_namespace ON public.submission_policy_mutation_idempotency_records USING btree (actor_profile_id, setup_run_id, setup_generation, setup_task_id, correlation_id, action_id) WHERE (service_identity IS NOT NULL);
CREATE UNIQUE INDEX uq_task_assignments_one_active_per_task ON public.task_assignments USING btree (task_id) WHERE ((status)::text = 'active'::text);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT checker_policies_approval_operation_id_fkey FOREIGN KEY (approval_operation_id) REFERENCES public.project_post_policy_operations(operation_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT checker_policies_projection_operation_id_fkey FOREIGN KEY (projection_operation_id) REFERENCES public.project_post_policy_operations(operation_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT checker_policies_supersession_operation_id_fkey FOREIGN KEY (supersession_operation_id) REFERENCES public.project_post_policy_operations(operation_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.actor_identity_links
    ADD CONSTRAINT fk_actor_identity_links_actor_profile_id_actor_profiles FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_granted_by_actor_profile_id_actor_profiles FOREIGN KEY (granted_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_granted_by_admin_role_grant_id_adm_81e0 FOREIGN KEY (granted_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_revoked_by_actor_profile_id_actor_profiles FOREIGN KEY (revoked_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_revoked_by_admin_role_grant_id_adm_78b5 FOREIGN KEY (revoked_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_scope_project_id_projects FOREIGN KEY (scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.admin_role_grants
    ADD CONSTRAINT fk_admin_role_grants_target_actor_profile_id_actor_profiles FOREIGN KEY (target_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.artifact_admission_charges
    ADD CONSTRAINT fk_artifact_admission_charges_scope FOREIGN KEY (scope_type, scope_id) REFERENCES public.artifact_admission_scopes(scope_type, scope_id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT fk_artifact_bindings_content_id_artifact_contents FOREIGN KEY (content_id) REFERENCES public.artifact_contents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT fk_artifact_bindings_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_bindings
    ADD CONSTRAINT fk_artifact_bindings_supersedes_binding_id_artifact_bindings FOREIGN KEY (supersedes_binding_id) REFERENCES public.artifact_bindings(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT fk_artifact_operation_receipts_replica_id_artifact_replicas FOREIGN KEY (replica_id) REFERENCES public.artifact_replicas(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempt_charges
    ADD CONSTRAINT fk_artifact_put_attempt_charges_attempt_id_artifact_put_b25d FOREIGN KEY (attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempt_charges
    ADD CONSTRAINT fk_artifact_put_attempt_charges_charge_id_artifact_admi_85a9 FOREIGN KEY (charge_id) REFERENCES public.artifact_admission_charges(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_checker_run_id_checker_runs FOREIGN KEY (checker_run_id) REFERENCES public.checker_runs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_guide_source_item_id_guide_sou_e48c FOREIGN KEY (guide_source_item_id) REFERENCES public.guide_source_snapshot_items(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_namespace_fingerprint FOREIGN KEY (storage_namespace_id, namespace_fingerprint) REFERENCES public.artifact_storage_namespaces(id, namespace_fingerprint) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_receipt_id_artifact_operation_receipts FOREIGN KEY (receipt_id) REFERENCES public.artifact_operation_receipts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_replica_id_artifact_replicas FOREIGN KEY (replica_id) REFERENCES public.artifact_replicas(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_attempts
    ADD CONSTRAINT fk_artifact_put_attempts_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_put_observation_receipts
    ADD CONSTRAINT fk_artifact_put_observation_receipts_put_attempt_id_art_237d FOREIGN KEY (put_attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT fk_artifact_receipt_checker_run FOREIGN KEY (checker_run_id) REFERENCES public.checker_runs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT fk_artifact_receipt_guide_item FOREIGN KEY (guide_source_item_id) REFERENCES public.guide_source_snapshot_items(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_operation_receipts
    ADD CONSTRAINT fk_artifact_receipt_put_attempt FOREIGN KEY (put_attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_initiation_audit_event_id_2af7 FOREIGN KEY (initiation_audit_event_id) REFERENCES public.audit_events(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_parent_recovery_attempt_i_130d FOREIGN KEY (parent_recovery_attempt_id) REFERENCES public.artifact_recovery_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_requester_actor_profile_i_77f5 FOREIGN KEY (requester_actor_profile_id) REFERENCES public.actor_profiles(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_requester_identity_link_i_3619 FOREIGN KEY (requester_identity_link_id) REFERENCES public.actor_identity_links(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_retry_verification_job_id_b330 FOREIGN KEY (retry_verification_job_id) REFERENCES public.artifact_verification_jobs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_source_verification_job_i_5eac FOREIGN KEY (source_verification_job_id) REFERENCES public.artifact_verification_jobs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_submission_id_submissions FOREIGN KEY (submission_id) REFERENCES public.submissions(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_recovery_attempts
    ADD CONSTRAINT fk_artifact_recovery_attempts_terminal_audit_event_id_a_47ab FOREIGN KEY (terminal_audit_event_id) REFERENCES public.audit_events(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_replicas
    ADD CONSTRAINT fk_artifact_replicas_content_id_artifact_contents FOREIGN KEY (content_id) REFERENCES public.artifact_contents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_replicas
    ADD CONSTRAINT fk_artifact_replicas_storage_namespace_id_artifact_stor_d6cc FOREIGN KEY (storage_namespace_id) REFERENCES public.artifact_storage_namespaces(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_verification_jobs
    ADD CONSTRAINT fk_artifact_verification_jobs_originating_put_attempt_i_3260 FOREIGN KEY (originating_put_attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_verification_jobs
    ADD CONSTRAINT fk_artifact_verification_jobs_replica_id_artifact_replicas FOREIGN KEY (replica_id) REFERENCES public.artifact_replicas(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_verification_jobs
    ADD CONSTRAINT fk_artifact_verification_parent FOREIGN KEY (parent_verification_job_id) REFERENCES public.artifact_verification_jobs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.artifact_verification_receipts
    ADD CONSTRAINT fk_artifact_verification_receipts_verification_job_id_a_dabf FOREIGN KEY (verification_job_id) REFERENCES public.artifact_verification_jobs(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT fk_assignments_contribution_project FOREIGN KEY (submitter_contribution_policy_version_id, project_id) REFERENCES public.contribution_policy_versions(id, project_id);
ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT fk_assignments_task_project FOREIGN KEY (task_id, project_id) REFERENCES public.workstream_tasks(id, project_id);
ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT fk_audit_events_authority_idempotency FOREIGN KEY (idempotency_reference, actor_ref_kind, actor_id) REFERENCES public.authority_idempotency_records(id, actor_ref_kind, actor_ref) NOT VALID;
ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT fk_audit_events_invalidation_cause FOREIGN KEY (invalidation_cause_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.authority_control
    ADD CONSTRAINT fk_authority_control_bootstrap_grant_id_admin_role_grants FOREIGN KEY (bootstrap_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_effective_policy_hash FOREIGN KEY (effective_policy_id, effective_policy_hash) REFERENCES public.effective_project_submission_artifact_policies(id, effective_policy_hash);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_pre_submit_checker_hash FOREIGN KEY (pre_submit_checker_policy_id, pre_submit_checker_bundle_hash) REFERENCES public.pre_submit_checker_policies(id, compiled_bundle_hash);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.checker_policies
    ADD CONSTRAINT fk_checker_policies_supersedes_policy_id FOREIGN KEY (supersedes_policy_id) REFERENCES public.checker_policies(id);
ALTER TABLE ONLY public.checker_results
    ADD CONSTRAINT fk_checker_results_checker_run_id_checker_runs FOREIGN KEY (checker_run_id) REFERENCES public.checker_runs(id);
ALTER TABLE ONLY public.checker_results
    ADD CONSTRAINT fk_checker_results_submission_id_submissions FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.checker_results
    ADD CONSTRAINT fk_checker_results_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_audit_event_id_audit_events FOREIGN KEY (audit_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_locked_post_submit_policy_hash FOREIGN KEY (locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash) REFERENCES public.checker_policies(id, guide_version, policy_hash);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_submission_id_submissions FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_submission_locked_post_submit_policy_hash FOREIGN KEY (submission_id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash) REFERENCES public.submissions(id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_submission_version FOREIGN KEY (submission_id, task_id, submission_version) REFERENCES public.submissions(id, task_id, version);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_supersedes_checker_run_id_checker_runs FOREIGN KEY (supersedes_checker_run_id) REFERENCES public.checker_runs(id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_task_locked_guide FOREIGN KEY (task_id, locked_guide_version) REFERENCES public.workstream_tasks(id, locked_guide_version);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_task_locked_payment_policy FOREIGN KEY (task_id, locked_payment_policy_version) REFERENCES public.workstream_tasks(id, locked_payment_policy_version);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_task_locked_review_policy FOREIGN KEY (task_id, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash) REFERENCES public.workstream_tasks(id, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash);
ALTER TABLE ONLY public.checker_runs
    ADD CONSTRAINT fk_checker_runs_task_locked_revision_policy FOREIGN KEY (task_id, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash) REFERENCES public.workstream_tasks(id, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT fk_compensation_binding_adapter_actor FOREIGN KEY (adapter_actor_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT fk_compensation_binding_created_by FOREIGN KEY (created_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.compensation_adapter_binding_lifecycle_events
    ADD CONSTRAINT fk_compensation_binding_event_actor FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.compensation_adapter_binding_lifecycle_events
    ADD CONSTRAINT fk_compensation_binding_event_binding FOREIGN KEY (adapter_binding_id) REFERENCES public.project_compensation_adapter_bindings(id);
ALTER TABLE ONLY public.compensation_adapter_binding_lifecycle_events
    ADD CONSTRAINT fk_compensation_binding_event_prior_suspension FOREIGN KEY (prior_suspension_event_id) REFERENCES public.compensation_adapter_binding_lifecycle_events(id);
ALTER TABLE ONLY public.compensation_adapter_binding_lifecycle_events
    ADD CONSTRAINT fk_compensation_binding_event_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT fk_compensation_binding_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT fk_compensation_binding_resumed_by FOREIGN KEY (resumed_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT fk_compensation_binding_retired_by FOREIGN KEY (retired_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_compensation_adapter_bindings
    ADD CONSTRAINT fk_compensation_binding_suspended_by FOREIGN KEY (suspended_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT fk_compilation_attempt_exact_persisted_compilation FOREIGN KEY (persisted_compilation_id, id) REFERENCES public.project_guide_compilations(id, attempt_id);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT fk_compilation_attempt_exact_setup FOREIGN KEY (setup_run_id, project_id, guide_id, source_snapshot_id, setup_generation) REFERENCES public.project_setup_runs(id, project_id, guide_id, source_snapshot_id, setup_generation);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT fk_compilation_attempt_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT fk_compilation_request_actor FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT fk_compilation_request_actor_link FOREIGN KEY (identity_link_id, actor_profile_id) REFERENCES public.actor_identity_links(id, actor_profile_id);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT fk_compilation_request_authorization_event FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT fk_compilation_request_exact_attempt FOREIGN KEY (attempt_id, project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation) REFERENCES public.project_guide_compilation_attempts(id, project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT fk_compilation_request_guide FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT fk_compilation_request_predecessor FOREIGN KEY (expected_predecessor_compilation_id, project_id, guide_id) REFERENCES public.project_guide_compilations(id, project_id, guide_id);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT fk_compilation_request_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT fk_compilation_request_setup FOREIGN KEY (setup_run_id, project_id, guide_id, source_snapshot_id, setup_generation) REFERENCES public.project_setup_runs(id, project_id, guide_id, source_snapshot_id, setup_generation);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT fk_compilation_request_snapshot FOREIGN KEY (source_snapshot_id, project_id, guide_id) REFERENCES public.guide_source_snapshots(id, project_id, guide_id);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT fk_compilation_request_source_event FOREIGN KEY (source_authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_guide_compilation_request_operations
    ADD CONSTRAINT fk_compilation_request_source_operation FOREIGN KEY (source_mutation_operation_id) REFERENCES public.guide_mutation_idempotency_records(operation_id);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT fk_contribution_award_definition_binding FOREIGN KEY (adapter_binding_id, project_id, instrument_type) REFERENCES public.project_compensation_adapter_bindings(id, project_id, instrument_type);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT fk_contribution_award_definition_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT fk_contribution_award_definition_rule FOREIGN KEY (contribution_rule_id, contribution_policy_version_id, project_id, contribution_type) REFERENCES public.contribution_rules(id, contribution_policy_version_id, project_id, contribution_type);
ALTER TABLE ONLY public.contribution_award_definitions
    ADD CONSTRAINT fk_contribution_award_definition_unit FOREIGN KEY (project_id, instrument_type, unit_code) REFERENCES public.project_compensation_units(project_id, instrument_type, unit_code);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT fk_contribution_policy_created_by FOREIGN KEY (created_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT fk_contribution_policy_current_version FOREIGN KEY (current_published_version_id, id, project_id) REFERENCES public.contribution_policy_versions(id, contribution_policy_id, project_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.contribution_policy_transition_custody
    ADD CONSTRAINT fk_contribution_policy_custody_actor FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_policy_transition_custody
    ADD CONSTRAINT fk_contribution_policy_custody_policy FOREIGN KEY (contribution_policy_id, project_id) REFERENCES public.contribution_policies(id, project_id);
ALTER TABLE ONLY public.contribution_policy_transition_custody
    ADD CONSTRAINT fk_contribution_policy_custody_prior_version FOREIGN KEY (prior_current_version_id, contribution_policy_id, project_id) REFERENCES public.contribution_policy_versions(id, contribution_policy_id, project_id);
ALTER TABLE ONLY public.contribution_policy_transition_custody
    ADD CONSTRAINT fk_contribution_policy_custody_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.contribution_policy_transition_custody
    ADD CONSTRAINT fk_contribution_policy_custody_version FOREIGN KEY (contribution_policy_version_id, contribution_policy_id, project_id) REFERENCES public.contribution_policy_versions(id, contribution_policy_id, project_id);
ALTER TABLE ONLY public.contribution_policy_lifecycle_events
    ADD CONSTRAINT fk_contribution_policy_event_actor FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_policy_lifecycle_events
    ADD CONSTRAINT fk_contribution_policy_event_policy_ownership FOREIGN KEY (contribution_policy_id, project_id) REFERENCES public.contribution_policies(id, project_id);
ALTER TABLE ONLY public.contribution_policy_lifecycle_events
    ADD CONSTRAINT fk_contribution_policy_event_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.contribution_policy_lifecycle_events
    ADD CONSTRAINT fk_contribution_policy_event_publication_custody FOREIGN KEY (publication_custody_operation_id) REFERENCES public.contribution_policy_transition_custody(operation_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.contribution_policy_lifecycle_events
    ADD CONSTRAINT fk_contribution_policy_event_version_ownership FOREIGN KEY (contribution_policy_version_id, contribution_policy_id, project_id) REFERENCES public.contribution_policy_versions(id, contribution_policy_id, project_id);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT fk_contribution_policy_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT fk_contribution_policy_retired_by FOREIGN KEY (retired_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_policies
    ADD CONSTRAINT fk_contribution_policy_transition_custody FOREIGN KEY (last_transition_operation_id) REFERENCES public.contribution_policy_transition_custody(operation_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_created_by FOREIGN KEY (created_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_policy FOREIGN KEY (contribution_policy_id, project_id) REFERENCES public.contribution_policies(id, project_id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_published_by FOREIGN KEY (published_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_retired_by FOREIGN KEY (retired_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_transition_custody FOREIGN KEY (last_transition_operation_id) REFERENCES public.contribution_policy_transition_custody(operation_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.contribution_policy_versions
    ADD CONSTRAINT fk_contribution_policy_version_updated_by FOREIGN KEY (last_updated_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.contribution_rules
    ADD CONSTRAINT fk_contribution_rule_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.contribution_rules
    ADD CONSTRAINT fk_contribution_rule_version FOREIGN KEY (contribution_policy_version_id, project_id) REFERENCES public.contribution_policy_versions(id, project_id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_policy_creation_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_policy_creation_decision FOREIGN KEY (creation_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_policy_creation_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_policy_creation_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_policy_creation_project FOREIGN KEY (creation_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_project_submission_artifact_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_psap_guide FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_psap_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_psap_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_psap_submission_policy_hash FOREIGN KEY (submission_artifact_policy_id, submission_artifact_policy_hash) REFERENCES public.submission_artifact_policies(id, policy_hash);
ALTER TABLE ONLY public.effective_project_submission_artifact_policies
    ADD CONSTRAINT fk_effective_psap_supersedes FOREIGN KEY (supersedes_effective_policy_id) REFERENCES public.effective_project_submission_artifact_policies(id);
ALTER TABLE ONLY public.evidence_items
    ADD CONSTRAINT fk_evidence_items_submission_id_submissions FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_finalization_actor_link FOREIGN KEY (identity_link_id, actor_profile_id) REFERENCES public.actor_identity_links(id, actor_profile_id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_finalization_compilation_attempt FOREIGN KEY (compilation_id, attempt_id) REFERENCES public.project_guide_compilations(id, attempt_id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_finalization_exact_attempt FOREIGN KEY (attempt_id, project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation) REFERENCES public.project_guide_compilation_attempts(id, project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_finalization_exact_setup FOREIGN KEY (setup_run_id, project_id, guide_id, source_snapshot_id, setup_generation) REFERENCES public.project_setup_runs(id, project_id, guide_id, source_snapshot_id, setup_generation);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_finalization_policy_lineage FOREIGN KEY (artifact_policy_operation_id, compilation_id, setup_run_id, setup_generation) REFERENCES public.project_guide_component_projection_operations(operation_id, compilation_id, setup_run_id, setup_generation);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_finalization_sufficiency_lineage FOREIGN KEY (sufficiency_operation_id, compilation_id, setup_run_id, setup_generation) REFERENCES public.project_guide_component_projection_operations(operation_id, compilation_id, setup_run_id, setup_generation);
ALTER TABLE ONLY public.guide_source_snapshot_items
    ADD CONSTRAINT fk_gssi_source_snapshot FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_bindings_exact_item FOREIGN KEY (source_item_id, source_snapshot_id) REFERENCES public.guide_source_snapshot_items(id, source_snapshot_id);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_bindings_exact_setup_generation FOREIGN KEY (project_setup_run_id, project_id, guide_id, source_snapshot_id, setup_generation) REFERENCES public.project_setup_runs(id, project_id, guide_id, source_snapshot_id, setup_generation);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_bindings_exact_snapshot FOREIGN KEY (source_snapshot_id, project_id, guide_id) REFERENCES public.guide_source_snapshots(id, project_id, guide_id);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_bindings_verified_replica_content FOREIGN KEY (verified_replica_id, content_id) REFERENCES public.artifact_replicas(id, content_id);
ALTER TABLE ONLY public.guide_source_format_classifications
    ADD CONSTRAINT fk_guide_classifications_exact_binding FOREIGN KEY (binding_id, content_id, verified_replica_id, setup_generation) REFERENCES public.guide_source_artifact_bindings(id, content_id, verified_replica_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_attempts
    ADD CONSTRAINT fk_guide_extraction_attempts_exact_binding FOREIGN KEY (binding_id, content_id, setup_generation) REFERENCES public.guide_source_artifact_bindings(id, content_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_attempts
    ADD CONSTRAINT fk_guide_extraction_attempts_exact_classification FOREIGN KEY (classification_id, binding_id, content_id, setup_generation) REFERENCES public.guide_source_format_classifications(id, binding_id, content_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_retry_budgets
    ADD CONSTRAINT fk_guide_extraction_retry_budgets_exact_binding FOREIGN KEY (binding_id, content_id, setup_generation) REFERENCES public.guide_source_artifact_bindings(id, content_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_retry_budgets
    ADD CONSTRAINT fk_guide_extraction_retry_budgets_exact_classification FOREIGN KEY (classification_id, binding_id, content_id, setup_generation) REFERENCES public.guide_source_format_classifications(id, binding_id, content_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT fk_guide_extraction_usages_exact_attempt FOREIGN KEY (extraction_attempt_id, binding_id, content_id, setup_generation, attempt_status) REFERENCES public.guide_source_extraction_attempts(id, binding_id, content_id, setup_generation, status);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT fk_guide_extraction_usages_exact_binding FOREIGN KEY (binding_id, content_id, source_item_id, project_setup_run_id, setup_generation) REFERENCES public.guide_source_artifact_bindings(id, content_id, source_item_id, project_setup_run_id, setup_generation);
ALTER TABLE ONLY public.guide_source_extraction_usages
    ADD CONSTRAINT fk_guide_extraction_usages_exact_content FOREIGN KEY (extracted_content_id, content_id) REFERENCES public.guide_source_extracted_contents(id, content_id);
ALTER TABLE ONLY public.guide_source_artifact_incidents
    ADD CONSTRAINT fk_guide_incidents_exact_binding FOREIGN KEY (binding_id, content_id, verified_replica_id, setup_generation) REFERENCES public.guide_source_artifact_bindings(id, content_id, verified_replica_id, setup_generation);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_mutation_idempotency_records_actor_profile_id__2ee3 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_mutation_idempotency_records_identity_link_id__3ddf FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_mutation_idempotency_records_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_mutation_idempotency_records_setup_run_id_proj_7dc3 FOREIGN KEY (setup_run_id) REFERENCES public.project_setup_runs(id);
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_source_artifact_bindings_content_id_artifact_contents FOREIGN KEY (content_id) REFERENCES public.artifact_contents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.guide_source_artifact_bindings
    ADD CONSTRAINT fk_guide_source_artifact_bindings_supersedes_binding_id_bfa2 FOREIGN KEY (supersedes_binding_id) REFERENCES public.guide_source_artifact_bindings(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.guide_source_artifact_ingests
    ADD CONSTRAINT fk_guide_source_artifact_ingests_actor_profile_id_actor_22c1 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_source_artifact_ingests
    ADD CONSTRAINT fk_guide_source_artifact_ingests_source_item_id_guide_s_7ba9 FOREIGN KEY (source_item_id) REFERENCES public.guide_source_snapshot_items(id);
ALTER TABLE ONLY public.guide_source_extracted_contents
    ADD CONSTRAINT fk_guide_source_extracted_contents_content_id_artifact_contents FOREIGN KEY (content_id) REFERENCES public.artifact_contents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_created_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_created_admin_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_created_decision FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_created_identity_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.guide_source_snapshots
    ADD CONSTRAINT fk_guide_source_snapshots_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_actor_16d8 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_guide_1d2b FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_ident_2378 FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_proje_7f82 FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_repor_48c3 FOREIGN KEY (report_id) REFERENCES public.guide_sufficiency_reports(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_setup_7059 FOREIGN KEY (setup_run_id) REFERENCES public.project_setup_runs(id);
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records
    ADD CONSTRAINT fk_guide_sufficiency_mutation_idempotency_records_sourc_9985 FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id);
ALTER TABLE ONLY public.guide_sufficiency_report_source_usages
    ADD CONSTRAINT fk_guide_sufficiency_report_source_usages_report_id_gui_1d57 FOREIGN KEY (report_id) REFERENCES public.guide_sufficiency_reports(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_guide_sufficiency_reports_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_guide_sufficiency_reports_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_guide_sufficiency_reports_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_guide_sufficiency_reports_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.legacy_workflow_eligibility
    ADD CONSTRAINT fk_legacy_workflow_eligibility_actor_id_legacy_actor_identities FOREIGN KEY (actor_id) REFERENCES public.legacy_actor_identities(actor_id);
ALTER TABLE ONLY public.outbox_delivery_attempts
    ADD CONSTRAINT fk_outbox_delivery_attempts_claim_decision_event_id_aud_d27a FOREIGN KEY (claim_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.outbox_delivery_attempts
    ADD CONSTRAINT fk_outbox_delivery_attempts_event_id_outbox_events FOREIGN KEY (event_id) REFERENCES public.outbox_events(event_id);
ALTER TABLE ONLY public.outbox_delivery_attempts
    ADD CONSTRAINT fk_outbox_delivery_attempts_finalize_decision_event_id__ef22 FOREIGN KEY (finalize_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.outbox_delivery_attempts
    ADD CONSTRAINT fk_outbox_delivery_attempts_invoke_decision_event_id_au_4ca6 FOREIGN KEY (invoke_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.outbox_delivery_attempts
    ADD CONSTRAINT fk_outbox_delivery_attempts_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.outbox_events
    ADD CONSTRAINT fk_outbox_events_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.payment_policies
    ADD CONSTRAINT fk_payment_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.payment_policies
    ADD CONSTRAINT fk_payment_policies_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT fk_policy_mutation_idempotency_records_actor_profile_id_41c2 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT fk_policy_mutation_idempotency_records_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT fk_policy_mutation_idempotency_records_identity_link_id_b806 FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.policy_mutation_idempotency_records
    ADD CONSTRAINT fk_policy_mutation_idempotency_records_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_post_policy_operations
    ADD CONSTRAINT fk_post_policy_operation_actor_link FOREIGN KEY (identity_link_id, actor_profile_id) REFERENCES public.actor_identity_links(id, actor_profile_id);
ALTER TABLE ONLY public.project_post_policy_operations
    ADD CONSTRAINT fk_post_policy_operation_compilation_scope FOREIGN KEY (compilation_id, project_id, guide_id) REFERENCES public.project_guide_compilations(id, project_id, guide_id);
ALTER TABLE ONLY public.project_post_policy_operations
    ADD CONSTRAINT fk_post_policy_operation_policy_scope FOREIGN KEY (policy_id, project_id, guide_id) REFERENCES public.checker_policies(id, project_id, guide_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.pre_submit_execution_attempts
    ADD CONSTRAINT fk_pre_submit_attempt_actor_link FOREIGN KEY (identity_link_id, actor_profile_id) REFERENCES public.actor_identity_links(id, actor_profile_id);
ALTER TABLE ONLY public.pre_submit_execution_attempts
    ADD CONSTRAINT fk_pre_submit_attempt_assignment FOREIGN KEY (assignment_id, task_id, actor_profile_id) REFERENCES public.task_assignments(id, task_id, contributor_id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_effective_hash FOREIGN KEY (effective_policy_id, effective_policy_hash) REFERENCES public.effective_project_submission_artifact_policies(id, effective_policy_hash);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_guide FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_checker_policies_supersedes FOREIGN KEY (supersedes_pre_submit_checker_policy_id) REFERENCES public.pre_submit_checker_policies(id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_assignment FOREIGN KEY (assignment_id, task_id, actor_profile_id) REFERENCES public.task_assignments(id, task_id, contributor_id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_guide_lineage FOREIGN KEY (guide_id, project_id, guide_version) REFERENCES public.project_guides(id, project_id, version);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_identity_actor FOREIGN KEY (identity_link_id, actor_profile_id) REFERENCES public.actor_identity_links(id, actor_profile_id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_predecessor FOREIGN KEY (predecessor_submission_id, task_id, predecessor_submission_version) REFERENCES public.submissions(id, task_id, version);
ALTER TABLE ONLY public.pre_submit_evidence_results
    ADD CONSTRAINT fk_pre_submit_evidence_results_evidence_set_id_pre_subm_096e FOREIGN KEY (evidence_set_id) REFERENCES public.pre_submit_evidence_sets(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_actor_profile_id_actor_profiles FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_assignment_id_task_assignments FOREIGN KEY (assignment_id) REFERENCES public.task_assignments(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_effective_policy_id_effecti_6a99 FOREIGN KEY (effective_policy_id) REFERENCES public.effective_project_submission_artifact_policies(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_identity_link_id_actor_iden_5cef FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_pre_submit_policy_id_pre_su_c77f FOREIGN KEY (pre_submit_policy_id) REFERENCES public.pre_submit_checker_policies(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_predecessor_submission_id_s_6ec2 FOREIGN KEY (predecessor_submission_id) REFERENCES public.submissions(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_source_snapshot_id_guide_so_1667 FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_sets_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_task_artifact_policy FOREIGN KEY (task_id, effective_policy_id, locked_artifact_policy_sha256) REFERENCES public.workstream_tasks(id, locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_task_checker_policy FOREIGN KEY (task_id, pre_submit_policy_id, locked_checker_policy_sha256) REFERENCES public.workstream_tasks(id, locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_task_guide FOREIGN KEY (task_id, guide_version) REFERENCES public.workstream_tasks(id, locked_guide_version);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_task_project FOREIGN KEY (task_id, project_id) REFERENCES public.workstream_tasks(id, project_id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT fk_pre_submit_evidence_task_source_snapshot FOREIGN KEY (task_id, source_snapshot_id, source_snapshot_sha256) REFERENCES public.workstream_tasks(id, locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_policy_creation_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_policy_creation_decision FOREIGN KEY (creation_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_policy_creation_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_policy_creation_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.pre_submit_checker_policies
    ADD CONSTRAINT fk_pre_submit_policy_creation_project FOREIGN KEY (creation_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_compensation_units
    ADD CONSTRAINT fk_project_compensation_unit_created_by FOREIGN KEY (created_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_compensation_units
    ADD CONSTRAINT fk_project_compensation_unit_iso_currency FOREIGN KEY (iso_currency_code) REFERENCES public.iso_4217_currency_codes(code);
ALTER TABLE ONLY public.project_compensation_units
    ADD CONSTRAINT fk_project_compensation_unit_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_compensation_units
    ADD CONSTRAINT fk_project_compensation_unit_retired_by FOREIGN KEY (retired_by) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT fk_project_create_idempotency_records_actor_profile_id__ebb1 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_create_idempotency_records
    ADD CONSTRAINT fk_project_create_idempotency_records_identity_link_id__ddce FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT fk_project_guide_compilation_attempts_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.project_guide_compilation_attempts
    ADD CONSTRAINT fk_project_guide_compilation_attempts_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilation_predecessor FOREIGN KEY (supersedes_compilation_id, project_id, guide_id) REFERENCES public.project_guide_compilations(id, project_id, guide_id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_attempt_id_project_guide__0e94 FOREIGN KEY (attempt_id) REFERENCES public.project_guide_compilation_attempts(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_authorization_decision_ev_42ad FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_created_by_actor_profile__953f FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_created_via_identity_link_b250 FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_setup_run_id_project_setup_runs FOREIGN KEY (setup_run_id) REFERENCES public.project_setup_runs(id);
ALTER TABLE ONLY public.project_guide_compilations
    ADD CONSTRAINT fk_project_guide_compilations_source_snapshot_id_guide__033a FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT fk_project_guide_component_projection_operations_author_53b0 FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT fk_project_guide_component_projection_operations_guide__4545 FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT fk_project_guide_component_projection_operations_policy_22cc FOREIGN KEY (policy_id) REFERENCES public.submission_artifact_policies(id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT fk_project_guide_component_projection_operations_prior__98cf FOREIGN KEY (prior_operation_id) REFERENCES public.project_guide_component_projection_operations(operation_id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT fk_project_guide_component_projection_operations_projec_86f7 FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT fk_project_guide_component_projection_operations_report_b664 FOREIGN KEY (report_id) REFERENCES public.guide_sufficiency_reports(id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT fk_project_guide_component_projection_operations_reques_063a FOREIGN KEY (request_operation_id) REFERENCES public.project_guide_compilation_request_operations(operation_id);
ALTER TABLE ONLY public.project_guide_document_accesses
    ADD CONSTRAINT fk_project_guide_document_accesses_attachment_allocatio_99f0 FOREIGN KEY (attachment_allocation_id) REFERENCES public.project_guide_runtime_allocations(id);
ALTER TABLE ONLY public.project_guide_document_accesses
    ADD CONSTRAINT fk_project_guide_document_accesses_attempt_id_project_g_fd8d FOREIGN KEY (attempt_id) REFERENCES public.project_guide_compilation_attempts(id);
ALTER TABLE ONLY public.project_guide_document_accesses
    ADD CONSTRAINT fk_project_guide_document_accesses_document_version_id__da51 FOREIGN KEY (document_version_id) REFERENCES public.guide_source_artifact_ingests(id);
ALTER TABLE ONLY public.project_guide_document_accesses
    ADD CONSTRAINT fk_project_guide_document_accesses_source_item_id_guide_fac9 FOREIGN KEY (source_item_id) REFERENCES public.guide_source_snapshot_items(id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT fk_project_guide_proposal_approvals_actor_profile_id_ac_138f FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT fk_project_guide_proposal_approvals_admin_role_grant_id_c2fe FOREIGN KEY (admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT fk_project_guide_proposal_approvals_artifact_policy_id__74ba FOREIGN KEY (artifact_policy_id) REFERENCES public.submission_artifact_policies(id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT fk_project_guide_proposal_approvals_authorization_decis_0fd3 FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT fk_project_guide_proposal_approvals_effective_policy_id_e004 FOREIGN KEY (effective_policy_id) REFERENCES public.effective_project_submission_artifact_policies(id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT fk_project_guide_proposal_approvals_finalization_id_pro_a505 FOREIGN KEY (finalization_id) REFERENCES public.project_guide_setup_finalizations(id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT fk_project_guide_proposal_approvals_operation_id_submis_cdf3 FOREIGN KEY (operation_id) REFERENCES public.submission_policy_mutation_idempotency_records(operation_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT fk_project_guide_proposal_approvals_pre_submit_policy_i_020c FOREIGN KEY (pre_submit_policy_id) REFERENCES public.pre_submit_checker_policies(id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT fk_project_guide_proposal_approvals_prior_approval_oper_464d FOREIGN KEY (prior_approval_operation_id) REFERENCES public.project_guide_proposal_approvals(operation_id);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT fk_project_guide_proposal_corrections_actor_profile_id__0d74 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT fk_project_guide_proposal_corrections_admin_role_grant__7dce FOREIGN KEY (admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT fk_project_guide_proposal_corrections_authorization_dec_47af FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT fk_project_guide_proposal_corrections_finalization_id_p_7d0c FOREIGN KEY (finalization_id) REFERENCES public.project_guide_setup_finalizations(id);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT fk_project_guide_proposal_corrections_successor_setup_r_db10 FOREIGN KEY (successor_setup_run_id) REFERENCES public.project_setup_runs(id);
ALTER TABLE ONLY public.project_guide_runtime_allocations
    ADD CONSTRAINT fk_project_guide_runtime_allocations_attempt_id_project_f464 FOREIGN KEY (attempt_id) REFERENCES public.project_guide_compilation_attempts(id);
ALTER TABLE ONLY public.project_guide_runtime_allocations
    ADD CONSTRAINT fk_project_guide_runtime_allocations_container_allocati_6331 FOREIGN KEY (container_allocation_id) REFERENCES public.project_guide_runtime_allocations(id);
ALTER TABLE ONLY public.project_guide_runtime_allocations
    ADD CONSTRAINT fk_project_guide_runtime_allocations_content_id_artifac_96ac FOREIGN KEY (content_id) REFERENCES public.artifact_contents(id);
ALTER TABLE ONLY public.project_guide_runtime_allocations
    ADD CONSTRAINT fk_project_guide_runtime_allocations_document_version_i_741e FOREIGN KEY (document_version_id) REFERENCES public.guide_source_artifact_ingests(id);
ALTER TABLE ONLY public.project_guide_runtime_allocations
    ADD CONSTRAINT fk_project_guide_runtime_allocations_put_attempt_id_art_b927 FOREIGN KEY (put_attempt_id) REFERENCES public.artifact_put_attempts(id);
ALTER TABLE ONLY public.project_guide_runtime_allocations
    ADD CONSTRAINT fk_project_guide_runtime_allocations_replica_id_artifac_a10d FOREIGN KEY (replica_id) REFERENCES public.artifact_replicas(id);
ALTER TABLE ONLY public.project_guide_runtime_allocations
    ADD CONSTRAINT fk_project_guide_runtime_allocations_source_file_alloca_cfc9 FOREIGN KEY (source_file_allocation_id) REFERENCES public.project_guide_runtime_allocations(id);
ALTER TABLE ONLY public.project_guide_runtime_allocations
    ADD CONSTRAINT fk_project_guide_runtime_allocations_source_item_id_gui_7254 FOREIGN KEY (source_item_id) REFERENCES public.guide_source_snapshot_items(id);
ALTER TABLE ONLY public.project_guide_runtime_allocations
    ADD CONSTRAINT fk_project_guide_runtime_allocations_storage_namespace__ef59 FOREIGN KEY (storage_namespace_id) REFERENCES public.artifact_storage_namespaces(id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_project_guide_setup_finalizations_actor_profile_id_a_109b FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_project_guide_setup_finalizations_artifact_policy_id_eb23 FOREIGN KEY (artifact_policy_id) REFERENCES public.submission_artifact_policies(id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_project_guide_setup_finalizations_authorization_deci_9791 FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_project_guide_setup_finalizations_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_project_guide_setup_finalizations_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_project_guide_setup_finalizations_request_operation__c6a1 FOREIGN KEY (request_operation_id) REFERENCES public.project_guide_compilation_request_operations(operation_id);
ALTER TABLE ONLY public.project_guide_setup_finalizations
    ADD CONSTRAINT fk_project_guide_setup_finalizations_sufficiency_report_dfc6 FOREIGN KEY (sufficiency_report_id) REFERENCES public.guide_sufficiency_reports(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_activation_operation FOREIGN KEY (activation_operation_id, project_id, id) REFERENCES public.guide_mutation_idempotency_records(operation_id, project_id, resource_id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_contribution_policy FOREIGN KEY (contribution_policy_version_id, contribution_policy_id, project_id) REFERENCES public.contribution_policy_versions(id, contribution_policy_id, project_id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_last_mutated_actor FOREIGN KEY (last_mutated_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_last_mutated_admin_grant FOREIGN KEY (last_mutated_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_last_mutated_decision FOREIGN KEY (last_authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_last_mutated_identity_link FOREIGN KEY (last_mutated_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_selected_review_policy FOREIGN KEY (project_id, version, selected_review_policy_id, selected_review_policy_generation, selected_review_policy_hash) REFERENCES public.review_policies(project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.project_guides
    ADD CONSTRAINT fk_project_guides_selected_revision_policy FOREIGN KEY (project_id, version, selected_revision_policy_id, selected_revision_policy_generation, selected_revision_policy_hash) REFERENCES public.revision_policies(project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.project_post_policy_operations
    ADD CONSTRAINT fk_project_post_policy_operations_actor_profile_id_acto_e2b8 FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_post_policy_operations
    ADD CONSTRAINT fk_project_post_policy_operations_admin_role_grant_id_a_a838 FOREIGN KEY (admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_post_policy_operations
    ADD CONSTRAINT fk_project_post_policy_operations_authorization_decisio_0e5b FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_post_policy_operations
    ADD CONSTRAINT fk_project_post_policy_operations_upstream_approval_ope_4fef FOREIGN KEY (upstream_approval_operation_id) REFERENCES public.project_guide_proposal_approvals(operation_id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_actor_profile_id_actor_profiles FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_granted_by_actor_profile_id_acto_c240 FOREIGN KEY (granted_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_granted_by_admin_role_grant_id_a_71d7 FOREIGN KEY (granted_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_revoked_by_actor_profile_id_acto_a5dd FOREIGN KEY (revoked_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT fk_project_role_grants_revoked_by_admin_role_grant_id_a_aa4d FOREIGN KEY (revoked_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT fk_project_role_qualification_snapshots_actor_profile_i_aedc FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT fk_project_role_qualification_snapshots_captured_by_act_ab57 FOREIGN KEY (captured_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT fk_project_role_qualification_snapshots_captured_by_adm_c8b8 FOREIGN KEY (captured_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_role_qualification_snapshots
    ADD CONSTRAINT fk_project_role_qualification_snapshots_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_artifact_incident FOREIGN KEY (error_artifact_incident_id) REFERENCES public.guide_source_artifact_incidents(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_authorized_actor FOREIGN KEY (authorized_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_authorized_admin_grant FOREIGN KEY (authorized_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_authorized_decision FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_authorized_identity_link FOREIGN KEY (authorized_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_post_submit_checker_policy FOREIGN KEY (output_post_submit_checker_policy_id) REFERENCES public.checker_policies(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_retained_continuation_verification_job FOREIGN KEY (retained_continuation_verification_job_id) REFERENCES public.artifact_verification_jobs(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_source_snapshot_id_guide_source_snapshots FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_submission_artifact_policy FOREIGN KEY (output_submission_artifact_policy_id) REFERENCES public.submission_artifact_policies(id);
ALTER TABLE ONLY public.project_setup_runs
    ADD CONSTRAINT fk_project_setup_runs_sufficiency_report FOREIGN KEY (output_sufficiency_report_id) REFERENCES public.guide_sufficiency_reports(id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT fk_projection_operation_actor_link FOREIGN KEY (identity_link_id, actor_profile_id) REFERENCES public.actor_identity_links(id, actor_profile_id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT fk_projection_operation_exact_attempt FOREIGN KEY (attempt_id, project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation) REFERENCES public.project_guide_compilation_attempts(id, project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT fk_projection_operation_exact_compilation FOREIGN KEY (compilation_id, attempt_id) REFERENCES public.project_guide_compilations(id, attempt_id);
ALTER TABLE ONLY public.project_guide_component_projection_operations
    ADD CONSTRAINT fk_projection_operation_exact_setup FOREIGN KEY (setup_run_id, project_id, guide_id, source_snapshot_id, setup_generation) REFERENCES public.project_setup_runs(id, project_id, guide_id, source_snapshot_id, setup_generation);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_creation_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_creation_admin_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_creation_decision FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_creation_identity_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT fk_proposal_approval_actor_link FOREIGN KEY (identity_link_id, actor_profile_id) REFERENCES public.actor_identity_links(id, actor_profile_id);
ALTER TABLE ONLY public.project_guide_proposal_approvals
    ADD CONSTRAINT fk_proposal_approval_compilation_scope FOREIGN KEY (compilation_id, project_id, guide_id) REFERENCES public.project_guide_compilations(id, project_id, guide_id);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT fk_proposal_correction_actor_link FOREIGN KEY (identity_link_id, actor_profile_id) REFERENCES public.actor_identity_links(id, actor_profile_id);
ALTER TABLE ONLY public.project_guide_proposal_corrections
    ADD CONSTRAINT fk_proposal_correction_compilation_scope FOREIGN KEY (compilation_id, project_id, guide_id) REFERENCES public.project_guide_compilations(id, project_id, guide_id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_checker FOREIGN KEY (admitting_checker_run_id) REFERENCES public.checker_runs(id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_committed_queue FOREIGN KEY (review_queue_entry_id, project_id, task_id, submission_id, submission_version, admitting_checker_run_id) REFERENCES public.review_queue_entries(id, project_id, task_id, submission_id, submission_version, admitting_checker_run_id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_queue FOREIGN KEY (review_queue_entry_id) REFERENCES public.review_queue_entries(id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_submission FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_submission_lineage FOREIGN KEY (submission_id, task_id, submission_version) REFERENCES public.submissions(id, task_id, version);
ALTER TABLE ONLY public.review_admission_idempotency_records
    ADD CONSTRAINT fk_review_admission_task FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_policy_version FOREIGN KEY (reviewer_contribution_policy_version_id, project_id) REFERENCES public.contribution_policy_versions(id, project_id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_queue_lineage FOREIGN KEY (review_queue_entry_id, project_id, task_id, submission_id, submission_version) REFERENCES public.review_queue_entries(id, project_id, task_id, submission_id, submission_version);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_reviewer FOREIGN KEY (reviewer_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_submission FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.review_leases
    ADD CONSTRAINT fk_review_lease_task FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_actor_profile FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_admin_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_decision_event FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_identity_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.review_policies
    ADD CONSTRAINT fk_review_policies_supersedes FOREIGN KEY (supersedes_policy_id) REFERENCES public.review_policies(id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_active_lease FOREIGN KEY (active_lease_id, id) REFERENCES public.review_leases(id, review_queue_entry_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_checker FOREIGN KEY (admitting_checker_run_id) REFERENCES public.checker_runs(id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_preferred_reviewer FOREIGN KEY (preferred_reviewer_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_project FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_submission FOREIGN KEY (submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_submission_lineage FOREIGN KEY (submission_id, task_id, submission_version) REFERENCES public.submissions(id, task_id, version);
ALTER TABLE ONLY public.review_queue_entries
    ADD CONSTRAINT fk_review_queue_task FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_actor_profile FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_admin_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_decision_event FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_identity_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.revision_policies
    ADD CONSTRAINT fk_revision_policies_supersedes FOREIGN KEY (supersedes_policy_id) REFERENCES public.revision_policies(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_sap_supersedes_policy FOREIGN KEY (supersedes_policy_id) REFERENCES public.submission_artifact_policies(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_artifact_policies_guide_id_project_guides FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_artifact_policies_project_guide FOREIGN KEY (project_id, guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_artifact_policies_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_artifact_policies_source_snapshot_hash FOREIGN KEY (source_snapshot_id, source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_actor_profile_id_actor_profiles FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_artifact_content_id_art_12c8 FOREIGN KEY (artifact_content_id) REFERENCES public.artifact_contents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_assignment_id_task_assignments FOREIGN KEY (assignment_id) REFERENCES public.task_assignments(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_consumed_by_submission__2b23 FOREIGN KEY (consumed_by_submission_id) REFERENCES public.submissions(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_durable_intent_id_submi_102c FOREIGN KEY (durable_intent_id) REFERENCES public.submission_bundle_durable_intents(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_identity_link_id_actor__d29d FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_pre_submit_evidence_set_a752 FOREIGN KEY (pre_submit_evidence_set_id) REFERENCES public.pre_submit_evidence_sets(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_predecessor_submission__242d FOREIGN KEY (predecessor_submission_id) REFERENCES public.submissions(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_put_attempt_id_artifact_bbc3 FOREIGN KEY (put_attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_put_observation_receipt_5136 FOREIGN KEY (put_observation_receipt_id) REFERENCES public.artifact_put_observation_receipts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_put_operation_receipt_i_9602 FOREIGN KEY (put_operation_receipt_id) REFERENCES public.artifact_operation_receipts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_verification_receipt_id_0ea1 FOREIGN KEY (verification_receipt_id) REFERENCES public.artifact_verification_receipts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_admissions
    ADD CONSTRAINT fk_submission_bundle_admissions_verified_replica_id_art_3a4e FOREIGN KEY (verified_replica_id) REFERENCES public.artifact_replicas(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_durable_intents
    ADD CONSTRAINT fk_submission_bundle_durable_intents_pre_submit_evidenc_c406 FOREIGN KEY (pre_submit_evidence_set_id) REFERENCES public.pre_submit_evidence_sets(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_bundle_durable_intents
    ADD CONSTRAINT fk_submission_bundle_durable_intents_put_attempt_id_art_b4e4 FOREIGN KEY (put_attempt_id) REFERENCES public.artifact_put_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_approval_actor FOREIGN KEY (approved_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_approval_decision FOREIGN KEY (approval_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_approval_grant FOREIGN KEY (approved_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_approval_link FOREIGN KEY (approved_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_approval_project FOREIGN KEY (approval_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_creation_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_creation_decision FOREIGN KEY (creation_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_creation_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_creation_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.submission_artifact_policies
    ADD CONSTRAINT fk_submission_policy_creation_project FOREIGN KEY (creation_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_actor_f5bb FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_commi_4fa6 FOREIGN KEY (committed_effective_policy_id) REFERENCES public.effective_project_submission_artifact_policies(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_commi_571a FOREIGN KEY (committed_policy_id) REFERENCES public.submission_artifact_policies(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_commi_baa9 FOREIGN KEY (committed_pre_submit_policy_id) REFERENCES public.pre_submit_checker_policies(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_guide_ed8d FOREIGN KEY (guide_id) REFERENCES public.project_guides(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_ident_2567 FOREIGN KEY (identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_proje_442a FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_setup_a102 FOREIGN KEY (setup_run_id) REFERENCES public.project_setup_runs(id);
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records
    ADD CONSTRAINT fk_submission_policy_mutation_idempotency_records_sourc_536e FOREIGN KEY (source_snapshot_id) REFERENCES public.guide_source_snapshots(id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_assignment_identity FOREIGN KEY (task_assignment_id, task_id, contributor_id) REFERENCES public.task_assignments(id, task_id, contributor_id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_contributor_id_actor_profiles FOREIGN KEY (contributor_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_locked_effective_policy_hash FOREIGN KEY (locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash) REFERENCES public.effective_project_submission_artifact_policies(id, effective_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_locked_post_submit_policy_hash FOREIGN KEY (locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash) REFERENCES public.checker_policies(id, guide_version, policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_locked_pre_submit_checker_hash FOREIGN KEY (locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash) REFERENCES public.pre_submit_checker_policies(id, compiled_bundle_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_locked_source_snapshot_hash FOREIGN KEY (locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_supersedes_submission_id_submissions FOREIGN KEY (supersedes_submission_id) REFERENCES public.submissions(id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_assignment_id_task_assignments FOREIGN KEY (task_assignment_id) REFERENCES public.task_assignments(id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_effective_policy_hash FOREIGN KEY (task_id, locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash) REFERENCES public.workstream_tasks(id, locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_guide FOREIGN KEY (task_id, locked_guide_version) REFERENCES public.workstream_tasks(id, locked_guide_version);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_payment_policy FOREIGN KEY (task_id, locked_payment_policy_version) REFERENCES public.workstream_tasks(id, locked_payment_policy_version);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_post_submit_policy_hash FOREIGN KEY (task_id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash) REFERENCES public.workstream_tasks(id, locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_pre_submit_checker_hash FOREIGN KEY (task_id, locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash) REFERENCES public.workstream_tasks(id, locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_review_policy FOREIGN KEY (task_id, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash) REFERENCES public.workstream_tasks(id, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_revision_policy FOREIGN KEY (task_id, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash) REFERENCES public.workstream_tasks(id, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash);
ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT fk_submissions_task_locked_source_snapshot_hash FOREIGN KEY (task_id, locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash) REFERENCES public.workstream_tasks(id, locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_ack_actor FOREIGN KEY (warnings_acknowledged_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_ack_decision FOREIGN KEY (warning_acknowledgement_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_ack_grant FOREIGN KEY (warnings_acknowledged_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_ack_link FOREIGN KEY (warnings_acknowledged_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_ack_project FOREIGN KEY (warning_acknowledgement_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_create_actor FOREIGN KEY (created_by_actor_profile_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_create_decision FOREIGN KEY (authorization_decision_event_id) REFERENCES public.audit_events(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_create_grant FOREIGN KEY (created_by_admin_role_grant_id) REFERENCES public.admin_role_grants(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_create_link FOREIGN KEY (created_via_identity_link_id) REFERENCES public.actor_identity_links(id);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_suff_create_project FOREIGN KEY (creation_scope_project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.guide_sufficiency_report_source_usages
    ADD CONSTRAINT fk_sufficiency_report_source_usage_exact_extraction FOREIGN KEY (extraction_usage_id, source_item_id, binding_id, content_id, extraction_attempt_id, extracted_content_id, project_setup_run_id, setup_generation) REFERENCES public.guide_source_extraction_usages(id, source_item_id, binding_id, content_id, extraction_attempt_id, extracted_content_id, project_setup_run_id, setup_generation);
ALTER TABLE ONLY public.guide_sufficiency_reports
    ADD CONSTRAINT fk_sufficiency_reports_setup_run FOREIGN KEY (project_setup_run_id) REFERENCES public.project_setup_runs(id);
ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT fk_task_assignments_contributor_id_actor_profiles FOREIGN KEY (contributor_id) REFERENCES public.actor_profiles(id);
ALTER TABLE ONLY public.task_assignments
    ADD CONSTRAINT fk_task_assignments_task_id_workstream_tasks FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id);
ALTER TABLE ONLY public.task_command_receipts
    ADD CONSTRAINT fk_task_command_assignment FOREIGN KEY (assignment_id, task_id, contributor_id) REFERENCES public.task_assignments(id, task_id, contributor_id);
ALTER TABLE ONLY public.task_command_receipts
    ADD CONSTRAINT fk_task_command_receipts_actor_profile_id_actor_profiles FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.task_command_receipts
    ADD CONSTRAINT fk_task_command_task FOREIGN KEY (task_id) REFERENCES public.workstream_tasks(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_tasks_guide_contribution_policy FOREIGN KEY (project_id, locked_guide_version, locked_contribution_policy_version_id) REFERENCES public.project_guides(project_id, version, contribution_policy_version_id);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_effective_policy_hash FOREIGN KEY (locked_effective_project_submission_artifact_policy_id, locked_effective_project_submission_artifact_policy_hash) REFERENCES public.effective_project_submission_artifact_policies(id, effective_policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_guide FOREIGN KEY (project_id, locked_guide_version) REFERENCES public.project_guides(project_id, version);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_payment_policy FOREIGN KEY (project_id, locked_payment_policy_version) REFERENCES public.payment_policies(project_id, guide_version);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_post_submit_policy_hash FOREIGN KEY (locked_post_submit_checker_policy_id, locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash) REFERENCES public.checker_policies(id, guide_version, policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_pre_submit_checker_hash FOREIGN KEY (locked_pre_submit_checker_policy_id, locked_pre_submit_checker_bundle_hash) REFERENCES public.pre_submit_checker_policies(id, compiled_bundle_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_review_policy FOREIGN KEY (project_id, locked_guide_version, locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash) REFERENCES public.review_policies(project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_revision_policy FOREIGN KEY (project_id, locked_guide_version, locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash) REFERENCES public.revision_policies(project_id, guide_version, id, policy_generation, policy_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_locked_source_snapshot_hash FOREIGN KEY (locked_guide_source_snapshot_id, locked_guide_source_snapshot_hash) REFERENCES public.guide_source_snapshots(id, bundle_hash);
ALTER TABLE ONLY public.workstream_tasks
    ADD CONSTRAINT fk_workstream_tasks_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);
ALTER TABLE ONLY public.pre_submit_evidence_sets
    ADD CONSTRAINT pre_submit_evidence_sets_attempt_id_fkey FOREIGN KEY (attempt_id) REFERENCES public.pre_submit_execution_attempts(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_execution_attempts
    ADD CONSTRAINT pre_submit_execution_attempts_actor_profile_id_fkey FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.pre_submit_execution_attempts
    ADD CONSTRAINT pre_submit_execution_attempts_evidence_set_id_fkey FOREIGN KEY (evidence_set_id) REFERENCES public.pre_submit_evidence_sets(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.project_role_grants
    ADD CONSTRAINT qualification_ownership FOREIGN KEY (qualification_snapshot_id, actor_profile_id, project_id, role) REFERENCES public.project_role_qualification_snapshots(id, actor_profile_id, project_id, requested_role) ON DELETE RESTRICT;
CREATE UNIQUE INDEX uq_audit_assignment_release_cause ON public.audit_events
((event_payload->'references'->>'assignment_id'),
 (event_payload->'references'->>'authority_invalidation_event_id'))
WHERE event_type = 'TaskAssignmentAuthorityRevoked';
ALTER TABLE ONLY public.project_guide_compilation_request_operations
ADD CONSTRAINT uq_compilation_request_setup_trigger
UNIQUE (setup_run_id, setup_generation, request_trigger);
CREATE UNIQUE INDEX uq_guide_activation_resource
ON public.guide_mutation_idempotency_records (resource_id)
WHERE action_id = 'project.guide.activate';
ALTER TABLE public.actor_profiles ADD CONSTRAINT ck_actor_profiles_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.actor_identity_links ADD CONSTRAINT ck_actor_identity_links_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.legacy_workflow_eligibility ADD CONSTRAINT ck_legacy_workflow_eligibility_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.artifact_contents ADD CONSTRAINT ck_artifact_contents_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.pre_submit_execution_attempts ADD CONSTRAINT ck_pre_submit_execution_attempts_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.pre_submit_evidence_sets ADD CONSTRAINT ck_pre_submit_evidence_sets_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.pre_submit_evidence_results ADD CONSTRAINT ck_pre_submit_evidence_results_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.artifact_bindings ADD CONSTRAINT ck_artifact_bindings_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_source_artifact_bindings ADD CONSTRAINT ck_guide_source_artifact_bindings_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_source_format_classifications ADD CONSTRAINT ck_guide_source_format_classifications_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_source_artifact_incidents ADD CONSTRAINT ck_guide_source_artifact_incidents_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_source_extraction_attempts ADD CONSTRAINT ck_guide_source_extraction_attempts_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_source_extracted_contents ADD CONSTRAINT ck_guide_source_extracted_contents_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_source_extraction_usages ADD CONSTRAINT ck_guide_source_extraction_usages_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.artifact_admission_charges ADD CONSTRAINT ck_artifact_admission_charges_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.artifact_put_attempts ADD CONSTRAINT ck_artifact_put_attempts_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.submission_bundle_durable_intents ADD CONSTRAINT ck_submission_bundle_durable_intents_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.submission_bundle_admissions ADD CONSTRAINT ck_submission_bundle_admissions_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.artifact_replicas ADD CONSTRAINT ck_artifact_replicas_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.artifact_operation_receipts ADD CONSTRAINT ck_artifact_operation_receipts_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.artifact_put_observation_receipts ADD CONSTRAINT ck_artifact_put_observation_receipts_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.artifact_verification_jobs ADD CONSTRAINT ck_artifact_verification_jobs_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.artifact_recovery_attempts ADD CONSTRAINT ck_artifact_recovery_attempts_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.artifact_verification_receipts ADD CONSTRAINT ck_artifact_verification_receipts_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.authority_idempotency_records ADD CONSTRAINT ck_authority_idempotency_records_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.admin_role_grants ADD CONSTRAINT ck_admin_role_grants_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_role_qualification_snapshots ADD CONSTRAINT ck_project_role_qualification_snapshots_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_role_grants ADD CONSTRAINT ck_project_role_grants_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.checker_runs ADD CONSTRAINT ck_checker_runs_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.checker_results ADD CONSTRAINT ck_checker_results_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_compensation_adapter_bindings ADD CONSTRAINT ck_project_compensation_adapter_bindings_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.compensation_adapter_binding_lifecycle_events ADD CONSTRAINT ck_compensation_adapter_binding_lifecycle_events_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.contribution_policies ADD CONSTRAINT ck_contribution_policies_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.contribution_policy_versions ADD CONSTRAINT ck_contribution_policy_versions_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.contribution_rules ADD CONSTRAINT ck_contribution_rules_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.contribution_award_definitions ADD CONSTRAINT ck_contribution_award_definitions_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.contribution_policy_transition_custody ADD CONSTRAINT ck_contribution_policy_transition_custody_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.contribution_policy_lifecycle_events ADD CONSTRAINT ck_contribution_policy_lifecycle_events_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.outbox_events ADD CONSTRAINT ck_outbox_events_event_id_uuid7 CHECK ((get_byte(uuid_send(event_id), 6) >> 4) = 7 and (get_byte(uuid_send(event_id), 8) & 192) = 128);
ALTER TABLE public.projects ADD CONSTRAINT ck_projects_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_create_idempotency_records ADD CONSTRAINT ck_project_create_idempotency_records_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_mutation_idempotency_records ADD CONSTRAINT ck_guide_mutation_idempotency_records_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_sufficiency_mutation_idempotency_records ADD CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.submission_policy_mutation_idempotency_records ADD CONSTRAINT ck_submission_policy_mutation_idempotency_records_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.policy_mutation_idempotency_records ADD CONSTRAINT ck_policy_mutation_idempotency_records_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_guides ADD CONSTRAINT ck_project_guides_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.checker_policies ADD CONSTRAINT ck_checker_policies_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.review_policies ADD CONSTRAINT ck_review_policies_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.revision_policies ADD CONSTRAINT ck_revision_policies_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.payment_policies ADD CONSTRAINT ck_payment_policies_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_source_snapshots ADD CONSTRAINT ck_guide_source_snapshots_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_source_snapshot_items ADD CONSTRAINT ck_guide_source_snapshot_items_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_source_artifact_ingests ADD CONSTRAINT ck_guide_source_artifact_ingests_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_setup_runs ADD CONSTRAINT ck_project_setup_runs_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_sufficiency_reports ADD CONSTRAINT ck_guide_sufficiency_reports_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.guide_sufficiency_report_source_usages ADD CONSTRAINT ck_guide_sufficiency_report_source_usages_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.submission_artifact_policies ADD CONSTRAINT ck_submission_artifact_policies_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.effective_project_submission_artifact_policies ADD CONSTRAINT ck_effective_project_submission_artifact_policies_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.pre_submit_checker_policies ADD CONSTRAINT ck_pre_submit_checker_policies_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_guide_compilation_attempts ADD CONSTRAINT ck_project_guide_compilation_attempts_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_guide_compilation_request_operations ADD CONSTRAINT ck_project_guide_compilation_request_operations_operati_56df CHECK ((get_byte(uuid_send(operation_id), 6) >> 4) = 7 and (get_byte(uuid_send(operation_id), 8) & 192) = 128);
ALTER TABLE public.project_guide_compilations ADD CONSTRAINT ck_project_guide_compilations_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_guide_component_projection_operations ADD CONSTRAINT ck_project_guide_component_projection_operations_operat_d599 CHECK ((get_byte(uuid_send(operation_id), 6) >> 4) = 7 and (get_byte(uuid_send(operation_id), 8) & 192) = 128);
ALTER TABLE public.project_guide_setup_finalizations ADD CONSTRAINT ck_project_guide_setup_finalizations_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_guide_runtime_allocations ADD CONSTRAINT ck_project_guide_runtime_allocations_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_guide_document_accesses ADD CONSTRAINT ck_project_guide_document_accesses_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_guide_proposal_approvals ADD CONSTRAINT ck_project_guide_proposal_approvals_operation_id_uuid7 CHECK ((get_byte(uuid_send(operation_id), 6) >> 4) = 7 and (get_byte(uuid_send(operation_id), 8) & 192) = 128);
ALTER TABLE public.project_guide_proposal_corrections ADD CONSTRAINT ck_project_guide_proposal_corrections_operation_id_uuid7 CHECK ((get_byte(uuid_send(operation_id), 6) >> 4) = 7 and (get_byte(uuid_send(operation_id), 8) & 192) = 128);
ALTER TABLE public.review_queue_entries ADD CONSTRAINT ck_review_queue_entries_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.review_admission_idempotency_records ADD CONSTRAINT ck_review_admission_idempotency_records_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.review_leases ADD CONSTRAINT ck_review_leases_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.task_command_receipts ADD CONSTRAINT ck_task_command_receipts_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.workstream_tasks ADD CONSTRAINT ck_workstream_tasks_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.task_assignments ADD CONSTRAINT ck_task_assignments_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.submissions ADD CONSTRAINT ck_submissions_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.evidence_items ADD CONSTRAINT ck_evidence_items_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.audit_events ADD CONSTRAINT ck_audit_events_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128);
ALTER TABLE public.project_post_policy_operations ADD CONSTRAINT ck_project_post_policy_operations_operation_id_uuid7 CHECK ((get_byte(uuid_send(operation_id), 6) >> 4) = 7 and (get_byte(uuid_send(operation_id), 8) & 192) = 128);
CREATE TRIGGER actor_identity_link_history_guard BEFORE DELETE OR UPDATE ON public.actor_identity_links FOR EACH ROW EXECUTE FUNCTION public.guard_actor_identity_link_history();
CREATE CONSTRAINT TRIGGER actor_identity_link_profile_guard AFTER INSERT OR UPDATE ON public.actor_identity_links DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_canonical_actor_link();
CREATE TRIGGER actor_profile_history_guard BEFORE DELETE OR UPDATE ON public.actor_profiles FOR EACH ROW EXECUTE FUNCTION public.guard_actor_profile_history();
CREATE CONSTRAINT TRIGGER actor_profile_link_guard AFTER INSERT OR UPDATE ON public.actor_profiles DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_canonical_actor_link();
CREATE CONSTRAINT TRIGGER admin_role_grants_bootstrap_invariant AFTER INSERT OR DELETE OR UPDATE ON public.admin_role_grants DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_bootstrap_authority_state();
CREATE TRIGGER admin_role_grants_guard BEFORE INSERT OR DELETE OR UPDATE ON public.admin_role_grants FOR EACH ROW EXECUTE FUNCTION public.guard_admin_role_grant();
CREATE TRIGGER admin_role_grants_reject_truncate BEFORE TRUNCATE ON public.admin_role_grants FOR EACH STATEMENT EXECUTE FUNCTION public.reject_admin_role_grant_truncate();
CREATE TRIGGER artifact_receipt_producer_reference BEFORE INSERT OR UPDATE OF put_attempt_id, guide_source_item_id, checker_run_id, logical_role ON public.artifact_operation_receipts FOR EACH ROW EXECUTE FUNCTION public.guard_artifact_receipt_producer_reference();
CREATE TRIGGER artifact_recovery_attempt_custody BEFORE INSERT OR DELETE OR UPDATE ON public.artifact_recovery_attempts FOR EACH ROW EXECUTE FUNCTION public.validate_artifact_recovery_attempt();
CREATE TRIGGER artifact_verification_lineage_custody BEFORE UPDATE ON public.artifact_verification_jobs FOR EACH ROW EXECUTE FUNCTION public.validate_artifact_verification_lineage();
CREATE TRIGGER assignment_contribution_stamp BEFORE INSERT OR UPDATE ON public.task_assignments FOR EACH ROW EXECUTE FUNCTION public.protect_assignment_contribution_stamp();
CREATE TRIGGER assignment_release_authority BEFORE INSERT ON public.audit_events FOR EACH ROW EXECUTE FUNCTION public.guard_assignment_release_authority();
CREATE TRIGGER audit_events_reject_truncate BEFORE TRUNCATE ON public.audit_events FOR EACH STATEMENT EXECUTE FUNCTION public.reject_audit_event_mutation();
CREATE TRIGGER audit_events_reject_update_delete BEFORE DELETE OR UPDATE ON public.audit_events FOR EACH ROW EXECUTE FUNCTION public.reject_audit_event_mutation();
CREATE TRIGGER audit_events_set_authority_time BEFORE INSERT ON public.audit_events FOR EACH ROW EXECUTE FUNCTION public.set_authority_audit_database_time();
CREATE TRIGGER audit_events_validate_idempotency BEFORE INSERT ON public.audit_events FOR EACH ROW EXECUTE FUNCTION public.validate_linked_authority_event();
CREATE CONSTRAINT TRIGGER authority_control_bootstrap_invariant AFTER INSERT OR DELETE OR UPDATE ON public.authority_control DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_bootstrap_authority_state();
CREATE TRIGGER authority_control_guard BEFORE INSERT OR DELETE OR UPDATE ON public.authority_control FOR EACH ROW EXECUTE FUNCTION public.guard_authority_control();
CREATE TRIGGER authority_control_reject_truncate BEFORE TRUNCATE ON public.authority_control FOR EACH STATEMENT EXECUTE FUNCTION public.reject_authority_control_truncate();
CREATE TRIGGER authority_idempotency_guard BEFORE INSERT OR DELETE OR UPDATE ON public.authority_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.guard_authority_idempotency_record();
CREATE CONSTRAINT TRIGGER authority_idempotency_pending_guard AFTER INSERT OR UPDATE ON public.authority_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.reject_pending_authority_idempotency();
CREATE TRIGGER authority_idempotency_reject_truncate BEFORE TRUNCATE ON public.authority_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_authority_idempotency_truncate();
CREATE TRIGGER compensation_binding_event_change_guard BEFORE DELETE OR UPDATE ON public.compensation_adapter_binding_lifecycle_events FOR EACH ROW EXECUTE FUNCTION public.reject_compensation_binding_lifecycle_event_change();
CREATE TRIGGER compensation_binding_event_insert_guard BEFORE INSERT ON public.compensation_adapter_binding_lifecycle_events FOR EACH ROW EXECUTE FUNCTION public.guard_compensation_binding_lifecycle_event();
CREATE TRIGGER compensation_binding_event_truncate_guard BEFORE TRUNCATE ON public.compensation_adapter_binding_lifecycle_events FOR EACH STATEMENT EXECUTE FUNCTION public.reject_compensation_binding_lifecycle_event_change();
CREATE CONSTRAINT TRIGGER compensation_binding_lifecycle_event_required AFTER INSERT OR UPDATE ON public.project_compensation_adapter_bindings DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_compensation_binding_lifecycle_event();
CREATE TRIGGER compilation_document_evidence_guard BEFORE UPDATE ON public.project_guide_compilation_attempts FOR EACH ROW EXECUTE FUNCTION public.guard_compilation_document_evidence();
CREATE TRIGGER contribution_award_definitions_content_guard BEFORE INSERT OR DELETE OR UPDATE ON public.contribution_award_definitions FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_policy_children();
CREATE CONSTRAINT TRIGGER contribution_award_definitions_graph_guard AFTER INSERT OR DELETE OR UPDATE ON public.contribution_award_definitions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_contribution_policy_graph();
CREATE TRIGGER contribution_award_definitions_published_graph_guard BEFORE INSERT OR DELETE OR UPDATE ON public.contribution_award_definitions FOR EACH ROW EXECUTE FUNCTION public.guard_published_contribution_policy_graph();
CREATE TRIGGER contribution_award_definitions_reject_truncate BEFORE TRUNCATE ON public.contribution_award_definitions FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE CONSTRAINT TRIGGER contribution_policies_graph_guard AFTER INSERT OR DELETE OR UPDATE ON public.contribution_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_contribution_policy_graph();
CREATE TRIGGER contribution_policies_reject_truncate BEFORE TRUNCATE ON public.contribution_policies FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE TRIGGER contribution_policy_custody_change_guard BEFORE DELETE OR UPDATE ON public.contribution_policy_transition_custody FOR EACH ROW EXECUTE FUNCTION public.reject_contribution_policy_event_change();
CREATE CONSTRAINT TRIGGER contribution_policy_custody_guard AFTER INSERT ON public.contribution_policy_transition_custody DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_policy_transition_custody();
CREATE TRIGGER contribution_policy_custody_truncate_guard BEFORE TRUNCATE ON public.contribution_policy_transition_custody FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_event_change();
CREATE TRIGGER contribution_policy_event_change_guard BEFORE DELETE OR UPDATE ON public.contribution_policy_lifecycle_events FOR EACH ROW EXECUTE FUNCTION public.reject_contribution_policy_event_change();
CREATE TRIGGER contribution_policy_event_insert_guard BEFORE INSERT ON public.contribution_policy_lifecycle_events FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_policy_event_insert();
CREATE TRIGGER contribution_policy_event_truncate_guard BEFORE TRUNCATE ON public.contribution_policy_lifecycle_events FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_event_change();
CREATE TRIGGER contribution_policy_row_transition_guard BEFORE UPDATE ON public.contribution_policies FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_policy_row_transition();
CREATE TRIGGER contribution_policy_version_row_transition_guard BEFORE UPDATE ON public.contribution_policy_versions FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_policy_version_row_transition();
CREATE TRIGGER contribution_policy_versions_content_guard BEFORE DELETE OR UPDATE ON public.contribution_policy_versions FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_policy_version_content();
CREATE CONSTRAINT TRIGGER contribution_policy_versions_graph_guard AFTER INSERT OR DELETE OR UPDATE ON public.contribution_policy_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_contribution_policy_graph();
CREATE TRIGGER contribution_policy_versions_reject_truncate BEFORE TRUNCATE ON public.contribution_policy_versions FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE TRIGGER contribution_rules_content_guard BEFORE INSERT OR DELETE OR UPDATE ON public.contribution_rules FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_policy_children();
CREATE CONSTRAINT TRIGGER contribution_rules_graph_guard AFTER INSERT OR DELETE OR UPDATE ON public.contribution_rules DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_contribution_policy_graph();
CREATE TRIGGER contribution_rules_published_graph_guard BEFORE INSERT OR DELETE OR UPDATE ON public.contribution_rules FOR EACH ROW EXECUTE FUNCTION public.guard_published_contribution_policy_graph();
CREATE TRIGGER contribution_rules_reject_truncate BEFORE TRUNCATE ON public.contribution_rules FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE CONSTRAINT TRIGGER effective_submission_policy_custody AFTER INSERT OR UPDATE ON public.effective_project_submission_artifact_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_submission_policy_authority_custody();
CREATE TRIGGER effective_submission_policy_provenance_immutable BEFORE UPDATE ON public.effective_project_submission_artifact_policies FOR EACH ROW EXECUTE FUNCTION public.protect_submission_policy_output_provenance();
CREATE CONSTRAINT TRIGGER finalization_atomic_custody AFTER INSERT OR UPDATE ON public.project_guide_setup_finalizations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_project_setup_finalization_custody();
CREATE CONSTRAINT TRIGGER finalization_atomic_custody AFTER INSERT OR UPDATE ON public.project_setup_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN ((((new.status)::text = ANY ((ARRAY['sufficiency_blocked'::character varying, 'policy_draft_ready'::character varying])::text[])) OR (new.output_sufficiency_report_id IS NOT NULL) OR (new.output_submission_artifact_policy_id IS NOT NULL))) EXECUTE FUNCTION public.validate_project_setup_finalization_custody();
CREATE TRIGGER finalization_change_guard BEFORE DELETE OR UPDATE ON public.project_guide_setup_finalizations FOR EACH ROW EXECUTE FUNCTION public.reject_project_guide_projection_change();
CREATE TRIGGER finalization_insert_guard BEFORE INSERT ON public.project_guide_setup_finalizations FOR EACH ROW EXECUTE FUNCTION public.guard_project_guide_setup_finalization();
CREATE TRIGGER finalization_setup_change_guard BEFORE DELETE OR UPDATE ON public.project_setup_runs FOR EACH ROW EXECUTE FUNCTION public.guard_finalized_project_setup();
CREATE TRIGGER finalization_setup_truncate_guard BEFORE TRUNCATE ON public.project_setup_runs FOR EACH STATEMENT EXECUTE FUNCTION public.guard_finalized_project_setup();
CREATE TRIGGER finalization_truncate_guard BEFORE TRUNCATE ON public.project_guide_setup_finalizations FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_guide_projection_change();
CREATE TRIGGER guide_compilation_request_change_guard BEFORE DELETE OR UPDATE ON public.project_guide_compilation_request_operations FOR EACH ROW EXECUTE FUNCTION public.reject_project_guide_compilation_request_change();
CREATE TRIGGER guide_compilation_request_insert_guard BEFORE INSERT ON public.project_guide_compilation_request_operations FOR EACH ROW EXECUTE FUNCTION public.guard_project_guide_compilation_request_operation();
CREATE TRIGGER guide_compilation_request_truncate_guard BEFORE TRUNCATE ON public.project_guide_compilation_request_operations FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_guide_compilation_request_change();
CREATE TRIGGER guide_document_access_guard BEFORE INSERT OR DELETE OR UPDATE ON public.project_guide_document_accesses FOR EACH ROW EXECUTE FUNCTION public.guard_guide_document_access();
CREATE TRIGGER guide_document_access_truncate_guard BEFORE TRUNCATE ON public.project_guide_document_accesses FOR EACH STATEMENT EXECUTE FUNCTION public.guard_guide_document_access();
CREATE TRIGGER guide_lineage_lifecycle_guard BEFORE INSERT OR UPDATE ON public.project_guides FOR EACH ROW EXECUTE FUNCTION public.guard_guide_lineage_and_lifecycle();
CREATE TRIGGER guide_mutation_idempotency_guard BEFORE INSERT OR DELETE OR UPDATE ON public.guide_mutation_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.guard_guide_mutation_idempotency();
CREATE TRIGGER guide_mutation_idempotency_reject_truncate BEFORE TRUNCATE ON public.guide_mutation_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_guide_mutation_idempotency_truncate();
CREATE CONSTRAINT TRIGGER guide_mutation_product_custody AFTER INSERT OR UPDATE ON public.project_guides DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_guide_mutation_custody();
CREATE CONSTRAINT TRIGGER guide_mutation_reservation_custody AFTER INSERT OR UPDATE ON public.guide_mutation_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_guide_mutation_custody();
CREATE CONSTRAINT TRIGGER guide_proposal_approval_custody AFTER INSERT OR UPDATE ON public.effective_project_submission_artifact_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_guide_proposal_approval();
CREATE CONSTRAINT TRIGGER guide_proposal_approval_custody AFTER INSERT OR UPDATE ON public.pre_submit_checker_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_guide_proposal_approval();
CREATE CONSTRAINT TRIGGER guide_proposal_approval_custody AFTER INSERT OR UPDATE ON public.project_guide_proposal_approvals DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_guide_proposal_approval();
CREATE CONSTRAINT TRIGGER guide_proposal_approval_custody AFTER INSERT OR UPDATE ON public.submission_artifact_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_guide_proposal_approval();
CREATE CONSTRAINT TRIGGER guide_proposal_approval_custody AFTER INSERT OR UPDATE ON public.submission_policy_mutation_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_guide_proposal_approval();
CREATE TRIGGER guide_proposal_content_immutable BEFORE UPDATE ON public.effective_project_submission_artifact_policies FOR EACH ROW EXECUTE FUNCTION public.protect_guide_proposal_content();
CREATE TRIGGER guide_proposal_content_immutable BEFORE UPDATE ON public.pre_submit_checker_policies FOR EACH ROW EXECUTE FUNCTION public.protect_guide_proposal_content();
CREATE TRIGGER guide_proposal_content_immutable BEFORE UPDATE ON public.submission_artifact_policies FOR EACH ROW EXECUTE FUNCTION public.protect_guide_proposal_content();
CREATE CONSTRAINT TRIGGER guide_proposal_correction_custody AFTER INSERT ON public.project_guide_proposal_corrections DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_guide_proposal_correction();
CREATE CONSTRAINT TRIGGER guide_proposal_correction_custody AFTER INSERT OR UPDATE ON public.project_setup_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_guide_proposal_correction();
CREATE TRIGGER guide_runtime_allocation_guard BEFORE INSERT OR DELETE OR UPDATE ON public.project_guide_runtime_allocations FOR EACH ROW EXECUTE FUNCTION public.guard_guide_runtime_allocation();
CREATE TRIGGER guide_runtime_allocation_truncate_guard BEFORE TRUNCATE ON public.project_guide_runtime_allocations FOR EACH STATEMENT EXECUTE FUNCTION public.guard_guide_runtime_allocation();
CREATE TRIGGER guide_setup_snapshot_ownership_guard BEFORE INSERT OR UPDATE ON public.project_setup_runs FOR EACH ROW EXECUTE FUNCTION public.validate_guide_task_example_source_custody();
CREATE TRIGGER guide_snapshot_task_examples_guard BEFORE INSERT ON public.guide_source_snapshots FOR EACH ROW EXECUTE FUNCTION public.validate_guide_task_example_source_custody();
CREATE CONSTRAINT TRIGGER guide_source_snapshot_items_custody AFTER INSERT ON public.guide_source_snapshot_items DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_guide_source_snapshot_items();
CREATE TRIGGER guide_source_snapshot_items_immutable BEFORE DELETE OR UPDATE OR TRUNCATE ON public.guide_source_snapshot_items FOR EACH STATEMENT EXECUTE FUNCTION public.reject_guide_source_snapshot_item_mutation();
CREATE CONSTRAINT TRIGGER guide_task_examples_create_custody AFTER INSERT ON public.project_guides DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_guide_task_examples_create_custody();
CREATE TRIGGER immutable_guide_proposal_operation BEFORE DELETE OR UPDATE ON public.project_guide_proposal_approvals FOR EACH ROW EXECUTE FUNCTION public.reject_guide_proposal_change();
CREATE TRIGGER immutable_guide_proposal_operation BEFORE DELETE OR UPDATE ON public.project_guide_proposal_corrections FOR EACH ROW EXECUTE FUNCTION public.reject_guide_proposal_change();
CREATE TRIGGER immutable_guide_proposal_operation_truncate BEFORE TRUNCATE ON public.project_guide_proposal_approvals FOR EACH STATEMENT EXECUTE FUNCTION public.reject_guide_proposal_change();
CREATE TRIGGER immutable_guide_proposal_operation_truncate BEFORE TRUNCATE ON public.project_guide_proposal_corrections FOR EACH STATEMENT EXECUTE FUNCTION public.reject_guide_proposal_change();
CREATE TRIGGER immutable_post_policy_content BEFORE DELETE OR UPDATE ON public.checker_policies FOR EACH ROW EXECUTE FUNCTION public.guard_post_policy_change();
CREATE TRIGGER immutable_post_policy_operation BEFORE DELETE OR UPDATE ON public.project_post_policy_operations FOR EACH ROW EXECUTE FUNCTION public.reject_guide_proposal_change();
CREATE TRIGGER immutable_post_policy_operation_truncate BEFORE TRUNCATE ON public.project_post_policy_operations FOR EACH STATEMENT EXECUTE FUNCTION public.reject_guide_proposal_change();
CREATE TRIGGER immutable_post_policy_truncate BEFORE TRUNCATE ON public.checker_policies FOR EACH STATEMENT EXECUTE FUNCTION public.guard_post_policy_change();
CREATE TRIGGER iso_4217_currency_codes_immutable BEFORE INSERT OR DELETE OR UPDATE ON public.iso_4217_currency_codes FOR EACH ROW EXECUTE FUNCTION public.guard_iso_4217_currency_codes();
CREATE TRIGGER iso_4217_currency_codes_reject_truncate BEFORE TRUNCATE ON public.iso_4217_currency_codes FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE CONSTRAINT TRIGGER outbox_attempt_delivery_custody AFTER INSERT OR UPDATE ON public.outbox_delivery_attempts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_outbox_delivery_projection();
CREATE TRIGGER outbox_delivery_attempt_guard BEFORE INSERT OR DELETE OR UPDATE ON public.outbox_delivery_attempts FOR EACH ROW EXECUTE FUNCTION public.guard_outbox_delivery_attempt();
CREATE TRIGGER outbox_delivery_attempt_truncate_guard BEFORE TRUNCATE ON public.outbox_delivery_attempts FOR EACH STATEMENT EXECUTE FUNCTION public.guard_outbox_delivery_attempt();
CREATE TRIGGER outbox_delivery_authority_guard BEFORE INSERT OR UPDATE ON public.outbox_delivery_attempts FOR EACH ROW EXECUTE FUNCTION public.require_outbox_phase_authority();
CREATE CONSTRAINT TRIGGER outbox_event_delivery_custody AFTER INSERT OR UPDATE ON public.outbox_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_outbox_delivery_projection();
CREATE TRIGGER outbox_events_custody BEFORE INSERT OR DELETE OR UPDATE ON public.outbox_events FOR EACH ROW EXECUTE FUNCTION public.guard_outbox_event();
CREATE TRIGGER outbox_events_reject_truncate BEFORE TRUNCATE ON public.outbox_events FOR EACH STATEMENT EXECUTE FUNCTION public.guard_outbox_event();
CREATE CONSTRAINT TRIGGER policy_mutation_replay_custody AFTER INSERT OR UPDATE ON public.policy_mutation_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_policy_mutation_custody();
CREATE TRIGGER policy_mutation_replay_immutable BEFORE INSERT OR DELETE OR UPDATE ON public.policy_mutation_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.guard_policy_mutation_replay();
CREATE TRIGGER policy_mutation_replay_reject_truncate BEFORE TRUNCATE ON public.policy_mutation_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_policy_mutation_replay_truncate();
CREATE CONSTRAINT TRIGGER post_policy_operation_custody AFTER INSERT ON public.project_post_policy_operations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_post_policy_operation();
CREATE CONSTRAINT TRIGGER post_policy_output_custody AFTER INSERT OR UPDATE ON public.checker_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_post_policy_custody();
CREATE CONSTRAINT TRIGGER pre_submit_attempt_completion AFTER INSERT OR UPDATE ON public.pre_submit_execution_attempts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_pre_submit_attempt_evidence();
CREATE TRIGGER pre_submit_attempt_guard BEFORE INSERT OR DELETE OR UPDATE ON public.pre_submit_execution_attempts FOR EACH ROW EXECUTE FUNCTION public.guard_pre_submit_attempt();
CREATE TRIGGER pre_submit_attempt_no_truncate BEFORE TRUNCATE ON public.pre_submit_execution_attempts FOR EACH STATEMENT EXECUTE FUNCTION public.guard_pre_submit_attempt();
CREATE CONSTRAINT TRIGGER pre_submit_evidence_attempt AFTER INSERT ON public.pre_submit_evidence_sets DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_pre_submit_attempt_evidence();
CREATE TRIGGER pre_submit_evidence_results_immutable BEFORE DELETE OR UPDATE ON public.pre_submit_evidence_results FOR EACH ROW EXECUTE FUNCTION public.guard_pre_submit_evidence_results_immutable();
CREATE TRIGGER pre_submit_evidence_results_membership BEFORE INSERT ON public.pre_submit_evidence_results FOR EACH ROW EXECUTE FUNCTION public.guard_pre_submit_evidence_result_membership();
CREATE TRIGGER pre_submit_evidence_results_no_truncate BEFORE TRUNCATE ON public.pre_submit_evidence_results FOR EACH STATEMENT EXECUTE FUNCTION public.guard_pre_submit_evidence_results_immutable();
CREATE TRIGGER pre_submit_evidence_sets_creation BEFORE INSERT ON public.pre_submit_evidence_sets FOR EACH ROW EXECUTE FUNCTION public.guard_pre_submit_evidence_set_creation();
CREATE TRIGGER pre_submit_evidence_sets_immutable BEFORE DELETE OR UPDATE ON public.pre_submit_evidence_sets FOR EACH ROW EXECUTE FUNCTION public.guard_pre_submit_evidence_sets_immutable();
CREATE TRIGGER pre_submit_evidence_sets_no_truncate BEFORE TRUNCATE ON public.pre_submit_evidence_sets FOR EACH STATEMENT EXECUTE FUNCTION public.guard_pre_submit_evidence_sets_immutable();
CREATE CONSTRAINT TRIGGER pre_submit_policy_custody AFTER INSERT OR UPDATE ON public.pre_submit_checker_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_submission_policy_authority_custody();
CREATE TRIGGER pre_submit_policy_provenance_immutable BEFORE UPDATE ON public.pre_submit_checker_policies FOR EACH ROW EXECUTE FUNCTION public.protect_submission_policy_output_provenance();
CREATE TRIGGER pre_submit_result_reconstruction BEFORE INSERT ON public.pre_submit_evidence_results FOR EACH ROW EXECUTE FUNCTION public.require_pre_submit_result_reconstruction();
CREATE CONSTRAINT TRIGGER project_activation_custody AFTER UPDATE OF status ON public.projects DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_project_activation_custody();
CREATE TRIGGER project_compensation_binding_update_guard BEFORE UPDATE ON public.project_compensation_adapter_bindings FOR EACH ROW EXECUTE FUNCTION public.enforce_compensation_binding_lifecycle();
CREATE TRIGGER project_compensation_units_lifecycle_guard BEFORE INSERT OR DELETE OR UPDATE ON public.project_compensation_units FOR EACH ROW EXECUTE FUNCTION public.guard_project_compensation_units();
CREATE TRIGGER project_compensation_units_reject_truncate BEFORE TRUNCATE ON public.project_compensation_units FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_policy_truncate();
CREATE TRIGGER project_create_idempotency_guard BEFORE INSERT OR DELETE OR UPDATE ON public.project_create_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.guard_project_create_idempotency();
CREATE TRIGGER project_create_idempotency_reject_truncate BEFORE TRUNCATE ON public.project_create_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_create_idempotency_truncate();
CREATE CONSTRAINT TRIGGER project_create_reservation_custody AFTER INSERT OR UPDATE ON public.project_create_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_project_create_custody();
CREATE CONSTRAINT TRIGGER project_creation_custody AFTER INSERT OR UPDATE OF created_by_actor_profile_id, created_via_identity_link_id, created_by_admin_role_grant_id, creation_scope_type, creation_action_id, authorization_decision_event_id ON public.projects DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_project_create_custody();
CREATE TRIGGER project_guide_runtime_configuration_guard BEFORE INSERT OR UPDATE ON public.project_guide_compilation_attempts FOR EACH ROW EXECUTE FUNCTION public.guard_project_guide_runtime_configuration();
CREATE TRIGGER project_guide_task_examples_guard BEFORE INSERT OR DELETE OR UPDATE ON public.project_guides FOR EACH ROW EXECUTE FUNCTION public.guard_project_guide_task_examples();
CREATE TRIGGER project_guide_task_examples_truncate_guard BEFORE TRUNCATE ON public.project_guides FOR EACH STATEMENT EXECUTE FUNCTION public.guard_project_guide_task_examples();
CREATE TRIGGER project_guides_policy_selection_immutable BEFORE UPDATE ON public.project_guides FOR EACH ROW EXECUTE FUNCTION public.guard_project_guide_policy_selection();
CREATE TRIGGER projected_policy_delete_guard BEFORE DELETE ON public.submission_artifact_policies FOR EACH ROW EXECUTE FUNCTION public.reject_compilation_projection_business_delete();
CREATE TRIGGER projected_policy_truncate_guard BEFORE TRUNCATE ON public.submission_artifact_policies FOR EACH STATEMENT EXECUTE FUNCTION public.reject_compilation_projection_business_truncate();
CREATE TRIGGER projected_policy_update_guard BEFORE UPDATE ON public.submission_artifact_policies FOR EACH ROW EXECUTE FUNCTION public.guard_compilation_projection_business_change();
CREATE TRIGGER projected_report_delete_guard BEFORE DELETE ON public.guide_sufficiency_reports FOR EACH ROW EXECUTE FUNCTION public.reject_compilation_projection_business_delete();
CREATE TRIGGER projected_report_truncate_guard BEFORE TRUNCATE ON public.guide_sufficiency_reports FOR EACH STATEMENT EXECUTE FUNCTION public.reject_compilation_projection_business_truncate();
CREATE TRIGGER projected_report_update_guard BEFORE UPDATE ON public.guide_sufficiency_reports FOR EACH ROW EXECUTE FUNCTION public.guard_compilation_projection_business_change();
CREATE TRIGGER projected_usage_delete_guard BEFORE DELETE OR UPDATE ON public.guide_sufficiency_report_source_usages FOR EACH ROW EXECUTE FUNCTION public.reject_compilation_projection_business_delete();
CREATE TRIGGER projected_usage_insert_guard BEFORE INSERT ON public.guide_sufficiency_report_source_usages FOR EACH ROW EXECUTE FUNCTION public.guard_compilation_projection_source_usage_insert();
CREATE TRIGGER projected_usage_truncate_guard BEFORE TRUNCATE ON public.guide_sufficiency_report_source_usages FOR EACH STATEMENT EXECUTE FUNCTION public.reject_compilation_projection_business_truncate();
CREATE TRIGGER projection_operation_change_guard BEFORE DELETE OR UPDATE ON public.project_guide_component_projection_operations FOR EACH ROW EXECUTE FUNCTION public.reject_project_guide_projection_change();
CREATE TRIGGER projection_operation_insert_guard BEFORE INSERT ON public.project_guide_component_projection_operations FOR EACH ROW EXECUTE FUNCTION public.guard_project_guide_component_projection_operation();
CREATE TRIGGER projection_operation_truncate_guard BEFORE TRUNCATE ON public.project_guide_component_projection_operations FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_guide_projection_change();
CREATE CONSTRAINT TRIGGER require_document_creation_pair AFTER INSERT ON public.guide_mutation_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_guide_document_creation_pair();
CREATE CONSTRAINT TRIGGER require_document_creation_pair AFTER INSERT ON public.guide_source_snapshots DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_guide_document_creation_pair();
CREATE CONSTRAINT TRIGGER require_document_creation_pair AFTER INSERT ON public.project_guides DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.require_guide_document_creation_pair();
CREATE TRIGGER retained_guide_content_guard BEFORE INSERT OR UPDATE ON public.project_guides FOR EACH ROW EXECUTE FUNCTION public.guard_retained_guide_source_fields();
CREATE TRIGGER retained_guide_continuation_guard BEFORE INSERT OR UPDATE ON public.project_setup_runs FOR EACH ROW EXECUTE FUNCTION public.guard_retained_guide_source_fields();
CREATE TRIGGER retired_guide_material_write_guard BEFORE INSERT OR DELETE OR UPDATE OR TRUNCATE ON public.guide_source_artifact_bindings FOR EACH STATEMENT EXECUTE FUNCTION public.reject_retired_guide_material_write();
CREATE TRIGGER retired_guide_material_write_guard BEFORE INSERT OR DELETE OR UPDATE OR TRUNCATE ON public.guide_source_extracted_contents FOR EACH STATEMENT EXECUTE FUNCTION public.reject_retired_guide_material_write();
CREATE TRIGGER retired_guide_material_write_guard BEFORE INSERT OR DELETE OR UPDATE OR TRUNCATE ON public.guide_source_extraction_attempts FOR EACH STATEMENT EXECUTE FUNCTION public.reject_retired_guide_material_write();
CREATE TRIGGER retired_guide_material_write_guard BEFORE INSERT OR DELETE OR UPDATE OR TRUNCATE ON public.guide_source_extraction_retry_budgets FOR EACH STATEMENT EXECUTE FUNCTION public.reject_retired_guide_material_write();
CREATE TRIGGER retired_guide_material_write_guard BEFORE INSERT OR DELETE OR UPDATE OR TRUNCATE ON public.guide_source_extraction_usages FOR EACH STATEMENT EXECUTE FUNCTION public.reject_retired_guide_material_write();
CREATE TRIGGER retired_guide_material_write_guard BEFORE INSERT OR DELETE OR UPDATE OR TRUNCATE ON public.guide_source_format_classifications FOR EACH STATEMENT EXECUTE FUNCTION public.reject_retired_guide_material_write();
CREATE TRIGGER retired_guide_material_write_guard BEFORE INSERT OR DELETE OR UPDATE OR TRUNCATE ON public.guide_sufficiency_report_source_usages FOR EACH STATEMENT EXECUTE FUNCTION public.reject_retired_guide_material_write();
CREATE TRIGGER review_admission_idempotency_records_reject_truncate BEFORE TRUNCATE ON public.review_admission_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_review_queue_foundation_truncate();
CREATE TRIGGER review_admission_records_guard BEFORE INSERT OR DELETE OR UPDATE ON public.review_admission_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.guard_review_admission_record();
CREATE CONSTRAINT TRIGGER review_leases_active_lease_guard AFTER INSERT OR UPDATE ON public.review_leases DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_review_active_lease();
CREATE TRIGGER review_leases_guard BEFORE INSERT OR DELETE OR UPDATE ON public.review_leases FOR EACH ROW EXECUTE FUNCTION public.guard_review_lease();
CREATE TRIGGER review_leases_reject_truncate BEFORE TRUNCATE ON public.review_leases FOR EACH STATEMENT EXECUTE FUNCTION public.reject_review_lease_truncate();
CREATE TRIGGER review_policies_immutable BEFORE DELETE OR UPDATE ON public.review_policies FOR EACH ROW EXECUTE FUNCTION public.guard_review_policies_immutable();
CREATE TRIGGER review_policies_reject_truncate BEFORE TRUNCATE ON public.review_policies FOR EACH STATEMENT EXECUTE FUNCTION public.guard_review_policies_immutable();
CREATE CONSTRAINT TRIGGER review_policy_mutation_custody AFTER INSERT OR UPDATE ON public.review_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_policy_mutation_custody();
CREATE CONSTRAINT TRIGGER review_queue_entries_active_lease_guard AFTER INSERT OR UPDATE ON public.review_queue_entries DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_review_active_lease();
CREATE TRIGGER review_queue_entries_guard BEFORE INSERT OR DELETE OR UPDATE ON public.review_queue_entries FOR EACH ROW EXECUTE FUNCTION public.guard_review_queue_entry();
CREATE TRIGGER review_queue_entries_reject_truncate BEFORE TRUNCATE ON public.review_queue_entries FOR EACH STATEMENT EXECUTE FUNCTION public.reject_review_queue_foundation_truncate();
CREATE TRIGGER revision_policies_immutable BEFORE DELETE OR UPDATE ON public.revision_policies FOR EACH ROW EXECUTE FUNCTION public.guard_revision_policies_immutable();
CREATE TRIGGER revision_policies_reject_truncate BEFORE TRUNCATE ON public.revision_policies FOR EACH STATEMENT EXECUTE FUNCTION public.guard_revision_policies_immutable();
CREATE CONSTRAINT TRIGGER revision_policy_mutation_custody AFTER INSERT OR UPDATE ON public.revision_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_policy_mutation_custody();
CREATE TRIGGER service_identity_migration_evidence_row_guard BEFORE DELETE OR UPDATE ON public.actor_profile_migration_state FOR EACH ROW EXECUTE FUNCTION public.guard_service_identity_migration_evidence();
CREATE TRIGGER service_identity_migration_evidence_truncate_guard BEFORE TRUNCATE ON public.actor_profile_migration_state FOR EACH STATEMENT EXECUTE FUNCTION public.guard_service_identity_migration_evidence();
CREATE CONSTRAINT TRIGGER source_setup_run_custody AFTER INSERT OR UPDATE ON public.project_setup_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_guide_mutation_custody();
CREATE CONSTRAINT TRIGGER source_snapshot_product_custody AFTER INSERT OR UPDATE ON public.guide_source_snapshots DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_guide_mutation_custody();
CREATE TRIGGER submission_bundle_admission_delete BEFORE DELETE OR TRUNCATE ON public.submission_bundle_admissions FOR EACH STATEMENT EXECUTE FUNCTION public.guard_submission_bundle_admission_delete();
CREATE TRIGGER submission_bundle_admission_lineage BEFORE UPDATE ON public.submission_bundle_admissions FOR EACH ROW EXECUTE FUNCTION public.guard_submission_bundle_admission_lineage();
CREATE TRIGGER submission_bundle_admission_verified_lineage BEFORE INSERT ON public.submission_bundle_admissions FOR EACH ROW EXECUTE FUNCTION public.guard_submission_bundle_admission_verified_lineage();
CREATE TRIGGER submission_bundle_durable_intent_put_attempt BEFORE INSERT ON public.submission_bundle_durable_intents FOR EACH ROW EXECUTE FUNCTION public.guard_submission_bundle_durable_intent_put_attempt();
CREATE TRIGGER submission_bundle_durable_intents_immutable BEFORE DELETE OR UPDATE ON public.submission_bundle_durable_intents FOR EACH ROW EXECUTE FUNCTION public.guard_submission_bundle_durable_intents_immutable();
CREATE TRIGGER submission_bundle_durable_intents_no_truncate BEFORE TRUNCATE ON public.submission_bundle_durable_intents FOR EACH STATEMENT EXECUTE FUNCTION public.guard_submission_bundle_durable_intents_immutable();
CREATE TRIGGER submission_contribution_immutable BEFORE UPDATE ON public.submissions FOR EACH ROW EXECUTE FUNCTION public.protect_submission_contribution_stamp();
CREATE TRIGGER submission_contribution_stamp BEFORE INSERT ON public.submissions FOR EACH ROW EXECUTE FUNCTION public.require_submission_contribution_stamp();
CREATE TRIGGER submission_policy_approval_provenance_immutable BEFORE UPDATE ON public.submission_artifact_policies FOR EACH ROW EXECUTE FUNCTION public.protect_submission_policy_approval_provenance();
CREATE CONSTRAINT TRIGGER submission_policy_creation_custody AFTER INSERT OR UPDATE ON public.submission_artifact_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.validate_submission_policy_creation_custody();
CREATE TRIGGER submission_policy_creation_provenance_immutable BEFORE UPDATE ON public.submission_artifact_policies FOR EACH ROW EXECUTE FUNCTION public.protect_submission_policy_creation_provenance();
CREATE CONSTRAINT TRIGGER submission_policy_product_custody AFTER INSERT OR UPDATE ON public.submission_artifact_policies DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN ((((new.derivation_source)::text <> 'unified_compilation'::text) OR (new.approval_action_id IS NOT NULL))) EXECUTE FUNCTION public.validate_submission_policy_authority_custody();
CREATE CONSTRAINT TRIGGER submission_policy_replay_custody AFTER INSERT OR UPDATE ON public.submission_policy_mutation_idempotency_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (((new.status)::text = 'committed'::text)) EXECUTE FUNCTION public.validate_submission_policy_authority_custody();
ALTER TABLE ONLY public.project_create_idempotency_records ADD CONSTRAINT ck_project_create_idempotency_records_operation_id_uuid7 CHECK (((get_byte(uuid_send(operation_id), 6) >> 4) = 7) AND ((get_byte(uuid_send(operation_id), 8) & 192) = 128));
ALTER TABLE ONLY public.guide_mutation_idempotency_records ADD CONSTRAINT ck_guide_mutation_idempotency_records_operation_id_uuid7 CHECK (((get_byte(uuid_send(operation_id), 6) >> 4) = 7) AND ((get_byte(uuid_send(operation_id), 8) & 192) = 128));
ALTER TABLE ONLY public.guide_sufficiency_mutation_idempotency_records ADD CONSTRAINT ck_guide_sufficiency_mutation_idempotency_records_opera_d8fb CHECK (((get_byte(uuid_send(operation_id), 6) >> 4) = 7) AND ((get_byte(uuid_send(operation_id), 8) & 192) = 128));
ALTER TABLE ONLY public.submission_policy_mutation_idempotency_records ADD CONSTRAINT ck_submission_policy_mutation_idempotency_records_opera_94d5 CHECK (((get_byte(uuid_send(operation_id), 6) >> 4) = 7) AND ((get_byte(uuid_send(operation_id), 8) & 192) = 128));
ALTER TABLE ONLY public.policy_mutation_idempotency_records ADD CONSTRAINT ck_policy_mutation_idempotency_records_operation_id_uuid7 CHECK (((get_byte(uuid_send(operation_id), 6) >> 4) = 7) AND ((get_byte(uuid_send(operation_id), 8) & 192) = 128));
ALTER TABLE ONLY public.project_guide_setup_finalizations ADD CONSTRAINT ck_project_guide_setup_finalizations_operation_id_uuid7 CHECK (((get_byte(uuid_send(operation_id), 6) >> 4) = 7) AND ((get_byte(uuid_send(operation_id), 8) & 192) = 128));
ALTER TABLE ONLY public.project_guides ADD CONSTRAINT ck_project_guides_activation_operation_id_uuid7 CHECK (activation_operation_id IS NULL OR (((get_byte(uuid_send(activation_operation_id), 6) >> 4) = 7) AND ((get_byte(uuid_send(activation_operation_id), 8) & 192) = 128)));
CREATE TRIGGER submissions_contributor_human BEFORE INSERT OR UPDATE OF contributor_id ON public.submissions FOR EACH ROW EXECUTE FUNCTION public.require_human_actor_profile_reference('contributor_id');
CREATE TRIGGER task_assignments_contributor_human BEFORE INSERT OR UPDATE OF contributor_id ON public.task_assignments FOR EACH ROW EXECUTE FUNCTION public.require_human_actor_profile_reference('contributor_id');
CREATE TRIGGER task_command_receipt_immutable BEFORE DELETE OR UPDATE ON public.task_command_receipts FOR EACH ROW EXECUTE FUNCTION public.protect_task_command_receipt();
CREATE TRIGGER task_command_receipt_no_truncate BEFORE TRUNCATE ON public.task_command_receipts FOR EACH STATEMENT EXECUTE FUNCTION public.protect_task_command_receipt();
CREATE TRIGGER task_contribution_stamp BEFORE INSERT OR UPDATE ON public.workstream_tasks FOR EACH ROW EXECUTE FUNCTION public.protect_task_contribution_stamp();
CREATE TRIGGER task_management_audit BEFORE INSERT ON public.audit_events FOR EACH ROW EXECUTE FUNCTION public.guard_task_management_audit();
CREATE CONSTRAINT TRIGGER trg_artifact_binding_history AFTER INSERT ON public.artifact_bindings DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION public.validate_artifact_binding_history();
CREATE TRIGGER trg_artifact_bindings_immutable BEFORE DELETE OR UPDATE ON public.artifact_bindings FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_artifact_contents_immutable BEFORE DELETE OR UPDATE ON public.artifact_contents FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_artifact_operation_receipts_immutable BEFORE DELETE OR UPDATE ON public.artifact_operation_receipts FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_artifact_put_observation_receipts_immutable BEFORE DELETE OR UPDATE ON public.artifact_put_observation_receipts FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_artifact_storage_namespaces_immutable BEFORE DELETE OR UPDATE ON public.artifact_storage_namespaces FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_artifact_verification_receipts_immutable BEFORE DELETE OR UPDATE ON public.artifact_verification_receipts FOR EACH ROW EXECUTE FUNCTION public.reject_artifact_fact_mutation();
CREATE TRIGGER trg_compilation_attempt_delete BEFORE DELETE OR TRUNCATE ON public.project_guide_compilation_attempts FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_guide_compilation_mutation();
CREATE TRIGGER trg_compilation_attempt_update BEFORE UPDATE ON public.project_guide_compilation_attempts FOR EACH ROW EXECUTE FUNCTION public.guard_project_guide_compilation_attempt_update();
CREATE TRIGGER trg_compilation_insert BEFORE INSERT ON public.project_guide_compilations FOR EACH ROW EXECUTE FUNCTION public.guard_project_guide_compilation_insert();
CREATE TRIGGER trg_compilation_mutation BEFORE DELETE OR UPDATE OR TRUNCATE ON public.project_guide_compilations FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_guide_compilation_mutation();
CREATE TRIGGER trg_project_role_grants_history BEFORE INSERT OR DELETE OR UPDATE ON public.project_role_grants FOR EACH ROW EXECUTE FUNCTION public.guard_project_role_grant_history();
CREATE TRIGGER trg_project_role_grants_reject_truncate BEFORE TRUNCATE ON public.project_role_grants FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_role_history_truncate();
CREATE TRIGGER trg_project_role_qualification_snapshots_immutable BEFORE INSERT OR DELETE OR UPDATE ON public.project_role_qualification_snapshots FOR EACH ROW EXECUTE FUNCTION public.guard_project_role_snapshot_history();
CREATE TRIGGER trg_project_role_snapshots_reject_truncate BEFORE TRUNCATE ON public.project_role_qualification_snapshots FOR EACH STATEMENT EXECUTE FUNCTION public.reject_project_role_history_truncate();
CREATE TRIGGER trg_submission_policy_replay_immutable BEFORE DELETE OR UPDATE ON public.submission_policy_mutation_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.reject_submission_policy_replay_mutation();
CREATE TRIGGER trg_submission_policy_replay_no_truncate BEFORE TRUNCATE ON public.submission_policy_mutation_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_submission_policy_replay_truncate();
CREATE TRIGGER trg_sufficiency_replay_immutable BEFORE DELETE OR UPDATE ON public.guide_sufficiency_mutation_idempotency_records FOR EACH ROW EXECUTE FUNCTION public.reject_sufficiency_replay_mutation();
CREATE TRIGGER trg_sufficiency_replay_no_truncate BEFORE TRUNCATE ON public.guide_sufficiency_mutation_idempotency_records FOR EACH STATEMENT EXECUTE FUNCTION public.reject_sufficiency_replay_truncate();
