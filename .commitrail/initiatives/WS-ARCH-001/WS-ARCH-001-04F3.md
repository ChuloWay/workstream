# ARCH-04F3 — Exact-cause checker-remediation replacement intake

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: one hidden contributor replacement ZIP passes the
  canonical pre-submit intake again and creates a new immutable Submission and
  generation-one evaluation request only when its immediate predecessor has the
  exact current authorized checker-remediation outcome.
- Original base: merged main `735cf2659` (PR 534), with
  `0032_checker_remediation`; reconciled with main `d47ee1e99` (PR 535) and
  its `0033_contribution_reads` predecessor. This record is group 1 of the first complete
  contributor milestone in the [current plan](planning/PLAN.md).

## Intent

Before F3, the TASK context accepted `needs_revision` with only the latest
Submission ID/version and labels every such predecessor `revision`. ART retains
that predecessor across preparation, passing pre-submit evidence, verified
admission and binding. The canonical TASK writer creates version 2 and its
evaluation dispatch from that admission. [04F2](WS-ARCH-001-04F2.md) now makes
`needs_revision` possible from a completed, authorized, contributor-correctable
checker result, but none of those intake facts prove which result caused it.
The existing ART predecessor-change check proves the ZIP changed, not that
the contributor is allowed to replace this particular failed evaluation.

The target is a hidden, usable replacement path through the existing ART
preparation/verifier, TASK context and single `TaskSubmissionCreationService`.
The TASK repository locks its own task/assignment/latest Submission rows and
selects an owner-qualified immutable `TaskPostSubmitRoutingManifest`. One TASK
composite implementing the **existing** `TaskSubmissionContextPort` then
checks CHECKERS currentness through the existing public evaluation port. All
production context callers, including ART before byte access and TASK creation,
use that composite through the existing adapter binding. No generic TASK
repository method gains a CHECKERS dependency or remains as a weaker parallel
port. The source must be
`needs_revision`, exact for that task, assignment, contributor, Submission,
run and result, and have its completed AUTH-backed routing consequence. The
context exposes one server-selected `checker_remediation_manifest_id`; no
caller-selected checker route or new endpoint is introduced. A source mismatch
or absence denies before contributor ZIP bytes are read, and a late change
denies before evidence, admission consumption or a new Submission commits.

Carry that single cause ID from the TASK context through ART passing evidence,
verified admission and final binding, then into the TASK creation dispatch.
The existing predecessor ID/version, locked policy context, archive and
semantic manifest remain the other lineage facts. Bind the cause in the final
prepared AUTH resources for bundle preparation, artifact binding and Submission
creation; preliminary actor/assignment preflight remains before byte access.
The database closes the same cause relationship across immutable rows and the
three retained AUTH receipts. No second findings store or duplicated checker
result body is needed. An ART durable intent already references its immutable
evidence set, and a Submission already references its one admission/dispatch;
extra cause columns on those rows would repeat an existing exact link.

The existing `revision` kind currently conflates checker remediation with
human revision. The new TASK context and committed creation kind will name
`checker_remediation` explicitly for new replacement creation. New uncaused
`revision` SQL inserts are denied; no historical revision alias or invented
source is added to runtime/replay. The migration checks retained revision rows
before changing the schema. If their exact cause and authority receipts cannot
be proven, upgrade refuses transactionally with the rows and 0033 schema
unchanged. Retained initial rows migrate unchanged. New human-review revision
admission remains unavailable until its own exact Review cause exists.

Alternatives considered: predecessor-only checks are insufficient because a
synthetic or human-review `needs_revision` state could reach ART; copying
findings/result JSON into ART would duplicate CHECKERS evidence; a separate
replacement writer or route would fork the atomic creation operation.

## Bounded change

