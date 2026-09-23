# WS-ARCH-001-03C1 — Exact assignment-reconciler authority

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: The existing hidden assignment release operation uses
  canonical fixed-service AUTH/PREP and records its exact authorization decision.

## Intent

Main at `606a0a73` includes 03B9's exact TASK effect and AUTH-OUTBOX-02's shared
delivery custody. Its production handler registry is empty. Feature authority
is still an explicitly unavailable port; synthetic test authority does not prove
the real service's permissions or revocation. Complete that authority before
connecting originating AUTH mutations to production delivery. This refines the
existing 03C sequence, without adding a new lifecycle or delivery subsystem.

## Bounded change

Register only `workstream.task.assignment_reconciler` with the sole action and
permission `task.assignment.authority_reconcile`. Reuse ACTORS provisioning,
AUTH's fixed-service matrix, canonical PREP, closed audit vocabulary and TASK's
existing exact facts. Do not introduce a second public facts schema. AUTH's
private resource binds the complete target, cause and invocation digests,
delivery generation (1 through 2147483647, matching OUTBOX), task state and locked context. Preparation and consumption
must bind the same action, project, session, root transaction and exact facts.
The authorization decision and TASK release evidence share the effect transaction.
Request UUID is the delivery event UUID; correlation UUID is the immutable
authority-invalidation event UUID. Neither parses the envelope string correlation
nor accepts a caller-selected principal. Assertions bind both audit identifiers.
The distinct private resource uses AUTH's existing `task_authority` token,
never the human claim/start resource class. The audit target uses its existing
`task` resource token with the task UUID and exact project scope. No vocabulary
is invented to duplicate these existing owner contracts.

Replace the unavailable TASK composition with the canonical authority adapter.
Replace the affected prepare/consume/close port with nominal, process-local
`PreparedAssignmentInvalidation` and `prepare_assignment_invalidation(facts)`
returning an async context manager. TASK uses `async with`; AUTH alone owns the
canonical fixed-service context manager. No manual context entry or duplicate
resolver. Update every caller and test together. Preserve TASK -> assignment -> feature AUTH -> OUTBOX
lock order. The handler remains unregistered in production. No retained event
backfill or automatic effect is enabled by provisioning this principal.

Return the canonical resource digest with the real decision. Persist the existing
bounded TASK authority facts and digest in the closed release payload; AUDIT and
SQL recompute the canonical resource commitment and bind every target reference,
source status and request/correlation identifier. A digest alone cannot prevent
copying a valid same-task decision to another assignment. No second facts schema
or ledger is introduced. AUDIT verifies the referenced immutable ALLOW,
exact action/permission, fixed service identity, actor, project/task and digest
before accepting a release receipt. Migration 0029 adds a narrow event guard
for the same relationship, including the immutable ACTORS service identity.
AUDIT reads its owned decision without importing private ACTORS persistence.
The shared AUDIT input accepts one event-specific JSON snapshot bounded to 4096
canonical bytes; TASK semantic parsing stays in adapter composition to avoid
a cyclic public dependency. The SQL guard applies the same bound.
It locks actor profiles and audit events before
preflight/constraint changes and refuses any existing release receipt rather
than inventing provenance. Missing/disabled principal and malformed facts are
terminal REJECT; evidence-service or unknown database failures propagate to
existing UNKNOWN handling, without automatic uncertain-effect repetition.

### Allowed files

- `backend/app/modules/actors/api/service_identities.py` and ACTORS closed
  identity tests, migration environment current-head admission and affected head
  expectations in OUTBOX migration tests and `tests/test_alembic.py`; new `backend/alembic/versions/0029_assignment_reconciler_authority.py`.
- AUTH `catalogue.py`, `admin_schemas.py` (exact public permission count),
  `runtime.py`, `prepared.py`, private
  `assignment_invalidation_authorization.py`, `domain/assignment_invalidation.py`,
  `domain/prepared_service.py`, `domain/resource_digest.py`,
  `domain/audit_targets.py`; canonical kernel only if an exact existing service
  guard requires the new resource. Composition in `app/adapters/auth/__init__.py`.
- TASK `api/assignment_invalidation.py`, `assignment_invalidation.py`,
  `app/adapters/tasks/__init__.py` for the affected authority seam only.
- AUDIT `schemas.py`, `service.py`, `repository.py` and
  `app/adapters/audit/__init__.py` for exact release/decision custody.
