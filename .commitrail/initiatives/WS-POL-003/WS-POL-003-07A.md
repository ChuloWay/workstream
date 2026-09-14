# WS-POL-003-07A — ART-owned pre-submission attempt recovery

- Initiative: WS-POL-003
- Durable disposition: Complete
- Intended merge outcome: reserve an exact pre-submission execution attempt
  before invoking checks, and recover its completed canonical ART evidence
  without another checker invocation or upload capability.

## Intent

This is the approved prerequisite identified by reviewing the
[adopted POL-07 contract](planning/chunks/WS-POL-003-07-single-checker-service-port.md)
against main `d5dd94d3`.
Current ART evidence writes are idempotent only after checker execution; a
crash before evidence commit leaves no record of the invocation. A prepared
generation is process-local and cannot be reassigned to a retried upload.

## Bounded change

### Allowed

- ART models, one additive Alembic migration and its current-head startup registry, `pre_submit_evidence.py`,
  `submission_materialization.py`, `submission_admission.py`, a focused
  owner-local attempt module and corresponding typed ART contracts. The existing
  hidden preparation route translates recovery unavailability to 503, distinct
  from concealed authority denial; it remains hidden.
- Exact ART composition adjustments and affected authorization tests; no
  permission registration, relaxed authority or replacement AUTH implementation.
  Include the existing fixed materializer resource in its database audit
  vocabulary: real AUTH proof found that missing persisted allowlist entry.
- Focused real PostgreSQL/scratch tests, exact affected test/owner inventories,
  current checker/ART docs, roadmap and initiative dependency navigation.

### Not allowed

- No second checker/evidence implementation, facade cache, rewritten historical
  evidence, new provider, storage lifecycle or scratch-generation rebinding.
- No new contributor endpoint, guide activation, post-submit executor, acceptance
  or phase facade in this prerequisite. POL-07 owns the next internal facade
  boundary; public intake exposure retains its separate cutover.
- No automatic retry of an attempt whose execution outcome is uncertain.

## Proposed owner design

1. Add one ART attempt row, uniquely keyed by actor and idempotency key. Its
   immutable identity binds actor/link, project/task/assignment/predecessor,
   locked plan/guide/policies/catalogue, packet digest, archive digest/size,
   semantic_manifest_sha256,
   and storage scheme. The original execution generation is recorded separately
   and is immutable. The logical attempt UUID is
   deterministically derived from its key namespace. Request digest binds all
   logical facts; changed packet, content or lineage under the same key conflicts.
   A retry must spool and inspect bytes to confirm the same archive/manifest, but
   its new scratch generation cannot become the original execution generation.
2. Under fresh contributor and fixed materializer authority, commit the
   reservation after bounded ZIP inspection and before any checker member is
   invoked. Consume the first exact AUTH handle for inspected custody/reservation.
   The original prepared
   authorization cannot cross that commit: obtain and consume fresh authority
   in the existing materialization transaction. The existing adapter resets its
   handle after consume and can issue a fresh one; no fallback adapter is added.
   Prove both consumes against actual AUTH idempotency/audit semantics. Acquire TASK then PROJECT context, contributor AUTH, fixed-materializer AUTH
   when needed, then attempt/evidence locks in every transaction. Do not hold an attempt lock across checks.
3. Only the request that created the reservation can proceed. ART mints an opaque,
   nonserializable one-use winning claim only after its reservation commits.
   Bind it to the exact original prepared object/generation and request digest;
   consume it at `PreparedBundleMaterializationService.materialize_prepared_bundle`
   before processor construction and verify the committed reserved
   row. A failed commit cannot leave an executable claim. Final persistence
   requires the corresponding execution receipt, not an attempt UUID or boolean.
   An existing
   unresolved reservation fails closed, including crashes after checker return
   but before evidence commit. No timeout silently resets it. A genuinely new
   authorized attempt uses a new key and fresh scratch custody.
