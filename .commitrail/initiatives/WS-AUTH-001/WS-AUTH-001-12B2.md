# Chunk Contract: WS-AUTH-001-12B2 - Exact Setup Finalization Authority

- Initiative: `WS-AUTH-001`
- Durable disposition: Planned
- Intended merge outcome: Authorize exact hidden setup finalization and make POL-04B the next usable boundary.

## Intent

POL-04A2 and AUTH-12J are complete. POL owns hidden atomic finalization and
its database constraints; AUTH owns the preceding component projection
adapters. This change supplies the concrete authorization adapter for the
existing finalization port and activates only `project.setup_run.update` for
fixed `workstream.project.setup`.

A caller must prove current service authority for exactly the finalization
whose locked facts become an immutable receipt. Production worker routing
remains outside this chunk: POL-04B owns the later live one-call cutover.

## Bounded change

### Allowed files

- This change record, AUTH `OVERVIEW.md`, `.commitrail/INDEX.md`, POL overview,
  `docs/spec_authorization_service.md`, and `docs/roadmap_status.md` for the
  resulting capability and next boundary.
- `backend/app/modules/authorization/project_setup_finalization.py` and
  `domain/project_setup_finalization.py` (new purpose-specific adapter and
  exact resource/preparation/replay rules).
- `backend/app/modules/authorization/catalogue.py`, `runtime.py`, `kernel.py`,
  `prepared.py`, `domain/prepared_service.py`, and
  `prepared_projection_replay.py` for narrow shared PREP integration.
- `backend/app/adapters/auth/__init__.py` for the explicit composition-root factory.
- `backend/app/modules/authorization/api/project_setup_finalization.py` and
  `backend/app/modules/projects/guide_compilation/finalization.py` only to
  transmit the already-derived correlation ID in the preparation locator.
- `backend/tests/authorization/setup_finalization/` (new bounded proof modules),
  `backend/tests/projects/guide_compilation/finalization/` (locator updates and
  real-adapter PostgreSQL integration), existing exact authorization catalogue
  assertions and architecture tests affected by the new action availability.
- `backend/scripts/test_lane_catalogue.py`, `backend/tests/test_ci_lane_catalogue.py`,
  `.github/workflows/backend.yml`, and affected exact ownership/boundary records
  only for additive registration and coverage enforcement.

### Prohibited changes

No HTTP or Celery call-graph cutover, worker edits, provider calls, new
projection execution, policy/compiler behavior, human authority, service
provisioning shortcut, migration, settlement, review/contribution behavior,
serialized handles, compatibility path, or generic setup-ledger capability.
The finalizer remains unavailable by default; the explicit concrete AUTH
factory is exercised by integration callers until POL-04B supplies live wiring.
No thresholds, selection requirements, or existing assertions are weakened.

## Design and implementation plan

1. Add required `correlation_id` to the public locator and supply the existing
   deterministic finalization correlation in POL. Preparation happens before
   locked facts are available; independently derived operation and correlation
   UUIDs cannot be reconstructed from the locator's current operation alone.
   Do not substitute the operation ID as the audit correlation: migration 0010
   requires exact receipt/audit correlation equality.
2. Define frozen, closed preparation and final resource contexts. Recompose the
   complete public finalization facts and canonical digests; validate exact
   deterministic receipt/operation/correlation identity, classification/output
   shape, actor/link identity, and locator agreement. The final resource is
   `project_guide_setup_finalization`, never the old generic setup mutation
   context. Reject the legacy `ProjectSetupRunMutationResourceContext` on
   direct kernel, human PREP and service PREP paths for this active action.
   AUTH consumes locked facts; it does not query private POL owners.
3. Reuse `fixed_service_prepared_authorization`, its canonical service identity
   admission, authority row locks, opaque single-use handle and caller-owned
   root transaction. Add one exact finalization binding to shared PREP and one
   exact service-resource guard. Human and unrelated-service paths deny, even
   with broad project grants. Do not alter existing projection semantics.
4. Implement `PreparedSetupFinalization` with consume and replay paths. New
   consumption writes the existing canonical allow evidence and returns every
   field of the public authority receipt. Replay requires freshly prepared
   current authority and exact stored decision identity/envelope/digest; it
   creates no second allow event and consumes/closes its handle once.
5. Export the explicit adapter factory through `app/adapters/auth/__init__.py`. Keep
   live POL wiring and the unavailable default unchanged. Update current docs
   only after implementation and proof establish the new hidden capability.

