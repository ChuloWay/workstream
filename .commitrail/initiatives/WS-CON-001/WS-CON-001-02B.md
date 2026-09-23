# CON-02B — Hidden shared outbox delivery and recovery

- Initiative: WS-CON-001
- Durable disposition: Complete
- Intended merge outcome: one hidden, feature-neutral claim/invoke/finalize operation
  with committed claim custody, bounded automatic recovery and truthful drain
  facts. Production dispatch remains unavailable until AUTH-OUTBOX-02.

## Intent

The project/task lifecycle needs durable follow-up after a transaction commits.
Reuse `OutboxEvent`, the caller-transaction append participant, existing delivery
states and the AUTH-OUTBOX-01 preparation contract. Do not create another queue,
feature permission system or provider integration.

Base is main `08556adf` after PR #427. Existing persistence already fences state
transitions, immutable envelopes, deletion and archival. It has no dispatcher.
It clears worker/lease facts on finalization and retains no outcome digest, so
its current row alone cannot prove an exact finalization replay. Add the minimum
per-event/generation custody record to preserve those facts. Current business
policy and submission versions are unrelated to this storage change.
Existing event projection and new custody must agree at transaction commit;
deferred constraints protect both mutation directions, not only normal service
writes. A completed custody outcome remains immutable.

## Bounded change

Allowed files:

- `backend/app/modules/outbox/`: independent public claim/outcome/drain contracts,
  typed static handler registry, delivery repository, custody model and hidden
  orchestration. Preserve append ownership and its public result.
- `backend/alembic/versions/0027_outbox_delivery_custody.py`, `alembic/env.py`,
  `app/db/models.py`: register and enforce the new custody records. Preserve the
  baseline and retained data; fail rather than invent unprovable claim history.
- `backend/app/adapters/outbox/__init__.py`: explicit owner composition requiring the
  AUTH preparation factory; no default, permissive adapter or runtime registry.
- Focused `backend/tests/outbox/` contracts, PostgreSQL and recovery tests;
  `tests/test_outbox.py` affected raw-transition fixtures, obsolete persistence-only
  structure assertion and superseded dead-letter-reopening expectation;
  migration graph, exact schema/reset inventory, lane/ownership registrations
  and their exact tests where the new files/table require them.
- `docs/spec_contribution_compensation.md`, affected current capability/navigation and
  architecture/specification documents, this record, and the AUTH-OUTBOX-02
  activation contract in `WS-AUTH-001/planning/PLAN.md`.

Prohibited: active AUTH evaluator/catalogue changes; human/operator authority;
feature handlers or provider calls; public routes; production Celery/beat
registration; new broker/storage provider; compatibility paths; data deletion;
baseline rewriting; gate, coverage or assertion weakening.

The old archived proposal conflated delivery with manual operational controls.
`operations.outbox.retry` is only a planned permission, without an executable
action/port. Dead-letter operator requeue, pending cancellation and delayed
archival therefore remain separate authorized operational work. Preserve existing
SQL protections; 0027 additionally rejects reopening a completed delivery without
new coherent custody. Repair valid raw-SQL fixtures to stage matching custody so
their negative assertions still reach the original guard. Replay means exact committed claim/outcome
redelivery, not an unauthorized manual reopening of terminal work. Actual worker
registration and broker transport belong to AUTH-OUTBOX-02 integration; this PR
must not claim live Redis delivery proof or install a worker that can bypass the
missing authority adapter.

## Delivery design

1. Discover one exact event without locking. Build proposed facts from its
   canonical project, payload digest and generation using database time.
2. In a fresh root transaction, prepare AUTH before any outbox row lock. Lock
   and refresh the exact event, recompose and compare facts, and recheck proposed
   lease validity using locked `clock_timestamp()` after any lock wait. Only then consume one matching
   allow decision, and persist claim plus custody atomically. Commit before
   returning a claim. A competing or changed candidate does not gain authority.
3. In another fresh transaction, prepare INVOKE, lock event then custody in the
   same order, verify committed exact generation/owner/lease, consume authority,
   and record invocation once. Commit and close sessions before calling the
   handler. Duplicate invocation does not run the handler again.
