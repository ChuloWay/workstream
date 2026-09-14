# WS-POL-003-07B — One internal checker command per phase

- Initiative: WS-POL-003
- Durable disposition: Planned
- Risk class: L1
- Intended merge outcome: route hidden ZIP preparation through one pre-submit
  phase command, provide the separate unavailable post-submit command, and
  remove the obsolete public JSON precheck and its exclusive implementation.

## Intent and reviewed boundaries

This implements the remaining [POL-07 contract](planning/chunks/WS-POL-003-07-single-checker-service-port.md)
after POL-07A on main `0849ca3e`. The old contract overstated what this boundary
can prove. ART already owns pre-submit reservation, execution and canonical
evidence. ARCH-04A supplies detached post-submit value contracts and registered
capability proof; it does not supply live execution authority or persistence.

The facade introduces no policy compiler, member executor, attempt store,
result projection or authorization path. Project guide activation remains
CP07/AUTH-12H work. Live post-submit materialization, attempts, authority,
currentness, workers and routing remain ARCH-04B/04C/04D/04E work. Existing
post-submit run/result/history consumers cannot be deleted before that cutover.

## Allowed and prohibited scope

- Allowed: ART `submission_admission.py` phase call site and narrow owner-local
  protocol; composition in `adapters/artifacts` and `adapters/checkers`;
  CHECKER `router.py`, `service.py`, `runner.py`, `schemas.py` solely for deleting
  the JSON precheck and exclusive helpers; affected tests and exact test/debt
  inventories; current checker/ART documentation, roadmap and initiative navigation.
- Prohibited: changes to ART reservation, claim, lock order, persistence,
  durable-put, scratch or storage lifecycle; migrations; new routes, permission
  registrations, checker selection, policy compilation, guide activation,
  post-submit production execution, acceptance or compatibility paths.
- Shared consumers: the existing post-submit service still loads locked policy
  context and uses runner packet/evidence/path/attestation helpers. Preserve
  those required behaviors; remove only helpers exclusive to draft JSON precheck.
  Hidden Submission creation and its separately documented lock concern are
  outside this change.

## Implementation

1. Add a composition-level checker phase service with exactly
   `evaluate_pre_submission` and `evaluate_post_submission`. Inject ART's
   existing evidence operation and CHECKER's existing post execution port.
   ART imports only an owner-local pre-phase protocol; CHECKER imports no ART
   private types or concrete facade.
2. After ART's reservation transaction commits, invoke the pre command once
   for both completed replay and a winning reservation. Clear the consumed
   prepared authorization from the process-local request before this handoff.
   Return the original canonical ART persistence result unchanged on replay;
   otherwise call the existing `execute_reserved`. That operation alone mints
   the committed claim, reauthorizes, evaluates and persists. Preserve the
   original pass-capability semantics and durable continuation.
3. Delegate the post command to CHECKER's typed contract, checking its exact
   request/result correspondence. Production composition explicitly injects
   `UnavailablePostSubmissionExecution`; fixtures exercise delegation and
   registered contract facts without advertising a live post executor.
4. Delete `/tasks/{task_id}/submission-precheck`, its schemas, service method,
   draft-packet runner and exclusive helpers/callers/tests. Existing real ZIP
   intake checks remain the standard. Do not replace the removed HTTP route
   with a compatibility route or expose hidden preparation prematurely.

## Acceptance and proof

- A prepared winner and an exact completed replay each reach the facade once.
  Winner executes members once; replay executes none and returns the exact
  canonical evidence identity with no fresh upload capability. Existing real
  PostgreSQL attempt tests retain unresolved/conflicting request denial,
  revocation, fresh authority, rollback and concurrency coverage.
- Facade inputs carry no usable prepared authorization across the commit.
  Existing committed-claim checks continue to bind exact packet, plan, bytes,
  manifest, generation and actor/task/project facts; no plan recompilation.
- Post delegation preserves exact request identity and validates the returned
  member plan/hash/generation. Production always reports unavailable. No test
  claims post database ownership, AUTH, replay or currentness from value objects.
- Removed route and schemas are absent from routing/OpenAPI. Remove obsolete
  JSON-only tests; retain shared post-check assertions and required real ZIP
  packet/size/path/integrity coverage. Test changes must discriminate a bypass
  of the facade on completed replay and an incorrectly accepted post result.
- Run focused pure facade/contract tests, real PostgreSQL preparation/attempt
  and affected checker tests; then canonical hosted lanes (zero intentional
  skips/deselections), coverage at least 90% for changed subsystem, lint,
  module/AUTH/test-structure/behavior ownership gates, test inventory,
  markdown links, Commitrail validation and stale wording scan. Reconcile
  roadmap and any local sheet exports with the intended merged outcome.

## Review and human focus

Required focused internal tracks: architecture/reuse, security, QA/test-delta,
documentation/product operations and CI integrity for changed test inventories.
Plan review must verify the ART transaction split and that no post fixture is
mistaken for production execution. Final reviews use a clean exact candidate.
Human focus: unchanged ART authority/custody and canonical result ownership;
complete obsolete precheck deletion; honest unavailable post boundary; next
work advances to CP06/CP07 without claiming live submitted-work execution.
