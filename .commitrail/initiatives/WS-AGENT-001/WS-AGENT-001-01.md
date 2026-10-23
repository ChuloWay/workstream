# WS-AGENT-001-01 — Neutral guide tools and OpenRouter inference

- Initiative: WS-AGENT-001
- Durable disposition: Planned
- Intended merge outcome: Remove provider-specific document custody from the core and run the existing OpenAI Agents SDK through OpenRouter using trusted bounded document tools.

## Intent

The user requires independently replaceable agent runtimes and model providers.
A live OpenRouter credential/model probe succeeded, but the existing runtime
cannot switch: PROJECTS requires OpenAI Responses and OpenAI file attachments.
The companion `WS-AGENT-001-02` adds OmniCoreAgent and qualifies both actual SDKs
against this same document-tool/result contract. This is a repair to the current hosted
guide journey, not a general agent platform or an additional product lifecycle.

## Behavior before this change

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
  the current SDK adapter, trusted provider selection, common result validation and
  the same bounded document-tool capability; preserve manager-authored behavior.
- PROJECTS `api/guide_documents.py` and `guide_compilation/` affected models,
  custody, composition and validation; ART `guide_document_access.py` and its
  composition only for trusted exact-read evidence. Keep cross-owner ports.
- API dependency and Celery worker composition for the same configuration/tool ports.
- The shared guide-media literal and its PROJECTS/ART/parser consumers, preserving
  one neutral definition rather than parallel format lists.
- A fixed document parser service and client under the existing adapter/worker
  conventions, using the release image and a private Unix socket. No generic
  command execution or new network API.
- One linear Alembic migration and affected schema baseline/fingerprints:
  runtime-independent configuration/access invariants and retained-data proof.
- `backend/pyproject.toml`, `backend/uv.lock`, applicable dependency installation
  declarations: fixed parser dependencies; reserve the second SDK installation for
  the companion change.
- `docker/backend/`, `deploy/hosted/`, local Compose, canonical environment examples and focused
  deployment tests: worker-only provider credentials and secret-free parser role.
- Move the existing pure ZIP directory-envelope helper to `backend/app/core/zip_safety.py`,
  updating its ART and parser consumers together; remove the former private module
  without an alias. This prevents parser coupling to ART internals while retaining
  one canonical bounded archive implementation.
- `backend/scripts/guide_compilation_e2e.py` and its API/pilot drill callers:
  replace the removed hosted-resource interface with the same neutral tool contract.
  Remove only their obsolete generated-ID inventory entries.
- Focused affected tests, ownership/lane inventories, and current guide/runtime,
  deployment, developer and roadmap documentation. No unrelated inventory edits.
- Historical TASK migration fixtures may restore checksum-bound predecessor
  data through the existing isolated archive-restore operation. Restore is setup,
  not proof of a current writer: all guards must be restored before the real
  migration, recovery or replay assertions. Do not retain old runtime execution
  merely to construct that data.
- `.github/workflows/release-images.yml`: select the affected local deployment,
  drill-readiness and parser-isolation proof in the existing release gate. Preserve
  frozen installation, complete test execution and existing image checks.

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

1. Keep `ProjectGuideAgentRuntime` and its typed factory. Keep
   `openai_agents_sdk` independently selectable from `model_provider`; the
   companion change registers `omnicore_agent` without changing core or schema.
   Use OpenRouter with the already-probed `openai/gpt-5.6-terra` for the concrete
   two-runtime qualification. Credentials and provider endpoints stay in trusted
   composition, outside persisted model instructions and result bodies.
2. PROJECTS owns the exact immutable run configuration, source manifest and
   trusted document-access facts. Its rule is that the authorized owner verified
   and exposed that original during that attempt, not that OpenAI attached it.
   Separate "no inference" from "no remotely hosted document resources".
   Preserve historical access/allocation facts and hashes; never invent a parsed
   result for an earlier upload. Retain only an exact-ID OpenAI cleanup reader for
   outstanding recorded resources, selected from immutable resource facts rather
   than the current inference factory. It has no dispatch/inference capability and
   cannot clear unknown allocations. Stop new remote-allocation writes; remove the
   former hosted execution path. Historical document-access rows remain facts of
   their recorded ART verification/staging; new writes use trusted neutral reads.
   Upgrade must refuse unresolved old pre-dispatch or partially persisted work
   requiring the replaced runtime until supported old-image recovery completes;
   retained uncertain terminal work is not replayed or discarded.
   The SDK capability contains only the opaque-handle document tool port. It has
   no resource allocator or document-evidence mutation method. The trusted tool
   owner alone invokes ART, validates the parser reply against request/source
   hashes, persists exact attempt/manifest access evidence and returns text. Its
   attempt/runtime authority comes from fenced composition, never model input.
3. Both SDKs receive the same opaque-handle read/search tools. ART rechecks exact
   authority, manifest, checksum and byte count on each source access. Read/search
   results have bounded text, locators, pagination/truncation and exact identity.
   Do not send all guide content up front. Common final validation rejects cited
   unopened sources and mismatched proposals regardless of SDK.
