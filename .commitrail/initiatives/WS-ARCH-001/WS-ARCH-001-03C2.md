# WS-ARCH-001-03C2 — Atomic assignment-invalidation publication and delivery

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: supported originating authority changes atomically
  publish exact assignment targets and the first production handler delivers
  their existing authorized release through the shared OUTBOX owner.

## Intent

Finish the missing link after 03C1: revoking Submitter authority, suspending or
deactivating an actor, or revoking an identity link must durably schedule release
of that actor's affected pre-submission assignments. A delayed delivery cannot
select a newer assignment. Reuse existing TASK/AUTH/AUDIT/OUTBOX transactions,
receipts and retry semantics. Timed contributor leases and voluntary skip are
parked in draft #433; they are not part of this change or a predecessor.

## Current behavior and source reconciliation

Main `46a30772` includes 03C1. `AuthorityMutationService.complete` stages success
and invalidation AUDIT facts and completes an idempotency receipt, but publishes
no assignment event. Actor/link lifecycle and project-role services share this
path. The TASK `AssignmentInvalidationOperation` validates a committed exact
cause, locks task then assignment, uses exact feature AUTH and OUTBOX custody,
and commits an immutable decision-bound release through its transactional
adapter. `production_outbox_delivery` still installs an empty registry. Celery
has recovery scans and a 300-second hard delivery limit but no queue/pool
activation guard. No producer may scan retained invalidation rows for backfill.

## Bounded change

### Allowed

- `backend/app/modules/authorization/api/assignment_invalidation.py` (new narrow
  publication contract), `authorization/service.py`, `lifecycle_service.py`,
  `project_role_service.py`, `admin_service.py`, `service_actor_service.py`,
  and exact composition call sites in `authorization/router.py`.
- `backend/app/adapters/auth/__init__.py`, a cohesive AUTH publication adapter,
  `adapters/tasks/__init__.py`, and `adapters/outbox/__init__.py`.
- `backend/app/modules/tasks/api/assignment_invalidation.py`, `backend/app/modules/tasks/repository.py` as the nonlocking SQL owner,
  and owner composition; no lifecycle expansion.
- `backend/app/modules/outbox/api.py`, `schemas.py` removal, `__init__.py`,
  `service.py`, `repository.py` and exact affected contract imports/tests: move
  existing append values/validation into the canonical API, remove unused root
  exports, and supply `OutboxAppendPort` via the existing OUTBOX adapter. The
  package-root facade was not a public boundary under the dependency guard;
  source review confirmed no existing public append port. No new implementation,
  private-edge exception or compatibility export is introduced.
- `backend/app/modules/outbox/delivery.py` with `CommittedInvocationReader` reusing existing repository observation
  without circular registration.
- `backend/app/workers/celery_app.py`, `workers/outbox.py`, a focused delivery
  topology guard, existing config/environment documentation only if required.
- Focused tests under `backend/tests/tasks/`, `tests/authorization/`,
  `tests/outbox/`, `tests/projects/guide_compilation/finalization/pg_authorization.py`,
  existing Celery configuration tests and affected exact inventories in
  `test_authorization.py`, `test_behavior_ownership.py`, `test_ci_lane_catalogue.py`.
- `.github/workflows/backend.yml`: provision Redis for the real broker proof,
  without changing lane selection, test gates or coverage thresholds.
- Exact ownership registration, lane inventory, import/debt/assertion metadata
  only where real moved/added owners require it; do not raise limits.
- This record, current ARCH plan/overview/map/03C contract, affected AUTH/CON/POL
  overviews/index, README, roadmap, TASK/AUTH operational specifications and
  worker deployment examples and current shared OUTBOX specifications. Update
  ignored roadmap exports together if present.

### Not allowed

No public task/guide/Submission route activation, no expiry/skip, no policy
selection, no REV or checker/acceptance activation, no new permission/service
identity, no service provisioning shortcut, retained-data backfill/deletion,
new scheduler or alternate outbox. No broader AUTH permission, private TASK
imports in AUTH, compatibility constructors, weakened ownership or CI gates.
No schema change is expected; any demonstrated schema gap needs explicit record
reconciliation before code, preserving retained data.

