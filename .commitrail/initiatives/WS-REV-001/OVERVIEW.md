# WS-REV-001 — Review and revision lifecycle

Current upstream dependency: [ARCH-04E canonical `allow_review`](../WS-ARCH-001/planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md).
This is the pre-review admission fact, not REV activation or implementation
of review/revision behavior. The downstream owner contracts remain separate.

- Disposition: Planned
- Delivered prerequisite: [ART-07A1](../WS-ART-001/WS-ART-001-07A1.md) supplies
  metadata-only packet types. REV-03B packets and REV-04A immutable Review source storage are delivered; REV-04B shared FinalAcceptance storage is delivered; CON-03C contribution/award storage is delivered; atomic participation remains next. No packet resolver or human runtime is live.

- Completed boundary: queue admission and ReviewLease persistence through 03A2,
  plus normalized immutable packets through 03B, Review sources through 04A
  and shared FinalAcceptance source storage through 04B.
- Intent: ensure the authorized reviewer evaluates the exact verified artifact
  under the locked policy version and produces attributable outcomes.
- Delivered upstream boundary: ARCH-04E1A provides immutable route-neutral TASK
  source storage, detached source facts and the type-only accepted-effects
  Protocol. It provides no writer, reader, handler, routing authority, current
  pointer or acceptance implementation.
- Delivered storage: [REV-03B](../WS-REV-001/WS-REV-001-03B.md) freezes exact
  lease packets with normalized live guide ingests; no resolver or byte authority.
  [REV-04A](../WS-REV-001/WS-REV-001-04A.md) adds complete immutable Review, findings, resolutions and completed request storage; no decision runtime.
- Next usable boundary: CON-07 atomic participation and the existing REV-12A/CON fence foundation under the canonical
  order; human hidden behavior may continue independently behind exact AUTH,
  ART and CON prerequisites.
- Governing sources: `docs/spec_review_lifecycle.md`,
  `docs/engineering/review_authorization_action_custody.md`, code, migrations,
  and tests.
- Preserve: only `accept`, `needs_revision`, and `reject`; immutable attempt
  policy lineage; separation of duties; and atomic final acceptance effects.

## Delivered

- Hidden review queue/admission persistence, ReviewLease, and preference
  persistence are merged through 03A2. REV policy identities and mutations and
  the fail-closed AUTH PREP/read handoff are available.
- [REV-04A](WS-REV-001-04A.md) delivers immutable Review, finding, resolution and completed request storage. Submission responses remain with their future preparation owner.
- No live claim or canonical review decision is implied by this foundation.

[REV-04B](WS-REV-001-04B.md) stores exclusive Review/TASK source lineage without
AUTH receipts or a production writer. Before runtime use, harden this same table
with mandatory exact originating authority and refuse retained pre-authority rows.
Neither storage foundation grants acceptance authority.

## Remaining v0.1 sequence

### Acceptance-mode amendment — Planned

Use `human_review_required: bool = true` in the existing locked guide-bound
ReviewPolicy: after required post-submit checks pass, true requires human
review and false proceeds to authorized FinalAcceptance without reviewer
contribution. No mode enum or additional policy is needed. The
[canonical shared acceptance contract](../../../docs/spec_review_lifecycle.md#finalacceptance)
defines both triggers, exclusive provenance, constraints, authority and one
atomic operation. Do not build a separate workflow engine.

REV owns shared final-acceptance semantics for both paths. The automated path
must have explicit AUTH service authority and exact TASK/CHECKERS evidence,
without a fabricated Review, ReviewLease, human actor, or reviewer contribution.
CON validates that acceptance provenance using the same atomic
submitter-contribution and applicable compensation participant. These effects
are planned runtime work; the source storage foundations are delivered.
The human branch below continues to use `allow_review`; it is not an automatic
acceptance signal.

The [versioned policy setting](../../changes/pre-review-plan-reconciliation.md#delivered-policy-setting-implementation)
is available for draft configuration. Add mandatory shared acceptance authority custody and
the CON participant for both sources before enabling false. The automated branch must not depend on
live human queues, ReviewLeases or decision endpoints. Human lifecycle work
remains required for v0.1, but need not delay the first automated end-to-end
proof. No adjudication setting or behavior is included.

1. `03B` is complete: normalized reviewer packet persistence consumes the delivered
   [ART-07A1 exact membership contract](../WS-ART-001/WS-ART-001-07A1.md).
   REV-04A Review-source storage is also complete; neither step activates human review.
2. Continue hidden claim/revision behavior against canonical `allow_review`,
   copying the Submission policy version without a current-policy lookup.
3. TASK's early 04E1A source schema/detached facts and source-neutral accepted-
   effects types are delivered. After delivered REV-03B and REV-04A storage, REV-04B shared FinalAcceptance storage is also delivered. Continue CON-07 atomic submitter participation. This foundation
   can precede human runtime: ARCH-04E uses it for false/pass acceptance without
   live queues, leases or decisions. Pull the existing REV-12A/CON shared
   obligation-fence foundation forward before either trigger; later drain and
   operator work extends the same controller, not another fence.
   Human decision composition later adds Review/reviewer participation and
   invokes that same acceptance sequence on accept, not a second implementation.
4. Activate public claim/decision behavior only after exact AUTH/ART/CON gates.

## Preserved history

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).
These verbatim records preserve completed work and original proposals; where
pending sequencing conflicts, the current dependency contract above governs.
