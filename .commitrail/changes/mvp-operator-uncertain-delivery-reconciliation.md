# Reconcile uncertain post-submit delivery without repeating effects

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: An authorized system Operator can inspect exact
  uncertain post-submit request and completion deliveries, hold ambiguous
  effects, and schedule one source-specific reconciliation that verifies
  committed work or invokes the existing owner only when durable facts prove no
  effect.

## Intent

Close the first supported uncertain-delivery recovery boundary left by #581 and
the known-terminal checker retry change. An Operator needs to distinguish a
committed checker result or routing outcome from a request that provably never
started and from an invocation whose external or product effects remain
ambiguous. Committed work must become operationally reconciled without another
checker call, acceptance, contribution, award, Review, or revision round.
Ambiguous work must remain visible and held.

This change covers the two registered post-submit deliveries that complete the
first backend journey: `PostSubmissionEvaluationRequested` and
`PostSubmissionEvaluationCompleted`. Acceptance commit/acknowledgement loss is
the false-review-policy committed form of the completion delivery; it is not a
third operation.

## Current behavior

- OUTBOX commits an `invoked` attempt before calling a handler and finalizes an
  interrupted or exceptional invocation as immutable `dead_letter` /
  `INVOKE_OUTCOME_UNKNOWN` custody. Request and completion handlers are not in
  the registry's `replay_safe` set. `OutboxDeliveryAttempt` and the database
  transition guards deliberately prohibit reopening a terminal attempt.
- `EvaluationRequestHandler` and `DeliveryExecutionAuthority` require one live
  invocation while the existing `PostSubmissionExecutor` claims, executes and
  finalizes a CHECKERS run. Durable CHECKERS state distinguishes an untouched
  queued reservation from a running lease and from an exact terminal result.
- `EvaluationCompletionHandler` calls the existing
  `TaskPostSubmitOutcome` in one root transaction. The retained
  `TaskPostSubmitRoutingManifest` and its database-closed consequences identify
  a committed routing result. A false-policy manifest binds the single
  `FinalAcceptance`, submitter `ContributionRecord`, complete governed award
  set, TASK/assignment effects, audit and outcome event. The operation's replay
  path validates those exact facts but currently also requires a live original
  OUTBOX invocation.
- The public Operator surface lists and retries only exact current finalized
  `infrastructure_failed` checker runs. It intentionally excludes queued,
  running, completed and uncertain-delivery sources. OUTBOX exposes aggregate
  drain counts, not privacy-bounded per-delivery inspection or source-specific
  reconciliation.

## Bounded change

### Allowed

- `.commitrail/changes/mvp-operator-uncertain-delivery-reconciliation.md`.
- Existing OUTBOX public contracts, repository observation/fence code,
  production static registration and focused delivery tests, only to expose an
  exact finalized-UNKNOWN observation and bind one registered post-submit
  reconciliation event to its original terminal attempt. The original event and
  attempt remain immutable. No generic reopen or redrive API.
- Existing CHECKERS execution public contracts, coordinator/repository and
  delivery-authority composition, plus one cohesive source-specific
  reconciliation module, only to classify exact request execution facts and to
  reuse `PostSubmissionExecutor` under a live reconciliation-event fence after
  proving the original run has no execute lease/evidence/result. Existing
  `require_current_completion` and finalized-infrastructure source validation
  supply committed verification; do not copy their row predicates.
- Existing TASK evaluation delivery, routing request/source/outcome public
  ports and composition, plus one cohesive source-specific reconciliation
  module, only to classify exact completion facts, extract a nonmutating source
  observer from the existing routing source owner, extract an owner-owned
  retained-outcome verifier from `TaskPostSubmitOutcome` replay validation, and
  reuse `TaskPostSubmitOutcome` under a live reconciliation-event fence after
  proving no routing manifest/effects committed. The verifier must validate
  retained effects without calling `apply` or acceptance participation.
- Existing checker operations router and one focused API dependency/composition
  module for project-scoped Operator list/reconcile endpoints, signed
  bounded cursor, reason and UUID idempotency key, canonical transaction
  rollback/denial restaging, exact HTTP error mapping and privacy-bounded DTOs.
