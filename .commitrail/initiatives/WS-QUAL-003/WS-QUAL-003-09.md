# WS-QUAL-003-09 — Audit the sufficiency-mutation service test family

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: Replace the complete mixed controlled-port sufficiency
  mutation family with cohesive, independently discriminating behavior tests.

## Intent

After PR #373, stop slicing a few assertions into each PR. Audit one complete
service-test family together: human report creation, warning acknowledgement,
manual dispatch, shared authority/lineage guards and replay integrity handling.
The existing suite mixes sequential mutations and permissive fake repositories
inside tests up to 355 lines. A prior failed state can mask a later guard, and
test names claiming commits do not establish transactions through those fakes.

Production behavior, PostgreSQL tests, worker/materialization tests and actual
AUTH/PREP enforcement remain unchanged. This is completion of the controlled-port
family audit, not completion of all PROJECT tests or the v0.1 product.

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
- `backend/scripts/test_lane_catalogue.py` and
  `backend/tests/test_ci_lane_catalogue.py`: exact full-module PROJECT ownership.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: canonical smaller inventory;
  remove obsolete function entries without adding debt or exceptions.

Not allowed: production, migrations, grants, routes, worker implementation,
dependencies, workflow/coverage changes, conftest, real database test deletion,
new runtime semantics, AUTH suspension-race repair, or edits to unrelated tests.

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

## Acceptance criteria

Each parameter below represents an independently failing behavior with one
fresh baseline. Test modules stay below 500 lines; test functions stay below120
lines, with a 75-line target; helpers stay below100 lines.

| Existing proof / required strengthening | Named new proof |
| --- | --- |
| Human wrong kind, missing grant, foreign project; valid project/system decisions | `test_human_authority_requires_matching_grant`, `test_human_authority_accepts_covered_scope` |
| Fixed-service wrong kind/grant; valid fixed decision | `test_setup_authority_requires_fixed_service`, `test_setup_authority_accepts_fixed_decision` |
| Unsupported preparation forwards exact denial; supported handle passes through | `test_prepare_forwards_exact_unsupported_denial`, `test_prepare_returns_handle` |
| Missing material and absent required setup stop before provider/consume | `test_agent_requires_material`, `test_agent_requires_setup_lineage` |
| Retired public service helper remains absent | `test_legacy_run_agent_entry_is_absent` |
| Missing/foreign guide, non-draft guide, absent/replaced snapshot, setup mismatch, required setup absent | `test_lineage_rejects_invalid_context` |
| Fresh locked/unlocked lineage control and exact owner selectors | `test_lineage_resolves_exact_context` |
| Setup custody rejects wrong run/generation, missing row, stale status/step/task; fresh control | `test_setup_custody_rejects_stale_context`, `test_setup_custody_resolves_current_context` |
| Manual dispatch stages stable response and dispatch intent | `test_dispatch_stages_exact_intent` |
| Queue progress does not invalidate committed replay | `test_dispatch_replay_survives_queue_progress` |
| Missing setup lineage/row, completed work, missing material/task identity, stale task ID reject before consume | `test_dispatch_rejects_unusable_setup` |
| Create stages exact human report provenance and stable replay completion | `test_create_stages_human_report` |
| Initial and locked lineage differ: create/ack/dispatch deny before consume | `test_mutation_rejects_changed_locked_lineage` |
| Consume failure cannot produce product effect or complete replay (each command) | `test_mutation_consume_failure_has_no_product_effect` |
| Existing report cannot be created again; lost insert race conceals integrity error | `test_create_rejects_existing_report`, `test_create_conceals_insert_conflict` |
| Acknowledgement binds actor/link/grant/action/decision/note and time | `test_acknowledgement_stages_exact_provenance` |
| Missing/foreign initial report, missing locked report, changed snapshot hash, non-warning status reject before consume | `test_acknowledgement_rejects_invalid_report` |
| Already acknowledged report cannot be changed again | `test_acknowledgement_rejects_repeat` |
| New reservation pending/mismatch dispositions prevent protected mutation for each command | `test_mutation_requires_claimed_reservation` |
| Exact report and acknowledgement replay returns stored response after reauthorization, without another product effect | `test_mutation_recovers_committed_response` |
| Each existing mismatch/pending/resource-digest case rejects independently for create/ack/dispatch | `test_replay_rejects_changed_identity`, `test_replay_rejects_incomplete_record`, `test_replay_rejects_changed_resource_digest` |
| Disappeared reservation after both insert outcomes and failed completion | `test_reservation_disappearance_is_integrity_error`, `test_missing_completion_is_integrity_error` |
| SQL-port valid controls reach return, without claiming database proof | `test_reservation_returns_claimed_row`, `test_completion_accepts_returned_row` |
| Fixed service rejected on create/dispatch/ack public endpoints before actor resolution/product lookup | `test_public_mutation_conceals_service` |

All six old tests' assertions must have a named retained/replacement disposition;
no removed parameter or real-database case. Remaining monolith AST is unchanged.
Consolidate shared setup and duplicate assertions, not distinct failure states.

## Risk and review routing

- L1: authorization-adjacent proof and mutation ordering, no runtime changes.
- Before implementation: focused plan feasibility/guard and oracle review.
- Final: QA/test-delta, security/CI-integrity, architecture/reuse.
- Human focus: whole-family completion, fresh negative fixtures, meaningful
  missing-proof repairs, small modules, no fake database guarantees.

## Evidence

Lead runs the six original tests locally before replacement, then all new
family modules and catalogue tests. Ruff, canonical debt inventory/validation,
Commitrail, Markdown links, stale scans and diff checks must pass. Hosted CI owns
the full suite, PostgreSQL tests, manifest reconciliation and coverage floors.

Run passing controls plus temporary discriminating defects for wrong authority,
masked lineage rejection, omitted replay reauthorization, duplicate replay
product effect, omitted consume, and public service-gate bypass. Defects must
fail assertions, not setup errors; keep probes outside Git. No exhaustive
mutation or complete repository-audit claim. Freeze one clean candidate for the
impact-routed reviews; batch valid findings before replay and hosted rerun.

## Reconciliation

- Current source: main `9b6750fb`, merged fence slice08.
- Next usable boundary: remaining PROJECT submission-policy mutation family;
  later AUTH's recorded concurrency diagnosis before routine decomposition.
- Remaining risks: unrelated PROJECT/worker/database test families and global
  oversized files remain; hosted setup-latency cause is not diagnosed here.
