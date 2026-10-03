# WS-ARCH-001-04E2A — Exact hidden routing authorization preparation

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: exact routing preparation and receipt-staging contracts
  extend canonical AUTH/PREP while `task.post_submit.route` remains unavailable.

## Intent

Continue the governed Submission-to-outcome sequence after request reservation.
Prepare the existing routing issuer for both locked ReviewPolicy branches without
publishing an early allow, source manifest, human admission or final acceptance.
False/pass remains the selected first complete runtime path; it invokes shared
acceptance without a fabricated Review or reviewer contribution. Submitter
claim leases and skip remain deferred.

## Current behavior

Main `176952e6` includes ARCH-04E1B-A. TASK reserves an immutable operation ID,
future manifest ID and exact completion selectors, with currentness and caller
root transaction custody. AUTH-19A supplies untrusted source/receipt DTOs and the
planned fixed router identity. AUTH/PREP's existing kernel rejects planned actions
before issuing any handle; direct service authorization also denies. The source
writer, full owner projection, mandatory receipt storage and atomic consequences
are not implemented. Those facts constrain this chunk's proof: a successful
value preparation is not an issued capability or persisted allowed decision.

## Bounded change

### Allowed

- This record and affected current ARCH/AUTH/POL/CON/REV navigation, coordination
  contract, `.commitrail/INDEX.md`, README, roadmap, canonical authorization and
  review specifications and authorization custody documentation.
- `backend/app/modules/authorization/domain/post_submit_routing.py`,
  `post_submit_routing_authorization.py` and existing `acceptance_source_contracts.py`;
  existing `api/acceptance_source.py` only if the existing receipt contract requires it.
- AUTH `prepared.py`, `runtime.py`, `domain/prepared_service.py`,
  `domain/resource_digest.py`, `domain/audit.py` and `domain/audit_targets.py`
  only for the exact routing action's typed extension; no persisted audit registry change.
- Existing TASK public request/source contracts if a concrete owner seam is
  missing; no TASK source writer or routing handler.
- `backend/tests/authorization/post_submit_routing/{test_contracts,test_prepared,support}.py`;
  existing `tests/authorization/test_acceptance_source_contracts.py` and
  TASK `tests/tasks/post_submit_routing/{support,contract_fixtures}.py` only for reuse.
- Exact `backend/scripts/{behavior_ownership,test_lane_catalogue}.py`,
  `.ci/behavior-ownership/partition.v1.json`, `backend/tests/test_ci_lane_catalogue.py`
  inventory registration; no runner/workflow/cap/skip changes.

### Not allowed

No action availability change, new service identity/permission, hidden bypass,
production handler, public route, source insertion/current pointer, Review or
FinalAcceptance writer, contribution/award effect, schema migration, audit allow
registry activation, generic new preparation framework or compatibility path.
Do not modify observability, dependencies, application or Celery bootstrap in
this branch; the concurrent observability worktree owns those changes.

## Design and decisions

Reuse strict TASK request/source values and AUTH's canonical source commitment.
Reconcile every shared selector between request, future source and completion
claim; mismatched project, Submission/version, checker request/generation/result,
manifest identity, route operation/digest or policy branch must reject.
The exact resource distinguishes the true human-admission consequence from the
false shared-acceptance consequence, including its allocated acceptance identity.
No value or digest proves persisted ownership, live authority or currentness.
Project request selectors exclude database-created timestamps; all semantic
selectors and allocated operation/manifest identities remain bound.

Extend existing AUTH/PREP binding and consumption seams rather than constructing
another capability. Retain planned-action rejection in the kernel and fixed
service matrix. Source projection/currentness supplied by future owner composition
must be validated under the same transaction and lock order before any eventual
consumption. The nominal receipt participant only projects after canonical PREP consumption
returns a real decision; it writes or commits nothing. This code is unreachable
while planned, with no alternate callable allow path. Source receipt shape is
derived from the exact context and canonical
source commitment; genuine immutable audit-event verification and mandatory
persisted receipt custody remain activation prerequisites, not an assumed fact.

Preparation must not acquire TASK locks and then attempt to acquire fixed-service
locks. The future routing composition acquires its live service authority first,
then owner locks, and stages the eventual decision and consequences together.
Do not add a test-only activation switch or commit fabricated allows to obtain
positive pre-activation integration proof.

## Acceptance criteria

1. Valid preparation values for both policy branches bind every exact request,
   source and consequence selector; independent substitutions reject or change
   the canonical commitment as appropriate.
2. Shared PREP matches the same action/project/request/operation and final facts;
   existing supported actions preserve behavior.
3. A real provisioned router still cannot obtain a prepared executable handle or
   commit an allowed decision through the planned action; unrelated service and
   human principals cannot substitute. Rejection leaves no source or product effect.
4. Receipt candidates are explicitly untrusted; mismatched issuer, request,
   resource or source commitment cannot be silently projected as the exact receipt.
5. Real caller rollback preserves the existing request/no-effect boundary.
   Positive handle/receipt/lock-order/atomic-outcome execution is not reachable
   while planned and is not claimed: exercise value matchers with valid controls
   and prove actual PREP denial without fabricating an allowed decision.
6. Current navigation identifies the next usable CON-07/shared acceptance or
   hidden-handler prerequisite without claiming live routing or acceptance.

## Risk and review routing

- Risk class: L1, bounded authorization/architecture and workflow contract.
- Plan review: architecture and security, including fixture feasibility.
- Implementation reviews: architecture/reuse, security, QA/test delta,
  documentation/product operations, CI integrity for any proof inventory change.
- Human review focus: no early allow, no alternate issuer, exact source and
  request commitments, and both policy branches retained.

## Evidence

Run focused pure routing/source contract tests, real PostgreSQL planned-action
and rollback proofs, retained PREP/source tests and canonical module/AUTH/test
boundaries. Add named guard-removal probes for discriminating substitution tests.
Run Ruff, Commitrail/link/stale-wording checks and full hosted completeness with
no skips/deselections. Positive live issuer, persisted receipt and outcome proofs
belong to the activation chunk and must not be claimed here.

## Reconciliation

- Current-source reconciliation: merged #467 supplies exact TASK reservation;
  #465 supplies inert AUTH source contracts. No code change is authorized by an
  old plan where it contradicts these current owner boundaries.
- Next usable boundary: CON-07/shared acceptance preparation and hidden handlers,
  followed by exact receipt/consequence activation and live composition.
- Remaining risks: source projection and actual receipt custody are still future
  work; detached values never substitute for the immutable AUTH event.
