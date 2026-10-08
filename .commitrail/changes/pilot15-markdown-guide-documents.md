# [PILOT-15] Admit Markdown Guide Originals

- Initiative: None
- Durable disposition: Complete
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
repeats the same three values. Delivered PILOT-13 provides task-locked
contributor original reads and CLI downloads with the same closed media type.

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
- Review-packet typed metadata/model constraint plus forward-only revision
  `0027_markdown_guide_media` after delivered `0026_task_guide_read`, its
  graph/schema consumers and direct PostgreSQL refusal/acceptance proof.
- The Go guide-declaration client and current CLI/API documentation for
  `text/markdown`. The merged PILOT-13 task guide DTO/extension/download consumers,
  their real upload/read fixtures and direct tests are reconciled without copying
  its implementation.
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
  implementation. No compatibility variant, data rewrite, downgrade,
  deployment, merge or issue closure.

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

- [x] Public API and Go CLI declaration accept exactly `text/markdown`; HTML,
  `text/plain`, binary/malformed UTF-8 and media-type substitution remain denied.
- [x] Real PostgreSQL/MinIO intake stores and reads back the exact Markdown
  bytes with the server-computed SHA-256, byte count and declared media type.
- [x] The existing setup-agent workspace opens the exact `.md` version through
  its run-scoped grant and retains disabled network, bounded resources and cleanup.
- [x] Review-packet metadata and PostgreSQL accept the exact Markdown member
  while direct writes of unsupported media types still fail.
- [x] An assigned contributor lists and downloads the
  task-locked Markdown original byte-identically through REST/CLI; foreign,
  unassigned, corrupt and unsafe-destination cases retain their existing denial.
- [x] PDF, DOCX and PPTX declaration/upload/setup/review/contributor behavior
  remains covered and unchanged; no second migration head is introduced.
- [x] Current API/CLI, artifact/guide specifications and roadmap state the
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
| Bounded Markdown classification | Focused format/API/review-packet/setup batch plus Ruff | 126 passed; strict streaming UTF-8, binary substitution and HTML/plain-text negatives passed | Markdown semantics are not parsed or rendered |
| Durable original custody | Isolated PostgreSQL 16/MinIO intake journey with provider readback, replay and recovery | Both journey variants passed; runner verified database and MinIO cleanup | Hosted S3 remains shared ART-provider evidence |
| Setup-agent exact read | Workspace/runtime batch with Markdown version, byte-bearing grant and disabled network | Exact `.md` bytes, media type, run handle and cleanup passed | No live model inference is required for byte-access proof |
| Persisted review metadata | PostgreSQL 16 predecessor/head direct-write and schema-fingerprint proofs | Predecessor rejected Markdown; 0027 admitted it past the media check; HTML remained rejected; graph and regenerated fingerprint passed | Existing rows are retained; no downgrade is supported |
| Contributor REST/CLI | Real PostgreSQL/MinIO locked-read batch and built-CLI HTTP/public-API journeys | Six backend cases, 34 HTTP cases and the real built-CLI API journey passed, including concealment, successor locking, corrupt originals and `.md` publication | Deployment remains outside this change |

## Review findings

- Real PostgreSQL/MinIO replay exposed a PDF-specific alternate-key fixture;
  the control now reuses each declared media type while preserving conflict proof.
- The merged PILOT-13 policy setup fixture assumed every already-committed source
  was PDF. It now accepts an existing ingest only when its media matches the
  snapshot item, while its synthetic fallback remains PDF-only.
- FastAPI correctly appends the UTF-8 charset parameter to a Markdown response;
  the REST test compares its parsed base media type while the CLI independently
  parses and requires the advertised `text/markdown` type.
- Hosted boundary validation found that the MinIO intake proof had grown past
  the frozen 120-line test limit. A focused helper now performs only the stored
  original lookup; every replica and byte assertion remains in the same primary
  test node, which falls below the hard limit and adds no structural-debt entry.
- The CLI public-contract formatter found the Markdown download journey was not
  in canonical Ruff form. The focused integration source is now formatted and
  remains covered by the built-CLI HTTP journey.

## Reconciliation

- Current-source reconciliation: Merged main
  `36e8a615f01801cecd6ccf83d7411235ab1cfa8f`, where PILOT-13 is delivered as
  revision `0026_task_guide_read`. The later PILOT-00 experiment and delivery
  changes add no migration, so this branch retains the next linear revision,
  `0027_markdown_guide_media`.
- Delivered dependency reconciliation: PILOT-13's exact task-locked authority,
  concealment, verified streaming and safe CLI publication are unchanged; only
  its closed media type and extension maps admit Markdown.
- Remaining risks: Live provider/model inference is outside this byte-custody
  change. Hosted deployment and HTML/docs-site ingestion remain unsupported.
