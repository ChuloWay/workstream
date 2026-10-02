# REV-04A — Immutable Review source storage

- Initiative: `WS-REV-001`
- Durable disposition: `Planned`
- Intended merge outcome: complete immutable Review source storage for shared FinalAcceptance, without activating human decisions or acceptance.

## Intent and current behavior

Continue the approved packet -> Review -> shared FinalAcceptance sequence.
Main `fcff997f` contains REV-03B packets, queue/lease storage and exact immutable
Submission lineage, but no Review table. Shared acceptance needs a real human
source relation even when the automated branch becomes the first runtime path.

The archived 04 parent is design history, not an implementation checklist.
Canonical `docs/spec_review_lifecycle.md` excludes separate finding/response
artifact uploads in v0.1. Do not add ReviewEvidenceArtifact or revive an ART
upload path. SubmissionFindingResponse requires the exact revision preparation
head; that owner is not present. Its schema belongs with preparation storage,
not an unchecked UUID or a compatibility field here. Review source storage must
retain exact predecessor/finding relations without claiming revision admission.

## Bounded change

### Allowed

- `backend/app/modules/reviews/decision/`: cohesive internal immutable Review,
  finding, resolution and decision-request storage models and strict value
  contracts only; no production writer or repository.
- `backend/app/db/models.py`: register the new models.
- `backend/alembic/versions/0013_review_source.py`: additive schema, exact owner
  constraints, safe qualified SQL, immutable aggregate guards.
- `backend/alembic/env.py`: current migration predecessor/head registration.
- `backend/tests/reviews/decision/`: focused contracts, real PostgreSQL ownership,
  immutable aggregate, caller rollback, concurrency and migration proof.
- `backend/tests/conftest.py`, `backend/tests/test_alembic.py`: new schema/reset
  inventory and measured fingerprint, preserving required validation.
- `backend/scripts/identifier_inventory.py`, `backend/tests/test_identifier_schema.py`:
  classify any new natural keys; preserve surrogate UUIDv7 enforcement.
- `backend/scripts/test_lane_catalogue.py`, `backend/tests/test_ci_lane_catalogue.py`:
  register new proof in existing lanes without excluding existing tests.
- `backend/scripts/behavior_ownership.py`, `backend/tests/test_behavior_ownership.py`,
  `.ci/behavior-ownership/partition.v1.json`: exact new owner inventory.
- This record and `.commitrail/INDEX.md`.
- `.commitrail/initiatives/WS-REV-001/OVERVIEW.md`
- `.commitrail/initiatives/WS-ART-001/OVERVIEW.md`
- `.commitrail/initiatives/WS-AUTH-001/OVERVIEW.md`
- `.commitrail/initiatives/WS-AUTH-003/OVERVIEW.md`
- `.commitrail/initiatives/WS-CON-001/OVERVIEW.md`
- `.commitrail/initiatives/WS-POL-003/OVERVIEW.md`
- `.commitrail/initiatives/WS-ARCH-001/OVERVIEW.md`
- `.commitrail/initiatives/WS-AUTH-001/planning/PLAN.md`
- `.commitrail/initiatives/WS-AUTH-001/planning/CHUNK_MAP.md`
- `.commitrail/initiatives/WS-POL-003/planning/PLAN.md`
- `.commitrail/initiatives/WS-POL-003/planning/CHUNK_MAP.md`
- `.commitrail/initiatives/WS-ARCH-001/planning/PLAN.md`
- `.commitrail/initiatives/WS-ARCH-001/planning/CHUNK_MAP.md`
- `.commitrail/initiatives/WS-ARCH-001/planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md`
  These pages advance only the delivered Review-storage prerequisite.
- `README.md`, `docs/roadmap_status.md`, `docs/architecture_data_model.md`,
  `docs/spec_review_lifecycle.md`, `docs/spec_artifact_storage_service.md`,
  `docs/engineering/authorization_activation_custody.md`: reconcile affected
  capability, storage/activation distinction and next dependency.
- Local ignored roadmap exports only if present.

### Prohibited

No public route, AUTH activation, canonical decision command, CON/no-op
participant, acceptance operation, queue routing, lease claim, artifact/provider
access, revision preparation/runtime, baseline rewrite, retained-data deletion,
compatibility alias, second workflow, or weaker CI/coverage/timeout gate.