4. Parse only the currently supported PDF, DOCX, PPTX and Markdown formats in a
   fixed secret-free, networkless service with read-only root and bounded
   memory/CPU/PIDs and per-call deadlines. Stream verified bytes over a private
   Unix socket; no shared source paths or durable extracted-content storage.
   Bootstrap the container as UID/GID 0 with exactly KILL, SETGID and SETUID
   capabilities, then drop all real/effective/saved broker credentials to
   UID 10002/GID 10001. The broker retains only those three capabilities to launch
   and terminate children; inheritable/ambient sets are empty, no-new-privileges
   remains set and dumpable is zero. Verify this before binding. Two fixed child
   identities (10003:10003 and 10004:10004), empty supplementary groups and zero
   capabilities isolate concurrent calls. Child startup reapplies dumpable zero
   after exec and verifies identity before importing parser libraries or reading
   input. Existing process-count limits forbid child forks. Reuse a slot only
   after confirmed exit and reap. A Docker healthcheck drops immediately to the
   unprivileged socket-client identity and retains no capabilities.
   Use a dedicated socket volume mounted only by parser (read-write) and guide
   worker (read-only), with directory owner/parser UID 10002, worker group 10001,
   directory mode 0750, socket mode 0660. API, Beat, migrations and checker receive
   no socket mount. Parser alone creates/removes its own socket; reject symlinks
   or foreign owners, and remove a stale owned socket only after proving no live
   listener. Cap simultaneous parser work, request bytes and output; abort partial
   frames and enforce a hard per-call child deadline inside the secret-free parser
   container. No child inherits worker secrets or network. Parser tmpfs is bounded.
   Use closed operations and bounded framing/output; enforce OOXML archive/XML
   limits and malformed/encrypted/oversized PDF denial. No arbitrary execution.
5. Adapters own native loops, model-request retry/timeout mechanics and parsing
   of output. The core records a bounded immutable effective adapter profile and
   enforces the whole-run deadline, source/tool/output budgets and final validity.
   Vendor-specific settings are not universal fields; unsupported options are
   rejected, never silently ignored. OpenAI can record its controlled request
   timeout/retries. OmniCore's companion adapter records SDK-owned behavior and
   must not claim knobs the release lacks. Do not stack retry loops. Cancellation
   must terminate/await native tasks; retain uncertainty for remote outcomes.
   Runtime identity/provider/model/protocol and the effective profile are frozen
   before dispatch, with installation/configuration validation in composition.
6. Keep secrets in the worker-only trusted provider configuration. No request can
   choose credentials or endpoints. Disable native filesystem tools, offload,
   persistent sessions, telemetry capture/export, skills, subagents and remote
   tools. Capture real SDK requests to verify origin, tool inventory, absence of
   file/container/session calls and actual retention parameters. Do not infer
   provider retention from an unsupported setting or from a synthetic success.
7. Both real adapters remain the overall initiative outcome. First land this
   complete OpenAI SDK/OpenRouter path; the companion adds OmniCore with its own
   dependency environment. Resolver evidence shows published OmniCore 0.6.0 /
   LiteLLM requires `openai<3`, incompatible with the current `openai==3.37.0`.
   Do not force coinstallation, downgrade unrelated packages or bypass the lock.
   Isolated SDK environments share the exact same Workstream source/contracts.

## Acceptance criteria

- The actual OpenAI Agents SDK completes synthetic tool and original-guide
  qualification through OpenRouter and the neutral tools. The companion applies
  the same contract suite to OmniCoreAgent; this change does not claim it runs.
- Runtime substitution needs no provider-specific branching in PROJECTS/ART
  business logic or a schema change. Installed-adapter validation remains explicit.
- An unknown/foreign document handle, stale grant, altered bytes, unopened citation,
  injected storage selector, malformed output and exceeded budget are rejected.
- Required document formats support bounded incremental reads/searches with stable
  locators; a large guide is not silently truncated or sent whole to inference.
- Real isolated parser tests cover no network/credential/source mount, malformed
  and resource-exhausting inputs, cancellation, concurrent requests and cleanup.
- Committed release-image proof exercises real broker/child credentials, both
  simultaneous slots and every supported format. A compromised-child simulation
  cannot control the broker socket or inspect/signal the broker or sibling; the
  worker client remains functional. Prove timeout/cancellation reap before slot
  reuse, startup rejection for invalid identity/capabilities, and a discriminating
  removal probe. Unprivileged transport fixtures may model only the OS identity
  boundary; production has no same-UID fallback.
- Normal container SIGTERM must run the existing parser shutdown operation,
  reap admitted children and remove only its own socket. The real release-image
  proof must observe clean exit and socket removal, without a harness cleanup
  substituting for production shutdown.
