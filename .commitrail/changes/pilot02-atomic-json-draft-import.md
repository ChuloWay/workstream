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

## Baseline before this chunk

The implementation incorporates merged source prerequisite PR520 on main
`d3c50e1500beffea684fe881cd0a2b3431e6ccb9`. Its parser in `tasks/api/task_import.py`
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

- TASK: `api/task_import.py`, `api/transition_audit.py`, a cohesive `task_import_batches.py`,
  `authorized_commands.py`, `command_replay.py`, `models.py`, `schemas.py`,
  `repository.py` and `router.py`: typed import/status contracts, immutable batch
  receipt and row membership, server provenance and reuse of canonical creation.
- Coordinated shared extraction: `task_import_membership.py` and its typed
  `api/task_import_membership.py` are the single native original-response/member
  validator used by import/status and the separate bulk owner. SCREEN/RELEASE
  prepare/authorize/stage phases preserve the existing single-Task wrapper;
  CREATE and source preparation remain unchanged. Retain the native participant
  test in `tests/authorization/task_authority/test_management_participants.py`
  and its exact shared-lane/owner inventory.
- ART: `task_import_sources.py` implements TASK’s bounded source-consumer
  preparation/binding port over the existing verified source. ART already
  depends on TASK’s canonical parser; the consumer contract remains in TASK
  `api/task_import.py` to preserve the acyclic owner graph. Existing ART public
  source/AUTH contracts remain intact. No second provider path, storage lifecycle
  or inspector.
- Composition: existing `adapters/tasks/__init__.py`,
  `adapters/artifacts/__init__.py`, `adapters/auth/__init__.py` and
  `api/deps/authorization.py`: explicit owner ports and one transaction root.
- AUTH: exact batch import/status resource facts, preparation and closed
  action/permission/resource classifications in the existing TASK authority
  owner; reuse covered Project Manager grant evaluation and canonical denials.
- Focused TASK/ART/AUTH public-contract and native PostgreSQL/MinIO tests;
  `tests/test_task_import_sources.py` explicitly invokes the existing canonical
  ART startup namespace owner omitted by ASGITransport, before scripted guide
  prerequisites reuse the actual configured `primary` singleton;
  affected ownership/lane/inventory expectations and the selected MCP
  `authorization_context_get` snapshot for additive ActionId parity; current TASK/ART/AUTH specs,
  README and roadmap claims for this chunk only.
- AUDIT: the existing closed TaskCreated payload source-type classification in
  `audit/schemas.py`; preserve every existing type and canonical event owner.
- One coordinated successor migration and its graph/reset/fingerprint consumers,
  authored solely by the delegated migration owner after final schema handoff.
  The delegated owner authored `0034_task_import_batches` after merged `0033`;
  this worktree consumes that handoff without authoring DDL.

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
   server provenance. First import verifies actual provider bytes and parses
   them before the TASK write root. Committed exact-file replay instead recovers
   immutable IDs/facts from verified native original-source/receipt ancestry,
   with fresh batch/source authority and no provider read or reinterpretation.
   A different selected source needs its own actual verified receipt and the same
   exact original byte identity/count; a client-claimed digest is insufficient.
   Typed prepared facts bind source/project, exact SHA/count and actual
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
   relationship. Newly imported rows may expose the native batch UUID spelling
   through that string metadata field. Batch APIs select the new UUID owner,
   never arbitrary metadata; a manually supplied spelling creates no membership.
   Existing management/contributor projection and concealment stay unchanged.
   A duplicate project/external-ID preflight must stop with a diagnostic, without
   deleting or rewriting retained Tasks. Affected review freezes this mapping,
   exact replay AUTH facts and lock order before application coding.

