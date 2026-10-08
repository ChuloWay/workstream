# [PILOT-15] Admit Markdown Guide Originals

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: A Project Manager can declare and upload a
  `text/markdown` guide original that retains byte-exact ART custody and is
  available through the existing setup-agent and assigned-contributor reads.

## Intent

Resolve F-019 / [issue #508](https://github.com/Flow-Research/workstream/issues/508).
Project Managers should not have to export a Markdown guide to PDF before using
the existing governed guide flow. Markdown remains an original guide document,
not executable input or a separate storage path.

## Current behavior

`GuideDocumentMediaType` and `DOCUMENT_EXTENSIONS` in
`backend/app/modules/projects/api/guide_documents.py` admit PDF, DOCX and PPTX.
The public guide declaration, ART upload format inspection, setup-agent manifest,
review-packet metadata and Go declaration client consume that closed type. The
database constraint on `review_packet_guide_items.media_type` independently
repeats the same three values. PILOT-13 PR #505 adds task-locked contributor
original reads and CLI downloads, but its open branch is not delivered behavior.

## Bounded change

### Allowed

- The existing PROJECTS `GuideDocumentMediaType` and extension mapping, public
  guide declaration schemas/OpenAPI, and their direct contract tests.
- ART's existing bounded guide-format inspector and upload admission path for
  byte-preserving UTF-8 Markdown classification; existing digest, size,
  idempotency, storage and namespace custody remain unchanged.
- The existing setup-agent manifest/workspace path and focused tests proving a
  `.md` original is opened under the same run-scoped grant, disabled-network
  container and exact resource cleanup.
- Review-packet typed metadata/model constraint plus one forward-only migration
  after the actual merged migration head, its graph/schema consumers and direct
  PostgreSQL refusal/acceptance proof.
- The Go guide-declaration client and current CLI/API documentation for
  `text/markdown`. After PR #505 merges, its task guide DTO/extension/download
  consumers and tests may be reconciled without copying its implementation.
- Existing guide API, real PostgreSQL/MinIO intake fixtures, format, setup
  workspace, review-packet, CLI declaration and later PILOT-13 contributor-read
  tests; current README, artifact/guide specifications, roadmap and this record.

### Not allowed

- No HTML, docs-site, URL-fetch or generic text formats; no Markdown rendering,
  conversion, sanitization or separate storage/per-task copy.
- No changes to PDF, DOCX or PPTX behavior, artifact byte limits, digests,
  namespaces, authority, locks, task/guide lifecycle, setup proposal shape or
  isolated-workspace policy.
- No checker catalogue/registration changes, activation refusal or recovery
  behavior; F-020 belongs to PILOT-04 / issue #491.
- No duplicate contributor read, task authority, streaming or CLI download
  implementation while PR #505 remains open. No compatibility variant, data
  rewrite, downgrade, deployment, merge or issue closure.

## Design and decisions

Extend the one owner type with `text/markdown` and `.md`. ART classifies the
declared type as bounded UTF-8 text without interpreting Markdown and preserves
the original bytes for hashing, storage and reads. Known binary signatures and
malformed UTF-8 remain invalid rather than being relabelled as Markdown. Existing
typed consumers inherit the new member; the review-packet database check receives
the matching additive value in the next linear migration. The setup agent stages
the verified original through its current opaque handle and network-disabled
workspace. Contributor REST/CLI support is reconciled only from merged PILOT-13.

## Acceptance criteria

- [ ] Public API and Go CLI declaration accept exactly `text/markdown`; HTML,
  `text/plain`, binary/malformed UTF-8 and media-type substitution remain denied.
- [ ] Real PostgreSQL/MinIO intake stores and reads back the exact Markdown
  bytes with the server-computed SHA-256, byte count and declared media type.
- [ ] The existing setup-agent workspace opens the exact `.md` version through
  its run-scoped grant and retains disabled network, bounded resources and cleanup.
- [ ] Review-packet metadata and PostgreSQL accept the exact Markdown member
  while direct writes of unsupported media types still fail.
- [ ] After PILOT-13 merges, an assigned contributor lists and downloads the
  task-locked Markdown original byte-identically through REST/CLI; foreign,
  unassigned, corrupt and unsafe-destination cases retain their existing denial.
- [ ] PDF, DOCX and PPTX declaration/upload/setup/review/contributor behavior
  remains covered and unchanged; no second migration head is introduced.
- [ ] Current API/CLI, artifact/guide specifications and roadmap state the
  delivered boundary without claiming HTML, remote sites or deployed capability.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, reuse, security, qa, test_delta,
  documentation, product_ops
- Human review focus: Strict media classification without byte rewriting;
  unchanged ART/authority/isolation boundaries; one linear migration after
  PILOT-13; no duplicate contributor-read implementation; honest format limits.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Bounded Markdown classification | Focused `test_guide_formats.py` and upload mismatch controls | Required before completion | Markdown semantics are not parsed or rendered |
| Durable original custody | Isolated real PostgreSQL/MinIO guide-intake journey with provider readback | Required before completion | Hosted S3 remains shared ART-provider evidence |
| Setup-agent exact read | Existing workspace/runtime tests with Markdown version and byte-bearing grant | Required before completion | No live model inference is required for byte-access proof |
| Persisted review metadata | Real PostgreSQL migration/direct-write and review-packet storage proof | Required after PR #505 establishes the predecessor | Existing rows are retained; no downgrade is supported |
| Contributor REST/CLI | PILOT-13 focused public API and built-binary tests extended after merge | Blocked on merged PR #505 | Open-branch code is inspection input, not delivered proof |

## Review findings

No review finding has produced a durable source change yet.

## Reconciliation

- Current-source reconciliation: Based on main
  `3fa0dfb9eeda18888cdced494dfe813bd8dacf63`, whose migration head is
  `0025_submission_dispatch`. PR #505 currently proposes the next guide-read
  migration and contributor read/CLI owners; this branch will not allocate its
  revision or duplicate those owners before it merges.
- Next usable boundary: Merge and verify PILOT-13, then reconcile its exact task
  guide media type and CLI extension consumers and allocate the next migration.
- Remaining risks: Live provider/model inference is outside this byte-custody
  change. Hosted deployment and HTML/docs-site ingestion remain unsupported.
