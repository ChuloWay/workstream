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
- `.commitrail/changes/pilot02-bulk-transitions-cli.md`: reconcile only its
  current outcome paragraph with this correction; retain historical evidence.
- This change record.

Prohibited: new routes, new optionality flags, compatibility paths, policy
defaults, AUTH/grant changes, transaction or lock-order changes, imports or
cross-owner dependencies, migrations, retained-data edits, checker changes,
PILOT-08 revision work, CI selection/timeout changes, or weakened safeguards.

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

- Risk class: `L1` — bounded task-readiness contract correction.
- Required reviewers: combined security/architecture and QA/test-delta/docs;
  plan review before implementation, exact clean candidate review after proof.
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

## Reconciliation

Base: main `5f026b7f2563617a230f320d8e9b536d8ac92644`, including merged #569.
The separate agent owns remaining PILOT-08 corrections; this change touches
only the screening validator and its proof, not revision behavior. Reconcile
shared TASK/spec/roadmap edits before merge. No local spreadsheet exports are
present in this worktree. Hosted first-layer verification remains #555 after
the known screening and revision corrections land.
