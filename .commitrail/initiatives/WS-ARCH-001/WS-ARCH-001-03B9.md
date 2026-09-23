# WS-ARCH-001-03B9 — Exact pre-submit assignment invalidation

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Intended merge outcome: A hidden TASK-owned reconciliation operation releases
  only the exact pre-submit assignment affected by a committed authority change.

## Intent

When a contributor loses authority, foreground commands already deny further
work. Reconciliation must also close the affected ordinary assignment so another
eligible contributor can claim the task. Delayed delivery must never release a
replacement assignment or rewrite submitted work and revision obligations.

## Current behavior

Current main includes AUTH-OUTBOX-02. Shared delivery has live fixed-dispatcher
authority, committed invocation observation, recovery and bounded prefork workers.
Its production handler registry is empty. AUTH mutations retain immutable
invalidation audit events; they do not yet publish TASK reconciliation events.
TASK has exact claim/start authority and immutable claim/start evidence but no
assignment invalidation operation. The existing 03B/03C coordination contracts
separate hidden TASK behavior from originating AUTH event wiring and activation.

## Bounded change

### Allowed

- TASK public reconciliation facts/ports and private operation/repository code;
  exact assignment release with retained locked context and existing history.
- Existing shared OUTBOX observation contract only where necessary to verify
  the complete committed invocation envelope and fence it in the effect
  transaction; no second dispatcher.
- AUDIT bounded invalidation-cause projection and typed lifecycle evidence;
  adapter composition through existing owners.
- Focused contract, PostgreSQL, race, rollback and fault-injection tests;
  exact test-lane and ownership registrations for those files.
- This record, adopted 03B/03C plans, initiative navigation, current roadmap
  and applicable TASK/AUTH operating and architecture documentation.

### Not allowed

- Production handler registration, AUTH producer fan-out, new public routes or
  live feature permission activation; these remain ARCH-03C.
- Generic manager reassignment, automatic revision release, Submission changes,
  checker execution, financial effects or retained-data deletion.
- Relaxed boundary guards, compatibility paths, fabricated production authority,
  changes to existing ordinary claim/start transaction ownership or new workers.

## Design and decisions

Use one exact assignment target per event, including project, task, contributor
and immutable AUTH invalidation identity. Never select the current assignee as
a substitute for the event's original assignment. Verify the complete persisted
event and its exact committed invocation, not a caller-constructed claim alone.
Resolve eligible causes through their owning audit boundary: Submitter grant
revocation, profile suspension/deactivation or identity-link revocation.
Reviewer/admin role changes and reactivation cannot release assignments.

Require an explicit feature authorization port; shared dispatcher authority
does not authorize TASK writes. Keep production unavailable until the exact
fixed-service implementation and originating event wiring land in 03C.

Serialize on TASK then its exact assignment. Only a consistent active assignment
on a claimed/in-progress task with no Submission may become authority_revoked;
clear assigned_to and return the task to ready without changing locked policy
lineage. Use the existing typed audit participant for atomic immutable release
evidence and exact replay. Do not expand generic lifecycle transitions: that
would also widen the existing manager release operation.

The event is `TaskAssignmentAuthorityInvalidationRequested`, protocol version 1,
aggregate type `task_assignment` and aggregate ID equal to the assignment UUID.
Its closed payload contains only project_id, task_id, assignment_id,
contributor_id and authority_invalidation_event_id. Its causation_event_id
is that same invalidation UUID. This protocol identifier is not a parallel
implementation version.

Replace the claim-only OUTBOX observation with full-envelope observation and
update every caller/test together. The initial independent committed observation
rejects forged/uncommitted delivery before TASK SQL. Inside the effect root
transaction, lock TASK, exact assignment, feature AUTH, then OUTBOX event and
attempt through a narrow session-bound owner port. Recheck every immutable
envelope field, generation, invoked stage and database-clock lease after waits.
Keep the OUTBOX rows locked through effect/evidence commit. The guarantee is
validity at fence acquisition and frozen generation/state until commit, not a
promise that wall-clock lease time stops advancing. Perform no external I/O
after the fence. Shared dispatch releases its locks before handler execution
and never acquires TASK locks; future AUTH producers must not acquire TASK locks.

