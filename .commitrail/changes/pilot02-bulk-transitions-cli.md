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
- Explicit atomic-owner handoff permits the single native membership owner in
  `task_import_membership.py`, its small `api/task_import_membership.py` error/row
  facts, exact original-response wrapper replacement, and batch error import
  updates in TASK router/import tests. A tiny `_locked_task` extraction shares
  its unchanged AUTH prepare/consume/finally-close block through `_authorize_facts`.
  CREATE methods/dataclass and source ancestry preparation remain untouched.
- New route/dependency modules and append-only composition of the typed batch
  transition owner. Shared TASK `router.py`, `schemas.py`, model/receipt and AUTH
  regions require an explicit owner handoff before edits. Existing per-Task
  SCREEN/RELEASE actions and canonical denial handling remain mandatory.
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
  and `test_task_batch_sources_http.py`; the existing HTTP fixture receives one
  PUT handler delegating to its unchanged exact-body POST capture. No retained
  GET/PATCH/POST expectations or test guards are removed.
- Native participant lifetime/composition proof is owned in
  `backend/tests/authorization/task_authority/test_management_participants.py`;
  it extends the existing management proof using actual PostgreSQL and AUTH.
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
is based on the unmerged atomic candidate; reconcile after its human merge or
use an explicitly coordinated stacked draft. Native schema/storage claims are
pending the sole-author migrations and actual isolated PostgreSQL/MinIO drills.
The offline converter is implemented with focused Go boundary checks and built
CLI/server-parser proof for quoting/Unicode, exact JSON commitment, no-clobber,
invalid CSV zero-output effects and 500/501 rows. This proof needs no token/API
configuration and makes no database or source-storage claim. Canonical
SCREEN/RELEASE extraction and the single native membership owner are implemented;
aggregate models/public composition remain pending.
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
extraction atop the CLI checkpoint, so exact frozen-head replay is still required.
This uses existing schema through source0031 and canonical seeded project
prerequisites; it proves Task/AUTH transactions, not new batch DDL, provider bytes,
live setup inference or a complete 200-member public bulk journey.

## Reconciliation

- Current-source reconciliation: Preserve the atomic owner's import/status and
  source custody; shared-file regions require handoff before edits.
- Next usable boundary: Complete the separate explicit bulk/CLI journey under
  issue 489; whole-issue completion requires every agreed acceptance criterion.
- Remaining risks: Aggregate receipt/currentness design and native concurrency
  proof remain to be established before backend public composition.
