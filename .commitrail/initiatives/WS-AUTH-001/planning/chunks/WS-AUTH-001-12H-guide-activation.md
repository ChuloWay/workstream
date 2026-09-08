# Chunk Contract: WS-AUTH-001-12H - Unified Guide Activation Cutover

Status: Proposed after POL-07, merged 12B2, CP05 active
ContributionPolicy behavior, CP06 validation, and CP07 ProjectGuide binding;
inactive. Risk: L1. CP08, WS-ARCH-001-03A/03B/03C, and CP09 are downstream and
are not prerequisites.

## Merge state

- Outcome on merge: `planned`

## Goal

Preserve CP07's guard for the locked ReviewPolicy boolean:
`human_review_required=false` cannot activate before the exact automated
FinalAcceptance/CON path is proven and available. An AUTH allow is not a
substitute for that capability check. True follows the human branch without
depending on automated acceptance; never silently coerce false to true.

Activate only `project.guide.activate` over one complete approved
current-generation unified compilation chain.

## Allowed files

AUTH catalogue/kernel/PREP/runtime/API composition, project activation
authorization adapter/resource context, one AUTH-owned parity/provenance
migration if required, focused tests, specifications, and AUTH/POL memory.

## Not allowed

Compilation, policy derivation/approval/compiler semantics, agent calls, ART
provider behavior, CON redesign, task/submission/review activation, legacy
chain compatibility, or issuer-role fallback.

## Acceptance

- Entry requires exact immutable `ProjectGuideCompilation`, accepted result and
  sufficiency/artifact/pre/post component hashes, source/setup generation, both
  catalogue snapshots, approved effective/pre/post projections, completed
  unified setup custody, and exact review/revision policy IDs, `policy_generation`,
  canonical hashes and current guide generation. Review/revision configuration
  is PROJECTS readiness input; REV execution/admission is not a prerequisite.
- Every capability-gap disposition or blocked/partial/unapproved/mixed-generation
  component denies. Only ordinary non-blocking sufficiency warnings admit exact
  PM acknowledgement; the current schema has no optional capability-gap bypass.
- Final PREP binds the complete chain plus actor/link/grant, action, operation,
  request/idempotency, session, and transaction. The CP07 PROJECTS command owns product
  locks and the one activation commit.
- CP07 supplies the exact validated binding candidate through CP06, including
  expected policy/version equality to the active aggregate's current selector.
  AUTH consumes those locked facts and CP07 persists
  `ProjectGuide.contribution_policy_version_id` in the same activation
  transaction. A previously persisted binding or active guide is not a
  prerequisite to its own activation. Retired economic fields grant no
  authority and are ignored by this activation path; CP09 removes them only
  after all consumers are replaced, including CHECKERS and public 02I, with
  retained history preserved.
- ARCH-04A proves the selected registered evaluator implementations and POL-07
  proves compatible typed phase composition/configuration. No actual Task,
  Submission, CheckerRun, ARCH-04C persistence or ARCH-04D runtime activation
  is needed to activate a guide. Requiring a completed execution here creates
  a cycle because that execution first needs a task under the active guide.
- Consume CP07's single hidden PROJECTS activation command and replacement
  readiness guard; AUTH does not implement policy selection, validation or
  guide writes. Exact runtime composition and activation tests traverse that
  command with all canonical prerequisites and without legacy PaymentPolicy.
- No old independent sufficiency/submission/post rows are sufficient without
  compilation/component linkage; no compatibility authorization remains.
- Concurrent activation yields one active guide. Stale candidate, revoked
  authority, mismatched replay, copied/wrong handle, session or transaction
  mismatch denies before mutation. Exact replay returns the same activation
  after fresh authority checks without publishing or binding twice.

## Verification and review

Complete/partial/mixed-chain matrix, gap acknowledgement, concurrency/replay,
AUTH all-pairs, POL-07 sole-port and activation integration, migration round trip, hosted
coverage, and impact-routed architecture/security/product/QA review plus
affected migration, test and documentation tracks. Human focus: complete
unified lineage only.
