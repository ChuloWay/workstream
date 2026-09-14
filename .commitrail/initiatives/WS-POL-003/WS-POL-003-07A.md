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
  or public phase facade in this prerequisite. POL-07 retains that next boundary.
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
   Prove both consumes against actual AUTH idempotency/audit semantics. Retain TASK then PROJECT lock
   ordering before attempt-row locks. Do not hold an attempt lock across checks.
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
POL-07 work.