### Reviewed schema and replay handoff

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
  The reviewed handoff must name the original source ID/operation identity,
  put-attempt ID, artifact content/replica IDs, verification job ID/generation
  and append-only verification receipt with its observed SHA/count. Exactly one
  existing operation acknowledgement or confirmed observation receipt must bind
  that same attempt and stored object ancestry. Reuse ART's existing native
  admission/receipt custody pattern; do not copy it into TASK or accept a DTO as
  proof. Initial import still uses the existing actual verified-byte read.
  Committed recovery validates retained immutable ancestry through an ART-owned
  participant and must not depend on the source read helper's current replica
  availability/integrity flags, active namespace or provider access. Native
  substitutions must fail without treating changed operational health as a new
  import or reinterpreting original rows.
  Direct SQL must reject foreign ancestry, partial closure and changed tuples.
  Native FK representations follow each existing owner, including string-mapped
  actor/audit UUIDs. The sole migration author receives the reviewed field/lock
  contract against then-current main before allocating a linear successor.

### Public and row-mapping contract

- POST `/projects/{project_id}/task-import-batches` accepts a closed
  `{source_id: UUID}` body and the shared UUID idempotency header. Its import
  action is `project.task.import`; proposed native resource facts use the
  bounded `task_import_batch` classification with project/source identity.
- GET `/projects/{project_id}/task-import-batches/{batch_id}` uses
  `project.task.import_batch.read`, returns only native membership, and separates
  immutable original creation facts from current Task states. All responses are
  bounded by the retained maximum 500 rows and keep document row order.
- The validated source's instruction fields map directly to canonical TaskCreate
  fields. Server metadata stamps additive source type `json_import`,
  `source_ref=task-import-source:<native source UUID>`, the actual verified
  `source_payload_hash`, and native batch UUID spelling in `import_batch_id`.
  Select exactly `json_import` in the server-only ImportedTaskCreate subtype,
  TaskTransitionFacts and the closed TaskCreated payload. Public manual-create
  TaskCreate keeps its existing three source types; callers cannot select the
  server-only import value through that route. The sole-author successor updates the current
  lifecycle SQL custody validator to admit that same exact token; historical
  baseline files stay unchanged. Normal manual/markdown/CSV entries remain.
  Caller input cannot choose or relabel these atomic-import server stamps.
  These labels add no authority; a manually stamped matching label remains
  outside native membership. The server does not infer deadline, assignment,
  guide locks, contribution terms or release state.
- Parser/mapping identity captures this exact field mapping and the published
  `workstream.task_import.v1` document version. Source metadata labels are retained
  as display values, never used as replay, project or authorization selectors.
  Actual provider bytes are parsed only on first import; stored creation facts
  and verified native receipts govern committed replay.

### Concrete owner and schema preparation for review

The implemented application boundary separates canonical Task creation into
three caller-root phases: prepare all retry/Task identities, consume the same
exact CREATE authority facts, then stage the existing Task/create event/receipt.
Normal public create remains the root-owning wrapper over those phases, with
its current advanced-state replay rejection unchanged. Batch replay recovers
its immutable creation responses and never routes through single-Task recovery.
No public route or per-row command transaction is invoked from the batch owner.

The proposed native tables are `task_import_batches`,
`task_import_batch_members` and `task_import_batch_command_receipts`:

- Batch reservation has UUIDv7 ID, project UUID, original command receipt UUID
  (deferred circular closure), original source UUID and its
  operation identity, exact source SHA/count, document schema and parser/mapping
  identity, row count, retained optional metadata label, original actor/link, current batch creation decision and
  original immutable ordered result. Project/SHA/count identifies one original
  batch. A reservation may be incomplete only inside its caller root; a deferred
  closure check rejects any committed pending header, missing or extra member,
  incorrect row count or incomplete ordered result.
- Native ART ancestry stores source/attempt/content/replica IDs, verification
  job/generation/receipt and exactly one operation/observation acknowledgement.
  FKs plus owner validation bind each tuple to the same project/source bytes;
  mutable replica health is not an original creation fact.