## Design and decisions

1. **One originating publication gate.** Add AUTH-owned closed immutable facts
   and `AuthorityInvalidationPublicationPort`. `AuthorityMutationService.complete`
   requires an explicit `publication` argument: a port for exactly Submitter
   project-role revoke, actor suspend/deactivate and identity-link revoke;
   `None` for every unsupported cause. A supported loss with no port fails before
   completion; unsupported causes cannot attach one. There is no optional default
   or router-only publication. Derive facts from the already-validated request,
   success event and newly staged invalidation event. Publish before completing
   the receipt, in the same caller session/root transaction. Any append failure
   propagates and rolls back state, audit, events and idempotency completion.
   Define AUTH-owned `AuthorityInvalidationPublicationUnavailable`. Normalize
   expected projection validation, SQL and OUTBOX exceptions into it, never
   cancellation. Explicitly catch it in all three originating route paths
   (actor lifecycle, identity-link lifecycle and project-role revoke), roll back,
   then return the existing sanitized retryable service-unavailable response.
   The existing SQLAlchemy-only database wrapper does not supply this mapping.
   Exact-id conflicts are rollback failures, never partial success.
2. **Explicit composition.** Three originating lifecycle/project-role services
   require the publication port in their constructor. Existing AUTH adapter
   factories supply the real session-bound implementation. Unrelated mutation
   completions pass explicit `None`; tests use real composition or narrow
   recording/raising ports for their declared unit boundary. No missing-port
   fallback. AUTH facts do not import TASK or OUTBOX implementation types.
3. **Exact target capture under AUTH serialization.** TASK exposes nonlocking,
   project/actor-scoped immutable request/page facts.
   `TaskRepository.read_assignment_invalidation_targets_page` owns the fixed
   scalar SQL query, with stable UUID keyset
   pagination, at most 100 rows per query. Select exact active assignment,
   `claimed`/`in_progress` task, current assignee and no retained Submission,
   with assigned_at no later than the newly recorded database cause timestamp.
   Project-grant revoke filters its exact project; profile/link losses fan out
   across all affected projects. Other roles/reactivation/admin changes emit none.
   AUTH target locks already serialize claim; never acquire TASK row locks after
   those locks. The handler revalidates all facts at delivery.
4. **Complete atomic fan-out.** The adapter maps each exact target to the existing
   closed five-field `AssignmentInvalidationTarget`, uses one deterministic UUID
   and idempotency key per invalidation/assignment, and appends through the shared
   OUTBOX public service. Aggregate is exact assignment; project is target project;
   causation is invalidation event UUID; correlation is originating audit
   correlation. All pages remain in one originating transaction; no publication
   to the broker from it. Accept linear total work proportional to assignments
   for v0.1: page/memory is bounded, total transaction time is not guaranteed.
   There is no enforced contributor assignment cap today. Do not invent one,
   silently truncate, or let a new arbitrary cap prevent authority revocation.
5. **First immutable registry entry.** Register only
   `TaskAssignmentAuthorityInvalidationRequested` version 1 using the existing
   transactional TASK handler, real 03C1 feature authorization and existing AUDIT
   receipt/cause adapters. Use `CommittedInvocationReader` in existing `outbox/delivery.py`, delegating
   `DeliveryRepository.observe` in an independent session. Existing delivery
   observation delegates the same reader to avoid mutable registry construction, fake proxies or
   an unnecessary second delivery engine. The handler acknowledges after commit.
   Dispatch authority does not supply feature authority. Missing/revoked service
   authority fails closed; infrastructure/evidence uncertainty remains UNKNOWN.
6. **Enforced execution topology.** Route delivery to dedicated queue
   `workstream.outbox`. A worker consuming that queue must use prefork and must
   not enable eager execution; reject invalid topology at startup. Other queues,
   including guide-only solo workers, remain supported. Guard delivery entry
   before SQL against eager/direct execution or an unvalidated consumer. Route
   overrides/dynamic queue addition cannot bypass that guard. Reject disabled or extended per-message hard limits. Preserve the real
   300-second hard process limit and UNKNOWN no-reinvoke semantics. Periodic
   existing OUTBOX recovery scans publish selectors to this queue after commit.