1. TASK context: extend `TaskSubmissionContextFacts`. The repository only
   locks TASK rows and selects an owner-qualified 04F2 manifest. A tightly
   scoped TASK composite in `submission_composition.py` or its own TASK file
   implements the existing port and uses `EvaluationCoordinationPort` to read
   the manifest's full stored request and exact current result/recommendation.
   It also requires the existing SQL complete-outcome predicate. Inject that
   port at `task_submission_context_port` and the existing creation composition;
   trace every ART pre-byte, post-byte, evidence and put relock to this binding.
   Initial intake keeps no cause. A missing, foreign, stale, setup-fault or
   non-remediation manifest denies. No private CHECKERS model import in TASK.
2. ART intake: compare the source selected before ZIP reading with each later
   relock. Include its ID in the existing passing evidence operation identity,
   passing capability, durable final preparation resource, verified admission,
   consumption and binding resource. Run the full original ZIP intake and
   canonical change gate; the predecessor's archive and immutable evidence are
   read only.
3. TASK creation: consume only an admission with the same exact cause, append
   the source ID to the existing dispatch and creation AUTH resource, then
   reserve the successor evaluation and outbox event inside the same root
   transaction. Fresh-authorized replay checks the committed source/receipts
   by the same admission key and does not require the old run still be current.
4. A linear migration after main’s `0033_contribution_reads` adds the minimal cause
   columns/checks/FKs and replaces the existing admission, AUTH-resource and
   dispatch SQL closure as necessary. Retained initial evidence and its exact
   receipts remain valid. If retained `revision` dispatches cannot prove the
   new exact source and receipts, fail before applying DDL; keep their rows and
   0033 revision unchanged. Do not backfill a guessed cause or preserve an
   uncaused runtime/replay branch. Deny SQL substitution of cause, predecessor,
   recommendation or receipt. No sibling Alembic head.

### Allowed files

- TASK: `backend/app/modules/tasks/api/submission_context.py`,
  `api/submission_command.py`, `api/__init__.py`, `repository.py`, `submission_composition.py`,
  `submission_replay.py`, `submission_dispatch.py`, `submission_participants.py`,
  `models.py`, and `backend/app/adapters/tasks/__init__.py`. A narrowly scoped
  new `backend/app/modules/tasks/submission_context.py` is allowed only if the
  existing composition file cannot keep the owner small.
- ART: `backend/app/modules/artifacts/api/submission_preparation.py`,
  `pre_submit_evidence.py`, `submission_materialization.py`,
  `submission_admission.py`, `submission_bindings.py`, `schemas.py`,
  `models.py`, `service.py`, `authorization.py`, and
  `backend/app/adapters/artifacts/__init__.py`.
- AUTH: `backend/app/modules/authorization/submission_preparation.py`,
  `submission_consumption.py`, `submission_creation_authorization.py`,
  `prepared_submission_replay.py` only if its exact replay comparison needs
  the cause, and `backend/app/modules/authorization/artifact_project_authority.py`
  only if its typed guard needs the new closed kind. Existing action and grant
  identities stay unchanged.
- One linear `backend/alembic/versions/0034_checker_remediation_replacement.py`
  migration after 0033 contribution reads; matching model/schema registration and
  `backend/tests/test_alembic.py` migration graph assertion.
- Focused existing owner tests under
  `backend/tests/test_submission_predecessor_custody.py`,
  `backend/tests/tasks/submission_dispatch/`,
  `backend/tests/tasks/post_submit_routing/`,
  `backend/tests/test_submission_bundle_admission.py`,
  `backend/tests/test_submission_composition.py`,
  `backend/tests/test_submission_preparation_authorization.py`,
  `backend/tests/authorization/task_authority/test_submission_authority.py`,
  `backend/tests/test_tasks.py`, plus
  `backend/tests/tasks/submission_dispatch/test_replacement_migration.py` for
  retained-row upgrade proof and
  `backend/tests/tasks/submission_dispatch/test_replacement_creation.py` for
  ready-admission supersession, concurrent creation and late-insert rollback.
