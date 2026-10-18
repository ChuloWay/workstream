"""Admit exact uncertain delivery evidence and recovery routing custody."""

from alembic import op
from sqlalchemy import text


revision = "0055_delivery_reconciliation"
down_revision = "0054_artifact_proof_timing"
branch_labels = None
depends_on = None


_CONSTRAINT = "ck_audit_events_authorization_action_evidence"
_PRIVACY_CONSTRAINT = "ck_audit_events_authority_privacy_bounds"
_ROUTING_GUARD = "public.guard_task_routing_authority()"
_ANCHOR = (
    "(((action_id)::text = 'operations.checker_retry_source.list'::text) AND "
    "((permission_id)::text = 'operations.status.read'::text))"
)
_PAIRS = (
    (
        "(((action_id)::text = 'operations.post_submit_delivery.list'::text) AND "
        "((permission_id)::text = 'operations.status.read'::text))"
    ),
    (
        "(((action_id)::text = 'operations.post_submit_delivery.reconcile'::text) AND "
        "((permission_id)::text = 'operations.reconcile.run'::text))"
    ),
)


def _definition(name: str) -> str:
    return op.get_bind().execute(
        text(
            "select pg_get_constraintdef(oid) from pg_catalog.pg_constraint "
            "where conrelid='public.audit_events'::regclass and conname=:name"
        ),
        {"name": name},
    ).scalar_one()


def _replace(name: str, definition: str) -> None:
    op.execute(f"alter table public.audit_events drop constraint {name}")
    op.execute(
        f"alter table public.audit_events add constraint {name} {definition}"
    )


def _replace_function(signature: str, old: str, new: str) -> None:
    """Refuse to modify an unexpected predecessor custody function."""
    body = op.get_bind().execute(
        text(
            "select pg_catalog.pg_get_functiondef("
            "cast(:signature as regprocedure))"
        ),
        {"signature": signature},
    ).scalar_one()
    if body.count(old) != 1:
        raise RuntimeError(
            "operational delivery routing predecessor changed: " + signature
        )
    op.execute(body.replace(old, new))


def upgrade() -> None:
    definition = _definition(_CONSTRAINT)
    if definition.count(_ANCHOR) != 2 or any(pair in definition for pair in _PAIRS):
        raise RuntimeError(
            "operational delivery audit predecessor constraint shape changed"
        )
    additions = "".join(f" OR {pair}" for pair in _PAIRS)
    _replace(_CONSTRAINT, definition.replace(_ANCHOR, _ANCHOR + additions))

    definition = _definition(_PRIVACY_CONSTRAINT)
    resource_start = definition.index("resource_type IS NULL")
    target_start = definition.index("target_ref_kind IS NULL")
    resource_registry = definition[resource_start:target_start]
    addition = "('outbox_delivery'::character varying)::text, "
    if addition in definition or resource_registry.count("ARRAY[") != 1:
        raise RuntimeError(
            "operational delivery audit privacy constraint shape changed"
        )
    index = definition.index("ARRAY[", resource_start) + len("ARRAY[")
    _replace(
        _PRIVACY_CONSTRAINT,
        definition[:index] + addition + definition[index:],
    )
    _extend_routing_custody()


