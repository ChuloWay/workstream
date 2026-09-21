# WS-ARCH-001-03B2 — Project-scoped ready task queue facts

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: TASK exposes one hidden owner port for bounded,
  detached ready-task queue pages; live AUTH/HTTP composition stays in ARCH-03C.

## Intent

Provide the missing contributor-ready queue data boundary without rebuilding
CP08 lineage writers, duplicating claim, or exposing an unauthorised route.
This is the next bounded child after delivered 03B1. Manager/operations/audit
projections and committed-event assignment invalidation remain separate children.

## Current behavior

`tasks.repository.TaskRepository` owns task/assignment queries but has no list
operation. `AuthorizedTaskCommands.claim` revalidates current exact-project
AUTH and locked context before assigning ready unassigned work. The existing
`task.queue.read` permission serves work-context reads, but no queue action or
HTTP queue exists. TASK has no task-specific visibility column: contributor
queue eligibility is project scope, ready state, and no current assignment.
The broader old token-role detail/management reads remain explicitly 03B/03C
cutover work; this queue must not call those helpers or create another role path.

## Bounded change

### Allowed

- `backend/app/modules/tasks/api/ready_queue.py`, its API exports, and
  `backend/app/modules/tasks/repository.py` extending the existing owner.
- `backend/tests/tasks/test_ready_queue.py`; exact TASK test-lane registration
  and its equality assertion.
- This record, ARCH parent/overview/map, affected current navigation and
  README, task specification, operating manual and roadmap status.

### Not allowed

- HTTP routes, AUTH decisions/action activation, token-role inference, grants,
  new assignment/lineage writers, policy selection or readiness changes.
- Migrations, retained-data deletion, dispatcher/invalidation implementation,
  payment/economic cleanup, compatibility paths or unrelated read replacements.
- CI/test gate, dependency or coverage-threshold weakening.

## Design and decisions

One internal `ReadyTaskQueuePort` returns frozen scalar/tuple facts. A validated
request requires a UUID project selector, limit 1..100 (not bool), and optional
project-bound cursor `(project_id, created_at, task_id)` with aware timestamp.
The cursor is a position, never authority; a future authorized caller derives
project scope and supplies it after AUTH, never trusts cursor scope. Wire tokens,
actor authority and public routes belong to 03C; this port alone grants nothing.
No separate resolver, permission type, signed cursor system or generic paginator.

Use one scalar-column SELECT, ordered by `created_at,id` ascending, with project,
`status=ready`, `assigned_to IS NULL`, and NOT EXISTS active TaskAssignment
predicates before cursor comparison and `limit+1`. Excluding inconsistent active
assignment rows is required even if task.assigned_to is null. An inactive
historical assignment does not hide a ready task. Return at most limit entries
and a next cursor only when the extra eligible row exists. No total count, offset,
ORM object, private source metadata, actor ID, policy body/hash, or stored artifact
reference escapes. A page item has task/project IDs, title, task type, difficulty,
skill tags (tuple), estimated minutes and created_at. Cursor/page identity must
match the request project. No snapshot/reservation/claim guarantee is implied.

Read under `session.no_autoflush`; do not commit, rollback, refresh, or lock rows.
Caller owns transaction. Concurrent claims are authoritative through the existing
claim operation; pagination is a live view, not a snapshot. Previously returned
or deleted/claimed cursor anchors need no database lookup; identical timestamps
use the unique task ID tie-breaker. No query selects a current guide or CON policy.

## Acceptance criteria

- [ ] Invalid input fails before database access; wrong-project cursor rejects.
- [ ] Project/state/assignment eligibility filters precede limit and next cursor;
      foreign/draft/assigned tasks cannot affect a page or indicate another page.
      Isolate each predicate: local READY/non-null assigned_to/no active assignment
      and local READY/null assigned_to/exact-stamp active assignment are separate
      committed decoys with their pre-query state asserted. Interleave all decoys
      with eligible controls and verify exact items/cursors through exhaustion.