7. **No historical event manufacture.** Only the currently executing authorized
   mutation captures its original assignments. Exact mutation replay publishes
   nothing again. Existing audit invalidations are evidence, not a work queue.
   New claim after reactivation gets a distinct assignment and cannot be released
   by a delayed old target. Preserve wrong-role changes and submitted work.

## Acceptance criteria

- Real originating API changes emit the exact complete deterministic event set;
  all four supported causes, scoped/multi-project/multi-page targets, unrelated
  actor/project and non-Submitter negative controls use real authority.
- Failing an append after staged cause/audit and an earlier append rolls back
  every mutation/event/receipt; observe eligible targets and append entry so
  this negative cannot pass through an earlier unrelated rejection.
- Independent PostgreSQL claim/lifecycle sessions prove both orderings. Claim
  committed first is captured exactly once. AUTH target lock first sees no
  uncommitted claim and does not wait on TASK; pending claim denies after loss.
  Adding FOR UPDATE to target projection must fail the nonlocking/race proof.
- Exact replay and retained historical invalidations create no additional events.
  Remove publication as a mutation probe: positive exact-set test must fail.
- Actual production composition handles a real committed API cause/event through
  dispatcher authorization, invocation, TASK authority, effect commit and delivery
  finalization; task READY, assignment authority_revoked and exact immutable
  receipt. Duplicate delivery adds no release and delayed old target never
  mutates a successor. Missing/revoked feature service leaves TASK unchanged.
- Feature delivery and existing shared recovery tests retain crash-before-invoke
  safe retry and committed-unknown no-reinvoke behavior. No weakening existing
  actual prefork hard-timeout proof.
- Real Celery startup/consumer tests reject delivery queue with solo/non-prefork
  and eager, accept prefork, and allow solo for other queues. Synchronous delivery
  entry rejects direct/eager/unvalidated use before database access. A real
  prefork/broker feature-delivery drill verifies actual routing and effect;
  test stubs are not production-transport proof.
- Schema and permission inventories remain unchanged except actual owner/coverage
  bookkeeping; no loss of coverage or weakened negative tests.

## Risk and review routing

- Risk class: L1 (bounded auth, transactions, workflow and worker activation).
- Required reviewers: architecture/security/reuse/senior engineering;
  QA/test_delta/product_ops; CI integrity; documentation.
- Human review focus: same-transaction completeness, exact original assignment,
  lock ordering, no historical backfill, prefork enforcement and uncertainty.

## Evidence

Use existing `backend/scripts/run_isolated_tests.py` with private disposable
PostgreSQL configuration and exact per-run metadata; use real Redis/broker and
prefork for the new production-delivery proof. Existing shared fixtures supply
real policy locks and service grants. Focused test modules:
`tests/authorization/test_assignment_invalidation_publication.py`,
`tests/authorization/test_assignment_invalidation_publication_races.py`,
`tests/tasks/test_assignment_invalidation_targets.py`,
`tests/outbox/test_assignment_invalidation_delivery.py`,
`tests/outbox/test_delivery_topology.py`. Extend existing handler/lifecycle/race
and worker tests for affected callers; list new modules in canonical lanes.

The hosted lane provisions a pinned Redis service and supplies an explicit test
broker URL. Local evidence provisions an owned disposable Redis instance. Each
real-broker test uses a unique transport key prefix, bounded process cleanup and
namespace cleanup; never flush a shared Redis database. Missing broker setup is
a failure, not a skip. Existing Python Redis/Celery dependencies suffice.

Proof map (runtime results and exact reviewed head are recorded in the PR):

