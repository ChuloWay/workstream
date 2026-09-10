# POL-04B — Agent-driven unified guide setup

- Initiative: WS-POL-003
- Durable disposition: Planned
- Risk: L1
- Intended merge outcome: authorized document upload to private artifact storage
  starts one isolated agent investigation, ending at findings and separate draft
  pre/post policies. This replaces the earlier extraction-dependent, single-prompt
  implementation in the same unmerged change.

## Intent

The project manager uploads DOCX/PDF guide documents; PowerPoint is included only
through a tested reader (PPTX first, no unsupported binary PPT claim). Standalone
image/audio/spreadsheet/text-source expansion is outside this change. S3 stores
original immutable files; PostgreSQL stores metadata, versions, operation custody
and validated findings/policy proposals, not extracted document bodies.

After successful upload and metadata commit, one asynchronous setup job receives
the exact guide manifest. The agent chooses which granted documents to inspect,
uses document tools and an isolated workspace, keeps notes, manages context and
produces one complete proposal. One job may contain many model/tool calls.
Duplicate delivery must not start another agent run. Insufficient/unreadable
material ends with an explicit outcome. Ready proposals wait for manager review,
correction and approval. POL-05 owns manager surfaces and fresh manual reruns.

Every file access is restricted to an explicitly assigned source-item version
within the exact project/guide/snapshot/generation/run. Metadata or tool arguments
cannot widen that scope. No S3 credentials, bucket browsing, arbitrary keys,
provider URLs or access to another run's workspace reach the model.

The creator explicitly authorized replacing the old affected implementation in
this PR, including obsolete tests. No compatibility aliases, old/new runtime
variants, extraction fallback, or separate cleanup prerequisite is permitted.
Retained records are not authorized for deletion.

## Current-source findings

Base is `c69ff853`. ART currently stores originals through ArtifactStore, then
requires verification, binding, classification and extraction before setup.
`guide_sufficiency_material.py` loads canonical PostgreSQL text rows for all
sources; `projects/service.py` and `guide_compilation/context.py` flatten them
into a 12 MiB snapshot. The adapter sends that entire snapshot, has no tools and
limits execution to one model turn. These are the superseded paths.

The dependency extends into sufficiency projection provenance, submission-policy
mutation validation, setup continuation and authorization resource facts. Merely
changing the SDK adapter or placing tools over the PostgreSQL text aggregate
would leave the wrong design operational. Current source evidence references
extraction usage; the new contract must bind original document versions instead.

## Bounded implementation plan

### 1. Document upload and readiness

Reuse the existing authorized guide upload route, committed-source preparation,
ArtifactStore provider boundary and immutable source snapshot. New snapshot items use only `source_kind=document`,
`ingestion_adapter=upload` and required PDF/DOCX/PPTX media types. Keep ingress
permission, declared/observed size bounds and checksum computed during upload.
Reuse GuideFormatDetector and existing OOXML/ZIP safety against prepared bytes
before admission; require actual type to match the persisted declaration, reject
macro/binary-PPT substitutions, and never use request headers as format authority. Store the source once and record its exact committed
object identity. No mandatory post-upload download/classification/extraction.

A new setup run starts `awaiting_documents`. Guide `object_confirmed` has an
explicit `document_stored` receipt outcome and zero verification jobs. The final
exact upload atomically claims `dispatch_pending`; queued/eager worker handling
keeps the existing deterministic task identity. Concurrent, out-of-order and
replayed uploads must publish at most that one logical task. Late storage
completion for a stale snapshot may remain retained evidence, but cannot dispatch
or satisfy the latest run. This guide-specific exception updates ADR 0013 and
the ART specification in this change. It must not
mark a shared artifact replica verified or mint a fake verification receipt.
Submission/checker artifact verification remains unchanged, including when bytes
are shared with a guide. Readiness requires every assigned item in the manifest
to have a successful same-owner committed upload. Queue publication occurs only
after commit; existing bounded continuation scans recover missed publication.
Replace the guide continuation's verification-job dependency with upload/run
identity. Unresolved upload outcomes remain unavailable rather than guessed.

### 2. Manifest and run-scoped file access

Replace GuideSufficiencyMaterialPort and its extracted-content aggregate with a
metadata-only guide document manifest capability. It returns project, guide,
snapshot/generation, ordered source-item IDs, source checksum/size/media type,
and exact committed storage identity for server use. The model-facing projection
contains opaque document handles and safe generated names; it excludes storage
coordinates. Manifest hashing is deterministic and contains no document body.

