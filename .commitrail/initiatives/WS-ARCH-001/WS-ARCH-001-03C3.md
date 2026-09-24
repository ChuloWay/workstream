# WS-ARCH-001-03C3 — Authorized manager task readiness

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Intended merge outcome: the existing create, screen and release HTTP operations
  use exact project-manager authority and atomic replay through the existing TASK
  command owner; screening retains the approved guide's complete policy lineage.

## Intent

Complete the manager's draft -> screening -> ready boundary before remaining
public task discovery/projection work. Preserve draft creation before a guide is
ready. Screening locks the approved guide; release validates that frozen context.
Claim/start already have canonical authority and retain their behavior. Contributor
leases and voluntary skip remain parked in #433. Include the retained two-line
roadmap correction from closed #435 in this product PR, not a separate cleanup PR.

## Current behavior

Main `27aac3d9` includes merged #434/ARCH-03C2. The public routes in
`tasks/router.py` call `TaskService.create_task`, `move_to_screening` and
`release_to_ready`. Those methods still use `require_any_role`, old actor-context
roles and owner-local commits. CP08 already implements complete guide stamping.
`AuthorizedTaskCommands` supplies the sole transaction/PREP owner for claim/start,
`TaskCommandReplay` supplies durable receipts, and `_TaskTransitionAudit` supplies
same-transaction shared evidence. The three manager actions do not yet exist in
the AUTH catalogue. The three existing receipt constraints require an assignment,
so they cannot honestly represent pre-assignment manager work unchanged.

## Bounded change

### Allowed

- TASK `router.py`, `authorized_commands.py`, `command_replay.py`, `service.py`,
  `models.py`, `repository.py`, `schemas.py`, existing `api/authorization.py` and
  `api/transition_audit.py`/exports: implement exactly create/screen/release through
  the current command and replay owners; remove superseded role-only methods.
- AUTH `catalogue.py`, `domain/task_authority.py`, `task_authorization.py`,
  `artifact_project_authority.py`, existing prepared/resource/audit dispatch and
  kernel only where the three closed actions require registration/parity.
  Reuse the exact actor/link/admin-grant lock owner; no new permission.
- Existing `adapters/tasks`, `adapters/auth`, `adapters/audit`, request composition
  in `api/deps/authorization.py`, shared AUDIT lifecycle schemas/service/repository,
  and TASK `api/audit_evidence.py` for exact manager transition facts and the
  existing hidden fixed-field audit projection; preserve other consumers.
- One additive Alembic revision after `0029_assignment_authority`: widen only the
  closed TASK command variants and corresponding AUDIT event guards; preserve
  every retained row and existing assignment command constraint. Require a deferred
  `task_command_receipts.task_id -> workstream_tasks.id` FK, permitting reservation
  before task insertion within one transaction. Preflight every retained task ID;
  refuse unprovable rows rather than inventing or deleting data.
- Focused `tests/authorization/task_authority/` manager tests and migration tests;
  affected existing TASK/ART fixture callers (`test_tasks.py`,
  `tasks/lineage_fixtures.py`) and every traced caller of these three HTTP mutations.
  Include `backend/scripts/api_contract_e2e.py`: supply keys on its four existing
  manager/denied-worker task mutations. Test `auth_headers` already supplies keys.
  Update real grant arrangements; replace obsolete role-only
  tests while retaining guide/lineage/validation/rollback assertions.
- Exact behavior ownership, lane inventory and structural-debt metadata, without
  raising limits or changing CI selection/thresholds; current ARCH parent/overview/
  map/index, README, TASK/AUTH operating/spec docs and affected roadmap claims.

### Not allowed

No new task states, timer/skip policy, public guide activation, queue/detail/read
activation, public Submission admission, ART/checker/REV execution, policy selection
at claim, duplicate command/replay subsystem, role/creator bypass, compatibility
methods, retained-data deletion or workflow/coverage weakening. No live model calls.

## Design and decisions

1. Register exactly `project.task.create`, `project.task.screen`, and
   `project.task.release`, all using existing `project.task.manage` and exact human
   Project Manager scope (project grant or a covering system grant). Submitter,
   Reviewer, Operator, Access Administrator and service identity alone do not grant
   this authority. Extend the existing TASK facts/PREP adapter and evaluator.
2. Require one UUID `Idempotency-Key` on all three routes through the existing
   duplicate-rejecting header dependency, before actor resolution/product SQL
   (not before token verification/rate controls). Use canonical actor profile IDs,
   not token roles. Preserve the existing route locations and response contracts.
3. Extend `AuthorizedTaskCommands` with these three operations and reuse existing
   TASK context validation/stamping helpers. Remove old mutating TaskService entry
   points and update their consumers; no alternate transaction owner. The ART
   arrangement fixture seeds a valid manager grant for its existing actor/link and
   calls the real commands/AUTH/audit adapters; no new production fixture helper.
   Create works on an existing project without an active guide. Preserve the
   controlled unknown-project error through the existing display port; do not
   invent a new project-lifecycle requirement. Screen requires draft, complete
   task fields and active approved context; release requires screening, a nonblank
   decision reason, valid frozen context and installed required capabilities.
