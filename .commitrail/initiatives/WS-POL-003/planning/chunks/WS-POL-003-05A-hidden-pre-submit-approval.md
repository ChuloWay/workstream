# Chunk Contract: WS-POL-003-05A - Hidden Pre-Submit Approval

Status: Proposed after 04B; inactive. Risk: L1.

## Goal

Build hidden PM approval and trusted effective/pre-submit projection behavior
over the complete immutable unified result.

## Allowed files

Project approval/policy service/repository/schema, ART catalogue/compiler
integration, deny-by-default AUTH seam, focused tests, and WS-POL-003 docs.

## Not allowed

Action activation, public live approval, model calls, post projection,
checker execution, second compiler/registry, or in-place proposal edits.

## Acceptance

- Approval input binds compilation/result/artifact/pre/post component hashes,
  source/setup generation, and both catalogue snapshots.
- The full proposal is reviewable before approval; required gaps block and
  optional gaps require acknowledgement.
- Mandatory platform entries cannot be selected, repeated, weakened, or
  reordered; stale lineage denies.
- Candidate effective/pre writes remain hidden and denied until AUTH-12F4.
- PROJECTS owns separate append-only approval/operation provenance keyed to
  the exact finalized setup receipt, compilation and proposed policy hashes.
  Existing canonical policy rows retain their own lifecycle; do not update a
  finalized `ProjectSetupRun`, its timestamp, outputs or receipt to record an
  approval. Choose the owner-local table/constraints in this hidden boundary,
  not in AUTH-12F4 or live 05B.
- The effective policy is mandatory platform defaults plus the approved
  project artifact policy, compiled by the existing ART-owned compiler into
  the exact pre-submit plan. Project requirements can strengthen/configure
  supported rules but cannot remove or duplicate platform work. Unknown
  required rules remain explicit gaps; do not invent defaults for them.
- Preserve review/revision policy configuration as separately validated,
  versioned PROJECTS guide inputs for later activation, not REV runtime work.

## Verification and review

Compiler parity, full-result-before-approval, gap, stale-hash, and denial tests;
real PostgreSQL approval provenance, immutable-finalization and rollback proof.
Required reviews: architecture, security, QA, product/operations.
Human focus: complete proposal and no inference at approval.
