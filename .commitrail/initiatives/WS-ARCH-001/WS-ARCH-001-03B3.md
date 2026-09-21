# ARCH-03B3 — Hidden management and operational task queues

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: TASK supplies separate bounded project management and operational queue facts through its existing repository; public access remains ARCH-03C.

## Intent

Continue the remaining ARCH-03B queue boundary after merged 03B2 without
inventing a new queue subsystem. Project managers need to discover draft and
assigned work as well as ready work. Operators need bounded status facts without
contributor content. Both future callers must authorize their exact project
before invoking these hidden reads; selecting a project is not authority.

## Current behavior

Main `94691737` includes CP08 lineage, 03B1 historical project display and 03B2
hidden contributor-ready queue facts. `TaskRepository.read_ready_tasks` has one
project-scoped scalar query and real PostgreSQL pagination/transaction tests.
No management or operations collection read exists. Existing task detail,
locked-context and submission reads still have older role paths; those are
separate projection/cutover work, not consumers of this queue. No existing queue
route or authorization is replaced or activated here. Migration head is
`0024_task_policy_lineage`. The only open PR inspected is CI impact reporting
(#410), with no overlapping product implementation.

## Bounded change

### Allowed

- `backend/app/modules/tasks/api/ready_queue.py`, API exports, and a focused
  `api/management_queue.py` contract for the two explicit projections.
- `backend/app/modules/tasks/repository.py`: two hidden reads on the existing
  owner and shared TASK-specific project/cursor query mechanics.
- `backend/tests/tasks/test_ready_queue.py` and `test_management_queue.py`;
  exact lane registration and catalogue assertion.
- Existing behavior-ownership partition, approved API targets and focused
  transition test: one exact new file, no neighboring target allowance.
- This record, current ARCH parent/overview/plan/map, affected initiative
  navigation, README, task specification, operating manual,
  `docs/operations_operator_workflow.md` availability note and roadmap.

### Not allowed

No routes, AUTH actions, role/grant logic, permission inference, policy lookup,
count query, lifecycle write, assignment invalidation, migration, new dependency,
retained-data deletion, compatibility alias, generic paginator framework, or
CI/test/coverage weakening. Assignment invalidation still needs shared committed
outbox claims. Detail/locked-context/audit projections remain separate work.

## Design and decisions

Replace the ready-specific cursor/request names with `TaskQueueCursor` and
`TaskQueueRequest` in their existing module and every caller/test/export. Their
existing UUID/project/aware-time validation and bounded limits stay intact;
remove the superseded names, with no aliases. They express the same live
project position now used by three actual reads. Ready items and its port keep
their distinct eligibility contract.

Add explicit immutable management and operational item/page/port types. Both
reads return all task states in one exact project, including draft and assigned
work, with no ready/assignee/assignment filter. Separate methods choose fixed
projections; no actor/token-role switch or caller-selected fields.

Management item fields: task_id, project_id, title, task_type, difficulty,
skill_tags (tuple), estimated_time_minutes, status, deadline_at, created_at,
updated_at. No description, acceptance criteria, source/import metadata,
contributor identity, artifact, policy body or secrets.

Operational item fields: task_id, project_id, status, created_at, updated_at.
No task title, description, tags, actor, source, policy or artifact facts.

Each page is a frozen tuple bound to its project; continuation equals its final
item's `(project_id, created_at, task_id)` only if another matching row exists.
Limits remain 1..100; sort by created_at then UUID id. Shared private query
mechanics apply project and cursor before limit+1, while ready eligibility stays
explicit in the ready read. No count, snapshot, permission or reservation is
implied. All reads use no_autoflush and preserve caller commit/rollback/locks.
A shared cursor positions each live view; it does not certify its audience or
membership. Future wire tokens/authority are ARCH-03C responsibilities.

## Acceptance criteria

- Both new queues return exactly the selected project's tasks in all nine
  current lifecycle states: draft, screening, ready, claimed, in_progress,
  submitted, evaluation_pending, review_pending and needs_revision. Foreign rows interleaved before and between local
  rows cannot consume page slots, alter continuation or escape serialization.
- Limit-one traversal covers equal timestamps, exact UUID tie ordering,
  exhaustion, empty/missing project and a deleted cursor anchor.
- Ready queue still excludes draft, assigned-only and active-assignment-only
  rows independently; released assignment history does not hide eligible work.
- Exact field sets, tuple detachment and frozen objects enforce distinct
  manager/operator projections. Injected private strings in task content do
  not appear in operator serialized facts.
- Invalid request/cross-project cursor fails before SQL. Reads neither flush
  pending invalid rows nor commit/rollback caller changes; an independent
  session observes rollback; `session.in_transaction()` remains true after the
  read. Reads complete while another session holds a
  task row lock.
- API exports contain the canonical request/cursor only; no former name alias
  remains. No new public route or AUTH action appears.
- Focused real PostgreSQL tests and unchanged full hosted gates pass. Removing
  the exact project predicate must fail `test_management_queue_pagination` for
  both methods. Injecting `status IN ('draft', 'ready', 'claimed')` must fail
  `test_management_queue_all_states` for both methods.

## Risk and review routing

- Risk class: `L1` (public owner contract, project isolation and projection privacy).
- Required reviewers: security/architecture/reuse/senior engineering;
  QA/test-delta/product-operations; documentation; CI integrity for exact test
  and ownership registration. Related tracks may share a bounded reviewer.
- Human review focus: fixed field sets and hidden authority boundary, reuse
  without speculative abstractions, exact project before pagination, preserved
  ready eligibility and transaction ownership.

## Evidence

Plan review preceded implementation and repaired the state-coverage gap below.
The named tests now implement these proof obligations; exact execution and review
provenance belong in the PR. Fixtures use existing task_client/create_active_project and
real constrained Task/Assignment rows, with stored precondition assertions.
Draft is valid without policy locks; ready and claimed fixtures use the existing
screen/release/real claim helpers, retaining CP08 lineage and real actor FKs.
`test_management_queue_all_states` persists all nine states and asserts their
exact stored set before reading either queue. Draft, ready and claimed use the
canonical helpers; later-state fixtures may update fully locked ready rows
with all database guards enabled. This arranges read fixtures only, and does
not claim the later lifecycle operations ran. The existing 0024 trigger guards
initial insertion/stamp mutation, and the fully locked rows satisfy non-draft
constraints without disabling a trigger.

Additional tests: `test_management_queue_projection` checks exact manager and
operator fields and private sentinels; `test_management_queue_transaction`
checks no-autoflush separately from flushed-marker rollback and the still-open
transaction; `test_management_queue_nonlocking` holds a real row lock in an
independent session. Parameterize each read proof over both queue methods.

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Project/pagination/privacy | `tests/tasks/test_management_queue.py` on isolated PostgreSQL via `scripts/run_isolated_tests.py` | Implemented | Exact head execution required before readiness |
| Ready behavior retained | Existing `tests/tasks/test_ready_queue.py` unchanged assertions with canonical renamed inputs | Preserved | Exact head execution required before readiness |
| Transaction/nonlocking | Real independent-session no-autoflush/rollback/row-lock tests for both new reads | Implemented with real sessions | Exact head execution required before readiness |
| Wrong-reason resistance | Remove only project predicate in actual owner query, rerun exact pagination test | Required probes | Project removal and three-state filter must fail |
| Architecture/docs/CI | Ruff, module/AUTH/test boundaries, ownership validator, links, stale scan, Commitrail, hosted seven lanes | Required | Final exact head evidence in PR |

## Review findings

`PLAN-03B3-01` / `QA-03B3-PLAN-01`: an all-states promise was initially tested
only with draft/ready/claimed. The contract now requires all nine persisted
states and a three-state-filter mutation probe, with fixture-only later state
setup distinguished from lifecycle-operation evidence.

`QA-03B3-IMPL-01`: the management projection now uses a persisted non-null
aware deadline and exact stored precondition, so a dropped deadline cannot pass
the field proof. `DOC-03B3-01`: the operator workflow now explicitly labels
queue reads hidden and public access pending ARCH-03C.

## Reconciliation

- Main integration: preserve merged retry/suspension behavior, both exact owner
  registrations and their regression tests, both TASK lane modules, and both
  roadmap outcomes. Recompute the combined ownership digest. Operational
  projection proof also inspects the actual executed SELECT columns, so loading
  private content cannot pass merely because serialization omits it. Keep the
  small shared datetime validator beside the existing queue input contracts;
  extracting another utility module is not needed for this reconciliation.
- Current-source reconciliation: extends merged 03B2; CP08 writers and public
  claims remain authoritative and untouched. No pre-release compatibility path.
- Next usable boundary: remaining actor-specific detail/locked-context/audit
  projections; invalidation waits for shared claims; ARCH-03C owns exact AUTH
  and public activation.
- Remaining risks: live pages may change between requests and reserve nothing.
