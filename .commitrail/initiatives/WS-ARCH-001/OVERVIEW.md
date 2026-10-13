# WS-ARCH-001 — Modular monolith boundaries

- Disposition: Planned
- Intent: keep product modules behind explicit ports, exact owner authority and
  one canonical transaction for each business outcome.
- Delivered first-layer boundary: public admission-backed ZIP preparation and
  TASK-owned atomic Submission/dispatch through
  [ARCH-02I-B](WS-ARCH-001-02IB.md); [ARCH-04F1](WS-ARCH-001-04F1.md), [04F2](WS-ARCH-001-04F2.md),
  [04F3](WS-ARCH-001-04F3.md) and [04F4](WS-ARCH-001-04F4.md) supply verified failure
  evidence, exact checker remediation, replacement intake and Operator retry;
  [ARCH-04E2-B](WS-ARCH-001-04E2B.md) authorized true/false outcomes; and
  [PILOT-04](../../changes/pilot04-external-checker-runtime.md) selected production
  request/completion registration with digest-pinned external PRE/POST images.
  The two executable catalogues were removed. A successful true result moves
  TASK to `review_pending` without a REV queue; eligible false completion uses
  shared FinalAcceptance/TASK/CON participation, with no Review or reviewer
  contribution. [ARCH-02I-B](WS-ARCH-001-02IB.md) exposes public initial and
  checker-remediation Submission entry. [ARCH-04E3-B](WS-ARCH-001-04E3B.md)
  admits complete false-policy guides with supported approved checks and
  corrects REV's selected-production manifest. New false/pass effects require
  an Operator-authorized LIVE REV generation. A known pre-effect non-live
  refusal retries within the existing OUTBOX budget; exhaustion dead-letters
  without automatic reopen. The default-true handoff remains independent of REV.
- Local proof: the public API and durable-worker drill passed at `d5703d9c6`
  through both policy branches, restart, revocation and exact contribution
  evidence under scripted approved-guide preconditions and local Flow-compatible
  auth. Next usable boundary: reproduce and operate that path with intended
  hosted identity and infrastructure. See the [current delivery
  plan](planning/PLAN.md#first-complete-contributor-milestone) and [change
  map](planning/CHUNK_MAP.md).
- Later scope: live human review/revision, payment fulfillment, external
  integrations and a manager-visible setup-fault hold. The current CHECKERS
  classifier emits `allow_review`, `needs_revision` or `not_evaluated`; selected
  completion rejects `task_setup_blocked`. A future setup-fault path must retain
  the Submission and locked rules without contributor penalty, but it is not a
  prerequisite to the proven local first-layer drill.
- Governing sources: `docs/architecture_lockdown.md`, accepted ADRs, current
  code, migrations, tests and the [capability ledger](../../../docs/roadmap_status.md).
- Preserve: exact AUTH receipts, locked lineage, immutable evidence, atomic
  accepted effects, no duplicate authorization or factory path.

The [pre-cutover status](pre-cutover/STATUS.md), [change map](pre-cutover/CHUNK_MAP.md)
and [chunk contracts](pre-cutover/chunks/) preserve their original planning and
review history; they do not supersede the current plan. Completed change records
retain their own delivery scope. This overview states the present integrated
boundary and next dependency only.
