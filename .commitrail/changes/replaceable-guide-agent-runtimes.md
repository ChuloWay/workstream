# Replaceable guide-agent runtimes and OpenRouter inference

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Execute the same governed guide-compilation operation through OpenAI Agents SDK or OmniCoreAgent with OpenRouter, without making PROJECTS depend on either runtime's file-storage conventions.

## Intent

The user requires independently replaceable agent runtimes and model providers.
A live OpenRouter credential/model probe succeeded, but the existing runtime
cannot switch: PROJECTS requires OpenAI Responses and OpenAI file attachments.
Add OmniCoreAgent as a real second adapter and exercise both SDKs against the
same document tools and result contract. This is a repair to the current hosted
guide journey, not a general agent platform or an additional product lifecycle.

## Current behavior

`interfaces/project_guide_runtime.py` couples provider-backed execution to
`openai/responses`. `adapters/project_agents/openai_agent_sdk.py` uses OpenAI
containers, Files and Code Interpreter. PROJECTS runtime resource custody and
its SQL guards require their attachment identities as proof of source access.
`manager_authored` separately records direct reads without inference. The SDK
factory exists, but substituting a runtime/provider still changes core rules.

The real retained hosted setup is provider-outcome-unresolved. Neither changing
configuration nor this repair authorizes rerunning, rewriting or deleting that
attempt. Preserve its evidence and separately disposition any retained cleanup
obligation before claiming the hosted journey recovered.

## Bounded change

### Allowed

- `backend/app/interfaces/project_guide_runtime.py`,
  `backend/app/interfaces/project_agents.py`, and a narrowly typed guide-document
  tool port: runtime-independent execution configuration, tool budgets and results.
- `backend/app/adapters/project_agents/`, `backend/app/core/project_agents.py`,
  `backend/app/core/project_guide_instructions.py`, `backend/app/core/config.py`:
  two real SDK adapters, trusted provider selection, common result validation and
  the same bounded document-tool capability; preserve manager-authored behavior.
- PROJECTS `api/guide_documents.py` and `guide_compilation/` affected models,
  custody, composition and validation; ART `guide_document_access.py` and its
  composition only for trusted exact-read evidence. Keep cross-owner ports.
- A fixed document parser service and client under the existing adapter/worker
  conventions, using the release image and a private Unix socket. No generic
  command execution or new network API.
- One linear Alembic migration and affected schema baseline/fingerprints:
  runtime-independent configuration/access invariants and retained-data proof.
- `backend/pyproject.toml`, `backend/uv.lock`, applicable dependency installation
  declarations: pinned published OmniCoreAgent and fixed parser dependencies.
- `docker/backend/`, `deploy/hosted/`, canonical environment example and focused
  deployment tests: worker-only provider credentials and secret-free parser role.
- Focused affected tests, ownership/lane inventories, and current guide/runtime,
  deployment, developer and roadmap documentation. No unrelated inventory edits.

### Not allowed

- Product authorization bypass, different proposal approval or acceptance paths,
  direct repairs to retained product rows, fabricated provider results, or retrying
  an unresolved hosted attempt under another runtime/provider.
- Model-selected URLs, S3 keys, filesystem paths, code, shell commands, parsers,
  credential access, network access from the parser, or Docker access in workers.
- A provider-free label for an inferred run; fake OpenAI resource/attachment facts;
  a new runtime identity merely because the model provider is OpenRouter.
- Speculative Claude adapters, generic plugin discovery, silent model/provider
  fallback, unrelated cleanup, or treating hosted storage retention as unchanged.
- Removing evidence or authorization tests merely because an SDK changes.

## Design and decisions

1. Keep `ProjectGuideAgentRuntime` and its typed factory. Register
   `openai_agents_sdk` and `omnicore_agent` independently of `model_provider`.
   Use OpenRouter with the already-probed `openai/gpt-5.6-terra` for the concrete
   two-runtime qualification. Credentials and provider endpoints stay in trusted
   composition, outside persisted model instructions and result bodies.
2. PROJECTS owns the exact immutable run configuration, source manifest and
   trusted document-access facts. Its rule is that the authorized owner verified
   and exposed that original during that attempt, not that OpenAI attached it.
   Separate "no inference" from "no remotely hosted document resources".
   Preserve all historical access/allocation facts and their hashes; never invent
   a successful parse receipt for an earlier upload. Identify retained cleanup
   dependencies explicitly; no selectable obsolete execution path.