- Member has batch/project/Task IDs, bounded original row index, exact external
  ID, normalized row digest, server-generated CREATE key, original Task command
  receipt/decision IDs and closed original Task creation response. Task/project
  and batch/project composite FKs close custody; unique Task membership,
  batch/index and project/external-ID identities reject substitutions. Existing
  arbitrary `import_batch_id` metadata never supplies these relationships.
- Batch command receipt has UUIDv7 ID, current actor/link, closed import action, UUID key,
  exact request digest over project/selected-source IDs, selected verified
  ancestry, original batch ID and closed immutable ordered result. Actor/action/
  key is unique. A changed selector conflicts after fresh authority; new-key
  exact-file recovery creates only the current retry receipt/evidence.

String-mapped owner UUID FKs use `Uuid(as_uuid=False)`; native UUID-typed receipt
IDs keep their existing representation. Reservation actor/project/source/Task
FK checks are deferred where they would otherwise acquire implicit locks before
explicit TASK/ART/AUTH preparation. SOURCE KEY SHARE is acquired explicitly
before AUTH and retained through commit. All three tables reject UPDATE/DELETE after committed
closure and reject statement-level TRUNCATE. Only the exact pending-to-committed
header/receipt completion may change staged fields; immutable identity and
ancestry never change. Members are append-only and committed headers cannot be
reopened or deleted. Native reset restores these guards through the canonical
owned reset helper, without leaving them disabled for product writes. The sole migration author reviews native
constraints, deferred closure and exact owner representations before DDL work;
the consumed sole-author `0034` installs the reviewed constraints and guards.

### Concrete non-DDL schema handoff

The ORM representations now declare these exact owner relationships for the
sole migration author’s affected review. The ORM does not install guards; the
consumed `0034` migration installs the matching native schema:

- `task_import_batches`: native string-mapped UUIDv7 `id`, project and original
  source UUIDs, unique original `creation_command_receipt_id`, exact SHA/count/
  JSON media, document/mapping versions, normalized-document `manifest_digest`,
  retained nullable `metadata_label`, row count, original actor/link, original
  batch ALLOW decision, pending/committed shape, original response and timestamps.
  Project/SHA/count and ID/project are unique. The original command receipt FK
  is deferred, closing the intentional header/receipt cycle at root commit.
- Both batch and retry receipt store native put-attempt/content/replica IDs,
  verification job/generation/receipt, original source operation identity and
  exactly one operation/observation acknowledgement UUID. Pending ancestry may
  be NULL only inside the creating root; committed generation is explicitly
  non-NULL and positive. Source/project/SHA/count/media uses the existing ART
  composite custody FK, deferred until commit. Every other ART UUID FK uses its
  owner’s string-mapped native UUID representation and is deferred.
- `task_import_batch_members`: native UUIDv7 ID, batch/project/Task UUIDs,
  original index/external ID/normalized row digest, server-generated CREATE key,
  original `TaskCommandReceipt` UUID (its existing Python UUID representation),
  actual CREATE decision UUID, exact original Task response and timestamp.
  Unique Task, batch/index, project/external-ID and CREATE receipt prevent
  duplicated or substituted membership; Task/project and batch/project FKs
  are deferred and bind actual native owners.
- `task_import_batch_command_receipts`: native UUIDv7 ID, current actor/link,
  exact action `project.task.import`, UUID key, immutable selector request digest,
  selected source/project/SHA/count/media and complete ART ancestry, original
  batch ID, this invocation’s batch ALLOW decision, pending/committed result and
  timestamps. Actor/action/key is unique; batch/project and actor/link custody
  is deferred. New-key exact-file recovery creates only this receipt and fresh
  authority evidence, with the original header/members/result unchanged.
- The header’s complete normalized-document digest is reconstructible from its
  retained metadata label and ordered original Task instruction fields. It must
  equal the original parsed document; native closure must also prove the exact
  member count/indexes, original CREATE receipt/decision/action/actor/key/result,
  truthful `json_import`/source-ref/hash/batch metadata and all ART ancestry.
  Retry closure binds its fresh actor/link/decision and selected native source
  while returning the original immutable ordered result. A pending header or
  receipt cannot survive commit. All three tables reject DELETE/TRUNCATE and
  committed UPDATE; only exact staged completion is admitted.