4. In the existing fresh evidence transaction, revalidate authority and locked
   lineage, persist the canonical evidence and atomically link it to the attempt
   as completed. New evidence also records its attempt ID/request digest and the packet digest
   computed from the winning claim’s original request. The database compares
   that independent evidence field to the reserved packet identity and
   includes that binding in its operation identity. Database guards reject
   rewritten request facts, illegal state transitions, duplicate evidence links
   and cross-resource or same-resource/different-packet completion. Retained
   evidence receives no invented attempt binding.
5. Completed exact replay revalidates contributor and fixed-service authority
   using the stored original materializer facts in a fresh transaction, including
   a fresh AUTH prepare/consume without scratch/member access. It resolves linked evidence
   before any member invocation. Return the canonical reference/result with no
   freshly minted `PreSubmitPassCapability`. Existing durable-put recovery may
   reuse its own receipt; missing durable continuation returns explicit
   infrastructure unavailability and requires a new authorized attempt, never
   re-execution under the old key. Close/discard any retry scratch. The response
   retains the original evidence/generation; no field is rewritten to the retry
   generation. Recovery is an evidence read, not proof that new custody passed.
6. Persist bounded member metadata and definition order, currently included in
   the result manifest hash but omitted from result rows. Row ordinal is not
   definition order. Add nullable metadata/order columns without
   rewriting retained evidence. New writes always include validated metadata;
   NULL retained metadata or definition order must fail reconstruction; neither
   can become a fabricated default. Reconstruct and
   verify the complete manifest digest for new attempt replay. No reservation
   is invented for previously retained evidence.

The attempt row records invocation custody and the evidence foreign key; it
does not contain a second result body or replace ART's immutable evidence tables.
The superseded after-execution replay lookup is removed from the evidence writer;
completed recovery has one path through the attempt owner before execution.
The minimal lifecycle is reserved then completed. A still-reserved row denotes
an unavailable/uncertain attempt to later callers, not contributor failure.

## Acceptance criteria

- Durable reservation precedes the real CHECKER processor; completed exact
  replay returns the same evidence ID/digest and invokes no members.
- Kill/fail after actual member completion but before final evidence commit:
  the reservation survives, evidence does not, and same-key recovery invokes
  no further members. This is the discriminating counterexample to the old flow.
- Independent concurrent PostgreSQL sessions with the same key permit one
  invocation. Conflicting key reuse, phase/resource/generation substitution,
  revoked contributor/service authority and stale policy context deny.
- Completion and evidence rows commit or roll back together; direct SQL cannot
  cross-link evidence or mutate immutable attempt identity.
- Replay never mints a new upload capability; different scratch bytes/generation
  do not inherit old passing evidence. Byte-identical reupload may recover the
  original completed result only after fresh authority; it cannot execute with
  the original claim or produce a new pass capability. Retained rows remain unchanged.
- Metadata reconstruction verifies the exact result digest; missing/corrupt
  metadata fails closed rather than filling defaults.
- `test_completed_replay_after_original_scratch_closes` must use real scratch:
  close the original preparation, prepare identical bytes under the same key
  with a different generation, and recover the original evidence with zero
  additional checker calls and no pass capability. Retry-byte verification
  uses the retry's own inspected custody; original generation is only returned
  evidence and a fresh authority selector, never a live retry handle.
- Real scratch/member execution and PostgreSQL proof are required. Fakes only
  isolate broker/provider publication; no live transport claim is made.

## Risk and review routing

- Risk: L1, bounded ART persistence/authority/recovery change.
- Required reviewers: plan/architecture, security, QA/test delta, reuse,
  documentation/product operations and CI integrity for migration/test custody.
- Human focus: crash semantics, fresh authority across commits, no cross-generation
  capability reuse and retention of immutable evidence.
- Planned verification: focused ART PostgreSQL/scratch suites plus new crash,
  race, replay and direct-SQL cases; migration round trip on isolated data;
  module/AUTH/CI inventories; lint/docs checks; full hosted suite and at least
  90% changed-subsystem coverage. Broker/provider transport is not part of this change.

## Evidence

The focused execution proof exercises real PostgreSQL and canonical scratch,
with a processor counter around the actual CHECKER implementation. It is
separate from controlled doubles used for command/error routing.

