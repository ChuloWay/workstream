# REV-03B — Immutable normalized reviewer packet persistence

- Initiative: `WS-REV-001`
- Durable disposition: `Planned`
- Risk: L1 (bounded schema, immutable evidence and owner contract correction).
- Intended merge outcome: REV persists one exact metadata packet per ReviewLease with normalized guide members; complete REV-04A Review storage is next. No claim, resolver, byte access or acceptance is activated.

## Intent

Continue the approved packet -> complete Review -> shared FinalAcceptance storage
sequence, so automated acceptance can become the first complete runtime path
without fabricating a Review. Build on merged ART-07A1 and the existing queue,
lease, Submission, checker and activated guide owners.

Current main `7754703f` has no packet persistence. Discovery also found that
ART-07A1's `guide_binding_id` targets the retired extraction binding table.
`retired_guide_material_write_guard` rejects every write to that table. The live
upload and guide manifest use `GuideSourceArtifactIngest.id`, exposed as
`ingest_id` by the PROJECTS public guide document contract. Replace the mistaken
field with that live identity in this affected scope; do not activate the old
table, add an alias, or delete retained data. Existing extraction evidence stays
read-only. The complete packet remains metadata-only.

## Bounded change

### Allowed implementation and proof files

- `backend/app/modules/artifacts/api/review_packet.py`: replace guide_binding_id with ingest_id, exact current owner vocabulary; no second contract.
- `backend/tests/artifacts/test_review_packet_contract.py`: update identity assertions and reject the removed field explicitly; retain all required proof.
- `backend/app/modules/reviews/packet_models.py`: normalized packet header and guide item models.
- `backend/app/modules/reviews/packet_schemas.py`: strict internal persistence input and detached stored result.
- `backend/app/modules/reviews/packet_repository.py`: caller-transaction persistence/replay and project-qualified stored metadata read.
- `backend/app/modules/projects/models.py`: correct the ingest model's stale not-yet-bound docstring only.
- `backend/app/db/models.py`: register the two REV models.
- `backend/alembic/versions/0012_review_packet.py`: additive tables, exact foreign keys, immutable/completeness guards, guide-ingest immutability, safe SQL name resolution.
- `backend/alembic/env.py`: accept predecessor and current migration head.
- `backend/tests/reviews/packet/__init__.py`
- `backend/tests/reviews/packet/support.py`
- `backend/tests/reviews/packet/test_storage.py`
- `backend/tests/reviews/packet/test_repository.py`
- `backend/tests/reviews/packet/test_migration.py`
- `backend/tests/conftest.py`: exact new resettable/guarded tables and measured schema fingerprint; no weaker validation.
- `backend/tests/test_alembic.py`: exact revision graph.
- `backend/scripts/test_lane_catalogue.py` and `backend/tests/test_ci_lane_catalogue.py`: additive registration in existing task lanes.
- `backend/scripts/behavior_ownership.py`, `backend/tests/test_behavior_ownership.py`, `.ci/behavior-ownership/partition.v1.json`: exact three-module REV addition and neighbor-rejection proof.

### Allowed current documentation

- This record; `.commitrail/INDEX.md`.
- `.commitrail/initiatives/WS-ART-001/WS-ART-001-07A1.md`: document the current corrected guide identity and link this repair, preserving its original delivery history.
- `.commitrail/initiatives/WS-ART-001/OVERVIEW.md`
- `.commitrail/initiatives/WS-REV-001/OVERVIEW.md`
- `.commitrail/initiatives/WS-ARCH-001/OVERVIEW.md`
- `.commitrail/initiatives/WS-AUTH-001/OVERVIEW.md`
- `.commitrail/initiatives/WS-POL-003/OVERVIEW.md`
- `.commitrail/initiatives/WS-CON-001/OVERVIEW.md`
- `.commitrail/initiatives/WS-AUTH-003/OVERVIEW.md`
- `.commitrail/initiatives/WS-ARCH-001/planning/PLAN.md`
- `.commitrail/initiatives/WS-ARCH-001/planning/CHUNK_MAP.md`
- `.commitrail/initiatives/WS-AUTH-001/planning/PLAN.md`
- `.commitrail/initiatives/WS-AUTH-001/planning/CHUNK_MAP.md`
- `.commitrail/initiatives/WS-POL-003/planning/PLAN.md`
- `.commitrail/initiatives/WS-POL-003/planning/CHUNK_MAP.md`
- `.commitrail/initiatives/WS-ARCH-001/planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md`
- `README.md`, `docs/roadmap_status.md`, `docs/spec_review_lifecycle.md`, `docs/spec_artifact_storage_service.md`, `docs/architecture_data_model.md`, `docs/engineering/authorization_activation_custody.md`.
- Local ignored roadmap exports only if present.