## Design review requirements

The exact Review/request/child schema below follows canonical owners. Review stores the exact lease, packet, Submission/assignment,
reviewer, locked ReviewPolicy and contribution-policy identity, decision and
bounded narrative. Later judgment never mutates an earlier Review. A single
Review belongs to one lease and Submission. A predecessor must follow real
same-task Submission ancestry; unrelated valid stored rows must fail.

Child membership must be immutable as a complete aggregate, including preventing
late inserts after the parent commits. Required blocking findings for
needs_revision and bounded reject reasons must be enforceable independently of
input DTOs. Finding resolutions refer to required prior findings without
changing their source rows. Decision request replay retains exact identity,
actor/scope and request digest; it must not become authority or a production
creation service. PostgreSQL owns timestamps. No current-policy lookup.

Storage fixtures are not a canonical authorized decision path: runtime composition
still requires AUTH, CON, the shared fence and atomic lifecycle effects. Do not
claim these missing participants are delivered or supply a fake implementation.

## Exact storage contract

Four tables, no mutable reservation state or unfinished Review:

- `reviews`: UUIDv7 id; exact project/task/Submission/version/assignment,
  queue/lease/packet identity and digest, canonical ZIP artifact_hash, reviewer, immutable reviewer ContributionPolicyVersion,
  locked guide version and ReviewPolicy id/generation/hash; nearest
  predecessor Review (nullable only with no reviewed Submission ancestor);
  decision, summary (1–4000 nonblank characters), finding_count,
  blocking_finding_count and resolution_count (0–100), semantic digest and
  PostgreSQL-owned completed_at. Unique Submission, lease, packet and non-null
  predecessor prevent duplicate or branching human decisions.
- `review_findings`: UUIDv7 id, Review id, item_order (0–99), kind
  blocking/advisory, nonblank area (1–200), issue and required_fix (1–4000).
  Unique Review/order. Completion time is inherited from the owning Review.
- `finding_resolutions`: UUIDv7 id, resolving Review id, prior finding id,
  item_order (0–99), result resolved/unresolved/not_applicable and nonblank
  rationale (1–4000). Unique Review/finding and Review/order.
- `review_decision_requests`: UUIDv7 id and operation_id, project/reviewer,
  caller UUID idempotency_key, non-null Review id, exact request digest.
  Unique project/reviewer/key, operation and Review. Deferred Review FK allows
  one complete request and Review to be staged in either order; rollback removes
  both. No status, pending row, unvalidated AUTH receipt or nullable source.

The semantic digest uses canonical JSON with domain
`workstream.review_source.v0.1`, all immutable Review source selectors, decision,
summary, counts and ordered complete findings/resolutions (including their IDs).
The request digest binds the same full aggregate. Future commands must recover
existing generated IDs before recomputing replay, never derive record IDs from
keys. IDs and times are not authority. Every protected SQL name is qualified and
functions pin `pg_catalog, public, pg_temp`.

Before Review insert, lock lease -> queue -> task; check active, unexpired lease
using PostgreSQL clock, exact current queue pointer and packet. Deferred checks
require consumed/review_recorded lease and closed/review_recorded queue. Exact
Submission/packet ownership, assignment, human reviewer distinct from submitter,
locked human_review_required=true policy and contribution policy are reconciled with persisted owners. Artifact hash is the sha256-prefixed canonical ART content SHA-256, never caller package_hash.
Immutable terminal source joins do not require the old policy to remain current. Individual existence FKs and qualified SQL reconcile tuples for which current owners have no composite unique keys; do not claim single-column FKs prove full ownership.

Nearest predecessor follows the same-task Submission supersedes chain, passing
through checker-correction submissions without inventing Reviews. Non-null
predecessors must be needs_revision. Finding resolutions reference only open
findings on that Review ancestry. Resolved/not_applicable closes a finding;
unresolved leaves it open. Every inherited open blocking finding needs a current
resolution. Accept has neither new nor unresolved inherited blocking findings;
needs_revision has at least one of those. Reject uses its bounded summary as
human reason and does not fabricate findings.

Counts describe new findings and current resolutions, not historical totals.
The inert AUTH decision contract currently requires a new blocking finding for
needs_revision; later decision composition must reconcile inherited-only blockers
before activation, without changing the meaning of its existing count fields.
The lease freezes ContributionPolicyVersion.id; do not fabricate the contribution-policy digest triple mentioned by the inert AUTH contract. That owner-contract reconciliation, plus 09A3/09B response/preparation custody, is required before human decision activation. No runtime authorization behavior is introduced here.

