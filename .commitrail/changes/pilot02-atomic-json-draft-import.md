# PILOT-02B — Import one verified JSON source into DRAFT Tasks atomically

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: A covered Project Manager imports one verified project-bound JSON source into one immutable batch and its DRAFT Tasks, with exact replay and complete rollback.

## Intent

Issue [489](https://github.com/Flow-Research/workstream/issues/489) requires a
real 200-row file to produce 200 DRAFT Tasks before separate screen and release.
PILOT-02A provides exact source custody but creates no Tasks. This chunk supplies
that missing JSON-to-DRAFT operation and a covered-manager batch-status read.
Issue #489 remains open after this chunk; batch transitions and CLI remain.

## Current behavior

The inspected integration is `7a3551e7caf2c07af51701db06d011207b44e106`,
based on main `a51cf06ccb5ab85f2c41528855f537d4362ec26b`. PR520 remains
the separate source prerequisite. Its parser in `tasks/api/task_import.py`
accepts one strict UTF-8 JSON document with 1..500 rows, required case-sensitive
external IDs, indexed duplicate errors and an 8 MiB ceiling. ART's
`api/task_import_source.py` and `task_import_sources.py` own project-bound
declaration, admission, fresh authority, verified reads and provider recovery.

`tasks/authorized_commands.py` owns canonical create/screen/release and their
per-task AUTH/audit; each public command opens its own root transaction.
`command_replay.py` reserves one Task's actor/action/key namespace and requires
fresh authority before recovery. Its receipt cannot represent a whole batch.
`WorkstreamTask` has source fields, but no batch record or project/external-ID
unique constraint. Its existing `import_batch_id` is nullable string metadata;
it is not an authoritative native-UUID batch relationship.

## Bounded change

### Allowed

- TASK: `api/task_import.py`, a cohesive `task_import_batches.py`,
  `authorized_commands.py`, `command_replay.py`, `models.py`, `schemas.py`,
  `repository.py` and `router.py`: typed import/status contracts, immutable batch
  receipt and row membership, server provenance and reuse of canonical creation.
- ART: `api/task_import_source.py` and `task_import_sources.py`: the smallest
  typed preparation/binding port over the existing verified source. No second
  provider path, storage lifecycle or inspector.
- Composition: existing `adapters/tasks/__init__.py`,
  `adapters/artifacts/__init__.py`, `adapters/auth/__init__.py` and
  `api/deps/authorization.py`: explicit owner ports and one transaction root.
- AUTH: exact batch import/status resource facts, preparation and closed
  action/permission/resource classifications in the existing TASK authority
  owner; reuse covered Project Manager grant evaluation and canonical denials.
- Focused TASK/ART/AUTH public-contract and native PostgreSQL/MinIO tests;
  affected ownership/lane/inventory expectations; current TASK/ART/AUTH specs,
  README and roadmap claims for this chunk only.
- One coordinated successor migration and its graph/reset/fingerprint consumers,
  authored solely by the delegated migration owner after final schema handoff.
  This planning work authors no migration and reserves no ordinal in advance.

### Not allowed

- PR520 source branch edits, batch screen/release, Task release/assignment,
  contributor task creation, CLI/frontend, CSV ingestion, external adapters or
  checker/runtime changes; no dependency on PILOT-04 execution.
- Changes to the normal screen/release guide locks, policy validation,
  compensation selection, hidden completion/routing or false-guide readiness.
- Route-to-route calls, per-row commits/savepoint success, copied TASK transition
  rules, direct product filesystem/provider access or invented byte receipts.
- Retained-row deletion, automatic repair/backfill of conflicts, unrestricted
  AUTH strings, threshold/skip/runner weakening, deployment, merge or issue closure.

## Design and decisions

1. Public import selects a project and verified source with exactly one UUID
   idempotency key; input supplies no Task state, creator, locked lineage or
   server provenance. ART verifies and bounds bytes before the TASK write root.
   Its typed prepared facts bind source/project, exact SHA/count and actual
   verification ancestry. Inside the write root, the ART participant validates
   the immutable reference again without provider I/O or a separate commit.
2. TASK owns a UUIDv7 batch record, exact received-file commitment and ordered
   row-to-Task membership. Project plus received-file identity governs exact-file
   recovery; actor/action/key receipts distinguish retries from changed requests.
   TASK row IDs use `new_record_id()` and are recovered from stored facts.
   A source supplied by another covered manager conveys no inherited authority.
3. One root reserves the batch, acquires deterministic TASK/custody locks before
   AUTH, and composes flush-only canonical create participants. Every new row
   retains its own exact CREATE decision and normal `TaskCreated` audit. Batch,
   all DRAFT Tasks, source binding, related receipts and successful evidence
   commit together. Any row failure removes all these effects; canonical denied
   evidence is retained through the correct AUTH owner after rollback.
4. Enforce case-sensitive `(project_id, external_task_id)` uniqueness in
   PostgreSQL, including concurrent imports. Same external ID in another project
   is allowed; an existing conflicting ID rejects the complete new batch with
   indexed errors. Preserve exact source bytes rather than hashing reserialized
   rows as the file identity. Imported provenance is server-stamped JSON custody;
   a converted CSV is never described as original server-retained CSV.
5. Exact replay returns the original ordered Task IDs and immutable creation
   facts with fresh covered-manager authority and no additional creation effects.
   It cannot mutate Tasks that subsequently advanced. Existing single-Task
   command replay/state-conflict behavior remains unchanged. Status reads are
   project-scoped and conceal foreign or revoked access without source coordinates.
6. The inspected string `import_batch_id` is genuinely caller-supplied metadata:
   retained public fixtures use `private-import-batch` and `ready-private-import`,
   and the Go management contract accepts `batch`. It cannot be cast to an owned
   UUID reference. The proposed handoff preserves that metadata unchanged and
   gives the new ordered membership table the authoritative native batch/Task
   relationship. Batch APIs select the new UUID owner, never arbitrary metadata.
   Existing management/contributor projection and concealment stay unchanged.
   A duplicate project/external-ID preflight must stop with a diagnostic, without
   deleting or rewriting retained Tasks. Affected review freezes this mapping,
   exact replay AUTH facts and lock order before application coding.

### Proposed schema and replay handoff for affected review

- Batch: UUIDv7 ID, project UUID, original source UUID, exact SHA/count,
  verified ART ancestry, row count, original actor/link and immutable creation
  receipt/result. Unique received-file identity is project plus SHA/count.
- Ordered membership: native batch and Task UUIDs, project, zero-based row index,
  external ID, normalized row digest and exact CREATE decision. Composite custody
  binds each member to its batch/project and Task/project. Each Task has one
  import membership; batch row indexes and project/external IDs are unique.
- Retry receipt: actor/action/UUID key namespace, exact project/source selector
  request digest, original batch ID and immutable ordered result. A changed
  selector under the same key conflicts even when the alternative source has
  identical bytes. A new key for the same exact project/file recovers the
  original batch after current authority and actual original custody checks.
- Fresh replay authorization binds the current caller to the stored batch/source
  and manifest digest. It does not borrow the original actor, issue new CREATE
  effects or pretend an advanced Task is DRAFT. Status can show current row
  states separately from immutable creation facts. Existing single-Task command
  state-conflict semantics remain intact.
- The ART binding participant validates actual immutable source/verification
  rows in the caller's root; an application-created DTO supplies no authority.
  Direct SQL must reject foreign ancestry, partial closure and changed tuples.
  Native FK representations follow each existing owner, including string-mapped
  actor/audit UUIDs. The sole migration author receives the reviewed field/lock
  contract against then-current main before allocating a linear successor.

## Acceptance criteria

- [ ] One real 200-row verified JSON source creates exactly 200 DRAFT Tasks under
  one batch; every row has the correct source hash/reference, external ID, actor,
  per-task AUTH decision and creation event. No locked screen/release lineage,
  assignment or release effects are invented.
- [ ] Invalid or unverified input, one conflicting row, duplicate ID, foreign
  source/project, missing authority and 501 rows yield indexed closed errors and
  zero batch/Task creation effects. Existing separately committed source/read or
  canonical denial evidence is distinguished from successful TASK effects.
- [ ] Exact same-key and exact-file retries recover original IDs with fresh
  authority; changed bytes/key reuse conflicts; revoked replay fails. Source,
  actor, receipt and row-membership substitutions fail closed.
- [ ] Native PostgreSQL proves identical concurrent import recovery, overlapping
  external-ID conflicts, deterministic intermediate lock waits and complete
  rollback after an injected late-row/audit/binding failure.
- [ ] Direct SQL rejects partial batch closure, foreign source/verification/Task
  membership, changed original receipts and NULL/changed custody. Upgrade/reset
  preserves every retained main and source fact on the sole linear schema.

## Risk and review routing

- Risk class: `L0` (multi-owner authority, immutable custody and atomic creation).
- Required reviewers: architecture/reuse for owner composition and native parity;
  security for current actor/project/source/replay custody; QA/test delta for
  observable rollback and discriminating native controls. The lead owns common
  CI/collection/cleanup validation and independent SQL review.
- Human review focus: batch/file identity, retained provenance preflight, fresh
  replay authority, per-task evidence, root atomicity and the SOURCE/TASK/AUTH
  lock graph. Source storage is a prerequisite, not the import result.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current owners and concrete gap | Inspect source port/parser, TASK create/replay/models and Issue 489 | Scope preparation only; no product code or import operation implemented | Exact schema and replay facts require affected review |
| Public import and atomic effects | Planned isolated runner: `pytest -q tests/tasks/test_task_import_batches.py` with real PostgreSQL 16/MinIO | Not run; tests not authored | All positive/negative/concurrency cases above must pass |
| Schema, guards and complete integration | Sole-author native graph/reset/UUID proof, affected guards, complete hosted lanes and aggregate | Not run for this chunk | Exact frozen candidate, actual merge tree and cleanup required |

## Review findings

No implementation review is claimed. Scope preparation identifies the existing
per-command transaction and unbound string provenance as explicit handoff issues.

## Reconciliation

- Current-source reconciliation: source PR520 stays frozen at `7a3551e7`;
  this separate preparation branch includes main's delivered hidden B8 owners.
- Next usable boundary: explicit atomic batch screen/release, then the CLI's
  project/source/batch commands and client CSV conversion against public contracts.
- Remaining risks: source prerequisite and current required CI/actual external
  review remain separate; no deployed import capability or whole Issue 489 claim.
