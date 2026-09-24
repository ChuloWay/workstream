# ARCH-03C4 — Exact-authorized public task queues

- Initiative: WS-ARCH-001
- Disposition: Planned
- Risk: L1 (authorization, public read exposure)
- Base: current main after merged ARCH-03C3 (#436).

## Intent and current-source reconciliation

Let a contributor discover ready tasks in one authorized project, a manager
inspect that project's task planning queue, and a system Operator inspect its
status-only queue. Reuse the TASK projections delivered by 03B2/03B3 and AUTH's
canonical request actor, stored grants, audit and signed keyset pagination.
Queue reads never claim work or authorize a later claim. Foreground commands
retain their current-authority and exact-task guards.

The 03C parent manifest is a skeleton, not implementation proof. Current main
has nonlocking `TaskRepository.read_ready_tasks`, `read_management_tasks` and
`read_operational_tasks`, with exact project filtering before pagination. No
public queue route currently exists. The earlier API drill also establishes
that retained task-detail/locked-context/audit reads still require old role and
creator checks; those distinct read cutovers remain the next bounded work.

## Bounded outcome

| Public GET route | Action | Exact authority |
|---|---|---|
| `/projects/{project_id}/tasks/ready` | `task.queue.read` | Active exact-project Submitter grant |
| `/projects/{project_id}/tasks` | `project.task.queue.read` | Project Manager grant covering the project |
| `/operations/projects/{project_id}/tasks` | `operations.task.queue.read` | System-scoped Operator grant |

Contributor discovery requires an active project. Manager and Operator queues
can inspect retained project states. All routes use limit 1–100 (default 50)
and the existing signed cursor codec bound to action/project/limit/order.
Every page rechecks live actor, identity link and grant; a cursor is no authority.
Unauthorized, foreign and absent projects have the same concealed 404 response.
Malformed/forged/cross-query cursors are 422 after live authority, without TASK
row access. Preserve the existing fixed summary fields; no source bodies,
contributor identities, checker configuration or private audit payloads escape.

## Design and transaction boundary

Add three closed catalogue actions, using existing permissions, and a bounded
queue resource context with exact project identity and normalized query digest.
Extend `AuthorizationService.require`, not PREP or a second authorization service.
The queue evaluator revalidates the request actor using existing AUTH repository
locks, then locks the exact Project and matched grant. It never locks TASK rows.
The existing composition root owns one transaction across authority, nonlocking
TASK projection, response construction and committed decision evidence. Denials
use the canonical rollback/restage path. Projection, serialization or audit
failure rolls back the allow decision and returns no successful page. No role
claim, creator identity, different project grant or service actor is sufficient.

Use the existing signed cursor implementation in the API composition root;
TASK ports keep their existing typed timestamp/UUID cursor. Small adapter
factories expose those existing ports. Public response schemas stay TASK-owned.
The migration only extends exact action/permission audit evidence pairs; no new
tables, retained-row rewrites, backfill or data deletion.

## Allowed scope

- AUTH catalogue/runtime/kernel and focused `domain/task_queues.py` evaluator;
  existing request-dependency error concealment and signed cursor reuse.
- TASK queue API docstrings, response schemas and existing adapter factories;
  queue SQL only if a concrete regression requires correction.
- API queue composition route and router registration.
- Additive Alembic 0031 action evidence constraint, migration admission/schema
  fingerprint and affected migration-head/inventory tests.
- Focused AUTH/TASK/API/migration tests, real API drill, lane test inventory.
- Current README, task/AUTH specifications, operating manuals, roadmap and
  initiative navigation. Local sheet exports only if present.

## Prohibited changes

No claim/start/lifecycle/policy selection changes, compatibility routes or
aliases, new permissions, new pagination or auth subsystem, public guide
activation, Submission/checker/review exposure, task-detail/read cutover,
leases/skip, frontend, model calls, private guide documents, secrets or `.env`.
Do not relax dependency guards, coverage, lane selection or retained assertions.

## Acceptance and proof

1. Signed HTTP requests with real stored grants distinguish submitter, manager
   and system Operator access. Independently reject absent/foreign/revoked grants,
   wrong role, token-role-only, service actor, suspended profile and revoked link.
2. A valid authorized empty project returns an empty page; unauthorized and
   absent project responses are indistinguishable. Ready discovery rejects
   paused projects; manager/operator inspection remains available.
3. Real PostgreSQL pages prove eligible READY/unassigned rows only for contributors,
   all states for managers/operators, exact project isolation, fixed private-field
   exclusion, bounded limits, stable tied-timestamp ordering and next-page reads.
   Use the existing valid task/guide/grant fixtures, never incomplete fake lineage.
4. Cursor tests distinguish valid continuation from tampering, changed action,
   project or limit, malformed input, and revocation between pages. Claim between
   pages can remove an item; pagination does not restart or reserve a task.
5. Observe SQL to prove authorization precedes task projection and Operator reads
   select no private columns. Verify committed exact action/permission/project
   and query digest evidence; injected projection/audit failure leaves no allow.
6. Real concurrent transactions prove actor/grant revocation serializes against
   queue reads. Follow existing AUTH lock ordering; no TASK lock is acquired.
7. Actual migration preserves existing evidence; direct SQL accepts new exact
   pairs and rejects mismatched permissions. Head upgrade/repeatability succeeds.
8. OpenAPI advertises three distinct actions and response fields. The real API
   drill discovers the manager-created/released task via authorized ready queue
   before claim, tests management/operator fields and denied cross-role access.
9. Remove-only mutation probes must make authorization/isolation/privacy proofs
   fail; preserve positive controls so earlier guards cannot mask the boundary.

## Verification and reviewers

Lead runs Ruff, module/AUTH boundary and test-structure checks, changed Markdown
links, stale-wording scans, Commitrail, focused isolated PostgreSQL tests and
complete local real HTTP drill (PG/Redis/MinIO). Full suite and coverage belong
in hosted CI. No `.env` or real providers are required. Freeze clean base/head
before each review wave and retain evidence provenance.

Plan and implementation reviewers: security + architecture/reuse; QA/test-delta
+ product operations; documentation; CI integrity for catalogue/selection and
hosted custody. Shared checks run once; reviewers perform discriminating probes
for their assigned boundaries. Human focus: exact authority per projection,
concealment, privacy, cursor replay, read/revoke ordering and atomic evidence.

## Reconciliation

- Intended merged disposition: Complete for these three queues only.
- Next usable boundary: remaining task-detail/requirements/locked-context/audit
  read authority, then public guide/intake integration per the parent roadmap.
- Remaining risks: bounded live pages are not snapshots; claim always rechecks.