| Required behavior | Regression proof |
| --- | --- |
| Original scratch closes; exact retry does not execute or mint a pass capability | `test_completed_replay_after_original_scratch_closes` |
| Checker returns, then evidence commit fails; same key never reruns | `test_crash_after_member_before_evidence_commit_cannot_rerun` |
| Independent sessions allow one invocation | `test_independent_sessions_same_key_invoke_members_once` |
| Different contributors/tasks/keys in one project cannot deadlock reservation against execution | `test_same_project_reservation_and_execution_complete_without_auth_project_deadlock` with real AUTH and an observed PostgreSQL lock wait |
| Reservation rollback cannot issue a claim | `test_uncommitted_reservation_never_issues_a_claim` |
| Completion failure rolls back evidence and retains reservation | `test_completion_failure_rolls_back_evidence_and_keeps_attempt_reserved` |
| Immutable attempt and same-resource/different-packet evidence binding | Direct SQL cases in `test_pre_submit_attempt_recovery.py` |
| Current contributor and fixed-service authority after commit and on replay | Integrated ART/real AUTH replay in `test_pre_submit_attempt_authority_integration.py`, contributor revocation in `test_pre_submit_attempt_recovery.py`, and kernel cases in `authorization/test_pre_submit_attempt_authority.py` |
| Missing/foreign/spent claim cannot build a processor; incomplete result cannot recover | `test_pre_submit_attempt_contracts.py` |
| Retained evidence stays unchanged; downgrade cannot discard a reservation | `test_pre_submit_attempt_migration.py` |
| Checker rejection, corrupt/unresolved recovery and concealed authority denial remain distinct | `test_submission_bundle_preparation_recovery.py` |

The focused run covers the new attempt owner and affected evidence/materializer
above 90 percent each. Exact hosted results and reviewer freshness belong in the
PR. The schema fingerprint was reconciled against the actual main schema object
inventory: only the attempt table and guards, result reconstruction fields,
evidence binding fields, and exact existing materializer audit resource
vocabulary changed. The existing oversized test file/function both shrink;
no structural exception or limit was added. No retained data was removed.

## Review findings and reconciliation

One-root-transaction claim/execution/evidence was rejected: rollback after a
completed invocation would erase the claim and allow the same attempt to run
again. AUTH receipts and artifact put receipts prove different operations and
cannot substitute for pre-submit invocation custody.

The user approved the ART prerequisite; the original POL-07 no-ART-change
restriction is superseded only for this bounded repair. The facade and obsolete
precheck removal remain the following POL-07 implementation boundary. CP06/CP07
and AUTH-12H activation remain downstream. Focused architecture/reuse and
security plan review passed after reconciling the winning claim, fresh authority,
original-generation replay and exact metadata reconstruction requirements.

Implementation review exposed a misleading database test: it supplied a foreign
request digest, so an earlier link guard masked the missing packet comparison.
The corrected regression supplies the new attempt’s valid digest and complete
copied results, then asserts the specific independently stored packet mismatch
and transaction rollback. Replay authorization is now exercised through ART and
real AUTH together, including both retry and original-generation audit facts;
removing original-generation authorization fails the denial assertion.

Recovery reports corrupt or unavailable evidence as infrastructure unavailability,
not a contributor checker failure. Only a still-ready durable admission returns
an admission ID; stale or consumed admissions retain their actual state without
usable custody. Current documentation assigns obsolete JSON precheck removal to
POL-07 and broader Submission call-path migration to ARCH-02I. The hidden route
currently returns a checker-failure code; structured public feedback remains
pending the canonical public intake cutover. ART constructs the bounded failure-audit projection, but publishing
it as a TASK audit event remains pending; current documentation distinguishes
that implementation gap from the target contract.


### Cross-request lock-order correction

Human review identified an execution/reservation cycle missed by the same-task
concurrency fixture: one request could hold the shared materializer principal
while waiting for project context, and another could hold project context while
waiting for that principal. A database deadlock abort after reservation commit
would leave the key unresolved. The correction stays in the existing ART command
and workflow, with no retry reset, AUTH relaxation, migration or second lock owner.

