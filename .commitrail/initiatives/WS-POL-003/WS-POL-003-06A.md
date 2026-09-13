# WS-POL-003-06A — Hidden post-submission policy custody

- Initiative: WS-POL-003
- Durable disposition: Complete
- Risk: L1
- Intended merge outcome: Deterministically project the saved post-submit proposal into the canonical checker policy, with separate approval and correction custody; live authority and public exposure remain AUTH-12G/POL-06B.

## Intent

The unified guide run already saves the complete result. POL-05B exposes it and
approves the artifact/effective/pre-submit chain. The missing next operation
projects its post-submit component without reading documents or calling a model.
The manager needs an exact complete policy draft before a separate approval.

`GuideProposalRepository.lock` already locks and validates compilation,
finalization, result hashes and setup generation. It loads optional approval
custody, validating it after the artifact policy leaves draft; it does not itself
require current upstream approval.
`guide_compilation/approval_custody.py` proves the approved chain.
`PostSubmitCheckerPolicy` remains the canonical business row in `checker_policies`;
`projects/post_submit_policy.py` and CHECKERS' `CompiledPostSubmitPolicy` already
own its sole body and `policy_hash`. Active-guide, task and artifact readers
consume that body. There is no live post-policy writer to preserve.

The current row's role-string approval/supersession fields are superseded by
exact actor/link/project-grant/decision custody in this scope. Shared fixtures
and active-guide readiness must follow the replacement; no compatibility fields
or alternate manual compiler path are introduced. Retained role-string values
remain inert historical data with no writer, reader, constraint or authority
dependence. Do not drop retained values; removing executable dependence is the
cleanup, and no historical column authorizes any operation.

## Bounded change

- PROJECTS canonical post-policy compiler, model, repository, typed API and hidden
  service, and guide-compilation approval/correction custody helpers where reuse
  needs a narrow extraction. A new cohesive post-policy module may own these
  operations; it must reuse finalization resolution and guide locking.
- CHECKERS public canonical compiler/value contracts only as needed to consume
  exact versioned bindings and their validated configuration; no registry or
  execution change.
- AUTH public typed unavailable-by-default post-policy PREP seam, replacement
  of the existing planned post-policy mutation resource shape, and bounded audit
  vocabulary, without action activation, evaluators or live composition. Remove
  its obsolete setup-step custody requirement; finalization is already closed.
- `interfaces/project_agents.py`: extract shared post-binding validation if needed
  so persistence and projection use the same requirement/configuration rules,
  with no runtime/schema change or duplicate validator.
- One successor Alembic migration for operation custody, ownership, immutable
  evidence, unique projection/approval/successor identities and lifecycle guards;
  matching models and exact schema inventory.
- Affected active-guide reads/fixtures, focused unit and PostgreSQL tests, test
  ownership/inventory entries, specifications, README/manual and current POL,
  ARCH and roadmap navigation. Update local roadmap exports only if present.

### File boundary

- `backend/app/modules/projects/post_submit_policy.py`, `models.py`, `schemas.py`,
  `repository.py`, `service.py`, `authorization_reads.py`;
  new `backend/app/modules/projects/post_policy/{service,repository,models,custody,compiler,correction}.py`
  and package initializer; `backend/app/modules/projects/api/post_policy.py`.
- `backend/app/modules/projects/guide_compilation/proposal_correction.py`,
  `proposal_repository.py`, `approval_custody.py`, `proposal_service.py` only for
  shared lock/correction extraction and complete read reuse.
- `backend/app/modules/authorization/api/post_policy.py`, `runtime.py`,
  `catalogue.py`, `domain/audit.py`, and `backend/app/modules/audit/schemas.py`
  for bounded evidence vocabulary; existing `api/guide_proposal_review.py` only if the exact read
  extension belongs there. Catalogue changes declare vocabulary, not availability.
- `backend/app/interfaces/project_agents.py` and
  `backend/app/modules/checkers/api/{post_submit_catalogue,policy_compilation}.py`.