- Direct callers of the superseded repository context method also require
  bounded test/support migration in `backend/tests/historical_submission_fixtures.py`,
  `backend/tests/authorization/task_authority/test_lifecycle_races.py`,
  `backend/tests/authorization/task_authority/test_submission_policy.py`,
  `backend/tests/test_artifact_bindings_db.py`,
  `backend/tests/test_submission_evaluation_capacity.py`,
  `backend/tests/test_effective_pre_submit_execution.py`, and
  `backend/tests/test_approved_guide_intake.py`,
  `backend/tests/retained_material_fixtures.py`,
  `backend/tests/pre_submit_test_helpers.py`, and
  `backend/tests/test_blocked_pre_submit_feedback_postgresql.py`,
  `backend/tests/test_artifact_bindings.py`,
  `backend/tests/test_submission_bundle_preparation_recovery.py`,
  `backend/tests/test_pre_submit_attempt_schema.py`,
  `backend/tests/reviews/decision/support.py`,
  `backend/tests/submission_fixtures.py`, and
  `backend/tests/authorization/submission_history/test_isolation.py`. The shared
  retained-material and pre-submit fixtures must also compose the canonical
  context port. Existing routing successor fixtures must publish the real
  checker-remediation outcome before intake; historical migration fixtures must
  remove temporary nullable cause seed columns before their upgrade assertions.
  Preserve each original
  owner, archive, authorization and race assertion while switching to the
  single composed context port or exact new context shape; add no old-port alias.
- `backend/tests/migration_fixtures.py` only to extend existing historical-schema
  seeding helpers with temporary all-null cause columns. Remove those columns
  before upgrade and assert original row values and column shape are restored;
  this test support does not add a runtime compatibility path.
- `backend/tests/migrations/test_contribution_read_audit.py` pins the newly
  merged contribution-read migration's own upgrade/downgrade proof to 0033,
  so later migrations do not intercept its retained-evidence refusal assertion.
- `backend/tests/conftest.py` only for the deterministic 0034 public-schema
  fingerprint, with the existing strict schema guard and resettable-table list
  retained. The lead independently verifies the integrated fingerprint.
- This record and affected current capability claims in `docs/roadmap_status.md`,
  `docs/spec_chunk_4_task_queue_assignment.md`,
  `docs/spec_artifact_storage_service.md`,
  `docs/spec_authorization_service.md`, `README.md`, ARCH plan/chunk map/overview
  and `.commitrail/INDEX.md` only where the merged outcome changes a claim.
  Verify exact documentation filenames and links before editing.
- Canonical F3 lineage and branch corrections in
  `docs/architecture_data_model.md`,
  `docs/architecture_lifecycle_state_machine.md`,
  `docs/spec_review_lifecycle.md`,
  `docs/operations_revision_replay.md`, and
  `docs/operations_queue_policy.md`: replace the nonexistent Submission cause
  column and distinguish delivered checker remediation from planned human
  Review preparation, finding responses and rebase. `README.md` receives the
  same locked-rule distinction in its current operating summary.
- Adjacent current navigation: ART, AUTH, POL, CON and REV initiative
  `OVERVIEW.md` files, plus AUTH and POL `planning/PLAN.md` and
  `planning/CHUNK_MAP.md`. These currently assign replacement intake as the next
  boundary; reconcile that claim in the implementation PR without rewriting
  completed historical records or claiming recovery is delivered.
  The adopted `planning/chunks/WS-ARCH-001-04F-checker-remediation.md` parent
  also records the user's first-release decision: retain submitted work in a
  manager-visible setup-fault hold without contributor penalty; defer changing
  submitted-task rules. This is remaining-work scope, not an F3 runtime claim.