4. A handler receives immutable envelope/payload and claim facts, never ORM rows,
   a dispatcher authority handle or its session. Its own feature composition
   must obtain feature authority and validate the committed claim through the
   public port. The port reads an independent transaction and requires committed
   invocation custody matching the current live claim. This is a point-in-time
   observation, not a lease extension or authority for feature writes. Feature
   integration must provide its own transaction fence, current AUTH and effect
   idempotency; an uncommitted claim cannot validate. One nonlocking SQL statement
   joins current event and incomplete invoked custody, checks all exact facts and
   `claim_expires_at > statement_timestamp()`, and returns immutable facts with DB
   `observed_at` from that same statement-stable instant. A fresh owner-controlled session closes before return. All
   mismatched/uncommitted/expired/completed cases share an unavailable result;
   the port never accepts the dispatcher writer session. Safe explicit retries can invoke multiple generations;
   feature effects must deduplicate by immutable event identity, not generation.
   There is no unconditional at-least-once guarantee: a crash after invocation
   custody commits but before handler entry is conservatively unknown, even when
   the handler actually ran zero times. No concrete feature handler is installed here.
5. Reopen a fresh FINALIZE authorization/transaction. Bind every outcome, error,
   retry and timestamp field through the OUTBOX-owned canonical outcome digest.
   Recompose exact facts under locks, consume authority, then atomically apply
   the outcome and preserve its receipt. No database or authority lock spans
   handler I/O. Stale generations cannot change current event state.

The custody record preserves immutable event/generation/project/payload/worker/
lease facts. Invocation progresses once; completed outcome facts are immutable.
Claimed-but-never-invoked expiry must not fabricate an invocation. Real SQL
guards bind custody and the event's projection in the same transaction and deny
deletion, rewriting and unsupported transitions. Retained attempts lacking
provable custody stop migration; migration must not create fictional evidence.
Database guards also reject invoked non-unknown outcomes completed after expiry,
future completion times, leases longer than one hour and retry delays over one day.

### Closed facts and outcomes

`OutboxClaim` preserves event UUID, project UUID, payload digest, generation,
owner and both UTC lease timestamps. `OutboxEventEnvelope` adds the original
immutable event type/version/aggregate/correlation/idempotency facts and canonical
JSON payload text. Recompute its digest before delivery; do not place a mutable
dictionary or ORM instance inside a nominally frozen envelope.

One custody row per `(event_id, claim_generation)` stores those exact claim
facts, optional `invoked_at`, then the complete canonical outcome. It stores no
AUTH decision UUIDs: the action is planned and cannot produce valid allowed audit
evidence. Before each mutation, require a returned `AuthorizationDecision` with
exact ALLOW/action/permission, following locked fact comparison and fresh DB-time
checks. Injected test ports prove only this synthetic service contract; retain
real AUTH planned-action denial tests. No fake allowed audit rows or permissive
production adapter may stand in for activation.

AUTH-OUTBOX-02 atomically adds the live evaluator, audit resource/action vocabulary,
exact audit matching guards, receipt decision foreign keys and production
composition. It must refuse preexisting attempts without provable authority,
not backfill evidence or delete retained data. This chunk's receipts establish
delivery facts only; they do not claim authorization evidence.

Closed handler results are acknowledge, safe retry, or nonretryable failure.
They carry no arbitrary result text or provider payload. Canonical finalization
contains `delivery_state`, closed `error_code`, `next_attempt_at`, `finalized_at`,
`receipt_completed_at`, `invocation_unknown` and the preserved nullable `invoked_at`. Hash all those
fields including nulls; AUTH's resource facts separately bind the complete claim.

| Source result | Event projection | Error and timestamps | Unknown |
|---|---|---|---|
| Handler acknowledge | acknowledged | error null, retry null, finalized DB time | false |
| Explicit safe retry, budget available | retryable | RETRY_REQUESTED, bounded retry DB time, finalized null | false |
| Explicit retry, budget exhausted | dead_letter | ATTEMPTS_EXHAUSTED, retry null, finalized DB time | false |
| Explicit nonretryable failure | dead_letter | HANDLER_REJECTED, retry null, finalized DB time | false |
| Never-invoked lease expiry, budget available | retryable | LEASE_EXPIRED_BEFORE_INVOKE, bounded retry DB time, finalized null | false |
| Never-invoked expiry, budget exhausted | dead_letter | ATTEMPTS_EXHAUSTED, retry null, finalized DB time | false |
| Invoked exception/timeout/interruption/expiry | dead_letter | INVOKE_OUTCOME_UNKNOWN, retry null, finalized DB time | true |

