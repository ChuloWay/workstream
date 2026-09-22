# ARCH-03B5 — Replace contributor and manager work-context projections

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Intended merge outcome: Existing authorized work-context routes use separate current contributor and manager contracts, with obsolete economic fields and submission capability removed.

## Intent

Continue the 03B projection work after merged #422 on main `dd77134c`.
Replace the affected development implementation rather than add another hidden
work-context path. Keep the existing live authorization and locked-policy
operation. Migration head remains `0025_task_command_replay`.

## Current behavior

`AuthorizedTaskCommands.work_context` already serves two live routes, using
`task.work_context.read` and `project.task.work_context.read`. Its transaction
locks TASK/assignment before AUTH and resolves historical PROJECTS custody via
`TaskService._load_locked_task_context`. The PROJECTS port validates complete
activation lineage; this must remain the only policy resolver.

Both audiences use `TaskWorkContextResponse` and its contributor-oriented
lifecycle. Its exclusive `TaskWorkerTaskContext` still carries `base_amount`,
`currency` and `payout_type`; `can_submit` is always false. Its builder creates
empty policy placeholders even though the locked resolver requires complete
stamps. 03B4 already supplies fixed contributor and manager task detail. Reuse
those facts and the PROJECTS detached display facts instead of another task
field list or another authorization evaluator.

## Bounded change

### Allowed

- `backend/app/modules/tasks/api/work_context.py` and `api/__init__.py`:
  current owner contracts and narrow ports, exported for existing composition.
- `tasks/authorized_commands.py`, `tasks/router.py`, `tasks/schemas.py`,
  `tasks/service.py`: replace only work-context entrypoints and exclusive
  builders/schemas; reuse existing detail repository reads and locked resolver.
- `backend/tests/tasks/test_work_context.py`; affected work-context assertions
  in `tests/test_tasks.py`, `tests/tasks/test_project_display.py`,
  `tests/authorization/task_authority/{test_task_commands,test_public_surface}.py`,
  `tests/test_pre_submit_related_lock_order.py`, and `scripts/api_contract_e2e.py`.
- Exact new-module registration in existing lane catalogue/ownership partition,
  digest/allowlist and their equality/neighbor tests. Preserve all earlier targets.
- This record, ARCH parent/overview/plan/chunk map, current AUTH/CON/POL navigation,
  index, README, task specification, operating manual and roadmap reconciliation.

### Not allowed

New routes/actions/grants, changed AUTH evaluation or lock order, new policy
selection or resolver, command/replay mutation, submission activation, checker
execution, other locked-context/requirements/audit cutovers, migrations, retained
data deletion, compatibility aliases or alternate constructors. No dependency,
workflow, gate, coverage-floor or test-selection weakening. No physical economic
column removal: unaffected command receipts and other surfaces still consume
those columns and remain explicitly outside this replacement.

## Design and decisions

Use one new owner API module with frozen Pydantic result contracts directly
consumed by FastAPI, rather than duplicate transport and owner field lists.
Separate `ContributorTaskWorkContext` and `ManagementTaskWorkContext` nest the
existing `ContributorTaskDetail`/`ManagementTaskDetail`, PROJECTS
`ProjectDisplayFacts`/`GuideDisplayFacts`, and immutable review/revision policy
references (`policy_id`, positive `policy_generation`, canonical `policy_hash`).
Validate common project identity across task/project/guide facts. No raw policy
bodies, artifact references, source documents or credentials enter these results.

Contributor-only lifecycle facts retain status, current-actor assignment and
immutable `next_actions`: claim for unassigned READY, start for own CLAIMED,
otherwise empty. Remove `can_submit`; do not advertise hidden Submission creation
or intake as an executable task command. Management receives its fixed management
task facts and the same locked guide/policy references, with no contributor
lifecycle or contributor action hints.

Replace the optional-project audience switch with explicit contributor and
management work-context methods on the same `AuthorizedTaskCommands` object,
implementing the two narrow public ports. Bind actor only from the existing
constructor; management requires project and task UUIDs. Reject malformed
internal selectors before SQL. Keep the existing transaction, `_locked_task`
AUTH path and `_load_locked_task_context` validation. Read 03B4 detail only after
current authority and complete historical custody pass, while existing locks
remain held. Missing projected facts fail closed and roll back staged evidence.
No new service/factory or independent permission check is needed.

