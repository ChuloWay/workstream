# WS-QUAL-003-10 — Submission-policy mutation proof audit

- Initiative: WS-QUAL-003
- Durable disposition: Complete
- Intended merge outcome: replace the mixed controlled-port manual submission-policy
  test family with small tests that discriminate each retained behavior.

## Intent

Audit production orchestration and its tests together. Preserve real PostgreSQL
rollback, exact reservation contention and concurrent replacement proof. This
change does not implement POL-04A2 or activate another product capability.

## Bounded change

Allowed files:

- This record and `OVERVIEW.md` for the audit disposition.
- `backend/app/modules/projects/schemas.py`: reject empty manual create
  `policy_version` with the same minimum length already required for update's
  successor identity. No other schema behavior or migration change.
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

## Design

Use fresh valid rows per independently failing case and standard mock ports,
not a second fake authorization or replay implementation. Production resource
builders cannot serve as their own expected-fact oracle. Repository query
assertions must inspect exact predicates and bound values, not column names in
the SELECT projection. Mocked queries prove composition only, not PostgreSQL
isolation, uniqueness, row locks, handle binding or transaction rollback.

## Acceptance criteria

| Behavior | Required proof |
| --- | --- |
| Public service denial before lookup; missing/malformed replay keys; malformed snapshot/CAS input | `test_public_routes.py`: exact error and first owner-call/auth non-call where reachable; schema cases independently reject |
| Empty creation version must not enter mutation as a valid policy identity | `test_create_schema_rejects_empty_policy_version`: fails against original schema, passes after the one-field minimum-length repair; normal create remains its positive control |
| Replay recovery still requires the exact covered PM admission lookup | `test_replay_requires_current_pm_admission`: exact permission/project/role filter; missing admission denies before replay or product lookup for create/update |
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

## Risk and review routing

L1: authorization-adjacent proof and CI selection custody. Focused plan
feasibility review precedes implementation. Final reviewers cover QA/test delta,
security, CI integrity, and reuse of fixture/query conventions; documentation
review is limited to this record and overview. No unrelated reviewer fanout.

## Evidence

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

## Paired-audit correction

Create accepted an empty `policy_version` while update required a non-empty
successor. This is a required version identity (canonical data model and policy
uniqueness), not optional display text. The focused repair aligns creation with
the existing successor rule. Its regression must fail against the original
schema. No claim is made that schema validation alone proves database custody.

## Original-proof dispositions

The ten replaced monolith definitions and their independently failing assertions
are reconciled below. Prefixes abbreviate only
`test_submission_artifact_policy_`; all new names are exact.

| Original suffix | Surviving proof / disposition |
| --- | --- |
| `create_update_conceals_service_before_lookup` | `test_public_mutation_conceals_service_before_owner_lookup` (POST/PATCH) |
| `create_rejects_malformed_snapshot_uuid` | `test_create_schema_rejects_malformed_snapshot`; remove false pre-actor claim |
| `create_rejects_invalid_idempotency_before_auth`, `update_rejects_invalid_idempotency_before_auth` | `test_invalid_key_precedes_actor_resolution` (POST/PATCH, absent/malformed); exploding actor override proves non-call |
| `update_rejects_invalid_preconditions` | `test_update_schema_rejects_invalid_precondition` retains all four cases |
| `replay_repository_idempotency_classifies_cross_action_states` | `test_reservation_classifies_existing_exact_row`, `test_reservation_rejects_changed_namespace_facts`, `test_reservation_insert_binds_exact_values`, `test_conflicting_reservation_without_matching_row_is_integrity_error`, `test_namespace_query_binds_exact_selectors`, `test_operation_lookup_uses_exact_operation_predicate`, `test_completion_requires_exact_pending_row` |
| `authority_service_is_flush_only` | `test_replay_delegates_exact_custody_without_transaction_ownership`, `test_replay_requires_active_root_transaction`, `test_invalid_human_replay_facts_never_reach_repository`, `test_fixed_service_replay_preserves_exact_custody`, `test_fixed_service_replay_rejects_changed_custody` |
| `manual_service_executes_authorized_create_and_update` | `test_mutation_stages_exact_policy_provenance`, `test_mutation_binds_exact_prepared_facts`, `test_committed_replay_returns_original_without_mutation`; ordinary no-replay branch is exercised by both real commands |
| `manual_lineage_loads_exact_locked_context` | `test_lineage_loads_exact_owner_context`, `test_missing_lineage_denies`, `test_incompatible_lineage_denies`, `test_warning_acknowledgement_digest_binds_exact_provenance`; exact owner selectors and lock-request order retained |
| `manual_service_fail_closed_guards` | `test_human_authority_requires_covered_grant`, `test_invalid_human_replay_facts_never_reach_repository`, `test_replay_requires_current_pm_admission`, `test_unsupported_prepare_forwards_exact_denial` |

Pruned artificial cases: successful insert followed by the same transaction
losing its inserted row; caller-supplied random create-policy identity where the
real caller derives it internally; isolated no-replay/return-value assertions.
The latter behaviors remain exercised by actual create/update commands and an
exact operation-query predicate test, not deleted coverage with no replacement.
Column-name presence in a SELECT becomes exact WHERE predicates/values and
INSERT conflict behavior. Pending/committed fixture shapes match schema state.

New missing-proof cases establish exact PREP inputs, consume-time absence of
product/replay effects, stale-lock rejection, cross-project/actor/link replay
denial, replay admission, warning provenance and empty-version rejection.
These are controlled-port or pure/schema proofs, not database enforcement.
The schema regression first failed with `DID NOT RAISE ValidationError` against
the original field; only then was the minimum length added.

Retained PostgreSQL limits remain explicit: sequential create replay proves one
policy and the same response, not replay/audit cardinality; concurrent CAS proves
one draft and one superseded row, not the exact loser error/evidence cardinality;
reservation contention proves same-human exact retry, not cross-action races.
No new mocked test upgrades those claims. Those broader database proof gaps
remain for the later transaction-family audit.