`invoked_at` is null only for never-invoked custody.
Outcome/digest/receipt time are present only when completed. Receipt completion time is DB-owned even when
the current event's `finalized_at` is null for retryable. Replays return the
original delivery identities, times, digest and disposition, with no extra receipt.
Cancellation/crash before finalization may leave invoked custody for later
expiry recovery; it must never manufacture a successful outcome.

Commit-time mapping is closed: generation-zero pending/cancelled events have no
attempt; a claimed event matches its latest claimed/invoked custody; retryable
or terminal attempted events match their completed custody exactly. An archival
timestamp does not change that completed receipt. Earlier generations remain
immutable completed evidence. Manual reopening without new coherent custody
cannot commit, including raw SQL that the earlier persistence-only guard allowed.

Use database time for eligibility, leases and retry scheduling. The existing
event trigger forbids `claimed -> claimed`; recovery finalizes an expired claim
that was never invoked to retry/dead-letter and only then permits a new generation.
An expired or interrupted invocation has unknown effects: record
`INVOKE_OUTCOME_UNKNOWN`, dead-letter it and retain unresolved-invocation evidence.
Do not automatically invoke it again or clear its uncertainty. Only an explicit
typed retry outcome from the handler, or expiry before invocation, permits an
automatic retry. Future authorized reconciliation owns unknown-effect recovery.
Attempt exhaustion
is bounded by the existing integer storage range and configured retry budget.
Completed-attempt replay compares the exact stored outcome and returns the
original receipt, even after a successor generation starts; it cannot mutate the
successor. Concurrent finalizers may re-prepare once with the winner's stored
digest under fresh authority. Substituted facts/outcomes fail closed.

Bounded options belong to one strict delivery-options value supplied by
composition, not a new environment or configuration framework. Handler failures
and timeouts become closed sanitized outcome codes, never raw exceptions,
provider responses, payloads or credentials. A deadline is enforced independently
of cooperative handler cancellation. Timed-out calls may still run physically;
retain their task until it ends and consume its exception, but never accept a late
result or retry unknown effects. Cancellation/crash leaves durable
recoverable custody rather than claiming successful handler completion.

Registry entries use exact event type/version and a typed handler. No dynamic
plugins, default handler or feature inference from event names. Registry
metadata is not authority. Production registrations stay empty until concrete
feature integrations supply and prove their own AUTH boundary. Unknown or absent
registrations remain unclaimed and counted as unsupported; they are neither
acknowledged nor silently excluded from observation.

## Drain and recovery limits

Expose one same-session, project-scoped, nonlocking SQL statement observing all relevant
events and custody, including unsupported event types and future retry times.
Pending/claimed/retryable are disjoint event-state counts, including future
eligibility and expired leases. Invoked counts invocation custody not completed
and overlaps claimed; unresolved counts completed unknown invocation custody and
does not overlap invoked. Unsupported counts nonterminal events without an exact
registry entry and overlaps their event-state counts. Report dead-letter events
separately. Do not sum overlapping counts or expose a readiness boolean. A single
statement binds these facts to one READ COMMITTED snapshot; multiple separate
queries are not equivalent.
An expired invocation may still be physically running; recovery cannot certify
its termination. Preserve that uncertainty rather than returning false zero.
Database/observation failure raises a bounded failure, never an empty result.
The observation is a snapshot, not authority or a substitute for the consuming
lifecycle owner's fence and feature obligation evidence.

## Acceptance criteria

1. Real PostgreSQL append/claim transaction rollback preserves existing append
   behavior; denied, mismatched or changed AUTH facts create no delivery writes.
2. Independent sessions prove committed visibility, one winner per generation,
   exact project/event/payload/owner/lease binding and stale-worker fencing.
3. A handler can acquire an independent event row lock during invocation, proving
   the dispatcher released locks. Redelivery cannot invoke a generation twice.
4. Crash before invoke, after invoke and around finalize commit has explicit
   recovery evidence. Expiry uses legal transitions, increments generation once
   and never acknowledges unknown work. Retry/backoff and exhaustion are bounded.
