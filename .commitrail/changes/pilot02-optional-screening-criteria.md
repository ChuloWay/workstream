# PILOT-02 — Preserve optional task criteria through screening

- Initiative: `None`
- Durable disposition: `Complete`
- Intended merge outcome: Imported briefs without task-local acceptance criteria can complete authorized single or bulk screening and release under their locked project guide.

## Intent

Issue [#489](https://github.com/Flow-Research/workstream/issues/489), F-021,
identifies a contradiction in the delivered import journey. The canonical JSON
schema, TASK import parser, persisted Task and public projections permit omitted
or null `acceptance_criteria`. `TaskService._validate_task_contract_fields`
nevertheless requires it during SCREEN. Both authorized single and bulk SCREEN
call this owner. The project guide supplies the governed requirements; optional
task-local criteria must not be fabricated to pass screening.

## Bounded change

Allowed files:

- `backend/app/modules/tasks/service.py`: remove only the optional criteria
  presence requirement from the canonical screening validation.
- `backend/tests/test_tasks.py`: replace the obsolete missing-criteria rejection
  assertion with real missing/blank required-title/description protection.
- `backend/tests/tasks/test_task_batch_transitions.py`: public verified JSON
  import to single/bulk SCREEN and RELEASE with omitted, null and supplied
  criteria; assert retained content, policy locks, replay and actual stored state.
- `backend/tests/tasks/test_task_import_contract.py`: retain explicit type and
  length validation for supplied optional criteria.
- `cli/tests/integration/test_task_batch_public_api.py`: extend the existing
  real 200-row CSV/CLI journey with absent optional criteria without removing
  its byte-custody, replay or revoked-authority assertions.
- `docs/spec_chunk_4_task_queue_assignment.md`, `docs/roadmap_status.md`: clarify
  optional task criteria across SCREEN/RELEASE and record the delivered repair.
- `docs/operations_queue_policy.md`, `docs/operations_project_operating_manual.md`,
  `docs/operations_operator_workflow.md`, `docs/product_first_user_flows.md`: align
  current operator/readiness guidance with optional task-local criteria and
  mandatory guide-governed requirements.
- `docs/spec_chunk_8_submission_artifact_policy_checkers.md`,
  `docs/template_project_guide.md`, `docs/architecture_checker_framework.md`,
  `docs/template_checker_policy.md`, `docs/architecture_data_model.md`:
  distinguish optional task-local criteria
  from mandatory guide-level acceptance requirements, including the retired
  checker record's misleading current-screening statement.
- `.commitrail/changes/pilot02-bulk-transitions-cli.md`: reconcile only its
  current outcome paragraph with this correction; retain historical evidence.
- `backend/tests/authorization/task_reads/test_visibility.py`,
  `backend/tests/tasks/test_task_detail.py`,
  `backend/tests/tasks/test_work_context.py`: isolate each owned-state visibility
  fixture in its own publicly created/claimed task, retaining all states,
  audiences and negative cases without fabricating expiry transitions.
- `backend/scripts/test_lane_catalogue.py`: move only the three non-database
  architecture inspection modules from the overloaded schema lane into the
  existing shared-foundation partition.
- `backend/tests/test_ci_lane_catalogue.py`: replace their obsolete schema-only
  placement expectation with explicit shared-family/exact-once node proof;
  retain all other inventory, schema/admin/reset and completeness assertions.
- `docs/operations_backend_testing.md`: describe that bounded placement repair.
- This change record.

Prohibited: new routes, new optionality flags, compatibility paths, policy
defaults, AUTH/grant changes, transaction or lock-order changes, imports or
cross-owner dependencies, migrations, retained-data edits, checker changes,
PILOT-08 revision work, selective test omission, timeout/workflow changes, or weakened safeguards.
The only CI placement change is the three-module move explicitly listed above.

## Acceptance criteria

Use the existing SCREEN owner. Retain required title/description validation,
approved active-guide resolution, exact frozen-policy stamping, installed-plan
validation at RELEASE, per-task authority/audit, replay and caller atomicity.
No import normalization, placeholder criteria or second screening path is needed.

- Omitted and explicit-null criteria survive verified public JSON import,
  single/bulk SCREEN and RELEASE, with no fabricated stored text.
- Supplied criteria remain exact, and malformed/oversized supplied values still
  reject at the import contract. Blank title/description still reject SCREEN.
- Positive journeys retain exact locked policy identities and idempotent
  replay; existing invalid-guide, authority denial and late-write rollback
  regressions remain selected and pass.
- The existing built CLI/real HTTP/PostgreSQL/MinIO 200-row journey passes with
  missing optional criteria. No route or authorization replacement is added.
- The new public regression fails on the unchanged pre-fix validator at SCREEN,
  then passes with the repair. Local fixtures establish active-guide prerequisites;
  this is import-through-release proof, not a hosted whole-product pilot.

## Risk and review routing

- Risk class: `L1` — bounded task-readiness correction and CI placement repair.
- Required reviewers: combined security/architecture and QA/test-delta/docs;
  CI integrity for the placement repair; plan review before implementation,
  exact clean candidate review after proof.
- Human review focus: only optional task-local criteria become optional at
  SCREEN; required instructions, authorization, lineage and atomicity remain.
- Verification: frozen backend environment; focused parser tests, public
  PostgreSQL/MinIO single/bulk journeys and existing refusal/rollback tests;
  built CLI native journey; scoped Ruff, module boundaries, stale-wording,
  Markdown links, Commitrail and full hosted Backend/CLI/Agent Gates checks.
  Preserve original test assertions except the explicitly obsolete criteria
  rejection behavior. Coverage remains diagnostic.

## Evidence

The new single and bulk public regressions were executed against the unchanged
validator at test-only commit `41ae10a28`. Both reached SCREEN after successful
verified import and failed specifically with HTTP 422, `task missing required
fields: acceptance_criteria`. PostgreSQL/MinIO cleanup completed. An earlier
five-minute attempt timed out during fixture work and is not counted as proof.

The corrected candidate runs these same regressions, required-instruction and
authority/rollback controls, and the existing built-CLI journey. Exact-head
results and review/check disposition belong in the PR.

## Necessary CI placement repair

The unchanged schema lane timed out twice at approximately 1,202 seconds, with
582/669 and 576/669 nodes completed, no assertion failure and successful cleanup.
None of this change's original test modules belongs to that lane. The earlier
successful baseline wrapper took 1,181.726 seconds against the unchanged
1,200-second deadline. Repeated retries are not the repair.

The CI plan review preferred a separate placement PR because the workload
defect predates this product change. This record retains the bounded repair
here to complete the requested full verification without another prerequisite
merge. It changes placement only, not screening scope or CI requirements.

Move `tests/test_artifact_architecture.py`,
`tests/architecture/test_module_boundaries.py` and
`tests/architecture/test_test_structure_boundary.py` to the existing shared
partition. They inspect repository structure without database fixtures. Baseline
setup/call/teardown evidence totals approximately 205 seconds for those modules;
the existing node hash assigns about 8/103/94 seconds to shared A/B/C. Measured
receiving job walls were about 596/905/690 seconds. Module-scoped setup can repeat
across processes, so those estimates require final-head hosted proof.

Keep the same 13 lanes, complete test inventory, canonical exact-node hash,
PostgreSQL/MinIO ownership, schema/admin/reset tests, timeout, coverage collection
and aggregate validation. Prove every moved node has exactly one shared owner;
no baseline test or assertion is removed. PR #566 overlaps the catalogue files
but is not a dependency; subsequent reconciliation must retain both changes.

## Reconciliation

Base: main `5f026b7f2563617a230f320d8e9b536d8ac92644`, including merged #569.
The separate agent owns remaining PILOT-08 corrections; this change touches
only the screening validator and its proof, not revision behavior. Reconcile
shared TASK/spec/roadmap edits before merge. No local spreadsheet exports are
present in this worktree. Hosted first-layer verification remains #555 after
the known screening and revision corrections land.

## External documentation correction

The review of `c4e918306` found two remaining contradictory statements: the
checker record described criteria as a current screening prerequisite, and the
guide template listed them as a required task field. Both now explicitly permit
omitted/null task-local criteria while retaining mandatory guide-level acceptance
requirements. The checker record retains its historical status and links current
contracts. Runtime code and tests are unchanged. The roadmap already records this
optional-criteria behavior; no additional capability or roadmap change is needed.
The linked current checker framework also qualifies missing acceptance
requirements as guide-level, not omitted optional task-local criteria.

The linked-document review also found current policy-template and data-model
passages still presenting the removed criteria-presence checker as selectable.
Their affected POST contract sections now describe the existing approved external
bindings and explicitly preserve optional task-local criteria. Retained predecessor
body provenance remains documented; no runtime or stored data changes are made.

## Visibility fixture correction discovered during verification

The fresh documentation-head CI run exposed an existing unordered-state fixture:
`test_task_read_contributor_visibility` reused one claimed task across nine
states, occasionally attempting `needs_revision -> ready` without an expiry
receipt. PostgreSQL correctly rejected both public-read parametrizations.
`test_task_detail_owned_states` and `test_work_context_owned_state_matrix` failed
with the same pattern in the task-B lane. These tests inspect
visibility, not lifecycle transitions. Use one publicly created/claimed task per
state, deliberately visit `needs_revision` before `ready`, and retain exact
persisted assignment/owner checks, all nine states and every negative case.
No production guard, lifecycle behavior, test selection or timeout changes.
Validate all four affected cases with real PostgreSQL/MinIO and rerun hosted CI.
The separate project-C lane hit its unchanged deadline with 459/470 completed
and no assertion failure; its previous successful run took 1,149 seconds.