Existing routes use these separate contracts/methods with unchanged action IDs,
dependencies and error translation. This is replacement of already-authorized
work context, not activation of the remaining proposed 03C actions. Old exclusive
schemas/builders/method are deleted; callers and tests move together. Task facts
use the existing canonical `task_id`; guide version lives in `guide.version`,
not a duplicate task field. No aliases preserve the superseded shape.

## Acceptance criteria

1. Both existing routes expose distinct exact schemas. Contributor task excludes
   management source/actor data; both exclude obsolete economic fields. Manager
   gets its declared source/assignment display facts, not contributor hints.
2. Contributor READY/CLAIMED/in-progress hints follow the existing guarded
   assignment state; no submit/precheck capability or fabricated entitlement.
3. Existing exact-project Submitter/Project Manager authority, visibility,
   foreign-project concealment, revocation/suspension and structured errors stay
   enforced. A manager is not made a contributor; token roles are not authority.
4. Historical guide and review/revision references remain exact after successor
   activation. Incomplete or substituted custody fails without result or committed
   allow evidence; no current-policy lookup or empty fallback references.
5. Results are detached/immutable, with exact project coherence and valid policy
   reference types; malformed selectors cause no SQL. Public serialization and
   OpenAPI agree with actual returned fields.
6. Existing task/assignment/AUTH/PROJECT locks and transaction order are retained;
   no task, assignment, receipt, policy or lifecycle evidence is written by a read.
   The existing real AUTH/ART work-context interleaving regression still passes.
7. Old exclusive work-context schemas/builders/callers are absent. Required
   historical-context/privacy/authorization tests remain, updated for the new
   contract rather than deleted. Remaining shared economic consumers are named.

## Risk and review routing

Risk: L1 (public response replacement and authorization-adjacent composition).
Plan: security/architecture/reuse and QA/test-delta/product-operations, including
fixture reachability. Implementation: same tracks, docs and CI integrity for
exact registrations. Human focus: same live authority/lock sequence, distinct
actor fields, immutable historical custody and complete removal of old shapes.

## Evidence

Future `tests/tasks/test_work_context.py` must cover exact immutable contracts,
malformed-selector no-SQL behavior, distinct OpenAPI contracts, and real public
contributor/manager results with persisted private/economic sentinel values.
Use real grant-backed READY -> CLAIMED -> in-progress operations; keep ordinary
unassigned draft denial distinct from any valid owned-state fixture. Verify
stored task/assignment preconditions before result assertions.

Retain and update existing real authority denial/error tests, historical successor
read tests and `test_pre_submit_related_lock_order` work-context race. Add a
failure after authorization (e.g. unavailable detail) and independently inspect
that staged allow evidence rolled back with no lifecycle/assignment changes.
A stored foreign task and valid same-project control must exercise manager scope;
missing/revoked-grant cases must use otherwise valid locked tasks, so policy
failure cannot mask missing authority.

Discriminating probes: reintroduce an economic response field and require the
exact shape proof to fail; add a contributor action hint to the manager response
and require rejection; bypass locked-context validation with a substituted policy
reference and require the historical-reference proof to fail. Preserve each
probe's actual execution target and intended assertion, not a fixture/setup error.

Run focused isolated PostgreSQL/API tests plus required real lock regression,
Ruff, module/AUTH/test-structure boundaries, exact lane/ownership tests, Commitrail,
links and stale wording. Full unchanged hosted CI proves all tests and coverage
on final head, with no skipped/deselected tests and changed modules >=90%.

## Review findings

Plan review pending. No product implementation has begun.

## Reconciliation

03B4 detail remains internal as a standalone read; this child consumes it in
already-live work context. Remaining 03B work is locked-context, requirements,
audit projections and dependency-gated assignment invalidation. ARCH-03C owns
new authority/public activation for those remaining surfaces. Retain all merged
queue/replay/suspension facts and do not imply those other cutovers are complete.