- [ ] Equal timestamps page deterministically without duplicates; removed or
      claimed anchors still permit continuation; exhausted and empty pages end.
- [ ] Active assignment inconsistency is excluded; inactive history is allowed.
- [ ] Exact immutable public facts contain only the declared fields and detach
      mutable skill tags; no SQLAlchemy model escapes.
- [ ] Pending writes are not flushed and caller rollback remains effective;
      read does not wait for another session's task row lock.
- [ ] Existing HTTP/OpenAPI exposes no queue, and existing claim/lineage behavior
      remains unchanged. Queue availability is documented as hidden only.

## Risk and review routing

- Risk class: L1 (tenant scope, privacy, architecture read contract).
- Required reviewers: architecture/reuse, security, QA/test-delta,
  documentation/product operations and CI integrity for lane ownership.
- Human review focus: exact project filtering, minimal fields, live pagination
  semantics and explicit boundary between internal reads and future authority.

## Evidence

The named tests below implement the proof boundaries; exact execution and
review evidence belongs to the PR.
Use actual PostgreSQL with existing `task_client`/`create_active_project` and
`create_ready_task` fixtures, which screen/release through existing CP08 writers.
Do not fabricate non-draft stamps or disable guards in normal arrangements.

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Input boundary | `test_ready_queue_request_validation` | Implemented; execution in PR | Pure controls including bool limit and naive dates |
| Scoped pagination | `test_ready_queue_filters_before_pagination` | Implemented; execution in PR | Two projects plus independently excluded local draft, assigned_to-only and active-assignment-only decoys; assert stored states, deterministic timestamps/UUID order and exact limit-one traversal to exhaustion |
| Claimed anchor | `test_ready_queue_continues_after_claim`: real exact-project grant and canonical claim; old cursor and fresh read exclude claimed task | Implemented; execution in PR | No claim or AUTH substitute |
| Assignment visibility | `test_ready_queue_assignment_visibility` | Implemented; execution in PR | Valid exact-stamp active assignment on ready task versus closed history; preserve all DB constraints |
| Detached facts | `test_ready_queue_detached_projection` | Implemented; execution in PR | Full field equality, mutable source-tag mutation and frozen result rejection |
| Caller transaction | `test_ready_queue_preserves_transaction` | Implemented; execution in PR | Pending invalid row no autoflush; separately flushed marker read/rollback and independent observer |
| Nonlocking read | `test_ready_queue_does_not_wait_for_task_lock` | Implemented; execution in PR | Two sessions, held FOR UPDATE and bounded independent read |
| Proof rejects defect | Scoped predicate-omission probe | Implemented; execution in PR | Remove project predicate only in isolated test copy; positive control passes, exact pagination test fails |
| Exposure/selection | Existing OpenAPI route inventory, exact TASK catalogue assertion | Implemented; execution in PR | No HTTP queue claimed |
| Shared checks | Ruff, boundaries, Commitrail, links, stale scans, hosted full Backend/MCP CI | Implemented; execution in PR | Migrations remain 0024; full suite stays hosted |

## Review findings

Security/architecture/reuse review accepts the hidden data-owner boundary;
existing per-task authority cannot authorize a collection without prior discovery.
QA-03B2-PLAN-01 repaired the predicate matrix: a claimed decoy is insufficient
for assigned_to because state/active-assignment guards also exclude it. Prove
each eligibility predicate independently using reachable exact-stamp database
states, without disabling constraints. Named tests remain future evidence.

## Reconciliation

- Base: merged #417 (`32a83a33`), including corrected CP08 roadmap.
- Next usable boundary: remaining management/operations/audit projections;
  invalidation after shared committed claims, then 03C authority/public wiring.
- Remaining risks: internal read does not authorize any actor or guarantee a
  later claim. All production access must still wait for 03C's exact authority.
