# WS-AUTH-001-19A — Exact acceptance-source commitments

- Initiative: WS-AUTH-001
- Durable disposition: Complete
- Intended merge outcome: exact, inert source commitments for human Review and
  post-submit routing, with the router registered as planned and unavailable.

## Intent

Main `04bf8b76` delivers the disabled REV-12A1 transaction fence. Review and
FinalAcceptance foundation rows still lack originating authorization receipts.
Inspection found that review.decision cannot execute and does not bind the
allocated Review/request identities; task.post_submit.route is not registered.
Mandatory receipt DDL now would require fabricated allows for positive tests or
make valid inserts unreachable. Define the source contracts first. This does not
satisfy persisted receipt custody: hidden source preparation, AUTH preparation/receipt staging remain
prerequisites to CON-07/shared acceptance. Mandatory persisted custody follows
with exact consequence activation before production consumption. A durable allow is first proven with
its complete governed consequence, never committed as an early prerequisite.

The automated false-policy branch remains the selected first runtime delivery.
True-policy routing retains its independent prerequisites. Submitter lease/skip,
live human queues and review/revision operations remain outside this change.

## Bounded change

Repair the existing initial/revision ReviewDecisionContract in place. Bind the
allocated Review ID, ReviewDecisionRequest ID, existing operation ID, native UUID
idempotency key, request digest and Review aggregate digest. Preserve existing
exact project/task/assignment/Submission/reviewer/packet/policy facts. Add
submission_version. Replace the speculative reviewer contribution policy
id/generation/digest triple with reviewer_contribution_policy_version_id. A decision
may request revision with a new blocker or an unresolved inherited blocker;
accept requires neither. Initial decisions cannot claim inherited blockers.
Bound counts to the delivered storage limit; do not duplicate Review content.

Define strict frozen source commitment and detached receipt value contracts in
AUTH's dependency-free public API. Human commitments project retained identity,
request and aggregate facts from the repaired private Review contract. Routing
commitments project identity and a canonical digest from the existing TASK
TaskPostSubmitManifestFacts, including its semantic manifest hash. TASK owns only task_post_submit_source_digest; a private AUTH
acceptance_source_contracts module projects TASK public facts into AUTH public
scalar DTOs. TASK public API imports no AUTH module. AUTH public API imports no
product or private module. Reuse canonical_json_hash and revalidate input before hashing. There
is no second manifest model or table. The source digest commits retained facts;
it is distinct from the full runtime authorization resource digest, which also
binds runtime facts and is not claimed independently reconstructible today.

Detached receipt facts bind event/action/actor/project/resource and the selected
source commitment. They are untrusted values until a future owner verifies the
actual immutable AUTH event and source. Construction, hashing and a receipt-shaped
value grant no authority. Routing claim/currentness/effect evaluation remains ARCH-04E1B/04E2 work.
The source contract binds distinct route_operation_id and route_request_digest;
these are not the checker evaluation request. ARCH-04E1B-A must stage them before ARCH-04E2-A prepares exact authority
and receipt custody. Durable receipt publication remains atomic with the final
consequence. This is not an executable routing context.

Register task.post_submit.route as a planned action/permission with ARCH-04E2
ownership and workstream.task.post_submit_router as its sole fixed identity.
Extend only ActorProfile's closed service-identity CHECK in a successor migration
for ORM/DDL parity. The migration creates no service actor, grant or event. Existing administrator
provisioning may admit the registered identity; it still cannot execute the
planned action. Leave audit registry
constraints, active action sets, kernel and prepared/evaluator paths unchanged.

### Exact contracts

All identities below are native UUIDs; SHA-256 fields use the canonical prefixed
lowercase form. Models are strict, frozen and reject extra fields.

- Human commitment: source=`human_review`; review_id,
  review_decision_request_id, project_id, task_id, task_assignment_id,
  submission_id/version, review_queue_entry_id, review_lease_id, reviewer_id,
  packet_manifest_id/digest, reviewer_contribution_policy_version_id,
  locked_review_policy_id/generation/hash, artifact_hash, decision, operation_id,
  idempotency_key, request_digest, review_aggregate_digest.
