# Chunk Contract: WS-POL-003-06A - Hidden Post-Submit Projection

Status: Proposed after 05B; inactive. Risk: L1.

## Goal

Build hidden deterministic projection and separate approval/correction behavior
from the post-submit component already stored in the unified result.

## Allowed files

Project post-submit compiler/service/repository/schema, canonical CHECKER/POL
catalogue projection, deny-by-default AUTH seam, focused tests, and POL docs.

## Not allowed

Action activation, live routes, guide rereads, any model call, checker
execution, new registrations, or reuse of agent provenance by manual policy.

## Acceptance

- Projection binds compilation/result/post component, approved upstream chain,
  catalogue snapshot, setup generation, and deterministic output hash.
- Unknown/wrong-stage/default-repeating entries fail closed.
- A correction request against existing provenance performs no model call. A
  correction requiring new unified generation is a separate compilation
  attempt with its own idempotency key. Separately proven manual provenance
  remains distinct; neither path may silently rederive from the guide.
- Candidate mutations remain denied until AUTH-12G.
- PROJECTS owns separate post-policy projection/approval/correction operations
  linked to the finalized receipt and upstream approval identity. Finalization
  is immutable, not a resumable row for later post-policy tasks. Atomic replay,
  supersession and operation uniqueness are proved here before AUTH consumes
  their facts; no later chunk invents a second setup state machine.
- Compilation is deterministic; execution of a registered work evaluator
  need not be. Preserve the canonical CHECKER definition/version, typed
  configuration, locked requirements, failure classification and implementation
  capability snapshot without invoking an evaluator during setup. A required
  unknown/disabled evaluator blocks activation instead of becoming a structural
  presence check or a silent human-review substitution.
- Provide bounded exact-draft read facts for approval, with compilation,
  upstream approval and canonical `policy_hash` lineage; a sparse legacy
  checker-name list is not the current draft. AUTH-12G must extend the exact
  object-scoped read resource contract before POL-06B exposes it.

## Verification and review

Zero-call, stale/replacement, catalogue/default, correction, denial, and race
tests; impact-routed architecture, security, QA and product/operations reviews, plus tracks affected by the actual diff. Human focus: deterministic projection only.
