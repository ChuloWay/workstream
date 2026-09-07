# WS-QUAL-003-13 — Admin access lifecycle proof audit

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: Eight mixed bootstrap/admin-access tests become
  bounded behavior proofs with a retained signed-token API journey and exact
  PostgreSQL concurrency/rollback custody.

## Intent

Continue the behavior-first audit without treating test count or coverage as
the goal. The human asked to compare unit and end-to-end proof: keep a small
representative connected journey, use PostgreSQL for persistence/transaction
claims, and use focused tests for independent variations. This is one PR with
reviewed commits, not a separate planning PR followed by tiny cleanup PRs.

## Current behavior

Baseline is main `0e34911be4cdc25b3ec79dbcb097b62181958304` (PR379).
`backend/tests/test_auth.py` retains 23 named tests. Eight selected tests occupy
the bootstrap/admin-access family; fifteen other test bodies remain unchanged.
The 1,040-line `test_signed_tokens_bootstrap_and_admin_grant_lifecycle` mixes
signed-token admission, bootstrap, reads, concealment, fault injection, grant
issue/revoke, scope and replay. Its final event totals depend on the entire
history instead of identifying each mutation's effects.

`test_admin_bootstrap_replay_and_cross_revoke_are_concurrency_safe` combines
bootstrap, timestamp ordering, same-key recovery, distinct-key duplication,
cross-revocation and both revoke-versus-issue orders. Several barriers establish
arrival but do not observe the actual database wait. The separate admin-read
race checks any blocker of the transition PID, not the exact reader PID; it
resets shared lifecycle rows between cases with disabled user triggers.

Production owners are `scripts/bootstrap_access_administrator.py`,
`authorization/admin_service.py`, `authorization/repository.py`, shared
authority mutation/PREP and route composition, plus ACTORS read/touch owners.
The canonical specification is `docs/spec_authorization_service.md`, especially
Bootstrap And Final-Administrator Safety. Bootstrap takes the control-row lock,
validates an active human/link, and atomically stages grant/control/event.
Later attempts produce audited conflicts; ordinary token role claims do not
grant Workstream administrator authority.

These are observed proof weaknesses, not established production defects.

## Bounded change

### Allowed

- This record and `WS-QUAL-003/OVERVIEW.md` for durable audit disposition.
- `backend/tests/test_auth.py`: remove only the eight named tests below, move
  its exact `auth_database_env` fixture to shared non-test support, re-import
  it for unchanged consumers, and remove only demonstrably dead imports.
