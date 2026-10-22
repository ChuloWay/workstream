# Manager-authored guide runtime — provider-free guide compilation

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: A second registered guide-compilation runtime, `manager_authored`, converts one manager-uploaded rules document into the existing untrusted compilation result with no inference, no network call and no provider resources, recorded as provider/API/model `none`.

## Intent

Project setup could compile a guide only through the OpenAI Agents SDK runtime,
so a project could not be set up without an OpenAI key, and teams using other
providers, local models or deterministic generators could not supply rules
(#641). Running the PILOT-04 public journey probe locally (#635) showed that the
rest of the guide → task → submission → acceptance journey needs no hosted
inference. This change makes pre-written rules a supported, explicitly
recorded option while every downstream check stays unchanged.

## Current behavior

- `backend/app/adapters/project_agents/__init__.py` registers only
  `openai_agents_sdk` in the typed `ExternalServiceAdapterFactory`.
- `ProjectGuideRuntimeConfiguration` and `Settings` pin `model_provider` to
  `Literal["openai"]` and `model_api` to `Literal["responses"]`.
- `guard_project_guide_runtime_configuration()` (baseline
  `v01_schema.sql`) rejects any stored configuration whose provider is not
  `openai` or whose API is not `responses`.
- Document-read evidence (`project_guide_document_accesses`) requires a
  non-null `attachment_allocation_id`; `guard_guide_document_access()` requires
  an allocated container → file → attachment chain, and
  `require_compilation_document_access()` walks it. A runtime that stages no
  provider files therefore cannot record a read, and without reads a ready
  result is refused (`guard_compilation_document_evidence()` and the Python
  check both require every assigned document to be opened and cited).
- Invalid output is terminal only when the runtime raises
  `ProjectGuideCompilationInvalidOutputError`; any other exception from
  `compile_project_guide` leaves the attempt provider-uncertain
  (`orchestrator.py`).

## Bounded change

### Allowed

- `backend/app/adapters/project_agents/manager_authored.py` (new) and its
  registration in `backend/app/adapters/project_agents/__init__.py`.
- `backend/app/interfaces/project_guide_runtime.py` and
  `backend/app/core/config.py`: admit `none` and enforce the runtime/provider
  pairing with one shared validator.
- `backend/app/interfaces/project_agents.py`: move the existing invalid-output
  classifier from the OpenAI adapter to the shared port so both runtimes use one
  rule (renamed `invalid_compilation_failure_code`; no behavior change).
- `GuideRuntimeResourceCustody.record_direct_document_open`, its SQLAlchemy
  implementation, nullable `ProjectGuideDocumentAccess.attachment_allocation_id`
  and the provider-free branch of `require_compilation_document_access`.
- Migration `0056_manager_authored_runtime`: replace three guard predicates and
  drop `NOT NULL` from `project_guide_document_accesses.attachment_allocation_id`;
  register the head in `alembic/env.py` and `tests/test_alembic.py`; refresh the
  test schema fingerprint in `tests/conftest.py`.
- Migration `0056_manager_authored_runtime` also lets a provider-free attempt
  return from `compilation_provider_uncertain` to `compilation_reserved`
  (`guard_project_guide_compilation_attempt_update()`), and refuses model
  `none` for hosted runtimes. The orchestrator, service and repository gain
  the matching `release_provider_free` path.
- Proposal correction refuses a manager-authored predecessor with the new
  `correction_unsupported` code.
- Behavior-ownership partition registration of the new adapter target.
- Focused tests, README, operations manual, `.env.example` and roadmap updates.

### Not allowed

- No change to compilation validation, proposal review, PRE/POST approval,
  finalization or activation. Correction changes only by refusing
  manager-authored proposals.
- No new admitted guide media type, upload path or manifest field.
- No relaxation of OpenAI validation, credentials, retry/circuit behavior or
  provider-resource custody for the hosted runtime.
- No fabricated provider identifiers and no provider allocation for a
  provider-free attempt.
- No other providers (Anthropic, OpenRouter, local models) inside Workstream;
  they can produce rules outside it.

## Design and decisions

**Runtime.** `ManagerAuthoredProjectGuideRuntime` is constructed only for
`runtime_key == "manager_authored"` with provider `none`. `admit_execution`
records a single admission and consults no model circuit; `aclose` releases
nothing; `cleanup_resources` reports clean only when custody holds no provider
resource. `compile_project_guide` opens every manifest document once, in source
order, through `capabilities.documents.open` (the ART grant authorizes and
checksum-verifies bytes), checks the yielded version, and records the read. The
whole read is bounded by the configured run timeout. Read or custody failures
raise a sanitized `ProjectAgentRuntimeError` (the existing provider-uncertain
path); rules problems raise `ProjectGuideCompilationInvalidOutputError` with
`schema_invalid`, or `unsafe_text` when the shared safe-text validator proves
it. Exceptions are raised outside handlers so no frame retains document bytes.

**Identifying the rules document.** The rule is content-based: exactly one
`text/markdown` original whose complete UTF-8 body (at most 4 MiB, the result
storage limit) is a JSON object with `"format": "workstream.project_guide_rules.v1"`.
An exact filename is impossible because the manifest deliberately carries only
generated names (`<source_item_id>.<ext>`), never source labels; a JSON media
type would widen ingress (format detector, review-packet constraint, upload
schema) for this one feature. Managers are told to label the upload
`workstream-rules.json`. A Markdown guide that is not such JSON is simply read
and recorded.

**Rules shape and evidence.** The object holds `format` plus exactly the eight
author-owned result fields; the runtime adds `agent_name`, the context's
`agent_version` and `schema_version`, then applies the unchanged
`require_complete_…`, `validate_project_guide_compilation_result` and the same
"ready cites every assigned document" rule as the hosted runtime. Author
evidence references name a document by `sha256:` digest or manifest filename and
must resolve to exactly one document. Because the rules document is itself an
assigned original that a ready result must cite, and it cannot contain its own
digest, the runtime appends a reference to the rules document on every finding,
requirement and suggestion. That attribution is true provenance — each item is
stated there — and it is the only evidence the runtime adds. Authors therefore
have at most 19 references per item.

**Custody without provider resources (minimal extension).** The hosted
runtime's read evidence is anchored to a provider attachment. Rather than
inventing `cntr_`/`file-`/`cfile_` identifiers, a provider-free attempt records
a read with a null `attachment_allocation_id` through a separate, explicit
`record_direct_document_open`. Both layers bind this to the attempt's stored
provider:

- Python custody refuses direct reads unless the locked attempt's provider is
  `none`, and refuses `begin_allocation` and staged `record_document_open` when
  it is.
- `guard_guide_document_access()` accepts a null attachment only for a provider
  `none` attempt, and then requires the canonical run-scoped handle and that the
  source item belongs to the attempt's snapshot with the exact ingest and
  SHA-256. Non-null attachments keep the full existing chain.
- `guard_guide_runtime_allocation()` refuses every allocation for a provider
  `none` attempt.
- `require_compilation_document_access()` reads the attempt's provider:
  provider-free rows must have no attachment, hosted rows must have the full
  file lineage.

The ready/citation guard on attempts is unchanged and still proves that every
document was read and cited.

**Configuration and provenance.** `require_project_guide_runtime_pairing` is
the single rule used by `ProjectGuideRuntimeConfiguration` and `Settings`:
`manager_authored` requires provider, API and model `none`; every other runtime
requires `openai`/`responses`. The trigger enforces the same pairing
null-safely, independent of Python. The default remains
`openai_agents_sdk`/`openai`/`responses`. Requiring model `none` keeps the
stored snapshot from naming a model that never ran. Instruction and limit
fields are still recorded (the schema requires them) but unused.

**Model circuit.** `provider_resilience.ModelCircuitAdmission` is constructed
only by the OpenAI adapter; the new runtime never touches it, so a rules
failure cannot open or consume the provider circuit.

Rejected: synthesizing an evidence reference only on the first item (arbitrary
and order-dependent); reading only Markdown originals (would leave PDFs
unrecorded and fail the ready guard); a generic "provider-free" flag on the
configuration (a second source of truth beside `model_provider`).

## Acceptance criteria

- [x] `manager_authored` is registered, constructs without `OPENAI_API_KEY`,
      makes no socket connection and never constructs the OpenAI runtime.
- [x] A guide with a valid rules document compiles through the live worker to
      `policy_draft_ready`; every original has a read record with no attachment
      and the attempt has no provider allocations.
- [x] A malformed, missing, duplicated or unresolvable rules document ends the
      attempt as `compilation_invalid_terminal`/`schema_invalid` (or
      `unsafe_text`).
- [x] Settings, the configuration snapshot and the database trigger each accept
      `none` only with `manager_authored` and reject every mixed pair; OpenAI
      remains the default and keeps strict validation.
- [x] The stored attempt configuration shows `manager_authored`/`none`.
- [x] The database refuses provider allocations for a provider-free attempt,
      direct reads for a hosted attempt, and direct reads of a foreign or
      mismatched original.
- [x] README, operations manual (with a sample `workstream-rules.json`),
      `.env.example` and roadmap describe the runtime.

## Risk and review routing

- Risk class: `L1` (new schema predicates on custody evidence and a new
  untrusted-input path; no authorization or payment change).
- Required reviewers: `security`, `architecture`, `qa`.
- Human review focus: the content-based identification rule; the runtime adding
  a rules-document citation to every item; null-attachment read evidence as the
  custody extension; requiring model `none`.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Runtime conversion, rejection codes, no credentials or network | `tests/test_agent_runtime.py` (manager-authored tests) | Pass | Socket patching proves no connection attempt in-process only |
| Settings/snapshot pairing | `tests/test_agent_runtime.py`, `tests/test_config.py` | Pass | — |
| Composition constructs only the selected runtime | `tests/test_external_service_adapters.py`, `tests/projects/guide_compilation/test_live_worker.py` | Pass | — |
| Trigger pairing, null-safe | `tests/projects/guide_compilation/test_runtime_configuration_postgresql.py` | Pass on PostgreSQL 16 | — |
| Direct-read custody and allocation refusal | `tests/projects/guide_compilation/test_document_file_custody_postgresql.py` | Pass on PostgreSQL 16 | — |
| Live worker ready and malformed outcomes | `tests/projects/guide_compilation/test_live_cutover_postgresql.py::test_manager_authored_rules_compile_through_the_live_worker_without_inference` | Pass | Document bytes come from a scripted grant; real ART/S3 reads are proved separately |
| Migration graph, fingerprint, predecessor upgrade | `tests/test_alembic.py`; 0055 fingerprint reproduced locally before refresh | Pass | — |
| Documented sample compiles | Ad hoc run of the operations-manual sample through the runtime | `draft_ready` | Not a committed test |

## Review findings

Focused security, architecture (with reuse) and QA/test-delta reviews ran on
candidate `7f42f7682`; no blocking finding. Dispositions:

- Security SEC-MAR-01 (should-fix): deeply nested rules JSON raised
  `RecursionError`, which escaped as a runtime failure and left the attempt
  provider-uncertain. Fixed: parse failures including `RecursionError` make the
  original a non-candidate, so the attempt ends `schema_invalid`; covered by a
  200,000-level nesting test.
- Security SEC-MAR-02 (nit): the allocation refusal compared provider with `=`.
  Fixed to `is not distinct from 'none'`.
- Security SEC-MAR-03 (nit): a direct-read row is not bound to the consumed ART
  read-authorization record. Accepted: the hosted attachment chain is equally
  application-written; binding reads to authorization decisions would be a
  separate custody change for both runtimes.
- Architecture ARCH-1 (should-fix): the rules document is an ordinary guide
  original visible to every locked-guide reader, including contributors.
  Documented in README and the operations manual; hiding it would need a
  manifest change, which is out of scope.
- Architecture ARCH-2 (should-fix): the hosted release still requires the
  OpenAI key file. README, manual and roadmap now scope "no key" to the native
  workflow; a conditional hosted secret is a possible follow-up.
- Architecture DEDUP-1/DEDUP-2/NIT-3: the ready-coverage rule is now one shared
  `require_ready_result_cites_every_document` used by both runtimes; the
  provider-free value is one constant `PROVIDER_FREE`; the custody lock flag is
  renamed `in_flight`.
- Architecture NIT-4: a transient read failure left a provider-free attempt
  provider-uncertain. Superseded by Codex P1 below: the attempt now reopens.
- QA-01/QA-02 (medium): the duplicate-rules and unresolvable-reference tests
  failed only through the citation rule. Added cases where every document is
  cited; re-ran both mutations (exactly-one guard removed; unresolvable
  references dropped) and each new test now fails under its mutation.
- QA-03 (low): the Python null-attachment branch of
  `require_compilation_document_access` has no independent test because the
  database guard refuses such rows first. Accepted as defense in depth.
- QA-04 (low): added tests for an oversized Markdown candidate, rules JSON under
  a non-Markdown media type, and a substituted document version. Timeout and
  cancellation reuse the hosted runtime's pattern and remain untested here.
- Replay on `b92e71363`: security, architecture and QA passed. QA-05 (low): the
  duplicate case only caught a "first candidate wins" regression; both rules
  documents now cite each other. The oversized-candidate test cannot isolate
  the byte-limit check, which is redundant behind the bounded read; accepted.
  Security noted, unverified, that lone-surrogate escapes in prose might fail
  the evidence guard's `jsonb` cast and leave the attempt provider-uncertain;
  the hosted runtime shares this pre-existing exposure.
- Codex review on PR #643 (four findings, all fixed):
  - P1, keep provider-free failures retryable: any non-invalid runtime failure
    after the fence left the attempt provider-uncertain, which recovery treats
    as terminal, so the guide was stranded although no provider call existed.
    Fixed: for a provider-free attempt the orchestrator releases the fence back
    to `compilation_reserved` and raises `runtime_unavailable`, the same
    retryable outcome as a pre-fence failure. The attempt-update guard allows
    this one transition only when the stored provider is `none`. Tests: a
    provider-free transient failure reopens and the retry reaches a terminal
    outcome; a hosted attempt cannot be released through the repository or
    by direct SQL.
  - P1, corrections were silently ignored: a successor recompiled the same
    rules and dropped the manager's reason. Fixed: correction requests on a
    manager-authored proposal are refused with `correction_unsupported` before
    authority is consumed, and the runtime refuses any context carrying
    correction feedback as `schema_invalid` without reading documents.
  - P2, unbounded retention of duplicate rules: every parsed candidate was kept
    until compilation rejected duplicates (up to 100 × 4 MiB of JSON). Fixed:
    only the first candidate keeps its parsed body; later ones are kept as
    `None`, which is enough to reject.
  - P2, hosted runtime with model `none`: the Python pairing and the SQL
    configuration guard accepted `openai`/`responses` with model `none`.
    Fixed in both; covered by the Python and SQL pairing tests.
  - Verification: 324 + 3 new unit tests, 121 PostgreSQL tests (guide
    compilation orchestrator, runtime configuration, document custody,
    Alembic), Ruff, architecture tests and the module, AUTH, test-structure and
    behavior-ownership validators pass. Schema fingerprint refreshed.
- Second review round on PR #643 (Codex and CodeRabbit, four findings, all
  fixed):
  - Codex P1, cancellation stranded the attempt: `CancelledError` bypassed the
    release. The orchestrator now releases a provider-free fence (shielded)
    before re-raising cancellation.
  - CodeRabbit, crashed workers stranded the attempt: recovery returned every
    uncertain attempt as terminal. A provider-free fence older than
    `timeout_seconds + cleanup_timeout_seconds` is now released during recovery
    and dispatch continues; a younger one is left alone so a run still in
    flight elsewhere is not duplicated. Setup continuation no longer treats a
    provider-free uncertain attempt as terminal, so redelivery reaches recovery.
  - CodeRabbit, retries could violate `uq_guide_document_access`: a retried run
    rereads documents the failed run recorded. `record_direct_document_open`
    now returns when the same document is already recorded for the attempt and
    refuses a different handle for it.
  - Codex P2, hosted prompt limit applied to provider-free runs: the
    orchestrator now applies `maximum_manifest_bytes` only to hosted runtimes.
  - Tests: cancellation reopens the attempt; recovery leaves a fresh fence and
    reopens a stale one; a repeated read records one row; a provider-free run
    with a 1,024-byte limit and a larger context still runs.
- Coordination: PR #633 also adds `0056`; whichever merges second renumbers its
  migration and refreshes `alembic/env.py`, `tests/test_alembic.py` and the
  schema fingerprint.

## Reconciliation

- Current-source reconciliation: based on `main` at `c6d916cc1`. Open PR #633
  also adds a `0056` migration; whichever merges second must renumber and
  refresh the schema fingerprint and `alembic/env.py`.
- Next usable boundary: None.
- Remaining risks: a manager-authored result is only as good as its author;
  it passes the same validation and still requires the manager's proposal
  review and approvals.