`app.adapters.artifacts` constructs the ART-owned typed document byte grant
using the existing store/scratch roots; `app.adapters.projects` injects its
public port into the coordinator. `app.workers.project_setup` remains a thin
public-composition consumer. Reuse fixed ARTIFACT_GUIDE_READER and
artifact.guide_source.read; do not add a reader identity/action. Replace old
verification facts with attempt/manifest, exact item/ingest/put/replica, project,
guide/snapshot/generation, namespace, checksum, size and media facts.
The manifest is bound before the fence; the runtime receives its already-fenced
opaque grant. Losing/replayed deliveries perform zero OpenAI I/O. Each open resolves an opaque handle in that grant,
checks exact ownership/version/current authority and streams only the resolved
object through ArtifactStore. No caller-supplied bucket/key/URL is accepted.
Before any provider file upload, each requested object is fully staged into
bounded scratch and its checksum/size matched to the committed document receipt.
No corrupt bytes are streamed onwards before that check; this read does not mark
the shared replica verified. Closure/cancellation/expiry invalidates the grant;
a new run cannot reuse it. Fixed-service/source denial at tool time aborts the
run, rather than becoming recoverable tool text. Original PM consent retains
POL-04B1 semantics; later PM role changes are not retroactive consent withdrawal.
Any local temporary staging uses ArtifactScratchManager with aggregate bounds.

### 3. Runtime workspace and configuration

Keep ADR 0014's typed ProjectGuideAgentRuntime factory and separate immutable
runtime/model/instruction configuration. The sole current implementation is the existing OpenAI SDK with a dedicated
hosted Code Interpreter container. This
uses existing supported DOCX/PDF/PPTX inspection rather than rebuilding a
Workstream extraction pipeline. Prove the pinned SDK/provider supports the required container isolation and
document controls before implementing the wider cutover. If that probe fails,
revise the plan rather than shipping an unsupported or fallback path.

After winning the fence, the trusted adapter creates a fresh explicit empty
container with network_policy disabled. Its local `open_guide_document(handle)`
tool resolves one authorized source, verifies its staged bytes, uploads it with
purpose=user_data and bounded expiry, records the provider ID, and attaches it
to that exact container. Filenames are generated from source-item UUID plus
trusted extension. The returned model-facing value contains its workspace path
and source-version reference, never an S3 coordinate or provider-file selector.
Set parallel_tool_calls=False and serialize duplicate opens with a bounded
per-handle lock. Repeated opens validate the grant but stage the same document
at most once. Known ART denial, missing/corrupt bytes or stale authority aborts
Runner with no subsequent model turn and no retry; SDK tool-error formatting
must not convert these failures to recoverable text. After an initial model
call, conservative provider-uncertain classification remains explicit.
No automatic container reuse, shared conversation, previous-response reuse,
File Search/vector store, MCP, S3 credentials or general storage API is exposed.
Only explicitly opened assigned files are mounted. Code Interpreter supplies
inspection and temporary notes; its output is not saved as source content.

OpenAI + Responses + hosted Code Interpreter is the sole current adapter
combination. Reject/remove the unmerged chat-completions and openai-compatible
execution branches; another adapter can implement an explicitly supported
provider later. Set ModelSettings(store=False) on all Responses requests and
use input-based, non-stored compaction when applicable. Provider Files and
containers still have application-state retention: deletion/expiry are cleanup
controls, not a claim of immediate erasure or zero-data-retention. No transcript,
raw tool output, source bytes or notes go into PostgreSQL or application logs.

Expose immutable limits for file count/bytes, model turns, wall time, tool work,
context compaction and temporary workspace lifetime. Use supported SDK/provider
context controls inside the single run, not just between user conversations.
Reject unsupported provider/API/tool combinations before execution; do not
silently downgrade to one-shot inference. Model and instructions remain explicit
in .env.example and independently configurable.

Provider resource custody is mandatory and owned by the compilation attempt.
Persist each allocation operation and each returned file/container ID with its
exact manifest mapping, state, cleanup deadline and runtime identity. Use a
public typed custody port composed through PROJECTS, not direct ORM imports in
the SDK adapter. The allocation capability is issued by the winning fence and
cannot record another attempt's resources. Cleanup authority is limited to those
allocated resources and remains usable after project/source access is revoked.

On exit perform bounded cancellation-shielded container-first then uploaded-file
deletion. An exact-ID cleanup reconciler retries recorded resources without
listing the OpenAI project's Files or Containers. Set bounded file/container
expiry at creation for process loss and unknown-create windows. Unknown
allocation is recorded as uncertain; it cannot be guessed successful, rediscovered
by global listing or retried as another agent run. Cleanup failure must not erase
a known valid/invalid result, change its classification or clear provider
uncertainty. Never persist generated container files or delete S3 originals as
part of this cleanup. All OpenAI creation/upload/model operations occur after
the fence; unknown staging/model outcomes remain provider-uncertain.

### 4. Result, evidence and projections