- Existing AUTH action/permission catalogue, action groups, prepared-resource
  matching, read and mutation adapters, audit pair constraint and focused AUTH
  fixtures/tests for exactly
  `operations.post_submit_delivery.list` / `operations.status.read` and
  `operations.post_submit_delivery.reconcile` /
  `operations.reconcile.run`. Add no permission, role, alias or service grant.
- One coordinated migration file `0055_operational_delivery_reconciliation.py`
  with revision `0055_delivery_reconciliation` after the separately owned
  `0054_artifact_proof_timing`. The migration may
  add only those two exact action/permission pairs and the exact
  `outbox_delivery` resource type to the closed audit constraints. The target
  remains the canonical project target; the migration adds no target or
  invalidation namespace. Include the corresponding Alembic
  head/fingerprint/test updates. It has no S3 runtime dependency; its only
  relationship to `0054` is the required linear schema sequence. Consume the
  canonical published `0054` before authoring `0055` and do not create a
  sibling migration.
- Focused real PostgreSQL request/completion recovery, public API, AUTH,
  transaction, concurrency, migration and delivery registration tests; exact
  ownership/lane/action/rate/OpenAPI inventories affected by the new routes and
  modules.
- `docs/operations_operator_workflow.md` and affected current claims across
  `README.md` and `docs/roadmap_status.md`. Update local roadmap XLSX/CSV only if
  the capability ledger change requires changing those present exports.

### Not allowed

- No reopening or rewriting the original OUTBOX event/attempt/outcome; no
  generic dead-letter redrive, `retry_unknown` registration, automatic UNKNOWN
  retry, broad event-type plugin, broker replacement or delivery-state repair.
- No repeat of an external checker when any execute lease/evidence or uncertain
  external phase exists. No treating an expired CHECKERS lease as proof of no
  effect. No retry when source, generation, locked policy, project or current
  TASK/CHECKERS custody changed.
- No second checker retry owner, direct product-row repair, mutable recovery
  receipt, reverse audit search as business truth, compatibility path or
  fallback authorization.
- No changed locked policies, contributor resubmission/revision charge, new
  Review or reviewer contribution, human decision runtime, acceptance policy
  change, payment fulfillment, reputation, CLI or frontend work.
- No raw OUTBOX payloads, artifact bodies, findings bodies, provider
  coordinates, exception text, `outcome_json`, event payload, transport or
  provider details, credentials or private assignment identity in public
  responses or diagnostics.
- No broad full-suite, Docker, Rust or cloud work in local authoring. #555 owns
  the later complete durable-worker interruption drill; this PR proves focused
  source-specific boundaries and does not claim deployment.

## Design and decisions

### Closed observations

The public read selects only project-qualified, finalized attempts whose stored
outcome says `invocation_unknown=true` and whose event type/version is one of the
two exact production post-submit handlers. It reports bounded delivery identity,
generation/timestamps/state, a closed `error_code` classification and bounded
source identity/status without returning exception text, `outcome_json`, event
payload or transport/provider detail. Stable pagination orders by finalization
time and event ID and binds the signed cursor to project, filters and limit. A
nonlocking owner-qualified selector conceals an absent or foreign project before
any foreign product row lock. Fresh system-Operator read authority is then
recorded before the project-bound delivery and product projection.

The source-specific classifier returns exactly:

- `committed`: the request has one exact terminal CHECKERS result with its
  phase evidence and the event shape required by that outcome (a completed run
  has its exact completion event; an infrastructure failure has none), or the
  completion has one exact database-closed routing manifest and all required
  branch effects. For false policy this includes the original FinalAcceptance,
  contribution and complete award set. Corrupt or partial apparent effects are
  not committed.
- `retry_safe`: the request is the exact current queued reservation with lease
  generation zero and no execute/finalize/material/result/completion evidence,
  or the completion is the exact current terminal CHECKERS source with no
  routing request/manifest/effects and unchanged TASK/policy branch. The
  completion observation uses a nonmutating owner method extracted from
  `TaskRoutingSourcePreparer`; it must not call `TaskRoutingRequests._stage`,
  allocate IDs or create a routing request. The observation is rechecked under
  the canonical mutation locks before a recovery event is appended.
