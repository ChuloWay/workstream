# WS-QUAL-003-09 — Audit the sufficiency-mutation service test family

- Initiative: WS-QUAL-003
- Durable disposition: Complete
- Intended merge outcome: Replace the complete mixed controlled-port sufficiency
  mutation family with cohesive, independently discriminating behavior tests.

## Intent

After PR #373, stop slicing a few assertions into each PR. Audit one complete
service-test family together: human report creation, warning acknowledgement,
manual dispatch, shared authority/lineage guards and replay integrity handling.
The existing suite mixes sequential mutations and permissive fake repositories
inside tests up to 355 lines. A prior failed state can mask a later guard, and
test names claiming commits do not establish transactions through those fakes.

Audit tests together with their implementation: remove redundant or impossible
fixtures, retain distinct protection, and fix confirmed defects with discriminating
regressions. This is not completion of all PROJECT tests or the v0.1 product.
The paired audit found missing report-generation validation during warning
acknowledgement. This change also adds that narrow guard and real PostgreSQL
proof that late acknowledgement rejection rolls back all staged effects.

## Bounded change

Allowed:

- This record and `OVERVIEW.md`: family boundary, assertion mapping, findings.
- `backend/tests/test_projects.py`: remove only these six functions and imports
  made unused by their removal:
  `test_sufficiency_mutation_fail_closed_internal_guards`,
  `test_sufficiency_mutation_manual_dispatch_commits_and_replays`,
  `test_sufficiency_mutation_services_commit_human_create_and_acknowledgement`,
  `test_sufficiency_replay_repository_impossible_states_fail_closed`,
  `test_sufficiency_lineage_and_target_guards_fail_closed`,
  `test_public_sufficiency_mutation_conceals_service_before_product_lookup`.
- `backend/tests/projects/sufficiency_mutations/`: `rows.py`, `fixtures.py`,
  `commands.py`, and `test_authority.py`, `test_lineage.py`, `test_dispatch.py`,
  `test_report_create.py`, `test_acknowledgement.py`, `test_replay.py`,
  `test_replay_repository.py`, `test_public_routes.py`.
- `backend/tests/projects/sufficiency_mutations/test_acknowledgement_postgresql.py`:
  real route/transaction rollback proof using existing shared PROJECT fixtures.
- `backend/app/modules/projects/sufficiency_mutation_service.py`: require the
  report generation to equal locked current lineage before continuation reset;
  no other production behavior changes.
- `backend/scripts/test_lane_catalogue.py` and
  `backend/tests/test_ci_lane_catalogue.py`: exact full-module PROJECT ownership
  and token-level coverage-command regression.
- `.github/workflows/backend.yml`: only replace the sufficiency coverage step's
  obsolete selectors with its two exact retained test nodes and all new family
  test modules; preserve both production coverage targets and the 90% floor.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: canonical smaller inventory;
  remove obsolete function entries without adding debt or exceptions.

Not allowed: other production changes, migrations, grants, routes, worker implementation,
dependencies, other workflow changes or coverage weakening, conftest, real database test deletion,
runtime semantics beyond the generation guard, AUTH suspension-race repair,
or edits to unrelated tests.

## Design

Use passive standard mock ports and fresh valid rows for each independently
failing case. Reuse PROJECT's existing settings-isolation fixture. Share only
small row constructors, mock-port setup and thin command invocation; no fake
repository class that implements replay/lifecycle rules or authorization.
Expected request/resource facts must be fixture-owned, not `_caller` or
`_resource` reused as the assertion oracle. Replay fixtures may capture an
initial successful operation as setup, then reset call history; tests must
prove the replay reauthorizes but neither reserves nor repeats the product effect.

Separate service composition from SQL-port failure handling and public-route
concealment. Keep real PostgreSQL/persisted AUTH evidence tests in their existing
locations unchanged. Mock rollback or staged audit counters are not database
atomicity evidence. Do not claim these tests enforce handle/session binding.
Setup-linked acknowledgement validation occurs after consumption and in-memory
acknowledgement changes. Its late rejection tests prove the conflict and absence
of continuation reset/replay completion, not absence of those earlier changes.
`test_acknowledgement_late_conflict_rolls_back` must exercise the real route,
stage acknowledgement, replay and AUTH evidence inside its transaction, then
verify a late context conflict leaves none committed using a fresh DB session.
This is hosted PostgreSQL proof, not a mock rollback assertion. A separate
`test_acknowledgement_rejects_report_generation_mismatch` changes only report
generation, keeps the current run/lineage valid, and must fail against pre-fix
production code. Existing worker/materialization and AUTH handle enforcement
remain unchanged.

Test-value standard: preserve one primary behavior per test; remove duplicates
only with a named surviving proof. Use persisted-valid fixtures except for an
explicit corruption threat. No arbitrary test-count target and no permissive
NoReturn ports. Temporary mutants identify proof gaps, not production defects.