The implemented order is TASK context, PROJECT policy context, contributor AUTH,
fixed-materializer AUTH, then attempt/evidence custody. It applies to the initial
context check, ZIP inspection and reservation transaction, execution transaction and
completion transaction; reacquiring an already held lock cannot replace the
required initial order. The reservation row is written after ZIP inspection.
Fixed-service authorization must still precede ZIP
inspection and checker construction. Both production materializer-preparation
callers and the real-AUTH test helper follow this order.

The regression uses real PostgreSQL and production AUTH with two contributors, different
tasks/assignments and distinct idempotency keys in one project. It coordinates a
reservation with another request's committed-attempt execution using explicit
barriers and observed database waits, not timing guesses. Both attempts must
complete with one checker invocation each and completed canonical evidence;
the same regression fails against the old implementation with PostgreSQL
`40P01` (`DeadlockDetectedError`). Same-key concurrency, replay, revocation and
rollback tests are retained. Required repair reviews are architecture/
reuse, security, QA/test-delta, CI integrity and affected docs/product operations.
The actual command reservation and both evidence transactions run in the
regression; its provider boundary stops only after evidence commits. The
superseded test requiring contributor AUTH before context locks is replaced
with context-first denial proof: denied authority still prevents fixed-service
consume and attempt reservation. Initial contributor preflight remains before
context or byte access.

### AUTH role issuance lock-order correction plan

Re-review source-traced a second cycle: ART holds PROJECT while requesting the
contributor profile; project-role issuance holds that profile while requesting
PROJECT. The previous ART/ART regression does not prove this AUTH/ART case.
Moving contributor authority ahead of TASK would conflict with existing TASK
commands, which lock TASK/assignment before contributor authority.

The required common order is TASK/assignment, contributor profile and identity
link, PROJECT policy context, submitter role grant, fixed-materializer AUTH, then
attempt/evidence. Full contributor revalidation cannot move before PROJECT:
role revocation locks PROJECT before the exact grant. Split the existing ART
context acquisition at TASK/PROJECT; expose a transaction-bound actor-only lock
on the existing authorization port, shared with initial preflight. Full project
authorization remains after PROJECT. No alternate authorization path is added.

Denied role issuance must also preserve the order. The AUTH principal selector
currently locks a service target before PROJECT even though services cannot
receive project roles. Filter the target row by immutable human actor kind
before FOR UPDATE. The existing final eligibility guard remains unchanged.
Move the existing final human eligibility lock before PROJECT as well: a
previously absent target may be provisioned after principal selection. Actor
kind is database-immutable; no unlocked mutable eligibility decision is
introduced. This narrow AUTH repository correction prevents the same cycle
through an ineligible request targeting the fixed materializer.

Allowed repair files are the existing ART command, materialization, evidence,
authorization adapter and port; AUTH repository principal selection and the existing role-issuance router lock
sequence; affected
tests/helpers and exact test-lane inventory; this record and checker architecture
wording. No kernel or role-mutation workflow replacement, permission relaxation,
schema change, retained-data deletion, or retry reset is authorized.

Required proof adds real PostgreSQL role issuance versus execution through
production AUTH: valid issuance and evidence complete, one checker invocation;
service-target issuance denies without aborting execution. The same regressions
must expose the pre-repair cycles. Retain the real ART/ART regression, and prove
TASK precedes actor locking while PROJECT precedes role-grant revalidation.
Exercise actual `AuthorizedTaskCommands.work_context` against the same actor/task
and actual `revoke_project_role_grant` against the submitter grant in PostgreSQL.
The former must expose an actor-before-TASK mutant; the latter must expose a
grant-before-PROJECT mutant. Revocation may cause fresh authority denial before
checker execution, but must not deadlock or cause another invocation. Verify
role-issuance eligibility is locked before PROJECT even when a target was absent
during the preliminary principal lookup.

Risk remains L1. Architecture/reuse and security plan review trace issue/revoke,
TASK consumers and ineligible service targets before implementation. After
focused SQL/unit verification, freeze the candidate for architecture/reuse,
security, QA/test-delta, CI integrity and affected documentation review; run
final-head hosted CI. Human review focus is the complete cross-owner lock order
and preservation of immutable invocation custody. This repair changes no
capability exposure or next roadmap dependency.