- `unresolved`: every other shape, including running/expired CHECKERS leases,
  partial or inconsistent retained facts, stale/superseded source, unsupported
  event/version, or a reconciliation child that itself finalized UNKNOWN. It
  remains visible and no event is appended.

Committed request classification delegates to CHECKERS
`require_current_completion` for completed delivery and the canonical #588
finalized-infrastructure source validator for infrastructure failure. Committed
completion classification delegates to a read-only verifier extracted from the
existing `TaskPostSubmitOutcome` replay branch. That verifier owns the complete
check of the exact retained source/manifest,
`public.task_routing_outcome_complete`, authorization/audit/outcome notice, and
the false-policy FinalAcceptance, submitter contribution and complete governed
award set. It never calls `TaskPostSubmitOutcome.apply`,
`acceptance.participate` or any effect writer.

Work failure, finalized infrastructure failure and exhausted known-terminal
retry remain projected as source facts but do not become uncertain-recovery
authorization. The existing #588 route remains their sole retry path.

### Durable source-specific recovery

The original UNKNOWN attempt stays immutable. A successful Operator command
uses prepared AUTH bound to project, original event/generation/digest, exact
classification, bounded reason and request key, then appends one immutable
`PostSubmissionDeliveryReconciliationRequested` event. The child contains only
the exact original selectors, classification, Operator decision reference and
request digest; it carries no original payload. OUTBOX idempotency provides
same-key replay. Exactly one child may exist for an original attempt. A
source-level uniqueness guard and locked child lookup make concurrent different
keys deterministic conflicts; every later different key conflicts after a
pending, active, acknowledged or UNKNOWN child. This first release deliberately
holds a child whose own outcome is UNKNOWN rather than adding child generations
or another recovery mechanism.

Public qualification and branch selection are detached, nonmutating
observations and grant no authority. Request mutation follows the existing
`DeliveryExecutionAuthority` TASK/AUTH/CHECKERS order and fences the original
OUTBOX invocation rows last; this plan does not introduce a second lock path.
Completion mutation first observes the branch without locks; when false-policy
acceptance is possible it acquires the REV lifecycle fence first, then TASK,
assignment/submission, PROJECTS, CHECKERS, AUTH and finally OUTBOX invocation
custody. Both paths re-read the exact branch, source currentness, original
UNKNOWN attempt and absence of a child after all canonical locks and before
append. A mismatch rolls back. Independent-session races cover an original
transaction committing or rolling back while the command classifies, plus two
concurrent commands, so no-effect observation and recovery cannot race a live
business commit.

The child handler first proves its own live invocation, then obtains the
original finalized-UNKNOWN envelope through a typed OUTBOX observation port.
The Operator decision is an immutable cause, not worker authority. The handler
validates it through a narrow AUTH cause port, while the existing executor and
routing outcome continue to obtain their current fixed-service execute,
finalize and route authority. No service gains an Operator permission.

- For `committed`, the handler delegates to the CHECKERS committed validators or
  the owner-owned read-only TASK retained-outcome verifier and acknowledges the
  child without calling the external checker, `TaskPostSubmitOutcome.apply` or
  acceptance participation. This is the acceptance commit/ack-loss path and
  cannot create another business effect.
- For `retry_safe`, a recovery-bound invocation observer/fence projects the
  child event's live custody only for the exact original envelope. The handler
  reclassifies under the same canonical locks before invoking anything. A
  source that is now committed takes the read-only committed path; a source
  that remains retry-safe invokes the existing `PostSubmissionExecutor` or
  `TaskPostSubmitOutcome`; every stale, partial or uncertain shape is held and
  produces no business effect. Those owners retain all TASK, PROJECTS,
  CHECKERS, AUTH, REV/CON and OUTBOX rules. The child is not `retry_unknown`; if
  its outcome becomes uncertain, the next Operator read reports that one child
  and the original source as held, and no later reconciliation is authorized in
  this release.

The sole child is the immutable reconciliation receipt. Inspection links it to
the original attempt and projects that child as pending, active, acknowledged
or held without changing the original dead letter. OUTBOX's internal UNKNOWN
child state is exposed only as the closed public `held` classification.

### Alternatives rejected

- Reopening the original event discards immutable phase custody and violates
  existing database guards.