Parent and child deferred checks lock the immutable Review and recompute exact
count/order/digest closure. A late child cannot extend a committed aggregate.
All four tables reject updates, deletes and truncation. The current data-model
page will remove unimplemented confidence/arbitrary evidence arrays and label
future evidence upload separately, consistent with the canonical v0.1 scope.

## Acceptance criteria and verification

- Real stored packet/lease/Submission control yields exact immutable Review
  source facts; all three canonical decision values have valid controls.
- Coherent foreign-project and same-project sibling substitutions fail at the
  intended owner guard, with valid digests/other fields preserved.
- Invalid decision, missing blocking finding, blank rejection reason, wrong
  policy/actor/packet/predecessor and child ownership fail specifically.
- Update/delete/truncate and post-commit child insertion fail; independent-session
  concurrent parent/child and duplicate request cases preserve complete evidence.
- Exact request lookup and conflicting keys remain distinct; caller rollback retains
  no partial aggregate. No production writer or public endpoint is introduced.
- At least one owner-predicate and one aggregate-custody removal probe reaches
  the intended negative assertion, rather than failing fixture setup.
- Migration preserves populated predecessor owner rows and rejects downgrade
  that would delete retained Review evidence.
- Strict contract tests, real PostgreSQL tests, Ruff, module boundaries, ownership,
  Commitrail, Markdown links, stale wording and complete hosted lanes pass.

## Named proof plan

New tests under `backend/tests/reviews/decision/`:

- `test_contracts.py`: closed types, bounds, AUTH decision-value parity,
  canonical digest includes changed scope and all nested fields.
- `test_storage.py::test_complete_decision_aggregate`: three valid decisions,
  exact stored lineage and every nested field compared to the source.
- `test_storage.py::test_owner_substitution`: coherent foreign and sibling
  owners with recomputed digest; exact rejection plus removed owner predicate.
- `test_storage.py::test_lease_terminal_custody`: expired active lease and
  missing consumed/closed state reject, exact valid atomic control.
- `test_storage.py::test_predecessor_chain`: checker-only gaps, nearest Review,
  wrong/null predecessor and branch denial.
- `test_storage.py::test_finding_carry_forward`: required inherited blockers,
  resolved/not_applicable closure, no reopening, inherited-only needs_revision.
- `test_storage.py::test_aggregate_immutability`: count/digest mismatch,
  late child, update/delete/truncate; removed aggregate predicate fails proof.
- `test_storage.py::test_request_custody`: missing/mismatched request, exact
  stored association and key/digest conflict; caller rollback.
- `test_storage.py::test_concurrent_request_and_child`: separate PostgreSQL
  sessions observe real conflicts/parent visibility, not mocked scheduling.
- `test_migration.py::test_review_upgrade_preserves_owners`: populated predecessor
  upgrade, exact new schema and non-destructive downgrade rejection.

Run backend `.venv/bin/python -m pytest tests/reviews/decision -q` against
isolated real PostgreSQL through the existing fixture/runner, plus affected
packet/ART contracts and schema inventories. Run Ruff on changed Python,
`python -m scripts.module_boundaries validate --protected-base origin/main`,
`python -m scripts.behavior_ownership validate`, root Commitrail validation,
Markdown link/stale scans, then all hosted lanes and canonical retained-evidence
validation. Test names above are future implementation targets, not results.

## Risk and review routing

- Risk class: L1 — bounded immutable storage and shared acceptance source lineage.
- Required reviewers: architecture/reuse, security, QA/test-delta, CI integrity,
  documentation/product operations, with preimplementation plan review.
- Human review focus: exact immutable source custody and the explicit separation
  between storage and authorized decision/acceptance runtime.

## Reconciliation

- Current-source reconciliation: merged #460 supplies exact packet membership,
  PostgreSQL lease deadlines, immutable complete sets and retained replay.
- Next usable boundary: REV-04B shared FinalAcceptance persistence, then the
  approved CON and shared-fence prerequisites before runtime routing.
- Remaining risks: no runtime human decision, revision response admission or
  automated acceptance is delivered by this storage boundary.