- Route commitment: source=`task_post_submit_route`; routing_manifest_id,
  project_id, task_id, assignment_id, submission_id/version, contributor_id,
  contribution_policy_version_id, checker_run_id, evaluation_request_id/generation,
  result_id, completion_event_id, human_review_required, locked_review_policy_id/
  generation/hash, content_id/hash, semantic_manifest_sha256,
  routing_source_digest, route_operation_id, route_request_digest. Both policy
  branches remain represented. The route operation must differ from the checker
  evaluation request; projection also rejects reuse of the checker request digest.
  Routing request content has distinct caller-owned semantics.
- Detached receipt: authorization_decision_event_id, action_id, permission_id,
  actor_profile_id, actor_identity_link_id, nullable service_identity and
  matched_grant_id, project_id, resource_type/id, request_id, correlation_id,
  idempotency_reference, resource_context_digest, source and source_commitment_digest.
  Human action/permission are review.decision, resource is review/Review.id,
  actor equals reviewer, service identity is null and matched grant is required.
  Route action/permission are task.post_submit.route, resource is
  task_post_submit_routing_manifest/manifest ID, fixed identity is
  workstream.task.post_submit_router and matched grant is null. Project and
  resource match the source. For human receipts, request_id and correlation_id
  equal source.operation_id; idempotency_reference equals
  source.review_decision_request_id. The caller idempotency_key remains separately
  committed. For routing receipts, request_id, correlation_id and
  idempotency_reference all equal source.route_operation_id; none substitutes the
  checker evaluation request. Test independent substitutions of all three fields
  and remove the envelope validator to prove the assertions discriminate.
  All request/correlation/idempotency references are native UUIDs. The full runtime
  resource digest is opaque here. Future audit persistence must carry and verify
  the source commitment; today's audit event does not persist this new shape.

Digest domains are workstream.task_post_submit_source.v0.1 and
workstream.authorization.acceptance_source.v0.1. TASK hashes every revalidated
TaskPostSubmitManifestFacts field except database-owned created_at, allowing a
pre-persistence commitment. The source commitment hashes every selected DTO field,
including its discriminator. These are initial v0.1 protocol identifiers, not
parallel implementations. No digest establishes persistence, currentness or
permission. inherited_unresolved_blocking_count is zero for initial decisions;
new plus inherited blockers is zero for accept, positive for needs_revision,
and never exceeds the retained storage limit of 100.

### Allowed files

- `backend/app/modules/actors/api/service_identities.py`.
- `backend/app/modules/authorization/catalogue.py`, `review_contracts.py`, `admin_schemas.py` permission count, and
  new `api/acceptance_source.py` and private `acceptance_source_contracts.py`
  (package exports only if needed).
- `backend/app/modules/tasks/api/post_submit_routing.py` and its existing export.
- One successor Alembic migration extending only the actor identity CHECK.
- Existing Review authorization, TASK routing contract, catalogue/service matrix
  and migration/schema tests; a focused AUTH source-contract test module if the
  existing tests cannot express the cross-contract proof cohesively.
- Shared test inputs in `backend/tests/tasks/post_submit_routing/contract_fixtures.py`
  and `backend/tests/authorization/review_contract_fixtures.py`; tests import these
  helpers directly, avoiding test-module import side effects during lane collection.
- `mcp_server/contracts/authorization_context_get.json`: refresh only the selected
  OpenAPI action enum, source provenance and canonical digest; no MCP runtime changes.
- Alembic/schema-head, CI lane and behavior-ownership inventories only as required
  by added paths or canonical identifiers; do not weaken boundaries or gates.
- This record, current AUTH/REV/CON/POL/ARCH overview/plan/chunk-map navigation,
  Commitrail index, current ARCH-04E contract, roadmap and canonical authorization/review/contribution specifications;
  README and ignored roadmap spreadsheet exports if affected/present.

### Prohibited changes

No Review/FinalAcceptance schema changes, receipt FK placeholders, audit registry
expansion, fake allow fixtures, actor provisioning, executable authority, kernel
or prepared registrations, false-policy activation, contribution/acceptance
writers, routes, workers or handler activation. No compatibility implementation,
retained-data deletion, unrelated cleanup, test skipping or gate relaxation.

