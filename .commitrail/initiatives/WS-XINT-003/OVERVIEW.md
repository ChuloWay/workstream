# WS-XINT-003 — REV/AUTH end-to-end integration

Current upstream dependency: [ARCH-04E canonical `allow_review`](../WS-ARCH-001/planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md).
This is the pre-review admission fact, not REV activation or implementation
of review/revision behavior. The downstream owner contracts remain separate.

- Disposition: Planned
- Completed boundary: review authorization readiness through 02D.
- Intent: bind AUTH authority to REV-owned facts and lifecycle guards without
  local role logic or circular repository access.
- Next usable boundary: later activation waves resume only against exact merged
  REV behavior.
- Governing sources: `docs/spec_authorization_service.md`,
  `docs/spec_review_lifecycle.md`,
  `docs/engineering/review_authorization_action_custody.md`, code, and tests.
- Preserve: unavailable-by-default actions, exact service principals, fresh
  authority inside transactions, and feature-owned row locks/final facts.

The existing XINT-003-08B `review.lifecycle.activation.manage` slice may precede
human runtime for the [scoped shared-acceptance manifest](../../../docs/spec_review_lifecycle.md#scoped-activation-before-human-review-runtime).
It requires the early REV-12A foundation, real enabled-writer observation/drain
proof and exact same-action AUTH activation. It exposes only the existing
Operator control command for that manifest; it does not activate other 08B
actions, reviewer endpoints or a second controller. Later human integration
extends the same approved manifest and action under its own proof.

## Preserved history

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).
These verbatim records preserve completed work and original proposals; where
pending sequencing conflicts, the current dependency contract above governs.