- Native TASK changes remain the approved global case-sensitive project/non-NULL
  external-ID uniqueness with retained duplicate diagnostic preflight, difficulty
  width 80 preserving values, and additive current lifecycle `json_import`
  evidence. Current sensitive-audit constraints/guards must admit only the exact
  batch resource/actions. Historical baseline SQL remains unchanged. Canonical
  reset and graph/fingerprint/UUID inventories must retain every merged owner.

Reservation order is retry namespace, exact-file header, all canonical Task
CREATE reservations, explicit sorted SOURCE KEY SHARE, then fresh batch/source/
row AUTH and sorted external-ID writes. New batch FKs are deferred to avoid
implicit actor/source locks before this preparation. A separate provider-free
source read preflight authorizes before preparation outcomes are observable;
it commits no Task or batch effect. Each creation preparation is bound to its
original active SQLAlchemy root, preventing reuse after rollback/commit. The
sole author allocates a successor only after the lead names the actual merged
predecessor. Source `0031`, remediation `0032` and contribution reads `0033` are
merged at main `d47ee1e9917689b94fd9439c09dffaf88c6d3ec1`. The lead delegated
atomic successor `0034` to that sole author; this source worktree authors no DDL.

### Scope decisions and transaction preparation

The lead confirmed the following issue489 boundaries during preparation:

- Preserve all retained/manual `import_batch_id` strings. New imports may stamp
  their native batch UUID spelling into metadata; native immutable membership
  alone selects and authorizes the batch. Add a public control showing that a
  manually supplied matching string never appears in the batch status response.
- Exact project/SHA/byte-count file replay returns original IDs and creation
  facts after fresh batch/source Project Manager authority, even if Tasks have
  advanced. Reused actor/action/key with a changed source selector conflicts;
  a new key for the same exact file recovers the original batch. Actual verified
  source ancestry and parser/schema identity are bound, not a client digest alone.
- Case-sensitive project/external-ID uniqueness covers every non-NULL Task
  external ID, including normal create. Native preflight reports retained
  duplicates without changing their data. NULL remains available for normal
  Tasks without an external ID; arbitrary batch-label metadata gains no authority.

The existing Task composite `(id, project_id)` uniqueness can bind native row
membership without rewriting Task IDs or their string-mapped UUID model type.
The new membership must bind the original external ID, row index, normalized
row digest, original CREATE decision and immutable creation response separately
from mutable current Task status. A batch closure invariant rejects committed
success with a missing, foreign or duplicated row. No committed pending batch
or partially created row set is an accepted intermediate product state.

The creation refactor stays in the existing TASK owner: extract the current
create operation into one explicitly caller-owned participant, with the current
single-create public method remaining its transaction-owning wrapper. Batch
imports compose that participant; they do not invoke the public command in a
loop. Reserve all needed per-row replay identities before current AUTH locks,
then retain each row's real CREATE decision and `TaskCreated` evidence. Successful
batch closure and all row effects use one root; denial restaging follows the
specific AUTH instance that captured the original decision. Late-row failure
must remove every earlier successful creation effect in that root.

The lead approved common AUTH-before-uniqueness ordering with sorted writes;
no additional global advisory fence or custody table is introduced. The exact
owner preparation and implicit-FK schedule still require affected schema review
and native discriminating proofs before any concurrency PASS:

1. For first import, finish bounded ART provider verification and JSON parsing
   before the TASK write root. Source read evidence belongs to that earlier
   operation; no provider stream, scratch cleanup or I/O occurs while TASK
   write locks wait. For committed exact-file replay, use stored immutable
   batch/member results and actual native verified-source/receipt ancestry.
   Do not depend on provider availability or parse old bytes again. If the
   requested selector differs, validate its own completed verified receipt and
   exact original SHA/count before recovering the original batch.