## Acceptance criteria

Each parameter below represents an independently failing behavior with one
fresh baseline. Test modules stay below 500 lines; test functions stay below120
lines, with a 75-line target; helpers stay below100 lines.

| Existing proof / required strengthening | Named new proof |
| --- | --- |
| Human wrong kind, missing grant, foreign project; valid project/system decisions | `test_human_authority_requires_matching_grant`, `test_create_stages_human_report`, `test_acknowledgement_stages_exact_provenance` |
| Fixed-service wrong kind/grant; valid fixed decision | `test_setup_authority_requires_fixed_service`, `test_setup_authority_accepts_fixed_decision` |
| Unsupported preparation forwards exact denial and propagates the NoReturn port's exception unchanged; supported handle passes through | `test_prepare_forwards_exact_unsupported_denial`, `test_mutation_passes_exact_prepared_context` |
| Missing material stops before provider/consume; required setup must resolve | `test_agent_requires_material`, `test_lineage_rejects_invalid_context[required_setup]` |
| Manual route does not invoke agent/materialization; worker composes fresh authority | retained `test_manual_sufficiency_request_never_materializes_or_invokes_agent_inline`, `test_verified_worker_composes_fresh_exact_setup_service_authority` |
| Missing/foreign guide, non-draft guide, absent/replaced snapshot, setup mismatch, required setup absent | `test_lineage_rejects_invalid_context` |
| Fresh locked/unlocked lineage control and exact owner selectors | `test_lineage_resolves_exact_context` |
| Setup custody rejects wrong run/generation, missing row, stale status/step/task; fresh control | `test_setup_custody_rejects_stale_context`, `test_setup_custody_resolves_current_context` |
| Manual dispatch stages stable response and a previously absent task ID; already-queued intent is not mutated | `test_dispatch_stages_exact_intent`, `test_dispatch_preserves_already_queued_intent` |
| Authoritative report blocks dispatch only for the matching setup run/generation | `test_dispatch_rejects_unusable_setup`, `test_dispatch_ignores_unrelated_report` |
| Queue progress does not invalidate committed replay | `test_dispatch_replay_survives_queue_progress` |
| Completed work, missing material/task identity, stale task ID reject before consume | `test_dispatch_rejects_unusable_setup` |
| Create stages exact human report provenance and stable replay completion | `test_create_stages_human_report` |
| Each command forwards fixture-owned exact PREP caller, scope and resource facts | `test_mutation_passes_exact_prepared_context` |
| Initial and locked lineage differ: create/ack/dispatch deny before consume | `test_mutation_rejects_changed_locked_lineage` |
| Consume failure cannot produce product effect or complete replay (each command) | `test_mutation_consume_failure_has_no_product_effect` |
| Existing report cannot be created again; lost insert race conceals integrity error | `test_create_rejects_existing_report`, `test_create_conceals_insert_conflict` |
| Acknowledgement binds actor/link/grant/action/decision/note and time | `test_acknowledgement_stages_exact_provenance` |
| Missing/foreign initial report, missing locked report, changed snapshot hash, non-warning status reject before consume | `test_acknowledgement_rejects_invalid_report` |
| Already acknowledged report cannot be changed again | `test_acknowledgement_rejects_repeat` |
| Setup-linked acknowledgement rejects older run, wrong output report or existing downstream policy without continuation reset/completion | `test_acknowledgement_rejects_invalid_continuation` |
| Report generation must match the current locked run; late rejection rolls back acknowledgement, replay and allowed evidence | `test_acknowledgement_rejects_report_generation_mismatch` (local service), `test_acknowledgement_late_conflict_rolls_back` (hosted PostgreSQL route) |
| Valid setup-linked acknowledgement resets exact enqueue fields and completes replay | `test_acknowledgement_resets_continuation` |
| New reservation pending/mismatch/replayed dispositions prevent protected mutation for each command | `test_mutation_requires_claimed_reservation` |
| Exact report and acknowledgement replay returns stored response after reauthorization, without another product effect | `test_mutation_recovers_committed_response` |
| Each existing mismatch/pending/resource-digest case rejects independently for create/ack/dispatch | `test_replay_rejects_changed_identity`, `test_replay_rejects_pending_record`, `test_replay_rejects_changed_resource_digest` |
| Disappeared reservation after both insert outcomes and failed completion | `test_reservation_disappearance_is_integrity_error`, `test_missing_completion_is_integrity_error` |
| SQL-port valid controls reach return, without claiming database proof | `test_reservation_returns_claimed_row`, `test_completion_accepts_returned_row` |
| Fixed service rejected on create/dispatch/ack public endpoints before actor resolution/product lookup | `test_public_mutation_conceals_service` |

All six old tests' assertions must have a named retained/replacement disposition;
no real-database case is removed. Remaining monolith AST is unchanged.
Consolidate shared setup and duplicate assertions, not distinct failure states.