- Lead-owned integration: `backend/alembic/env.py`,
  `backend/scripts/test_lane_catalogue.py`,
  `backend/scripts/behavior_ownership.py`,
  `.ci/behavior-ownership/partition.v1.json`, and
  `backend/tests/test_behavior_ownership.py`, plus
  `backend/tests/test_ci_lane_catalogue.py`. Register the exact new context
  module and migration proof without broadening permitted owners or dropping
  tests; regenerate the combined partition digest after implementation arrives.

Shared migration environment/fingerprint files, AUTH catalogue/action lists,
and any overlapping current docs are **coordination-owned by the lead** unless
explicitly allocated. A newly observed required file outside this list is a
plan-review delta before editing, not an invitation to widen implementation.

### Prohibited changes

No public 02I route, production handler registration, new checker command or
result writer, human Review/revision decision, acceptance/contribution/award,
Operator retry, claim lease, payment fulfillment, frontend, policy relaxation,
compatibility/fallback writer, or modification to the recovery worker's
terminal retry/setup-fault scope. Do not change existing committed Submission,
checker result, AUTH decision, outbox event or ART bytes. An infrastructure or
setup fault never becomes contributor remediation.

## Acceptance criteria

- AUTH creation resources reject mismatched kind, task status, version,
  predecessor pair or cause; binding resources require the exact successor
  version. Valid initial/remediation resources reach the real parser. Restoring
  the pre-repair validators must fail the malformed-shape assertions.
- From a real routed 04F2 `needs_revision` result, the same submitter's changed
  full ZIP passes pre-submit checks, reaches a verified ready ART admission,
  and creates exactly one version-2 Submission, binding, creation/binding
  receipts, generation-one CHECKERS reservation and request event atomically.
  It retains the exact predecessor and remediation manifest, locked policy and
  verified new bytes. The prior Submission, failure result and manifest remain
  byte-for-byte immutable; no Review or failure economics appear. Exercise both
  locked human-review-required values because remediation is policy independent.
- The unchanged archive and same semantic manifest fail the existing change
  gate before provider put, with actionable intake feedback. A blocked new
  pre-submit check creates no Submission or replacement dispatch. Valid new
  content is the control proving the cause gate is reachable.
- Foreign task/assignment/contributor/predecessor, a valid foreign remediation
  manifest, non-remediation success, task/setup failure, stale current run,
  later generation, missing or substituted AUTH receipt, and source changed
  between first context lock, byte read, verification and consumption all deny
  without a new Submission. Valid controls for each substitution are two
  independently routed failure fixtures, not random IDs or synthetic task
  status updates. Denial before byte access is checked with a source that fails
  if read.
- Concurrent replacement requests serialize on TASK and one succeeds; an
  independent-session current-run/generation race proves TASK-before-CHECKERS
  lock order and stale-cause denial. Replay after response loss returns the
  exact committed identities under fresh actor authority with no repeated
  binding, evaluation or outbox effect. Rollback and actual later participant
  insertion failure leave no partial replacement effects.
- Direct PostgreSQL probes reject evidence/admission/dispatch cause
  substitution and mismatched final AUTH contexts. Upgrade from 0033 preserves
  committed initial Submission and remediation outcome rows and validates their
  original receipts. A separately seeded retained uncaused `revision` dispatch
  makes the upgrade refuse with the 0033 schema and all rows unchanged. Function
  search paths and FKs do not trust caller text.

The valid integration control uses
`tests.tasks.post_submit_routing.remediation_support.remediation_source`. It
starts with real ART admission/Submission and CHECKERS finalization, then commits
the authorized outcome before replacement intake. The control checks TASK
`needs_revision`, the active original assignment, exact routing manifest/AUTH
receipt and zero REV/CON/economic effects. A changed `revision_archive(h.data)`
then goes through `_verified_admission` and the sole
`compose_hidden_submission_creation_command` writer.
`test_submission_predecessor_custody.py` uses this routed source rather than a
synthetic TASK status update. Initial-submission and success-path regressions
remain control requirements.