## Acceptance criteria

| Boundary | Required proof and custody |
|---|---|
| Exact service availability | Every service identity against finalization and human denial for the active action; planned downstream actions remain unavailable |
| Facts and preparation | Every locator, actor/link, operation/correlation, project/guide/source, setup generation, compilation identity, classification and output digest is bound; scalar mutations fail with valid controls |
| Handle lifetime | Consume/replay at most once; close, copy/pickle, session swap, nested or replaced root, commit and rollback invalidate; no provider I/O or serialized transport |
| Concrete new finalization | All three result classifications succeed with real service identity, real projection authority, exact allow event and immutable receipt in one PostgreSQL transaction |
| Replay | Identical replay preserves receipt and evidence counts; missing/foreign/mutated historical decision fails; freshly revoked actor/link denies despite a previously successful receipt |
| Revocation ordering | Independent sessions use production `ActorLifecycleService` and `IdentityLinkLifecycleService` (or their exact existing composition), with an authorized admin; revocation-first denies and finalization-first serializes on profile/link locks, observed through PostgreSQL activity rather than sleeps |
| Atomic failure | Evidence-write failure, invalid authority receipt or closure failure leaves no setup mutation, finalization receipt or orphan allow after rollback |
| Hidden boundary | Default finalizer remains denied; no live route/worker reference to the factory; component projections retain their own actions |
| Gate integrity | Explicit node registration, unchanged global 78% floor and repository floors, at least 90% coverage for new/materially changed AUTH surfaces |

Tests must reach their named assertion with complete persisted prerequisites.
The existing `pg_support.database_case` and `pg_prerequisites` supply actual
compiled/projected parents through AUTH-12J. Integration constructs the new
concrete adapter explicitly in the same caller session instead of using the
old strict finalization test port. Revocation tests target the persisted setup
service actor/link through the production lifecycle services and retain separate
successful non-revoked controls for actor and link cases. Seed authorized admin
prerequisites; do not replace the lifecycle path with raw SQL status updates.
Negative database cases retain valid controls and compare durable state after
rollback. Unit doubles claim only contract/ordering behavior. PostgreSQL tests
own storage, revocation and independent-session serialization claims. Each
critical assertion has a discriminating mutation or concrete counterexample.

### Planned test symbols and assertion ownership

The symbols below are future implementation tests, not executed evidence.
AUTH unit modules live in `backend/tests/authorization/setup_finalization/`;
PostgreSQL modules live in `backend/tests/projects/guide_compilation/finalization/`.