Preserve one complete structured result, distinct pre/post proposals, canonical
catalogue validation and the manager approval pause. Replace extraction-based
source references with exact document/source-version references. Storage access
receipts prove the files made available to the run; model-authored page/section
references remain untrusted proposal evidence, not independent proof of semantic
correctness. Do not claim a retrieved hit proves full-guide comprehension.

Require at least one successful document-open receipt before accepting a
compilation, and require every cited source to belong to the manifest and opened
set. Ready output must account for every assigned document; unavailable/unread
material cannot silently disappear from the findings. Bind the immutable
manifest and content-free run file-access evidence into
accepted-result custody and downstream projection checks. Adapt current
sufficiency/report and submission-policy provenance consumers together. Keep
fresh action-bound projection authority, locked lineage, atomic acceptance,
immutable finalization and current-authority replay. Unknown runtime outcomes
remain unresolved; recovery may not launch an uncontrolled second run.

### 5. Remove superseded affected paths

Remove mandatory guide format/extraction orchestration, whole-guide prompt
assembly, their active composition and obsolete execution tests. Trace shared
consumers before deleting parser helpers. Preserve submission ZIP processing,
required artifact scratch protections and immutable historical evidence. If old
extraction tables/rows are retained for references, make that retention explicit;
there must be no live fallback reader or new writes preserving the old flow.
Use a reviewed migration for current contracts, without fabricated backfills or
deletion of retained source/evidence data. Update schema/ORM/API parity together.

## Canonical metadata and retained-data disposition

The sole document-version source is GuideSourceSnapshotItem +
GuideSourceArtifactIngest + its exact object_confirmed ArtifactPutAttempt +
ArtifactReplica, with receipt, checksum, size and media. Do not create a second
corpus/document-version table. Add only attempt-bound provider allocation,
access and cleanup custody. Projection `_add_source_usages`, current report
validation/source refs, submission-policy mutation, AUTH material facts and
finalizer checks all switch together to this manifest/access owner.

Keep prior extraction/binding/content/usage rows and their necessary ORM metadata
read-only; new execution/reports/derivation/activation never consume them.
Retained extraction-backed reports are not eligible for new actions. Existing
locked task/policy facts remain intact; no fallback or fabricated backfill makes
old reports eligible. Guard retained tables against new writes after cutover.

Remove content_markdown from current guide create/update/response, assignments,
source/hash logic and docs. PATCH remains for bounded change_summary metadata
only. Rename the physical column to retained_content_markdown, preserving values,
make it nullable, retain only the same-name nullable ORM retention mapping, and
add database guards: new INSERT requires NULL and UPDATE cannot change it.
There is no current API/read/inference path or empty-string fallback for it.
Migration tests prove preservation and rejection of new writes/direct SQL edits.

## Test replacement map and precise guard boundaries

Replace guide setup/extraction material tests in test_guide_setup.py and
relevant test_guide_bindings.py sections. Retain/adapt test_guide_artifacts.py
PREP/admission/lineage/replay/concurrency, provider ownership and scratch cleanup,
plus submission verification coverage. Delete extractor-specific PDF/DOCX/PPTX
and general extraction tests only with their production consumers. Supported
format proof becomes actual ingress fixtures plus opt-in hosted read fixtures.
Automatic request/context/projection fixtures use committed-document/access
lineage. Preserve eager dispatch_pending/queued delivery, crash and replay tests.

Initial preflight rejects an invalid manifest before any OpenAI request. A forged
model-called handle is rejected before S3/scratch/provider staging for that call;
it does not erase the earlier model/container activity. Same-size corruption,
truncation or missing bytes discovered during an authorized open cause zero
provider-file creation for those bytes and no subsequent model continuation,
while exact cleanup calls remain permitted. Direct capability and whole-runtime
probes report these different boundaries honestly.

Use two valid projects/runs/generations and same-content items, mutate one
selector at a time, and test namespace/ref/hash/size drift separately from
permission. Same content/replica never grants another item's access. The live
isolation probe leaves an unrelated provider File in the same OpenAI project,
tries a foreign-ID substitution at the trusted staging boundary, lists only the
run's explicit container to verify its assigned file set, and tests actual
outbound network denial and absent OpenAI/S3 credentials. Clean up probe-owned
foreign fixtures too. Stage crashes, partial uploads, allocation-before-receipt,
delete failures and cancellation must preserve exact cleanup/replay custody.

Scripted SDK/model tests prove tool/config serialization, multiple turns, limits,
ephemeral state and compaction wiring. Only the paid probe establishes actual
hosted file inspection, note use and within-run compaction. Required fixtures are
DOCX + PDF, and PPTX before advertising it; no 429 or mocked tool execution is
reported as successful live-agent proof.

## Allowed files and boundaries

