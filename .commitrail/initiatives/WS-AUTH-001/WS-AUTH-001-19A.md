# WS-AUTH-001-19A — Exact acceptance-source commitments

- Initiative: WS-AUTH-001
- Durable disposition: Planned
- Intended merge outcome: exact, inert source commitments for human Review and
  post-submit routing, with the router registered as planned and unavailable.

## Intent and prerequisite correction

Main `04bf8b76` delivers the disabled REV-12A1 transaction fence. Review and
FinalAcceptance foundation rows still lack originating authorization receipts.
Inspection found that review.decision cannot execute and does not bind the
allocated Review/request identities; task.post_submit.route is not registered.
Mandatory receipt DDL now would require fabricated allows for positive tests or
make valid inserts unreachable. Define the source contracts first. This does not
satisfy persisted receipt custody: genuine source authorization and same-table
hardening remain prerequisites to CON-07/shared acceptance.

The automated false-policy branch remains the selected first runtime delivery.
True-policy routing retains its independent prerequisites. Submitter lease/skip,
live human queues and review/revision operations remain outside this change.

## Design

Repair the existing initial/revision ReviewDecisionContract in place. Bind the
allocated Review ID, ReviewDecisionRequest ID, existing operation ID, native UUID
idempotency key, request digest and Review aggregate digest. Preserve existing
exact project/task/assignment/Submission/reviewer/packet/policy facts. A decision
may request revision with a new blocker or an unresolved inherited blocker;
accept requires neither. Initial decisions cannot claim inherited blockers.
Bound counts to the delivered storage limit; do not duplicate Review content.

Define strict frozen source commitment and detached receipt value contracts in
AUTH's dependency-free public API. Human commitments project retained identity,
request and aggregate facts from the repaired private Review contract. Routing
commitments project identity and a canonical digest from the existing TASK
TaskPostSubmitManifestFacts, including its semantic manifest hash. TASK owns this
projection and digest; AUTH does not import TASK or private contracts through its
public API. Reuse canonical_json_hash and revalidate input before hashing. There
is no second manifest model or table. The source digest commits retained facts;
it is distinct from the full runtime authorization resource digest, which also
binds runtime facts and is not claimed independently reconstructible today.

Detached receipt facts bind event/action/actor/project/resource and the selected
source commitment. They are untrusted values until a future owner verifies the
actual immutable AUTH event and source. Construction, hashing and a receipt-shaped
value grant no authority. Routing operation/claim/currentness/effect evaluation
remains ARCH-04E1B/04E2 work; this does not define an executable routing context.

Register task.post_submit.route as a planned action/permission with ARCH-04E2
ownership and workstream.task.post_submit_router as its sole fixed identity.
Extend only ActorProfile's closed service-identity CHECK in a successor migration
for ORM/DDL parity. Create no service actor, grant or event. Leave audit registry
constraints, active action sets, kernel and prepared/evaluator paths unchanged.

## Allowed files

- `backend/app/modules/actors/api/service_identities.py`.
- `backend/app/modules/authorization/catalogue.py`, `review_contracts.py`, and
  new `api/acceptance_source.py` (package exports only if needed).
- `backend/app/modules/tasks/api/post_submit_routing.py` and its existing export.
- One successor Alembic migration extending only the actor identity CHECK.
- Existing Review authorization, TASK routing contract, catalogue/service matrix
  and migration/schema tests; a focused AUTH source-contract test module if the
  existing tests cannot express the cross-contract proof cohesively.
- Alembic/schema-head, CI lane and behavior-ownership inventories only as required
  by added paths or canonical identifiers; do not weaken boundaries or gates.
- This record, current AUTH/REV/CON/POL/ARCH overview/plan/chunk-map navigation,
  Commitrail index, roadmap and canonical authorization/review specifications;
  README and ignored roadmap spreadsheet exports if affected/present.

## Prohibited changes

No Review/FinalAcceptance schema changes, receipt FK placeholders, audit registry
expansion, fake allow fixtures, actor provisioning, executable authority, kernel
or prepared registrations, false-policy activation, contribution/acceptance
writers, routes, workers or handler activation. No compatibility implementation,
retained-data deletion, unrelated cleanup, test skipping or gate relaxation.

## Acceptance criteria and verification

1. Review contracts bind exact source/request identity. Independent substitutions
   change the source commitment; invalid scalar shapes reject. Existing initial
   and revision behavior stays covered, including inherited-only blockers and
   accept with an unresolved blocker rejecting.
2. TASK projects its existing source facts without copying their model. Every
   identity, policy, artifact and request substitution changes its canonical
   commitment. Equal revalidated values hash identically. Receipt envelopes reject
   action, actor, project/resource or commitment-digest mismatches.
3. Both originating actions remain unavailable. The fixed router matrix contains
   only the planned route action. No executor/handler/active-action registration
   appears. No public route or live receipt issuance is claimed.
4. Real PostgreSQL migration/schema tests prove canonical service vocabulary parity,
   preserve existing actor rows and create no new actor. A direct-SQL authority
   event control establishes valid audit input; changing it to the planned route
   action is rejected by the unchanged audit registry, not an unrelated FK/error.
5. Run focused pure and PostgreSQL proofs, discriminating guard-removal probes for
   receipt/source substitutions, module boundaries, ownership/lane completeness,
   lint, markdown links and stale wording checks. Full hosted CI remains blocking.
   Counts and coverage are diagnostics, not evidence of a particular guard.
6. Current navigation says source contracts delivered, genuine originating AUTH
   receipts and same-table source custody still required before CON-07. Preserve
   both policy branches; do not rewrite completed historical change records.

## Risk and reviews

- Risk class: L1 (authorization vocabulary and immutable source commitments).
- Plan review: security and architecture, including dependency direction and
  concrete valid-control feasibility before implementation.
- Implementation review: security; architecture/reuse; QA/test delta; docs/product
  operations; CI integrity for actual inventory/migration impact.
- Human focus: no receipt-shaped value confers authority, no hidden activation,
  source digests are reconstructible, and no artificial positive AUTH fixture.

## Evidence

Plan feasibility inspected at clean main `04bf8b76`; no runtime custody claim.
Exact command and reviewer evidence will accompany the implementation PR.
