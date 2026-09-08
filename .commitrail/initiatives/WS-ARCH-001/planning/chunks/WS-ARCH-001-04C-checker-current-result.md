# Chunk Contract: WS-ARCH-001-04C CHECKER Current Result Persistence

Disposition: Planned. Dependencies: 04A, 04B, its ART-owned output-custody
child and POL-07. Risk: L1. Outcome:
CHECKERS installs hidden, deny-only execution of the exact post-submit plan and
persists one immutable final result with explicit
supersession/currentness and routing recommendation.

Allowed: CHECKER owner-local run/result repository, service and Celery execution code,
its public API, focused tests, migrations chosen from current main, boundary
ledgers and evidence/status. Not allowed: ART binding writes, TASK status
mutation, AUTH activation, REV admission, model inference outside the compiled
policy, or synchronous-first execution.

Execution must reuse the POL-003 single checker-service port and
`evaluate_post_submission(...)`; no second dispatcher, phase API, catalogue,
or caller-triggered execution path is allowed. Production remains fail-closed
until 04D activates the exact fixed-service boundaries.

This is the only owner of the durable post-submit attempt, member-result,
final-result, supersession/currentness and worker-recovery writes. POL-07
declares the facade contract, not a competing persistence implementation.
Reuse the existing CHECKER registry/executor where compatible. Platform
defaults plus approved project rules execute once per logical attempt;
pre-submit evidence cannot substitute for post-submit evaluation.

Consume 04A's opaque `evaluation_request_id` and immutable envelope, without a
TASK dispatch-row lookup or foreign key. Own database uniqueness for
`(evaluation_request_id, phase)` and derive member/provider recovery identity
from that logical attempt. A matching key with a different envelope denies.
CHECKERS also owns a per-Submission currentness fence and a flush-only public
participant to initialize/advance it in a caller transaction. 04E later calls
that participant while coordinating TASK-owned evaluation generations; hidden
04C tests use controlled callers, not future TASK persistence.

Finalization locks the CHECKERS fence/result, validates that the request's
generation is still current, and changes only CHECKERS-owned state. It never
locks or mutates TASK rows and never independently advances the fence to make
an obsolete request current. A new coordinated generation supersedes the old
request; immutable completed results remain preserved. Public current-result
facts expose the exact request, generation, phase, attempt and final digest.

CHECKERS owns the typed immutable final-result notification envelope and its
same-transaction shared-outbox append here: exact project/Submission,
evaluation request/generation, phase/attempt, final digest/currentness and
verified binding/allow-event references. 04E1B later consumes that published
contract; it does not define CHECKERS events after their producer exists.

Do not hold row locks or PREP across evaluator/provider I/O. Persist the
attempt reservation before I/O, materialize only after fresh authority, and
revalidate exact current authority/lineage before atomic final persistence.
Unknown outcomes of unfinished provider calls recover the same attempt and
idempotency identity, not a fresh billable call. A terminal infrastructure
failure stays terminal: an Operator-authorized retry requires a reason and a
new superseding request/generation through the coordinated participant, as the
canonical checker architecture requires. No public retry action is activated
here. A late revoked result cannot become current or routable.
Member/running/retryable state is not a completed current phase result.

Keep execution-lease fencing separate from evaluation-request generation and
outbox delivery claims. CHECKERS owns the active worker lease/generation on
the logical attempt. Recovery may replace an expired worker lease, never the
attempt/provider identity. Finalization validates both the current evaluation
fence and exact active execution lease under lock; an old worker cannot
publish after takeover even if its evaluation request is still current.
Unknown provider outcomes may be retrieved/resumed only where the adapter
proves that capability; absent it, remain blocked rather than invoking again.
Prove slow-worker/takeover completion in both orders and no duplicate provider
call or final output from stale leases.

Required logs/generated outputs pass the ART-owned output admission and
independent verification path before final publication. Compose verified
checker-output bindings and CHECKERS final completion in one caller transaction
through owner public ports. Missing, stale, unverified or mismatched required
output prevents final-current result/routing. Do not implement ART writes here,
persist provider locations as evidence, or charge output bytes to a contributor.

The final multi-participant transaction must declare one lock order consistent
with AUTH PREP: prepare required service authority custody before feature locks,
then CHECKERS currentness/run and ART binding custody, with stable ordering for
multiple rows. Recompose/consume the exact facts after those locks. The ART
participant cannot privately reacquire CHECKERS rows or introduce a reverse
authority/feature lock order. Prove independent-session finalization/binding
contention and whole-transaction rollback; do not rely on retrying deadlocks
to conceal an inconsistent lock protocol.

Separate contributor-correctable work failures, project-policy/setup faults,
and retryable infrastructure/provider failures. Only a fully completed current
result satisfying every blocking rule may recommend `allow_review`; no
checker emits `accept` or creates a contribution record. Define these typed
failure categories in the canonical CHECKER contract, not ad hoc TASK strings.

Acceptance: retry and concurrency yield one current final result; stale plan,
generation, binding or Submission fails; `allow_review` is impossible for
failed/partial execution or while any blocking failure remains under the
locked post-submit policy; a blocking failure and current `allow_review`
cannot coexist; audit/outbox facts are atomic. Verify unit,
PostgreSQL concurrency, Celery retry/recovery, boundary validators, Ruff and
hosted coverage. Required reviews: architecture, security, product/ops, QA,
senior, CI and test delta.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

## Merge state

- Outcome on merge: `planned`
