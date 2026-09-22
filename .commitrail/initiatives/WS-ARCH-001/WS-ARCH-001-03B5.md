# ARCH-03B5 — Replace contributor and manager work-context projections

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
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

- `backend/app/modules/tasks/schemas.py`: distinct composite response models reuse
  canonical TASK and PROJECTS facts without changing TASK's public API dependencies.
- `tasks/authorized_commands.py`, `tasks/router.py`,
  `tasks/service.py`: replace only work-context entrypoints and exclusive
  builders/schemas; reuse existing detail repository reads and locked resolver.
- `backend/tests/tasks/test_work_context.py`; affected work-context assertions
  in `tests/test_tasks.py`, `tests/tasks/test_project_display.py`,
  `tests/authorization/task_authority/{test_task_commands,test_public_surface}.py`,
  `tests/test_pre_submit_related_lock_order.py`, and `scripts/api_contract_e2e.py`.
- Register the new test module in the existing lane catalogue and equality test.
  No new public API module or ownership target; restore the unchanged public API
  dependency guard and remove the superseded import exception/registration.
- This record, ARCH parent/overview/plan/chunk map, current AUTH/CON/POL navigation,
  index, README, task specification, operating manual and roadmap reconciliation.

### Not allowed

New routes/actions/grants, changed AUTH evaluation or lock order, new policy
selection or resolver, command/replay mutation, submission activation, checker
execution, other locked-context/requirements/audit cutovers, migrations, retained
data deletion, compatibility aliases or alternate constructors. No dependency,
workflow, gate, coverage-floor or test-selection weakening. No physical economic
column removal: `TaskResponse` still serves task CRUD/detail and authorized
claim/start responses; `TaskCommandReplay.recover` and `.complete` preserve immutable
response payloads stored on `TaskCommandReceipt.response`. `WorkstreamTask` economic columns and affected
PROJECTS economic persistence remain retained. These shared consumers are outside
this work-context replacement; they are not justification for keeping its old fields.

## Design and decisions

Use frozen composite Pydantic response models in the existing `tasks/schemas.py`,
directly consumed by FastAPI. TASK's public API retains its existing dependency
guard. Reuse immutable owner facts without duplicating them or adding interfaces.
Separate `ContributorTaskWorkContext` and `ManagementTaskWorkContext` nest the
existing `ContributorTaskDetail`/`ManagementTaskDetail`, PROJECTS
`ProjectDisplayFacts`/`GuideDisplayFacts`, and the existing immutable
`GuidePolicySelection` values from `context.facts.activation_receipt.command.review`
and `.revision` (`policy_id`, positive `generation`, canonical `policy_hash`).
Also expose exact UUID `contribution_policy_version_id` from that validated
receipt command. The existing resolver already proves equality with the task
stamp. Do not read CON or expose economic rules. No new policy-reference class
or conversion to the superseded `policy_generation` field is needed.
Validate common project identity across task/project/guide facts. Add no raw
policy-body, artifact-custody, source-document-content or credential fields.

Contributor-only lifecycle facts contain current-actor assignment and
immutable `next_actions`: claim for unassigned READY, start for own CLAIMED,
otherwise empty, including own READY and later own-active states. Task status
lives only in `task.status`; do not duplicate it in lifecycle. Remove `can_submit`; do not advertise hidden Submission creation
or intake as an executable task command. Management receives its fixed management
task facts and the same locked guide/policy references, with no contributor
lifecycle or contributor action hints.

Replace the optional-project audience switch with explicit contributor and
management work-context methods (`contributor_work_context(task_id)` and
`management_work_context(project_id, task_id)`) on the same
`AuthorizedTaskCommands` object. Existing composition already consumes this
concrete owner; do not add unused Protocols or a new adapter. Bind actor only from the existing
constructor; management requires project and task UUIDs. Malformed internal
selectors raise existing `TaskValidationError` before SQL. Keep the existing transaction, `_locked_task`
AUTH path and `_load_locked_task_context` validation. Read 03B4 detail only after
current authority and complete historical custody pass, while existing locks
remain held. Missing projected facts raise existing `TaskNotFound("task not found")`
and roll back staged evidence: HTTP 404, `error.code=resource_not_found`,
`error.retryable=false`, through the existing handler. Do not mask it as a generic
500 or return partial context.
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
4. Historical guide, review/revision references and ContributionPolicy version
   remain exact after successor
   activation. Incomplete or substituted custody fails without result or committed
   allow evidence; no current-policy lookup or empty fallback references.
