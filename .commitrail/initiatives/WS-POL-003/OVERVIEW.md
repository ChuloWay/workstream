# WS-POL-003 — Unified project-guide compilation

Latest completed POL behavior: [POL-04A2 hidden finalization](WS-POL-003-04A2.md).
Current remaining design: [POL plan](planning/PLAN.md) and the
[cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract).

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: hidden execution, deterministic projections, and immutable setup finalization.
- Intent: compile one locked guide and its policies into authoritative,
  versioned project behavior without circular subsystem authority.
- Next usable boundary: add the existing ReviewPolicy boolean per the product
  handoff below. ARCH-04A public catalogue/schema remains a prerequisite before
  POL-04B produces approval-eligible live generations using completed AUTH-12B2.
- Governing sources: project-guide specifications, authorization and
  contribution-policy specifications, code, migrations, and tests.
- Preserve: trusted policy compilation, explicit ownership, atomic persistence,
  no hidden activation, and no concrete adapter leakage.

## Delivered

- Strict unified catalogue, one guide-agent adapter, authorized immutable
  compilation persistence and bounded recovery classifications, hidden execution, and deterministic
  sufficiency/artifact-policy projections are complete through 04A3.
- POL-04A2 atomically binds those exact projections to an immutable finalization
  receipt and closes the current setup generation. AUTH-12B2 supplies the exact
  concrete adapter; the default port remains unavailable and HTTP/Celery have
  no finalization composition.

## Remaining v0.1 sequence

Next product-builder policy change: add `human_review_required: bool = true`
to the existing guide-bound ReviewPolicy input, persistence, read projection
and immutable semantics/hash. This is not a new policy or compiler lane.
Follow the [bounded handoff](../../changes/pre-review-plan-reconciliation.md#product-builder-handoff-implement-the-setting-next)
for legacy lineage, tests and activation guards. Configured `false` must not
activate a guide until the automated FinalAcceptance/CON path is proven and
available; `true` retains the human-review path. Adjudication is not included.

1. After ARCH-04A catalogue/schema reconciliation, POL-04B live explicit-manager
   cutover with every legacy inference call removed from reachability.
2. POL-05/06 complete proposal visibility, setup-wide correction, approval and
   post-submit manifests with AUTH-12F4/12G. Immutable
   finalized setup rows require separately reviewed downstream custody before
   live post-submit integration.
3. POL-07 facade consumes independent ARCH-04A registered-capability proof;
   ARCH-04C alone owns durable post-submit persistence. AUTH-12H activates
   CP07's hidden complete guide command without a Task/CheckerRun dependency.
   POL-08 physical cleanup follows ARCH-04E, with no legacy live fallback.