- Focused tests under `tests/authorization/`, `tests/tasks/`, `tests/migrations/`,
  existing catalogue/identity/ownership expectations; exact test module entries
  in `backend/scripts/test_lane_catalogue.py` and their inventory assertions;
  `backend/scripts/external_api_drill.py` for its exact permission oracle.
- `tests/conftest.py` for the inspected new schema fingerprint only;
  `backend/scripts/behavior_ownership.py` and its tests for exact new module
  registrations, `.ci/behavior-ownership/partition.v1.json` and digest; this record,
  adopted 03C contract, ARCH/AUTH/CON/POL overview navigation, `.commitrail/INDEX.md`,
  current README, TASK/AUTH architecture/operating docs and `docs/roadmap_status.md`.
- Current ARCH `planning/PLAN.md`, `planning/CHUNK_MAP.md` and adopted 03B parent
  contract; AUTH `planning/PLAN.md`, POL `planning/CHUNK_MAP.md`, and
  `docs/operations_project_operating_manual.md` to reconcile completed authority
  with the remaining producer/registration and public boundaries.

### Prohibited changes

No producer fan-out, handler registration, broker activation, new public route,
human entitlement, general service permission, retained-data rewrite/deletion,
compatibility adapter, changed task eligibility, policy selection, Submission,
review, checker or compensation behavior. Do not weaken boundaries, CI limits,
coverage gates or test assertions. Migration extends the closed identity and
authorization vocabulary; it neither provisions actors nor manufactures evidence.

## Acceptance criteria

- Exact provisioned active service can release the original eligible assignment
  using a real committed cause and invoked event. Release audit references the
  real canonical ALLOW decision and exact resource digest.
- Human, dispatcher and unrelated service cannot gain the action. Missing,
  suspended, deactivated or revoked feature principal produces no release.
- Each independent facts substitution, foreign session/root transaction,
  repeated consumption, closed preparation and copy/deepcopy/pickle transfer
  fails; a valid control succeeds.
- Root rollback removes decision, release and lifecycle evidence together.
  Replay preserves the original receipt and cannot release replacement work.
- PostgreSQL revocation versus effect proves service locks remain held through
  commit and the documented order adds no AUTH -> TASK acquisition.
- Schema and ORM/catalogue vocabularies agree. Migration preserves retained
  data and rejects unknown identities and action/permission combinations.
  Permission-definition/API drill expectations advance from 74 to 75; the
  service permission is metadata-visible but absent from all human role grants.
- Direct-SQL receipt substitutions (action, permission, service actor,
  project/task/resource and digest) reject while a complete valid control passes the same insert guard under nested
  rollback; the real-release test separately proves commit.
  Migration locking excludes concurrent actor provisioning during CHECK replacement.
- Remove the superseded deny implementation and its obsolete-only tests;
  retain or replace every required denial, custody and lifecycle regression.

## Evidence

Use real PostgreSQL with the owned `backend/scripts/run_isolated_tests.py`
runner. Implemented test modules are `tests/authorization/test_assignment_invalidation_contract.py`,
`tests/tasks/test_assignment_invalidation_authority.py`, and
`tests/migrations/test_assignment_reconciler_authority.py`. Reuse existing
`tests/tasks/invalidation_support.py` and real cause/invocation fixtures; do not
mock canonical AUTH in positive authority proof. Negative facts tests start from
an otherwise valid invocation. A discriminating mutation removes exact-facts
binding and must fail the substitution test. Service revocation proof starts
after feature locks are acquired and observes PostgreSQL blocking before commit.

Run focused new and existing assignment-invalidation, fixed-service, catalogue,
PREP and migration tests; Ruff; module/structural/ownership checks; lane inventory;
Commitrail/Markdown links and stale wording scans. Full hosted semantic lanes
must pass with no skips/deselections and preserve coverage. Command invocations,
exact heads and current results belong in the PR evidence, not invented here.

## Risk and review routing

Risk: `L1` (authorization and atomic lifecycle integration). Required plan and
implementation tracks: security, architecture/reuse, QA/test-delta,
product/operations; documentation and CI-integrity for their affected records.
Human focus: exact service privilege, complete facts commitment, revocation,
atomic evidence and hidden-versus-production boundary. Shared kernel changes
require regression proof for existing service consumers.

03C2 follows with originating AUTH mutation fan-out, nonlocking TASK projection,
atomic event publication and first handler registration with enforced prefork
topology. It must never backfill retained invalidation audit rows. Separately
bounded public task activation follows. Foreground authority remains immediate;
background release never grants access while a contributor lacks authority.

