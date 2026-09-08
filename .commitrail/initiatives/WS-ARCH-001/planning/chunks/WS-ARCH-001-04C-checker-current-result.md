# Chunk Contract: WS-ARCH-001-04C CHECKER Current Result Persistence

Disposition: Planned. Dependencies: 04A, 04B and POL-07. Risk: L1. Outcome:
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

Do not hold row locks or PREP across evaluator/provider I/O. Persist the
attempt reservation before I/O, materialize only after fresh authority, and
revalidate exact current authority/lineage before atomic final persistence.
Unknown provider outcomes recover the same attempt/idempotency identity, not a
fresh billable call. A late revoked result cannot become current or routable.
Member/running/retryable state is not a completed current phase result.

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