2. Within the root, reserve the batch/file retry identity and every per-row TASK
   retry identity. Acquire existing Task/member custody needed by replay in
   deterministic order before the first AUTH lock. Proposed new batch/row tuples
   must not introduce foreign owner locks through premature FK writes.
   The existing TaskCommandReceipt defers both actor and Task FKs until commit;
   new pre-AUTH reservation rows must follow that owner pattern for actor,
   project, source and not-yet-inserted Task references. An immediate actor FK
   would let two same-actor imports retain KEY SHARE and deadlock while upgrading
   to AUTH's actor FOR UPDATE. An immediate source FK before remaining TASK
   reservations would silently invert TASK-before-ART custody. Native controls
   must distinguish both implicit-FK hazards without weakening final custody.
3. Validate actual ART source/verification custody through its typed participant
   after TASK custody and before fresh AUTH consumption. Read immutable tuples
   with the weakest required lock; do not lock a mutable put attempt merely to
   trust an application DTO. The source row is acquired FOR KEY SHARE here and
   retained through commit: its existing upload/replay operation uses FOR UPDATE,
   so postponing source FK custody until after AUTH could invert SOURCE/AUTH.
   This compatible immutable-parent lock also satisfies deferred final custody
   without reacquiring a conflicting source lock after actor authority.
   Preserve existing TASK-before-CHECKERS/ART order.
4. Consume fresh current batch/source authority and exact per-row CREATE
   authority through the shared TASK owner. After AUTH, insert external-ID-bearing
   Tasks in deterministic project/UTF-8 external-ID order. Retain document row
   indexes and immutable responses independently from insertion order. Stage
   membership and evidence, close the batch and flush within the caller root.
   No per-row TASK reservation or additional ART custody acquisition follows AUTH.

Normal create already consumes fresh AUTH before inserting its Task. An import
that wrote the unique external key before AUTH could hold that key while a
normal create held the same actor's AUTH lock: the normal create would wait on
uniqueness while the import waited on AUTH. Shared AUTH-before-write ordering
prevents that inversion. Distinct actors retain independent AUTH custody;
deterministic multi-row writes prevent crossed-key index waits. Native controls
must observe intermediate waits for same-actor create/import and distinct-actor
imports whose documents list overlapping external IDs in reverse order, alongside
revocation and late-failure rollback. Native uniqueness also protects direct SQL;
AUTH custody and file replay do not depend on an invented global creation fence.

Field mapping has one confirmed native-parity decision:
`TaskImportRow.difficulty` publishes an 80-character limit, whereas the baseline
`WorkstreamTask.difficulty` column was `varchar(50)` and `TaskCreate` has no length
validator. A valid retained source must not fail as an unexplained late database
error. The lead confirmed expanding that TASK display column to 80 in the
sole-author successor migration, preserving existing values and the published
source shape. Source intake is not narrowed and retained values are not rewritten.
Native 51/80-character controls and an indexed 81-character rejection must
discriminate the chosen boundary. No alteration is authored by this record.
The batch retains the actual `workstream.task_import.v1` document identity and
an explicit row-mapping/parser commitment, alongside verified bytes, so replay
never silently reinterprets retained rows under a later mapping.

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
- [ ] After successful import and Task advancement, provider unavailability
  cannot prevent same-key or new-key exact-file recovery of original IDs/facts;
  replay performs zero provider reads and emits no additional Task creation.
  Revoked current authority still denies that recovery. A different verified
  source with identical actual SHA/count recovers under a new key; a declaration
  with only the claimed digest, foreign/missing receipt or different bytes never
  recovers. Changing the selected source under the original key conflicts even
  when both verified sources contain identical bytes.
- [ ] Native PostgreSQL proves identical concurrent import recovery, overlapping
  external-ID conflicts, deterministic intermediate lock waits and complete
  rollback after an injected late-row/audit/binding failure.
