# WS-REV-001 — Review and revision lifecycle

Current upstream dependency: [ARCH-04E canonical `allow_review`](../WS-ARCH-001/planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md).
This is the pre-review admission fact, not REV activation or implementation
of review/revision behavior. The downstream owner contracts remain separate.

- Disposition: Planned
- Completed boundary: queue admission and ReviewLease persistence through 03A2.
- Intent: ensure the authorized reviewer evaluates the exact verified artifact
  under the locked policy version and produces attributable outcomes.
- Next usable boundary: prepare shared acceptance/source and existing fence
  foundations under the canonical order; human hidden behavior may continue
  independently behind exact AUTH, ART and CON prerequisites.
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
contribution. No mode enum or additional policy is needed. The
[canonical shared acceptance contract](../../../docs/spec_review_lifecycle.md#finalacceptance)
defines both triggers, exclusive provenance, constraints, authority and one
atomic operation. Do not build a separate workflow engine.

REV owns shared final-acceptance semantics for both paths. The automated path
must have explicit AUTH service authority and exact TASK/CHECKERS evidence,
without a fabricated Review, ReviewLease, human actor, or reviewer contribution.
CON validates that acceptance provenance using the same atomic
submitter-contribution and applicable compensation participant. These changes
are planned runtime work, not delivered behavior.
The human branch below continues to use `allow_review`; it is not an automatic
acceptance signal.

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
3. After TASK's early 04E1A source schema/public port, implement the REV-04B
   shared source/FinalAcceptance persistence foundation,
   then CON-03C/CON-07 persistence and submitter participation. This foundation
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