- Marking either production handler `retry_unknown` guesses that no effect
  occurred and makes duplicate broker delivery an authorization source.
- Calling the external checker synchronously from the public Operator request
  bypasses the existing durable worker boundary.
- Treating only an AUTH audit row as the recovery receipt cannot supply live
  worker invocation custody or serialize two different request keys.
- A generic reconciliation table/engine is unnecessary: the existing OUTBOX
  event is the durable request/receipt, and the handler admits only two named
  sources with closed classifiers.

## Acceptance criteria

- [x] A current system Operator can list bounded exact request/completion
  UNKNOWN attempts for one project with signed stable pagination, source run and
  generation, delivery attempt state and one of committed/retry-safe/unresolved;
  the response contains no raw payload, artifact/provider data, credential or
  private assignment identity.
- [x] Wrong actor kind, absent/revoked/non-Operator grant, foreign project,
  malformed cursor, wrong source/generation, changed-key payload and stale
  source fail closed with canonical concealed/conflict/unavailable behavior,
  denial evidence and no product or recovery event.
- [x] A terminal CHECKERS request result is reconciled by an acknowledged child
  without another external execution, result, completion event or business
  audit. A queued generation-zero request may execute once through the existing
  owner; running, expired-running and partially evidenced requests remain held.
- [x] A complete routing manifest is reconciled without calling the routing
  operation or acceptance participation. The owner-owned verifier checks the
  database closure, exact source/manifest, authorization/audit/outcome notice
  and branch effects. False-policy acceptance commit/ack-loss retains exactly
  one FinalAcceptance, submitter ContributionRecord and governed award set and
  creates no Review. A no-effect completion may invoke the existing routing
  operation once; partial, stale or inconsistent outcomes remain held.
- [x] Same-key command and response-loss replay return the same recovery event.
  Concurrent or sequential changed keys cannot schedule another child. A child
  that finalizes UNKNOWN remains visibly held and cannot be retried by this
  surface. Transaction,
  AUTH/audit, append, handler and commit failures roll back their caller-owned
  writes, while already committed business effects are detected on the next
  observation rather than repeated.
- [x] The recovery event remains absent from `retry_unknown`; an UNKNOWN child
  is projected as held by later authorized reads from durable source facts, and
  no later reconciliation command or event is allowed.
- [x] Real PostgreSQL tests interrupt request execution before invocation,
  during an uncertain external phase and after finalization; interrupt
  completion before commit and after false-policy acceptance commit; and assert
  exact locks, immutable original attempts, complete/unchanged effects,
  idempotency and no blind repeat. Independent sessions race the original
  commit/rollback against recovery and race two command keys. Handler tests move
  the source between command and child execution and require fresh committed,
  retry-safe or held classification before any effect.
- [x] Production registration, AUTH/action/audit pairs, OpenAPI, route-rate
  controls, ownership and test-lane catalogues include only the exact new
  surface. Current Operator workflow and roadmap describe the delivered limit;
  #581/#555 remain open for the full durable-worker interruption drill.

## Risk and review routing

- Risk class: L1. This crosses public Operator authorization, immutable OUTBOX
  custody, external execution and atomic acceptance/economic effects.
- Required reviewers: architecture, security, QA, test delta, product/operations,
  reuse/dedup, CI integrity and documentation. Plan review must first challenge
  whether the child event is necessary, whether existing operations are reused
  without fabricated invocation, and whether every retry-safe predicate is
  race-free under the actual lock order.
- Human review focus: the closed classifier, original-versus-child custody,
  prepared Operator cause versus unchanged fixed-service authority, no-repeat
  acceptance proof, concurrent keys, privacy projection, migration sequencing
  and the explicit #555 limit.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing terminal UNKNOWN attempts are immutable and excluded from automatic replay | Inspect OUTBOX delivery/model/recovery SQL guards and production registry | Confirmed on base | Plan review must challenge whether a child event is the smallest safe execution seam |
