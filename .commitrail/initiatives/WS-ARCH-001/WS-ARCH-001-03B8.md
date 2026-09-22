# ARCH-03B8 — Bounded task audit evidence

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
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
include `TaskService.list_task_audit_events` and submission finalization recovery.
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
- `backend/tests/tasks/test_audit_evidence.py`, relevant existing audit/delegation
  tests and the TASK lane catalogue/exact-set registration.
- Current ARCH overview/plan/chunk map/03B/03C contracts, related AUTH/CON/POL
  navigation, INDEX, README, roadmap, task specification, data model, glossary
  and operating manual. Local roadmap exports only if present.

### Not allowed

No route, permission, AUTH decision, token-role switch, writer, migration,
retained-data deletion, compatibility alias, fallback, generic pagination
framework, dependency-guard weakening or new private import. No PROJECTS lookup,
policy evaluation, assignment invalidation or current-guide selection.

## Design and decisions

The TASK API remains dependency-free except for its own public contracts.
`AuditTaskEvidenceRequest` binds UUID project/task, limit 1..100 (default 50),
and optional `TaskEvidenceCursor` containing the same project/task plus aware
created_at and UUID event_id. Validate before SQL; cursor is a position, never
proof of authority or event existence.

`read_audit_task_evidence` first verifies the exact project/task using a scalar
TASK query. Missing and foreign tasks return None without loading any audit
rows. All task states are eligible. The shared audit owner selects only fixed
lifecycle columns for entity_type task and the exact task ID, excluding authority
records. Scope and cursor predicates precede limit+1. Ordering is ascending
(created_at, id); continuation exists only when another matching event exists.
Existing unbounded reads cannot safely implement this bounded SQL contract, but
remain required by the named live consumers above; do not add a fallback to them.

The immutable item contains event_id, event_type, from_status, to_status,
actor_id (stored attribution, not current identity/authority), created_at,
event_version and occurred_at. It excludes external subject/issuer, actor roles,
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
  task states; missing/foreign tasks conceal before AUDIT is called.
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

Planned tests in `tests/tasks/test_audit_evidence.py`: contracts/invalid inputs,
real PostgreSQL scope and pagination, fixed SQL fields/privacy, transaction and
nonlocking behavior, and hidden API exposure. Concrete controls must first prove
that fixture events are persisted under the existing append-only audit guards.
No tests disable data protections merely to reach an assertion.

Discriminating probes must drop exact project scoping, drop task event filtering,
and substitute full-row selection, each causing its intended test to fail.
Run existing audit visibility/recovery and architecture tests, lane exact-set
checks, Ruff, stale wording, Markdown links and Commitrail validation. Full hosted
PostgreSQL/MinIO lanes and coverage govern final evidence. Migration head remains
0025. Runtime execution and plan feasibility are reported separately in the PR.

## Reconciliation

- Current-source reconciliation: 03B7 is merged; no competing product PR. PR410
  owns separate advisory CI impact work; this change does not alter workflows.
- Next usable boundary: assignment invalidation after AUTH-OUTBOX-01 and CON-02B
  shared committed claims, then ARCH-03C exact authority/public activation.
- Remaining risks: the retained public audit wrapper remains until its explicit
  authority replacement; live pagination is not a snapshot export.
