# ARCH-04E1B-B7 — Hidden initial evaluation request delivery

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Risk: L1 — untrusted delivery selectors, live feature authority and transactions.
- Intended merge outcome: one unregistered typed handler recovers B6's exact
  committed request and runs the existing CHECKERS executor under independently
  verified outbox invocation custody. Completion routing remains the next boundary.

## Intent

Advance step 4 of the [first-layer sequence](planning/PLAN.md#first-complete-contributor-milestone).
B6 already atomically stores Submission, exact receipts, generation-one reservation
and request event. `EvaluationCoordinator.read_reserved_evaluation` returns that
request without creating or repairing it. `PostSubmissionExecutor` owns execution,
materialization and terminal publication; the shared outbox owns delivery.
The missing link is a handler that binds these owners to the same committed event.
No additional job, request store, executor or retry engine is needed.

## Bounded change

1. TASK recovers its immutable dispatch using event/project/submission identifiers
   together. Compare the complete canonical event with the stored dispatch and
   CHECKERS reservation, including request digest, generation, attempt/result,
   creation/binding receipts and exact content/assignment identity. Payload values
   are selectors, never authority. Use the existing event builder and select-only
   owner read; no cross-owner private imports or SQL.
2. An independently committed invocation observation precedes recovery/execution.
   CHECKERS still performs fresh fixed-service AUTH for execute and finalize,
   currentness checks, exact ART materialization and terminal receipt validation.
   A delivery-specific composition participant binds that exact request and fences
   the invocation in each execute/finalize transaction, including terminal replay.
   Use the existing TASK evaluation guard before entering canonical AUTH PREP,
   then acquire CHECKERS custody and finally the outbox fence in the prepared
   consume/replay participant. A false new-generation eligibility value forbids
   new execution but does not forbid exact terminal replay. Release
   each transaction before provider/scratch work; never hold a delivery SQL lock
   across materialization. The two existing prepared authority interfaces remain
   distinct, and delivery custody never substitutes for AUTH.
3. Acknowledge only a returned, committed terminal executor result. Duplicate
   successful delivery reuses retained execution/finalization evidence and does
   not reopen material, create a generation or append a second completion event.
   Reject malformed/uncommitted requests before effects. Unexpected exceptions,
   cancellation and uncertain effects propagate to shared UNKNOWN handling;
   never return RETRY merely because an invocation failed. An expired running
   attempt is not automatically retried by this handler: prepared execute consume
   rejects lease generation greater than one, while exact terminal replay uses
   the retained receipt. Authorized infrastructure
   recovery remains ARCH-04F; live registration remains ARCH-04E3.
4. Keep the handler absent from the production registry. No completion routing,
   source publication, acceptance, human review, remediation, public intake or
   authority activation is added. This closes only the request half of step 4.

## Allowed files

- TASK `submission_dispatch.py` and one focused `evaluation_delivery.py` owner
  module; existing TASK composition adapters or a focused adapter file.
- CHECKERS composition adapters and a focused delivery-custody composition
  adapter using existing prepared execute/finalize, observer and fence ports.
  Existing public execution-port annotations may be tightened without changing
  direct executor behavior or introducing an optional custody bypass.
- Focused `backend/tests/tasks/evaluation_delivery/` tests and support; existing
  real admission/execution/outbox helpers only for concrete fixture reuse.
- Exact new-file ownership and test-lane inventories, their tests, and dependency
  metadata if required. No relaxed boundary, timeout, test-completeness or CI gate.
- This record, affected ARCH/POL/AUTH/REV current navigation, README, checker/
  artifact operating documentation and `docs/roadmap_status.md`; local roadmap
  exports only if present. Preserve unrelated main changes.

## Acceptance criteria

- Real PostgreSQL delivery of B6's committed event reaches the existing executor
  with actual fixed-service authority and Local/MinIO material. Verify exact run,
  material custody, immutable AUTH receipt identities, completion event and no
  routing/acceptance effects. Existing execution tests retain byte/hash proof.
- Real shared outbox delivery acknowledges once; duplicates do not access the
  provider or create additional checker/completion facts. Terminal handler replay
  requires current invocation and fresh feature authority.
- A second valid stored lineage supplies foreign substitutions. Event/header,
  request, digest, receipt and attempt/result substitutions reject before provider
  or scratch access. Use recomputed valid digests where necessary so an earlier
  malformed-input guard cannot mask the ownership assertion.
- A claimed-but-not-invoked event cannot execute. Pre-start expiry or completed
  delivery cannot start effects. An expired running generation-one attempt under
  a live invoked claim cannot acquire a second lease or reopen the provider;
  removing that generation guard must fail the exact regression. A read already
  authorized may finish after expiry, but cannot publish its terminal result.
  Independent-session invalidation while provider I/O is
  paused prevents finalization and releases scratch; committed execute custody
  remains intact. Cancellation/unknown preserves the shared no-repeat behavior.
- Lost terminal acknowledgement does not require another evaluation. Distinguish
  direct exact terminal replay proof from automatic recovery, which is deferred.
- Guard-removal probes discriminate request matching and final transaction
  invocation fencing. Reuse real AUTH and database constraints in race proofs;
  coordinate barriers rather than relying on short sleeps.
- Run focused new and affected execution/outbox tests, module boundaries, lint,
  committed Commitrail validation, markdown links, stale-wording/diff checks and
  exact-head hosted suite. Report actual infrastructure and uncertainty honestly.

## Risk and review routing

Plan review precedes implementation. Required implementation tracks: architecture/
reuse, security, QA/test delta, CI integrity and documentation/product operations.
Reviewers inspect a clean exact target and relevant unchanged owner paths; the
lead supplies shared deterministic evidence and batches repairs.

Human focus: invocation custody is additional to feature AUTH; it cannot become
an event-based authority shortcut. UNKNOWN must not silently become retry. The
production handler registry and both true/false governed-outcome gates remain
unchanged. Approval of this chunk does not authorize merge or live activation.

## Evidence

Plan feasibility traces the existing TASK dispatch, CHECKERS executor, real
materialization fixture and shared outbox observation/fencing. Runtime verification
will exercise the named acceptance boundaries on the implementation candidate.
