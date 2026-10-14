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
- `backend/alembic/versions/0040_contribution_export_snapshots.py`, the Alembic
  current-head guard and graph test, and the CON
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
  snapshot migration test, the shared test-database reset/fingerprint metadata,
  exact test-lane inventory updates required for any new test module, and only
  the behavior-ownership metadata required by changed eligible source paths.
- `cli/tests/integration/test_contribution_evidence_public_api.py` only to
  activate the existing pagination-secret fixture for the real API contract;
  no CLI implementation or consumer behavior changes.
- Affected current contract text in `README.md`,
  `cli/README.md`,
  `docs/spec_contribution_compensation.md`,
  `docs/spec_authorization_service.md`, and `docs/roadmap_status.md`.

### Not allowed

- CLI production or consumer changes; issue #499 has separate ownership.
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
| Migration allocation | Lead reserved migration number 0040 after `0039_false_guide_activation`; the revision is the 32-character-safe `0040_contribution_export_page` | Confirmed | Migration implementation and parity proof pending |
| Cursor and snapshot plan | Required architecture/security plan review at `017729ca4ea319d20f1d8fec02fa9660862cbdf1` | Passed with low residual risks | Runtime and exact-candidate review remain |
| Pure page/cursor behavior | `cd backend && .venv/bin/python -m pytest -q tests/contributions/test_export_projection.py` | 20 passed | PostgreSQL owner/API paths remain |
| Lint, import syntax and documentation coverage | Focused Ruff over changed Python and CLI integration source, `compileall`, and unchanged `docstr-coverage --config .docstr.yaml` | Passed; documentation coverage is 80.2% | Full repository checks remain |
| Migration graph and schema fingerprint | Isolated PostgreSQL migration through `0040_contribution_export_page`; public schema fingerprint `a14b2b41d5c2e3a450105ad8283720490116545c376404c6507c9054b9986bac` | Passed; owned temporary database cleaned | Migration constraint/index tests remain |
| Focused PostgreSQL owner/API proof | 39 selected export, migration and graph tests split only after two host-pressure timeouts | First 24 passed before the second timeout; its 25th node later passed alone and the already completed 26th passed; the remaining selection produced 12 passes and one fixture-only failure, then the repaired migration node passed alone in 143.69 seconds. The earlier broad runs remain incomplete and are not reported as one clean passing batch. | Hosted complete lane execution remains required; one earlier authorization node failure had no captured traceback and did not reproduce alone, so its cause is unknown |
| Migration constraints and model parity | Exact real-PostgreSQL `test_snapshot_storage_bounds_model_parity_and_immutable_membership` after atomically seeding the baseline-required actor/identity pair | 1 passed in 143.69 seconds; database and role cleanup complete | Hosted schema lane remains |
| Fixed 1,001-member storage/traversal and contended pruning | Isolated PostgreSQL execution of `test_real_postgres_retains_and_slices_1001_members_across_sessions` and `test_locked_expired_pruning_skips_contention_and_preserves_live_cursor` | 2 passed in 278.90 seconds through migration `0040_contribution_export_page`; database, role and container cleanup complete. The run used committed base `11db9d21dfe4ef119d9d7d1801c75921fd9708e1` plus the exact uncommitted test file later frozen in this change, SHA-256 `d54ae3a16b4489dd04e4041e554945631ffebe1be860a8c0a533cb0fb96c4b45`. | This is dirty-tree execution with content custody, not an exact committed-head run; hosted complete lane execution remains required |
| Hosted failure diagnosis at draft head `84542bf37` | Inspect GitHub Actions run `38528310566` job steps and bounded logs | All ten semantic lanes stopped at the unchanged 80% docstring gate because the new pagination modules lowered total coverage to 79.9%; the added function documentation restores 80.2%. The CLI job's first evidence read returned 503 because its separate pytest root had not activated the required existing cursor-secret fixture. | Fresh hosted run required after the repaired head is pushed |
| Focused real CLI/API contract after secret-fixture repair | Exact socket/PostgreSQL contribution evidence node with the independently built CLI | The backend now returns its successful JSON page, and the current CLI fails it as `invalid_api_response` because strict decoding does not admit `next_cursor`; database and role cleanup complete | Issue #499 must consume continuation or fail explicitly before this backend contract can ship or hosted CLI CI can pass |
| CLI consumer continuation after main `24119122b` | Inspect `cli/internal/api/contribution_evidence.go` and `cli/internal/command/contribution_evidence.go` | JSON strict decoding has no `next_cursor`; both JSON and CSV perform one request, and CSV ignores `X-Workstream-Next-Cursor`. Issue #499 remains open and no separate continuation PR is open; its current issue body covers submission/status rather than this export contract. | The continuation correction still needs explicit CLI ownership before coordinated shipment; this change does not alter CLI production behavior |
| Final hosted backend and CLI execution at `90d36d102` | GitHub Actions run `38551898443`, including one failed-job retry | The repaired schema lane and eight other backend lanes passed. `project_lifecycle_a` reached the 1,200-second lane limit twice with `interrupted=true` and no failing node or traceback; the unchanged lane passed at prior head `00771a387`. CLI passed 9 tests and failed only the public contribution-evidence node with `invalid_api_response`. | Aggregate remains failed by the incomplete project lane and the known CLI continuation incompatibility; no timeout increase or skipped test is introduced |

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

Exact-candidate QA/test-delta review identified missing real-PostgreSQL coverage
for 1,001-member storage/continuation and contended bounded pruning. The two
focused regressions above now cover those boundaries. Its high-severity CLI
integration finding remains valid and externally owned by issue #499; this
backend change stays blocked from coordinated shipment until that consumer
accepts and follows the JSON and CSV continuation contracts.

## Reconciliation

- Current-source reconciliation: the implementation is reconciled with main
  `24119122bf5b4284878996b7c655072e666d96e1`, including CLI25 submission and
  the merged MCP runtime dependency repair. Neither merge changed the
  contribution evidence consumer; continuation remains an unresolved CLI
  handoff associated with open issue #499, whose present scope does not itself
  enumerate the export cursor/header contract.
- Next usable boundary: CLI cursor traversal can consume the merged backend
  contract in its separately owned change.
- Remaining risks: exact operational cost of 100,000-ID materialization and
  expiry pruning must be measured on PostgreSQL; no deployed-service claim.