- [ ] Direct SQL rejects partial batch closure, foreign source/verification/Task
  membership, changed original receipts and NULL/changed custody. For each of
  batch/member/receipt tables, native direct-SQL UPDATE, DELETE and TRUNCATE
  negatives retain all original facts. TaskCreated evidence uses the exact
  `json_import` token and server provenance; malformed/caller-relabelled stamps
  cannot produce a committed batch. Upgrade/reset
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
| Canonical creation participant | Exact `59d47a6c` isolated native execution of five retained CREATE, denial, rollback and receipt controls | 5 passed in 69.02 seconds; schema `0031_task_import_source`; owned database/role/MinIO cleanup complete | Proves preservation of normal creation; no atomic batch success claim |
| Source consumer and current CREATE participants | Exact `37d8705d` isolated execution of actual immutable-binding substitution/provider-health, public source, canonical denial, CREATE rollback and receipt controls | 10 passed in 120.95 seconds; runner exit 0, schema `0031_task_import_source`; owned database/role/MinIO cleanup complete | Raw `/tmp/pilot02-atomic-37d-source-create-corrected.log` and `.json`; validates existing owner integration, not installed batch schema |
| Shared SCREEN/RELEASE participant and membership extraction | Inspected sibling exact `4400568a` native replay; seven source/test files integrated as `96b1fb820` without its separate CLI record | 5 passed in 225.05 seconds; runner exit 0, schema `0031_task_import_source`; database/role cleanup complete | Raw `/tmp/pilot02-bulk-4400568-native.log` and `.json`; historical exact extraction proof, not a new batch-schema or public bulk success claim |
| Current owners and concrete gap | Inspect source port/parser, TASK create/replay/models and Issue 489 | Canonical caller-root phases, closed batch DTOs, ART binding and batch/root/AUTH composition are implemented; sole-author `0034` is consumed | Bulk SCREEN/RELEASE and CLI remain separate; hosted complete-execution evidence remains required |
| Current-main owner reconciliation | Source-equivalent `13c031333` focused catalogue/import contracts and protected API inventory | 50 passed in 2.09 seconds; one API inventory case passed in 16.01 seconds after its exact two import routes were registered; retained route hashes unchanged | Module boundary, Ruff, Commitrail and Markdown link checks pass; partition has 475 unique exact-union targets. Live OpenAPI comparison and tamper hash pass for all nine selected MCP fragments, plus the transitive-reference control. These pure/contract checks do not prove installed batch schema or public native import success |
| First installed-schema acceptance diagnostic | Exact combined `28e72311f` source plus sole-author `0034_task_import_batches`; isolated PostgreSQL 16/MinIO runner | First actual 200-row import failed in 61.03 seconds with safe 503; runner exit 1 and complete database/role/MinIO cleanup | PostgreSQL records an ambiguous `project_id` parameter in the binding validator at COMMIT. The migration owner repairs DDL; no native success is claimed. Retained public absent/null-label controls bind the optional label to JSON null rather than SQL NULL. The retained advancement fixture supplies the required canonical nonblank RELEASE reason before the next execution |
| Public import and atomic effects | Exact clean `09570d3a956a0c604b76c04037027c1dd8fd5c0f` / tree `32a2d1708e17c4108ecf6f776766ac606379d858`; isolated runner `pytest -x -vv tests/tasks/test_task_import_batches.py`, actual PostgreSQL 16 and MinIO | 26 passed in 686.84 seconds; runner exit 0; installed `0034_task_import_batches`; database/role and MinIO bucket/prefix cleanup complete | Raw `/tmp/pilot02-atomic-screenable-native26.log` and `.json`. Real 200-Task closure, both label forms, advanced/provider-independent same/new-key recovery, verified alternative-source recovery, revoked authority, late rollback, intermediate lock waits, foreign/partial closure rejection and all three tables’ UPDATE/DELETE/TRUNCATE guards. No bulk or CLI journey claim |
| Complete integration | Required local guards, independent SQL review, complete hosted lanes and canonical aggregate | Native public batch/SQL guards pass at `09570d3a`; complete hosted evidence is not yet produced for this chunk | Exact final frozen candidate, actual tested merge tree and complete execution/cleanup remain required |

