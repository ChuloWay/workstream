# Stable Contribution Export Pagination — Fixed membership beyond 1,000 records

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: Authorized contribution JSON and CSV reads traverse a short-lived fixed membership beyond 1,000 records with fresh authority on every page.

## Intent

### Problem being solved

The public self and project contribution reads currently refuse any selected set
larger than 1,000 records. A normal `(recorded_at, contribution_id)` keyset does
not safely remove that ceiling: `ContributionRecord.created_at` is assigned at
insert time, so a transaction can stage a row after page one's boundary, remain
invisible to page one, commit before page two, and then enter a live keyset
traversal even though it was not a member of page one's result set.

### Why this work matters

Project evidence exports must remain complete and auditable as accepted work
grows. Every contribution visible in the first request's PostgreSQL snapshot
must appear exactly once even when other acceptances commit between pages.

### Current behavior

- `ContributionReadRepository.read` filters immutable records, orders them by
  `(created_at, id)`, probes row 1,001, and refuses the whole response when the
  fixed 1,000-record maximum is exceeded.
- `ContributionReadService.read` authorizes before loading facts and validates
  exact records, awards, task/source facts, actor labels and acceptance lineage.
- `contribution_export_response` owns one fresh `REPEATABLE READ` transaction,
  serializes JSON or CSV before committing the canonical ALLOW evidence, retries
  one SQLSTATE `40001`, and freshly reauthorizes a retried attempt.
- The current PILOT-10 record explicitly rejects timestamp ceilings, UUIDv7
  ceilings, tuple-xmin approximations, and exported PostgreSQL snapshots held
  across HTTP requests as fixed-membership mechanisms.

### Target behavior

The supported v0.1 completeness range is 1..100,000 contributions. The first
authorized request selects at most 100,000 contribution IDs in its
existing repeatable-read snapshot and, only when another page exists, stores
their exact order in one CON-owned expiring snapshot row. Pages contain 1..1,000
complete contribution items. A signed opaque cursor names that snapshot and the
next offset while binding the current actor, audience, project, normalized
filters, output format, page limit, ordering contract and expiry. Continuations
authorize first, then verify the cursor and stored snapshot, and project only
the retained page IDs through the existing owner ports.

## Bounded change

### Allowed

- `.commitrail/changes/stable-contribution-export-pagination.md` for this
  bounded intent, plan, evidence and final reviewer dispositions.
- `backend/alembic/versions/0040_contribution_export_snapshots.py` and the CON
  record model for one expiring snapshot table containing bounded ordered UUID
  membership, exact caller/query binding, database timestamps and supporting
  expiry/selection indexes. The reserved predecessor is
  `0039_false_guide_activation`.
- `backend/app/modules/contributions/api/records.py` for page request/response,
  position and closed cursor failures; the maximum page size is 1,000, the
  initial fixed-membership allocation is at most 100,000, and the default page
  size is 1,000.
- `backend/app/modules/contributions/records/{pagination,read_repository,read_service}.py`
  for the CON-owned signed cursor, fixed-membership materialization, bounded
  expired-snapshot pruning and exact page projection.
- Existing contribution adapter, export dependency and routes for pagination
  secret composition, query parameters, generic cursor errors, JSON
  `next_cursor`, the equivalent CSV continuation response header, and the
  existing authorization-read rate-control dependency without its early
  nonhuman concealment wrapper.
- `backend/app/modules/authorization/contribution_read.py` only if needed to
  retain a digest of the normalized page query and presented cursor without
  persisting raw cursor material; no evaluator, permission or grant change.
- Focused existing contribution export/projection/CSV/AUTH tests, a focused
  snapshot migration test, exact test-lane inventory updates required for any
  new test module, and only the behavior-ownership metadata required by changed
  eligible source paths.
- Affected current contract text in `README.md`,
  `docs/spec_contribution_compensation.md`,
  `docs/spec_authorization_service.md`, and `docs/roadmap_status.md`.

### Not allowed

- CLI changes; issue #499 has separate ownership.
- Contribution, award, policy, acceptance, review, task, artifact or economic
  mutation; fulfillment, payout, reconciliation, reputation or broad
  all-project export.
- New AUTH actions, permissions, roles, grant coverage, evaluator behavior or
  concealment weakening.
- Cross-request database transactions, exported PostgreSQL snapshot handles,
  timestamp/UUID/xmin membership approximations, mutable membership, or a
  generic export platform/maintenance subsystem.
- Private owner payload expansion, raw cursor persistence/audit, compatibility
  routes, alternate factories, workflow reductions, test skips or weakened
  assertions.

## Design and decisions

### Fixed membership and owner projection

The first page runs canonical AUTH before membership selection. The CON
repository reads only ordered contribution IDs under the response's existing
repeatable-read snapshot, probes the 100,001st ID, and refuses an oversized
selection before storing or serializing anything. When the result exceeds the
requested page size, one snapshot row stores the complete UUID array, its
creator actor, canonical query digest, database creation/expiry timestamps, and
UUIDv7 record identity. The array is immutable, non-null, duplicate-free by
owner validation, and database-bounded to 100,000 members. A database trigger
rejects snapshot updates while allowing the owner repository to delete expired
ephemeral rows. Existing immutable
ContributionRecord foreign/source constraints remain the source of truth; the
snapshot grants no authority and creates no contribution fact.