### Named regression functions

- `test_reconciler_registration_is_exact`: singleton matrix, all human roles and
  unrelated services excluded, public permission count and availability correct.
- `test_real_reconciliation_binds_decision`: real eligible assignment, committed
  contributor invalidation, invoked delivery, canonical feature PREP, joined
  ALLOW receipt, exact digest and request/correlation IDs.
- `test_reconciler_lifecycle_denies`: preserve the same otherwise-valid contributor
  cause/invocation; independently remove provisioning or suspend/deactivate the
  reconciler profile or revoke its link. Observe entry into feature preparation
  and exact TASK/assignment eligibility before asserting unchanged state.
- `test_prepared_reconciliation_binds_every_fact`: independent project, task,
  assignment, contributor, invalidation, cause, delivery, generation, cause digest,
  invocation digest, status and locked-hash changes; original valid control.
- `test_prepared_reconciliation_custody`: foreign session/root, repeated use,
  closed context and copy/deepcopy/pickle rejection.
- `test_real_reconciliation_rollback`: inject after real release flush, first
  observe staged ALLOW, matching receipt/digest, READY task and revoked assignment
  in that transaction, then verify their absence/original values independently.
- `test_release_replay_survives_service_revocation`: receipt validation is
  historical; later service lifecycle revocation cannot invalidate an existing
  receipt. ACK with identical original evidence and no fresh decision; preserve
  a replacement assignment through existing real reclaim regression.
- `test_reconciler_revocation_waits_for_effect`: PostgreSQL service lifecycle
  mutation blocks after effect PREP until root commit; no AUTH-to-TASK lock edge.
- `test_reconciler_migration_preserves_records`, `test_reconciler_migration_refuses_unproven_release`,
  `test_reconciler_migration_serializes_provisioning`, and
  `test_release_receipt_rejects_substitution`: predecessor/control, exact upgrade
  and repeated head, atomic refusal, lock-wait proof and direct-SQL negatives.

These implemented functions describe proof boundaries, not execution results.
Exact-head command results remain PR evidence. Preserve the existing
full real-cause, custody, start/Submission race and replacement-work regressions.

## Review size and source reconciliation

This L1 diff spans the existing TASK/AUTH/AUDIT effect transaction. Exact service
registration, real decision receipt validation and the schema guard must land
together. The larger test portion replaces synthetic positive authority in
existing lifecycle/race proofs, adds real PREP and migration negatives, and
updates exact closed inventories without weakening them. No separate delivery
owner, worker, route or policy implementation is added. Local sheet exports are
absent. The following boundary is 03C2 producer publication plus registration.

Plan inspection closed wrong resource-token, missing decision-reference proof,
unspecified request/correlation mapping, and potentially masked rollback tests.
Current proof distinguishes historical replay from live authority; only new
effects require current service status.

### Existing structural-debt repair

The frozen structural guard rejects growth in the touched AUTH runtime and
PREP binding parser, and same-size edits to the monolithic permission test.
Do not raise limits or grant an exception. Group the exact fixed-service
binding parser calls in the existing `domain/prepared_service.py`; relocate the
unchanged selector-ID helper from `runtime.py` to existing public `api/facts.py`
and update its three consumers (`api/routes/auth.py`, PROJECTS
`authorization_reads.py` and `router.py`) directly, without a runtime reexport.
Move only the permission-definition response assertions into
`tests/authorization/test_catalogue.py`, advancing only the intentional count;
keep role policy, scopes and role-response assertions in their existing test.
Record its original assertions and refresh the shrinking debt inventory.
Allowed additional paths are AUTH `api/facts.py`/`api/__init__.py`, those
import-only consumers, `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`,
`assertion-maps/WS-ARCH-001-03C1.json`, and removal of any now-stale entry from
`IMPORT_LEDGER.md`. No new private edge or compatibility alias is permitted.
Review this repair through CI-integrity and architecture/reuse; prove selector
identity parity, intact test assertions and no newly admitted structural debt.

### Review-driven contract proof

The copied delivery generation shares OUTBOX's signed-integer upper bound in
both TASK facts and the receipt guard. Pure boundary controls and self-consistent
direct-SQL receipt/decision substitutions reject zero and oversized generations.
Malformed authority digests stop before AUDIT. A well-formed wrong digest starts
with genuine PREP, reaches the AUDIT equality guard after a real decision and
staged TASK effect, and rolls all effects back. These are required behavior
regressions, not compatibility tests.