## Review findings

The installed-schema replay at exact `e56fd60a` passed the real 200-row closure
and both optional-label controls, then stopped before the advancement import:
the committed guide fixture had claimed ART's live `primary` namespace with
fake local-provider facts. A diagnostic observed the exact
`ArtifactStorageNamespaceError`; database, role and MinIO namespace cleanup
completed. Two attempted dedicated fixture IDs were rejected by the native
varchar(20) and singleton-ID constraints at `0015caa7` and `1f904cc7`; both runs
completed cleanup and neither is passing proof. The shared guide fixture is
restored unchanged. The actual MinIO source fixture now invokes canonical ART
startup namespace validation before scripted guide prerequisites reuse its exact
configured singleton, and closes its bootstrap. Guide object bytes remain
scripted; actual source bytes still use real MinIO PUT and verification. No
production validation or migration is changed; the failed public case and full
26-case replay subsequently passed at `09570d3a`; full hosted evidence remains required.

At exact `99b4d170`, the integrated replay again passed the 200-row and two label
controls. The startup repair also allowed source upload and the advancement
import to succeed; canonical SCREEN then correctly rejected its minimal input
for missing acceptance criteria. The advancement fixture now includes legitimate
criteria in the original verified JSON, rather than changing a Task or weakening
SCREEN. That run ended 3 passed / 1 failed in 180.57 seconds with complete owned
cleanup; the corrected exact `09570d3a` complete 26-case execution then passed.

Independent schema/lock handoff review at exact `37d8705d` found no actionable
architecture/reuse/security issue in the non-DDL models, replay and preparation
graph. This qualified review does not prove native guards or public batch
success; those require the integrated migration and real end-to-end execution.
Scope preparation identifies the existing
per-command transaction and unbound string provenance as explicit handoff issues.
Affected independent planning review found two concrete missing integration
requirements: the closed TaskCreated JSON source token and complete batch/header/
TRUNCATE immutability. This record now names all typed/audit/native token owners
and all-three-table UPDATE/DELETE/TRUNCATE controls. Those planning gaps are
closed by the consumed sole-author `0034` and the exact
`09570d3a` public/native proof. Independent source/fixture review at `09570d3a`
found no weakening: the actual configured namespace uses canonical startup,
scripted guide bytes remain qualified, and the advanced replay input satisfies
existing SCREEN/RELEASE requirements. That reviewer excludes its authored DDL;
the lead retains independent SQL and final full-evidence review.

## Reconciliation

- Current-source reconciliation: this preparation branch incorporates source
  prerequisite PR520 and merged main `e31e1777c47b794b1d4d8240192608e4fff4f536`,
  retaining its ten-lane CI, hidden materialization/completion/failure/feedback
  owners, contribution export and CLI approval/correction contracts. The additive
  AUTH union retains all 152 actions (116 active and 36 planned), all 78
  permissions, both contribution-read audit arms and the reviewed atomic import
  classifications. Shared metadata retains every incoming assignment and lane;
  the selected MCP context contract is recaptured from clean backend commit
  `13c0313334d20acbaecd6ea76c54b3573336a40d` after the owner union.
  Main guide-activation integration at `89c18c78` changes only incoming CLI/docs
  files; all backend source, tests and migration blobs are byte-identical to
  exact native-proven `09570d3a` (`git diff --exit-code 09570d3a -- backend`).
  The native proof remains attributed to `09570d3a`, not relabeled to the merge.
  The required structural guard then identified `_index_actions` at 101 lines
  after adding the two closed import actions. One adjacent Task action declaration
  line is consolidated, preserving its entire AST and returning the function
  to 100 lines; no debt entry, policy limit or authority assertion is relaxed.
  Canonical Task creation shares caller-root phases with its normal public
  wrapper, and public atomic import/status use the consumed sole-author `0034`.
  No deployed or main-delivered atomic import capability is claimed before merge.
