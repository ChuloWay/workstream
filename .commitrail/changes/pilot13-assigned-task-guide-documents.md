# [PILOT-13] Assigned contributors read exact locked guide originals

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Assigned contributors list and download their task's
  exact guide originals through public REST and Go CLI, without examples.

## Intent

Fix F-018 / [issue #503](https://github.com/Flow-Research/workstream/issues/503).
A contributor must be able to read the instructions governing assigned work.
Original documents already exist under ART custody and TASK already locks their
snapshot. Do not create storage, byte copies or another policy lifecycle.

## Current behavior

`AuthorizedTaskCommands.contributor_work_context` resolves exact activated
historical PROJECTS context but returns guide display identity only. Its existing
AUTH read also allows unassigned ready-task browsing. Setup document manifests
and `ScopedGuideDocumentGrant` are explicitly current-draft/run scoped; reusing
their authorization for a contributor would be incorrect. ART's committed
original resolver and preparation service already check durable replica/receipt
identity and completely hash/count bounded bytes in canonical scratch.

## Bounded change

### Allowed

- TASK public guide-document contracts, contributor work-context schema,
  authorized command, route and existing task composition/dependency roots.
- PROJECTS public locked-original metadata capability and its repository/root;
  exact active/superseded guide and snapshot selectors, original item/ingest only.
- ART original resolver extraction/reuse and TASK-consumer implementation/root;
  existing provider-neutral bootstrap, namespace validation and scratch preparation.
- One assigned-task-only AUTH action, catalogue/domain rules, exact audit-evidence
  pair migration after current main, and corresponding contract fixtures/tests.
- CLI work-context decoder/renderer and fixed `task guide TASK_ID [--download DIR]`
  command with authenticated original reads through the shared transport.
- Focused TASK/PROJECTS/ART/AUTH integration tests, CLI process/real-API journey,
  lane catalogue and existing exact behavior-ownership partition registration
  for the two new Python modules, current API/CLI docs, affected roadmap claims
  and this standalone record.
- Existing MCP authorization-context snapshot: synchronize only its transitive
  `ActionId` enum, canonical digest and backend capture reference; no new tools.

### Not allowed

No examples in contributor projections; no new guide/lock/storage tables or
per-task copies; no draft/newer/foreign reads; no broad management authority,
setup-agent changes, upload/presigned-URL subsystem, compatibility variants,
review/rebase implementation, frontend/MCP capabilities, dependencies, CI
weakening or merge. The existing MCP snapshot synchronization above is the only
adapter change.

## Design and decisions

- Add `task.guide.read` under existing project submitter permission. AUTH requires
  the current actor, identity, exact project grant and active assigned TASK facts.
  It does not grant unassigned-ready access. Conceal denied/wrong document reads.
- Contributor work context adds `guide_documents`, empty for legitimate ready-task
  browsing and populated only for the current assignment. CLI consumes that field;
  existing strict context decoding/rendering is updated rather than duplicated.
- Each public document has `document_id`, `order`, `label`, `media_type`,
  `byte_count`, `sha256` and a task-scoped relative `read_reference`. No storage
  coordinates, source bodies or examples. Membership follows the locked snapshot,
  not the latest guide. Historical activated/superseded guides remain usable.
- TASK's injected consumer port resolves originals through PROJECTS's public
  exact-snapshot metadata capability and ART's reused confirmed-version resolver.
  New ports are necessary because existing setup grants require a draft/run,
  while assigned work must retain an activated historical snapshot.
  TASK's frozen selection and response contracts remain owner-local; ART
  translates selectors to the PROJECTS port rather than importing PROJECTS
  contracts into TASK's public API.
- `GET /api/v1/tasks/{task_id}/guide/documents/{document_id}/content` prepares the
  entire original against its retained digest/size using canonical ART scratch.
  Missing/corrupt bytes become a structured integrity error before headers/body.
  AUTH/TASK/PROJECTS locks cover selection and verification; commit authorized
  read evidence before serving immutable prepared bytes. A request-scoped yield
  dependency owns provider/preparation cleanup even on disconnect/cancellation.
  No unauthenticated URL, ranges, caller provider key or first-pass streaming.
- CLI downloads only fixed same-origin public paths reconstructed from validated
  task/document UUIDs; never follow arbitrary response URLs or redirects. Use
  generated UUID/media-extension names, private bounded temporary files, verify
  digest/size before publishing, never overwrite existing files or trust labels
  as paths, and clean unpublished files on failure. Download reauthorizes each
  document; rebase/revocation between listing and fetching fails safely.
- Extend the existing JSON transport's bounded response selector for document-
  bearing work context (2 MiB); other read envelopes keep 64 KiB. Binary downloads
  stream to disk and cannot exceed ART's existing 512 MiB hard ceiling. Reuse the
  existing shared error redaction and one-shot mutation transport unchanged.
- MCP's existing authorization-context response transitively references AUTH's
  closed `ActionId` enum. Adding `task.guide.read` therefore updates that selected
  contract snapshot and its canonical digest; otherwise valid self-authority
  responses can be rejected by the existing adapter's response validator. Keep
  the backend OpenAPI drift check intact; do not add a guide MCP tool here.
- This single user-requested outcome crosses four existing owner boundaries and
  includes its requested CLI consumer. The diff exceeds the preferred small L1
  size because ports, catalogue/schema guards and retained constructor fixtures
  must change together. Keep it one cohesive PR, with explicit owner-focused
  review rather than splitting half-wired public authority across PRs.

## Acceptance criteria

- After claim, the work context and CLI list exact ordered locked documents and
  hashes/sizes; real downloads reproduce original bytes. No task examples leak.
- Stored Bob/foreign-project/unassigned actors, inactive grant/profile/link and
  unauthenticated callers cannot read; a stored foreign-snapshot document is denied.
- Activating a newer guide does not change current task reads. A PROJECTS port
  contract test resolves alternate exact locked selectors; it is not a product
  rebase test. Actual changed-membership/rebase ordering awaits PILOT-08, which
  owns the not-yet-implemented task rebase operation.
- Missing bytes, digest/size drift and namespace/receipt substitution never serve
  partial successful content; failed preparation releases owned scratch/provider.
- Real PostgreSQL proves exact stored lineage, authorization and read/revocation
  ordering; MinIO proves retained original readback/integrity.
- Built CLI process tests prove metadata validation, safe file publication,
  malicious labels/URLs, overwrite/symlink refusal, size/hash mismatch, cleanup,
  and authentication. Existing public real-API journey remains complete.
- Full hosted Backend/CLI and owner boundary, formatting, links, stale-wording
  and Commitrail checks pass without skips, quotas or weakened assertions.

## Risk and review routing

- Risk class: L1, bounded contributor authorization and original-byte delivery.
- Plan feasibility review before implementation. Focused architecture/reuse/docs,
  security, and QA/test-delta/product-flow assignments after a clean candidate.
- Human focus: active-assignment authority, locked historical rather than latest
  originals, no examples, complete verification before exposure, cancellation
  cleanup, and safe local file publication. No new human permission decision.

## Evidence

Implementation proof paths: `backend/tests/tasks/test_guide_documents.py`,
`cli/tests/integration/test_task_guide_http.py` and
`cli/tests/integration/test_task_guide_public_api.py`, alongside the retained CLI
public API journey. Fixtures must use real original ingest/confirmed receipts; a
mock guide or successful label alone cannot certify storage/assignment isolation.
Build a composite fixture from existing public guide creation/content upload to
MinIO and compilation/finalization/policy approval/activation helpers, followed
by public task creation, screening, release, claim and start. Independently
assert the stored confirmed receipt/object commitment before testing contributor
list/download. Existing activation fixtures alone script provider access;
existing MinIO intake fixtures alone stop before activation. Neither certifies
this complete boundary without connecting their real operations.
The independent CLI workflow uses its existing real PostgreSQL service and
canonical local ArtifactStore for the new public download journey; backend owner
tests separately prove MinIO behavior. This does not claim deployed Flow or
real model compilation. Agent findings are scripted; custody, activation,
authorization, task release/claim/start and document reads are real.
Observe a named PostgreSQL revocation waiter while a verified read retains AUTH
locks, then show revocation can commit before immutable prepared bytes finish
serving. Verify that a later request is denied and cancellation/integrity errors
release scratch reservations. No product rebase behavior is claimed.
Public ASGI disconnect proof additionally traverses FastAPI's yield dependency
and StreamingResponse after response start/first body, then checks provider
closure and zero retained scratch reservations. This is framework-composition
proof; the real CLI journey separately exercises the HTTP network boundary.
Run these through the existing isolated PostgreSQL/MinIO runner, Go build/vet/
module verification, Ruff, module-boundary checks, documentation checks and full
hosted suites. Prior missing-document context is the live-defect negative control;
digest/foreign-snapshot guards need discriminating defective variants.

## Reconciliation

Originally started from merged main `66a26d8d`; reconciled onto `235f9e1b`
after PR #501 merged. Its local-stack composition remains independently owned
and does not overlap this assigned-document read. PR #502 owns second-review
policy validation, not this read boundary.
Keep PILOT-12 upload transport separate; this read uses authenticated verified
streaming without choosing its upload-intent implementation. Remaining review,
rebase and upload work stays under its existing issues.
