# WS-QUAL-003-10 — Submission-policy mutation proof audit

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended outcome: replace the mixed controlled-port manual submission-policy
  test family with small tests that discriminate each retained behavior.

## Intent and scope

Audit production orchestration and its tests together. Preserve real PostgreSQL
rollback, exact reservation contention and concurrent replacement proof. This
change does not implement POL-04A2 or activate another product capability.

Allowed files:

- This record and `OVERVIEW.md` for the audit disposition.
- `backend/tests/test_projects.py`: replace the controlled-port family from
  `test_submission_artifact_policy_create_update_conceals_service_before_lookup`
  through `test_submission_artifact_policy_manual_service_fail_closed_guards`,
  including their decorators, and remove newly unused imports only.
- `backend/tests/projects/submission_policy_mutations/`: passive row/port support
  and separate public-route, lineage, authority, command, replay and repository
  behavior tests. No module reaches 500 lines; tests target 75 lines and must
  remain below 120; helpers below 100.
- `backend/scripts/test_lane_catalogue.py`,
  `backend/tests/test_ci_lane_catalogue.py`, `.github/workflows/backend.yml`:
  register the new modules in the canonical PROJECT lanes and replace only the
  obsolete submission-policy supplemental coverage selectors. Preserve both
  production targets, append semantics and the 90% threshold. No PostgreSQL test
  enters that supplemental command without a provisioned Workstream database.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: reconcile the canonical reduced
  inventory, without new debt entries, exceptions or weakened limits.

Prohibited: production changes without a reproduced defect and explicit repair
scope added here; migrations, public interfaces, activation, grants, agent/worker
implementation, other test families, fixture-global changes, coverage weakening,
local full-suite/PostgreSQL execution, and deletion of real database tests.

## Design and acceptance-to-proof mapping

Use fresh valid rows per independently failing case and standard mock ports,
not a second fake authorization or replay implementation. Production resource
builders cannot serve as their own expected-fact oracle. Repository query
assertions must inspect exact predicates and bound values, not column names in
the SELECT projection. Mocked queries prove composition only, not PostgreSQL
isolation, uniqueness, row locks, handle binding or transaction rollback.

| Behavior | Required proof |
| --- | --- |
| Public service denial before lookup; missing/malformed replay keys; malformed snapshot/CAS input | `test_public_routes.py`: exact error and first owner-call/auth non-call where reachable; schema cases independently reject |
| Covered system/project PM provenance and exact PREP action/caller/scope/resource | `test_commands.py`: real create/update orchestration and fixture-owned expected facts; returned handle identity preserved |
| Consume denial and changed locked lineage precede replay reservation/product effects | `test_commands.py`: observe empty product/replay call history inside consume and assert non-calls after denial; independent create/update cases |
| Replacement preserves predecessor linkage and completes exact replay response | `test_commands.py`: compare staged successor, supersession selector and response; no claim of commit |
| Committed replay returns original response without new mutation; identity/digest/pending mismatches deny | `test_replay.py`: real replay classifier, schema-valid committed/pending rows, exact stored response and no repeat product effect |
| Project/guide/snapshot/setup/report/predecessor guards and lock selectors | `test_lineage.py`: exact locked/unlocked selectors and fresh invalid controls, including report generation and warning acknowledgement provenance |
| Invalid human authority, unsupported PREP and malformed human/service replay custody | `test_authority.py`: narrow independent guards; unsupported denial raises by default and propagates exact exception |
| Root transaction required; replay delegation is flush-only | `test_authority.py`: active root control and absent/inactive/nested failures; exact delegated facts, no service commit/rollback |
| Reserve claimed/pending/committed/mismatched; lost rows; failed completion | `test_repository.py`: fresh records, bound query values and null-safe predicates, no swallowed errors |
| Persisted replay and rollback/concurrent CAS remain protected | Retain `test_submission_artifact_policy_replay_postgres_converges_exact_reservations`, `test_submission_artifact_policy_create_exact_idempotency_replay_is_stable`, `test_submission_artifact_policy_create_fault_rolls_back_atomic_boundary`, `test_submission_artifact_policy_update_fault_rolls_back_replacement`, `test_submission_artifact_policy_update_concurrent_cas_creates_one_successor` unchanged; hosted execution |

Every original assertion needs a named replacement or stronger retained proof.
Remove repetitive orchestration only, not independent failure boundaries. A
source-count or case-count reduction is not acceptance evidence. Preserve the
AST of every retained monolith definition.

## Risk, review and verification

L1: authorization-adjacent proof and CI selection custody. Focused plan
feasibility review precedes implementation. Final reviewers cover QA/test delta,
security, CI integrity, and reuse of fixture/query conventions; documentation
review is limited to this record and overview. No unrelated reviewer fanout.

Local: original controlled-port nodes, then the new controlled-port modules and
catalogue tests; Ruff; structural inventory/validation; Commitrail; stale scans;
Markdown links; diff check. Use passing controls and out-of-tree counterexamples
for omitted consume, stale lineage, incorrect PREP facts and replay duplication.
The exact named test must fail at the behavioral assertion, not fixture setup.

Hosted CI owns full canonical collection, PostgreSQL/MinIO, manifest comparison,
global coverage and both protected submission-policy source-file floors. Compare
removed nodes with named new/retained protection and report actual source/test
deltas. A green coverage percentage does not establish complete safety proof.

Human review focus: meaningful proof instead of more coverage-only cases; no
mock rollback or scheduling-only race claim; no weakened guards; bounded modules.
Next after this family remains AUTH's recorded concurrency diagnosis, not another
automatic implementation in the same PR.
