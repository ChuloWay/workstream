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
ArtifactStore provider boundary and immutable source snapshot. Keep ingress
permission, declared/observed size bounds, format allowlist and content checksum
computed during upload. Store the source once and record its exact committed
object identity. No mandatory post-upload download/classification/extraction.

Guide storage completion has an explicit document-stored outcome. It must not
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

ART owns a typed run-scoped document byte capability, composed by the worker.
It is constructed from persisted run identity and the committed manifest after
the existing execute fence. Each open resolves an opaque handle in that grant,
checks exact ownership/version/current authority and streams only the resolved
object through ArtifactStore. No caller-supplied bucket/key/URL is accepted.
Closure/cancellation/expiry invalidates the grant; a new run cannot reuse it.
Any local temporary staging uses ArtifactScratchManager with aggregate bounds.

### 3. Runtime workspace and configuration

Keep ADR 0014's typed ProjectGuideAgentRuntime factory and separate immutable
runtime/model/instruction configuration. First implementation candidate is the
existing OpenAI SDK with a dedicated hosted Code Interpreter container. This
uses existing supported DOCX/PDF/PPTX inspection rather than rebuilding a
Workstream extraction pipeline. Before committing this choice, prove the pinned
SDK/provider supports the required container isolation and document controls.

The trusted adapter uploads only separately granted documents, uses generated
source-item filenames, creates a fresh explicit container, disables its network,
and supplies exactly that run's provider file IDs. No automatic container reuse,
shared conversation, File Search/vector store, MCP, S3 credentials or general
storage API is exposed. Code Interpreter operates only on staged files and its
own temporary notes. A later Deep Agents adapter can consume the same document
and output ports; no speculative second adapter is installed now.

Expose immutable limits for file count/bytes, model turns, wall time, tool work,
context compaction and temporary workspace lifetime. Use supported SDK/provider
context controls inside the single run, not just between user conversations.
Reject unsupported provider/API/tool combinations before execution; do not
silently downgrade to one-shot inference. Model and instructions remain explicit
in .env.example and independently configurable.

File/container staging has explicit cleanup on success, invalid output, timeout
and cancellation, plus provider expiry for process loss. Record content-free
cleanup custody where required to retry cleanup without rerunning inference.
Provider creation/cleanup uncertainty must not accidentally create an additional
agent run. Do not treat a cleanup attempt as authorization to delete S3 originals.

### 4. Result, evidence and projections

Preserve one complete structured result, distinct pre/post proposals, canonical
catalogue validation and the manager approval pause. Replace extraction-based
source references with exact document/source-version references. Storage access
receipts prove the files made available to the run; model-authored page/section
references remain untrusted proposal evidence, not independent proof of semantic
correctness. Do not claim a retrieved hit proves full-guide comprehension.

Bind the immutable manifest and content-free run file-access evidence into
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
   provider I/O; expired/closed grants and traversal attempts cannot read bytes.
4. Real SDK tool configuration admits only a fresh container with the assigned
   files and disabled network. Cleanup and cancellation tests cover every
   allocated resource, including partial staging/provider uncertainty.
5. A scripted multi-turn SDK run reads multiple documents, preserves working
   notes through within-run context reduction and returns the canonical result.
   A one-shot/max-turn-one mutant fails that test; valid controls still pass.
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