| Implemented proof boundary | Guard / assertion | Valid control |
| --- | --- | --- |
| Both locked ReviewPolicy modes, changed ZIP | TASK exact completed source; ART full pre-check; atomic TASK dispatch | Commit the real 04F2 outcome under each policy, then prepare `revision_archive(h.data)` and create through the canonical writer |
| No routed cause, setup fault, or success | TASK context before `byte_source` iteration | Completed failure before outcome, real setup-fault completion, or real success result; pair with committed remediation of the same initial fixture |
| Foreign task, assignment, contributor, predecessor or source | TASK owner-qualified lock/source selection before bytes | Two independently committed remediation fixtures; same fixture with its own exact selectors succeeds |
| Current run superseded after remediation | Composite CHECKERS current-result check before bytes | Original routed source first passes; reserve a real successor generation under TASK lock, then retry the old cause |
| Source changes after first lock or ZIP read | Second TASK composite relock before pre-submit evidence | Start from committed source and valid changed ZIP; reserve a successor at the controlled interphase seam |
| Source changes after checked evidence or verifier publication | Evidence/put relock or ART admission consumption before TASK creation | Same passing ZIP and ready verified admission before the competing generation; unchanged cause continues successfully |
| Unchanged archive, same semantic manifest, blocked new pre-check | Existing ART change gate or pre-submit check before provider put/Submission | Same committed remediation source with `revision_archive(h.data)` as passing changed-content control |
| Competing replacements and response-loss replay | TASK lock, unique admission/dispatch and fresh AUTH replay | Two valid ready admissions for one cause; winning committed request replays exact receipt after later task state |
| Late participant failure | Root transaction's real binding/evaluation/outbox insertion | Valid preparation/admission and authority reach the chosen failing insertion; no partial rows persist |
| Direct SQL cause or receipt substitution | ART/TASK FK, immutable row and deferred dispatch/AUTH closure | A complete committed replacement first passes SQL predicates; alter one cause or receipt in an isolated transaction |
| 0033 to 0034 upgrade | Migration retained-row precheck and revised SQL closure | Retained initial Submission and 04F2 remediation source survive; separately seeded uncaused revision refuses unchanged |

Preserve existing initial, success, archive/semantic-change and foreign-predecessor
controls; replace only synthetic-status fixtures that would bypass the new
causality rule. Each negative must first demonstrate its adjacent valid path,
then fail at the named boundary rather than fixture setup.

## Evidence

The implementation PR carries actual command, CI and reviewer evidence; this
record defines the required proof, not an executed-test attestation. Verify
focused contracts, bounded isolated PostgreSQL/Local and MinIO behavior,
migration upgrade/replay, boundary/inventory/docs/link checks and the hosted
suite. Discriminating probes must remove the cause/currentness guard and show
the specific negative assertion fails after a valid control passes.

## Risk and review routing

- Risk class: L1: contributor authorization, immutable evidence and atomic
  ART/TASK/AUTH/SQL lineage cross owner boundaries.
- Size exception: one cause reference must travel through the existing TASK
  context, ART evidence/admission, AUTH receipts and atomic dispatch together.
  Their migration and affected callers cannot be split into independently
  usable changes. Current navigation and focused storage proofs add files but
  no second product outcome; terminal infrastructure retry stays in 04F4.
- Plan review before implementation: architecture, security and QA, including
  a reachable positive control and each negative's earliest expected denial.
- Frozen implementation review: architecture, security, QA, test delta,
  reuse/dedup, product operations and documentation. Add CI integrity if
  migration/test registration or required checks change. The lead runs shared
  checks once and coordinates review target freshness.
- Human focus: the replacement must be caused by the exact current checker
  failure, use the original assignment and locked policies, pass full intake
  again, and atomically dispatch a new evaluation. The failure path creates no
  acceptance or economic facts; public activation remains later work.

No human product decision is needed for this bounded hidden path. The lead's
internal plan review is the implementation sequencing point; it is not a
new user permission gate.