| Request source has a durable no-effect discriminator | Inspect CHECKERS queued/running/terminal state, lease generation and phase evidence | Queued generation zero with no phase evidence is distinct; running or expired-running is uncertain | Real PostgreSQL race/interruption proof required |
| Completion commit is atomically distinguishable | Inspect `TaskPostSubmitOutcome`, routing manifest and deferred closure | Complete manifest is the retained outcome; absent transaction leaves no committed routing effects | Real false-policy commit/ack-loss and corruption proof required |
| Existing operations remain sole writers | Recovery-bound typed invocation observation composes the existing executor/outcome owners; committed completion uses the extracted read-only retained-outcome verifier | Focused public PostgreSQL proofs pass without a repeated checker, routing, acceptance, contribution or award effect | The full durable-worker interruption drill remains #555 |
| Public authority remains least privilege | Exact list/status.read and reconcile/reconcile.run pairs; project-targeted `outbox_delivery` audit resource; cause validation while existing owners retain their fixed-service actions | Catalogue/OpenAPI/rate proofs pass; public PostgreSQL denial, revocation and same-key replay proofs pass | No new permission, role or service grant |
| Migration preserves closed audit vocabularies | Upgrade from 0054 to `0055_delivery_reconciliation`, direct inserts for both exact pairs/resource, wrong pair and target rejection, downgrade refusal | 1/1 focused PostgreSQL migration test passed in 64.20s at `9581e3e5a`; cleanup complete | Final full-suite execution remains repository CI evidence |
| Request, completion and child custody are source-specific | Seven public PostgreSQL cases plus three independent-session races; immutable original, one child, committed verification, retry-safe execution, held UNKNOWN, source transition and foreign denial | First public path 1/1 at `e4918bc10` (47.25s); committed acceptance 1/1 at `6be05ae89` (29.20s); first five public cases passed at `ef4789198`; final transition/denial/race slice 5/5 at `3e6b61e5c` (162.14s), with isolated cleanup complete | Split-head evidence is exact about its provenance; later changes after `e4918bc10` affect tests, docs and generated ownership data only |
| Closed contracts and production inventories match the surface | DTO/privacy/idempotency contracts, canonical OUTBOX append validation, AUTH catalogue, OpenAPI, rate, ownership and lane checks | 33/33 focused contracts passed; three focused inventory/API checks passed; boundary, structure, ownership, Commitrail, link and stale-wording checks passed | No generic OUTBOX recovery surface was added |
| Full interruption drill | Parent #555 durable-worker matrix | Deferred | This PR must not claim the complete #555 drill or deployed operation |

## Review findings

- `REC-581-PLAN-ARCH-001` closed in plan: detached branch observation now leads
  into the existing false-policy REV -> TASK -> assignment/submission ->
  PROJECTS -> CHECKERS -> AUTH -> OUTBOX order, with post-lock recheck and
  independent-session commit/rollback and two-command races.
- `REC-581-PLAN-QA-001` closed in plan: committed completion uses one read-only
  verifier extracted from the `TaskPostSubmitOutcome` replay owner; request
  verification delegates to the existing CHECKERS completion and
  finalized-infrastructure validators.
- `REC-581-PLAN-REUSE-001` closed in plan: completion observation extracts a
  nonmutating routing-source method and cannot call request staging or allocate
  IDs.
- `REC-581-PLAN-PROD-001` closed in plan: exactly one immutable child is
  permitted; same-key replay is exact, every different key conflicts, and a
  child UNKNOWN remains visibly held rather than introducing a sequencing
  subsystem.
- Architecture/security plan review also required two exact AUTH pairs and the
  required 0055 migration after 0054, plus a closed public `error_code`; both
  are now explicit.

## Reconciliation

- Current-source reconciliation: stacked on canonical artifact-proof timing
  source `2a67bf6d9`, which contains `0054_artifact_proof_timing` and is based on
  main `51b86807111ff25b067402219ba0b533e0750f3e`. This change owns the single
  linear `0055_delivery_reconciliation` migration; `0054` remains byte-for-byte
  under its original owner and is not a runtime dependency of recovery.
- Next usable boundary: after this focused source-specific recovery passes,
  #555 must run the complete durable-worker interruption matrix against the
  supported public path before #581 can close.
- Remaining risks: source-specific UNKNOWN outside these two exact event types,
  human-review decisions, fulfillment/payment callbacks and deployed hosted
  recovery remain held and out of scope.