3. Both SDKs receive the same opaque-handle read/search tools. ART rechecks exact
   authority, manifest, checksum and byte count on each source access. Read/search
   results have bounded text, locators, pagination/truncation and exact identity.
   Do not send all guide content up front. Common final validation rejects cited
   unopened sources and mismatched proposals regardless of SDK.
4. Parse only the currently supported PDF, DOCX, PPTX and Markdown formats in a
   fixed secret-free, networkless service, nonroot/read-only with bounded
   memory/CPU/PIDs and per-call deadlines. Stream verified bytes over a private
   Unix socket; no shared source paths or durable extracted-content storage.
   Use closed operations and bounded framing/output; enforce OOXML archive/XML
   limits and malformed/encrypted/oversized PDF denial. No arbitrary execution.
5. Adapters own their native loops, tool wrappers, parsing of model output and
   cleanup. Preserve Workstream turn/tool/time bounds, sanitized errors and
   retry/circuit semantics. Disable SDK autonomous filesystem tools, persistent
   sessions, telemetry capture/export, skills, subagents and remote tools. Verify
   actual offered tools. SDK incompatibility must fail before dispatch where
   detectable; never silently ignore configuration.
6. Pin the published `omnicoreagent==0.6.0` distribution (MIT; Python >=3.12,
   <3.15), not the stale local development checkout. Resolve its Python/dependency
   intersection and inspect its actual API/retry behavior before implementation.
   The current release image uses Python 3.12. No SDK monkeypatch or global
   credential rewriting to implement per-run selection.

## Acceptance criteria

- The two actual SDKs run the same synthetic tool conversation and original-guide
  live qualification through OpenRouter, changing runtime configuration only.
  They need not produce identical prose; both must pass identical Workstream
  schema, source-evidence, capability and policy validation.
- Runtime substitution needs no provider-specific branching in PROJECTS/ART
  business logic or a schema change. Installed-adapter validation remains explicit.
- An unknown/foreign document handle, stale grant, altered bytes, unopened citation,
  injected storage selector, malformed output and exceeded budget are rejected.
- Required document formats support bounded incremental reads/searches with stable
  locators; a large guide is not silently truncated or sent whole to inference.
- Real isolated parser tests cover no network/credential/source mount, malformed
  and resource-exhausting inputs, cancellation, concurrent requests and cleanup.
- PostgreSQL tests preserve retained facts and reject false source lineage; old
  unresolved work is not redispatched. Remove tests for obsolete OpenAI-only
  implementation requirements while retaining their actual safety guarantees.
- Hosted settings expose the current model/provider/runtime and required key
  clearly. No production provider switch or full-journey completion is claimed
  until the reviewed images and actual durable workers pass the hosted drill.

## Risk and review routing

- Risk class: L1 (untrusted documents, runtime dependencies, retained evidence).
- Required reviewers: architecture/reuse and security for the plan; architecture,
  security, QA/test delta, documentation and dependency/deployment CI integrity
  for the implementation, proportionate to their changed boundary.
- Human focus: runtime/provider independence, exact original-document access,
  existing evidence preservation, no hidden telemetry or SDK-generated tools,
  and actual SDK/live execution rather than mock-only interchangeability.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current OpenRouter key/model is usable | Private authenticated model catalogue and one synthetic Responses request | HTTP 200; `openai/gpt-5.6-terra` completed | Does not prove tool loops or document processing |
| Current core is provider-coupled | Runtime configuration, resource custody and SQL inspection | OpenAI-only pairing and attachment requirement confirmed | Correction not implemented |
| OmniCoreAgent API identified | Published 0.6.0 wheel metadata/source and official release page | Async tool registry/run API exists | Retry/privacy controls and dependency installation need qualification |
| Shared behavior | Planned actual-SDK contract suite and PostgreSQL negative/control cases | Not run | New tests must fail on the reproduced coupling/invalid-access cases |
| Deployment and live substitution | Planned secret-free parser isolation and one live guide run per SDK | Not run | No full hosted journey claim |

## Reconciliation

- Current-source reconciliation: based on main `f23fc7187`. PR #651 changes the
  same guide adapter, output specifications, draft review and correction inputs.
  Preserve/reconcile its outcome; do not overwrite that work or call it merged.
- Next usable boundary: real two-runtime guide qualification, then the existing
  project-owned checker and contribution journey drill.
- Remaining risks: no implementation decision may silently weaken SDK retry,
  privacy or source-evidence controls to make the second runtime pass.