- `backend/alembic/versions/0020_post_submit_policy_custody.py` and `backend/alembic/env.py`
  for exact current migration admission;
  `backend/app/db/models.py` for model registration;
  `backend/tests/conftest.py` for exact migrated schema inventory.
- New `backend/tests/projects/post_policy/` tests and local fixture helpers;
  `backend/tests/projects/{post_submit_fixtures,test_activation_readiness}.py`,
  `backend/tests/projects/guide_compilation/proposals/{pg_support,test_postgresql,test_migration,test_inventory}.py`,
  `backend/tests/checkers/post_submit/{test_compiled_policy,support}.py`,
  `backend/tests/{test_checkers,test_artifact_admission,test_authorization}.py`;
  `backend/tests/projects/{unified_policy_fixtures,policy_bundle_fixtures}.py`,
  `backend/tests/committed_guide_fixtures.py`, `backend/tests/test_api_contract_e2e.py`
  and `backend/tests/test_tasks.py` for their shared downstream policy setup;
  `backend/tests/test_alembic.py` for exact migration graph enrolment;
  `backend/scripts/api_contract_e2e.py` for its isolated hidden-prerequisite call.
  Replace manual policy seed assertions with real operation custody; preserve
  runtime requirement and revision behavior tests using reachable canonical inputs.
- `backend/scripts/behavior_ownership.py`, `.ci/behavior-ownership/partition.v1.json`,
  affected `.ci/behavior-ownership/{auth,lifecycle}/` records, canonical test-lane
  catalogue and inventory, and `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`
  for exact shrinking source/line changes only. `.github/workflows/backend.yml`
  adds an exact post-policy 90% coverage gate; no existing threshold or proof
  requirement is weakened.
- This record, adopted `planning/chunks/WS-POL-003-06A-hidden-post-submit-projection.md`,
  `planning/PLAN.md`, `OVERVIEW.md`, `.commitrail/INDEX.md`, ARCH current dependency
  plan, `README.md`, `docs/roadmap_status.md`,
  `docs/operations_project_operating_manual.md`,
  `docs/architecture_checker_framework.md`, `docs/architecture_data_model.md`,
  `docs/product_first_user_flows.md` and the current project-guide spec.
  Local `sheets/workstream_roadmap.{xlsx,csv}` only if present.

## Risk and review routing

L1: exact policy lineage, authorization, transactions and retained evidence.
Required tracks: architecture/reuse, security, QA/test-delta, product/docs and
CI integrity. Human focus is complete projection and atomic decision custody.

## Prohibited changes

No public routes, action activation, guide activation, CP06/CP07, checker execution,
provider invocation, document reread, new capability registration, frontend,
external adapter changes, manual policy fallback, retained-data deletion or
weakening of authorization, lineage, atomicity, tests or CI.

## Acceptance criteria

1. Resolve the exact finalized compilation under existing guide serialization.
   Explicitly require current ApprovalCustody: committed reservation, approval
   operation, approved artifact/effective rows, compiled pre row and no successor.
   Validate approved_projection_digest and the current approval tip before
   compiling or writing. A valid finalized but unapproved proposal must reject. Bind project/guide/source, setup generation,
   finalization, compilation/result/post component, upstream approval operation
   and output digest, effective/pre identities/hashes, catalogue identity/hash
   and canonical compiled policy hash into immutable projection custody.
2. Compile only persisted post bindings through the canonical catalogue. Validate
   each requirement disposition, exact definition/version, post stage,
   selectability, configuration and implementation state. Insert platform defaults
   once, reject their repetition by selections, unknown/disabled/wrong-stage or
   missing requirement bindings. Multiple requirements may legitimately share
   one identical configured checker; preserve all requirement traceability while
   emitting that checker once. Never silently omit an intended required check.
   Capability suggestions remain non-executable and visible in the existing
   complete proposal package; they confer no implementation support.
3. Hidden exact-draft read returns the canonical body, policy hash, immutable
   target and operation lineage with the existing safe proposal display. It is
   separately authorized and exposes no source handles. No sparse name-list
   response substitutes for a reviewable draft. Reuse the existing complete
   review-package read action, with an exact post-draft extension to its hidden
   typed facts; AUTH-12G supplies its live implementation. Keep the existing
   derive, approve and correction actions planned; no parallel action family.