- `backend/tests/authentication/fixtures.py`: own the unchanged database fixture.
- New `backend/tests/authorization/admin_access/` package with `__init__.py`,
  `conftest.py`, `support.py`, `fixtures.py`, `fault_support.py`,
  `concurrency_support.py`, `read_support.py` and the test files below.
  Split support further only by a named behavior and record the scope correction
  before implementation; no arbitrary helper framework.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json` and new assertion map
  `.ci/auth-boundaries/assertion-maps/WS-QUAL-003-13.json`: reconcile actual
  inventory without new/grown or rewritten-same-size debt.
- `backend/scripts/test_lane_catalogue.py` and
  `backend/tests/test_ci_lane_catalogue.py`: register moved tests in existing
  lanes and prove no omission. Preserve unrelated product registrations.

### Not allowed

No production, migration, public contract, runtime authority, workflow,
threshold, timeout, dependency, or feature change. No whole-suite local run or
local PostgreSQL execution. No deletion justified by line count or coverage.
No edits to the product worktree. No re-audit of completed PR379 families.
Do not rewrite the other fifteen authentication tests or the 163-test AUTH
monolith. Read them as possible survivors, not editable scope.

## Design and decisions

Inventory every original assertion and materially distinct loop/parameter case
before removal. Map it to a surviving named assertion, or explain its redundant
protection and stronger existing owner test. Hashes demonstrate custody, not
semantic equivalence. No deletion decision is pre-approved by this plan.

Keep a short signed-token → first access → local bootstrap → grant → observed
role → revoke → observed role-removal journey through ASGI and real PostgreSQL.
Call it API composition, not deployed-network/worker E2E. Use strict reusable
setup for the other tests instead of replaying every previous behavior. Setup
must use real owners or valid fresh rows and must fail promptly on invalid
preconditions. Faults are test-local and installed only after setup.

Keep each new file below 500 lines, tests at most 120 and helpers at most 100.
Do not hide the old 1,040-line scenario in a helper. Separate meaningful failure
cases; do not multiply equivalent parameter combinations for coverage.

Reuse `auth_concurrency_support.wait_for_named_database_lock` with exact waiter
and blocker PIDs. Capture session PIDs before each claimed lock; retain the real
owner call. Hold the winner until the observer proves the contention. A waiter
that finishes early is failure, not success. Each harness owns cancellation,
task joining and hook restoration in `finally`; the observer uses its existing
fresh AUTOCOMMIT connection. No sleep is proof of serialization.

Give each admin-read lifecycle case fresh valid identities/grants. The actual
profile/link transition may use direct SQL as the existing lock test does, but
keep triggers enabled; it proves read/row-lock protection, not lifecycle API
orchestration. Grant revocation keeps the real HTTP command. Do not disable
triggers to restore shared fixtures between cases.

For commit-failure tests, inspect actual staged grant/state and audit effects
before raising, then inspect fresh-session state after rollback. Assert issue,
revoke and read failures independently; evidence-denial tests must identify
whether the fault happens before staging or after it. Scope event assertions
by exact operation/resource and link success to invalidation, not global totals.
Keep response concealment assertions independent of internal evidence assertions.

## Source selection and destinations

All sources below are the exact functions in baseline `backend/tests/test_auth.py`.
Destination paths below are relative to `tests/authorization/admin_access/`.

| Original function | Disposition / destination |
|---|---|
| `test_signed_tokens_bootstrap_and_admin_grant_lifecycle` | Audit all assertions; retain representative `test_api_journey.py`; separate `test_bootstrap_postgresql.py`, `test_admin_reads_postgresql.py`, `test_grant_api_postgresql.py`, `test_failure_atomicity_postgresql.py` |
| `test_bootstrap_command_manifest_matches_the_active_catalogue` | Retain exact principal/action/permission proof in `test_bootstrap_cli.py` |
| `test_bootstrap_cli_preserves_committed_outcome_when_engine_cleanup_fails` | Retain command-output proof; strengthen exact actor forwarding and cleanup custody |
| `test_bootstrap_cli_does_not_relabel_internal_type_error_as_invalid_request` | Retain private infrastructure-failure mapping |
| `test_bootstrap_cli_rejects_arguments_without_echoing_them` | Retain distinct malformed arguments; assert neither stdout nor stderr leaks supplied data and execution is not entered |
| `test_bootstrap_cli_reports_interrupt_and_pre_outcome_cleanup_failure` | Split interrupt from infrastructure/cleanup failure into independent command cases |
| `test_admin_bootstrap_replay_and_cross_revoke_are_concurrency_safe` | Split `test_grant_concurrency_postgresql.py` and `test_timestamp_concurrency_postgresql.py`; preserve each distinct operation/order and replace arrival-only claims with exact custody |
| `test_actor_admin_reads_hold_caller_and_grant_locks_through_disclosure` | `test_read_concurrency_postgresql.py`; retain profile/link × suspend/deactivate/link-revoke/grant-revoke cases with exact blocker, independent fresh setup and denied subsequent disclosure |

## Acceptance criteria and named future proof

Every row is a future proof requirement, not an executed result. All database,
API and concurrency tests below run in hosted CI only; command tests are local.
Parameter cases must remain independently identifiable in final assertion map.

| Behavior | Future proof name | Required observation |
|---|---|---|
| Connected signed authentication and grant lifecycle | `test_signed_admin_grant_journey` | Real verifier, API, PostgreSQL; target role appears then disappears after revoke |
| External role does not bootstrap authority | `test_token_role_cannot_read_authorization_catalogue` | Valid signed token with elevated role claim, denied protected read |
| Dry run is non-mutating | `test_bootstrap_dry_run_leaves_control_grants_and_events_unchanged` | Fresh DB control/grant/event snapshots before and after |
| Completed bootstrap is irreversible | `test_later_bootstrap_returns_audited_original_grant_conflict` | Original grant/control unchanged; exact conflict evidence |
| Bootstrap principal metadata is exact | Existing manifest test name | Literal action, permission and system principal |
| CLI outcome survives cleanup failure | Existing committed-outcome test name | Exact actor/mode forwarded; one output; cleanup attempted |
| CLI internal errors stay private | Existing TypeError test name | Infrastructure failure, no private exception text |
| Malformed CLI arguments do not execute | Existing arguments test name | Strict forbidden `_run`, bounded stdout and empty stderr |
| Interrupt is distinct | `test_bootstrap_cli_reports_interrupt` | Closed coroutine, interrupted output and cleanup attempt |
| Pre-outcome failure cannot claim success | `test_bootstrap_cli_reports_pre_outcome_cleanup_failure` | Infrastructure output on both failures |
| Admin reads conceal private fields | `test_admin_read_projects_only_public_fields` | Actual stored private sentinel values absent from response/logs; exact public fields |
| Admin read observes only caller | `test_admin_read_touches_caller_not_target` | Seeded old timestamps, independent caller/target snapshots |
| Read evidence has exact request/grant/target | `test_admin_read_records_exact_authorization_provenance` | Stored allow event matches request/correlation and matched grant |
| Missing admin target has no success effects | `test_missing_admin_target_has_concealed_response_and_no_success_effect` | Equal concealed response; timestamps and success evidence unchanged |
| Read faults cannot leak successful effects | `test_admin_read_failure_rolls_back_staged_effects` | Separate profile/link × evidence/lookup/touch/commit cases with stage-appropriate assertions |
| Grant issue/revoke faults roll back | `test_grant_mutation_commit_failure_rolls_back` | Separate operations; real staged state/event observed before fault, fresh DB restored afterward |
| Grant recovery is exact | `test_grant_mutation_exact_replay_has_one_effect` | Issue/revoke stable response, one persisted operation and linked evidence |
| Replay mismatch does not mutate | `test_grant_mutation_mismatch_preserves_product_state` | Separate issue/revoke mismatch; bounded denial evidence distinguished from forbidden success |
| Distinct duplicate differs from replay | `test_distinct_operation_duplicate_grant_is_conflict` | New key, same target/role, one grant |
| Actor eligibility denial is concealed | `test_ineligible_grant_targets_share_missing_response` | Real service/suspended/no-active-link targets and genuinely absent control |
| Project audit reads cannot cross scope | `test_project_auditor_reads_only_granted_project` | Two persisted projects, exact selected rows; foreign request denied |
| Audit authority cannot mutate | `test_audit_authority_cannot_issue_grant` | Valid active auditor; mutation denied without grant |
| Read query and grant request validation | `test_invalid_admin_request_is_bounded` | Preserve individually mapped original invalid field/cursor/selector cases |
| Concurrent bootstrap has one winner | `test_concurrent_bootstrap_has_one_persisted_winner` | Two sessions, exact control-lock wait, grant/control/success event and losing conflict |
| Same-key concurrency recovers | `test_concurrent_same_key_grant_returns_one_result` | Exact reservation wait, matching outputs, one grant and evidence pair |
| Distinct-key concurrency cannot double issue | `test_concurrent_distinct_keys_create_one_active_grant` | Exact control wait, 201/409, one persisted grant |
| Cross-revoke retains effective administrator | `test_cross_revoke_retains_one_effective_admin` | Exact control wait, one revoke and one denied caller, one effective surviving administrator |
| Issue/revoke follows serialized authority | `test_issue_against_revocation_obeys_lock_order` | Both winner orders independently; exact waiter/blocker, exact permitted/forbidden grant and events |
| Older observation cannot regress timestamps | `test_older_read_cannot_regress_committed_observation` | Ordered real requests/commits, captured newer timestamps, monotonic final stored values |
| Read holds exact authority through disclosure | `test_admin_read_blocks_exact_authority_transition` | Eight cases with exact reader blocker; later revoked caller denied without timestamp/success effects |

Any additional original assertion not enumerated in the table must acquire its
own named survivor in the exact assertion map before the source is removed;
the table is not permission to discard field, self-protection or pagination proof.

## Risk and review routing

- Risk class: L1 (authorization proof; no runtime change).
- Plan and implementation: combined QA/test-delta and focused security review.
- Implementation shared-file custody: CI integrity; docs only for material
  reconciliation. Reuse review only if support extraction introduces a new
  abstraction rather than using existing owners. No blanket reviewer fanout.
- Human review focus: real journey retained; no mock downgrade; exact stage
  and database lock proof; no arbitrary deletions or coverage-only additions.

## Evidence

Local: focused `test_bootstrap_cli.py` (future file), Ruff on changed Python,
`tests/test_ci_lane_catalogue.py`, existing structural-ledger/assertion-map
validation, root Commitrail/Markdown/stale scans and `git diff --check`.
Collection only may enumerate all moved cases but never claims PG execution.
Hosted: every Backend lane and aggregate, preserved coverage floors, full node
manifest with zero skips/deselections, isolated PostgreSQL/MinIO cleanup.
Record measured suite cost rather than promising an arbitrary reduction.

Before final review, compare the fifteen unselected test bodies by AST, map
every original assertion, and probe at least one real lock-observer omission,
one rollback early-failure false proof, and one CLI privacy/dispatch defect.
Removing the intended guard must fail the named regression at its assertion,
not fail fixture setup. All full database/coverage custody stays hosted.

## Reconciliation

- Product PR377 shares lane catalogue and debt ledger, not this selected test
  family. Preserve its registrations/debt corrections when integrating main;
  do not edit its worktree, workflow, root fixture or product implementation.
- Next usable boundary: service-actor provisioning and profile/link lifecycle
  matrices in the remaining authentication monolith, then remaining AUTH owners.
- Remaining risks: new isolated cases may increase fixture cost; final hosted
  timings and genuine duplicate-survivor review must evaluate that tradeoff.
