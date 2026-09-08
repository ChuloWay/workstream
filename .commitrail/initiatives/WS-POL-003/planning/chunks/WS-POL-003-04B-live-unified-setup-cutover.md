# Chunk Contract: WS-POL-003-04B - Live Unified Setup Cutover

Disposition: Planned. Dependencies: complete 04A/04A3/04A2 and AUTH-12I/12J/12B2. Risk: L1.

## Goal

Make the unified setup service the sole live inference path and persist the
complete compilation plus canonical sufficiency/artifact-policy projections.

## Allowed files

Project setup-service/queue/composition, existing projection/finalization
public ports and explicit AUTH-12I/12J/12B2 adapters, focused tests,
specifications, and WS-POL-003 docs. Do not rebuild completed projections.

## Not allowed

Approval/pre effective mutation, post canonical projection, checker execution,
compatibility routing, or a second provider attempt/key.

## Acceptance

- Live orchestration invokes only `compile_project_guide`.
- Sufficiency and artifact-policy projections each consume fresh action-bound
  PREP in their own atomic transaction. Each PREP binds the immutable
  compilation and accepted-result hashes plus its exact sufficiency or
  artifact-policy component hash.
- All three old model methods/prompts are unreachable for unified generations;
  no deferred legacy post call or fallback exists.
- Complete replay returns canonical outputs with zero provider calls.
- Explicit PM request/recovery is the live entry. Bind one immutable attempt,
  use AUTH-12J for the two projections and AUTH-12B2 for finalization. Reuse
  the exact finalizer; do not mutate its closed setup row or mint a parallel
  completion receipt. Automatic ingestion continuation is not added here.
- Remove legacy model calls from live reachability in this PR. Later physical
  deletion does not permit fallback execution in the interim.

## Verification and review

Real PostgreSQL/Celery/API cutover, static reachability, one-attempt replay,
projection/finalization atomicity, hosted coverage, and impact-routed reviews
(architecture, security, QA, product/operations). Human focus: clean
one-call cutover with reusable, not borrowed, projection authority.