5. Results are detached/immutable, with exact project coherence and valid policy
   reference types; malformed selectors cause no SQL. Public serialization and
   OpenAPI agree with actual returned fields.
6. Existing task/assignment/AUTH/PROJECT locks and transaction order are retained;
   no task, assignment, command receipt, policy or TASK transition evidence is
   written by a read. The canonical AUTH allow decision is the sole expected
   write within the owner transaction, bound to the exact action/project/actor, with a project-scoped audit selector
   and exact TASK context bound by the authorization resource digest.
   Request identity/rate-control processing remains outside this claim. The existing real
   AUTH/ART work-context interleaving regression still passes.
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

The following tests implement the proof obligations; exact execution results
and review freshness belong in the PR.
Tests live in `backend/tests/tasks/test_work_context.py` unless qualified.

| Behavior atom | Named proof and independently observable assertion |
|---|---|
| Immutable exact contracts and project coherence | `test_work_context_contracts`: reject mutable/invalid nested fields, foreign task/project/guide IDs and malformed policy references; frozen mutation rejects; accepted values remain detached; contributor accepts exactly ContributorTaskDetail and manager exactly ManagementTaskDetail, rejecting audience substitution |
| Distinct public field sets | `test_work_context_openapi`: exact contributor/manager schemas, canonical task ID and guide/version placement; manager has no lifecycle; no obsolete work-context schema or economic/submission capability fields |
| Malformed selectors before SQL | `test_work_context_invalid_selectors`: both concrete methods reject each invalid UUID before transaction/execute/authority access |
| Actual actor-specific JSON and privacy | `test_work_context_public_projections`: valid granted actor/manager requests, stored non-null economic and private source sentinels, exact allowed returned keys/values; economics absent for both, management-only facts absent for contributor |
| Contributor executable hints | retained `test_project_grant_drives_claim_start_and_current_action_hints`: real READY -> claim -> start; false/true assignment ownership and claim/start/empty hints and absence of submit/precheck flags |
| All own-active states and ordinary draft denial | `test_work_context_owned_state_matrix`: real canonical claim plus fully locked status-only fixture for all nine string states, including owned draft/READY; persisted assignment/assignee/context preconditions asserted; only own CLAIMED advertises start. Ordinary unassigned draft separately returns existing 403 guard denial |
| Current authority and concealment | retained grant/revocation/suspension tests plus `test_work_context_project_scope`: stored foreign task, valid same-project manager control, wrong route project returns 404; valid locked task without required grant denies, with no assignment/task changes |
| Successful audit custody | `test_work_context_public_projections`: before/after task/assignment/receipt/transition state stable and exactly one AUTH allow per read with correct action, project selector and actor, plus canonical resource digest; existing AUTH-owner proofs cover exact task-context digest binding |
| Post-AUTH projection failure rollback | `test_work_context_projection_failure_rolls_back` for both methods/routes: wrapped real detail read proves exact nonmissing audience/task/project and staged allow in its transaction, then returns None; HTTP 404/resource_not_found/nonretryable; independent observer finds no committed new allow, task/assignment/receipt/transition unchanged |
| Exact historical guide and complete policy references | extend `tests/tasks/test_project_display.py::test_task_display_survives_guide_successor_for_contributor_and_manager`: assert stored original task stamps and a valid successor with a distinct ContributionPolicy version; both read results retain exact guide identity, both policy IDs/generations/hashes and ContributionPolicy UUID, using separate audience field sets |
| Invalid custody | retained `test_task_context_apis_fail_closed_when_locked_context_is_missing` and `test_task_context_apis_fail_closed_on_stale_locked_context_rows`, plus `test_work_context_missing_locked_context`: ordinary manager draft has actual authority before 422/task_locked_context_invalid; no successful allow commits |
| Both route error contracts | update `test_task_command_routes_preserve_structured_errors` owner method names only; preserve each public status/code/retry/request-ID assertion |
| Unchanged real lock interleaving | `tests/test_pre_submit_related_lock_order.py::test_work_context_task_lock_precedes_art_actor_lock`: update removed method call and canonical task.status assertion, retain real AUTH/ART sessions, order and completion assertions |
| Old path removal | `test_work_context_obsolete_symbols_absent`: deleted exclusive schemas, service builders and old optional-project method absent; current routes bind the separate owner methods; required old proof is updated, not removed |

