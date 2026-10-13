# PILOT-02C — Atomic batch screening/release and explicit CLI intake

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: Covered Project Managers explicitly screen and release every immutable imported batch member atomically and use the public CLI for separate source/import/status/screen/release operations and local CSV conversion.

## Intent

Issue [489](https://github.com/Flow-Research/workstream/issues/489) requires
separate all-or-nothing screening and release after canonical JSON import.
PILOT-02A supplies ART source custody; PILOT-02B supplies immutable native batch
membership and canonical CREATE participation. Normal single-Task SCREEN/RELEASE
already own guide locks, validation, per-Task authority, audit and retry receipts.
Their current root transaction prevents composition across a complete batch.

## Bounded change

### Allowed

- Historical migration proofs retain main's literal predecessor fixtures.
  Superseded schema-adapting seed writers are removed by PILOT-04 and stay
  removed. Diagnose failures against the actual original schema and retained
  rows; do not add temporary model columns to an older migration test database.
- The existing receipt SQL negative in `tasks/test_command_replay.py` may use
  TRUNCATE CASCADE to reach its owner guard despite the new native FK, with
  retained receipt equality after every refused statement. The contribution
  audit migration test pins its exact 0033 upgrade, so its downgrade refusal
  exercises that migration rather than a later generic no-downgrade guard.
- `scripts/test_lightweight_agent_gates.py` validates the actual reusable CLI
  job block, its MinIO dependency and exact source-pinned artifact input.
  `backend/scripts/identifier_generation_classifications.json` receives only
  the exact bulk per-row idempotency-key transport-token classification; preserve
  the atomic owner's separate classification on reconciliation. No scanner,
  category, threshold, skip, deadline or required-result weakening. Lane
  rebalancing needs a separate exact lead-coordinated module/runtime handoff.

- New TASK batch-transition owner and typed API contracts under
  `backend/app/modules/tasks/task_batch_transitions.py` and
  `backend/app/modules/tasks/api/task_batch_transition.py`; native membership
  selection only. Extend exact existing SCREEN/RELEASE participants in
  `authorized_commands.py` through prepare/authorize/stage phases. Coordinate
  these regions with the atomic-import owner before edits.
- Aggregate custody is owned in `task_batch_transition/models.py`: exactly one
  actor/action/key aggregate and its complete native member links. Lead review
  approved compact ordered receipt projections and a scoped batch-write client
  deadline, to be selected after native 200/500 measurements. No global transport
  change or claimed measured ten-minute requirement is authorized.
- Explicit atomic-owner handoff permits the single native membership owner in
  `task_import_membership.py`, its small `api/task_import_membership.py` error/row
  facts, exact original-response wrapper replacement, and batch error import
  updates in TASK router/import tests. A tiny `_locked_task` extraction shares
  its unchanged AUTH prepare/consume/finally-close block through `_authorize_facts`.
  CREATE methods/dataclass and source ancestry preparation remain untouched.
- Sole schema-owner handoff authorizes only the two aggregate model imports in
  `backend/app/db/models.py`. The new model owner is relocated once to
  `task_batch_transition/models.py` so canonical registration uses the existing
  protected metadata-discovery exception, without an alias or new private debt.
  A fresh-process canonical-only metadata/FK compiler check belongs in the
  existing compact-contract test module. Migration, Alembic/env, fingerprints,
  reset lists and schema-owner inventory remain with the sole migration author.
- New route/dependency modules and append-only composition of the typed batch
  transition owner. Shared TASK `router.py`, `schemas.py`, model/receipt and AUTH
  regions require an explicit owner handoff before edits. Existing per-Task
  SCREEN/RELEASE actions and canonical denial handling remain mandatory.
- Atomic-owner-approved canonical custody hunks are the nullable
  `TaskCommandReceipt.batch_transition_receipt_id` column/closed action constraint,
  optional `command_replay.reserve` binding argument, and SCREEN/RELEASE
  preparation/digest validation only. CREATE and other retained command digests
  remain unchanged. New delivery is exactly `task_batch_transition_router.py`,
  `api/deps/task_batch_transitions.py`, one TASK-router include and one TASK-adapter
  factory. The new dependency composes inside the existing `get_task_commands`
  yielding lifecycle; it neither duplicates AUTH denial handling nor creates an
  alternate authority owner.
- New Go CLI `internal/taskimport/` conversion/validation, scoped
  `internal/api/task_import*.go`, `internal/command/task_batch*.go`, and one
  registration in `internal/command/command.go`; focused native Go/HTTP and
  real public backend journey tests. Reuse existing HTTP client and output/error
  conventions. Source admission, import, status, screen and release stay explicit.
  Import validates the original retained source and complete row custody. If an
  equivalent verified source selector recovers that original batch, it reads only
  the exact requested source's public status and requires verified SHA/byte-count
  equality. Any failed post-write comparison/read remains an unknown outcome;
  no retry, replacement response or arbitrary source lookup is permitted. Focused
  controlled HTTP and real socket tests cover recovery and changed-key refusal.
- Lead-approved exact `cli/internal/api/client.go` PUT additions: classify PUT
  alongside POST/PATCH at the three existing mutation checks and require the
  canonical error envelope for POST/PUT. Disable automatic body replay and retain
  uncertain-write reporting. Measured batch writes also permit one explicit
  `taskBatchHTTP` client cloned from the unchanged transport, with a three-minute
  timeout, and a narrow extraction of the existing bounded-response operation to
  accept that client. Only import/SCREEN/RELEASE use it. Status, source operations,
  redirects, proxies, automatic retries and default twelve-second requests stay
  under their existing contracts. Real delayed HTTP controls prove the scope.
- Exact CLI proof paths are new `cli/tests/integration/test_task_batch_csv.py`
  and `test_task_batch_sources_http.py`, plus
  `test_task_batch_commands_http.py`; the existing HTTP fixture receives one
  PUT handler delegating to its unchanged exact-body POST capture. No retained
  GET/PATCH/POST expectations or test guards are removed.
- Actual socket proof is `cli/tests/integration/test_task_batch_public_api.py`:
  reuse the canonical migrated database/source fixture with explicit asyncio
  registration, real app lifespan and a 200-row CSV→verified JSON source→DRAFT
  import→SCREEN→RELEASE journey. Use actual retained rows for assertions,
  unchanged-key replay and canonical grant revocation. Hidden active-guide
  prerequisites and the canonical development identity verifier are qualified;
  no route, authority or provider override is introduced. Its subprocess budget
  is scoped to the three-minute writes; the shared twenty-second HTTP fixture
  stays unchanged. Workflow registration is coordinated separately with the
  lead before final freeze; no native test is skipped or silently omitted.
- Exact workflow hunks are `.github/workflows/cli.yml` and the CLI caller in
  `.github/workflows/backend.yml`: require the existing source-pinned MinIO
  producer artifact through its job output, bind its SHA/attempt name, verify its
  checksum and start/clean up one actual provider. Add Go tests to existing
  verify/build commands. Partition the old mixed integration run into controlled
  task/local HTTP checks, guide HTTP checks and existing native public API callers,
  each with the unchanged
  240-second isolated-run cap. Select existing native `*_public_api.py` files
  automatically, excluding only the owned bulk file. Existing
  `test_public_self_service.py` and the owned bulk file each have a separate
  240-second isolated run. HTTP/local selection is
  the exact complementary file set: guide `test_guide*.py` files excluding native
  files, and remaining HTTP/local files. Refuse empty native or guide arrays.
  Every test stays selected once, the fifteen-minute job cap and aggregate
  required CLI result remain unchanged, and no skips or fallback providers are
  introduced. Preserve the separate PILOT-10 export-native partition at union.
  CI integrity review remains required before readiness.
- Native participant lifetime/composition proof is owned in
  `backend/tests/authorization/task_authority/test_management_participants.py`;
  it extends the existing management proof using actual PostgreSQL and AUTH.
- Closed response proof is `tests/tasks/test_task_batch_transition_contract.py`;
  actual public native journeys/rollback/revocation/wait proof is
  `tests/tasks/test_task_batch_transitions.py`. These two modules require exact
  TASK lane/inventory registration after coordinated atomic/current-main union.
- Exact metadata hunks are two TASK catalogue registrations and their unchanged
  exact-set assertion in `backend/tests/test_ci_lane_catalogue.py`, plus five
  explicit `PILOT_02C_BULK_TRANSITION_TARGETS` paths and additive partition
  regeneration. Preserve all atomic/source and ten-lane entries, retained
  assignments, protected-base custody and zero private-edge growth.
- Exact public API inventory hunk is the existing `batch_actions` block in
  `backend/tests/test_api_controls.py`: append SCREEN/RELEASE with canonical
  actions and change complete/protected route counts from 102/100 to 104/102.
  Preserve atomic POST/GET and both retained-route hashes unchanged. The real
  OpenAPI check at `932412232` failed on the missing two-route registration;
  this updates the closed expected inventory rather than weakening a gate.
- Current-main reconciliation preserves both the atomic import and merged P10
  AUTH arms/action registries. Update the exact closed catalogue count and its
  assertion to their 152-action union, preserving permissions and evaluators;
  reconcile only the selected MCP authorization-context enum digest/provenance.
  No bulk AUTH actions are introduced.
- Current TASK/AUTH/ART and CLI contracts, README, affected roadmap sections,
  this record, and exact coordinated owner/lane/selected-contract metadata.
- Required schema/receipt changes only through the sole migration author after
  the aggregate replay contract is reviewed and its exact DDL is handed off.

### Not allowed

No atomic-import/source owner rewrites, migration authorship or ordinal allocation,
arbitrary `Task.import_batch_id` membership, contributor creation, route calls,
per-row commits, alternate transition rules, skipped SCREENING, guide/activation
loosening, checker changes, external adapters, automatic write retries, provider
access, payouts, CI reductions, deployment, merge or issue-closing keywords.

## Design and decisions

Use native committed batch/member identities and preserve original row order in
responses. Lock all selected TASK/Assignment custody deterministically before
CHECKERS/project-policy or AUTH custody. Canonical single-Task operations and
bulk operations share the same flush-only participants and existing per-Task
receipts. One caller root authorizes every member and commits all lifecycle,
locked-guide, audit and receipt effects together. Aggregate exact-key custody
must bind the project, native batch, operation, reason and immutable membership;
its concrete receipt design is reviewed with the atomic owner before backend
composition. Replay reauthorizes the current covered PM and never reapplies
effects. Partial advanced state, crossed membership or any late failure refuses
the whole request.

The lead confirmed canonical replay currentness on this assignment: every member
must still match the recorded SCREEN/RELEASE post-state, locked-context hash and
unassigned custody. A partly advanced or assigned batch conflicts atomically even
with unchanged input/key. Atomic-import replay's original DRAFT facts after
advancement remain a separate contract. CLI uncertain-write instructions retain
the same key/request, and warn that subsequent state changes can prevent replay.

### Proposed aggregate custody for owner review

The import/source command receipt cannot represent SCREEN/RELEASE, and the
canonical per-Task namespace admits only one Task per actor/action/key. A dedicated
`TaskBatchTransitionReceipt` plus append-only `TaskBatchTransitionMember` is
proposed; no new AUTH action or alternative Task writer is needed. The root's
receipt namespace is actor + existing SCREEN/RELEASE action + caller UUID key.
It binds exact project/native batch, reason request digest and original immutable
batch manifest. Successful member links bind every native import member in row
order to its canonical per-Task command receipt and consumed authority decision.
Per-Task keys are server-created random keys retained in those exact links;
callers never choose membership or per-row keys.

Reservation and complete native membership preparation occur before any AUTH.
Prepare each canonical Task operation in UUID order (receipt, Task, assignment),
then consume all fresh per-Task authority, then stage shared canonical transitions.
Only after all succeed does the aggregate become committed with its exact ordered
response. Replay uses the retained per-Task links, freshly authorizes all members,
and runs canonical currentness recovery. Changed request and member/receipt drift
are conflicts after authority; no successful staging survives a late failure.
Direct-SQL guards must enforce exact closed action, complete membership, canonical
receipt/action/Task/actor/project equality, audit equality, original row order,
success response equality and immutable committed rows. Pending reservations
remain transaction-local, never a separately committed partial lifecycle.
Committed aggregate/member UPDATE and DELETE and statement-level TRUNCATE must
be refused. Deferred commit closure requires exactly the complete original native
member set/count; no subset, duplicate, substituted Task, action, actor, project,
decision, receipt or response is admitted. Reservation actor/Task/batch FKs must
defer premature AUTH/ART locks. The atomic owner independently reviewed this
namespace/closure design and found no shared-region blocker.

Links alone could reuse earlier committed single-Task receipts and misrepresent
one aggregate root. The lead approved explicit nullable canonical receipt root
binding, subject to the atomic owner's exact model/replay handoff. Bulk receipts
bind `batch_transition_receipt_id` into their request digest; existing null
single-Task and CREATE request digests remain byte-compatible. Deferred closure
must require that exact binding and its canonical success/AUTH evidence, so a
historical standalone success cannot be enrolled after the fact.

### Historical aggregate checkpoint before schema installation

The aggregate models, compact public DTO, native membership selection, reservation,
sorted all-Task preparation, fresh all-member AUTH, canonical staging and exact
ordered replay are implemented. Both public routes compose through the actual
canonical Task denial lifecycle. Successful AUTH, Task effects, member links and
both receipt layers share one root; the response is validated/serialized before
commit. Complete replay compares all native links and canonical root binding,
recovers each normal retained current-state receipt, and compares the complete
original compact response. An identity-link mismatch also rolls back the root.

Pure compact-contract plus retained parser verification passed 41 cases. Ruff and
the protected module-boundary validator passed without exemptions or new private
edges. Native participant proof at the earlier exact clean extraction head
`4400568a484a8a3fdf1a428d3ef78e560c892c27` passed five cases in 225.05 seconds
through migration 0031 with cleanup complete; it proves the extraction only.
The newly written aggregate tests cover complete 200/500-member public journeys,
fresh-authorized exact replay, injected failure after the second actual canonical
write, changed-input/partial-advance rollback, real grant-revocation denial and an
observed native holder/waiter before concurrent same-key recovery. They have not
run because aggregate custody DDL is pending the sole migration author. No native
aggregate, native 200/500 timing, full CI, or readiness claim is made here.
The native module also carries two commit-closure controls after genuine
canonical stages: omitting the final initial member INSERT and leaving the root
pending. Both require a complete successful-effect rollback. Direct SQL controls
cover UPDATE/DELETE and TRUNCATE refusal for each committed aggregate table,
unchanged retained facts and fresh-authorized exact replay afterward. They are
written controls awaiting installed schema, not executed native evidence.

Peer review of aggregate checkpoint `42900b036` found that the new dependency
projected immutable identity after the canonical Task dependency rolled back and
expired the resolved ORM actor/link. The repair projects the existing public
`ActorIdentityFacts` first, before that rollback; no row refresh, implicit read,
new authority owner or private actor import is introduced. The peer dependency-order/ORM-expiration discriminator uses actual FastAPI and
attached SQLAlchemy models without SQL, schema or AUTH execution. It proves the
composition defect and correction; native aggregate public proof remains pending.
The same peer review found missing/blank RELEASE input reached the native pending
receipt reason CHECK before normal validation. The repair uses the canonical
`TaskValidationError` reason requirement before opening/reserving the root,
retains the native CHECK, and adds public missing/blank negative controls asserting
unchanged aggregate, Task, lifecycle and successful authority facts. Valid inputs
still consume every member's fresh canonical AUTH.
The repaired pure compact/admission plus retained parser checks passed 44 cases
in 7.40 seconds; the protected module-boundary check also exited successfully.
The owned idle PostgreSQL container was stopped after the earlier native proof's
isolated DB/role cleanup, while aggregate DDL remains pending.

Peer review also found the canonical model graph omitted the aggregate tables,
so the new canonical receipt FK could not resolve in a fresh process. The repair
registers both aggregate classes through the existing metadata-discovery owner
and relocates their unchanged bodies once to the protected `.models` shape.
The focused regression imports only `app.db.models` in a fresh interpreter,
resolves every canonical FK and compiles the canonical receipt and aggregate
tables with the PostgreSQL dialect. This is model-graph proof, not installed DDL
or native aggregate proof.
The focused compact/admission/model-graph module passed 15 cases in 7.98 seconds.
Removing only canonical registration makes the fresh-process check fail at the
missing aggregate table; registration was restored exactly. The protected
module-boundary validator passed without ledger changes or gate exemptions.

CLI import/status/screen/release are implemented as separate exact typed calls.
Original/status responses are bounded to 16MiB, compact transitions to 2MiB,
with complete 1..500 ordered membership and strict original DRAFT/source custody.
Status validates original and current identities independently. The six new
built-CLI HTTP cases passed in 15.03 seconds, including complete 500-row output,
crossed/malformed/partial refusal, invalid selectors/keys producing zero requests,
canonical versus unrecognized denial, dropped connections and one-body/one-h2
GOAWAY behavior. These are controlled HTTP fixtures, not native batch proof.
Go compilation, focused package tests and `go vet ./...` passed. The longer
deadline for batch writes has not been selected: it remains dependent on actual
native 200/500 timing, and existing transport semantics remain unchanged.

No migration ordinal is allocated here. The sole author receives the final exact
models and constraints only after this custody design and shared regions are
reviewed. New tables are justified by the concrete aggregate/per-Task namespace
gap; no business snapshot or generic batch framework is proposed.

Proposed public routes are POST project-scoped native batch `/screen` and
`/release`, with a bounded reason and caller UUID Idempotency-Key. Responses name
the exact project/batch/operation and 1..500 ordered Task results. Release requires
its normal nonblank reason and all locked prerequisites.

CLI uses `project task-batch` with explicit project/source/batch selectors and
caller-owned keys. Local `convert-csv --input FILE --out FILE` creates bounded
UTF-8 canonical JSON without network or token access; output refuses existing
files. It handles CSV quoting, Unicode and semicolon-separated skill fields,
maps category to task_type and languages/tools to skill_tags, validates 1..500
rows, required case-sensitive external IDs and document limits, and reports the
SHA/count of its exact output bytes. Those JSON bytes are the uploaded server
source; no original-CSV retention claim is made.
CSV headers accept canonical row names plus `source_id` for `external_task_id`,
`category` for `task_type`, and semicolon `languages`/`tools` appended after
`skill_tags`. Duplicate/unknown headers and simultaneous alias/canonical headers
are refused. Blank semicolon segments are omitted; other instruction text and
case-sensitive external IDs are preserved. One optional UTF-8 BOM is accepted.

## Acceptance criteria

- A real 200-row source/import followed by one SCREEN and one RELEASE produces
  200 READY Tasks with exact immutable membership, per-Task authority/audit and
  the normal locked guide/policy fields.
- Invalid/missing prerequisite, unauthorized member, arbitrary metadata,
  partial advanced state, changed key payload or late write failure leaves no
  partial lifecycle, successful audit or receipt effects.
- Fresh-authority exact replay and actual PostgreSQL concurrent lock controls
  preserve original identities, deterministic order and revocation refusal.
- CLI performs only explicitly requested writes, validates exact returned
  selectors and bounded results, never automatically retries, and preserves
  caller keys for manual unchanged-request recovery.
- CSV quoting/UTF-8/semicolon mapping and invalid/duplicate/501-row/oversized
  cases are discriminated; output SHA/count equals uploaded JSON bytes.
- Required complete CI, independent AUTH/architecture/product/QA review and
  current source documentation are reconciled at the final tested head.

## Risk and review routing

- Risk class: `L1`.
- Required reviewers: AUTH/security, architecture/reuse, product operations,
  QA/test delta and affected documentation/CI ownership, coordinated by the lead.
- Human review focus: aggregate replay custody, shared participant parity,
  locking/rollback and explicit CLI write semantics.

## Evidence

The exact `34256da51b5041561877b797affb4f4b5189cdd8` full native batch ended
at the unchanged 1800-second runner limit (exit 124), with database, role and
MinIO cleanup complete. It produced one completed-case progress marker and no
final JUnit report; no complete-suite or 200/500 timing claim follows from it.
Live PostgreSQL observations showed active COMMIT with no wait event during
both aggregate and 500-row import closure. Repeated deferred child triggers
were invoking the whole membership validator for each member.

The sole migration author supplied `136e20199e77ab7f90d3380ce906e19265ea4c5b`
and its reviewed repair `90069d357c5dc65c88648c0807f36ad4e1daf617`. Complete
closure now runs on the committed root event; child admission requires a
committed parent written in the same top-level transaction. Import replay
commands validate their own immutable facts against retained original custody.
Every root/command event checks the final persisted status, so an empty pending
declaration cannot escape closure. Native xid comparison preserves epoch
semantics, and the sole author measured the changed public function fingerprint.
The owned native test adds an empty-root/no-child refusal and a surplus command
attachment to an earlier committed aggregate. These controls distinguish the
new admission guards from member completeness and immutable UPDATE guards.
The composed native proof, complete suite and measured batch-write CLI deadline
remain pending; source and focused two-case proof qualifications below remain
unchanged.

The exact clean `966b98a547ebcaff22e8ad3d9f20021d21f670f3` composed run completed
in 786.13 seconds with 15 passes and two failures, and all database, role and
MinIO cleanup complete. Both 200/500 public import-screen-release journeys with
fresh replay passed. Recorded SCREEN durations were 58.60/121.36 seconds and
RELEASE durations 48.96/115.93 seconds. Empty pending declaration, surplus
command attachment, complete-membership, concurrency, partial advance, direct
SQL immutability and original import replay controls passed. The revocation
fixture selected all active PM grants instead of the actual imported creator's
grant; its repair narrows that selection. The stronger digest control observed
only the first lifecycle INSERT before refusal; its repair injects into the last
initial lifecycle INSERT, after both real Task writes are observed. The original
failure remains retained, and focused repaired proof is pending. No full native
suite, hosted CI or readiness claim is made from this partial result.

Focused replay at `f7f399580d5331b9f2bcd90ab504cc245c099f12` passed the stronger
digest corruption control after both actual Task writes and failed the grant
fixture selection, in 40.99 seconds, with cleanup complete. The creator has both
system and project-covering PM grants; selecting only its actor still returns
multiple grants. The bounded repair revokes every actual covering PM grant in
deterministic order through the unchanged canonical revocation operation. It
retains permission denial, denial-only evidence and unchanged successful facts.

Focused replay at exact `0e642e9f4ee091d4be7bafd6ee41388c69fac35e` passed both
repaired controls in 49.68 seconds, with installed 0035 and all cleanup complete.
The original statement trace qualifies the digest refusal: the existing
`guard_task_management_audit` baseline INSERT guard reports SQLSTATE 23514,
`task management audit mismatch`. It already recomputes the null-stripped
resource-context digest and compares the consumed decision. The control proves
two real Task writes followed by native refusal and complete rollback; it does
not separately prove the redundant aggregate hash predicate or a completed
second receipt/root. The earlier assumption that no SQL manager-fact binding
existed missed the retained baseline and is corrected here.

The measured 500-member SCREEN maximum of 153.72 seconds exceeds the default
twelve-second CLI deadline. The scoped batch-write deadline is three minutes,
an explicit budget with headroom above these local timings, not a production
latency promise. Other requests retain the default deadline. All-body/connection
failure uncertainty, caller keys and no automatic write retry remain mandatory.

Go tests, build and vet passed for the scoped transport checkpoint; all 18
controlled CSV/source/batch HTTP cases passed in 65.49 seconds, including actual
thirteen-second batch-write responses and ordinary status timeout. First native
socket attempt at `202af962afcc7cb9e43500cb28f57a5d18bc8af7` failed before any
business request because its fixture omitted the canonical pagination HMAC
secret required by application lifespan. Database, role and MinIO cleanup were
complete. The fixture imports the existing canonical secret provisioner; no
startup guard or product configuration requirement is relaxed.

At clean `b8ae5e0646b11f3f7de3af7722834f67e2665853`, the actual built-CLI
200-row socket journey passed in 198.99 seconds with installed 0035 and complete
database, role and MinIO cleanup. Import took 20.63 seconds, SCREEN 59.95 and
RELEASE 59.04. This is exact-head caller evidence, not final-head full CI or
readiness. Inspection then found the CLI wrongly required the original batch's
source ID to equal a different verified equivalent source used for recovery.
The atomic owner deliberately retains the original source/rows and permits that
recovery with a new key; the CLI must validate equal verified bytes while keeping
that original response. An unchanged key with a changed selector still conflicts.
The owned native bulk module also adds a genuine missing-active-guide negative:
verified source and DRAFT import succeed in a bare project, but SCREEN must fail
with the canonical prerequisite error and no successful Task, aggregate, receipt,
lifecycle or authorization effects. The added equivalent-source and prerequisite
controls are written but not yet executed at this repair checkpoint.

Exact clean `56b15ba0b5d7666247e35f05981eb16a5a2ea47f` passed Go test/build/vet
and nine affected controlled HTTP cases in 6.53 seconds. Actual socket recovery
passed in 23.83 seconds: two distinct verified sources with equal bytes recover
the original batch/source/ordered rows under a new key, while the original key
with a changed source conflicts without duplicated effects. The genuine missing
active-guide SCREEN refusal passed in 16.37 seconds with zero success effects.
Both isolated native runs used installed 0035 and completed database, role and
MinIO cleanup. These focused proofs do not claim final full-suite or hosted CI.

The complete 18-case native bulk selection passed in 859.62 seconds at clean
`932412232c6af92d94c74558841f0858f9a68ac0`, installed 0035, with all database,
role and MinIO cleanup complete. Real 200/500 source→DRAFT import→SCREEN→RELEASE
and fresh-authority replay passed; SCREEN took 56.08/153.72 seconds and RELEASE
47.35/131.30. Complete native membership, partial advancement, late real Task
write rollback, canonical grant revocation, observed PostgreSQL holder/waiter,
empty pending roots, surplus/old standalone receipt attachment, immutable SQL
UPDATE/DELETE/TRUNCATE and advanced-state original import replay all passed.
The initial command misspelled the replay test selector and exited during
collection without running tests; its cleanup and raw result are retained. The
corrected exact eighteen-node selection was collected before this complete run.
No timeout, lifecycle guard, authority rule or migration was changed for it.

At the same frozen head, Go test/build/vet, full backend Ruff, all 25 owned
CSV/source/batch HTTP controls and existing documentation/stacked-record/boundary
checks passed. All nine protected MCP fragments match actual backend OpenAPI
and their canonical digests using the canonical selected-fragment helpers; the
reused environment cannot execute the whole MCP suite because its older MCP
dependency lacks `mcp.server.context`. Hosted complete checks remain required.
Actual final CLI collection is 167 tests, split disjointly into 165 retained and
two native caller cases. The source-artifact shell binding accepts only the
exact SHA/attempt and rejects a prior attempt; removing that guard admits the
same wrong artifact.

The two-case native CLI partition passed at exact clean
`2c9cff0a12ced5c817de885362f05df6abbb6561` in 176.02 seconds, within the unchanged
240-second cap, with installed 0035 and complete database, role and MinIO cleanup.
The 200-row socket case measured import 17.58, SCREEN 45.12 and RELEASE 48.41
seconds; equivalent-source recovery/conflict took 14.01 seconds. Go source bytes
and native bulk product/test bytes are unchanged from the recorded `932412232`
proof; this checkpoint only fixes the closed API inventory and records evidence.

The retained mixed 165-case CLI run exhausted the original 240-second cap with
complete cleanup and no observed assertion failure. Its buffered partial output
records 73 completed tests; actual collection places the next running case at
the existing delayed guide-upload HTTP control. This is retained as a failed
budget proof, not a passing suite or a batch product failure. The bounded repair
separates controlled HTTP/local checks from the existing native public API files
using complementary selections, retaining all tests, the same 240-second caps
and fifteen-minute job cap. No fixture deadline, test assertion or lifecycle rule
changes. Both resulting partitions and the updated exact completeness comparison
must pass before claiming this workflow usable. Independent review and complete
hosted CI remain pending.

The first split run at `2b8e88ec` also exhausted 240 seconds, with complete
cleanup and 53 completed cases. Its collection revealed a concrete selector
defect: pytest resolves ignore globs from the `backend` working directory, so
`*_public_api.py` did not exclude files under `cli/tests/integration`. Those
native callers still ran in the supposed HTTP partition. The corrected glob
names that directory explicitly; its collection contains 156 controlled cases.
The complementary nine existing native files contain nine cases, and the owned
bulk file contains two. All 167 original cases must remain selected once. The
same caps, fixture deadlines, assertions and product contracts remain unchanged.

The corrected 156-case HTTP run at `051a0adb` reached 145 passing cases before
the unchanged 240-second cap, again with complete cleanup and no reported
assertion failure. Collection identifies the next case as the existing
malformed Task-guide media-type control, after cumulative delayed transport
controls. The bounded repair separates existing guide-family HTTP files from
the remaining task/local HTTP files, keeping 240 seconds for each group and the
fifteen-minute job limit. Exact collection must prove their union plus the nine
retained native and two bulk native cases equals the original 167, with no
overlap. Actual measured partition results remain required.

At exact clean `32d033903`, guide HTTP passed all 58 cases in 74.66 seconds and
task/local HTTP passed all 98 in 173.76 seconds, each with complete cleanup. The
retained nine-case native selection then exhausted 240 seconds after eight
passing cases, during the final existing self-service case; no assertion failure
was reported and cleanup completed. Native guide callers and that self-service
file are now separate bounded selections, each still capped at 240 seconds.
The job limit stays fifteen minutes and its required workflow result covers all
groups. These partitions retain the original 167 tests exactly once; no test,
deadline, fixture or product owner changes. Their measured results are required
before a final workflow claim.

The final native selections passed at exact clean
`43ff2ae51e7342a90b83ac574318ff88e5161c28`: eight guide callers in 184.81 seconds
and the self-service caller in 79.38 seconds, each under the unchanged
240-second isolated-run cap with complete database and role cleanup. Neither
group provisions MinIO or claims its byte custody. Combined with the recorded
58 guide HTTP, 98 task/local HTTP and two real-MinIO bulk native cases, all 167
CLI cases are selected exactly once. Actual collection proves the five sets are
pairwise disjoint and their union equals the whole integration directory. Every
completed partition has zero skipped, failed or errored cases. The five pytest
durations total 688.63 seconds; isolated provisioning, build, installation and
provider startup add job time. The unchanged fifteen-minute hosted job budget
still requires an actual hosted result; this local proof does not claim hosted
CI success. Workflow repairs and this evidence update do not change the Go,
backend product or native bulk test bytes used by the recorded proofs.

Inspection at atomic checkpoint `4a6d00fc8` identifies the reusable canonical
SCREEN/RELEASE root and the native `TaskImportBatchMember` custody. This branch
is reconciled onto the unmerged atomic candidate `91183adafec37e7ad7eda624ad3556d89dc54ce6`;
preserve its source/member/ten-lane metadata union and use only an explicitly
coordinated stacked draft before its human merge. Native schema/storage claims are
pending the sole-author migrations and actual isolated PostgreSQL/MinIO drills.
The offline converter is implemented with focused Go boundary checks and built
CLI/server-parser proof for quoting/Unicode, exact JSON commitment, no-clobber,
invalid CSV zero-output effects and 500/501 rows. This proof needs no token/API
configuration and makes no database or source-storage claim. Canonical
SCREEN/RELEASE extraction and the single native membership owner are implemented;
aggregate models/public composition are also implemented, with native aggregate
DDL and actual public proof still pending.
Source CLI uses separate existing declaration/upload/status routes and sends exact
original JSON bytes. Go tests/vet/tidy-diff and built CLI CSV/source boundary plus
retained HTTP/profile/project/guide declaration checks pass. The PUT transport
control removes only its write classification: the actual HTTP/2 peer then
receives two identical bodies on two connections and the client loses uncertain
write reporting. The correct implementation receives one body/connection and
reports uncertainty. Source was restored byte-exact after that control.

The atomic owner explicitly handed off SCREEN/RELEASE phase extraction and the
native original/member validator at clean `4a6d00fc8`. CREATE preparation,
import/source ancestry and `_prepare_sources` remain with that owner. The shared
validator extraction must preserve label/manifest, ordered native Member/CREATE
receipt/response validation and advanced-state-independent original facts. Its
commit will be shared back with the atomic owner to avoid parallel validators.
Protected-base module-boundary validation and canonical import parser checks
pass. A native preflight proves retained single-Task SCREEN/RELEASE replay/guide
lock parity, successor-guide/currentness behavior, foreign-root participant
refusal, and two-Task late-failure rollback including actual successful AUTH
decisions. Its database/role cleanup is complete. The initial run used the dirty
extraction atop the CLI checkpoint; the later exact `4400568` five-case native
replay above supplies the qualified frozen extraction proof.
This uses existing schema through source0031 and canonical seeded project
prerequisites; it proves Task/AUTH transactions, not new batch DDL, provider bytes,
live setup inference or a complete 200-member public bulk journey.

## Reconciliation

The native journey's AUTH assertions use canonical manager audit projection:
`resource_type=project` and the exact project resource ID. The retained Task
lifecycle event binds each member's original decision through its authorization
reference, exact `manager_authority_facts` Task/project and identical context
digest. Replay allow-count observations select the project resource too. This
repairs the test's former Task-ID expectation without changing AUTH projection,
product behavior or the immutable aggregate contract. Installed bulk/native
proof remains pending the sole-author schema and source handoff. The sole DDL
author requested a source-model index named
`ix_task_command_receipts_batch_transition_receipt_id` on the nullable aggregate
root reference. Exact closure must count all attached canonical receipts,
including surplus; the index avoids a growing global receipt-table scan per
commit. The sole author mirrors this same index in the sequential migration.

Main `d47ee1e9917689b94fd9439c09dffaf88c6d3ec1` now contains P10's linear audit
migration 0033. This branch preserves its source and read contracts alongside the
atomic import candidate, including both exact AUTH audit-target arms and all
existing catalogue actions. Their approved union contains 152 ActionIds (116
active and 36 planned, with permissions unchanged); its
closed count and exact assertion are updated together. The protected partition
now has 480 unique targets and the complete lane inventory has 532 modules,
preserving all incoming/atomic/bulk targets and the original protected base.
The selected MCP operation/components already equal the actual merged OpenAPI;
only the union digest and exact capture provenance are reconciled. Native atomic
and bulk migrations remain sequential sole-author work after 0033.
The focused reconciliation run passed the 46 exact CI-catalogue and 15
compact/admission/canonical-graph cases; its only failure was the retained
114-active catalogue assertion. Updating that exact expectation to the union's
116 active actions made all seven catalogue cases pass in 6.18 seconds.
Protected module boundaries and scoped Ruff checks also passed. These are
source/model/contract checks, with installed bulk proof still pending.

Before the main-d47 union, additive bulk metadata preserved every trusted
assignment and the existing protected base: 459 unique production targets
validated, with exactly five new bulk paths; that ten-lane inventory covered
523 test modules. Its exact
TASK owner assertion is extended by the two actual new proof modules; the focused
catalogue suite passes 46 cases in 7.79 seconds without weakening any gate.
Canonical TASK/CLI documentation distinguishes current-state transition replay
from original import replay and still marks native aggregate readiness pending.

The atomic predecessor is integrated from exact `09570d3a956a0c604b76c04037027c1dd8fd5c0f`,
whose separately produced installed-0034 public proof passed 26 cases in 686.84
seconds with database, role and MinIO cleanup confirmed. That evidence covers
atomic import only. Sole-author `6d315a41e7511906793da4cbb86ee2d697066576`
is consumed once as the unchanged 0035 successor; its separately captured
exact-head graph/reset/native-UUID proof passed three cases in 18.95 seconds.
The composed source is `a2c1c96cc2a83e17689e56e51327ae234593f242`.
The additive ownership union preserves all 480 targets and the original
protected base. Only the selected MCP authorization-context capture is updated
to this exact source; all nine retained selected contract fragments are checked.
These predecessor/schema controls do not prove the public bulk transaction.
The composed `370edbd87` native attempt failed before bulk admission: all 14
cases reached source upload's genuine scratch free-space floor. The isolated
database, role and MinIO namespace were cleaned up. A separate initial MinIO
storage-floor refusal is also retained. The owned replacement MinIO uses bounded
tmpfs; pytest scratch now lives in owned `/dev/shm` with sufficient physical free
space. ART's 512MiB reservation and 512MiB minimum floor remain unchanged.

The two-row discriminator then proved actual late second-stage rollback, but
legitimate SCREEN failed at commit. Its original SQL exception was the 0035
custody check: the validator equated SCREEN's consumed pre-write context hash
with its post-write receipt hash. The sole migration author supplied `f6b53ea1`,
preserving RELEASE equality and exact pre-state binding. Its protected setup
refusal measured fingerprint `b280e4e561f83740799a4fe29c43ba73145262d05d663d4bf7e7439cbdf7189a`;
sole-author `fc1794b8` records that measurement. All these runs cleaned up their
database, role and MinIO namespaces.

Further source review required an explicit aggregate check of the actual
lifecycle manager facts. Sole-author
`af2bdc2d` adds the exact canonical hash of the null-stripped manager resource
context against the consumed decision. Its changed function body requires a new
measured schema fingerprint. The existing native incomplete-custody control now
also alters a digest-shaped initial lifecycle pre-write hash while retaining the
genuine decision and event digest. It must refuse admission and roll back all staged
effects. This is an additive test-only admission control; no production or gate
owner changes. The 15-case suite retains the actual 200/500 journeys, currentness,
fresh authority, observed PostgreSQL waits and immutable SQL controls. Native
public bulk success, those timings and readiness remain pending. Sole-author
`ae9263b8` records the completed function body's measured PG16 fingerprint
`fea62e31eaedf4812046fda79c6dd732edb8f74184a4103d41ed8bb743f4d7bf`.
The exact clean `79debf3eae277f6f5b848dbfcbf9d279206ba634` discriminator run
passed two cases in 99.73 seconds with installed 0035 and database, role and MinIO
cleanup all confirmed. It proves late-stage rollback followed by legitimate
SCREEN, changed-payload and partially advanced replay refusal, and the new
altered-manager-facts refusal. The negative control additionally observes both
canonical Task writes before refusal; the full 15-case run must verify
that stronger observation and the larger journeys before any readiness claim.

- Current-source reconciliation: Preserve the atomic owner's import/status and
  source custody; shared-file regions require handoff before edits.
- Next usable boundary: Complete the separate explicit bulk/CLI journey under
  issue 489; whole-issue completion requires every agreed acceptance criterion.
- Remaining risks: The installed aggregate receipt/currentness contract has the
  recorded native 200/500, rollback, concurrency and direct-SQL proof. The atomic
  owner must consume the sole-authored 0034 correction before its human merge;
  bulk must not edit an already deployed predecessor migration. Required final
  independent reviews and complete hosted CI remain. Local bounded CLI
  partitions pass; hosted job-level timing remains unproved.

## Current-main takeover reconciliation

Reconcile bulk/CLI against the root atomic import slice and merged main
`6d64a6353`. Allowed paths are the existing scoped bulk/CLI paths above, additive
metadata, current roadmap and exact CI contract assertions. The sole migration
owner places bulk after reconciled atomic `0037`, preserving the current selected
checker flow and all merged migrations. Do not restore historical schema seed
adaptors removed by PILOT-04; retained literal fixtures remain canonical.
Preserve current-main CLI 300-second isolated bounds and 15-minute job bound,
all current native export tests and disjoint exhaustive test selection. Verify
actual public CSV200/source/import/status/screen/release/replay plus invalid,
revocation, rollback and PostgreSQL waits. Required independent tracks include
architecture/security, QA/test delta and CI integrity; no deployment or merge.

### Migration-owner linearization

The migration-only reconciliation renames the unchanged aggregate-custody
migration to `0038_task_batch_transitions` and places it directly after
`0037_task_import_batches`. The migration body remains byte-identical to the
final `e1b813db` handoff apart from its revision identity and predecessor. The
linear graph and reset/TRUNCATE inventories preserve merged selected-checker
tables, all three atomic-import tables and both bulk-transition tables. Alembic
recognizes each installed revision through the single `0038` head.

The first controlled PostgreSQL 16 setup retains the measured atomic `0037`
fingerprint
`5abd992592eea9b00ce1f2b4330ff0e121577ff7c8ab34fc76fa9e71a8d336d5`
only to emit the exact combined `0038` digest. That deliberate setup refusal is
not a bulk test pass; the migration owner must bind the measured combined value
before affected schema and public bulk proof. No application, model, AUTH,
workflow, cap, predecessor fixture or compatibility code is part of this
migration reconciliation.

### Measured placement of new batch proofs

The authenticated main Backend run `38352326348` leaves aggregate TASK headroom
986.284s under unchanged 1200s caps, versus historical atomic+bulk native totals
1546.46s from different sources. Existing PROJECT headroom is 1856.320s.
Place only the five new project/source/batch proof modules in the existing four-way
PROJECT partition, preserving every main module, node and execution kind. This
is a placement rationale, not a passing-time prediction. Actual final hosted
execution remains required, especially the concentrated 500-member journey.

After the atomic timestamp repair and current-main CLI reconciliation, fresh
native `0038` at `6f6bc1c1fed5ce825e1a4f01ad5ff3a46f02f4fe` measured
`1178d7b70c17bfb3a6f55737a771834c7798f535d39ac96a488cd7cde2cb869d`.
`/tmp/pilot02-bulk-schema-measure.{log,json}` uses the unchanged conftest
catalogue query extracted verbatim and executed against the isolated migrated
PostgreSQL database. All database/role/MinIO cleanup completed. This proves
schema installation and fingerprint only; behavior execution remains required.

Independent QA found two remaining contract mismatches: the CSV standard-library
reader normalizes quoted CRLF despite exact instruction preservation, and new
batch reason bounds permit 4000 characters while canonical TASK/AUDIT permit
1000. Repair scope retains the standard CSV validator and recovers original
quoted contents; all new bulk request/CLI/model/DDL bounds must match canonical
1000 without enlarging existing owners. Add exact CRLF/LF and Unicode boundary
regressions, including public 1001 rejection without effects and 1000 admission.

At `c743c3135`, the 200-row public native journey passed, but its four-case
group timed out at 900 seconds during the next case. This is not a full pass.
All owned cleanup completed. The isolated rollback case at `38a6bcae8` then
passed in 72.53 seconds (39.32-second call), with all cleanup complete; it did
not reproduce a lock hang. Raw evidence: `/tmp/pilot02-bulk-current-native4`
and `/tmp/pilot02-bulk-rollback-diagnostic` `.log`/`.json` pairs.

The reason discriminator at `785c7f7dd172b6790d899cea723d27e5862c8e08`
reproduced an actual HTTP 500 for a 1001-character reason instead of the expected
422 (`/tmp/pilot02-bulk-reason-before.{log,json}`, one failed in 93.96 seconds,
all cleanup true). New DTO, CLI, ORM and sole-author DDL bounds now use the
canonical 1000-character limit; the existing canonical owner is unchanged.