### Prohibited changes

No public route, ART resolver or materializer, provider I/O, extraction revival,
AUTH action/permission activation, claim/queue routing implementation, Review,
FinalAcceptance, CON effect, worker or acceptance trigger. No baseline rewrite,
retained-data deletion, compatibility field/alias, generic manifest framework,
JSON member set, workflow/timeout/coverage gate change or test suppression.

## Design

### Exact metadata and two normalized tables

`ReviewGuideMember` uses `ingest_id`, `source_item_id`, `item_order`,
`logical_role='guide_source_original'` and the existing guide media type. The
logical role describes a packet member; it does not assert a row in the retired
binding table. The existing header request retains all eleven scope fields.

`review_packet_manifests` columns:

- `id` (UUIDv7), `created_at` (PostgreSQL clock).
- `review_lease_id` (unique), `review_queue_entry_id`.
- The eleven ART request fields: `project_id`, `task_id`, `submission_id`,
  `submission_version`, `checker_run_id`, `result_id`, `guide_id`, `guide_version`,
  `source_snapshot_id`, `project_setup_run_id`, `setup_generation`.
- `submission_binding_id`, `submission_logical_role`, `submission_media_type`.

Exactly one required ZIP is represented by non-null header fields; no separate
one-to-one item table. All IDs/references use native PostgreSQL UUID, with native
Python UUID at new typed boundaries. Existing owner string representations stay
at existing boundaries. `result_id` is the aggregate CheckerRun.result_id.

`review_packet_guide_items` columns: `packet_id`, `source_item_id` (composite
primary key), `ingest_id`, `item_order`, `logical_role`, `media_type`.
Unique packet/ingest and packet/order. No surrogate ID for this natural member
key. Closed roles/media types, bounded nonblank guide version, positive versions,
nonnegative item order. No hash, size, provider/content/replica identity, receipt,
capability, raw policy, arbitrary metadata or source body in either table.

### Database custody

Restrictive FKs bind header to lease, queue, exact Submission/version, checker
run/result, guide/project/version, snapshot/project/guide, setup/snapshot/generation
and Submission binding; item rows reference header, source item and live ingest.
Additional canonical checks reconcile:

- Lease and queue exactly match the full project/task/Submission lineage and
  queue admitting run; checker is a completed allow-review source with matching
  aggregate result. Storage does not replace live claim/currentness authority.
- Submission's locked guide version/snapshot and original ZIP binding match;
  binding belongs to the exact Submission/project and original role/media.
- Guide activation custody identifies the exact setup run/generation, including
  a superseded historical guide; never select current/latest guide or setup.
- Each guide item matches its ingest/source-item, declared order and media,
  and exact header snapshot. The complete declared guide set is present in both
  directions, with 1..100 members. Missing/extra/swapped valid foreign members
  fail independently of malformed-ID guards.

Use deferred final-state checks for the atomic header/member insertion. No
persisted draft/sealed state or seal workflow is necessary: immutable header and
items, exact-set validation and unique natural identities prevent later append,
mutation or deletion. Parent absence must fail explicitly, including concurrent
parent visibility; no missing-row branch silently returns success. Protect
TRUNCATE as well as row mutations. PostgreSQL assigns creation time; callers
cannot forge it. Future replay is a read of the retained exact packet, not a
fresh claim or clock reset.