- `backend/app/interfaces/project_agents.py`, `project_guide_runtime.py`,
  `artifact_operations.py` and a focused guide-document port module if needed.
- `backend/app/adapters/project_agents/`, affected artifact composition and
  `backend/app/core/project_agents.py`, `project_guide_instructions.py`, config.
- Guide-only ART source/binding/materialization/extraction/preparation paths,
  relevant storage-completion and repository branches, schemas/models and tests.
- PROJECTS guide upload/readiness/queue/worker, guide compilation context,
  orchestration, accepted evidence, projections, report/policy provenance and
  affected authorized mutation/read callers; relevant schema/model definitions.
- Existing AUTH guide-resource/preflight/PREP facts and evaluators solely to
  reconcile exact stored-document lineage. No broader roles/actions/service
  permissions. Add a focused public capability only when owner review requires.
- Required migration, dependency metadata/lock, .env.example, README, canonical
  guide/ART/agent specs, roadmap, affected initiative navigation and local exports.
- Affected focused tests/fixtures, API/MinIO drill and an explicit opt-in live
  agent probe. CI metadata may change only for accurate ownership/selection;
  no reduction in checks, floors, assertions or required test execution.

Prohibited: frontend work; PM approval/rerun APIs belonging to POL-05; automatic
acceptance; checker evaluation; compensation/reputation; changes to submission
verification; unrestricted storage/network tools; parallel runtime paths;
repository-wide cleanup; deletion of retained data; unrelated dependency updates.

## Acceptance and verification

1. Uploading supported files stores originals and metadata only; setup starts
   after all assigned uploads commit, without extraction or verification jobs.
   Unknown/partial upload, stale generation and unauthorized actor controls fail.
2. Shared-source bytes cannot bypass submission verification. Probe guide upload
   followed by submission of the same content as a discriminating control.
3. Two projects and two runs with distinct sentinel files prove exact-file
   isolation: foreign/forged/stale handles and key/URL substitution fail before
   the attempted file read or provider staging; expired/closed grants and traversal attempts cannot read bytes.
4. Real SDK tool configuration admits only a fresh container with the assigned
   opened assigned files and disabled network. Cleanup and cancellation tests cover every
   allocated resource, including partial staging/provider uncertainty.
5. Scripted SDK/model tests exercise multiple document-open turns, stable
   run/container identity, limits, ephemeral context and compaction request
   serialization. A max-turn-one mutant fails sequencing while valid controls
   pass. Concurrent duplicate opens produce one staged upload/attachment and
   exact cleanup custody. Hosted reads, note use and actual compaction are
   established only by the paid probe in item 8.
6. Actual SDK parser rejection remains sanitized invalid-terminal, including
   redaction on/off and exception traceback custody. PostgreSQL replay proves
   that invalid/uncertain/complete outcomes do not start another agent run.
7. PostgreSQL tests bind manifest/source evidence to accepted results and both
   atomic authorized projections/finalization; substitution and stale authority
   controls must reach the intended guard rather than an earlier invalid shape.
8. Opt-in paid smoke uses the user's ignored .env, real DOCX and PDF with distinct
   content, at least two document inspections and a multi-step investigation.
   Verify structured findings/proposals and persisted replay, source-version
   evidence, workspace isolation and cleanup. Record provider/model/tool usage;
   no key or raw confidential document output in logs. PPTX gets its own fixture
   before support is advertised. Test unreadable/insufficient guides explicitly.
9. Run Ruff, appropriate focused tests and MinIO/API/PG proof, then final hosted
   full lanes/coverage/Agent Gates without skips/deselections. Perform stale
   wording and markdown-link checks; reconcile roadmap/navigation after main.

## Reviews and human focus

Architecture and security review this concrete plan before product edits. QA/
test-delta review the real guard reachability and paid-test design. After shared
checks, freeze a clean candidate and run architecture/reuse, security, QA/
test-delta, product/docs and CI-integrity tracks. Batch repairs and replay only
affected reviews. The size exception is one explicitly authorized cohesive
replacement within the existing unmerged PR, reviewed by owner boundary; it is
not permission for unrelated cleanup or an unbounded new agent platform.

Human focus: exact-file isolation; originals versus temporary data; no extracted
content database; a real tool-using run; correct source-version grounding;
separate draft policies; manager approval pause; no duplicated run on replay.

## References

- [OmniCoreAgent](https://github.com/omnirexflora-labs/omnicoreagent)
- [Deep Agents context management](https://docs.langchain.com/oss/python/deepagents/context-engineering)
- [OpenAI SDK tools](https://openai.github.io/openai-agents-python/tools/)
- [OpenAI file inputs](https://developers.openai.com/api/docs/guides/file-inputs)
- [OpenAI Code Interpreter](https://developers.openai.com/api/docs/guides/tools-code-interpreter)
