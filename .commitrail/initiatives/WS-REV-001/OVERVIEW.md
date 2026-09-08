# WS-REV-001 — Review and revision lifecycle

Current upstream dependency: [ARCH-04E canonical `allow_review`](../WS-ARCH-001/planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md).
This is the pre-review admission fact, not REV activation or implementation
of review/revision behavior. The downstream owner contracts remain separate.

- Disposition: Planned
- Completed boundary: queue admission and ReviewLease persistence through 03A2.
- Intent: ensure the authorized reviewer evaluates the exact verified artifact
  under the locked policy version and produces attributable outcomes.
- Next usable boundary: continue hidden behavior behind exact AUTH, ART, and CON
  prerequisites; live claim requires the canonical review action gate.
- Governing sources: `docs/spec_review_lifecycle.md`,
  `docs/engineering/review_authorization_action_custody.md`, code, migrations,
  and tests.
- Preserve: only `accept`, `needs_revision`, and `reject`; immutable attempt
  policy lineage; separation of duties; and atomic final acceptance effects.

## Delivered

- Hidden review queue/admission persistence, ReviewLease, and preference
  persistence are merged through 03A2. REV policy identities and mutations and
  the fail-closed AUTH PREP/read handoff are available.
- No live claim or canonical review decision is implied by this foundation.

## Remaining v0.1 sequence

### Acceptance-mode amendment — Planned

Use `human_review_required: bool = true` in the existing locked guide-bound
ReviewPolicy: after required post-submit checks pass, true requires human
review and false proceeds to authorized FinalAcceptance without reviewer
contribution. No mode enum or additional policy is needed. Reconcile the existing
human-only contracts before implementing final acceptance; do not build a
separate workflow engine. The detailed direction and outstanding consumer
contracts are in the [current reconciliation record](../../changes/pre-review-plan-reconciliation.md#accepted-direction-project-controlled-acceptance-mode).

REV owns shared final-acceptance semantics for both paths. The automated path
must have explicit AUTH service authority and exact TASK/CHECKERS evidence,
without a fabricated Review, ReviewLease, human actor, or reviewer contribution.
CON must support that distinct acceptance provenance using the same atomic
submitter-contribution and applicable compensation participant. These changes
are planned, not supported by the current human-only persistence contract.
The human branch below continues to use `allow_review`; it is not an automatic
acceptance signal. This amendment must be reconciled before treating the
remaining sequence as implementation-ready.

The [versioned policy setting](../../changes/pre-review-plan-reconciliation.md#delivered-policy-setting-implementation)
is available for draft configuration. Extend shared acceptance persistence and
the CON participant for both sources before enabling false. The automated branch must not depend on
live human queues, ReviewLeases or decision endpoints. Human lifecycle work
remains required for v0.1, but need not delay the first automated end-to-end
proof. No adjudication setting or behavior is included.

1. `03B`: normalized reviewer packet manifest after ART publishes the exact
   packet-membership contract.
2. Continue hidden claim/revision behavior against canonical `allow_review`,
   copying the Submission policy version without a current-policy lookup.
3. Implement Review and FinalAcceptance persistence plus the CON atomic
   participant; every final decision creates the reviewer record, and accept
   additionally creates the submitter record.
4. Activate public claim/decision behavior only after exact AUTH/ART/CON gates.

## Preserved history

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).
These verbatim records preserve completed work and original proposals; where
pending sequencing conflicts, the current dependency contract above governs.