5. Same-outcome finalize replay returns original facts without duplicate writes;
   differing outcomes or claim substitutions fail. Direct SQL attempts to alter
   immutable custody or commit inconsistent event/custody state are rejected.
6. Drain counts include locked/unregistered/future/expired work and unresolved
   invocations; tenant substitution and query failure cannot yield false zero.
7. No live dispatcher/feature handler/authority surface is added. Existing
   fixed-service admission still denies the planned dispatcher; the hidden
   mechanics use explicitly injected test authority only in labeled tests.
8. Replace the obsolete no-dispatch-anywhere test with append-only transaction
   ownership plus no broker/public/live composition assertions. Retain existing
   immutable-envelope, replay, SQL transition, cancellation and archival protections.
   Replace the now-obsolete permissive dead-letter-reopen assertion with rejection
   and preservation; retain its generation/error-code protection using reachable
   typed retry custody. No production caller currently uses that reopening path.
9. Run focused tests, real PostgreSQL proof, meaningful mutation probes for
   generation/outcome binding and committed-only validation, structural/module
   boundaries, exact lane selection, docs/links/stale wording and final hosted
   CI. Changed subsystem coverage >=90%; preserve global coverage and all gates.

## Evidence

The implemented proof map uses real PostgreSQL for delivery, migration and
recovery, and explicitly synthetic preparation ports for unavailable AUTH.
Current command results and review freshness belong in the PR, not this record.

- `tests/outbox/test_delivery_postgresql.py::test_claim_race_commits_one_generation`:
  two independent sessions, one committed winner, loser consumes no authority.
- `test_stale_eligible_generation_rejects_before_consumption`: pause a proposal,
  advance another claim through safe retry until eligible, then resume the stale
  proposal. Removing only the refreshed-generation comparison must fail this
  proof; the simpler simultaneous claim race does not isolate that guard.
- `test_claim_lease_expiring_behind_lock_consumes_no_authority`: hold the event
  row in another transaction beyond the proposed lease, then release it. No
  consume/write occurs; removing locked clock revalidation must fail the proof.
- `test_claim_validator_requires_committed_invocation`: false before claim commit,
  false after claim commit, false while invocation is uncommitted, true only
  after exact INVOKE custody commits, then false after finalization. Independent
  project/event/payload/owner/generation/lease substitutions fail. A validator
  checking only claimed event state or reading its writer's transaction must
  fail this test. Handler validation is not the broader internal state read
  used to prepare dispatch phases.
- `test_each_phase_denies_mismatch_and_reused_authority`: parameterize all three
  phases with valid control, denial, wrong action/permission and phase/fact
  mismatch. Require zero phase writes; mismatched facts consume no authority.
  Reusing CLAIM preparation at INVOKE must fail the intended assertion.
- `tests/outbox/test_recovery_postgresql.py::test_completed_generation_replays_without_mutating_successor`:
  finalize gen1, commit gen2, then replay the exact historical receipt under fresh
  authority without changing gen2. Old invocation and substituted receipts reject.
- `test_concurrent_same_outcome_finalizers_replay_winner`: independently prepared
  outcomes race; the loser reauthorizes the stored digest once, preserving the
  original receipt instead of writing a second outcome.
- `test_unknown_registration_stays_unclaimed_and_counted`: exact pending row
  remains unchanged with no authority, custody or handler calls. A default
  handler or automatic terminal outcome mutation must fail this proof.
- `test_invoke_releases_locks_and_runs_generation_once`: handler takes the event
  lock using another connection; concurrent duplicate invocation runs once.
- `tests/outbox/test_recovery_postgresql.py::test_crash_before_invoke_recovers`:
  claim commit then process loss; expiry is retryable without invented invocation.
- `test_crash_after_invoke_commit_before_handler_entry_is_unknown`: invocation
  persisted, zero handler calls; expiry is unknown/dead-letter, not ack or retry.
- `test_crash_after_handler_before_finalize_is_unknown`: handler ran, finalize
  absent; expiry preserves unknown evidence and cannot re-invoke automatically.
- `test_running_handler_expiry_preserves_unknown_and_late_replay` and
  `test_cancelled_invocation_leaves_custody_for_unknown_recovery`: real blocked
  handler and cancellation interleavings preserve unknown custody, truthful drain
  counts, one invocation and original receipt replay.
