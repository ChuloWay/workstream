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
- Lead-approved exact `cli/internal/api/client.go` PUT additions: classify PUT
  alongside POST/PATCH at the three existing mutation checks and require the
  canonical error envelope for POST/PUT. Disable automatic body replay and retain
  uncertain-write reporting; no other shared-client changes are authorized.
- Exact CLI proof paths are new `cli/tests/integration/test_task_batch_csv.py`
  and `test_task_batch_sources_http.py`, plus
  `test_task_batch_commands_http.py`; the existing HTTP fixture receives one
  PUT handler delegating to its unchanged exact-body POST capture. No retained
  GET/PATCH/POST expectations or test guards are removed.
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

### Implemented aggregate checkpoint, migration pending

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

Further source review found that digest-shape plus event/decision equality did
not cryptographically bind the actual lifecycle manager facts in SQL. Sole-author
`af2bdc2d` adds the exact canonical hash of the null-stripped manager resource
context against the consumed decision. Its changed function body requires a new
measured schema fingerprint. The existing native incomplete-custody control now
also alters a digest-shaped initial lifecycle pre-write hash while retaining the
genuine decision and event digest. It must refuse commit and roll back all staged
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
canonical Task lifecycle stages before refusal; the full 15-case run must verify
that stronger observation and the larger journeys before any readiness claim.

- Current-source reconciliation: Preserve the atomic owner's import/status and
  source custody; shared-file regions require handoff before edits.
- Next usable boundary: Complete the separate explicit bulk/CLI journey under
  issue 489; whole-issue completion requires every agreed acceptance criterion.
- Remaining risks: The implemented aggregate receipt/currentness contract still
  needs sole-author native closure DDL, direct-SQL refusal, public rollback and
  concurrency proof, and measured 200/500 journeys before readiness.