Reuse real PostgreSQL fixtures in `tests.test_tasks`; persist economic sentinels
only after valid guide activation/screening so no invalid fixture masks a leak.
The nine-state fixture reuses the proven 03B4 fully locked task and active assignment
with status-only changes. Ordinary unassigned draft denial is distinct from a
fully locked owned draft and from manager draft's missing-policy failure.

Discriminating probes must fail at the intended assertion, not fixture setup:
add an economic field to the actual returned HTTP task projection and require
`test_work_context_public_projections` exact keys to fail; add contributor hints
to manager output and require the same audience assertion to fail; substitute
one valid-but-wrong historical review/revision reference or ContributionPolicy
UUID in the returned projection and require the persisted-reference comparison
to fail. These output substitutions test projection proof, not a claim to bypass
unchanged PROJECTS database guards. Exclude owned draft in the command and add a
claim hint for own READY in separate probes; the nine-state test must catch both.
Force assigned_to_current_actor true for unassigned READY and require the retained
grant test to reject the false ownership fact. Retain actual execution targets
and cleanup evidence for every credited probe.

Run focused isolated PostgreSQL/API tests plus required real lock regression,
Ruff, module/AUTH/test-structure boundaries, exact lane/ownership tests, Commitrail,
links and stale wording. Full unchanged hosted CI proves all tests and coverage
on final head, with no skipped/deselected tests and changed modules >=90%.

## Review findings

Plan repairs: PLAN-03B5-01 binds the required ContributionPolicy UUID;
PLAN-03B5-02 reuses `GuidePolicySelection`; PLAN-03B5-03 removes unused interfaces;
PLAN-03B5-04 removes duplicate status; PLAN-03B5-05 explicitly protects successful
AUTH evidence; PLAN-03B5-06 / QA-03B5-PLAN-02 cover all nine owned states.
QA-03B5-PLAN-01 supplies named atomic proofs; QA-03B5-PLAN-03 fixes the exact
post-AUTH failure/rollback contract; QA-03B5-PLAN-04 names retained economic
consumers and scopes the obsolete-symbol removal proof. These plan corrections preceded product implementation.

External review corrected the response-model boundary: composite transport models
belong in existing TASK schemas, so the public API dependency guard remains
unchanged; the attempted import exception and new API module are removed. The
successor history proof must establish a different ContributionPolicy version
before asserting both audiences retain the original locked UUID. The prior audit
test incorrectly queried a raw task resource. Existing AUTH intentionally records
a project selector and a resource digest binding TASK facts; proof uses that
privacy-safe selector. No production AUTH behavior changed.

Internal review repairs: QA-03B5-IMPL-01 updates the retained real AUTH/ART race's
status assertion to `task.status`; QA-03B5-IMPL-02 proves the original detail read
succeeds before injecting its missing-result failure; QA-03B5-IMPL-03 asserts
false ownership for unassigned READY and true ownership after claim/start.
DOC-03B5-01 keeps this child in the parent's completed predecessor sequence.

## Reconciliation

03B4 detail remains internal as a standalone read; this child consumes it in
already-live work context. Remaining 03B work is locked-context, requirements,
audit projections and dependency-gated assignment invalidation. ARCH-03C owns
new authority/public activation for those remaining surfaces. Retain all merged
queue/replay/suspension facts and do not imply those other cutovers are complete.