AUDIT projects the immutable invalidation and its exact cause together, validating
domain/source/version, direction, actor, cause identity and role-specific scope.
No ORM object or private AUTH model crosses this boundary. Release evidence uses
the closed `TaskAssignmentAuthorityRevoked` lifecycle event and exact project,
task, assignment, authorization-decision and authority-invalidation references.
Its deterministic identity derives from invalidation plus assignment; read that
exact evidence before considering any later active assignment.

The consumer owns no commit inside its caller's transaction. Handler composition
owns the transaction and acknowledges only after commit. A failed transaction
has no partial release/evidence. An uncertain commit never requests automatic
repetition. Exact prior release ACKs without a new effect; submitted/revision or
replaced work remains unchanged. Malformed/forged causes and denied authority
REJECT. RETRY is allowed only after a positively known rollback-safe failure;
uncertain failures propagate to shared UNKNOWN handling.

Exact implementation paths: TASK `api/assignment_invalidation.py`,
`assignment_invalidation.py`, `repository.py`; AUDIT `api.py`,
`invalidation.py`, `repository.py`, `schemas.py`; OUTBOX `api.py`, `delivery.py`,
`delivery_repository.py`; owner composition `adapters/tasks/__init__.py`,
`adapters/audit/__init__.py`, `adapters/outbox/__init__.py`; tests under
`tests/tasks/` and `tests/outbox/` plus exact catalogue/ownership expectations.
No schema change is required; migration head remains 0028. Positive feature
authority is explicitly a controlled test seam, not a real AUTH ALLOW event.
Production composition supplies an unavailable adapter and no registration.

## Acceptance criteria

- [ ] Exact committed delivery and eligible cause release the original claimed
  or in-progress assignment and preserve policy locks and prior history.
- [ ] Wrong project/actor/role/cause/assignment, forged envelope, uncommitted or
  expired invocation and missing feature authority produce no release.
- [ ] Submitted/evaluation/review/revision work cannot return to ordinary ready.
- [ ] Replay and concurrent delivery produce one release/evidence; a later claim
  survives old delivery, and reactivation never restores a closed assignment.
- [ ] Rollback removes every release effect; concurrency with start/submission
  preserves a single valid outcome without reversing existing lock order.
- [ ] No production handler, route or permission becomes available in this PR.

## Risk and review routing

- Risk class: `L1` (bounded lifecycle and authority-sensitive integration).
- Required reviewers: architecture, security, reuse_dedup, qa, test_delta,
  product_ops, documentation; ci_integrity for lane/ownership registration.
- Human review focus: exact invalidation target, delayed delivery/reclaim,
  submitted-history preservation and hidden-versus-live scope.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing contracts reconciled | Inspect TASK commands, AUTH emitters and OUTBOX committed observation on current main | Scope identified | Plan review must close cause, chronology and transaction-fence details |
| Hidden operation safety | Focused PostgreSQL proof and a guard-removal probe for stale assignment protection | Required | Not implemented |
| Boundaries and current docs | Module/structural boundary checks, Ruff, Commitrail, stale wording and Markdown links | Required | Not run for implementation |
| Complete regression evidence | Hosted Backend semantic lanes and coverage | Required | Not run for implementation |

## Review findings

Plan inspection identified two obsolete assumptions: shared delivery is already
implemented, while invalidation audit events still are not dispatchable events.
Generic claimed/in-progress-to-ready transitions would inadvertently broaden
the retained manager operation; reconciliation must own its narrower guard.
Security/architecture and QA/product reviews required full-envelope verification,
an AUDIT-owned exact cause projection, an assignment-specific event, and a real
same-transaction OUTBOX fence after TASK/AUTH locks. The initial observation-only
proposal was rejected. The delayed-TASK-lock regression must fail when the fence
is omitted. Synthetic feature-authority proof is explicitly separate from real
PostgreSQL/AUTH cause and shared dispatcher evidence.

## Reconciliation

- Current-source reconciliation: merged AUTH-OUTBOX-02 supplies shared delivery;
  no overlapping product PR is open.
- Next usable boundary: ARCH-03C exact feature authority/producer wiring and
  separately bounded public task activation. First production handler activation
  must enforce the prefork worker/routing topology required by AUTH-OUTBOX-02.
- Remaining risks: Real fixed-service feature authority and atomic producer
  fan-out are deferred to 03C; this hidden PR cannot claim their runtime proof.