4. Projection, approval and correction have distinct action-bound nominal PREP
   handles. The production seam has no permissive implementation or implicit
   constructor default. Exact fresh authority and root-transaction checks precede
   protected writes; replay checks retained evidence and current authority.
   A fixed setup-service identity derives; a project-scoped human manager approves
   or corrects. AUTH-12G implements these authorities later.
5. Approval accepts the exact draft and upstream commitments, never new policy
   content. It records actor/link/grant/decision and immutable operation receipt.
   Reject stale setup, upstream replacement, catalogue change, repeat approval
   under another key or policy-content substitution. Exact replay returns the
   same receipt without another projection, approval or provider invocation.
6. Correction preserves the original result/policy body and creates an attributed
   post-policy correction receipt linked to the existing unified correction
   operation/successor. Reuse its operation and generation allocation, separately
   authorizing both protected actions in one caller transaction. Enter both
   authority contexts before acquiring product locks in fixed order: post-policy
   PREP then unified-correction PREP, using both precomputed locators. Never call
   or nest `GuideProposalService.request_correction` after post-policy locks.
   Extract the existing allocation/custody routine for the already-prepared
   handle. Consume both actions, close both contexts, then persist the existing
   correction operation, one successor, and post-policy correction/supersession
   in the same caller root transaction. Replay validates both retained decisions.
   Do not create a second setup state machine. Dispatch remains the existing separately authorized
   public operation. Supersede the post policy atomically; replay allocates no
   successor. Fresh inference, if requested later, belongs to that new generation.
   There is no manual-policy provenance mode.
7. Reprojection after a corrected generation uses its newly approved upstream
   chain, supersedes any current predecessor through the canonical lifecycle and
   keeps old receipts immutable. Direct database guards reject duplicate chains,
   mismatched ownership/outputs, mutation/deletion of evidence and missing custody.
   Use one specific append-only post-policy operation table for this action
   family, unique by policy and operation kind, with one projection per upstream
   approval. Its target binds the existing GuideProposalTarget, upstream approval
   receipt/digest and policy_hash; the policy remains the sole compiled body.
   Do not reopen finalization or repurpose setup output pointers.
8. Replace role-string proof in affected policy readers/fixtures with validated
   operation custody. Keep one canonical policy body/hash and required behavior
   tests. Required capability gaps stay explicit and cannot turn into supported
   structural judgments or authorize activation.

## Evidence

Before implementation: read-only plan review of reuse, correction transaction
composition, authorization separation, schema ownership and concrete test paths.

Focused proof: complete valid finalized/approved fixtures derived from
`tests/projects/guide_compilation/proposals/pg_support.py`; real compiler positive
and independently invalid selections; stored requirements sharing one checker;
exact read; approval/replay; correction/replay and next-generation replacement;
foreign project/actor, revocation, stale catalogue/setup/upstream; prepared-close
failure and rollback; concurrent projection/approval/correction; direct-SQL missing
receipt, duplicate chain and immutable-evidence probes. Pure compiler contract tests revalidate and reject malformed bindings; these
unit mutants make no claim of persisted custody. Unknown, wrong-stage, disabled
or missing bindings already fail initial compilation validation. PostgreSQL
operation negatives instead start from valid finalized and approved results and
must pass earlier guards, changing only the targeted downstream fact (stale
catalogue/upstream, missing operation relation, or substituted output). Compiler
selection-omission mutants and persisted missing-custody mutants are separate;
each exact test must fail when only its relevant protection is removed.
Runtime/document providers are
forbidden spies during these operations. No real provider test is relevant here.

Run affected tests with PostgreSQL/MinIO using the canonical isolated runner,
coverage (at least 90% for materially changed subsystem), Ruff, architecture and
schema/test inventories, stale wording and markdown links. Then exact-tree hosted
CI with zero skipped/deselected tests and verified aggregate artifacts. Use the
independent locked `/tmp/pol05b-clean-venv` environment; the shared backend venv
has previously crashed and is not evidence for this change.

