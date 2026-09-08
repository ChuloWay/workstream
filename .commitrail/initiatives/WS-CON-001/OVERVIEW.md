# WS-CON-001 — Contribution and conditional compensation

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: hidden policy behavior.
- Intent: turn accepted work into immutable ContributionRecords and optional
  project-policy-driven compensation awards without coupling lifecycle truth to
  an economic provider.
- Next usable boundary: prepare CP05 activation, then guide-activation
  validation/persistence before task readiness.
- Governing sources: `docs/spec_contribution_compensation.md`,
  [`CONFORMANCE.md`](CONFORMANCE.md), code, migrations, and tests.
- Preserve: exact policy-version lineage, no claim-time drift, decimal-string
  quantity integrity, atomic REV/CON effects, and no runtime reputation
  projection in v0.1.

## Delivered

- Shared outbox, adapter-binding persistence and hidden lifecycle behavior,
  contribution-policy persistence and hidden draft/publication/retirement
  behavior, and shared lifecycle-audit participation are merged.
- Finance Authority adapter-binding actions are active; five policy actions
  remain unavailable. ContributionRecord, award, dispatch, fulfillment, and
  public CON behavior are not yet complete.

## Remaining v0.1 sequence

Use the [current cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
for the existing CP05-CP09 work; CON does not create a second policy/binding lane.

1. CP05 activates only the merged hidden policy behavior.
2. CP06 validates the selected frozen policy; CP07 builds hidden PROJECTS
   activation/binding, and AUTH-12H activates it. CP08 supplies lineage fields;
   ARCH-03B locks/copies them through TaskAssignment and Submission. CP09 removes the replaced legacy
   economic path only after all consumers are replaced, including CHECKERS and
   public Submission cutover; it does not block canonical `allow_review`.
3. Add ContributionRecord/CompensationAward persistence after stable REV FK
   targets, then the atomic REV/CON decision participant before live decisions.
4. Add dispatcher, fulfillment, reconciliation, and product reads only after
   their exact AUTH service identities and actions exist.
