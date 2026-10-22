# Project points unit creation — authorized Finance command and operator script

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Finance Authority can create a project's `project_points` compensation unit through a new authorized internal command, and a local operator script enables project points end to end (adapter actor, unit, binding) without direct database writes.

## Intent

A ContributionPolicy can award project points only if its definition references
an active `ProjectCompensationUnit` and an active `project_points` adapter
binding. Bindings already have an authorized internal command, but nothing
could create a unit: the only creators were test fixtures and the PILOT-04
probe, which insert rows directly. A project therefore could not publish a
points policy through supported paths. Flow wants every accepted task in its
projects to award Flow Points (unit code `FLOW`), starting with the local
agent-loop stack.

## Current behavior

- `ProjectCompensationUnit` (`backend/app/modules/contributions/models.py`) and
  its `guard_project_compensation_units()` trigger admit only active inserts.
  `ProjectCompensationUnitInput` documents "no lifecycle command".
- `ContributionPolicyService._lock_resources_and_build` rejects a definition
  whose unit row is missing, so publication needs a unit.
- `AdapterBindingService.create` (`backend/app/modules/compensation/service.py`)
  is reachable only through `compensation_adapter_binding_authorization`; no
  route or script composes it.
- `tests/projects/guide_activation/compensation_fixtures.py::create_binding`
  and `experiments/pilot04_external_checker_runtime/public_guide_setup.py`
  create the unit by direct insert.

## Bounded change

### Allowed

