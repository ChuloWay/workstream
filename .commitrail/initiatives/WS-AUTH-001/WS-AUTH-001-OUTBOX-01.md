# AUTH-OUTBOX-01 — Restricted dispatcher authorization contract

- Initiative: WS-AUTH-001
- Durable disposition: Planned
- Intended merge outcome: register one unavailable dispatcher action and fixed
  identity with closed phase-bound facts and a typed preparation port; leave
  delivery and live authorization to CON-02B and AUTH-OUTBOX-02.

## Intent

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
- `backend/alembic/env.py`: retain 0025 as an admitted predecessor and register
  0026 as the current head; repeated `upgrade head` must remain valid.
- `backend/tests/conftest.py`: refresh only the exact public-schema digest after
  PostgreSQL catalogue comparison proves the identity CHECK is the sole delta.
  Preserve the immutable 0001 baseline manifest.
- Remove the superseded `actors/service_identities.py` re-export; update its
  exact production/test import consumers to `actors.api`. Update only matching
  AUTH/private-edge debt entries and ownership partition/closed-transition tests.
  This mechanical consumer repair preserves all existing service identities.
- Focused `backend/tests/authorization/test_outbox_dispatch_contract.py` and
  `backend/tests/migrations/test_outbox_dispatch_identity.py`, existing catalogue,
  boundary, identity and ownership expectations; exact lane registrations.
  Update the explicit action inventory 116 -> 117, permission inventory 73 -> 74
  (new permissions 24 -> 25), and service memberships 23 -> 24 without loosening
  exact-set assertions.
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
digest (`sha256:[0-9a-f]{64}`), strict integer claim generation 1..2147483647,
worker owner matching `[A-Za-z0-9._:-]{1,120}`, aware claimed-at and strictly
later lease expiry. FINALIZE additionally requires a canonical `outcome_digest`;
CLAIM/INVOKE forbid it. CON-02B owns the typed outcome and hashes every result,
retry and dead-letter field to be written; AUTH does not interpret that schema. For claim these describe the proposed next reservation;
for invoke/finalize they describe the already-committed reservation. CON-02B
must compare claim generation against locked persisted state and validate
committed ownership; callers cannot assert commit by supplying a boolean.
The canonical resource digest uses the single domain
`workstream.authorization.outbox_dispatch` and binds every normalized fact plus
fixed action, permission, service identity, resource type/id and project scope.
There is no compatibility domain. Phase and outcome are included so neither a
copied claim nor pre-invocation facts identify a later-phase operation. Same
instant timestamp offsets canonicalize to UTC.

Expose a nominal abstract `PreparedOutboxDispatch` and typed context-manager
port for one exact phase:
`PreparedOutboxDispatch.consume(facts: OutboxDispatchFacts) -> AuthorizationDecision`
and `prepare_outbox_dispatch(facts, request_id, correlation_id) ->
AbstractAsyncContextManager[PreparedOutboxDispatch]`. Reuse the existing public
decision type; add no receipt class. Request/correlation identifiers are invocation
context, excluded from resource facts/digest. Preparation resolves the fixed identity internally;
there is no caller-selected service or feature action. A handle must remain
process-local and rejects pickle, shallow copy and deep copy. Concrete session/root-transaction binding,
single consumption, equality of recomposed phase/facts/outcome, live authority
and committed-generation revalidation belong
to AUTH-OUTBOX-02 consuming CON-02B's public claim port. No live implementation,
factory, permissive default or fabricated allow receipt is added here. Each
phase requires a new preparation; no handle crosses commit, lease wait or I/O.

The ACTORS transitional import file has no implementation. Trace all consumers,
replace their imports with the existing canonical public API, remove the alias
and retire only its exact debt/inventory references. Preserve synthetic tests
which still protect required private-boundary behavior using a real retained
private owner where appropriate. Do not duplicate the identity enum.

## Acceptance criteria

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
5. Real PostgreSQL fixed-service admission proves missing identity raises
   `ACTOR_NOT_FOUND`; a provisioned active dispatcher/link with its exact planned
   action raises `PERMISSION_NOT_GRANTED`; an active foreign service action
   raises `PERMISSION_NOT_GRANTED`. Assert persisted actor/link status, exact
   matrix membership and availability before testing the denial. Positive control uses an existing provisioned
   active service action so a universally failing fixture cannot pass.
6. No live imports use the deleted alias; boundary/ownership/lane validation and
   all retained identity/authorization tests pass without relaxed gates.

## Evidence

These are contract/registration proofs, not runtime lease/replay/crash proofs.
CON-02B must prove persisted claim fencing and recovery; AUTH-OUTBOX-02 must prove
live generation matching and fresh authority/session/transaction consumption.
Mutation probes must remove the planned gate or exact matrix membership check,
change digest generation/phase binding, and widen the identity DB constraint;
corresponding tests must fail at their intended assertion with valid controls.

## Risk and review routing

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

### Named proof inventory

Future nodes in `tests/authorization/test_outbox_dispatch_contract.py`:

- `test_dispatch_registration_is_exact_and_unavailable`: exact catalogue,
  fixed-service pair, human exclusion and closed metadata corruption controls.
- `test_dispatch_facts_validate_all_phases`: valid controls and each malformed
  field independently, including phase-specific outcome requirements.
- `test_dispatch_digest_binds_every_fact`: independent substitutions of each
  field, fixed canonical bytes, same-instant UTC normalization, forged typed
  input rejection and action/permission/service/resource envelope assertions.
- `test_dispatch_prepared_contract_is_nominal_and_process_local`: abstract
  handle plus pickle/copy/deepcopy rejection; no runtime authority claim.
- `test_dispatch_service_admission`: real persisted missing, active planned,
  foreign-action denials and existing active-service success in distinct steps.
- `test_service_identity_alias_is_removed`: whole live Python consumer scan,
  absent old file, current ledgers clean; historical records are not rewritten.

Future nodes in `tests/migrations/test_outbox_dispatch_identity.py`:

- `test_dispatch_identity_upgrade_preserves_records_and_exact_schema`: install
  0025, commit actor/link controls, reject dispatcher before upgrade, apply0026,
  reconnect to verify persistence and unchanged records; compare exact constraint
  vocabulary with ACTORS model and assert only the identity CHECK changes.
- `test_dispatch_identity_head_upgrade_is_repeatable`: repeated head migration
  succeeds and leaves schema/records unchanged after0026 is already committed.
- `test_dispatch_identity_rejects_unknown_and_duplicate`: actual raw-DB exact
  identity acceptance, unknown CHECK rejection and duplicate UNIQUE rejection,
  each with valid surrounding fields and its exact expected constraint.
- `test_dispatch_identity_downgrade_preserves_records`: unchanged revision,
  constraint and actor/link snapshots after the existing no-downgrade guard.

The current tests do not prove live committed-claim equality, lease validity,
session/transaction lifetime or delivery recovery. Those remain CON-02B and
AUTH-OUTBOX-02 implementation proofs. Admission tests use existing denial codes.
The planned-gate mutation changes only action availability in fixed-service
admission; the matrix mutation changes only exact membership. Digest mutations
omit generation/phase/outcome independently. The DB mutation widens only the
identity CHECK so the unknown-identity test must stop raising. These probes must
reach the named semantic assertion; setup failures do not count as detection.

## Review findings

Plan review added repeated-migration admission, exact schema fingerprint custody,
explicit method signatures and serialization restrictions, fixed-envelope hashing,
finalize outcome binding, named wrong-reason-resistant controls, and the distinction
between current registration proof and future live dispatcher proof.