| Module | Test functions and discriminating controls |
| --- | --- |
| authorization/test_assignment_invalidation_publication.py | `test_supported_causes_publish_exact_targets` (four causes), `test_reactivation_publishes_nothing`, `test_reviewer_revoke_does_not_publish_submitter_assignments` and existing admin operation-map tests, `test_actor_fanout_publishes_every_page` (>100 rows; success and later-page failure with observed earlier append, full rollback and sanitized 503), `test_publication_failure_is_sanitized_and_same_key_can_retry` (grant/link paths), `test_replay_does_not_publish_or_backfill` (retained unrelated cause), `test_supported_causes_publish_exact_targets` also checks deterministic envelope/payload identity; `test_project_revoke_is_scoped_and_actor_loss_spans_projects` checks exact fan-out scope. Removing publication must fail the supported positive. |
| tasks/test_assignment_invalidation_targets.py | `test_target_projection_exact_membership`, `test_target_projection_independent_state_predicates` and `test_target_projection_excludes_retained_submission` (independently excluded released assignment, wrong assignee/state/project/actor, retained submission and future timestamp, alongside eligible controls), `test_target_projection_is_nonlocking` (independent row lock). Probe each removed predicate where a persisted fixture can reach that boundary; otherwise inspect compiled SQL alongside the enforced database constraint and state why an impossible fixture is not forged. |
| authorization/test_assignment_invalidation_publication_races.py | `test_claim_and_loss_publish_only_committed_original_assignments` (both orderings); real independent AUTH sessions, bounded barriers and exact committed event set. Adding target row locking must fail the second ordering. |
| outbox/test_assignment_invalidation_delivery.py | `test_production_delivery_releases_exact_assignment`, existing hidden duplicate/delayed-successor tests and production duplicate assertion, `test_missing_feature_authority_preserves_assignment`, `test_real_broker_prefork_delivers_committed_invalidation`; use production composition and real feature authority. |
| outbox/test_delivery_topology.py | `test_delivery_queue_requires_prefork`, `test_delivery_queue_rejects_eager`, `test_other_queue_allows_solo`, `test_delivery_entry_rejects_unvalidated_execution` (direct/eager/dynamic queue override before SQL), `test_delivery_routes_to_dedicated_queue`, actual Worker startup rejection/solo controls, and rejection of disabled/extended message hard limits. |
| outbox/test_worker_postgresql.py | Replace obsolete `test_empty_production_registry_does_not_claim_feature_work` with `test_production_registry_claims_only_registered_invalidation`; preserve unrelated-event unclaimed control, registry malformed/duplicate negatives, crash-before-invoke recovery, committed UNKNOWN no-reinvoke and actual prefork hard-timeout proof. |

Update current empty-registry claims in README, AUTH operating documentation,
ARCH plan, AUTH overview and roadmap. Preserve historical 03B9/03C1/OUTBOX02
records as historical evidence.

Run focused regressions, Ruff, ownership/import/AUTH structural gates, Markdown
links/stale wording/Commitrail checks, required internal reviewers and hosted CI.
All new/changed subsystem coverage must remain >=90 percent. Future proof listed
here is not executed evidence until recorded in the PR.

## Review findings

Pre-plan source review ruled out router-only publication, mutable/fake registry
observers and globally banning solo workers. It also found no enforced task cap;
complete atomic paged fan-out therefore explicitly accepts linear transaction
work rather than pretending to bound total cardinality.

Plan review closed the SQL-owner, error-mapping and proof-environment findings.
Implementation dependency checking then identified the unused OUTBOX root facade
as private: existing append contracts/validation moved into `outbox/api.py`, the
old schemas module/root exports were removed, and existing append service is
composed through `OutboxAppendPort`. Architecture source review confirmed this
minimal repair without a new private edge or dependency-guard exception.
The prefork proof observes its owned child exit sentinel; the pool remains the
sole waitpid/reaping owner. This avoids competing reapers while retaining the
same termination bound and UNKNOWN/duplicate-delivery assertions.

## Reconciliation

- Current-source reconciliation: 03C1 and shared OUTBOX authority are merged;
  handler registration and producer remain absent. Draft #433 is deferred.
- Next usable boundary: existing bounded public task/guide activation; no lease
  or skip dependency and no automatic next-chunk start.
- Remaining risks: large actor-wide changes hold AUTH locks through complete
  fan-out; deployment must run the dedicated prefork consumer and recovery scan.
