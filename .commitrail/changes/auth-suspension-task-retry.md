# Deny suspended self access and recover committed task commands

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: suspension denies self-read and self-update; existing
  task claim/start commands support authorized durable idempotent replay.

## Intent

The human confirmed that suspension blocks even self-read. Before this change,
AUTH's self evaluator and actor response allowed suspended reads. Claim/start
prevented duplicate assignments but could not recover their success after a lost
response. ARCH-03C already requires replay; fulfill that bounded requirement
here rather than build a competing claim operation. Merged ARCH-03B2 owns the
hidden ready queue and remains unchanged.

## Bounded change

Allowed: AUTH self lifecycle evaluator, `actors/service.py` self response, TASK command/router/model/repository and
typed authority facts, exact AUTH task resource/PREP adapter, an additive task
receipt migration and migration admission, affected caller tests/drills, schema
fingerprint/reset inventory, behavior-owner inventory, focused test-lane registration if needed, canonical
AUTH/TASK specifications, roadmap and ARCH-03C remaining-scope reconciliation.
The MCP lifecycle parity test must assert the same suspended-access denial as REST.
Refresh exact structural-debt inventory for the shrinking touched AUTH owners;
refresh current assertion-map targets while retaining historical provenance;
do not raise limits, add debt or grant exceptions.
No multiple issuers, queue activation, new permissions, new claim operation,
assignment invalidation, submission/review lifecycle changes, retained-data
deletion, compatibility fallbacks or weakened CI/coverage.

## Design and decisions

- Remove the suspended self-read exception; active-link/active-profile checks
  continue to govern self read/update. Revoked/deactivated denial is unchanged.
- Require a canonical UUID Idempotency-Key on claim, start and reasoned operator
  start. Reuse the core header parser; validate before actor provisioning.
- TASK owns one durable receipt namespace (actor, operation, key), request digest,
  task/assignment identity, locked-context digest and typed success-response
  snapshot. Reserve with PostgreSQL's existing insert/conflict-lock convention;
  complete in the same transaction as assignment/state and lifecycle audit.
  Receipt lock precedes TASK/assignment then AUTH locks; no second session or
  independently committed reservation. Failure rolls back the reservation too.
  The receipt's actor FK is initially deferred: its implicit KEY SHARE must not
  precede AUTH's actor lock and deadlock parallel commands from the same actor.
  PostgreSQL still enforces the FK at commit.
  Database guards forbid deletion/truncation and material alteration of committed
  receipts; exact no-op conflict locking remains allowed. Pending completion is
  the only material update. Parse the stored response and bind its task/assignment
  identities to both receipt and freshly locked rows before returning it.
- Current caller authorization is checked before exposing replay/mismatch
  results. A stored receipt is not authority. Extend the existing typed task
  facts/resource with receipt-backed replay assignment identity so AUTH evaluates
  actual post-operation state, never fabricated pre-operation state. PREP binds
  the exact key, request and replay facts; do not add replacement action IDs.
- Replay requires the original task, active assignment, contributor, locked
  policy context and expected result state (claimed for claim, in_progress for
  start). Claim replay requires a claimed task and its active own assignment;
  start replay requires in_progress and its active own assignment; operator
  replay requires in_progress, a consistent active non-self assignment and the
  same nonblank reason. All require exact receipt assignment identity.
  Stale/mismatched replay never succeeds: if fresh AUTH denies the current
  post-state, return its normal concealed denial. Only after current authority
  succeeds may TASK disclose a bounded 409 request/receipt/context conflict.
  Same namespace with different task/reason rejects without mutating either.
  Fresh authority evidence is allowed; no duplicate lifecycle success event.
- Return the stored typed response for valid replay. A generic response cache,
  token-based replay authority and assignment-only duplicate detection cannot
  safely meet the lost-response requirement and are not introduced.

## Acceptance criteria

- Suspended self GET/PATCH deny without writes; active control succeeds; revoked
  and deactivated cases retain their denials.
- Missing/malformed/duplicate keys fail before provisioning. OpenAPI declares
  the required key, and all affected callers use it without a compatibility path.
- Claim, normal start and operator start replay their exact response after a
  committed result; one assignment/transition/receipt remains. Cross-actor keys
  are isolated and operations have distinct namespaces.
- Same-key changed task/reason fails; absent/revoked/foreign grant, suspended
  actor, revoked link and changed assignment/context/state cannot replay success.
- Independent PostgreSQL sessions prove same-key serialization and different-key
  claim contention. Inject failures after evidence/receipt staging and prove
  rollback of task, assignment, receipt and success evidence; retry can succeed.
- Direct SQL/schema tests protect receipt ownership/shape. Existing lineage,
  claim races and hidden queue tests remain intact.
  Direct SQL must also reject committed identity/digest/response rewrites,
  deletion and truncation while allowing the exact no-op used for locking.

## Evidence

Commands: focused `pytest --no-cov` actor self, task authority/PREP and new
`tests/tasks/test_command_replay.py` tests; real PostgreSQL through
`scripts/run_isolated_tests.py`; Ruff; module/AUTH boundaries; migration/schema
fingerprint proof; links/stale scans; full hosted Backend and MCP checks.
Named tests define required verification; current execution and review results
belong in the PR, not this durable intended-outcome record.

Named proofs in `test_command_replay.py`: `test_committed_task_response_replays_once`,
`test_task_key_mismatch_rejects_reason_and_target`, `test_task_key_namespace_is_per_operation`,
`test_replay_rechecks_current_authority`, `test_same_key_independent_sessions_have_one_result`,
`test_receipt_failure_rolls_back_and_retry_succeeds`, `test_task_key_validated_before_provisioning`,
and `test_committed_receipt_is_immutable_through_sql`. The actor lifecycle suite's
`test_suspended_profile_is_not_readable` protects the removed exception.

## Risk and review routing

- Risk class: L1 (authorization, idempotency, transaction and schema).
- Required reviewers: security; architecture/reuse; QA/test-delta;
  documentation; CI integrity for schema/test inventory changes.
- Human focus: suspension denies all self access; replay never revives revoked
  authority or reports an old assignment as current; no multiple-issuer work.
- Plan review precedes code; implementation reviews use a clean exact target.

## Reconciliation

Base includes merged #419. Existing claim/lineage writers and hidden queue are
reused. ARCH-03C keeps its remaining activation/projection/invalidation work;
this change removes only its unimplemented claim/start replay requirement.
No additional human decision is needed within the confirmed scope.

## Review-driven corrections

- Preserve old assertion IDs, spans and source hashes in the AUTH split map,
  while explicitly superseding the old suspended-read allowance with the
  human-confirmed denial contract. This is a policy correction, not a claim
  that the old `200` assertion is preserved.
- Update the migration-chain proof and all current self-access/drill wording.
- Prove failure rollback and same-key recovery separately for claim, start and
  operator start. Exercise revoked system-Operator authority and each exact
  non-self post-state guard, rather than infer them from submitter replay.
