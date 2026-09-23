# CON-02B — Hidden shared outbox delivery and recovery

- Initiative: WS-CON-001
- Durable disposition: Planned
- Intended outcome: one hidden, feature-neutral claim/invoke/finalize operation
  with committed claim custody, bounded automatic recovery and truthful drain
  facts. Production dispatch remains unavailable until AUTH-OUTBOX-02.

## Intent and current owners

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

## Scope and reconciliation

Allowed files:

- `backend/app/modules/outbox/`: independent public claim/outcome/drain contracts,
  typed static handler registry, delivery repository, custody model and hidden
  orchestration. Preserve append ownership and its public result.
- `backend/alembic/versions/0027_outbox_delivery_custody.py`, `alembic/env.py`,
  `app/db/models.py`: register and enforce the new custody records. Preserve the
  baseline and retained data; fail rather than invent unprovable claim history.
- `backend/app/adapters/outbox.py`: explicit owner composition requiring the
  AUTH preparation factory; no default, permissive adapter or runtime registry.
- Focused `backend/tests/outbox/` contracts, PostgreSQL and recovery tests;
  `tests/test_outbox.py` only the obsolete persistence-only structure assertion;
  migration graph, exact schema/reset inventory, lane/ownership registrations
  and their exact tests where the new files/table require them.
- `docs/spec_shared_outbox.md`, affected current capability/navigation and
  architecture/specification documents, and this record.

Prohibited: active AUTH evaluator/catalogue changes; human/operator authority;
feature handlers or provider calls; public routes; production Celery/beat
registration; new broker/storage provider; compatibility paths; data deletion;
baseline rewriting; gate, coverage or assertion weakening.

The old archived proposal conflated delivery with manual operational controls.
`operations.outbox.retry` is only a planned permission, without an executable
action/port. Dead-letter operator requeue, pending cancellation and delayed
archival therefore remain separate authorized operational work. Existing SQL
guards and their tests remain. Replay here means exact committed claim/outcome
redelivery, not an unauthorized manual reopening of terminal work. Actual worker
registration and broker transport belong to AUTH-OUTBOX-02 integration; this PR
must not claim live Redis delivery proof or install a worker that can bypass the
missing authority adapter.

## Delivery design

1. Discover one exact event without locking. Build proposed facts from its
   canonical project, payload digest and generation using database time.
2. In a fresh root transaction, prepare AUTH before any outbox row lock. Lock
   and refresh the exact event, recompose and compare facts, consume one matching
   allow decision, and persist claim plus custody atomically. Commit before
   returning a claim. A competing or changed candidate does not gain authority.
3. In another fresh transaction, prepare INVOKE, lock event then custody in the
   same order, verify committed exact generation/owner/lease, consume authority,
   and record invocation once. Commit and close sessions before calling the
   handler. Duplicate invocation does not run the handler again.
4. A handler receives immutable envelope/payload and claim facts, never ORM rows,
   a dispatcher authority handle or its session. Its own feature composition
   must obtain feature authority and validate the committed claim through the
   public port. The port reads an independent transaction, so an uncommitted
   claim cannot validate. Delivery is at least once across generations; feature
   effects must use immutable event identity/idempotency, not generation, to
   deduplicate. No concrete feature handler is installed here.
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
Same-generation outcome replay compares the exact stored outcome and returns
the original receipt; substituted facts/outcomes fail closed.

Bounded options belong to one strict delivery-options value supplied by
composition, not a new environment or configuration framework. Handler failures
and timeouts become closed sanitized outcome codes, never raw exceptions,
provider responses, payloads or credentials. Cancellation/crash leaves durable
recoverable custody rather than claiming successful handler completion.

Registry entries use exact event type/version and a typed handler. No dynamic
plugins, default handler or feature inference from event names. Registry
metadata is not authority. Production registrations stay empty until concrete
feature integrations supply and prove their own AUTH boundary; an absent or
unknown registration cannot silently acknowledge an event.

## Drain and recovery limits

Expose one same-session, project-scoped, nonlocking observation of all relevant
events and custody, including unsupported event types and future retry times.
Count pending, claimed, retryable, invoked and unresolved execution separately.
An expired invocation may still be physically running; recovery cannot certify
its termination. Preserve that uncertainty rather than returning false zero.
Database/observation failure raises a bounded failure, never an empty result.
The observation is a snapshot, not authority or a substitute for the consuming
lifecycle owner's fence and feature obligation evidence.

## Acceptance and verification

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
   immutable-envelope, replay, SQL transition, cancellation and archival tests.
9. Run focused tests, real PostgreSQL proof, meaningful mutation probes for
   generation/outcome binding and committed-only validation, structural/module
   boundaries, exact lane selection, docs/links/stale wording and final hosted
   CI. Changed subsystem coverage >=90%; preserve global coverage and all gates.

Named new tests and reproducible commands are finalized with the implementation;
planned tests are not claimed as executed evidence. Broker transport is not part
of this hidden owner boundary and must be proven when worker wiring is added.

## Risk and review

L1: bounded shared delivery, concurrency, authorization consumption and retained
database evidence. Required focused tracks: security/architecture/reuse, QA/test
delta, CI integrity, documentation and operational recovery. Plan review precedes
implementation; final review uses a clean frozen target and shared verification.
The custody record is justified by erased lease facts and missing exact outcomes;
do not add additional frameworks or tables for hypothetical future integrations.

Human focus: committed claims are facts, not borrowed feature authority; crash
recovery cannot produce a false completion; manual operations and production
dispatch stay unavailable. Next boundary remains AUTH-OUTBOX-02 exact activation,
then dependency-gated assignment invalidation and ARCH-03C integration.