## Acceptance criteria

1. Review contracts bind exact source/request identity. Independent substitutions
   change the source commitment; invalid scalar shapes reject. Existing initial
   and revision behavior stays covered, including inherited-only blockers and
   accept with an unresolved blocker rejecting.
2. TASK projects its existing source facts without copying their model. Assert
   both true and false survive AUTH projection, and a human reject changes both
   the projected decision and source commitment. Every
   identity, policy, artifact and request substitution changes its canonical
   commitment. Equal revalidated values hash identically. Receipt envelopes reject
   action, actor, project/resource or commitment-digest mismatches.
3. Both originating actions remain unavailable. The fixed router matrix contains
   only the planned route action. No executor/handler/active-action registration
   appears. No public route or live receipt issuance is claimed.
4. Real PostgreSQL migration/schema tests prove canonical service vocabulary parity,
   preserve existing actor rows and create no new actor. A direct-SQL authority
   event control establishes valid audit input; changing it to the planned route
   action is rejected by the unchanged closed authority constraints, expected
   ck_audit_events_authority_registries (observed PostgreSQL constraint),
   with audit rows unchanged.
   The control uses the real contribution-policy authorization operation and
   unchanged clone_decision(event, {}); only action/permission change for denial.
   Prove a provisioned router still cannot resolve the planned action.
5. Run focused pure and PostgreSQL proofs, discriminating guard-removal probes for
   receipt/source substitutions, module boundaries, ownership/lane completeness,
   lint, markdown links and stale wording checks. Full hosted CI remains blocking.
   Counts and coverage are diagnostics, not evidence of a particular guard.
6. Current navigation says source contracts delivered, hidden originating issuer/receipt
   staging still required before CON-07; mandatory persisted custody accompanies
   consequence activation before production consumption. The first
   durable allow commits only with the complete governed consequence. Preserve
   both policy branches; do not rewrite completed historical change records.

### Named checks

Extend test_review_authorization_contracts.py, tasks/post_submit_routing/
test_contracts.py, authorization/test_catalogue.py, migrations/
test_service_identity_schema.py and authorization/contribution_policies/
test_policy_audit_schema.py. New focused source/receipt tests may live in
 tests/authorization/test_acceptance_source_contracts.py. Run their complete pytest
modules through the isolated PostgreSQL runner, plus test_alembic.py and affected
boundary/inventory tests. Run ruff check on changed Python; scripts.module_boundaries
validate --protected-base 04bf8b76; scripts.behavior_ownership validate;
scripts/check_commitrail_records.py --base-ref 04bf8b76;
scripts/check_markdown_links.py and the existing stale wording/authorization/
artifact/review scans. Hosted CI must complete all collected nodes. Shared fixtures must not import test
modules: prove canonical full-suite collection and isolated collection produce
identical node sets for the affected modules under one head seed. This protects
the lane runner from import-time parametrization identity changes without
changing its selectors or gates.

## Risk and review routing

- Risk class: L1 (authorization vocabulary and immutable source commitments).
- Plan review: security and architecture, including dependency direction and
  concrete valid-control feasibility before implementation.
- Implementation review: security; architecture/reuse; QA/test delta; docs/product
  operations; CI integrity for actual inventory/migration impact.
- Human focus: no receipt-shaped value confers authority, no hidden activation,
  source digests are reconstructible, and no artificial positive AUTH fixture.

## Evidence

Plan review repaired the public dependency direction, removed speculative reviewer
policy selectors, and fixed exact request/correlation bindings before implementation.
PostgreSQL proves the migration preserves source rows and rejects the planned route
through its unchanged closed audit registry. The receipt values remain untrusted;
there is no runtime source custody claim. Exact command and reviewer evidence
belong to the implementation PR.

External review exposed an ambiguous issuer dependency. The current ARCH-04E
contract now splits existing source preparation/issuer work from later handlers
and activation; no durable receipt is required to exist before its atomic
consequence. The index keeps durable boundaries, while the roadmap carries the
implementation sequence. Test helpers moved out of test modules so full and
isolated collection retain identical node identities without changing CI gates.
