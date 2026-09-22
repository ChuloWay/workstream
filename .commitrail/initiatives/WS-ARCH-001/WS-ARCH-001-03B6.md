# ARCH-03B6 — Explicit task locked-context projections

- Initiative: `WS-ARCH-001`
- Durable disposition: Planned
- Intended merge outcome: one historical context resolver supplies explicit
  management, operational and audit projections, with no parallel old response.

## Intent and current behavior

After 03B5, complete policy locks and historical validation already exist.
`TaskService._load_locked_task_context` validates every TASK stamp against the
PROJECTS activation receipt; it must remain the sole resolver. The current
`TaskLockedContextResponse` and `_locked_context_response` expose one mutable,
operator-labelled shape, though `/tasks/{task_id}/locked-context` actually uses
token-role admin or creator-manager checks. No canonical Operator/Audit action
is live for this read. The adopted 03B/03C contracts require separate projections
and assign live authority/public cutover to 03C.

This child completes only locked-context projection composition. Requirements
translation and audit-event history are different reads and remain next work;
assignment invalidation still requires the shared committed-claim dependencies.

## Bounded change

### Allowed

- `backend/app/modules/tasks/schemas.py`: replace the old locked-context response
  with frozen, strict, extra-forbidden actor-specific composite models; make the
  existing post-submit summary deeply immutable.
- `tasks/service.py`: explicit scoped read methods and constructors sharing the
  existing resolver; replace the old projection builder and delegate the retained
  manager-capable route to the same management implementation.
- `tasks/repository.py`: exact project/task lookup using the existing task owner;
  no new persistence or query framework.
- `tasks/router.py`: name/type of the existing management response only.
- `backend/tests/tasks/test_locked_context.py`, affected `tests/test_tasks.py`
  assertions and the existing history-successor fixture if needed; register the
  new module in `backend/scripts/test_lane_catalogue.py` and its equality test.
- Current ARCH overview/plan/chunk map/03B parent, current AUTH/CON/POL navigation,
  index, README, roadmap, task specification, glossary/data-model and operating
  manual sections describing this boundary. Local roadmap exports if present.

### Not allowed

- No AUTH catalogue/permission/PREP changes or new public routes. No token role
  selects an operational or audit projection. No generic audience parameter.
- No migrations, policy writers, current-policy substitution, checker execution,
  requirements translation, audit-event reads, invalidation or data deletion.
- No PROJECTS imports in TASK public API, guard exceptions, compatibility aliases
  or parallel response implementation. `tasks/api/**` and its guards stay unchanged.
- Do not expand ART's `TaskLockedProjectContextReferences` to serve this different
  read: its existing submission consumers need the narrow request lineage.

## Design and decisions

Composite models belong in existing TASK schemas, as in 03B5. They are not new
cross-module owner facts, so no public API wrapper or abstraction is necessary.
All three models share exact scalar references: task/project IDs; guide version;
source snapshot ID/hash; effective submission-policy ID/hash; pre-submit policy
ID/bundle hash; post-submit policy ID/version/hash; review and revision
ID/generation/hash; ContributionPolicy version UUID. Keep existing wire member
names. UUIDs must be UUIDs, hashes canonical SHA-256 tokens, generations positive,
and versions nonempty. Defaults must never fabricate missing lineage.

`ManagementTaskLockedContext` additionally contains the existing bounded
post-submit summary (schema version, default/required/warning/execution checker
IDs and blocking severities), with immutable tuples. `OperationalTaskLockedContext`
and `AuditTaskLockedContext` contain references only. Neither exposes bodies,
instructions, source metadata, actor identities, evidence, storage URIs or money.
Distinct result types preserve future permission-specific composition even when
the two reference-only field sets match. Shared scalar construction is permitted;
constructors are explicit, never role-selected redaction of a broader response.

Hidden `read_management_task_locked_context`, `read_operational_task_locked_context`
and `read_audit_task_locked_context` take exact UUID project/task selectors.
Reject malformed selectors before SQL. Exact project filtering occurs in the task
lookup before historical resolution; missing and foreign tasks both raise existing
`TaskNotFound`. Take the TASK row lock before the existing PROJECTS custody locks.
Use the caller's transaction; never flush, commit, rollback or create a nested
transaction. A caller's pending writes are not implicitly flushed.

The existing route still checks its current role and creator scope before using
the canonical management projection. This explicitly retained authority wrapper
is a dependency for 03C, not a new compatibility route or a claim that canonical
manager/Operator/Audit authority is complete. Preserve current manager access and
denials. Remove the superseded response class and builder and update their tests.
The new operational/audit methods are internal only, with no OpenAPI activation.

## Acceptance and proof

1. Exact frozen field contracts: valid constructors succeed; malformed UUID/hash,
   empty version, nonpositive generation, extra private field and mutable nested
   collections fail. Operational/audit models reject management summary input.
2. Real PostgreSQL project/task scope: valid fully activated/screened task is a
   successful control for all three methods; stored foreign task and missing task
   conceal identically. Resolver is not called for either missing/foreign case.
3. Historical identity: activate a valid successor with a distinct ContributionPolicy
   version using the existing test fixture. All three reads retain the original
   exact task stamps; management summary remains that original compiled policy.
4. Invalid custody: valid control first, then permitted TASK post-policy-body
   mismatch causes the existing coded failure for every read. Draft missing locks
   also fail. Immutable PROJECTS data is not altered to evade its database guards.
5. Transaction/locks: caller owns rollback, unflushed sentinels remain pending,
   flushed caller edits remain uncommitted; TASK acquisition precedes PROJECTS.
   A real two-session TASK-lock test verifies the read waits and resolves the
   committed task context after the lock is released.
6. Retained HTTP boundary: existing manager success, worker denial, foreign creator
   concealment and structured domain errors remain; only the management schema is
   reachable. Operational/audit references appear nowhere in OpenAPI. Old exclusive
   response/builder symbols are absent, while required behavioral tests remain.

Future tests live in `tests/tasks/test_locked_context.py`. Use existing real
`tests.test_tasks` setup, canonical guide activation and ready-task helpers.
Do not use a fake policy resolver for the successful PostgreSQL controls.
Discriminating probes: remove project filtering and prove foreign-task rejection
fails; inject management summary into an operational response and prove exact
fields fail; substitute successor policy identity and prove the history assertion
fails after a distinct valid successor is established.

Shared checks include Ruff, the original TASK/PROJECTS public dependency guards,
module boundaries, lane catalogue parity, affected HTTP contracts, links, stale
wording and Commitrail. Use `backend/scripts/run_isolated_tests.py` for PostgreSQL
with owned local resources and cleanup evidence. Migration head is
`0025_task_command_replay`. Hosted CI must execute the complete selected suite
with zero skips/deselections and preserve existing coverage gates; changed TASK
modules remain above 90%. Exact commands/results belong in PR evidence.

## Risk and review routing

- Risk: L1 (policy identity, privacy and owner composition).
- Plan review before code: architecture/security/reuse and QA/product operations.
- Implementation review: those tracks plus test delta, documentation, senior
  engineering for simplicity/locking, and CI integrity for test registration.
- Human focus: actor-specific field sets, preserved historical validation,
  retained authority dependency and absence of premature Operator/Audit access.

## Reconciliation

Base: merged #423 at `40d15d3d`. Only open #410 is CI impact reporting; this child
does not modify CI workflows or impact selection. No spreadsheet exports found
during initial discovery; check again when reconciling the roadmap.
Next: requirements and task audit-evidence projections, then dependency-gated
invalidation and 03C exact AUTH/public activation. This child does not mark
the whole 03B parent complete.