## Risk and review routing

- L1: authorization-adjacent proof, transaction rollback and a narrow generation
  consistency repair; no new capability or authority.
- Before implementation: focused plan feasibility/guard and oracle review.
- Final: QA/test-delta, security/CI-integrity, architecture/reuse.
- Human focus: whole-family completion, fresh negative fixtures, meaningful
  missing-proof repairs, small modules, no fake database guarantees.

## Evidence

Lead runs the six original tests locally before replacement, then the eight
controlled-port family modules and catalogue tests. The new PostgreSQL module
runs only in hosted CI. Ruff, canonical debt inventory/validation,
Commitrail, Markdown links, stale scans and diff checks must pass. Hosted CI owns
the full suite, PostgreSQL tests, manifest reconciliation and coverage floors.
The workflow regression must assert exact pytest selector tokens: the retained
worker-composition and setup-service-adoption nodes plus every replacement test
module, with no obsolete `-k` expression. It must retain both per-file coverage
targets and the existing 90% threshold.

Run passing controls plus temporary discriminating defects for wrong authority,
masked lineage rejection, omitted replay reauthorization, duplicate replay
product effect, omitted consume, and public service-gate bypass. Defects must
fail assertions, not setup errors; keep probes outside Git. No exhaustive
mutation or complete repository-audit claim. Freeze one clean candidate for the
impact-routed reviews; batch valid findings before replay and hosted rerun.

## Reconciliation

The six former mixed controlled-port tests are replaced by 37 named tests in
nine behavior modules, including one real PostgreSQL transaction test. Their
971 lines leave the monolith; the replacement family and three passive support
modules total 1,357 lines. This is deliberately
not a net source-count reduction: independent negative controls and missing
PREP, continuation and route proof replace compact but masked multi-behavior
tests. The largest new module is 210 lines; the longest new test is 74 lines.
All retained monolith definitions, including PostgreSQL tests, remain
AST-identical. No real database case or coverage floor is removed.

The original six tests passed before replacement. Local controlled-port and
catalogue execution is separate from hosted PostgreSQL proof. Out-of-tree probes
begin from passing controls and detect
missing-grant acceptance, ignored foreign-guide lineage, omitted replay
reauthorization, duplicate replay product effect, omitted consumption, and
bypassed public service rejection at assertions, not setup failures.

QA's escaped mutants exposed three additional proof gaps: a returning fake for
the NoReturn denial port, project-only creation/acknowledgement provenance and
unobserved authoritative-report dispatch rejection. The corrected cases prove
exception identity propagation, both system/project provenance, each independent
completed-output/terminal guard, matching versus unrelated reports and assignment
of a previously absent task ID. Five additional defects now fail at assertions;
those probes do not modify shipped production code or stand in for hosted
PostgreSQL evidence. The later paired audit independently reproduced a real
missing report-generation guard; its regression fails against the pre-fix
implementation, not merely a hypothetical mutant.

The paired audit prunes thirteen redundant or impossible expanded cases:

- Human positive helper cases are covered by both system/project command
  provenance tests; successful PREP pass-through is covered by each command's
  exact PREP-context test, now with exact preparation call count.
- Required-setup helper output cannot be absent after successful required
  lineage resolution; the real lineage rejection and locked selector controls
  replace those artificial agent/dispatch fixtures. An unused method-name
  absence assertion is replaced by the retained route/worker behavior tests.
- Seven schema-impossible incomplete replay combinations become three valid
  pending rows, one per command. Identity/resource mismatch guards remain.
- A missing referenced setup row contradicts the persisted FK. A mocked current
  setup generation change is replaced by the actual report-generation defect.
  The older-run case now returns the row actually identified by the report.
- Helper-only PREP non-call assertions are removed because those helpers never
  receive the PREP port; command-level denial ordering remains. Public-route
  lookup spies now target the first lookup used by each route.

Two new cases add unique service and transaction proof for the confirmed defect.
The PostgreSQL case commits the inconsistent report generation, observes real
staged acknowledgement/replay/AUTH evidence before rejection, and compares all
report/setup columns and bounded evidence counts in a fresh session afterward.
No fake rollback or swallowed denial is accepted as proof.

Plan review corrected the stale focused coverage selector, missing `replayed`
reservation rejection, setup-linked acknowledgement coverage and explicit PREP
fact mapping. Structural inventory removes three oversized function entries and
adds none. The workflow selects the two retained nodes plus all replacement
modules; its targets and threshold remain unchanged. This disposition records
the intended merged audit boundary, not transient CI or approval state.

- Current source: main `9b6750fb`, merged fence slice08.
- Next usable boundary: remaining PROJECT submission-policy mutation family;
  later AUTH's recorded concurrency diagnosis before routine decomposition.
- Remaining risks: unrelated PROJECT/worker/database test families and global
  oversized files remain; hosted setup-latency cause is not diagnosed here.
