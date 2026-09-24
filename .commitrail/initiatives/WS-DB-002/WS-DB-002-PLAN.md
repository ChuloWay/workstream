# WS-DB-002 — UUIDv7 and native-UUID cutover

- Initiative: WS-DB-002
- Durable disposition: Planned
- Intended merge outcome: uniform UUIDv7 record generation and native UUID storage, with a fresh development baseline and aligned CI/local setup.

## Intent

The human requests implementation with the plan in the same PR, without preserving
disposable development data. Current models mix UUID and text identities; writers include v4 and
deterministic v5. The [overview](OVERVIEW.md) records owners, scope and retry risks.

## Bounded change

Allowed: this record/index/overview; backend core identifiers, owner models,
repositories/services/adapters and affected typed API callers; schema/baseline,
bootstrap/worker/drill tools; tests and lane inventory; pinned dependency/lock;
Compose/backend image/init and hosted backend/MCP checks; affected current docs,
AGENTS.md and contributor/reset guidance. The overview specifies the required
owner graph, internal stages and proof. Not allowed: permission/lifecycle changes,
new public APIs, v4/v5 surrogate fallback, weakened tests/coverage/guards, another
identity registry, unrelated cleanup, or reset of unverified/shared targets.
Assess roadmap technical-foundation and operating impact at completion; update
affected sections without claiming new product exposure. No separate planning PR.

The human also approved repairing the unavailable MinIO container distribution
within this PR: retain MinIO and real S3 tests, build its pinned upstream source
with verified inputs under `docker/minio/`, and reuse that image in CI and local
Compose. Build/cache once per Backend workflow and distribute the image to its
existing jobs; do not compile once per test lane, publish a new registry, replace
the provider, weaken checks, or change artifact volumes. Source/build pins and
license provenance must be explicit, and fresh-build health plus existing S3
tests must pass before readiness. These additions include affected workflow
contract tests under `scripts/`.

## Acceptance criteria

- Define generated record IDs versus meaningful natural/external keys.
- Specify native-UUID storage, one v7 generator, deterministic retry replacement
  and a fresh baseline without conversion/compatibility machinery.
- Cover safe reset boundaries, concurrency with product work, enforcement,
  behavioral proof, risks and implementation sequencing.
- Complete both internal stages and all overview proof obligations in one PR;
  keep disposition Planned until implementation evidence exists.

## Risk and review routing

- Risk class: L0 broad critical work.
- Required reviewers: architecture, security, QA/test-delta, CI integrity and
  documentation, assigned by owned impact rather than ceremonial fanout.
- Human review focus: uniformity scope, fresh-schema reset and realistic review size.

## Evidence

Source baseline: main after PR #436. The inventory accounts for 89 schema tables:
78 generated surrogate-key owners and 11 intentional natural/composite-key owners
(including the migration-only singleton). Native UUID references preserve each
owner's Python UUID or canonical-string representation.

Implementation proof includes fresh PostgreSQL 16 baseline installation, refusal
of the superseded schema stamp, native UUID round trips, named UUIDv4 rejection,
and first-access creation/race/rollback probes. Generator, metadata and inventory
checks pass; CI collection tests retain reproducible node identity without
replacing the runtime generator. Required database guarantees from removed
revision-history tests are rehomed in current-schema tests; lane catalogue checks
pass. These focused results do not certify the entire implementation.

Review-driven repairs bind projection custody to the exact audit correlation and
add version guards to generated non-primary operation identities. Artifact
producer references now accept the canonical UUIDv7 actor identity. Focused
PostgreSQL tests reject substituted projection correlation and UUID4 finalization
and activation operations. Natural compilation recovery also rejects changed
request, idempotency-key and actor facts instead of trusting a stored winner.
Public grant issue/revoke replay checks pass. Final frozen review remains required.
Hosted regression diagnosis identified native-UUID cursor binds, raw-driver fixture
types and a manual-policy PREP identity mismatch. Repairs retain exact prepared
resource binding: allocate the actual record IDs before preparation, and recover
an already committed same-key winner under the existing project lock with fresh
authorization. Projection finalization also checks its exact correlation selector.
The real MinIO source build and startup passed; that infrastructure result does
not certify the still-required full backend regression and coverage run.
The retained registered-actor dependency now uses the resolved canonical profile
ID instead of deriving a second identity; its focused regression and PostgreSQL
review-queue reservation pass. Outbox exact replay, concurrent commit/rollback
and changed-payload conflict probes pass. Fresh-schema manifest/function-body
verification and artifact recovery lineage pass against the isolated database.

Reproducible focused checks from `backend/`:

```sh
.venv/bin/ruff check app tests scripts
.venv/bin/pytest -q tests/test_identifiers.py tests/test_identifier_schema.py tests/test_identifier_inventory.py
```

Real-database checks use `scripts/run_isolated_tests.py` with an explicitly owned
`WORKSTREAM_TEST_ADMIN_DATABASE_URL`; do not point it at another worktree's
database. Required retained proofs include
`tests/test_identifier_schema_postgresql.py`,
`tests/test_alembic.py::test_fresh_database_matches_committed_manifest`,
the projection/finalization PostgreSQL guard suites, and the existing outbox
independent-session retry and rollback tests. Fresh-schema verification also
recompiles installed function bodies with validation enabled after every table
exists; migration-time deferred validation is not the final proof.

Remaining proof: complete affected owner regressions, full hosted tests/coverage,
baseline/model parity after final repairs, final docs checks and the
required exact-target reviews. Keep this change Planned until that work is done;
no compatibility path or separate planning PR is introduced. Other product work
remains independent except explicitly shared paths and environments.

### Bounded index comparison

PostgreSQL 16 in an isolated local container: two alternating UUID4/UUID7 trials,
10,000 records per identical table, 1,000-row insert batches. UUID4 inputs were
seeded-shuffled; UUID7 inputs retained generator order. Average generation time
was 0.1170s versus 1.0943s, and insert time 5.2508s versus 4.5663s. Primary-key
indexes were 409,600 versus 335,872 bytes. Both used indexed point lookups and
passed uniqueness, duplicate rejection and exact round-trip probes.

These small local observations support index locality, not an end-to-end speed
claim: UUID7 generation cost was higher, lookup timings were noisy, and no
distributed/concurrent production workload was measured. UUID7 does not replace
business timestamps, lifecycle generations or explicit ordering rules.

A separate representation comparison reused the same 10,000 UUID4 values and
payloads, excluding generation time. Across two alternating-order trials,
VARCHAR(36) inserts averaged 5.9087s and native UUID inserts 4.4234s; primary-key
indexes were 671,744 and 409,600 bytes respectively. Exact round trips,
uniqueness, duplicate rejection and indexed lookups passed in both representations.
This isolates storage representation from UUID version and carries the same
local-workload limitations above.