The live ingest writer `ArtifactRepository` already returns an identical row or
rejects conflicting prepared bytes; no production update/delete consumer exists.
Add unconditional update/delete/truncate protection for these immutable ingest
facts so retained packets cannot change meaning through a referenced source.
Do not add a check-then-update race dependent on whether a packet currently
exists. Snapshot items, Submission bindings, terminal checker evidence and
activated guide custody already have immutable owner protections. Preserve
mutable availability/status transitions that are outside semantic membership.

All new SQL functions use `SET search_path=pg_catalog,public,pg_temp`, fully
qualified protected relations/function calls and unambiguous argument names.
Temp-table names must not influence constraints. No privileged bypass fixture.

### Repository and proof boundary

`ReviewPacketRepository.store(lease_id, membership)` locks the exact
project-qualified REV lease before selecting/writing that lease's packet. It
allocates a UUIDv7 only for a new packet, inserts header and all guide rows, and
flushes without committing. Deferred checks stay within the caller transaction.
An identical retry returns the stored identity; any membership difference raises
one bounded conflict. Same-lease concurrency serializes through the lease row;
failed/rolled-back writes leave no packet or members. It acquires no AUTH,
project or contributor lock and cannot grant authority.

`read(project_id, lease_id)` returns only normalized stored metadata as detached
strict facts, ordered by source item order; qualify ownership before lookup.
`ReviewPacketStored` contains `packet_id`, `review_lease_id`,
`review_queue_entry_id`, `created_at`, and the canonical ART `membership` value.
A missing or foreign scope returns no packet. Authorization is a future caller's
responsibility; no endpoint or runtime composition exposes this repository.

## Acceptance criteria

- Correct the unusable ART field; removed `guide_binding_id` is rejected, never
  accepted as an alias. Existing strictness/privacy/shape proof is retained.
- Real PostgreSQL positive control creates a packet from current activated guide,
  admitted Submission and completed checker facts, then compares all header and
  nested values with their canonical owners.
- SQL rejects independently mismatched valid owners, wrong numeric version,
  result/setup substitutions, omitted/extra guide members, wrong ZIP/media/order,
  all immutable mutations, late appends, parent absence and source-ingest changes.
- Save/replay, changed replay, rollback, independent project lookup, concurrent
  same-lease store and retained historical read preserve identities and evidence.
- Temp-shadow probe cannot change validation. Mutation probes removing the
  specific membership/immutability guards fail the intended test assertions after
  a valid control, not fixture setup.
- Upgrade from 0011 preserves populated Submission/checker/guide/queue/lease facts
  and creates empty packet tables. Fresh schema, metadata parity, identifier
  inventory, exact reset schema and existing owner tests pass.
- Current navigation advances to complete REV-04A source storage; resolver,
  canonical claim and byte authority remain future work. Both acceptance branches
  continue to share one operation, without synthetic Review/actor.

## Risk and review routing

L1: architecture/reuse, security, QA/test-delta, documentation/product operations,
CI integrity. Pre-implementation review must check live ingest ownership,
reference immutability, declared-set completeness, concurrent insert proof and
real-fixture feasibility. Required human focus: exact retained lineage and no
runtime permission from metadata. One coherent schema/repository change may
exceed the usual 500-line preference because migration, direct-SQL failure proof
and current navigation are inseparable; no extra lifecycle is included.

## Evidence

Reuse `tests/tasks/post_submit_routing/support.completed_source` for actual
activated guide/admitted Submission/completed checker owners; use the existing
REV queue/lease repository with a real human actor and that Submission's stamped
published contribution policy. Guide ingests and declared source rows come from
the current unified guide fixture. Do not disable extraction write guards or
fabricate checker success/authorization receipts. These fixtures prove storage,
not a live claim API or ART resolver. Run focused tests with the canonical
isolated PostgreSQL runner, strict contract tests, migration/identifier/ownership
and lane inventory checks; run Ruff, module boundaries, Commitrail, links and
stale wording. Full hosted nine-lane and real API checks remain required, with
no skipped/deselected nodes. No spreadsheet exports are currently present.
