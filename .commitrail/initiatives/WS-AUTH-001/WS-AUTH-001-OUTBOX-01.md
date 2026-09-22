# AUTH-OUTBOX-01 — Restricted dispatcher authorization contract

- Initiative: WS-AUTH-001
- Durable disposition: Planned
- Intended merge outcome: register one unavailable dispatcher action and fixed
  identity with closed phase-bound facts and a typed preparation port; leave
  delivery and live authorization to CON-02B and AUTH-OUTBOX-02.

## Intent and current behavior

Reliable follow-up must survive a worker crash without giving the delivery
worker TASK, checker, artifact or compensation authority. Shared OUTBOX already
persists immutable events and delivery metadata; it has no dispatcher. AUTH
already owns the closed service matrix, planned-action gate and transaction-local
prepared-authority conventions. Extend these owners, not a second worker or
permission system. Current main includes ARCH-03B8 internal audit evidence.

## Bounded change

Allowed:

- `backend/app/modules/authorization/catalogue.py`: one planned action/permission
  `outbox.dispatch`, AUTH-OUTBOX-01 owner and exact singleton service matrix row.
- `backend/app/modules/authorization/api/outbox_dispatch.py` and `api/__init__.py`:
  immutable dispatcher facts, phase, digest and abstract prepared port only.
- `backend/app/modules/actors/api/service_identities.py` and
  `backend/alembic/versions/0026_outbox_dispatch_identity.py`: add only
  `workstream.outbox.dispatcher` to the existing closed identity vocabulary and
  database check after 0025. Do not provision an actor or rewrite retained data.
- Remove the superseded `actors/service_identities.py` re-export; update its
  exact production/test import consumers to `actors.api`. Update only matching
  AUTH/private-edge debt entries and ownership partition/closed-transition tests.
  This mechanical consumer repair preserves all existing service identities.
- Focused `backend/tests/authorization/test_outbox_dispatch_contract.py` and
  `backend/tests/migrations/test_outbox_dispatch_identity.py`, existing catalogue,
  boundary, identity and ownership expectations; exact lane registrations.
- AUTH/CON/ARCH current overview/plan/map, INDEX, README, roadmap, authorization
  and contribution specifications and operations docs where current boundary
  wording changes. No local spreadsheet exports exist.

Prohibited: dispatcher/handler implementation, worker registration, runtime
activation, generic service permissions, feature authority, grant changes,
public routes, outbox state/schema changes, data deletion, compatibility aliases,
new private imports, gate weakening or unrelated cleanup.

## Design

The dispatcher has exactly `outbox.dispatch`; no human role receives it and no
other service receives it. Availability stays `planned` in both the ordinary
catalogue and service-matrix metadata. Registering/provisioning an identity must
not make its action executable.

Expose a closed `claim`, `invoke`, `finalize` phase enum and immutable
`OutboxDispatchFacts`. Bind exact event UUID, project UUID, immutable payload
digest, positive claim generation, bounded worker owner token, aware claimed-at
and later lease expiry. For claim these describe the proposed next reservation;
for invoke/finalize they describe the already-committed reservation. CON-02B
must compare claim generation against locked persisted state and validate
committed ownership; callers cannot assert commit by supplying a boolean.
Phase is included in the action-domain-separated resource digest so neither a
copied claim nor pre-invocation facts identify a later-phase operation. Same
instant timestamp offsets canonicalize to UTC.

Expose a nominal abstract `PreparedOutboxDispatch` and typed context-manager
port for one exact phase. Preparation resolves the fixed identity internally;
there is no caller-selected service or feature action. A handle must remain
process-local and is not serializable. Concrete session/root-transaction binding,
single consumption, live authority and committed-generation revalidation belong
to AUTH-OUTBOX-02 consuming CON-02B's public claim port. No live implementation,
factory, permissive default or fabricated allow receipt is added here. Each
phase requires a new preparation; no handle crosses commit, lease wait or I/O.

The ACTORS transitional import file has no implementation. Trace all consumers,
replace their imports with the existing canonical public API, remove the alias
and retire only its exact debt/inventory references. Preserve synthetic tests
which still protect required private-boundary behavior using a real retained
private owner where appropriate. Do not duplicate the identity enum.

## Acceptance and proof

1. Catalogue/matrix admit exactly the new pair as planned, preserve all existing
   pairs, and reject extra feature membership. Existing fixed-service admission
   rejects dispatcher execution even when the actor/link are correctly provisioned.
2. Pure contract tests accept valid facts for all three phases, reject malformed
   UUID/digest/owner/counter/timestamp/phase values and mutable or substitute facts.
   Independently changing event/project/generation/owner/lease/payload/phase changes
   the digest. Valid same-instant timestamps are stable. Invalid output is sanitized.
3. The abstract handle cannot be instantiated as authority and cannot be pickled;
   no public HTTP surface or runtime evaluator appears. Protocol documentation
   explicitly binds future preparation/consumption to one session/root transaction.
4. Real PostgreSQL upgrade 0025 -> 0026 preserves existing actor/link rows and
   constraints, allows exact dispatcher provisioning, rejects unknown identities
   and duplicate singleton provisioning. The downgrade guard preserves data.
5. Real PostgreSQL fixed-service admission proves missing identity denies,
   provisioned dispatcher remains unavailable, and dispatcher cannot invoke any
   active foreign service action. Positive control uses an existing provisioned
   active service action so a universally failing fixture cannot pass.
6. No live imports use the deleted alias; boundary/ownership/lane validation and
   all retained identity/authorization tests pass without relaxed gates.

These are contract/registration proofs, not runtime lease/replay/crash proofs.
CON-02B must prove persisted claim fencing and recovery; AUTH-OUTBOX-02 must prove
live generation matching and fresh authority/session/transaction consumption.
Mutation probes must remove the planned gate or exact matrix membership check,
change digest generation/phase binding, and widen the identity DB constraint;
corresponding tests must fail at their intended assertion with valid controls.

## Risk and review

L1: bounded authorization, identity schema and public contract. Required tracks:
security, architecture/reuse, QA/test delta, CI integrity and docs. Human focus:
planned never means enabled; exact dispatcher permission gives no feature
permission; facts/receipts are not transferable authority; retained data survives.

Lead runs focused pure and isolated PostgreSQL proof, full boundary/ownership
preflight, Ruff, stale-wording/Markdown/Commitrail checks, then exact-head hosted
lanes and coverage. Freeze clean candidates for plan and implementation review;
reviewers own scoped falsification rather than repeating the full suite.

## Reconciliation

- Base: main 0c701e03 (merged PR #426); current migration head 0025.
- No overlapping open product PR; #410 concerns advisory CI reporting.
- Next usable boundary: CON-02B hidden shared dispatcher, followed by
  AUTH-OUTBOX-02 activation; TASK invalidation and ARCH-03C remain separate.
