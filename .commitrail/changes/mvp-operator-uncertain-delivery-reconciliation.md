# Reconcile uncertain post-submit delivery without repeating effects

- Initiative: None
- Durable disposition: Planned
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
  terminal-result validation supplies committed verification.
- Existing TASK evaluation delivery, routing request/source/outcome public
  ports and composition, plus one cohesive source-specific reconciliation
  module, only to classify exact completion facts and reuse
  `TaskPostSubmitOutcome` under a live reconciliation-event fence after proving
  no routing manifest/effects committed. Exact retained manifest/effect replay
  supplies committed verification.
- Existing checker operations router and one focused API dependency/composition
  module for project-scoped Operator list/detail/reconcile endpoints, signed
  bounded cursor, reason and UUID idempotency key, canonical transaction
  rollback/denial restaging, exact HTTP error mapping and privacy-bounded DTOs.
- Existing AUTH action/permission catalogue, action groups, prepared-resource
  matching, read and mutation adapters, audit pair constraint and focused AUTH
  fixtures/tests for two exact actions: an Operator status read and an Operator
  reconciliation command. Reuse `operations.status.read` and
  `operations.reconcile.run`; add no permission or role.
- One coordinated migration numbered `0055` only if the exact AUTH audit-pair
  constraint requires it after the separately owned `0054`. The migration may
  add only the two exact action/permission audit pairs and the corresponding
  Alembic head/fingerprint/test updates. It must not depend on S3 behavior; the
  dependency is migration-chain ordering only. If plan review finds a
  constraint-safe existing action that is semantically exact, omit the
  migration rather than creating it ceremonially.
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
  coordinates, transport errors, credentials or private assignment identity in
  public responses or diagnostics.
- No broad full-suite, Docker, Rust or cloud work in local authoring. #555 owns
  the later complete durable-worker interruption drill; this PR proves focused
  source-specific boundaries and does not claim deployment.

## Design and decisions

### Closed observations

The public read selects only project-qualified, finalized attempts whose stored
outcome says `invocation_unknown=true` and whose event type/version is one of the
two exact production post-submit handlers. It reports bounded delivery identity,
generation/timestamps/state/error and source identity/status without returning
the event payload. Stable pagination orders by finalization time and event ID and
binds the signed cursor to project, filters and limit. Fresh system-Operator
authority and the selected project are locked before any delivery or product
query.

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
  observation is rechecked under canonical TASK/CHECKERS/OUTBOX locks before a
  recovery event is appended.
- `unresolved`: every other shape, including running/expired CHECKERS leases,
  partial or inconsistent retained facts, stale/superseded source, unsupported
  event/version, or an uncertain recovery attempt. It remains visible and no
  event is appended.

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
same-key replay. The command locks the source in canonical feature order and
the original OUTBOX rows last, so classification and append cannot race another
source transition. A source-level lock and existing child lookup prevent two
different keys from scheduling concurrent recovery for the same original
attempt; changed-key facts conflict rather than produce another effect.

The child handler first proves its own live invocation, then obtains the
original finalized-UNKNOWN envelope through a typed OUTBOX observation port.
The Operator decision is an immutable cause, not worker authority. The handler
validates it through a narrow AUTH cause port, while the existing executor and
routing outcome continue to obtain their current fixed-service execute,
finalize and route authority. No service gains an Operator permission.

- For `committed`, the handler validates the exact terminal result or complete
  routing outcome and acknowledges the child without calling the external
  checker or `TaskPostSubmitOutcome.apply`. This is the acceptance
  commit/ack-loss path and cannot create another business effect.
- For `retry_safe`, a recovery-bound invocation observer/fence projects the
  child event's live custody only for the exact original envelope. The handler
  then invokes the existing `PostSubmissionExecutor` or
  `TaskPostSubmitOutcome`; those owners retain all TASK, PROJECTS, CHECKERS,
  AUTH, REV/CON and OUTBOX rules. The fence is acquired after the feature locks
  and rechecks the source classification in the same transaction. The child is
  not `retry_unknown`; if its outcome becomes uncertain, the next Operator read
  reclassifies from durable source facts. A later reconciliation may verify a
  committed effect, authorize a still-proven-no-effect try, or hold it.

An acknowledged child is the immutable reconciliation receipt. Inspection
links it to the original attempt and shows pending, active, acknowledged,
unknown or held reconciliation state without changing the original dead letter.

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

- [ ] A current system Operator can list bounded exact request/completion
  UNKNOWN attempts for one project with signed stable pagination, source run and
  generation, delivery attempt state and one of committed/retry-safe/unresolved;
  the response contains no raw payload, artifact/provider data, credential or
  private assignment identity.
- [ ] Wrong actor kind, absent/revoked/non-Operator grant, foreign project,
  malformed cursor, wrong source/generation, changed-key payload and stale
  source fail closed with canonical concealed/conflict/unavailable behavior,
  denial evidence and no product or recovery event.
- [ ] A terminal CHECKERS request result is reconciled by an acknowledged child
  without another external execution, result, completion event or business
  audit. A queued generation-zero request may execute once through the existing
  owner; running, expired-running and partially evidenced requests remain held.
- [ ] A complete routing manifest is reconciled without calling the routing
  operation. False-policy acceptance commit/ack-loss retains the exact one
  FinalAcceptance, submitter ContributionRecord and governed award set and
  creates no Review. A no-effect completion may invoke the existing routing
  operation once; partial, stale or inconsistent outcomes remain held.
- [ ] Same-key command and response-loss replay return the same recovery event.
  Concurrent changed keys cannot schedule two active children. Transaction,
  AUTH/audit, append, handler and commit failures roll back their caller-owned
  writes, while already committed business effects are detected on the next
  observation rather than repeated.
- [ ] The recovery event remains absent from `retry_unknown`; an UNKNOWN child
  is reclassified only by a later authorized source-specific command.
- [ ] Real PostgreSQL tests interrupt request execution before invocation,
  during an uncertain external phase and after finalization; interrupt
  completion before commit and after false-policy acceptance commit; and assert
  exact locks, immutable original attempts, complete/unchanged effects,
  idempotency and no blind repeat.
- [ ] Production registration, AUTH/action/audit pairs, OpenAPI, route-rate
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
| Existing operations can remain sole writers | Inject a recovery-bound typed invocation observer/fence into existing executor/outcome composition | Planned | Architecture/security review and exact integration proof required |
| Public authority can remain least privilege | Two exact actions reuse existing Operator permissions; handler validates decision as cause and uses current service actions | Planned | Catalogue/audit migration and revocation/substitution proof required |
| Full interruption drill | Parent #555 durable-worker matrix | Deferred | This PR must not claim the complete #555 drill or deployed operation |

## Review findings

No plan or implementation review findings recorded yet.

## Reconciliation

- Current-source reconciliation: based on main
  `51b86807111ff25b067402219ba0b533e0750f3e`, including merged #588 known-terminal
  Operator recovery, #589 registry/AUTH audit pairs, #592 S3 activation, #590
  hosted release configuration and #597 identity lifecycle. S3 separately owns
  the next `0054`; this change reserves no competing migration.
- Next usable boundary: after this focused source-specific recovery passes,
  #555 must run the complete durable-worker interruption matrix against the
  supported public path before #581 can close.
- Remaining risks: source-specific UNKNOWN outside these two exact event types,
  human-review decisions, fulfillment/payment callbacks and deployed hosted
  recovery remain held and out of scope.
