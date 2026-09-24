# WS-ARCH-001-03C2 — Atomic assignment-invalidation publication and delivery

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
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
- `backend/app/modules/tasks/api/assignment_invalidation.py`, a cohesive TASK
  nonlocking projection module and owner composition; no lifecycle expansion.
- `backend/app/modules/outbox/delivery.py` plus a narrow owner committed-invocation
  reader if needed to reuse existing observation without circular registration.
- `backend/app/workers/celery_app.py`, `workers/outbox.py`, a focused delivery
  topology guard, existing config/environment documentation only if required.
- Focused tests under `backend/tests/tasks/`, `tests/authorization/`,
  `tests/outbox/`, `tests/projects/guide_compilation/finalization/pg_authorization.py`,
  existing Celery configuration tests and affected exact inventories in
  `test_authorization.py`, `test_behavior_ownership.py`, `test_ci_lane_catalogue.py`.
- Exact ownership registration, lane inventory, import/debt/assertion metadata
  only where real moved/added owners require it; do not raise limits.
- This record, current ARCH plan/overview/map/03C contract, affected AUTH/CON/POL
  overviews/index, README, roadmap, TASK/AUTH operational specifications and
  worker deployment examples. Update ignored roadmap exports together if present.

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
2. **Explicit composition.** Three originating lifecycle/project-role services
   require the publication port in their constructor. Existing AUTH adapter
   factories supply the real session-bound implementation. Unrelated mutation
   completions pass explicit `None`; tests use real composition or narrow
   recording/raising ports for their declared unit boundary. No missing-port
   fallback. AUTH facts do not import TASK or OUTBOX implementation types.
3. **Exact target capture under AUTH serialization.** TASK exposes nonlocking,
   project/actor-scoped immutable assignment targets with stable UUID keyset
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
   receipt/cause adapters. Extract/reuse the existing OUTBOX independent-session
   committed observer to avoid mutable registry construction, fake proxies or
   an unnecessary second delivery engine. The handler acknowledges after commit.
   Dispatch authority does not supply feature authority. Missing/revoked service
   authority fails closed; infrastructure/evidence uncertainty remains UNKNOWN.
6. **Enforced execution topology.** Route delivery to dedicated queue
   `workstream.outbox`. A worker consuming that queue must use prefork and must
   not enable eager execution; reject invalid topology at startup. Other queues,
   including guide-only solo workers, remain supported. Guard delivery entry
   before SQL against eager/direct execution or an unvalidated consumer. Route
   overrides/dynamic queue addition cannot bypass that guard. Preserve the real
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

## Verification

Use existing `backend/scripts/run_isolated_tests.py` with private disposable
PostgreSQL configuration and exact per-run metadata; use real Redis/broker and
prefork for the new production-delivery proof. Existing shared fixtures supply
real policy locks and service grants. Named future test modules:
`tests/authorization/test_assignment_invalidation_publication.py`,
`tests/tasks/test_assignment_invalidation_targets.py`,
`tests/outbox/test_assignment_invalidation_delivery.py`,
`tests/outbox/test_delivery_topology.py`. Extend existing handler/lifecycle/race
and worker tests for affected callers; list new nodes in canonical lanes.
Run focused regressions, Ruff, ownership/import/AUTH structural gates, Markdown
links/stale wording/Commitrail checks, required internal reviewers and hosted CI.
All new/changed subsystem coverage must remain >=90 percent. Future proof listed
here is not executed evidence until recorded in the PR.

## Review findings

Pre-plan source review ruled out router-only publication, mutable/fake registry
observers and globally banning solo workers. It also found no enforced task cap;
complete atomic paged fan-out therefore explicitly accepts linear transaction
work rather than pretending to bound total cardinality.

## Reconciliation

- Current-source reconciliation: 03C1 and shared OUTBOX authority are merged;
  handler registration and producer remain absent. Draft #433 is deferred.
- Next usable boundary: existing bounded public task/guide activation; no lease
  or skip dependency and no automatic next-chunk start.
- Remaining risks: large actor-wide changes hold AUTH locks through complete
  fan-out; deployment must run the dedicated prefork consumer and recovery scan.
