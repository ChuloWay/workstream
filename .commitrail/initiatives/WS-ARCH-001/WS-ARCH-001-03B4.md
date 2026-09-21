# ARCH-03B4 — Hidden contributor and management task detail

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Intended merge outcome: TASK supplies fixed contributor and management task detail through its existing repository; exact public authority and route replacement remain ARCH-03C.

## Intent and current source

Main `77c8fc23` includes all three hidden queues, task command replay and actor
suspension denial. Migration head is `0025_task_command_replay`. The remaining
03B projection boundary begins with task detail. Existing `TaskService.get_task`
uses token-role visibility and one broad mutable `TaskResponse`, also consumed
by creation/screen/release and authorized claim/start receipts. Replacing that
HTTP surface requires the exact AUTH actions owned by 03C; this child must not
silently remove manager access or change immutable command receipts.

Add hidden owner reads for the detail facts needed by the future separate
contributor and manager surfaces. Do not call the old role-sensitive service or
reuse its broad response/redaction strategy. The existing route and command
response consumers are explicit remaining dependencies, not compatibility
aliases for these new owner facts. Locked-context/work-context, requirements,
operational and audit projections remain the next 03B boundary. Assignment
invalidation still requires the shared committed-claim contract.

## Scope and design

Risk: `L1` (tenant isolation and contributor visibility).

Allowed files: `backend/app/modules/tasks/api/task_detail.py`, API exports,
`backend/app/modules/tasks/repository.py`, new `backend/tests/tasks/test_task_detail.py`,
existing TASK lane catalogue and exact-set test, behavior-ownership partition,
exact API target allowlist and existing neighbor-denial test, this record,
current ARCH overview/plan/map/03B parent, affected initiative navigation,
README, task specification, operating manual and roadmap.

Prohibited: new HTTP routes, AUTH actions or grant decisions, role inference,
claim/start/replay changes, policy selection, locked-context validation changes,
assignment invalidation, lifecycle writes, schema/migrations, dependencies,
retained-data deletion, compatibility aliases, generic query/projection framework,
or weakened tests/coverage/gates. No work on unrelated old APIs.

Use two explicit immutable dataclass value contracts and two Protocols:
`ContributorTaskDetailPort.read_contributor_task_detail` and
`ManagementTaskDetailPort.read_management_task_detail`, implemented by
`TaskRepository`. Use an exact project/task request for management and a separate
project/task/contributor request for contributor visibility; validate UUID types
before SQL. Return `None` for missing, wrong-project or invisible tasks, without
an existence probe. No selector is authority: a future public caller must first
establish exact current authority and bind the contributor identity itself.

Both detail contracts contain task_id, project_id, title, description, task_type,
difficulty, skill_tags (tuple), estimated_time_minutes, status,
acceptance_criteria, rejection_criteria, deadline_at, created_at and updated_at.
Management additionally contains source_type, source_ref, source_payload_hash,
import_batch_id, external_task_id, created_by and assigned_to. No economic fields,
policy bodies, locked-context hashes, assignment payload, credentials or artifact
references enter either detail. These belong to other governed surfaces.

Use an explicit common detail value base only for the identical common fields,
with a management extension for its additional facts; no audience flag or
caller-selected columns. Validate UUIDs, scalar/optional types, tuple contents
and aware timestamps. Use fixed scalar SELECTs, never load the ORM task for
redaction. Contributor SQL must not SELECT source, actor or policy columns.

Management reads all task states within exact project/task scope. Contributor
reads mirror the existing TASK work-context visibility facts: unassigned READY
with no active assignment, or a matching active assignment whose contributor
and task.assigned_to both equal the requested contributor. Match assignment
project and task identity. Released/history rows do not confer visibility.
This is object visibility only, never a role/grant authorization decision.
Keep the unassigned READY predicate consistent with the delivered ready queue;
reuse a small TASK-specific predicate if needed, not a generic filter system.

Apply project, task and visibility predicates in the executed query. Use
no_autoflush, no commit/rollback/locks, and detached tuple/scalar results. Existing
queue behavior and command receipts remain unchanged.

## Acceptance and proof

All test names below are planned, not executed evidence.

- `test_task_detail_contracts`: immutable exact field contracts, invalid UUIDs,
  scalar/tuple/time shapes, no mutable nested values; malformed requests fail
  before SQL for both reads.
- `test_task_detail_scope`: persist local and foreign draft/ready rows through
  canonical helpers; both methods conceal an exact task requested under another
  project and missing task. Contributor sees local unassigned ready; manager
  sees local draft. Removing only project scope must fail the foreign case.
- `test_task_detail_visibility`: canonical real-AUTH claim with a real actor,
  then another actor and released/history fixtures; prove ready/own active
  visibility, other contributor denial, assigned_to alone denial, active
  assignment alone denial, and released history cannot confer ownership or hide
  unassigned ready. Store/precondition each fact before querying; no disabled
  database guard. Mutation removing the contributor ownership predicate must
  fail with a persisted foreign contributor/assignment.
- `test_task_detail_management_states`: all nine stored states, using canonical
  draft/ready/claimed plus fully locked later-state fixtures as in 03B3. Exact
  state preconditions and returned IDs; no claim these fixtures execute the
  later lifecycle operations. Contributor own-assignment state handling is
  checked against the current work-context visibility rule, without inventing
  a new lifecycle allowlist.
- `test_task_detail_projection`: exact DTO fields, source/actor sentinels in
  manager detail only, real executed contributor SELECT column set, non-null
  persisted deadline, detached tags and immutable result. Add only source_ref
  to actual SELECT and prove the exact column assertion fails.
- `test_task_detail_transaction` and `test_task_detail_nonlocking`: both methods;
  pending invalid row never flushed, flushed marker rolls back and another
  session observes original value, transaction stays open; independent session
  holds task FOR UPDATE and read completes within bounded timeout.
- No public route/action added; ready queue tests and replay tests remain in
  full hosted selection. Existing old detail/command response consumers remain
  explicit 03C dependencies; no alias or second public endpoint is introduced.

Fixtures reuse `tests.test_tasks` and existing ready/management queue tests with
real PostgreSQL and current migration0025. Trace valid actor/task/assignment
lineage under existing FKs before constructing negative cases. Run focused
isolated PostgreSQL tests, the three discriminating query mutations, exact
lane/ownership regressions, Ruff, module/AUTH/test-structure boundaries,
Markdown links, stale wording, Commitrail and full unchanged hosted CI.

## Review and human focus

Plan review before implementation: security/architecture/reuse and
QA/test-delta/product-operations; independently inspect fixture feasibility.
Implementation review: same tracks, docs and CI integrity for exact registration.
Lead owns shared checks and exact clean candidate. Human focus: project and
ownership filtering in SQL, fixed field privacy, preserved caller transaction,
no false public-availability claims, and no obsolete economic facts in new detail.

## Reconciliation

Extend the existing repository and current immutable queue vocabulary without
adding a second lifecycle service. No shared code is deleted because old detail
and command responses still have live callers. Do not rename them as cleanup.
After this child, remaining detail-adjacent locked-context/requirements and audit
contracts precede 03C authority/cutover. Roadmap and current navigation must
reflect this child’s intended merged outcome in the same PR.