def _extend_routing_custody() -> None:
    """Bind a recovered completion to its terminal original and live child."""
    _replace_function(
        "public.task_routing_resource_digest(public.task_post_submit_routing_manifests)",
        "'claim',m.authority_context->'claim','consequence',"
        "m.authority_context->'consequence'))",
        "'claim',m.authority_context->'claim','consequence',"
        "m.authority_context->'consequence') || CASE WHEN "
        "m.authority_context ? 'reconciliation_claim' THEN jsonb_build_object("
        "'reconciliation_claim',m.authority_context->'reconciliation_claim') "
        "ELSE '{}'::jsonb END)",
    )
    _replace_function(
        "public.task_routing_context_valid(public.task_post_submit_routing_manifests)",
        "'claim',m.authority_context->'claim','consequence',consequence);\n"
        "      RETURN m.authority_context=context AND public.task_routing_receipt_valid(m);",
        "'claim',m.authority_context->'claim','consequence',consequence);\n"
        "      IF m.authority_context ? 'reconciliation_claim' THEN\n"
        "        context := context || jsonb_build_object('reconciliation_claim',"
        "m.authority_context->'reconciliation_claim');\n"
        "      END IF;\n"
        "      RETURN m.authority_context=context AND public.task_routing_receipt_valid(m);",
    )
    _replace_function(
        _ROUTING_GUARD,
        "DECLARE a public.outbox_delivery_attempts%ROWTYPE; "
        "e public.outbox_events%ROWTYPE; expected_claim jsonb;",
        "DECLARE a public.outbox_delivery_attempts%ROWTYPE; "
        "e public.outbox_events%ROWTYPE; "
        "original_a public.outbox_delivery_attempts%ROWTYPE; "
        "original_e public.outbox_events%ROWTYPE; "
        "decision public.audit_events%ROWTYPE; "
        "operator_resource_json jsonb; resource jsonb; preparation jsonb; "
        "command jsonb; source jsonb; expected_claim jsonb; reconciliation jsonb; "
        "expected_request_digest text; expected_resource_digest text;",
    )
    _replace_function(
        _ROUTING_GUARD,
        """SELECT * INTO e FROM public.outbox_events WHERE event_id=NEW.completion_event_id AND project_id=NEW.project_id FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'routing invocation unavailable' USING ERRCODE='23514'; END IF;
      SELECT * INTO a FROM public.outbox_delivery_attempts
        WHERE event_id=e.event_id AND claim_generation=e.claim_generation FOR UPDATE;
      IF NOT FOUND OR a.stage<>'invoked' OR a.finalize_decision_event_id IS NOT NULL
        OR a.claim_expires_at<=clock_timestamp() OR a.project_id<>NEW.project_id
      THEN RAISE EXCEPTION 'routing invocation unavailable' USING ERRCODE='23514'; END IF;
      expected_claim := jsonb_build_object('event_id',a.event_id::text,'project_id',a.project_id::text,
        'payload_digest',a.payload_digest,'claim_generation',a.claim_generation,'claim_owner',a.claim_owner,
        'claimed_at',replace(public.outbox_dispatch_utc(a.claimed_at),'+00:00','Z'),'claim_expires_at',replace(public.outbox_dispatch_utc(a.claim_expires_at),'+00:00','Z'));
      IF NEW.authority_context->'claim' IS DISTINCT FROM expected_claim THEN
        RAISE EXCEPTION 'routing invocation differs' USING ERRCODE='23514'; END IF;""",
        """SELECT * INTO original_e FROM public.outbox_events
        WHERE event_id=NEW.completion_event_id AND project_id=NEW.project_id FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'routing invocation unavailable' USING ERRCODE='23514'; END IF;
      SELECT * INTO original_a FROM public.outbox_delivery_attempts
        WHERE event_id=original_e.event_id AND claim_generation=original_e.claim_generation FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'routing invocation unavailable' USING ERRCODE='23514'; END IF;
      expected_claim := jsonb_build_object('event_id',original_a.event_id::text,
        'project_id',original_a.project_id::text,'payload_digest',original_a.payload_digest,
        'claim_generation',original_a.claim_generation,'claim_owner',original_a.claim_owner,
        'claimed_at',replace(public.outbox_dispatch_utc(original_a.claimed_at),'+00:00','Z'),
        'claim_expires_at',replace(public.outbox_dispatch_utc(original_a.claim_expires_at),'+00:00','Z'));
      IF NEW.authority_context->'claim' IS DISTINCT FROM expected_claim THEN
        RAISE EXCEPTION 'routing invocation differs' USING ERRCODE='23514'; END IF;
      IF NOT (NEW.authority_context ? 'reconciliation_claim') THEN
        e := original_e;
        a := original_a;
        IF a.stage IS DISTINCT FROM 'invoked' OR a.finalize_decision_event_id IS NOT NULL
          OR a.claim_expires_at<=clock_timestamp()
          OR a.project_id IS DISTINCT FROM NEW.project_id
        THEN RAISE EXCEPTION 'routing invocation unavailable' USING ERRCODE='23514'; END IF;
      ELSE
        IF original_e.event_type IS DISTINCT FROM 'PostSubmissionEvaluationCompleted'
          OR original_e.event_version IS DISTINCT FROM 1
          OR original_e.delivery_state IS DISTINCT FROM 'dead_letter'
          OR original_e.last_error_code IS DISTINCT FROM 'INVOKE_OUTCOME_UNKNOWN'
          OR original_e.finalized_at IS NULL
          OR original_a.stage IS DISTINCT FROM 'completed'
          OR original_a.finalize_decision_event_id IS NULL
          OR original_a.project_id IS DISTINCT FROM original_e.project_id
          OR original_a.payload_digest IS DISTINCT FROM original_e.payload_digest
          OR original_a.outcome_json::jsonb->>'invocation_unknown' IS DISTINCT FROM 'true'
          OR original_a.outcome_json::jsonb->>'delivery_state' IS DISTINCT FROM 'dead_letter'
          OR original_a.outcome_json::jsonb->>'error_code' IS DISTINCT FROM 'INVOKE_OUTCOME_UNKNOWN'
        THEN RAISE EXCEPTION 'routing reconciliation original unavailable' USING ERRCODE='23514'; END IF;
        expected_claim := NEW.authority_context->'reconciliation_claim';
        SELECT * INTO e FROM public.outbox_events
          WHERE event_id=(expected_claim->>'event_id')::uuid AND project_id=NEW.project_id FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'routing reconciliation child unavailable' USING ERRCODE='23514'; END IF;
        reconciliation := e.payload;
        operator_resource_json := (reconciliation->>'authorization_resource_json')::jsonb;
        resource := operator_resource_json->'resource_context';
        preparation := resource->'preparation';
        command := preparation->'command';
        source := preparation->'source';
        expected_request_digest := 'sha256:'||encode(sha256(convert_to(
          public.project_guide_projection_canonical_json(jsonb_build_object(
            'domain','workstream.post_submit_delivery_reconciliation.v0.1',
            'preparation',preparation)), 'UTF8')), 'hex');
        expected_resource_digest := 'sha256:'||encode(sha256(convert_to(
          public.project_guide_projection_canonical_json(
            jsonb_strip_nulls(operator_resource_json)), 'UTF8')), 'hex');
        IF jsonb_typeof(reconciliation) IS DISTINCT FROM 'object'
          OR reconciliation - ARRAY['schema_version','original_event_id',
             'original_claim_generation','original_payload_digest','original_event_type',
             'original_event_version','evaluation_request_id','checker_run_id',
             'evaluation_generation','classification','reconciliation_request_id',
             'request_digest','authorization_decision_id','authorization_resource_digest',
             'authorization_resource_json','operator_actor_profile_id',
             'operator_identity_link_id'] IS DISTINCT FROM '{}'::jsonb
          OR e.event_type IS DISTINCT FROM 'PostSubmissionDeliveryReconciliationRequested'
          OR e.event_version IS DISTINCT FROM 1 OR e.producer IS DISTINCT FROM 'workstream'
          OR e.aggregate_type IS DISTINCT FROM 'outbox_delivery'
          OR e.aggregate_id IS DISTINCT FROM original_e.event_id
          OR e.causation_event_id IS DISTINCT FROM original_e.event_id
          OR e.correlation_id IS DISTINCT FROM reconciliation->>'reconciliation_request_id'
          OR e.idempotency_key IS DISTINCT FROM 'post-submit-reconcile:'||original_e.event_id::text
          OR reconciliation->>'schema_version' IS DISTINCT FROM 'post_submit_delivery_reconciliation.v1'
          OR (reconciliation->>'original_event_id')::uuid IS DISTINCT FROM original_e.event_id
          OR (reconciliation->>'original_claim_generation')::bigint IS DISTINCT FROM original_a.claim_generation
          OR reconciliation->>'original_payload_digest' IS DISTINCT FROM original_e.payload_digest
          OR reconciliation->>'original_event_type' IS DISTINCT FROM original_e.event_type
          OR (reconciliation->>'original_event_version')::integer IS DISTINCT FROM original_e.event_version
          OR (reconciliation->>'evaluation_request_id')::uuid IS DISTINCT FROM NEW.evaluation_request_id
          OR (reconciliation->>'checker_run_id')::uuid IS DISTINCT FROM NEW.checker_run_id
          OR (reconciliation->>'evaluation_generation')::bigint IS DISTINCT FROM NEW.evaluation_generation
          OR reconciliation->>'classification' IS DISTINCT FROM 'retry_safe'
          OR reconciliation->>'request_digest' IS DISTINCT FROM expected_request_digest
          OR reconciliation->>'authorization_resource_digest' IS DISTINCT FROM expected_resource_digest
          OR reconciliation->>'authorization_resource_json' IS DISTINCT FROM
             public.project_guide_projection_canonical_json(operator_resource_json)
          OR jsonb_typeof(operator_resource_json) IS DISTINCT FROM 'object'
          OR operator_resource_json - 'resource_context' IS DISTINCT FROM '{}'::jsonb
          OR NOT (operator_resource_json ? 'resource_context')
          OR jsonb_typeof(resource) IS DISTINCT FROM 'object'
          OR resource - ARRAY['resource_type','resource_id','scope_project_id',
             'identity_link_id','preparation'] IS DISTINCT FROM '{}'::jsonb
          OR resource->>'resource_type' IS DISTINCT FROM 'outbox_delivery'
          OR (resource->>'resource_id')::uuid IS DISTINCT FROM original_e.event_id
          OR (resource->>'scope_project_id')::uuid IS DISTINCT FROM NEW.project_id
          OR (resource->>'identity_link_id')::uuid IS DISTINCT FROM
             (reconciliation->>'operator_identity_link_id')::uuid
          OR jsonb_typeof(preparation) IS DISTINCT FROM 'object'
          OR preparation - ARRAY['command','source'] IS DISTINCT FROM '{}'::jsonb
          OR jsonb_typeof(command) IS DISTINCT FROM 'object'
          OR command - ARRAY['actor_profile_id','project_id','event_id','request_key',
             'reason'] IS DISTINCT FROM '{}'::jsonb
          OR (command->>'actor_profile_id')::uuid IS DISTINCT FROM
             (reconciliation->>'operator_actor_profile_id')::uuid
          OR (command->>'project_id')::uuid IS DISTINCT FROM NEW.project_id
          OR (command->>'event_id')::uuid IS DISTINCT FROM original_e.event_id
          OR (command->>'request_key')::uuid IS DISTINCT FROM
             (reconciliation->>'reconciliation_request_id')::uuid
          OR jsonb_typeof(command->'reason') IS DISTINCT FROM 'string'
          OR length(command->>'reason') NOT BETWEEN 1 AND 500
          OR command->>'reason' IS DISTINCT FROM btrim(command->>'reason')
          OR command->>'reason' ~ '[[:cntrl:]]'
          OR jsonb_typeof(source) IS DISTINCT FROM 'object'
          OR source - ARRAY['project_id','event_id','event_type','event_version',
             'aggregate_id','evaluation_request_id','checker_run_id',
             'evaluation_generation','claim_generation','payload_digest','finalized_at',
             'delivery_state','error_code','classification','reconciliation_event_id',
             'reconciliation_state'] IS DISTINCT FROM '{}'::jsonb
          OR (source->>'project_id')::uuid IS DISTINCT FROM NEW.project_id
          OR (source->>'event_id')::uuid IS DISTINCT FROM original_e.event_id
          OR source->>'event_type' IS DISTINCT FROM original_e.event_type
          OR (source->>'event_version')::integer IS DISTINCT FROM original_e.event_version
          OR (source->>'aggregate_id')::uuid IS DISTINCT FROM original_e.aggregate_id
          OR (source->>'evaluation_request_id')::uuid IS DISTINCT FROM NEW.evaluation_request_id
          OR (source->>'checker_run_id')::uuid IS DISTINCT FROM NEW.checker_run_id
          OR (source->>'evaluation_generation')::bigint IS DISTINCT FROM NEW.evaluation_generation
          OR (source->>'claim_generation')::bigint IS DISTINCT FROM original_a.claim_generation
          OR source->>'payload_digest' IS DISTINCT FROM original_e.payload_digest
          OR source->>'finalized_at' IS DISTINCT FROM
             replace(public.outbox_dispatch_utc(original_e.finalized_at),'+00:00','Z')
          OR source->>'delivery_state' IS DISTINCT FROM 'dead_letter'
          OR source->>'error_code' IS DISTINCT FROM 'INVOKE_OUTCOME_UNKNOWN'
          OR source->>'classification' IS DISTINCT FROM 'retry_safe'
          OR source->'reconciliation_event_id' IS DISTINCT FROM 'null'::jsonb
          OR source->'reconciliation_state' IS DISTINCT FROM 'null'::jsonb
          OR (SELECT count(*) FROM public.outbox_events linked
              WHERE linked.event_type='PostSubmissionDeliveryReconciliationRequested'
                AND linked.event_version=1
                AND linked.causation_event_id=original_e.event_id) IS DISTINCT FROM 1
        THEN RAISE EXCEPTION 'routing reconciliation child differs' USING ERRCODE='23514'; END IF;
        SELECT * INTO decision FROM public.audit_events
          WHERE id=(reconciliation->>'authorization_decision_id')::uuid;
        IF NOT FOUND OR decision.event_domain IS DISTINCT FROM 'authority'
          OR decision.event_type IS DISTINCT FROM 'SensitiveAuthorizationAllowed'
          OR decision.actor_ref_kind IS DISTINCT FROM 'actor_profile'
          OR decision.actor_id IS DISTINCT FROM reconciliation->>'operator_actor_profile_id'
          OR decision.action_id IS DISTINCT FROM 'operations.post_submit_delivery.reconcile'
          OR decision.permission_id IS DISTINCT FROM 'operations.reconcile.run'
          OR decision.project_id IS DISTINCT FROM NEW.project_id
          OR decision.resource_type IS DISTINCT FROM 'outbox_delivery'
          OR decision.resource_id IS DISTINCT FROM original_e.event_id::text
          OR decision.target_ref_kind IS DISTINCT FROM 'project'
          OR decision.target_ref_id IS DISTINCT FROM NEW.project_id::text
          OR decision.request_id::text IS DISTINCT FROM reconciliation->>'reconciliation_request_id'
          OR decision.correlation_id::text IS DISTINCT FROM reconciliation->>'reconciliation_request_id'
          OR decision.denial_code IS NOT NULL
          OR decision.after_facts::jsonb IS DISTINCT FROM jsonb_build_object(
            'allowed',true,'resource_context_digest',expected_resource_digest)
          OR NOT EXISTS(SELECT 1 FROM public.actor_profiles actor
            WHERE actor.id=(reconciliation->>'operator_actor_profile_id')::uuid
              AND actor.actor_kind='human')
          OR NOT EXISTS(SELECT 1 FROM public.admin_role_grants grant_row
            WHERE grant_row.id::text=decision.matched_grant_id
              AND grant_row.target_actor_profile_id=(reconciliation->>'operator_actor_profile_id')::uuid
              AND grant_row.role='operator' AND grant_row.scope_type='system'
              AND grant_row.scope_project_id IS NULL)
          OR NOT EXISTS(SELECT 1 FROM public.actor_identity_links link
            WHERE link.id=(reconciliation->>'operator_identity_link_id')::uuid
              AND link.actor_profile_id=(reconciliation->>'operator_actor_profile_id')::uuid)
        THEN RAISE EXCEPTION 'routing reconciliation cause differs' USING ERRCODE='23514'; END IF;
        SELECT * INTO a FROM public.outbox_delivery_attempts
          WHERE event_id=e.event_id AND claim_generation=e.claim_generation FOR UPDATE;
        IF NOT FOUND OR e.delivery_state IS DISTINCT FROM 'claimed'
          OR a.stage IS DISTINCT FROM 'invoked'
          OR a.finalize_decision_event_id IS NOT NULL
          OR a.claim_expires_at<=clock_timestamp()
          OR a.project_id IS DISTINCT FROM NEW.project_id
          OR a.payload_digest IS DISTINCT FROM e.payload_digest
          OR a.claim_owner IS DISTINCT FROM e.claim_owner
          OR a.claimed_at IS DISTINCT FROM e.claimed_at
          OR a.claim_expires_at IS DISTINCT FROM e.claim_expires_at
        THEN RAISE EXCEPTION 'routing reconciliation invocation unavailable' USING ERRCODE='23514'; END IF;
        expected_claim := jsonb_build_object('event_id',a.event_id::text,
          'project_id',a.project_id::text,'payload_digest',a.payload_digest,
          'claim_generation',a.claim_generation,'claim_owner',a.claim_owner,
          'claimed_at',replace(public.outbox_dispatch_utc(a.claimed_at),'+00:00','Z'),
          'claim_expires_at',replace(public.outbox_dispatch_utc(a.claim_expires_at),'+00:00','Z'));
        IF NEW.authority_context->'reconciliation_claim' IS DISTINCT FROM expected_claim THEN
          RAISE EXCEPTION 'routing reconciliation invocation differs' USING ERRCODE='23514'; END IF;
      END IF;
      """,
    )


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
