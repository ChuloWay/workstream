# Chunk Contract: WS-POL-003-04B - Live Unified Setup Cutover

Disposition: Planned. Dependencies: complete 04A/04A3/04A2 and AUTH-12I/12J/12B2,
plus POL-04B1 automatic request custody and [ARCH-04A consolidation](../../../WS-ARCH-001/WS-ARCH-001-04A.md). Risk: L1.

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
- Delete all three superseded model methods/prompts and their consumers/tests;
  no disabled retained implementation or fallback exists.
- Complete replay returns canonical outputs with zero provider calls.
- Verified source readiness automatically requests the first run. Bind one immutable attempt,
  use AUTH-12J for the two projections and AUTH-12B2 for finalization. Reuse
  the exact finalizer; do not mutate its closed setup row or mint a parallel
  completion receipt. Manager correction/rerun uses a new generation through POL-05; no arbitrary same-generation rerun is exposed.
- Remove superseded model calls physically in this PR; no deferred deletion.
- Consume the CHECKERS-owned public catalogue snapshot, not PROJECTS private
  registry imports or copied constants. Existing sparse-catalogue results are
  never enriched in place to make them approval-eligible.
- Update the PROJECTS input projection/validation adapter to consume that
  single current public contract, including supported typed binding parameters;
  do not keep the old blanket parameter rejection while advertising new
  capability schemas. Reuse canonical validators and prove parity without
  rebuilding the completed attempt/finalization state machine.
- A database `provider_idempotency_key` alone does not prove provider recovery:
  the current adapter does not accept that key or expose retrieval/resume.
  Unknown provider outcomes remain blocked and cannot trigger another call
  under a fresh key. Claim recovery only after a typed ADR-0014 capability
  demonstrably recovers that same provider operation. This cutover must expose
  the blocked outcome honestly and never promise automatic recovery that the
  provider contract cannot supply.

## Verification and review

Real PostgreSQL/Celery/API cutover, static reachability, one-attempt replay,
projection/finalization atomicity, hosted coverage, and impact-routed reviews
(architecture, security, QA, product/operations). Human focus: clean
one-call cutover with reusable, not borrowed, projection authority.

## Runtime configuration and terminal behavior

Use ADR 0014: `ProjectGuideAgentRuntime` extends the shared external adapter
contract and is constructed by `ExternalServiceAdapterFactory[ProjectGuideAgentRuntime]`
with explicit composition-root registration. OpenAI Agents SDK is the installed
runtime adapter, not the domain architecture. Runtime selection, model/provider
configuration and instructions are separate validated configuration concerns.
Switching runtime must not rewrite PROJECTS, Celery or policy behavior. Remove the
old hard-coded factory and affected callers/tests; do not retain an alias or
install speculative alternative runtimes. Instructions must be independently
configurable and their exact content/configuration must be bound to each immutable
attempt together with runtime/model identity. A changed deployment configuration
cannot silently alter an in-flight attempt. No credentials enter evidence.

Automatic compilation stops after findings and draft pre/post policy proposals;
insufficient guide results also terminate with findings. It never approves or
activates a guide. Manager correction/manual rerun is POL-05's new-generation
operation, using this same runtime and executor. No mode setting is introduced.
The superseded operator autostart flag must not leave manual-mode or parallel
pipeline code in the affected source-generation/continuation modules.