- SQL profile validation rejects noncanonical inner JSON even when the outer
  configuration hash matches, with a valid control. Production tool-budget tests
  enforce call and aggregate-output limits. Conflicting receipt replay preserves
  the original evidence, and a runtime citing an unread source cannot persist a
  compilation or successful access receipt.
- PostgreSQL tests preserve retained facts and reject false source lineage; old
  unresolved work is not redispatched. Remove tests for obsolete OpenAI-only
  implementation requirements while retaining their actual safety guarantees.
- A hostile fake runtime cannot record a document read or cite a document without
  calling its tool. Grant denial, parser hash mismatch/timeout and custody failure
  return no text and leave no successful access receipt. A valid control records
  the exact read. Removing the trusted wrapper must fail the intended assertions.
- Historical cleanup tests prove current provider selection cannot redirect or
  erase retained OpenAI cleanup obligations. No former runtime execution is kept.
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
| OpenRouter can run the native SDK tool loop | Production OpenAI Agents SDK adapter with an invented guide and in-memory typed document tools | Five reads, private draft, separate coverage review and validated result at `b9bf0e7d0` using `openai/gpt-5.6-terra` | Does not prove S3 custody, a durable worker run or another model |
| Document ownership no longer depends on provider attachments | Neutral capability, trusted tool wrapper, SQL access receipts and removal of hosted execution | Implemented; retained cleanup has no dispatch capability | Final migration, isolation and negative-proof corrections require exact-head verification |
| OmniCoreAgent is a separate runtime integration | Published 0.6.0 SDK qualification in companion change 02 | Companion owns its SDK environment, native behavior and registration | This change does not claim OmniCore deployment |
| Retained data and bounded archive behavior survive | Isolated PostgreSQL cleanup plus archive tests at `254fd6cfe` | 50 passed, isolated database and role cleanup confirmed | Subsequent profile guard and proof changes require replay |
| Runtime configuration, source custody and retained-data migration | Isolated PostgreSQL batch at `96b657e5f`; updated configuration/custody/cleanup batch at `dab1b940f` | 94 then 87 passed, including Unicode profile parity, UTF-8 byte bounds and typed retained-cleanup selection; database and role cleanup confirmed | Parser privilege separation has its own Docker proof |
| Existing durable setup callers use the neutral contract | Isolated PostgreSQL worker, capability-growth, public dispatch and recovery batch at `898d10712` | 50 passed | Scripted inference does not qualify a real provider |
| Canonical profile and conflicting receipt guards discriminate invalid input | Remove each guard independently on `96b657e5f` | Both named regressions fail at their expected rejection assertion | No claim about unrelated guards |
| Unread-source rejection has independent service and database protection | Disable the service check on `96b657e5f`, then replay the direct service regression at `1c806ea2c` | PostgreSQL independently rejects missing access; the service control passes and removing its guard fails the exact rejection assertion | No claim about unrelated finalization guards |
| Parser process identities isolate concurrent document reads | Clean release-image proof at `898d10712` | All ten cases passed: four formats, separate child identities, denied socket/process access, timeout/cancellation and reuse; owned containers removed and no Git index lock retained | This run predates the normal SIGTERM cleanup repair and does not prove that later boundary. Read-only Git inspection fixes the proof-runner file-limit failure; removing it fails the large-index regression |
| The public guide drill recognizes unapproved guide lineage | Shared external-client oracle at `c735327fb` | 37 script tests passed; the new valid-response regression rejects the preceding oracle at its exact shape assertion, and fabricated activation/policy IDs remain rejected | An oracle test is not a completed provider-backed guide run |
| The release parser preserves isolation and cleans up on ordinary container stop | Exact clean-source release image and full Docker proof at `95e02e2d6` | All eleven cases passed, including `sigterm_removes_owned_socket`; image `sha256:ae1e91d6122e6d530f7af146338cd4e2fb7672a6e5793d1087cbafaf16eee5a1` | This synthetic parser proof does not establish a provider-backed guide compilation or the full contribution journey |
| Historical TASK upgrades and recovery retain their original facts | Five focused PostgreSQL cases and 34 affected shared-restore cases over the fixture repair committed as `96d84725c` | All passed; owned databases and roles removed. Snapshots were captured from `6fa9a9b55`; checksum-bound restore reuses the existing guarded test restore operation | Runner metadata names `d0de1daf9` plus a verified six-file fixture patch, not a clean `96d84725c` checkout. Restoration is setup, not proof that current guide writers create old-schema data |

## Reconciliation

- Current-source reconciliation: incorporates main `6fa9a9b55`, including merged
  PR #651 setup output specifications, bounded draft review and correction inputs,
  and #655 guide metadata tools, plus #650 artifact Operator authorization.
  Preserve those behaviors across both adapters;
  runtime substitution changes document access, not proposal requirements.
- Next usable boundary: real two-runtime guide qualification, then the existing
  project-owned checker and contribution journey drill.
- Remaining risks: no implementation decision may silently weaken SDK behavior,
  privacy or source-evidence controls to make the second runtime pass.