A continuation loads the exact snapshot only after fresh canonical authority,
requires actor/query/expiry equality, slices the requested ordinal range, and
loads exactly those IDs. Returned record IDs and `(recorded_at, id)` order must
equal stored membership. Every page then uses the existing page-sized award,
task, actor and acceptance owner reads and their missing/extra/economic-lineage
guards. Page size never exceeds those owners' existing 1,000-key contracts.

### Cursor, replay and concealment

The cursor uses the configured 32-byte pagination HMAC secret and strict
canonical Base64url/JSON parsing. Its closed payload contains version, query
digest, snapshot UUID, next offset and exact database expiry. The query digest
binds action/audience, actor, project, contribution type, UTC half-open recorded
range, output format, limit and `recorded_at_uuid_asc` order. It contains no
contribution, award, task, source, label or grant facts.

Each cursor is stateless and replayable until expiry: replaying it with current
authority returns the same membership page while producing a fresh response
timestamp and canonical read decision. Starting another export does not mutate
an earlier snapshot. A revoked caller receives the existing concealed 404
before cursor decoding or snapshot lookup. An otherwise authorized request with
a malformed, forged, expired, missing or query-mismatched cursor receives one
generic 422 cursor error; it discloses no snapshot or contribution existence.
Serialization or first-page transaction failure rolls back both new snapshot
state and staged ALLOW evidence. A later-page failure leaves the already
committed snapshot replayable and rolls back only that attempt's ALLOW evidence.

### Lifetime, allocation and cleanup

Snapshot access expires one hour after the database creation timestamp. Every
page compares both cursor and stored expiry with database `clock_timestamp()`;
the one-hour boundary does not claim guaranteed physical deletion at that
instant. Each initial request allocates at most one row and 100,000 UUIDs;
selections above that bound receive a documented full 422 refusal with guidance
to narrow filters before any snapshot state or body is produced.

Both contribution routes consume the existing authorization-read rate control
directly. They do not use `enforce_human_authorization_read`, because that
wrapper would conceal service callers before the canonical contribution AUTH
evaluator can commit its existing DENY evidence.

In addition, an actor may retain at most five contribution export snapshots.
Each snapshot owns one allocation slot in 1..5 and the database enforces unique
`(actor_profile_id, allocation_slot)` occupancy. The repository prunes the
actor's expired rows before selecting one free slot and inserts with exact
conflict handling; the unique constraint is the final concurrency fence even
when two repeatable-read transactions both observed slot 5 as free. In a 4→5/6
race, one request acquires slot 5 and the other receives a conservative generic
429. Continuations do not allocate slots and remain available at capacity.
`Retry-After` uses the earliest expiry visible to the refusing transaction, or
the one-hour maximum when a conflicting newly committed slot is outside that
snapshot. It does not disclose snapshot membership or another actor's state.

Every authorized export request prunes at most 25 expired snapshot rows using
the existing repository convention of expiry order plus `FOR UPDATE SKIP
LOCKED`. The expiry index supports both bounded pruning and exact stale-state
tests. Pruning is transaction-owned: a failed response rolls it back, and a
later request can retry it. No product fact or immutable evidence row is
deleted; physical removal remains opportunistic without a new cleanup worker.

### JSON and CSV

JSON adds `next_cursor`; CSV continues to flatten the same complete page with
one row for zero awards and up to two rows for awards. CSV carries the same
cursor in `X-Workstream-Next-Cursor` when another page exists. Output format is
cursor-bound, so a traversal cannot change serialization rules mid-snapshot.
CSV row counts remain distinct from contribution counts.

### Alternatives considered

- A high timestamp/UUID boundary was rejected because insertion time is not
  commit visibility order: A and B commit, late L is staged after both, page
  one's authorization SQL fixes a repeatable-read snapshot while L is invisible,
  L commits before page one's owner selection continues, and page one with
  `limit=1` fixes membership as A/B. A fresh live keyset would later admit L even
  though page one's snapshot contained only A and B.
- PostgreSQL exported snapshots were rejected because their exporting
  transaction must remain open across HTTP requests.
- One membership row per contribution was rejected because a bounded UUID array
  preserves the same immutable ordering with much smaller write, cleanup and
  migration surface for the v0.1 maximum.
- A reusable generic export/snapshot framework was rejected because no second
  concrete owner needs it.

## Acceptance criteria

- [ ] Traversing any supported selection of 1,001..100,000 records returns every
      member visible in page one's snapshot exactly once; selections above
      100,000 receive one documented full refusal before state or output.
- [ ] A discriminating real PostgreSQL race commits A and B, stages late L,
      starts page one with `limit=1`, pauses after its first authorization SQL
      fixes the snapshot, commits L before owner selection continues, then proves
      traversal returns B and ends without L. A deliberately fresh live keyset
      would wrongly admit L on another page.