- `test_handler_suppressing_cancellation_cannot_ack_after_deadline`: an
  uncooperative call remains running when UNKNOWN commits; restoring the
  cooperative-only timeout must fail the proof.
- `test_invocation_observation_uses_one_stable_database_instant`: one nonlocking
  statement binds both lease eligibility and returned time; splitting into
  volatile clock reads fails the structural proof alongside real SQL bounds.
- `test_finalize_commit_and_exact_replay`: before-commit fault rolls back both
  writes; after-commit response loss replays the original receipt; substituted
  outcome/claim facts reject. Assert all original delivery identities, timestamps and
  digests and unchanged row count; mutate each digest-bound field independently.
  Removing outcome comparison must fail the test.
- `test_retry_backoff_and_exhaustion`: explicit retry plus a valid successful
  control; verify database times, bounds and exhaustion without changing limits.
- `tests/outbox/test_custody_postgresql.py::test_projection_and_receipt_commit_together`:
  direct SQL separately mutates each side with otherwise valid facts, requires
  rejection and rollback; paired valid write commits. Disable each deferred
  guard separately and require its corresponding negative to fail.
- `test_expired_invoked_sql_outcome_rejected`: paired direct-SQL ACK, RETRY and
  REJECT after expiry reject and roll back; UNKNOWN recovery remains valid.
  Removing the outcome-expiry guard must fail these negatives.
- `test_sql_completion_time_and_retry_bounds` and `test_sql_claim_lease_is_bounded`:
  paired writes isolate future completion, retry delay and lease limits.
- `test_completed_custody_is_immutable`: field substitutions, deletion and
  truncation each reject at their intended guard, with valid receipt controls.
- `tests/outbox/test_migration.py::test_pending_events_preserved_without_fabricated_attempts`
  and `test_attempted_events_refuse_unprovable_migration`: real 0026 -> 0027 with
  retained pending and each reachable attempted state, comparing rows, schema
  and revision. Refusal must not be an unrelated setup/downgrade failure.
- `tests/outbox/test_drain_postgresql.py::test_drain_uses_one_snapshot_and_exact_project`:
  interleaved foreign-project decoys, committed rows locked by another connection,
  future retries, unsupported events and unknown invocations. One nonblocking
  SQL statement; removing the project predicate or splitting the snapshot must fail.
- `test_drain_failure_never_returns_zero`: a database error raises bounded failure.
- `tests/outbox/test_contracts.py::test_append_transaction_and_hidden_delivery_boundaries`:
  append remains flush-only; no broker, route, production handler or live AUTH
  adapter is installed. Retain real planned-action denial from AUTH-OUTBOX-01.

Run the new modules and retained `test_outbox.py` through the canonical isolated
runner, not a deselected broad suite. Register every module exactly once in the
existing lanes, with migration tests in the schema lane. Broker transport is not
part of this hidden owner boundary and must be proven when worker wiring is added.

## Risk and review routing

L1: bounded shared delivery, concurrency, authorization consumption and retained
database evidence. Required focused tracks: security/architecture/reuse, QA/test
delta, CI integrity, documentation and operational recovery. Plan review precedes
implementation; final review uses a clean frozen target and shared verification.
This cohesive change exceeds the default 500-line L1 guideline because the one
operation needs SQL guards, migration preservation, concurrency/crash proof and
replacement of affected persistence-only tests together. Splitting the schema
from its sole writer/proof would leave an unusable boundary. Public activation,
feature handlers and broker wiring remain separate.
SQL outcome validation reuses the existing pure
`project_guide_projection_canonical_json(jsonb)` serializer. This is an explicit
shared dependency: later PROJECTS cleanup must trace the OUTBOX consumer before
renaming or removing it. No second serializer or compatibility wrapper is added.
The custody record is justified by erased lease facts and missing exact outcomes;
do not add additional frameworks or tables for hypothetical future integrations.

Human focus: committed claims are facts, not borrowed feature authority; crash
recovery cannot produce a false completion; manual operations and production
dispatch stay unavailable. Next boundary remains AUTH-OUTBOX-02 exact activation,
then dependency-gated assignment invalidation and ARCH-03C integration.
