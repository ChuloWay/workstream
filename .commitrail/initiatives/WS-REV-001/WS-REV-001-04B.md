# REV-04B — Shared FinalAcceptance storage foundation

- Initiative: `WS-REV-001`
- Durable disposition: `Planned`
- Intended merge outcome: one immutable REV FinalAcceptance source table supports later shared human/automated acceptance; no acceptance runtime or authority is activated.

## Intent

Continue the approved claim → ZIP intake → Submission → checking → outcome
sequence. The shared acceptance operation needs a canonical source identity before
CON can bind its submitter ContributionRecord. Use the same storage for human
`accept` and future authorized false-policy routing; never fabricate a Review.

## Current behavior

Main `06f34140` delivers REV-04A Review sources, REV-03B packets and ARCH-04E1A
route-neutral TASK manifests. `review.decision` remains planned in AUTH;
`task.post_submit.route` is not active. False-policy guide activation is denied.
No FinalAcceptance, contribution/award writer, shared acceptance operation or
obligation fence exists. The canonical final runtime contract is
`docs/spec_review_lifecycle.md#finalacceptance`.

## Bounded change

### Allowed

- `backend/app/modules/reviews/acceptance/{__init__,models,schemas}.py`:
  one ORM table and strict metadata input; no writer or runtime port.
- `backend/app/db/models.py` registration.
- `backend/alembic/versions/0014_final_acceptance.py`, `backend/alembic/env.py`.
- `backend/tests/reviews/acceptance/{__init__,support,test_contracts,test_storage,test_migration}.py`.
- `backend/tests/conftest.py`, `backend/tests/test_alembic.py`: exact migration,
  reset/immutability inventory and measured fingerprint changes only.
- `backend/scripts/test_lane_catalogue.py`, `backend/tests/test_ci_lane_catalogue.py`.
- `backend/scripts/behavior_ownership.py`, `backend/tests/test_behavior_ownership.py`,
  `.ci/behavior-ownership/partition.v1.json`: exact declaration-only registration.
- This record; `.commitrail/INDEX.md`; current REV/CON/ART/AUTH-001/AUTH-003/POL/ARCH
  initiative overviews; current AUTH/POL/ARCH `planning/PLAN.md` and `CHUNK_MAP.md`;
  ARCH `planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md`.
- `README.md`, `docs/roadmap_status.md`, `docs/glossary.md`,
  `docs/architecture_data_model.md`, `docs/spec_review_lifecycle.md`,
  `docs/spec_artifact_storage_service.md`,
  `docs/engineering/authorization_activation_custody.md`.
- Ignored local roadmap exports only if present.

### Not allowed

No public/API/service/repository writer, fake AUTH allow, activation of false
policy, CON participant or substitute, task-state effects, copied checker result,
new routing entity, obligation controller, revision workflow, baseline rewrite,
retained-data deletion, compatibility path or weakened verification.

## Design and decisions

One table `final_acceptances`: UUIDv7 id; project/task/Submission;
`acceptance_source` (`human_review` or `task_post_submit_route`); nullable exclusive
Review/routing-manifest source IDs; exact accepted submitter; database-owned
`accepted_at`; `recorded_by` actor; `policy_context_ref` exact locked ReviewPolicy.
Use owner-local Python string/UUID representations with native PostgreSQL UUID.
Unique task, Submission and each non-null source; restrictive FKs; closed source
shape; all rows immutable against UPDATE/DELETE/TRUNCATE.

The runtime contract additionally requires exact originating
`authorization_decision_event_id`. That custody is not yet constructible from
canonical owners. As with the delivered route-neutral TASK foundation, do not
invent an event, insert a nullable receipt placeholder, or pretend FK possession
is authorization. This storage slice omits that runtime-only column. Before a
production writer or CON effects can use it, the same table must gain mandatory
exact receipt custody under the originating AUTH activation, refusing retained
pre-authority rows rather than backfilling fabricated receipts. This is a
foundation, not an alternate acceptance path. Canonical/current docs must state
that boundary and preserve the final required field.

Database validation uses qualified canonical joins: project/task/Submission,
exact assignment and contributor, activated-or-superseded locked guide and exact
ReviewPolicy selectors. Human source requires immutable Review decision accept,
matching complete source tuple, reviewer as recorded_by, and locked true policy.
Automated source requires exact successful TASK manifest with locked false policy,
matching Submission/assignment/contributor plus a service actor; live exact routing
service/action/currentness receipt custody remains explicitly unavailable. Actor kind
is transport shape only: later hardening must bind recorded_by to the exact fixed
`workstream.task.post_submit_router` identity and `task.post_submit.route` allow,
never an arbitrary service. No automated positive row using a substitute service
may be committed in these tests.
No latest-policy lookup. SQL functions pin `pg_catalog,public,pg_temp` and protect
all referenced names. Source parents are immutable; deferred checks must reject
missing parents and preserve caller rollback. PostgreSQL stamps accepted_at.

