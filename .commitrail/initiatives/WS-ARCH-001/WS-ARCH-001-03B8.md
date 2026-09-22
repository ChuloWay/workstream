# ARCH-03B8 — Bounded task audit evidence

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: immutable, bounded task lifecycle evidence for the
  planned Audit Authority read, with exact project/task scoping and no public
  activation.

## Intent

An auditor needs ordered evidence of what happened to a task without receiving
raw authentication claims, private documents or arbitrary event payloads. Complete
this remaining 03B projection using the existing shared audit owner. Do not build
another audit store, writer, authority decision or history reconstruction.

## Current behavior

Main includes 03B7 at `ab4a4256`. TASK already supplies the other actor-specific
projections. `TaskRepository.list_audit_events` delegates to the shared
`AuditRepository`; it loads whole rows without pagination. Its live consumers
include `TaskService.list_task_audit_events`, submission finalization recovery
and `CheckerService` recovery provenance.
The retained HTTP route uses contributor/manager visibility and payload redaction.
It is not the proposed `audit.task.evidence.read` authority surface.

## Bounded change

### Allowed

- `backend/app/modules/tasks/api/audit_evidence.py` and `api/__init__.py`: pure
  immutable request, cursor, evidence, page and read port.
- `backend/app/modules/tasks/repository.py`: hidden exact-project/task composition
  through the existing shared audit repository.
- `backend/app/modules/audit/repository.py`: bounded fixed-column lifecycle
  evidence query, preserving existing writers and required full-row readers.
  Add WorkstreamTask to its existing tasks.models import solely for atomic
  project membership in this query; the recorded private-edge path is unchanged.
- `backend/tests/tasks/test_audit_evidence.py`, relevant existing audit/delegation
  tests and the TASK lane catalogue/exact-set registration.
- Current ARCH overview/plan/chunk map/03B/03C contracts, related AUTH/CON/POL
  navigation, INDEX, README, roadmap, task specification, data model, glossary
  and operating manual. Local roadmap exports only if present.

### Not allowed

No route, permission, AUTH decision, token-role switch, writer, migration,
retained-data deletion, compatibility alias, fallback, generic pagination
framework, dependency-guard weakening or new private import path. No PROJECTS lookup,
policy evaluation, assignment invalidation or current-guide selection.

## Design and decisions

The TASK API remains dependency-free except for its own public contracts.
`AuditTaskEvidenceRequest` binds UUID project/task, limit 1..100 (default 50),
and optional `TaskEvidenceCursor` containing the same project/task plus aware
created_at and UUID event_id. Validate before SQL; cursor is a position, never
proof of authority or event existence.

`read_audit_task_evidence` delegates one scoped query to the existing shared
audit repository. Select a non-null task marker and fixed audit columns from
WorkstreamTask LEFT OUTER JOIN AuditEvent. The WHERE clause selects exact
project/task; the ON clause selects the existing exact `legacy_lifecycle` persisted domain, task entity and matching
task ID, plus the event cursor. No task yields no rows (None); an existing task
with no matching events yields one null-event marker (empty page). All task
states are eligible. Scope/event/cursor predicates precede limit+1. There is no
separate existence query, lateral subquery or generic query framework. This
atomic statement prevents a concurrent draft project move from invalidating a
prior scope check. The existing AUDIT-to-TASK model debt path remains recorded;
no new edge or public API exception is introduced. Ordering is ascending
(created_at, id); continuation exists only when another matching event exists.
Existing unbounded reads cannot safely implement this bounded SQL contract, but
remain required by the named live consumers above; do not add a fallback to them.

The immutable item contains UUID event_id; str event_type and actor_id (stored
attribution, not current identity/authority); str|None from_status and to_status;
aware datetime created_at; and UUID|None assignment_id and
authorization_decision_id. Null statuses and untyped-event references are valid;
other malformed types reject. Each page uses an immutable tuple of these items.
SQL selects exactly the task marker, six base event fields and four JSON scalar
references; never the raw payload column or a complete ORM row. For canonical
TaskClaimed, TaskStarted and TaskStartOverridden events, select only scalar
references.project_id/task_id/assignment_id/authorization_decision_id from the stored payload;
require exact request project/task and both valid required UUID references. Reject
missing, malformed or crossed references with sanitized TaskEvidenceInvalid.
Other event types do not gain inferred references. Omit unused nullable
event_version/occurred_at fields. It excludes external subject/issuer, actor roles,
claim_snapshot, reason, arbitrary event_payload/before_facts/after_facts, source
or artifact references, and policy bodies. Project/task identity is on the page
and cursor. Existing audit locked-context facts remain the separate provenance
projection. This is bounded lifecycle evidence, not an authorization-decision
export or complete forensic payload.