- [ ] Every page preserves complete zero, one and two-award sets, exact decimal
      strings, source lineage, stable ordering and zero-award CSV visibility.
- [ ] JSON and CSV traversals over an unchanged source select the same
      contribution membership and exact values; CSV exposes the next cursor
      without treating flattened award rows as page membership.
- [ ] Malformed/tampered cursors and caller, project, filter, format or limit
      substitution fail generically; an unauthorized or revoked continuation
      is freshly denied and concealed before cursor/snapshot lookup.
- [ ] Cursor replay is deterministic until expiry; missing/expired state is
      generic, and bounded concurrent pruning neither deadlocks nor deletes a
      live traversal.
- [ ] Both routes consume the existing authorization-read rate limit without
      bypassing canonical service-caller DENY evidence. Two independent
      repeatable-read sessions racing from four occupied slots commit at most
      slot 5; one generic capacity refusal occurs and existing continuations
      remain available.
- [ ] First-page snapshot creation and ALLOW evidence roll back on projection,
      serialization, over-limit and driver failure; the existing bounded 40001
      retry creates at most one committed snapshot and one fresh ALLOW.
- [ ] Migration/model parity, UUIDv7/query/time/member checks, expiry index and
      snapshot query/index use are proved on real PostgreSQL.
- [ ] Existing contribution read authorization, concealment, immutable source
      and economic facts, and unrelated API behavior remain unchanged.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `architecture`, `security`, `qa`, `test_delta`, and
  `documentation`
- Human review focus: durable short-lived membership is the minimum mechanism
  that survives late commits; assess the supported 1..100,000 range, five-slot
  actor bound, one-hour access expiry, conservative concurrent allocation
  refusal, generic cursor concealment, exact per-page authority, replay behavior
  and CSV header contract.

## Implementation plan

1. Add failing pure cursor/request/response and real PostgreSQL snapshot tests,
   including the A/B/L late-commit counterexample and valid unchanged-source
   control; keep the >1,000 traversal proof separate from the three-row race.
2. Add reserved migration 0040 and matching CON model/repository operations for
   bounded materialization, exact page lookup and bounded expiry pruning.
3. Replace the hard 1,001-row refusal flow with page selection in the canonical
   read service while retaining all exact owner projection guards.
4. Compose the secret and publish cursor/limit contracts through the existing
   routes/dependency, with JSON body and CSV header parity.
5. Run focused pure, AUTH, migration and isolated PostgreSQL export proofs;
   then run lint, type checks, boundary/Commitrail/markdown/stale-wording gates
   and full CI without skips or threshold changes.
6. Reconcile current main, update the affected current docs/roadmap claims, freeze
   a clean candidate, and run exact-head architecture, security, QA, test-delta
   and documentation reviews before PR readiness.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current hard bound and transaction/owner invariants | Inspect canonical records API, repository, service, dependency, routes and existing export tests at `82a46ff3c5f21e3cdf762cf505d61d84531a7c80` | Confirmed | Implementation and runtime proof pending |
| Timestamp/UUID keyset cannot freeze membership | Trace A/B committed, L staged, page-one AUTH snapshot fixed, then L committed before owner selection | Discriminating counterexample established in plan review; regression test pending | Exact test fixture execution pending |
| Migration allocation | Lead reserved `0040_contribution_export_snapshots` after `0039_false_guide_activation` | Confirmed | Migration implementation and parity proof pending |
| Cursor and snapshot plan | Required architecture/security plan review | Pending | No application code starts before review |

## Review findings

Plan review at `5c4c50af69b7caafb562e94e26591f3e1943419f` blocked the
behind-boundary concurrency example and the unsupported assumption that these
routes already consumed authorization-read rate control. This revision uses the
discriminating A/B/L interleaving, adds the existing rate dependency plus a
database-enforced five-slot snapshot bound, clarifies the supported
1..100,000/full-refusal contract, distinguishes access expiry from opportunistic
physical deletion, and requires database rejection of snapshot updates.

Replay review found that a locked-but-unchanged actor row does not refresh a
waiting repeatable-read transaction's snapshot, so it cannot serialize a
count-and-insert quota. It also found that the human-read wrapper would suppress
existing canonical service DENY evidence. The repaired design uses a database
unique five-slot allocation fence and the rate-control-only dependency; no
actor business row changes and continuations allocate no slot.

## Reconciliation

- Current-source reconciliation: branch and worktree start at clean main
  `82a46ff3c5f21e3cdf762cf505d61d84531a7c80`; PILOT-10A REST/CSV and CLI24 are
  delivered, while CLI continuation belongs to separate issue #499 ownership.
- Next usable boundary: CLI cursor traversal can consume the merged backend
  contract in its separately owned change.
- Remaining risks: exact operational cost of 100,000-ID materialization and
  expiry pruning must be measured on PostgreSQL; no deployed-service claim.
