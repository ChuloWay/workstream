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
| `/projects/{project_id}/tasks/ready` | `task.queue.read` | `task.queue.read`; active exact-project Submitter grant |
| `/projects/{project_id}/tasks` | `project.task.queue.read` | `project.task.manage`; Project Manager system or exact-project grant |
| `/operations/projects/{project_id}/tasks` | `operations.task.queue.read` | `operations.status.read`; system-scoped Operator grant |

Contributor discovery requires an active project. Manager and Operator queues
can inspect retained project states. All routes use limit 1–100 (default 50)
and the existing signed cursor codec bound to action/project/limit/order.
Every page rechecks live actor, identity link and grant; a cursor is no authority.
Unauthorized, foreign and absent projects have the same concealed 404 response.
Request-shape validation (limit bounds and cursor length at most 512) may
return 422 before endpoint authority. Well-shaped malformed/forged/cross-query
cursors are decoded only after live authority and return 422 without TASK row
access or a committed allow decision. Preserve the existing fixed summary fields; no source bodies,
contributor identities, checker configuration or private audit payloads escape.

## Design and transaction boundary

Add three closed catalogue actions, using existing permissions, and a bounded
strict frozen `QueueReadResourceContext`: resource_type is `project`, resource_id
and scope_project_id are equal UUIDs, and request_digest is a canonical SHA256.
The stable cursor signing digest uses existing action/project/limit/fixed-order
binding and NEVER includes the cursor. Separately, request_digest hashes that
stable query digest plus nullable sha256 of the bounded presented cursor string.
The kernel's resource_context_digest therefore distinguishes first/next pages.
Register exact pairs in catalogue/database parity, context-digest audit evidence,
project audit targeting and the concealed-read action set. Never add a queue
permission or trust request-supplied project existence/status.
Extend `AuthorizationService.require`, not PREP or a second authorization service.
The queue evaluator revalidates the request actor using existing AUTH repository
locks, then the matched grant, then the exact Project, matching existing
manager/PREP order. The locked Project supplies current existence/status.
Use explicit role filters: exact-project Submitter; system-or-exact-project
Project Manager; system Operator only. It never locks TASK rows.
The existing composition root owns one transaction across authority, nonlocking
TASK projection, response construction and committed decision evidence. Denials
use the canonical rollback/restage path. Projection, serialization or audit
failure rolls back the allow decision and returns no successful page. No role
claim, creator identity, different project grant or service actor is sufficient.

Use the existing signed cursor implementation in the API composition root;
TASK ports keep their existing typed timestamp/UUID cursor. One adapter factory exposes the existing repository satisfying all three
queue protocols; no separate wrappers or query implementations. Public response schemas stay TASK-owned.
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
   select no private columns in ALL three projections, including unused extra
   columns; observe actual selected columns and mutate each projection to add a
   forbidden field so the proof fails. Verify committed exact action/permission/project
   and query digest evidence; injected projection/audit failure leaves no allow.
6. Real concurrent transactions prove actor/grant revocation serializes against
   queue reads. Observe the actual actor/profile-link → matched grant → Project
   FOR UPDATE sequence for all three actions and nonlocking TASK SELECT; include
   a real guide-activation/read interleaving with the shared project. A deliberate
   lock-order substitution must fail this proof; no TASK lock is acquired.
7. Actual migration preserves existing evidence; direct SQL accepts new exact
   pairs and rejects mismatched permissions. Head upgrade/repeatability succeeds.
8. OpenAPI advertises three distinct actions and response fields. The real API
   drill discovers the manager-created/released task via authorized ready queue
   before claim, tests management/operator fields and denied cross-role access.
9. Remove-only mutation probes must make authorization/isolation/privacy proofs
   fail; preserve positive controls so earlier guards cannot mask the boundary.


## Named verification targets

All paths below are new focused modules except the explicitly retained test.
They describe required future proof, not executed results.

- `backend/tests/authorization/task_queues/test_authority.py`:
  `test_queue_authority_matrix` (signed requests, each of the three actions,
  independent roles/scopes, PM system and project positive controls),
  `test_queue_conceals_absent_and_unauthorized_projects`,
  `test_queue_revalidates_actor_link_and_grant`,
  `test_queue_project_lifecycle` (persist a paused Project as a guards-on fixture;
  do not claim a public pause operation ran).
- `backend/tests/tasks/test_public_queues.py`:
  `test_public_queue_pages_preserve_owner_selection` (valid active guide/lineage,
  own/foreign project, draft/ready/assigned, equal timestamps, limits and full
  continuation), `test_queue_selects_only_declared_columns` (all three real SQL
  projections; forbidden-column mutation), `test_cursor_binds_query_and_rechecks_authority`
  (valid page two, tamper/action/project/limit substitution, revoked grant and
  claim between pages), `test_queue_rejects_invalid_request_shape`.
- Replace obsolete `test_ready_queue_has_no_public_route` in
  `backend/tests/tasks/test_ready_queue.py` with
  `test_public_queue_openapi_contract`: three exact GET actions/schemas and the
  unchanged manager POST create route. Retain all existing owner behavior tests.
- `backend/tests/authorization/task_queues/test_transactions.py`:
  `test_queue_records_exact_page_authority` (committed exact matched grant/action/
  permission/project and digest, first versus next-page cursor hash),
  `test_queue_failure_rolls_back_allow` (projection, serialization and audit
  failures; positive control), `test_queue_lock_order` (observed real SQL sequence),
  `test_queue_serializes_with_authority_revocation` (independent sessions and
  PostgreSQL blocking observation), `test_queue_serializes_with_guide_activation`.
  Mutation controls remove each authorization/tenant filter, add forbidden
  selected columns, omit presented-cursor binding, and reverse grant/Project locks;
  each relevant positive-plus-negative proof must detect its own defect.
- `backend/tests/migrations/test_task_queue_authority.py`:
  `test_upgrade_preserves_authorization_evidence`,
  `test_queue_audit_permission_pairs_are_closed` (real direct SQL valid events,
  change only the permission for each invalid event; mutation disabling the
  exact constraint makes rejection assertion fail). Existing graph/head upgrade
  and repeatability tests remain required.
- `backend/scripts/api_contract_e2e.py::exercise_api_contract`: full isolated
  signed HTTP drill, authorized queue discovery preceding contributor claim,
  manager/operator field separation and independent wrong-role denials.

## Plan-review findings

Plan review found and corrected draft lock ordering, stable cursor versus audit
request digest ambiguity, covered-PM scope wording, obsolete public-absence
assertions, request-shape precedence, and incomplete selected-column proof.
The repaired contract requires exact audit action pairs and named positive/
negative controls; implementation and runtime evidence remain outstanding.

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
