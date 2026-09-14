# WS-ARCH-001-CP07A — Lock policy authority before product resources

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: remove the cross-owner lock inversion in existing
  ContributionPolicy and compensation-adapter mutations before guide binding.

## Intent and current behavior

CP06 supplies exact policy validation but has no production guide caller.
Before CP07 composes it, existing CON mutations and COMPENSATION binding
mutations must agree with AUTH role issuance about lock order. Current main
`a3e4c696` includes CP06 and the independent CI artifact retry repair.
CON publication locks Project and bindings before preparing authority; binding
suspension locks its binding first. AUTH preparation then locks AuthorityControl,
caller identity and Finance grant. Role issuance takes those authority locks
before Project. This permits a cycle. Taking only AuthorityControl earlier is
insufficient: a Finance actor may also submit work, whose ART path locks the
caller profile before Project.

This prerequisite is one bounded repair. CP07 guide binding, AUTH-12H activation
and obsolete guide economic-schema reconciliation remain subsequent work.

## Bounded change

Allowed: existing CON/COMP mutation authorization protocols and deny defaults,
AUTH public authorization protocols, their application adapters, AUTH owner
adapters and PREP service; existing CON mutation entry/recovery helpers and
COMP mutation service; affected authorization fakes/contracts and real PostgreSQL
concurrency tests; exact test inventories; current roadmap/navigation and CP07
planning references. Extend existing files where practical.

Not allowed: new routes/actions/permissions, activation or guide/attempt writes,
policy-selection changes, new authorization evaluator, public generic lock API,
migrations, evidence bypass, retry-on-deadlock substitutes, compatibility paths,
or unrelated CI workflow changes. Do not alter ART or role-issue lock ordering.
No retained data deletion. Replay must keep its existing current-read authority.

## Design and decisions

- Extend existing domain mutation authority ports with a narrow scope-lock step:
  explicit closed mutation action, authenticated actor and project UUIDs.
- AUTH reuses its existing PREP/kernel authority preparation to acquire the
  singleton, caller profile/link and exact Finance grant in canonical order.
  Discard the temporary opaque prelocked object while retaining transaction
  locks. Issue no mutation handle, decision evidence or product effect here.
- Invoke this step after exact operation replay recovery and before any product
  owner row lock, for all four CON and all three binding mutations. Default
  composition denies; no optional-method or fallback path.
- Keep exact resource-bound prepare/consume/close after graph/binding facts are
  locked. Early scope locking cannot substitute for this authorization or let
  callers reuse authority across actor/action/project/transaction boundaries.
- Preserve Project-first CON validation and binding create/resume ordering;
  suspension does not gain a project-active eligibility requirement.
- Caller owns the root transaction. Denial and failure roll back all effects;
  completion replay remains authorized without repeating a mutation.

## Acceptance criteria and proof

- All seven non-recovered mutation paths acquire authority scope before Project/binding owner locks.
  The exact final PREP consumption remains mandatory and unchanged.
- Malformed action/UUID, wrong actor/project authority, service context, missing
  composition and nested/no-root transactions deny without product changes.
- Real PostgreSQL, real AUTH interleavings cover policy publication/retirement
  against role issuance, validation against suspension and role issuance, and
  a dual Finance/submitter caller holding its profile before Project. Use
  independent connections, observed blocking edges and valid eligible fixtures.
- Regression probes must fail when early authority locking is removed, and the
  dual-role proof must reject an AuthorityControl-only substitute. Do not fake
  successful authorization or accept unrelated SQL errors as concurrency proof.
- Prove early scope locking leaves no issued PREP handle, sealed prelock or
  decision/audit evidence, including cleanup on failure. Completed replay uses
  current-read authorization without creating a fresh mutation scope or handle.
- Preserve publication, binding lifecycle, replay, revocation and rollback tests.
  Run focused tests/coverage, exact inventories and boundary scanners, lint,
  links/stale wording/Commitrail checks and final hosted lanes. No weakened gates.

## Risk and review routing

Risk: L1, cross-owner authorization and concurrency. Required focused reviews:
architecture/reuse, security, QA/test delta, docs/product operations and CI
integrity for exact inventories. Human focus: early locking is not authority;
exact consumption/evidence survives, all affected mutations share the order,
and concrete PostgreSQL tests reach the conflicting edges.

## Plan reconciliation

The CP07 skeleton is not an implementation contract: current code has only
`ActiveGuideReadResponse`, already without PaymentPolicy in its response body,
and no old activation write to wire. Its readiness helper still has payment
arguments because current reads consume it. CP07 must replace the affected
readiness/guide binding path with one current implementation and trace shared
consumers, rather than resurrect an old response or add another activation path.
This repair changes no guide readiness capability. Next usable boundary remains
reviewed CP07 guide binding, followed by exact AUTH-12H activation.

## Concrete concurrency fixtures

Update `tests/authorization/contribution_policies/concurrency.py` and its
callers: a second mutation now waits on Control before reaching PROJECTS.
Observe actual backend PID blocking edges rather than requiring both
participants to enter the project-lock hook.

For the three-way proof, hold validation's Project lock, let role issuance
hold Control and wait on Project, then start binding suspension. Suspension
must wait on Control before taking the binding; validation can acquire that
binding and finish. Removing early suspension scope locking recreates the
Project-to-binding-to-Control cycle. Assert both waits and final outcomes.

For dual-role proof, reuse ART's existing `_harness` and `_PauseBeforeProject`
fixture, grant its contributor Finance authority, and invoke real CON
`create_draft` on the same project. ART holds the caller profile before Project;
a Control-only prelock still fails this case. Fixtures require no live guide
activation and must preserve ART's real authority composition.
