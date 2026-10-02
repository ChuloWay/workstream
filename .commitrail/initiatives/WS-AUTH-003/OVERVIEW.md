# WS-AUTH-003 — Authorization module-boundary recovery

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Delivered prerequisite: [ART-07A1](../WS-ART-001/WS-ART-001-07A1.md) supplies
  metadata-only packet types; REV-03B packet storage and REV-04A Review storage
  precede shared FinalAcceptance. No packet resolver or human runtime is live.

- Completed boundary: recovery foundation and [TASK/checker authorization cleanup](WS-AUTH-003-TASKCHECKER.md).
- Intent: route public authorization capability through `authorization.api`
  and remove cross-module repository/model coupling.
- Delivered dependent boundary: ARCH-04E1A route-neutral source facts and
  source-neutral accepted-effects types follow ARCH-04D2 exact service authority,
  ARCH-04C hidden execution, ARCH-04B hidden input,
  [ARCH-04B2 output custody](../WS-ARCH-001/WS-ARCH-001-04B2.md), ARCH-03D hidden
  intake and [AUTH-18 public manager activation](../WS-AUTH-001/WS-AUTH-001-18.md).
  They install no routing action, handler or runtime composition.
- Next usable boundary: continue canonical boundary recovery through REV-03B
  packet and complete REV-04A Review storage, then shared REV/CON/fence
  foundations and later ARCH-04E1B/04E2/04E3 routing.
  Submission/checker history uses canonical authority; the alternate gate lifecycle
  is removed. Continue shrinking the canonical import ledger as implementation
  reaches each remaining consumer.
- Governing sources: `docs/architecture_lockdown.md`,
  `.ci/auth-boundaries/IMPORT_LEDGER.md`, module-boundary scripts, and tests.
- Preserve: the ledger is CI debt data, not engineering authority, and may only
  shrink unless a separately reviewed architecture change authorizes growth.