- Next usable boundary: complete required local guards, independent SQL/final
  review and exact-head hosted CI for this atomic JSON-to-DRAFT slice. Native
  public acceptance is proven at `09570d3a`; integration includes sole-author
  `0034` after actual merged `0033`. Explicit batch screen/release and CLI
  project/source/batch commands with client CSV conversion are implemented on a
  separate coordinated lane; its public/native aggregate journey remains pending.
- Remaining risks: source prerequisite and current required CI/actual external
  review remain separate; no deployed import capability or whole Issue 489 claim.

## Current-main takeover reconciliation

Reconcile this atomic import slice with merged main `6d64a6353`: preserve the
selected external-checker flow, current authority inventory and retained data.
A normal merge has two historical merge bases and can silently remove the
atomic owner; apply the reviewed atomic-only delta from `e31e1777` instead.
Allowed reconciliation files are the existing scoped paths above, additive
action/route/owner metadata, canonical MCP action snapshot, current documentation
and focused tests. The sole migration owner moves the unmerged atomic migration
after `0036_selected_checker_flow`, including graph/reset/fingerprint consumers.
No old checker catalogue, predecessor schema-adapting writer or compatibility
path may return. Preserve all existing assertions and limits. Verify native
200-row atomic import, authority/replay, rollback, intermediate lock waits,
linear migration graph and current source retention before publication. Required
review tracks: architecture, security, QA/test delta and affected CI metadata.
Human review focuses on exact original source custody and caller-root atomicity.

### Migration-owner linearization

The migration-only reconciliation is limited to renaming the unmerged atomic
migration to `0037_task_import_batches`, setting its predecessor to merged
`0036_selected_checker_flow`, registering that single linear head in
`backend/alembic/env.py`, and updating the exact graph, reset/TRUNCATE ownership
and measured schema fingerprint consumers in `backend/tests/test_alembic.py` and
`backend/tests/conftest.py`. This block is the only additional record scope. The
SQL body remains byte-identical to the final `af82b1fe0` handoff apart from the
revision identity and predecessor, including the `d0020ffd8` once-per-root
custody validation. Historical evidence above remains correctly attributed to
the then-installed `0034_task_import_batches`; it is not relabeled as current
head proof.

The first controlled setup on reconciled head `728148626` installed `0037` and
refused the retained current-main fingerprint as intended, measuring the exact
combined PostgreSQL 16 schema digest
`5abd992592eea9b00ce1f2b4330ff0e121577ff7c8ab34fc76fa9e71a8d336d5`.
The runner exited at that deliberate setup boundary with database, role, bucket
and prefix cleanup all true; raw evidence is in
`/tmp/pilot02-takeover-first-native.log` and its adjacent JSON metadata. This
record binds that measured value without claiming an affected-test pass; the
schema/graph and atomic public cases still require their frozen-head replay. No
application, model, AUTH, workflow, cap, predecessor fixture or compatibility
code changes are allowed in this migration reconciliation. The separate bulk
transition migration follows as `0038` only after this atomic boundary is
frozen.

### Response timestamp custody finding

Independent source review found the pending-to-committed SQL closure did not
bind response `created_at` to the authoritative native batch timestamp. Extend
the existing counterfeit test by shifting only the staged response timestamp;
reproduce before adding the SQL equality and the owner replay mirror. Preserve
all prior native checks, add one real foreign-project public selector control,
and execute existing invalid-upload controls on the reconciled source. The
first full native module at `057a2a581` timed out after 900s and is not a pass;
all owned resources cleaned up. Its next focused metadata membership control
passed (1 case, 136.27s), including actual call33.56s/setup13.34s, with no observed
lock hang. Use targeted timed runs and complete hosted evidence for closure.
