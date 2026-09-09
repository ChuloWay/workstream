# WS-ARCH-001 — Modular monolith boundaries

Current remaining design: [acyclic dependency and ownership contract through
allow_review](planning/PLAN.md#current-dependency-contract).

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: through 02H, [CP05](WS-ARCH-001-CP05.md), and
  [ARCH-04A](WS-ARCH-001-04A.md) hidden post-submit contracts/conformance.
- Intent: keep product modules behind explicit ports and composition roots.
- Current boundary: CHECKERS exposes hidden versioned catalogue and phase
  contracts with registered structural conformance; live setup consumes them next.
- Next usable boundary: POL-04B live unified setup using the completed
  ARCH-04A catalogue/schema foundation, then the adopted POL
  approval/facade sequence. Return to independent CP06/CP07 after POL-07, then
  connect guide activation through AUTH-12H.
- Governing sources: `docs/architecture_lockdown.md`, accepted ADRs, code, and
  architecture tests.
- Preserve: no concrete-adapter imports in product services and no duplicate
  factory or authorization paths.

## Delivered and remaining

- Canonical module registry, frozen general/AUTH edge ledgers, CI enforcement,
  owner-facing TASK/PROJECT/CHECKER/ART APIs, hidden atomic Submission
  composition, and exact contributor/binding activation are merged through
  02H; the public route remains unchanged.
- Adapter-binding behavior and activation and hidden ContributionPolicy
  draft/publication behavior and exact Finance Authority are complete.
  CP06-CP09 remain: selected-policy validation, hidden guide binding/activation, and task-attempt lineage.
  CP09 physical removal follows zero legacy consumers, including checker/public
  Submission cutover; it is not on the `allow_review` critical path.
- ARCH-04A supplies hidden versioned catalogue, immutable phase contracts and
  registered structural conformance, not durable runs. ARCH-03A-03C then ARCH-04B-04F build project/task readiness,
  post-submit checker/materialization, remediation, and `allow_review` before
  final public 02I cutover and later REV admission.
