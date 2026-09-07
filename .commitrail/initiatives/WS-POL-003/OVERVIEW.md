# WS-POL-003 — Unified project-guide compilation

Current change record: [POL-04A2 hidden finalization](WS-POL-003-04A2.md).

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: hidden execution, deterministic projections, and immutable setup finalization.
- Intent: compile one locked guide and its policies into authoritative,
  versioned project behavior without circular subsystem authority.
- Next usable boundary: AUTH-12B2 exact finalization authority, followed by
  POL-04B live cutover.
- Governing sources: project-guide specifications, authorization and
  contribution-policy specifications, code, migrations, and tests.
- Preserve: deterministic compilation, explicit ownership, atomic persistence,
  no hidden activation, and no concrete adapter leakage.

## Delivered

- Strict unified catalogue, one guide-agent adapter, authorized immutable
  compilation persistence/recovery, hidden execution, and deterministic
  sufficiency/artifact-policy projections are complete through 04A3.
- POL-04A2 atomically binds those exact projections to an immutable finalization
  receipt and closes the current setup generation. Production authority remains
  unavailable; HTTP and Celery have no finalization composition.

## Remaining v0.1 sequence

1. AUTH-12B2 exact finalization authority, then POL-04B live explicit-manager
   cutover with every legacy inference call removed from reachability.
2. POL-05/06 approval and post-submit manifests with AUTH-12F4/12G. Immutable
   finalized setup rows require separately reviewed downstream custody before
   live post-submit integration.
3. POL-07 canonical checker port, AUTH-12H, and later POL-08 cleanup after the
   canonical ARCH-04E manifest.