No reject-link or audit/outbox extension is needed: Review already stores exact
Submission/assignment, and canonical decision effects remain later composition.
The historical split record does not authorize unused duplicate persistence.

## Acceptance criteria

- Strict frozen input rejects extra fields, mixed/missing sources, invalid
  discriminator and non-native UUIDs. Construction grants no authority.
- Real human accept Review chain persists; reject/needs_revision sources deny.
- SQL rejects same-project and foreign-project coherent owner substitutions,
  wrong source/submitter/reviewer/locked policy and wrong-policy branch.
- Exact task/Submission/source uniqueness prevents second acceptance; rollback
  removes tentative rows and leaves canonical source history unchanged.
- Database-owned time and UPDATE/DELETE/TRUNCATE protection hold.
- Populated 0013 upgrade preserves owner rows; downgrade refuses using the
  existing canonical message; ORM/migration inventories agree.
- Both source shapes are represented without a synthetic Review. False-policy
  positive runtime/storage ancestry cannot currently be produced legitimately;
  do not bypass guide activation or fabricate a false graph to claim that proof.
  Exercise exact branch predicate reachability against real true manifests and
  pure false source transport. Full false-source positive proof is mandatory
  before activation. Record this limitation explicitly.

## Risk and review routing

- Risk class: L1 (terminal retained lineage).
- Plan review: architecture/reuse and security/QA feasibility before code.
- Implementation: architecture/reuse, security, QA/test-delta, CI integrity,
  documentation/product operations.
- Human review focus: storage-only versus authorized terminal truth; exact source
  exclusivity and locked lineage; no fabricated receipts or automated Review.

## Evidence

Planned focused proof under `tests/reviews/acceptance/`:

- `test_contracts.py`: closed source shapes and native immutable input.
- `test_storage.py::test_human_acceptance_source`: actual stored accept Review, exact fields.
- `test_non_accept_review_denied`: real needs_revision/reject source controls.
- `test_exclusive_source_shape`: mixed/missing sources and invalid discriminator.
- `test_acceptance_owner_substitution`: coherent same-project and foreign-project
  submitter/reviewer/Submission/policy/source substitutions; remove one exact owner
  predicate and prove the named rejection reaches DID NOT RAISE.
- `test_automated_branch_polarity`: real true-policy TASK manifest plus matching
  true ReviewPolicy and an existing service-kind actor; ordinary insertion denies.
  Replace only `(manifest,policy)=(false,false)` with `(true,true)` transactionally;
  the same negative assertion must reach DID NOT RAISE. Roll back all synthetic
  acceptance state; do not fabricate false activation or canonical router evidence.
- `test_acceptance_unique_and_rollback`: independent-session uniqueness and
  rollback, no second acceptance and unchanged source history.
- `test_acceptance_clock_and_immutability`: database-owned time, update/delete/truncate denial.
- `test_missing_acceptance_source`: missing parent and concurrent parent rollback.
- `test_migration.py`: real populated predecessor upgrade plus refusal.
- Existing `test_identifier_schema.py`, complete `test_alembic.py`, lane catalogue,
  owner inventory and affected Review/TASK tests retained.

Run focused tests against isolated PostgreSQL/MinIO, Ruff, module boundaries,
structural/ownership checks, Commitrail, Markdown links and all stale wording
scans. Full hosted nine-lane completeness and real API contract remain required;
coverage is diagnostic. Freeze clean review target and reconcile current main.

## Required later activation proof

The same-table authority hardening must deliver
`test_acceptance_authority_upgrade_refuses_retained_foundation`: a nonempty
foundation table aborts upgrade with all rows unchanged and no backfill or deletion.
`test_acceptance_authority_upgrade_empty` must prove an empty table gains a
NOT NULL AUTH event relationship and exact action/source/actor/request/resource
and fixed TASK-router predicates. No production writer, CON consumer or accepted
TASK effect may activate before this hardening. These named future tests are
activation requirements, not execution evidence delivered by REV-04B.

## Review findings

Plan review required explicit future authority-upgrade refusal/empty-upgrade
proof and a discriminating automated-branch predicate probe. Both are named
above; generic service-kind transport is never treated as canonical provenance.

## Reconciliation

- Current-source reconciliation: starts after merged REV-04A; its exact immutable
  Review source removes the previously missing human FK target.
- Next usable boundary: CON-03C contribution/award persistence, CON-07 submitter
  participant and the existing REV-12A/CON fence foundation, then one shared
  acceptance operation and ARCH-04E1B/04E2/04E3 routing; false activation also
  waits for ARCH-04F remediation.
- Remaining risks: no current row conveys acceptance authority; before runtime,
  require exact mandatory AUTH receipts, currentness/fence serialization, atomic
  CON/TASK/audit/outbox effects and real positive false-policy composition proof.