Use the existing TASK-to-AUDIT repository delegation rather than another audit
implementation. Audit owns its SQL column selection; TASK owns scope and public
facts. Both reads use no_autoflush, no row locks, and no commit/rollback/flush.
Pages are live read-committed views, not durable export snapshots. Uncommitted
rows in the caller's transaction remain visible; later rollback must work.

The public contributor/manager audit route and recovery reader remain explicit
consumers. ARCH-03C must reconcile their audience/authority before removal;
this internal Audit Authority read does not silently replace their permissions.
The existing persisted audit namespace is not a compatibility implementation;
this change does not rewrite its retained records or shared writers.

## Acceptance criteria

- Valid own-project/task reads include persisted task lifecycle events in all
  nine current task states; missing/foreign tasks return None without projecting evidence.
  Task scoping and evidence selection cannot combine different statement
  snapshots. A move committed before the SELECT starts hides the old-project
  task and exposes it under its new project. A commit after the statement snapshot
  does not retroactively alter that live read; no current-at-return claim is made.
- Interleaved other-task, other-project and other-entity events cannot fill a
  page or alter continuation. Equal timestamps use exact UUID tie ordering.
- Limit-one traversal, exhaustion, empty history and a non-existent cursor anchor
  work; invalid selectors/limits and cross-project/task cursors reject before SQL.
- SQL never selects private columns or full ORM events. Exact fixed field sets
  and tuple/frozen values prevent mutable/raw payload escape.
- Reader retains caller transaction ownership: pending invalid rows never flush;
  flushed marker/evidence can be read then rolled back, with an independent
  observer confirming absence. Reader completes while another session holds a
  task row lock.
- No new HTTP/OpenAPI/AUTH activation, compatibility path, test removal or
  weakening. Existing public audit visibility and recovery tests remain passing.

## Risk and review routing

- Risk class: L1 (project-scoped audit data and owner boundaries).
- Required reviewers: security, architecture/reuse, QA/test-delta,
  product/operations, documentation, and CI integrity for lane registration.
- Human review focus: fixed evidence fields, project/task filtering before
  pagination, caller-owned transaction, and the explicitly remaining public
  authority dependency.

## Evidence

Planned nodes in `tests/tasks/test_audit_evidence.py`:
`test_task_evidence_contracts`, `test_task_evidence_rejects_before_sql`,
`test_task_evidence_project_scope`, `test_task_evidence_project_move`, `test_task_evidence_pagination`,
`test_task_evidence_transition_references`, `test_task_evidence_sql_privacy`,
`test_task_evidence_caller_transaction`, `test_task_evidence_does_not_lock`,
and `test_task_evidence_hidden_surface`. Concrete controls must first prove
that fixture events are persisted under the existing append-only audit guards.
No tests disable data protections merely to reach an assertion.

Discriminating probes must drop exact project scoping, drop task event filtering,
substitute full-row selection, bypass typed-reference checks, permit a split scope precheck plus event query, and permit crossed
cursor project/task identity, each causing its intended test to fail.
Retained consumer nodes are
`tests/test_tasks.py::test_task_repository_delegates_audit_persistence`,
`::test_task_service_finalization_provenance_fails_closed_without_lock_audit`,
`::test_full_task_claim_start_flow_writes_audit_events`,
`::test_retained_packet_reads_preserve_locked_lineage_and_redact_audit`, and
`::test_cross_worker_cannot_list_submissions_or_audit_after_submit`.
Run those existing audit visibility/recovery and architecture tests, lane exact-set
checks, Ruff, stale wording, Markdown links and Commitrail validation. Full hosted
PostgreSQL/MinIO lanes and coverage govern final evidence. Migration head remains
0025. Runtime execution and plan feasibility are reported separately in the PR.

## Plan review corrections

- QA-03B8-PLAN-01: specify PostgreSQL statement-snapshot semantics. The move
  test commits the writer before starting the read; exact-one-execute proof and
  a split-query mutant detect the former mixed-snapshot design.
- PLAN-03B8-01: retain fixed assignment and authorization-decision references
  required by the canonical TASK transition evidence contract; exclude raw JSON.
- PLAN-03B8-03: eliminate the two-query project-scope race with one scoped
  outer join; preserve missing-versus-empty without new locks or abstractions.
- PLAN-03B8-02: name concrete future tests and discriminating mutations before
  implementation; runtime proof remains outstanding until those tests execute.

## Reconciliation

- Current-source reconciliation: 03B7 is merged; no competing product PR. PR410
  owns separate advisory CI impact work; this change does not alter workflows.
- Next usable boundary: assignment invalidation after AUTH-OUTBOX-01 and CON-02B
  shared committed claims, then ARCH-03C exact authority/public activation.
- Remaining risks: the retained public audit wrapper remains until its explicit
  authority replacement; live pagination is not a snapshot export.