| Planned symbol | Variants and compatible custody |
|---|---|
| `test_catalogue.py::test_finalization_action_service_matrix` | Every service identity against finalization action/permission: only PROJECT_SETUP succeeds. PROJECT_SETUP action/permission substitutions retain existing valid projection pairs and deny invalid/mismatched pairs; exact catalogue assertion and real PREP/kernel service execution |
| `test_catalogue.py::test_human_and_direct_kernel_finalization_denied` | Human project manager/admin and fixed-service direct-kernel calls deny for exact and legacy resources; pure service |
| `test_resource_context.py::test_each_finalization_fact_is_bound` | Exhaustive field inventory below, each with a valid baseline; pure validated-resource and adapter/PREP consumption |
| `test_resource_context.py::test_preparation_locator_and_principal_are_bound` | Project, operation, correlation, actor, link, request and scope substitution; exact public locator -> prepared binding -> consume; pure service |
| `test_resource_context.py::test_deterministic_finalization_identity_is_exact` | Receipt, operation and correlation independently forged; source seed control preserved; pure contract |
| `test_resource_context.py::test_policy_tuple_and_transition_shape` | Three valid classifications; partial nullable tuples and conflicting classification/outcome reject; pure contract |
| `test_prepared.py::test_exact_resource_kinds_cannot_be_substituted` | Legacy setup context and projection contexts cannot consume finalization; finalization context cannot consume projection/other action; pure PREP/kernel |
| `test_prepared.py::test_handle_lifetime_is_bound` | Consume then consume/replay; replay then consume/replay; closed context; different session/root; nested, committed, rolled-back, inactive/replaced transaction; pure service, backed by PG cases below |
| `test_adapter.py::test_prepared_finalization_is_process_local` | Copy, deepcopy, pickle and arbitrary handle replacement deny; pure contract |
| `test_adapter.py::test_prepare_consume_and_close_fail_closed` | Prepare/consume/evidence/exit exceptions keep public denial mapping and close once; caller exceptions are not remapped; pure service |
| `test_replay.py::test_historical_decision_envelope_is_exact` | Missing/wrong decision and one-at-a-time event domain/type/actor-ref/actor/action/permission/project/resource/request/correlation/allow/digest substitutions; pure replay, not storage custody |
| `test_authorization_postgresql.py::test_concrete_finalization_is_atomic` | guide_blocked, draft_ready, draft_ready_with_warnings; real compilation + AUTH12J projections + concrete adapter + receipt + exact audit row in caller transaction |
| `test_authorization_postgresql.py::test_concrete_replay_is_exact` | Unchanged receipt/result and event counts with current valid authority; real PostgreSQL |
| `test_authorization_postgresql.py::test_revoked_service_denies_new_and_replay` | Actor suspension/deactivation and link revocation through production lifecycle services; both new finalization and stored-receipt replay; valid non-revoked controls |
| `test_authorization_postgresql.py::test_finalization_failure_rolls_back_all_effects` | Evidence insertion failure, invalid returned authority receipt, close failure and caller rollback; durable setup/receipt/allow-event comparisons with actual PG writes before failure where relevant |
| `test_authorization_postgresql.py::test_stored_replay_decision_substitution_denied` | Stored foreign/missing/mismatched decision fixture reaches replay validation; explicitly bounded transactional tampering where append-only constraints prohibit a naturally persisted invalid row |
| `test_authorization_concurrency_postgresql.py::test_finalization_and_revocation_serialize` | Actor and link lifecycle x revocation-first/finalization-first; distinct sessions/PIDs, named lock waiter and exact blocker, retained valid controls and cleanup of tasks |
| `test_structure.py::test_finalization_authority_has_no_live_reachability` | Factory explicit, default denial retained, no HTTP/Celery/provider reference; structural and default-service tests, not live execution proof |
| Existing catalogue and hosted evidence tests | Exact new module registration, all canonical nodes complete once, aggregate and new-owner coverage floors unchanged |

The exhaustive fact-mutation inventory is every field of
`ProjectSetupFinalizationFacts`: `project_id`, `guide_id`, `guide_version`,
`source_snapshot_id`, `source_snapshot_hash`, `setup_run_id`, `setup_generation`,
`celery_task_id`, `source_state_digest`, `operation_id`, `correlation_id`,
`finalization_id`, `attempt_id`, `request_operation_id`, `provider_idempotency_key`,
`compilation_id`, `canonical_input_hash`, `result_hash`, `result_schema_version`,
`compilation_agent_name`, `compilation_agent_version`, `component_hashes`,
`result_classification`, `setup_outcome`, `sufficiency_operation_id`,
`sufficiency_report_id`, `sufficiency_output_digest`, `artifact_policy_operation_id`,
`artifact_policy_id`, `artifact_policy_output_digest`. Each component hash key
gets an independent mutation. Tests assert the expected inventory matches the
public dataclass so future fields cannot silently escape proof.

For a field whose representation requires coupled values, distinguish malformed
shape rejection from a valid alternate fact vector reaching AUTH consumption or
replay; an earlier dataclass error is not proof of the later binding guard.
Unbound preflight facts are supplied only after POL obtains its serialization
locks; prove their exact digest appears in allow evidence and that changing a
fact invalidates historical replay, rather than claiming preflight knew them.

## Risk and review routing

Risk: L1 authorization and immutable audit custody.

Use focused local tests and lint; hosted CI owns PostgreSQL, independent-session
races, full-suite reconciliation and coverage because this workstation is
resource constrained. New test modules stay below 500 lines with bounded helpers.
Future implementation test paths above are planned and do not claim execution.

Before implementation, run architecture/security and QA/product plan review,
including correlation feasibility, exact resource dispatch and fixture reachability.
Implementation reviewers cover architecture, security, QA/test delta,
product/operations and reuse; add CI integrity for registration/gates and docs
for capability updates. Lead owns shared checks and freezes a clean exact target.

Human review focus: only exact finalization ledger authority becomes available;
POL still owns product state and the future live cutover. The user owns merge.

## Evidence

The test matrix above defines planned proof; no runtime execution is claimed.

## Durable outcome

Planned. On successful delivery, mark this boundary Complete and point to
POL-04B as the next usable boundary. Do not start POL-04B automatically.