- AUTH: `ActionId.CONTRIBUTION_COMPENSATION_UNIT_CREATE`
  (`contribution.compensation_unit.create`) mapped to the existing
  `compensation.policy.manage` permission under new action owner
  `project-points-unit-creation` (this record's slug), active for human Finance Authority only. It joins the ContributionPolicy
  mutation family (`domain/contribution_policies.py`) with its own exact
  resource context, `ProjectCompensationUnitCreateResourceContext`, so the
  existing kernel, PREP, grant filter, scope lock and audit-digest wiring apply.
  Prepared-parsing, audit-target and resource-union hooks accept it. The four
  adapter-binding catalogue rows are folded into one comprehension so
  `catalogue.py` stays within the 1,200-line structure limit.
- AUTH public facts `CompensationUnitCreateAuthorityFacts` and the CON → AUTH
  translation in `app/adapters/auth/contribution_policies.py`.
- CONTRIBUTIONS: `app/modules/contributions/units/` (service and the
  `ProjectCompensationUnitCreationEvent` model), public request/result/facts in
  `api/compensation_units.py`, repository helpers, and
  `project_compensation_unit_service` composition.
- Migration `0058_compensation_unit_create`: the action/permission pair in
  `ck_audit_events_authorization_action_evidence`, and the guarded
  append-only `project_compensation_unit_creation_events` table.
- `backend/scripts/provision_project_points.py`.
- Registrations: Alembic head, schema fingerprint and resettable tables,
  catalogue fixtures, MCP authorization-context enum, behavior-ownership
  partition (`COMPENSATION_UNIT_TARGETS`), identifier classification, test lanes.
- Docs: compensation spec, data model, roadmap, operating manual, local agent
  loop guide.

### Not allowed

- No public route or CLI command for units or bindings.
- No money units, unit retirement or other unit lifecycle state.
- No change to policy validation, publication, guide activation, awards or the
  existing binding command.
- No relaxation of the unit trigger; existing direct-insert fixtures stay.

## Design and decisions

**Hidden, like bindings.** Units and bindings together are project
compensation enablement. Binding administration is deliberately internal
(roadmap: "Compensation-binding administration remains internal"), and a unit
is useless without a binding, so the unit command follows the same boundary.
Exposing both publicly is a later product decision.

**Finance and `compensation.policy.manage`.** The spec makes CONTRIBUTIONS the
owner of "policy and unit truth"; the policy permission already belongs to
Finance Authority. Reusing it avoids a new permission and role mapping.

**Points only.** The data model also defines money units, but enabling a money
unit is a payment decision. The request, AUTH facts, resource context and
event table admit only `project_points`.

**Resource is the project.** A unit has a natural key and no record ID, so the
authorization resource is `resource_type="project"` bound to
`(instrument_type, unit_code)` and the operation digest. This reuses the
existing audit resource vocabulary; only the action/permission pair is new.

**Replay.** An immutable creation event, unique by operation and by unit,
records the request digest. Every call takes the AUTH scope lock first. A
stored identical request returns the original result after that fresh
authority check; a changed request under the same operation conflicts. A
second creation of an existing unit conflicts before authority is consumed.
Rejected: storing the operation on the unit row (it would mix custody into the
unit and still need an update path).

**Operator script.** Each step commits separately, so reruns report existing
state; a deterministic UUIDv5 operation ID turns a crash between the existence
check and creation into an exact replay. An active binding with another adapter
actor or route key is reported as `active_binding_mismatch`. The script refuses
production-like environments (the default `production` included). The adapter
actor is created through `POST /api/v1/service-actors` with the existing
helper, not in-process. The default unit is `FLOW` ("Flow Points") and the
route key `flow_points.local`. Units are project-scoped, so each Flow project
gets its own `FLOW` unit; Workstream does not aggregate them.

## Acceptance criteria

- [x] Finance Authority with a project or system grant creates an active points
      unit and an immutable creation event; allowed evidence is audited with
      the new action.
- [x] Project Manager, Operator and Finance scoped to another project are
      denied with no unit; foreign and missing projects give the same denial.
- [x] Identical replay returns the stored result and needs current authority;
      changed replay, duplicate unit, invalid code or instrument, unknown
      project and deny-default composition create nothing.
- [x] Creation events reject update, delete and truncate, and must match the
      unit creator.
- [x] The script creates missing actor/unit/binding, reports existing state on
      rerun, handles actor-only and unit-only partial state, and fails with
      bounded output on denial or missing prerequisites.

## Risk and review routing

- Risk class: `L1` (new authorization action, payment-adjacent configuration,
  migration).
- Required reviewers: `security`, `architecture`, `qa`.
- Human review focus: Finance owning unit creation under
  `compensation.policy.manage`; keeping units internal; points only; the
  project as the authorization resource.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Service, replay, conflicts, immutability | `tests/contributions/test_compensation_unit_create_postgresql.py` | Pass on PostgreSQL 16 | — |
| Real AUTH allow/deny, concealment, audit, fresh replay authority | `tests/contributions/test_compensation_unit_authority_postgresql.py` | Pass on PostgreSQL 16 | Denial evidence is not asserted because it is staged in the rolled-back transaction |
| AUTH contracts, PREP custody, CON → AUTH translation | `tests/authorization/contribution_policies/test_compensation_unit_contracts.py` | Pass | — |
| Operator script full, rerun and partial states | `tests/test_provision_project_points.py` | Pass on PostgreSQL 16 | The adapter-actor HTTP call is replaced in tests; the route itself is covered by `tests/test_auth.py` |
| Catalogue, audit vocabulary, boundaries, migration graph | `tests/authorization`, `tests/architecture`, `tests/test_alembic.py`; behavior-ownership, module, AUTH-import and test-structure validators | Pass | — |

## Review findings

Focused security, architecture (with reuse) and QA/test-delta reviews; no
blocking finding. Dispositions:

- Security: the script could act as any named Finance Authority against a
  non-local database. Fixed: it refuses production-like environments.
- Security: the database does not require a creation event for every unit, so
  a direct insert still yields a usable unit. Accepted for now: a deferred
  "unit needs an event" trigger would break the existing fixtures and the
  PILOT-04 probe that insert units directly; migrating them is follow-up work.
- Security: an identical replay re-checks authority through the scope lock,
  which records denials but no allow evidence (policy replay uses an audited
  read). Accepted; there is no unit read action to audit.
- Security/architecture/QA: the script reported any active binding as ready.
  Fixed: a different adapter actor or route key is a mismatch.
- Architecture: `PolicyAction` was widened to the unit action. Fixed with a
  separate `CompensationUnitAction` literal, used only where both are valid.
- Architecture: docs said none of the three prerequisites had a public route,
  a schema docstring was stale, and the owner ID did not follow catalogue
  practice. Fixed; the owner is now this record's slug.
- Architecture: add a production composition function for
  `AdapterBindingService`. Declined: the binding command stays uncomposed in
  production as CP03B intended; the script composes it like the existing test
  fixture and lifecycle script.
- QA: the money-instrument test passed without the instrument check, and the
  rollback test failed before any insert. Added `money`/`USD`, an event-write
  failure after the unit flush, concurrent same- and distinct-operation races
  with consumed-authority counts, non-Finance reuse of a known operation,
  actor/context mismatch, system Finance on a missing project, and script
  mismatch, partial-failure output and production-refusal tests.

## Reconciliation

- Current-source reconciliation: based on `main` at the merge of #633
  (`0057_roles_anywhere_custody` head); this change takes `0058`.
- Next usable boundary: public unit/binding administration and money units, if
  wanted.
- Remaining risks: test fixtures still create units by direct insert.
