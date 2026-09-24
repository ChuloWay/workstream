# WS-DB-002 — Uniform UUIDv7 record identities

- Disposition: Planned
- Intent: every Workstream-owned generated record identity uses UUIDv7 and native
  PostgreSQL UUID storage; references use the same type. Recreate disposable
  development data rather than preserve earlier development identities.
- Current change: [planning record](WS-DB-002-PLAN.md).

## Problem and human direction

Workstream is unreleased v0.1. Its record identities currently mix UUIDv4,
deterministic UUIDv5, native UUID columns and UUID strings. Standardize the first
version rather than add compatibility implementations. The human explicitly
does not require preservation of existing development rows for this change.
Planning is authorized; implementation and destructive execution have not begun.

UUIDv7 improves time locality of generated keys; native UUID avoids text storage
overhead. Neither guarantees faster whole-product queries or shorter CI. Measure
those separately. References: [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html),
[Python UUID](https://docs.python.org/3.14/library/uuid.html),
[PostgreSQL UUID](https://www.postgresql.org/docs/18/datatype-uuid.html).

## Current-source findings

Discovery is based on main after ARCH-03C3. Refresh the inventory before coding;
the following is an owner map, not a claim that every column has been audited.

| Owner | Current paths and relevant behavior |
|---|---|
| Model registration | `backend/app/db/models.py` registers the graph; migration-only objects must also be inventoried |
| ACTORS / AUTH | `modules/actors/models.py` uses text UUID keys; `modules/authorization/models.py` mostly native UUID; services and kernel create v4 identities; `authority_control.id=1` is a singleton, not a generated identity |
| PROJECTS | `modules/projects/models.py` mixes text entity keys with native command receipts; `guide_compilation/models.py` and `post_policy/models.py` have native keys but some deterministic v5 writers |
| TASK / shared AUDIT | `modules/tasks/models.py` mixes native command receipts with text task, assignment, submission and audit keys; `authorized_commands.py` reserves task identity before insertion |
| ART / CHECKERS | `modules/artifacts/models.py` and `modules/checkers/models.py` primarily use text record IDs; ART includes persisted deterministic pre-submit attempt identities and semantic namespace/scope keys |
| CON / compensation / REV / outbox | Native generated keys already exist; generation and references still require audit; outbox delivery attempts reuse `(event_id, claim_generation)` |
| Schema | `backend/alembic/versions/0001_v01_baseline.py`, `backend/alembic/baseline/` and successors through `0030_task_management.py`; SQL guards bind UUID/text values, JSON facts and exact decision/receipt identities |
| Runtime | `backend/pyproject.toml` allows Python >=3.11,<3.13; hosted jobs use Python 3.12/PostgreSQL 16, without native v7 generators |

Generated UUIDs also appear in adapters, bootstrap scripts, database reference
data, workers, drills and fixtures. Do not limit discovery to `id` columns or
`uuid4()` imports. Include `event_id`, `operation_id`, defaults, raw SQL, indirect
generators, fixed service identities, JSON references and object-key construction.

## Target contract

1. Every generated surrogate record key is UUIDv7, including event, receipt,
   attempt and operation keys. No retained v4/v5 record-ID generation path.
2. Store UUID identities and their relational references as PostgreSQL `uuid`,
   represented internally as Python `UUID`; serialize canonical strings at JSON,
   HTTP, log and object-storage boundaries. No string/UUID dual domain model.
3. Preserve meaningful natural/composite keys: currency codes, namespace names,
   rate-limit digest/scope, singleton control key, and delivery generation.
   UUID components of composite keys still use native UUID. These are not
   grandfathered surrogate IDs and must be explicitly classified in the inventory.
4. External issuer subjects, client idempotency/request tokens, content hashes,
   business version labels and non-row deterministic selectors keep their own
   semantics. Do not force UUIDv7 on caller keys or turn a hash into a row ID.
5. UUID timestamps are not authority, expiry, business time, causal order or
   commit order. Retain explicit timestamps and stable pagination contracts.
   IDs reveal approximate generation time and must never be treated as secrets.

## Generation and retry design

Use one shared `backend/app/core/identifiers.py` record-ID function backed by a
maintained RFC 9562 implementation supporting the pinned runtime. Do not write
custom bit packing or add a v4 fallback. Select and pin the dependency during the
first boundary after checking license, maintenance, platform support, randomness,
same-millisecond behavior, clock regression and process/fork safety. Do not
upgrade Python or PostgreSQL merely to obtain a built-in generator.

Application-side generation is required for identities reserved before insert,
including TASK create. Database constraints enforce v7 version/variant on owned
surrogate keys even for direct SQL writers; no second database generator.
Constraints and ORM metadata must match. Foreign keys inherit referenced identity
requirements; external request-key columns do not receive a v7-only constraint.

Deterministic v5 row identities need semantic replacement, not substitution:

- `authorization/api/project_setup_finalization.py`,
  `authorization/api/project_guide_projections.py` and their PROJECTS consumers;
- `projects/post_policy/service.py`, `projects/guide_activation/service.py`,
  `projects/submission_policy_mutation_service.py`;
- `artifacts/pre_submit_attempts.py` and persistent uses in pre-submit evidence;
- `adapters/auth/assignment_invalidation_publication.py` and other outbox writers.
- `schemas/auth.py::actor_id_from_external_identity` and ACTORS first-access
  resolution: `(issuer, subject)` remains the external identity lookup, but the
  persisted ActorProfile ID becomes v7, not a deterministic external-subject exception.

For each, trace the original deduplication tuple and owner. Reuse its existing
receipt/operation uniqueness to reserve a v7 identity once, atomically, then
recover that exact identity on retry. When uniqueness currently exists only
through the derived UUID, enforce the equivalent business tuple with an owner-local
unique constraint and lookup. Concurrent losers recover the winner; changed
payloads conflict only after required fresh authority. Never generate another
persisted identity per retry, randomize an authorization selector, or introduce
a generic cross-module identity registry. Update AUTH fact construction, payload
digests and SQL validators together. Preserve the established lock order and
ensure pre-authorization reservation cannot commit an unauthorized product row.
For assignment-invalidation delivery, the stable deduplication key is the cause
and assignment tuple, not a newly generated event ID. The outbox owner must
recover the first stored event ID on retries. Deterministic Celery/provider
request tokens are distinct from stored operation/event keys.

## Fresh-schema cutover and reset

There is no old-row conversion or preservation deliverable. Build one fresh
v0.1 baseline representing the final schema, reference data and required guards;
replace the superseded active migration graph, not an additional parallel baseline.
Give the new root a distinct revision and restrict the migration environment to
the new active graph so a previously stamped development database
cannot silently appear current. Existing nonempty or old-revision databases must
fail with explicit recreation guidance; never stamp them forward automatically.

Regenerate the baseline SQL/manifests using existing schema tooling. Preserve
the behavior proved by prior migration tests in fresh-schema tests (constraints,
triggers, authority, immutability, atomicity), not tests demanding an obsolete
upgrade path. Do not accept a manifest delta merely because fingerprints differ.
Review all changed constraints/functions/indexes and reference rows.

Before any reset, enumerate exact owned database/server, jobs, queue namespace,
artifact bucket/prefix and drill fixtures that refer to its IDs. Stop those
writers, recreate the named disposable database, reseed required reference data
and first-admin bootstrap, discard only associated disposable queue messages and
artifact references, then rerun smoke flows. Shared Redis, S3/MinIO buckets,
other agents' databases, private guide documents and unrelated files are not
implicitly disposable. If ownership cannot be established, stop that reset and
ask for the exact target. No global Docker prune or shared-volume deletion.
Operational recovery is a clean database with matching code/schema, not mixed
old/new writers or reconstruction of discarded development rows.

## Proposed implementation boundaries

These are sequencing guidance, not authorization or pre-created implementation
contracts. Each implementation PR receives its exact allowed-file contract when
started. All boundaries must be complete before claiming uniform identity.

### 01 — Complete identity inventory and shared generation foundation

Allowed: core identifier helper, pinned dependency/lock, focused identifier tests,
schema/generation inventory checks and the current identifier specification.
Inventory every generated key, reference, deterministic replay owner and semantic
exception across the registered models and migrated schema. Choose the dependency
with evidence. Test the generator without switching production writers yet.
The inventory must identify unclassified/new tables, not silently omit them.
No data reset, schema mutation, behavior change or claim that rollout is complete.

### 02 — Coordinated product and fresh-schema cutover

Allowed: inventoried model/owner/adapter/port/schema writers and affected callers;
baseline and SQL guards; bootstrap, drills and tests; identifier enforcement;
AGENTS.md/CONTRIBUTING.md/README.md and current specifications/roadmap. Reconcile
README's named baseline and broad volume-reset examples with scoped reset ownership.
Switch all record writers and UUID references together, replace deterministic
row-ID replay with owner-local reservation, install the new baseline, enable
enforcement and prove a clean deployment. No temporary v4/v5 record-ID fallback,
retained-ID bridge, weakened guards, lifecycle changes or changed API exposure.

This is broad critical work (L0), not a small mechanical PR. Use the completed
dependency inventory to judge reviewability before implementing. If it requires
splitting, propose dependency-closed owner boundaries first; each must leave main
functional without compatibility code. Do not silently multiply planning PRs or
merge a half-converted schema. Schema-connected edits must land together.

## Verification and acceptance

Proposed test files below are future implementation obligations, not existing
passing evidence. Add their real nodes to the existing lane catalogue; keep full
hosted tests, coverage floors and real PostgreSQL. Avoid a new parallel CI system.

| Required proof | Test or existing owner |
|---|---|
| RFC layout, canonical round trip, v7 variant/version, concurrent process generation, clock behavior without claiming global ordering | proposed `backend/tests/test_identifiers.py`; compare valid v7 with forced-v4 generator defect |
| Every surrogate PK native UUID/v7-constrained; FK components match; semantic exceptions exact; no omitted model/migration table | proposed `backend/tests/test_identifier_schema.py`; add a text/v4 test table and require inventory failure |
| Direct SQL cannot insert a v4/v5 surrogate ID; external idempotency v4 remains valid | same schema tests with valid-control rows satisfying all unrelated guards, then change only the record ID |
| Fresh baseline works; previous revision/nonempty DB refused; model/schema/SQL-guard parity and reference data correct | extend `backend/tests/test_alembic.py`, `backend/tests/test_database_reset.py` and schema-manifest tests |
| Retry recovers one v7 row/event, racing writers do not duplicate effects, rollback leaves no orphan, revoked/foreign identity denied | existing owner suites for TASK receipts, guide finalization/projections, post-policy, pre-submit and outbox; add paired duplicate-key/different-payload and independent-session races |
| Exact AUTH decision, audit lineage, immutable evidence and content hashes remain bound after type changes | current AUTH/TASK/ART/CON/PROJECTS suites and direct-SQL guard tests, with wrong-resource and substituted-decision negative controls |
| UUID serialization, object locators, filters, joins and equal-time pagination remain correct | public API/queue tests, `backend/scripts/api_contract_e2e.py`, MCP real-API contract and worker/adapter drills |
| Benefit measured without inventing a threshold | matched v4/v7 PostgreSQL insert workload with same native type, indexes, row count and concurrency; record latency/index sizes/buffers, separate text/native comparison |

Run applicable focused tests from `backend/` with
`.venv/bin/python -m pytest <paths>`; exact commands and test names must
be finalized in implementation records. Full hosted Backend is the authoritative
full-suite proof, not a local timeout. A surviving faulty-ID or duplicate-retry
probe is a proof gap to fix, not permission to remove the assertion.

Completion requires no generated non-v7 record identities in the fresh populated
drill database, no text UUID relationship columns, passing reset/bootstrap/drills,
and no unresolved inventory entry. New conventions go into AGENTS.md only with
their implemented enforcement. Do not call this a product capability or mark it
delivered while it is merely planned.

## Coordination, risk and decisions

Refresh main and open PRs before each boundary. Product queue/read work overlaps
TASK models, pagination and fixtures; coordinate those exact paths without
halting unrelated product work. Do not rewrite another agent's branch or reset its
environment. Preserve Git history and Commitrail historical records; disposable
development data does not mean deleting engineering evidence.

Required implementation reviews: architecture (type/owner/schema graph), security
(identity, replay and audit), QA/test-delta (behavior and fault discrimination),
CI integrity for enforcement/dependency/baseline jobs, documentation for final
operating/reset guidance. Use focused assignments, not nine automatic reviewers.

Human direction already settled: v7 for all generated records, native UUID,
no development-data preservation, no backward-compatibility layer. No additional
product policy decision is needed. Actual reset target ownership and a selected
dependency remain implementation prerequisites; neither blocks preparing this plan.
UUID performance does not justify weakening authorization, retry atomicity or
content custody. Timestamp disclosure is an explicit identifier trade-off.