4. Extend the existing receipt owner/table with manager-specific committed shape:
   no assignment/contributor is invented; exact task identity, immutable request
   digest, result, locked-context commitment and completion remain retained. Create
   binds project and full normalized payload; transition requests bind task/reason.
   Pending receipts have no result fields. Committed manager receipts require
   null assignment/contributor, result, completion and locked-context hash; create
   uses the deterministic all-null draft context hash. Existing assignment command
   shapes remain strict. Extend the existing typed AUTH facts with a closed create
   shape: reserved proposed task UUID, requested project and canonical full payload
   digest, no assignment. Explicit create guards bind all three through PREP.
   Screen/release use locked current-task facts; a committed receipt supplies an
   exact manager replay discriminator bound to action/key/task, admitting post-state
   replay only for that receipt. A new key cannot invoke a completed transition.
   Reserve before TASK/AUTH locks; choose one stored task UUID on duplicate create.
   Authorize the requested project/current resource before exposing replay or
   mismatch. Exact replay returns the original response only while current task
   state/context still matches; changed input returns 409 after fresh authority.
   Do not reset current state or select a newer guide on replay. A successor active
   guide does not invalidate replay against unchanged frozen task context. Changed
   task state/context conflicts after fresh authority; it never causes reselection.
5. For existing tasks, preserve TASK-before-AUTH locking, then load PROJECTS
   context through its existing port; trace guide activation and authority-change
   owners to prove no reverse edge. Creation locks canonical authority before
   inserting its new task, with deferred receipt references where required.
   Stage task mutation, exact AUTH decision, shared transition audit and completed
   receipt in one transaction. Denial, evidence failure or lost response cannot
   leave a partially created/ready task or a committed pending reservation.
6. Extend the existing typed transition audit with closed `TaskCreated` (null ->
   draft), `TaskScreened` (draft -> screening), and `TaskReleased` (screening ->
   ready) state-change events. Preserve source_type for creation and complete locked
   lineage for screen/release in bounded typed payloads, plus exact project/task/
   decision references. Assignment remains required only for assignment operations.
   Extend the existing hidden AUDIT projection and TASK evidence DTO to recognize
   these exact manager events with decision but no assignment; keep its fixed
   privacy-bounded fields. Null prior state is an event-specific creation exception,
   not a persisted task state. Reject extra payload keys, invalid source types,
   wrong references and malformed manager events without weakening generic event
   projection or assignment pairing. Use event-specific schema/SQL rules; preserve historical
   events and existing assignment-event rejection controls.

## Acceptance criteria

| Observable boundary | Named future proof and reachable arrangement |
|---|---|
| Project-manager create without a guide | `test_management_commands.py::test_create_draft_without_guide`: real project/admin grant, POST create; exact actor/project and one task/receipt/audit; no guide fixture required |
| Correct screening and release | `test_management_commands.py::test_screen_and_release_lock_approved_context`: existing real approved/active guide fixture, actual manager requests; exact policy UUIDs remain on READY and on a following real contributor claim |
| Wrong principal/project and revoked authority | `test_management_authority.py`: real scoped grants and stored foreign project/task; deny each action before mutation; existing AUTH audit targets project with exact resource digest, not task ID |
| Header validation | Missing/malformed/duplicate key cases for all three routes before identity resolution/product SQL; preserve token/rate-control boundary wording |
| Replay, changed input and stale state | `test_management_replay.py`: lost response, same key across managers/actions, changed project/payload/reason; advanced task conflicts while successor guide with unchanged frozen context replays exactly; no extra task/transition; new authority check on every retry |
| Atomicity | Parameterize create/screen/release: real PostgreSQL fault after staged mutation/audit and before completion: task state, receipt and success evidence all roll back, same key can subsequently succeed |
| Concurrency | Independent sessions: same-key create converges; same-action screen/screen and release/release permit one mutation; cross-action screen/release preserves legal serialization (screen first may permit both; release first denies release); grant revocation versus manager transition both orderings. Trace and probe guide activation lock order without mocking AUTH |
| Database preservation | `test_task_management_receipts.py`: additive migration retains existing claim/start receipts byte-for-byte; direct SQL rejects invalid closed action/state shapes and immutable-result rewrite, allows valid manager receipt with no assignment; pending create plus task commits together, missing task at commit rejects, assignment smuggling/null or malformed digest rejects |
| Exact request and audit evidence | Substitute create project/proposed task/payload digest through PREP and require rejection; prove exact source_type and full frozen lineage in audit and manager decision/no-assignment in hidden projection; omit one required lineage field to prove rejection |
| Superseded paths removed | Repository-wide caller scan plus required old guide/validation tests moved to the canonical operation; no compatibility alias or role-only mutation path |

Use the canonical isolated PostgreSQL runner for focused tests. Run Ruff,
module/AUTH boundaries, ownership/lane/structural validators, Commitrail, stale
wording and Markdown links. Full suite/coverage stays in hosted CI. Add one
mutation probe per critical newly asserted boundary (e.g. omitted authority,
missing receipt shape/state guard), not assertions that merely mirror code.

## Risk and review routing

- Risk class: L1, bounded authorization, transaction, schema and workflow change.
- Plan and implementation: security/architecture/reuse/senior-engineering;
  QA/test-delta/product-operations; CI integrity for schema/inventory/debt; docs.
- Human review focus: exact manager scope, transaction and lock order, safe replay,
  retained lineage/evidence and removal of the old mutating path.

## Evidence

Discovery traced the live routes, role-only TaskService methods, existing command
receipt assignment constraints, real project-manager fixtures, and ART lineage
fixture consumer. The acceptance table is proposed proof, not executed evidence. Plan review found
and corrected proposed-task binding, manager audit consumer shapes, mandatory
receipt custody, post-state replay admission, legal race outcomes, guide succession
replay semantics and the existing HTTP drill caller. No runtime proof is claimed.

## Reconciliation

- Current source: `27aac3d9`; 03C2 is delivered. Closed #435's roadmap move is
  retained as part of this branch.
- Next usable boundary after this change: bounded exact-authorized public task
  queues and remaining projections; public guide activation/intake admission stay
  separately sequenced. No claim that this change completes public integration.
- Remaining risk: every touched broad fixture must retain its original behavioral
  assertions while acquiring real authority and supplying explicit command keys.
