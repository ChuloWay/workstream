# ARCH-03B1 — Detach TASK project and guide display context

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: TASK consumes immutable PROJECTS-owned display facts through the existing guide-context port, with no private PROJECTS model or repository dependency.

## Intent

Keep the project and exact guide shown to a contributor connected to the same
validated guide used by their task. Complete the remaining metadata boundary
before adding the broader task queues and actor-specific projections.

## Current behavior

Main at merged CP08 (`d2416a44`) stamps exact contribution lineage. TASK's
`TaskService._load_locked_task_context` first obtains validated PROJECTS facts,
then independently loads private `Project` and `ProjectGuide` ORM objects for
display. `LockedTaskContext` retains those objects. Draft creation also directly
loads `ProjectRepository`. These are the three remaining private PROJECTS
imports in TASK service, not additional policy-selection owners.

The adopted 03B skeleton also contains completed CP08 acceptance criteria and
an assignment-invalidation handler requiring an unimplemented committed outbox
claim contract. Existing OUTBOX supplies append only. The bounded sequence is
03B1 metadata cutover, remaining 03B queues/projections, then assignment
invalidation after AUTH-OUTBOX-01 and CON-02B. ARCH-03C retains exact authority,
originating invalidation-event append and public activation.

## Bounded change

### Allowed

- `backend/app/modules/projects/api/locked_policy.py` and `api/__init__.py`:
  immutable project/guide display facts and the existing port's project lookup.
- `backend/app/modules/projects/locked_policy_{repository,projection}.py`:
  build those facts from exact PROJECTS-owned rows under the existing transaction.
- `backend/app/modules/tasks/service.py`: replace the private project lookup and
  ORM-valued context; remove all superseded imports/fields/calls together.
- Existing affected composition or fixtures only where required by the changed
  port. Focused PROJECTS context and TASK HTTP/read tests, including
  `backend/tests/test_tasks.py` and `backend/tests/projects/test_locked_policy_*.py` and its fixtures.
  Register new tests in the existing exact lane catalogue if needed.
- Existing module-boundary machine/human ledgers: remove only retired edges;
  no new debt, raised thresholds or exemptions.
- This record, adopted 03B skeleton and dependency map, current initiative
  navigation, README, architecture/operating docs and roadmap where affected.

### Not allowed

No new route, permission, authorization decision, queue, assignment invalidation
handler, dispatcher, lineage writer, policy selection, checker execution,
migration, economic-schema deletion or compatibility implementation. Preserve
existing HTTP field contracts, separate contributor/manager authority, lock
order, no-flush/no-commit context reads and retained data. Migration head stays
`0024_task_policy_lineage`.

## Design and decisions

Extend the existing PROJECTS context port, not a second guide resolver.
The complete context includes required immutable display values for the exact
project and guide already validated by the owner. Their identities must match
the existing context and activation receipt. Descriptive project metadata is
current display data, not a new policy hash or immutable business-policy input.
Guide metadata is from the selected historical guide, never the current guide.
Use only scalar strings, UUIDs and datetimes; no ORM/session objects.

Draft creation needs only project existence, not an activated guide. Add a
bounded project-metadata lookup to this same port that returns a detached
project value or absence. It must not acquire a new lock or require readiness,
and must not flush/commit the caller's work. TASK retains its current validation
and authorization order. This avoids making draft creation depend on a guide
that the project manager has not yet configured.

## Acceptance criteria

- TASK service has no private PROJECTS model or repository import, constructor
  or ORM-valued display field; superseded paths are removed, not renamed.
- Public context facts reject wrong-project or wrong-guide display identity;
  matching values are detached and immutable.
- A draft task can still be created before guide activation; missing projects
  deny without task/audit writes.
- Contributor and manager work-context responses preserve their field shapes,
  authorization and exact historical guide metadata after a successor activates.
- Metadata reads neither flush pending writes nor commit and do not add a lock
  inversion. Existing policy receipt/hash substitution checks remain intact.
- Boundary debt shrinks, current documentation distinguishes 03B1 from remaining
  queues/invalidation and public AUTH activation, and all applicable checks pass.

## Risk and review routing

- Risk class: L1 (owner boundary and contributor-visible context).
- Required reviewers: architecture/reuse, security, QA/test delta,
  documentation/product operations, CI integrity. Senior engineering review of
  the bounded design can be combined with architecture.
- Human review focus: exact guide identity, no false claim that queues or
  assignment recovery are delivered, and no changed authorization or policy hash.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current owner/dependency trace | Inspect TASK context/service, PROJECTS context port, OUTBOX exports | Private display reads and append-only outbox confirmed | Plan review before code |
| Detached exact display facts | Focused existing PROJECTS context tests plus identity-substitution negatives | Planned | Runtime proof required |
| Stable public workflow | Real PostgreSQL TASK creation and contributor/manager frozen-context reads | Planned | Runtime proof required |
| No gate or boundary weakening | Ruff, module/authorization/structure validators, lane equality, stale wording, markdown links, hosted full tests/coverage | Planned | Exact implementation head required |

## Review findings

Plan discovery found that the old 03B skeleton requires a committed outbox claim
that does not exist and repeats CP08 writers. Keep completed lineage out of
03B implementation and order invalidation after its actual shared owner.

## Reconciliation

- Current-source reconciliation: CP08 is merged; consume its complete frozen
  context and preserve its claim/revocation ordering.
- Next usable boundary: remaining 03B queues and actor-specific projections;
  assignment invalidation follows shared claim-contract delivery, before 03C
  integrated activation.
- Remaining risks: no live queue/invalidation/public activation is claimed by
  this bounded metadata cutover.