Internal reviews: architecture/reuse, security, QA/test-delta, product/operations
and documentation; CI integrity for schema/test inventory and hosted evidence.
Freeze a clean candidate, resolve findings in batches, replay affected tracks.
Human focus: exact saved-result projection, complete required checks, correction
recovery, atomic policy/authority custody, and honest hidden-versus-live wording.

## Implementation decisions

The canonical policy body stays in `checker_policies`; the specific
`project_post_policy_operations` table owns immutable derive/approve/correction
receipts. Deferred bidirectional guards protect source, output, authority and
successor relations. Retained post-policy operations prevent migration downgrade.
The existing planned AUTH resource now binds finalized compilation and approved
upstream evidence, replacing its obsolete unfinished-setup-step requirements.

The PROJECTS review-package contract is generic in its canonical policy value,
so its public API does not import a foreign owner's API. The hidden service binds
that parameter to CHECKERS' existing `CompiledPostSubmitPolicy`. This preserves
one complete typed body without copying the checker schema into PROJECTS.

Shared fixtures now select post-submit requirements before the unified result is
validated and finalized, then call the real hidden projection and approval.
They no longer fabricate approved post-policy rows or accept manual warning and
severity overrides outside the unified result. Runtime compiler/severity tests
remain. The retained-version revision/read test uses a required evidence failure
and preserves its revision, privacy and locked-lineage assertions; its deliberately
seeded packet is a post-routing fixture, not a claim that invalid intake passes.
Unrelated historical ReviewPolicy/RevisionPolicy fixtures remain outside this
post-policy replacement; they provide no post-policy authority.

The size guideline is exceeded because the approved boundary includes the
storage guards, typed authority seam, shared correction extraction, affected
readers and replacement fixtures together. Splitting those would leave readers
or tests using superseded approval proof. No public wiring or action activation
is included. Review is divided by these concrete risks, while the change remains
one post-policy custody outcome.


### Shared-consumer verification repairs

Affected tests now arrange post-policy custody through the same hidden operations,
including artifact recovery and pre-submit evidence prerequisites. Controlled
read-corruption tests inject only a loaded value; they do not rewrite immutable
policy evidence. Their original release/submission/checker rejection and zero-effect
assertions remain. Scope includes their existing owners
`backend/tests/test_artifact_recovery.py`, `backend/tests/test_artifact_internal_authorization.py`,
`backend/tests/test_default_pre_submit_execution.py`, `backend/tests/pre_submit_test_helpers.py`,
`backend/tests/authorization/task_authority/test_submission_policy.py`,
`backend/tests/projects/policy_read_fixtures.py`,
`backend/tests/projects/test_active_guide_read_composition.py` and
`backend/tests/test_ci_lane_catalogue.py`.

Additional regression proof covers stored foreign principals, separately denied
exact reads, fresh predecessor decisions after successor approval, and direct SQL
with an otherwise valid operation whose output, grant or action is substituted.
Schema parity uses the same PostgreSQL dialect on both sides; migration round-trip
uses the existing schema-contract isolation because dropped/re-added columns change
physical ordinals. The canonical schema fingerprint and all existing gates remain.


The affected `backend/tests/test_projects.py` contract also removes the two
obsolete tests that required role-string approval constraints or assigned a
`worker` string to retained policy fields. Current authority is protected by
post-policy stored-principal/direct-SQL tests and the shared proposal authority
matrix, including operator, audit, system-manager and foreign-project denials.
The retained pre-submit-hash rewrite test now requires the specific immutable
policy guard and proves the original hash survives rollback. It no longer
expects a foreign-key exception to precede the stronger immutable-row guard.

Main reconciliation preserves the API-drill repairs: archive byte/entry limits,
machine policy identifiers, request validation and document replay remain owned
by their existing pre-submit/setup paths. The shared agent-result schema keeps
those fields alongside the extracted post-binding validator. The ownership
partition includes both the guide-document drill and all eight POL-06A targets;
its digest is recomputed over the combined assignments. The roadmap retains the
completed client-drill evidence and advances only POL-06A's next boundary to
AUTH-12G/POL-06B.
