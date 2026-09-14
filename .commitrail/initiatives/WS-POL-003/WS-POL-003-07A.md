# WS-POL-003-07A — ART-owned pre-submission attempt recovery

- Initiative: WS-POL-003
- Durable disposition: Planned
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

- ART models, one additive Alembic migration, `pre_submit_evidence.py`,
  `submission_materialization.py`, `submission_admission.py`, a focused
  owner-local attempt module and corresponding typed ART contracts.
- Exact ART composition adjustments and affected authorization tests; no
  permission registration, relaxed authority or replacement AUTH implementation.
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
   storage scheme and exact prepared generation. The logical attempt UUID is
   deterministically derived from its key namespace. Request digest binds all
   facts; a changed generation or other fact under the same key is a conflict.
2. Under fresh contributor and fixed materializer authority, commit the
   reservation before any checker member is invoked. The original prepared
   authorization cannot cross that commit: obtain and consume fresh authority
   in the existing materialization transaction. Retain TASK then PROJECT lock
   ordering before attempt-row locks. Do not hold an attempt lock across checks.
3. Only the request that created the reservation can proceed. An existing
   unresolved reservation fails closed, including crashes after checker return
   but before evidence commit. No timeout silently resets it. A genuinely new
   authorized attempt uses a new key and fresh scratch custody.
4. In the existing fresh evidence transaction, revalidate authority and locked
   lineage, persist the canonical evidence and atomically link it to the attempt
   as completed. Database guards reject rewritten request facts, illegal state
   transitions, duplicate evidence links and cross-resource completion.
5. Completed exact replay revalidates authority and resolves that linked evidence
   before any member invocation. Return the canonical reference/result with no
   freshly minted `PreSubmitPassCapability`. Existing durable-put recovery may
   reuse its own receipt; missing durable continuation never licenses rebinding
   old evidence to another generation.
6. Persist the bounded member metadata currently included in the result manifest
   hash but omitted from result rows. Add a nullable metadata column without
   rewriting retained evidence. New writes always include validated metadata;
   NULL retained values cannot become an empty fabricated value. Reconstruct and
   verify the complete manifest digest for new attempt replay. No reservation
   is invented for previously retained evidence.

The attempt row records invocation custody and the evidence foreign key; it
does not contain a second result body or replace ART's immutable evidence tables.
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
  do not inherit old passing evidence. Retained rows remain unchanged.
- Metadata reconstruction verifies the exact result digest; missing/corrupt
  metadata fails closed rather than filling defaults.
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
  90% changed-subsystem coverage. No runtime evidence is claimed yet.

## Evidence

Read-only owner inspection and independent architecture/reuse review identified
the after-execution replay lookup and crash window. This establishes plan
feasibility constraints, not runtime proof. Implementation tests and exact-head
review results remain to be produced by this bounded change.

## Review findings and reconciliation

One-root-transaction claim/execution/evidence was rejected: rollback after a
completed invocation would erase the claim and allow the same attempt to run
again. AUTH receipts and artifact put receipts prove different operations and
cannot substitute for pre-submit invocation custody.

The user approved the ART prerequisite; the original POL-07 no-ART-change
restriction is superseded only for this bounded repair. The facade and obsolete
precheck removal remain the following POL-07 implementation boundary. CP06/CP07
and AUTH-12H activation remain downstream. No product implementation begins until
this transaction/authority design passes focused plan review.
