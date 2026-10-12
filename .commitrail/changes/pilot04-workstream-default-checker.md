# [PILOT-04] Deliver The External Checker Flow End To End

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Replace both built-in checker catalogues with one
  versioned Workstream default checker and immutable digest-pinned project
  images, then prove ZIP-to-prechecks-to-Submission-to-post-checks without a
  parallel runtime.

## Intent

Issue #491 owns the complete checker cutover. A contributor ZIP must first pass
the one Workstream default checker and every required project pre-submit image.
Only then may the existing caller-owned transaction create an immutable
Submission, move the task to `evaluation_pending`, and retain its durable
initial post-submit dispatch. Post-submit images produce evidence only.

## Current behavior

This branch contains the normalized external contract, immutable registry,
long-lived Rust service and SDK, typed Unix-socket client, callback-scoped ART
grant, and the exact four-behavior Workstream default checker. ART verifies the
received ZIP and canonical manifest before the default and every locked PRE
image run over one genuine prepared-material capability. The selected durable
owner takes TASK custody before CHECKERS state, commits its generation lease
before execution, runs without a database transaction, and finalizes either the
exact result or one recoverable infrastructure outcome in a fresh short root.
Only a complete pass mints the one-use admission capability consumed by TASK's
existing atomic Submission, `evaluation_pending`, evaluation reservation and
outbox operation. Work findings retain bounded evidence without a Submission.
Its closed AUTH contract now assigns those two phases to the dedicated selected
PRE service principal and binds preparation, scope, the durable request and the
exact execute/finalize fact digest without granting direct service access.
The selected POST processor consumes only actual Submission and ART material
through the phase-typed callback grant, runs every locked POST image in order,
and returns canonical evidence and observed isolation without any acceptance
or routing authority. The existing CHECKERS scheduler now recognizes that
selected envelope alongside retained legacy evidence, derives its lease and
execution deadlines from the exact locked images, recomputes the ART-owned
manifest before execution, and retains the complete selected result for
restart/replay. The existing production outbox registry now owns the evaluation
request handler alongside assignment invalidation, leases worker-owned ART
material only during execution, and creates the configured Rust adapter only
for a selected request. New TASK submission composition now requires selected
POST custody and refuses an unresolved legacy admission instead of executing
it; retained legacy envelopes remain read-only decoding inputs. Admission,
routing completion and remediation fixtures now exercise the selected PRE/POST
owners. Both obsolete executable catalogues and their isolated callers and
tests have been removed; retained immutable evidence has only its bounded
historical decoder. F-020 recovery now proves that registration alone cannot
activate the retained warning-bearing generation and that only an exact
registered binding in a corrected, linked approval can activate. The combined
native journey now exercises real PostgreSQL 16, MinIO, the Rust service and the
digest-pinned image across pass, work-failure, infrastructure/restart/fresh
verification and POST evidence paths with database, object-store and workspace
cleanup.

## Bounded change

### Allowed

- The bounded permission-fixture/PostgreSQL CI provider repair permits only
  `mcp_server/tests/test_access_reads.py`'s representative permission response
  total (78 to the current exact 80), four exact PostgreSQL image source
  prefixes in `.github/workflows/backend.yml` (two),
  `.github/workflows/cli.yml` (one) and `.github/workflows/mcp.yml` (one),
  and this record. Preserve every assertion, negative/schema constant, SDK
  lock, fixture identity, test selector, service count, PostgreSQL 16 version,
  OCI digest, health check, resource bound, job dependency and required check.
  No backend product, migration or CLI product/test source may change. The
  previous invalid-total negative remains invalid; no dynamic total fallback
  or schema broadening is allowed. Independently fetched Docker Hub OCI index
  bytes must match pinned `33f923b05f64ca54ac4401c01126a6b92afe839a0aa0a52bc5aeb5cc958e5f20`.
  Acceptance is the complete existing MCP package selection, retaining and
  identifying its two baseline environment-gated skips, including declarative
  schema/wire and authority-revocation cases; existing lightweight workflow
  controls and exact provider-only structural comparison must pass. Local
  MCP 2.2 evidence is separate from hosted SDK/wire proof.

- The bounded CI collection/selected-contract repair permits only additive
  package markers `backend/tests/authorization/pre_submit/__init__.py` and
  `backend/tests/authorization/post_submit_routing/__init__.py`, plus the exact
  affected `mcp_server/contracts/{authorization_context_get,permissions_list,
  admin_roles_list,actor_get}.json` snapshots and
  this record. No production, CLI, migration, workflow, pytest import mode,
  collection selection, canonical runner or test assertion changes are allowed.
  Both AUTH directories sit under the existing packaged `tests.authorization`
  owner and have colliding flat `test_contracts` names; package-qualified imports
  must retain every original node. Reuse the selected-fragment canonical capture
  functions, change only the demonstrated selected PRE ActionId/PermissionId additions,
  ServiceIdentity addition, dependent permission count, hashes and source
  provenance. Preserve all nine operations and the other five snapshot files
  byte-for-byte, including their captured source and hash. No MCP tool is added.
  Acceptance is fresh complete canonical backend collection with every node
  assigned once across all ten declared lanes, plus real backend OpenAPI drift
  checks and a deliberately wrong-schema negative that still fails. This repair
  makes no database/runtime or hosted green claim.

- Bounded current-document reconciliation covers `docs/roadmap_status.md`,
  `docs/architecture_checker_framework.md` and
  `docs/decision_0014_external_service_adapter_convention.md`. Describe selected
  hidden PRE/POST and production request/completion composition, distinguish
  retained predecessor contracts from removed executable catalogues, preserve
  the four default blockers and warning-only summary/attestation, and retain
  PILOT-08 false-guide activation and PILOT-12 public intake as remaining work.
  Generated output-file authority is still deny-only; normalized JSON result
  custody does not prove ART file outputs. Local runc/docker-dev proof is not
  deployed or gVisor proof. Worker transport/budget code and
  `docs/operations_authorization_service.md` remain lead-owned.

- Delegated TEST-only reconciliation is limited to
  `tests/projects/post_policy/test_guards.py`, `test_postgresql.py`,
  `test_public_api.py`, `tests/authorization/post_policy/pg_support.py`,
  `tests/projects/test_locked_policy_custody.py` and the single
  `activation_case` registry-spec passthrough in
  `tests/projects/guide_activation/pg_support.py` (all under `backend/`).
  Use the current two-argument service, saved approved external policy and
  real Operator-authorized immutable registration. Preserve authority,
  transaction, custody, replay, mutation and revocation assertions. Shared
  `tests/checkers/post_submit/support.py` and all production files stay untouched.
  Remove only mutable catalogue injection, whose owner no longer exists;
  replace its purpose with exact approved-binding version/digest substitution
  refusal and unchanged locked-context reads without live registry lookup.

  Purpose mapping: the obsolete `catalogue` parametrization of
  `test_exact_source_and_authority_substitutions_reject_without_writes` is
  removed because a mutable catalogue is no longer a service input. Its remaining
  upstream/project/link/policy-hash substitutions retain their zero-write checks.
  `test_post_policy_operation_preserves_finalization_without_provider_or_evaluator_calls`
  now binds one genuinely registered POST entry to the approved snapshot and
  refuses a substituted capability version. The old catalogue-rollout context
  case is replaced by
  `test_registry_substitution_blocks_activation_but_frozen_context_never_re_resolves`:
  a substituted registry digest blocks activation with unchanged state; restored
  identity activates; frozen and active contexts remain identical with live
  registry reads forbidden. Public response comparison uses the actual saved
  approved external policy. All SQL immutability, deferred receipt closure,
  replay, commit rollback, revocation and HTTP admission tests remain selected.

- This record and affected current PILOT-04 architecture, roadmap and owner docs.
- The existing local Rust-runtime protocol fixture and selected end-to-end
  probe, to distinguish actual default rejection from actual project-image
  rejection and verify both leave the task in progress without a Submission.
- The existing OUTBOX prefork topology and its delivery task hard bound, with
  topology and real process-containment regressions, to honor the selected
  request budget without changing event-specific owner deadlines or selectors.
- The backend CI Redis service source and its exact structural regression,
  preserving the official image digest, service count, ports and health checks
  while repairing a reproduced registry quota failure before test checkout.
- CHECKERS policy contracts, registry reads, default/external execution,
  durable attempt/result custody, post routing and composition roots.
- ART preparation, verified-material callback, evidence, admission and
  post-submit materialization owners needed by the one selected runtime.
- PROJECT approval persistence and activation readiness for exact registry,
  requirement, stage, configuration and resource-limit binding.
- TASK's existing submission composition and CHECKERS dispatch owners only to
  compose the already-owned atomic Submission/`evaluation_pending`/outbox
  operation after prechecks pass and to route post-submit evidence.
- The minimum existing hidden preparation-to-Submission composition needed to
  prove PILOT-04. PILOT-12 retains assignment-bound upload intent, contributor
  REST/CLI intake and requirements-read surfaces. The existing hidden command
  stops rejecting absent summary/attestation so the default checker can retain
  warning-only observations; this does not publish the PILOT-12 surface.
- One successor migration plus model, Alembic graph, fingerprint, reset
  inventory and direct-SQL guards if existing evidence tables cannot retain the
  exact external execution and latency facts. Its ordinal follows the actual
  single linear predecessor at publication.
- Removal of both obsolete catalogue implementations, callers and obsolete
  tests after replacement proof.
- Focused contract, AUTH, custody, replay, concurrency, failure, service,
  public API, CLI, PostgreSQL and MinIO tests and their exact CI ownership.
- The CHECKERS composition adapter and existing selected PRE/POST composition
  tests may defer the fixed Unix provider until a locked external entry is
  actually invoked. A default-only PRE policy and an empty POST policy require
  no Rust-service configuration; a nonempty policy with absent configuration
  must become the existing recoverable `implementation_unavailable` outcome
  after durable reservation. Partial configuration remains invalid. No second
  provider, fallback executor, alternate result or lifecycle path is allowed.
- The existing CLI post-policy read DTO and its HTTP/public-socket contract
  tests. Replace the removed catalogue-policy decoder with the one closed
  `external_post_submit_policy.v1` response; preserve selectors, fresh read
  authority, raw output, denial handling and transport failure semantics. No
  legacy-response fallback or command-surface change is allowed.

### Not allowed

- No second scheduler, store, submission lifecycle, acceptance operation,
  policy representation, compatibility alias or parallel execution.
- No checker-owned acceptance, Review fabrication, ContributionPolicy change,
  payment work, provider-path authority, host socket exposure, or external
  execution inside a database transaction.
- No optional summary/attestation blocker. Their absence remains a warning.
- No generic Workstream implementation of project rules; every project
  pre/post check is an approved digest-pinned external image.
- No PILOT-05, PILOT-06 or PILOT-09 work, deployment, merge or issue closure.

## Design and decisions

Approval resolves every project binding to an immutable phase-specific registry
row and persists its row ID, entry digest, platform image manifest digest,
schemas, configuration and resource ceilings under the locked policy hash.
Runtime never selects a latest version or trusts a proposal string as authority.

ART computes and verifies received bytes and the canonical file manifest before
external execution. Its callback grant maps one sealed read-only workspace into
the Rust service and expires on completion, timeout, disconnect or cancellation.
The Workstream checker implements exactly archive safety, server-owned receipt
and manifest identity, high-confidence secret detection and task-rule-aware
unchanged-resubmission refusal. Missing summary/attestation yields warnings.
Every required project pre image then runs in locked order. Work failures retain
bounded findings, create no Submission or dispatch, consume no contributor
attempt and leave the task `in_progress`. Infrastructure outcomes are
recoverable and are not contributor-failure facts.

External work remains outside database transactions. After every required
precheck passes, the caller opens one root and invokes the existing TASK
submission composition operation, which consumes the exact admission while
atomically creating Submission, advancing to `evaluation_pending`, reserving
the initial evaluation and appending the dispatch event. Post workers resolve
only locked entries, read immutable Submission material through ART and persist
normalized evidence; they cannot accept work.

Activation refuses any required capability suggestion without an exact
requirement/stage binding to a registered digest-pinned image in the same
approved generation. Registration alone, wrong project/stage/requirement, or a
stale approval does not clear F-020. Existing false-policy and warning-
acknowledgment guards remain.

The old pre/post catalogues are removed in the same final change after every
production caller and required proof uses the selected runtime.
Retained approvals, locked guides, evidence and completed runs are never
rewritten or deleted. Historical decoders remain narrowly scoped to immutable
old evidence. An unresolved old-catalogue queue item or locked guide fails
closed and requires an authorized recompile/reapproval transition; it is never
silently run through a new image. This retained-data reader is not an executable
compatibility runtime. New selected admission columns are nullable only for
those retained legacy rows; native checks require the complete guide, policy,
packet, manifest and selected-run custody whenever selected lineage is present,
so migration does not synthesize or rewrite historical facts.

Pre execution uses a durable lease/generation fence. One root reserves the
exact prepared-generation, policy, registry and request identities, commits,
then the ART callback and external service execute without a database
transaction. A fresh root locks TASK currentness before CHECKERS attempt state,
verifies lease/generation and material/result/isolation identities, and appends
the immutable outcome or marks a recoverable infrastructure result. Expired
leases are finalized as infrastructure failures under the same locks. Because
pre-Submission prepared bytes and the grant are deliberately process-local, a
restart never reconstructs them from a DTO or path: retry requires a fresh
upload, a fresh server-computed byte/manifest identity and a new attempt
generation while retaining the failed attempt. A grant is never serialized or
resumed. Queue/read-current/reserve, completion, replay and acknowledgment all
acquire TASK custody before CHECKERS state, including the retained
intermediate-wait regression.

## Acceptance criteria

- [x] Approval binds the default behavior digest and every project binding to
  an exact immutable registry row, phase, image, schemas, configuration and
  limits; substitutions and stale approvals fail closed.
- [x] Activation enforces exact F-020 requirement/stage/generation coverage and
  retains false-policy and warning-acknowledgment guards.
- [x] F-020 recovery is proven by register -> recompile -> approve -> activate
  in one current generation; registration alone and wrong generation, stage,
  requirement, registry digest or stale approval remain blocked.
- [x] ART verifies server receipt identity and a bounded safe manifest before
  any project image reads material.
- [x] The default checker runs exactly four blockers; absent summary and
  attestation remain warning-only.
- [x] Every required pre image passes before admission consumption. Work
  findings create no Submission/dispatch and keep the task `in_progress`;
  infrastructure failures remain recoverable and consume no attempt.
- [x] Passing preparation invokes the existing caller-owned atomic operation
  and commits Submission, `evaluation_pending` and initial dispatch together.
- [x] Required post images consume immutable Submission custody, persist
  normalized evidence and never decide acceptance.
- [x] Timeout, cancellation, crash/restart, changed policy/material,
  cross-project access and duplicate delivery cannot create partial effects;
  latency and queue/execution lineage are retained, and restart requires fresh
  server-verified uploaded material rather than a reconstructed scratch handle.
- [x] Retained old evidence remains readable without rewriting hashes; unresolved
  old execution cannot cross into the new runtime and requires authorized policy
  transition.
- [x] Both obsolete catalogues, implementations, callers and obsolete tests are
  removed without a fallback or parallel runtime.
- [x] A real PostgreSQL 16, MinIO and Rust-service journey proves pass, work
  failure, infrastructure/retry and post-dispatch paths with cleanup.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, authorization, product_ops,
  reuse_dedup, qa, test_delta, documentation, ci_integrity
- Human review focus: Locked policy/registry custody, TASK-before-CHECKERS
  ordering for read-current/reserve/enqueue/complete/replay/acknowledge,
  all-pre-before-Submission, transaction boundaries, durable pre lease and
  process-local grant lifetime, work-versus-infrastructure outcomes, retained
  history, F-020, post non-acceptance and complete catalogue removal.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing component custody | Prior PR538 default, Rust service/SDK, ART callback and contract reviews | Passed at recorded component heads | Final selected flow/current-main integration pending |
| PRE transaction boundary | `pytest -q` for invalid claim controls and `test_checker_processor_starts_only_after_authority_transaction_commits`, plus Ruff on the four affected files | 5 passed; processor construction is refused while the authority root is active and reached only after it commits | Durable lease/generation schema and selected external sequence remain pending |
| Selected PRE callback | `pytest -q backend/tests/checkers/external/test_selected_pre_submit.py`; Ruff and `git diff --check` on the affected files | 4 passed; exact default runs first, a real high-confidence secret prevents every external invocation, locked external pass/fail is retained, and the genuine request-bound ART grant completes cleanup with one bounded owned mount | Durable persistence, admission composition, crash recovery and native service journey remain pending |
| Selected admission binding | `pytest -q backend/tests/test_submission_change_gate.py backend/tests/checkers/external/test_selected_pre_submit.py`; Ruff and `git diff --check` on the affected files | 11 passed; existing callers retain their exact archive/manifest rejection while the selected binder carries unchanged work plus exact predecessor/current rules into the default checker | The binder is not yet selected by the durable admission caller |
| Selected durable result contract | `pytest -q backend/tests/checkers/external/test_selected_pre_submit.py`; Ruff and `git diff --check` on the affected files | 5 passed; canonical result/terminal digests bind the default, ordered external results, isolation, generation lease, outcome and measured queue/execution latency | PostgreSQL reservation, lease and finalize storage remain pending |
| Selected durable request contract | The same five selected-PRE tests plus focused Ruff and `git diff --check` | Passed; the reservation digest covers contributor/link, TASK, assignment, ART attempt/generation, policy/default, exact default input and archive/manifest custody, and the terminal includes that request digest | PostgreSQL ownership and SQL custody remain pending |
| Selected idempotent replay contract | `pytest -q backend/tests/checkers/external/test_selected_pre_submit.py backend/tests/checkers/external/test_selected_pre_submit_coordination.py backend/tests/checkers/external/test_selected_pre_submit_service.py backend/tests/checkers/external/test_selected_preparation_command.py backend/tests/authorization/pre_submit/test_contracts.py backend/tests/test_submission_bundle_admission.py`; focused Ruff and `git diff --check` | 70 passed; one actor/key namespace permits a fresh prepared generation only when every stable byte, packet, policy, TASK and assignment fact matches, validates stored terminal timing/results, replays bounded work findings or an existing durable upload, and rejects changed stable facts | Native uniqueness/immutability and concurrent PostgreSQL replay proof remain pending |
| Selected POST policy handoff | Focused selected PRE/admission/composition tests plus Ruff and `git diff --check` | 76 database-free tests passed; the complete approved POST image policy and digest now travel inside the selected PRE request, verified admission and ART consumption result, and malformed or substituted retained policy fails closed | Submission request selection and durable external POST result storage remain pending; seven separately selected routing tests required a PostgreSQL URL and were not claimed |
| Selected durable owner source | `pytest -q` over selected PRE, policy, coordination, PROJECT activation/proposal contracts and architecture module boundaries; focused Ruff | 51 focused/architecture tests passed; the selected run is its own durable attempt identity, TASK locks precede CHECKERS state, one-use admission facts are substitution-resistant, ordered deadlines fit ART custody, and four private module edges were removed through public ports/composition | Native migration, exact AUTH SQL closure, crash reclaim and admission composition remain pending |
| Selected lease execution boundary | `pytest -q backend/tests/checkers/external/test_selected_pre_submit_coordination.py backend/tests/checkers/external/test_selected_pre_submit_service.py backend/tests/checkers/external/test_selected_pre_submit.py backend/tests/architecture/test_module_boundaries.py`; focused Ruff | 49 passed; fixed-service preparation precedes owner locks, the lease commits before material execution, execution occurs with no root open, and exact lease/result digests are consumed in a separate finalization root | Native SQL custody and live admission selection remain pending |
| Selected PRE authority contract | `pytest -q backend/tests/authorization/pre_submit/test_contracts.py backend/tests/authorization/test_catalogue.py backend/tests/checkers/external/test_selected_pre_submit_service.py backend/tests/architecture/test_module_boundaries.py`; focused Ruff and `git diff --check` | 50 passed; one dedicated service identity owns only execute/finalize, prepared selectors bind project/run/request, exact phase facts bind the decision and audit digest, direct service calls remain unavailable, and composition uses the public authority port | Native actor/action/evidence constraints and live workflow injection remain pending |
| Selected POST callback | `pytest -q backend/tests/checkers/external/test_selected_post_submit.py`; Ruff and `git diff --check` on the affected files | 3 passed; actual Submission/ART identity reaches every locked POST image through its short-lived grant, work pass/fail remains evidence only, and infrastructure failure stays recoverable | Durable POST reservation/finalization, worker restart and routing composition remain pending |
| Selected durable POST contract | `pytest -q backend/tests/checkers/external/test_selected_post_submit.py backend/tests/test_submission_bundle_admission.py`; Ruff and `git diff --check` on the affected files | 56 passed; the request digest binds the exact approved selected policy, separately named locked TASK context and native Submission/ART identity, while the result digest binds request/generation, ordered execution evidence or a closed recoverable infrastructure category without acceptance authority; a legacy catalogue hash cannot stand in for the selected image-policy digest | The existing scheduler/materializer still needs to select this contract and persist it through restart/replay |
| Selected POST scheduler compatibility | `pytest -q backend/tests/checkers/external/test_selected_post_submit.py backend/tests/checkers/execution/test_results.py backend/tests/checkers/execution/test_completion_contract.py backend/tests/checkers/post_submit/test_request.py backend/tests/test_submission_bundle_admission.py`; focused Ruff | 84 passed; one discriminated owner accepts retained legacy and selected request/result envelopes, selected leases cover the ordered image budget and finalization margin, ART recomputes the selected manifest, and focused scheduler controls prove exact completed/infrastructure envelopes and generic replay parsing | Native selected columns/constraints and live Rust worker proof remain pending |
| Selected POST native custody | `python3 /tmp/p04_selected_runner.py <repo> /tmp/p04-selected-post-result-replay 420 tests/checkers/external/test_selected_post_submit.py::test_selected_post_materializes_actual_submission_and_replays`; focused selected-POST pure tests and Ruff | PostgreSQL 16 PASS 1 in 36.10s with database/role cleanup complete, plus 7 pure tests; actual immutable Submission and verified ART lineage materialize through the selected policy, finalize selected result/member custody and replay the stored strict envelope | The approved policy is empty in this discriminator; a locked nonempty image, live Rust service and worker restart remain pending |
| Nonempty selected POST policy and result | `python3 /tmp/p04_selected_runner.py <repo> /tmp/p04-selected-post-nonempty5 600 tests/checkers/external/test_selected_post_submit.py::test_selected_post_persists_locked_external_member`; `pytest -q backend/tests/checkers/external/test_selected_post_submit.py -m 'not postgres_schema_contract'`; focused Ruff and `git diff --check` | PostgreSQL 16 PASS 1 with database/role cleanup complete, plus 7 pure tests; an actual immutable registry entry is registered through Operator authority, compiled into one supported POST requirement, approved, activated, materialized from the real Submission/ART lineage and persisted as the exact selected member. Persisted UUID-bearing policy JSON and SQL requirement custody are decoded and validated without relaxing strict in-memory contracts. | The adapter in this discriminator is bounded and deterministic; a live Rust service, restart/reclaim and external work/infra outcomes remain pending |
| Actual selected POST Rust service | `run_selected_post_probe.py` through the isolated PostgreSQL runner at `/tmp/p04-selected-post-probe-final2`, using local registry platform manifest `sha256:c664d8d85d6dfcded31710223c8d91441548e5445f0aa9b59d246fc464a129ef`; focused Rust POST-grant round-trip test, Ruff and `git diff --check` | PASS 1 in 45.06s on PostgreSQL 16/schema 0037 with database/role and callback workspace cleanup complete. The real Rust service validates the full POST grant, launches the digest-pinned container in explicit local `runc`/`docker-dev` mode, reads every verified manifest file, returns an exact isolation receipt, and the normal owner persists its selected member. | This local proof does not claim hosted `runsc`; restart/reclaim, live PRE orchestration and final end-to-end MinIO evidence remain pending |
| Actual selected PRE Rust service | `PYTHONPATH=.:backend /tmp/workstream-pilot-review-locked-env/bin/python experiments/pilot04_external_checker_runtime/run_selected_pre_probe.py --image-reference localhost:35104/ws-pilot04-checker@sha256:c664d8d85d6dfcded31710223c8d91441548e5445f0aa9b59d246fc464a129ef --service-binary external_checkers/target/debug/workstream-checker-service`; Ruff and `py_compile` | PASS. Genuine prepared ART bytes and the server-computed manifest enter the selected default-plus-project-image processor before any Submission exists. The callback-scoped grant launches the exact digest-pinned image through the Rust service in explicit local `runc`/`docker-dev` mode, returns matching result/isolation custody, and confirms the workspace is empty after the callback. | This is the actual selected PRE execution boundary, not the final PostgreSQL/MinIO admission-to-dispatch journey or a hosted `runsc` claim. |
| Production delivery registration and owner boundaries | `pytest -q backend/tests/architecture/test_module_boundaries.py backend/tests/test_artifact_architecture.py backend/tests/outbox/test_contracts.py`; focused Ruff and a direct registry construction probe | 116 passed; the existing production outbox registry exposes assignment invalidation and evaluation request handlers, selected Rust configuration is lazy, and PRE coordination stays behind CHECKERS' public adapter root | Database-backed legacy/selected delivery and worker restart proofs remain pending |
| New Submission selected-only boundary | `pytest -q backend/tests/test_submission_bundle_admission.py backend/tests/checkers/external/test_selected_post_submit.py backend/tests/test_artifact_architecture.py::test_checker_custody_ports_have_exact_owner_and_art_consumers`; focused Ruff | 59 passed; retained legacy and selected admission projections are mutually exclusive, and the TASK writer accepts only selected POST custody for a new immutable Submission | Native rollback proof for a retained unresolved legacy admission remains pending |
| Obsolete catalogue removal | Focused lane/architecture/ownership suite; recursive collection of every modified surviving test module; Ruff, module-boundary inventory and stale-import scan | 84 focused tests passed and 94 surviving tests collected. Ten obsolete executable catalogue/runner targets, their private-edge debt and tests are absent; exact ownership metadata admits only the selected owners and those retirements. | The stacked branch still has separately tracked structural-debt growth from earlier P02/P10/P04 source, so the repository-wide structural-debt gate is not claimed by this deletion checkpoint. |
| F-020 recovery | `python3 /tmp/p04_selected_runner.py <repo> /tmp/pilot04-f020-native6 600 tests/projects/guide_activation/test_postgresql.py::test_checker_registration_requires_corrected_approval_before_activation`; focused external-policy tests and Ruff | PostgreSQL 16 PASS 1 with schema 0037 and database/role/MinIO cleanup complete, plus 6 pure compiler tests. A real Operator registration does not clear the existing warning generation; correction observes the current registry projection, a linked successor approval binds the exact row/digest, the successor activates, and the old generation remains refused. Wrong stage, requirement, identity and registry digest substitutions fail closed. | This proves the activation recovery gate, not the combined intake-to-POST journey. |
| Retained admission migration shape | `pytest -q backend/tests/test_submission_bundle_admission.py backend/tests/checkers/external/test_selected_pre_submit_coordination.py backend/tests/checkers/external/test_selected_preparation_command.py backend/tests/test_artifact_architecture.py::test_checker_materialization_contract_has_one_canonical_consumer_owner`; focused Ruff | 62 passed; selected rows require complete new custody while every new column stays null on retained legacy rows, avoiding fabricated backfill or historical hash rewrites | Successor SQL and direct retained/selected row controls remain pending |
| Owner/caller trace | PROJECT approval/activation, ART preparation/admission, TASK composition and CHECKERS dispatch | Selected PRE uses durable reserve/lease/finalize roots around the genuine ART callback; a pass is consumed only by TASK's existing atomic Submission/evaluation reservation/outbox composition, while POST uses immutable Submission/ART custody | Independent final integration review remains |
| Default behavior and warnings | `pytest -q backend/tests/checkers/default/test_contract.py backend/tests/checkers/default/test_execution.py backend/tests/checkers/external/test_selected_pre_submit.py -m 'not postgres_schema_contract'` | 30 passed. The manifest and executable behavior retain exactly four ordered blockers; empty summary and attestation produce warnings without changing eligibility. | Full required checks remain on the final reconciled head. |
| End-to-end replacement | `run_selected_end_to_end_probe.py` through the isolated runner, `/tmp/pilot04-selected-e2e10.log` and `.json`, using platform manifest `sha256:c664d8d85d6dfcded31710223c8d91441548e5445f0aa9b59d246fc464a129ef` | PASS on PostgreSQL 16/schema 0037 with database/role/MinIO/workspace cleanup complete. Real MinIO PRE and the Rust/runc image commit one Submission, `evaluation_pending` and dispatch, then actual Submission/ART POST evidence. A secret finding leaves a separate Task `in_progress` with no Submission. Service loss retains `implementation_unavailable`; restart uses a fresh upload and independent ART verification, records a completed successor generation and commits exactly one later Submission/dispatch. | This local proof uses explicit `runc`/`docker-dev`; hosted CI must exercise its configured runtime and the final reconciled head. |


| Delegated current post-policy callers | Exact `c1195f8b2d55bc02976efe41d6052bca8b975a66`: six focused PostgreSQL cases in `/tmp/pilot04-post-policy-c119-native-callers.log` and producer metadata `.json`; scoped Ruff and `git diff --check` | 6 passed in 104.91s, schema `0036_selected_checker_flow`, database/role cleanup complete. The registered digest substitution refuses activation with unchanged activation facts; restored registration activates, and active/frozen reads never consult registry. Public approval/replay/revocation and commit rollback, plus canonical AUTH derive/read/approve evidence pass. | Local PostgreSQL 16.15 uses an owned 512 MiB tmpfs and 256 MiB memory bound with fsync/synchronous_commit/full_page_writes enabled. This test-only proof uses local ART and scripted setup, not MinIO or runtime evaluation; final combined source and hosted CI remain separately verified. |

The registered-one-entry projection and exact approved-binding version rejection
also passed at `397e8812c`, with that test/source blob unchanged at `c1195f8b2`.
The companion registry-refusal test initially expected `proposal_stale`; its
actual canonical readiness outcome is `approval_blocked`, corrected and verified
in the six-case proof above. Two broader selections reached their unchanged
240-second child budget (physical-disk reset IO, then a selection too large for
that focused budget); both cleaned their databases/roles and are not reported as
complete module passes. All surviving tests remain in their canonical CI lanes.
The delegated reconciliation changes no capability or public exposure, so it has
no independent roadmap change beyond the parent cutover's documented scope.

## Reconciliation

- Current-source reconciliation: implementation starts at PR538 head
  `7453a0d8c5664cfd486872a381899f3755393004`; final publication will reconcile
  actual merged `main` and intervening owners.
- Next usable boundary: independent full-scope review and final required CI;
  no component-only merge.
- Remaining risk: reconcile the final stacked migration and owner metadata with
  actual `main`, then validate the complete required test union on that tree.

## Production completion repair

Independent review found that the production outbox registry selected evaluation
requests but omitted the existing completion handler. The earlier real Rust/MinIO
probe called the executor directly and ended at `evaluation_pending`; it did not
prove worker completion routing. The registry now composes the canonical
completion handler. The new native production-registry test exercises request
delivery, emitted completion delivery, acknowledgment and duplicate refusal for
both human review and shared automatic acceptance with complete awards. Its
runtime result remains pending until the isolated PostgreSQL command completes.
Publication must remove the accidentally stacked PILOT-02/PILOT-10 source and
reconcile the selected-flow successor with the actual merged migration chain.

## External PRE configuration repair

PRE bindings previously forced configuration to an empty object, so an otherwise
registered PRE image with required configuration could never be approved. PRE now
uses the existing bounded flat CapabilityParameter contract, enforces unique
parameter names and validates the exact registered schema in both compilation
and approval. Configuration arrays are normalized to JSON arrays for both
phases. Empty PRE parameters are excluded during serialization, preserving
retained empty-binding hashes. Focused compiler regressions cover configured
PRE success, required/type rejection, duplicate names and retained serialization.

### Selected replacement cause repair

After reconciling merged replacement intake and the operator-retry branch, source
review found selected PRE lineage omitted the remediation manifest. The repair
binds the exact cause through canonical reservation JSON, TASK revalidation,
ART final authority and ready-admission facts. Initial attempts require no cause;
replacement attempts require a UUID cause alongside the predecessor. Focused
proof covers cause round trips, publication and substitution denial. The first
contract run passed 120 tests; the expanded run passed 121 with one stale AUTH
fixture missing required packet/manifest facts. That fixture is being corrected
without changing authority guards. PostgreSQL currentness and full Rust/MinIO
proof remain pending on the final reconciled migration.

The reconciled AUTH composition exceeded its existing 1,200-line boundary. Move
its exact artifact-binding matcher to the existing materialization binding owner,
with explicit context/digest inputs and unchanged predicates; do not alter the
structural debt ledger or its limit.

The first reconciled Rust probe exposed a branch-reconstruction error: TASK's
repository reverted the merged `select_submission_context` operation while its
service still called it. Restore the merged repository operation, retaining
selected-policy decoding, and make selected PRE locking use the same canonical
TASK context service as all intake callers. This also retains CHECKERS currentness
validation for replacement attempts. The failed probe's owned database was
cleaned; rerun the real service proof after the repaired candidate is frozen.

Configuration repair: PRE and POST machine configuration accepts bounded
canonical relative paths/patterns through the existing CHECKERS syntax validator,
while retaining command, credential and control-character guards. Actual model
prose fields remain unchanged. The affected 127 contract/policy tests pass; an
independent 18-control replay confirms the former valid-path rejection is fixed.

The first reconciled native owner run failed four cases at deferred Submission
dispatch custody, before completion/replacement assertions. The new selected
admission has no historical evidence row, but merged replacement dispatch SQL
still used an inner join to that row. Preserve the replacement cause predicates
and adapt that join for the explicit selected lineage. All owned database, role
and MinIO resources were cleaned. No passing full-flow claim is made for that run.

Full-cutover cleanup after the user's clarification: remove the unused production
historical catalogue factory and historical Submission-content adapter. Move
only the frozen metadata needed to seed actual predecessor schemas into
`tests/historical_checker_metadata.py` and the migration-only Submission fixture.
No product adapter constructs the removed catalogue. New Operator retries only
construct selected external requests; immutable receipt replay is preserved.

Real local selected Rust/MinIO run at fbb397a passed default/PRE/Submission/POST
and production completion to review_pending, default-secret rejection without a
Submission, and unavailable-PRE recovery through fresh verified bytes. All owned
DB/role/MinIO/scratch cleanup passed. The runtime was runc/docker-dev, not gVisor.
The same-head native run passed the real production automatic acceptance case
(with exact contribution and both awards); replacement failed at strict UUID
lineage construction. Normalize the native PostgreSQL remediation UUID to the
TASK public port's Python UUID representation rather than weakening validation.
Replacement proof and runtime-budget alignment remain pending.

Runtime budget repair aligns selected POST work, ART custody and the production
request transport; only request events receive extended delivery bounds. Preserve
unknown-event refusal before invocation and authorized immutable finalization
replay by resolving bounds independently of current handler registration; the
existing claim/invocation guards still require a registered handler. Focused
unknown-registration and selected production delivery regressions are required.

Canonical multi-project fixtures reuse only an exact already-registered immutable
checker entry via the public registry reader, asserting the full spec digest;
otherwise they publish through real Operator authority. They do not duplicate
registrations or bypass registry custody. Selected replacement test substitutions
normalize a native cause UUID at the typed fixture boundary.

Static selected policy budgets are validated before compilation and approval.
POST rejects both a single excessive image and an excessive aggregate; PRE
rejects aggregate work beyond the platform custody ceiling. Lower deployment
limits still produce a recoverable infrastructure refusal at runtime. Focused
policy, outbox and transport verification passed 56 tests in the local locked
environment; this is not final-head full-suite CI evidence. Native 434b9e0d3
passed replacement replay, unknown registration and automatic acceptance; its
two cause guards stopped at a native UUID fixture boundary. Normalize that
fixture identifier only, preserving the strict production registry reader.
Database, role and MinIO cleanup completed; cause-guard rerun remains pending.

The selected cause-guard rerun reached the intended SQL immutability denial
(SQLSTATE 55000) but exposed two superseded test assumptions: successor requests
were rebuilt with the historical DTO, and mutation refusal was caught as an
integrity violation instead of DBAPIError. Use the exact selected constructor
for selected fixtures and retain the exact 55000 assertion. No production guard
or database constraint changes are part of this test repair. Reconcile roadmap
claims to selected hidden delivery, keeping public intake and hosted isolation
proof explicitly outside the delivered surface. Final guard rerun is required.

Real Celery transport must cover selected POST work, not just the asynchronous
owner timeout. Its fixed prefork hard bound is now the maximum lease plus a
60-second shutdown margin (3660 seconds), with exact task/message validation
to reject shorter or longer overrides. Per-event bounds remain selected request
3520/3600 and ordinary events 240/300. Preserve the existing scaled real-prefork
kill/reap/UNKNOWN regression while scaling both the installed test bound and its
entry guard; no production duration is shortened for verification.

Current-document reconciliation distinguishes selected hidden production
composition from public intake and false-guide activation. Immutable predecessor
contracts are retained provenance, not executable catalogue fallback. Source
inspection confirms output-file storage/binding is deny-only while selected
images produce closed JSON results. This editorial repair adds no runtime
proof; the lead owns final-head native cause guards, worker timing and hosted CI.

Final repaired native evidence: cause-substitution and intermediate TASK-lock
wait controls passed 3 tests in 186.12s at 11bd7bda0. Real prefork kill/reap,
UNKNOWN persistence and independent hard-limit checks passed 2 tests in 25.81s
at 2d111d8c7; topology and transport controls passed 24 tests in 3.65s. Owned
database, role and MinIO cleanup completed for both native runs. The selected
Rust/MinIO probe at 89df6a34a passed actual default and external PRE rejection
without a new Submission, passing PRE-to-Submission/dispatch-to-POST/completion
to review_pending, fresh completion restart/replay, and unavailable-service
recovery through fresh verified bytes. Image platform manifest is
sha256:c2d957341116c2324299461598330bf93937786c30658a4b71ef9392e9b78278.
Its runtime is local runc/docker-dev, not hosted gVisor. Database, role, object
store and scratch cleanup passed. Later documentation commits change no product
code from that tested head. Full final-head hosted CI remains required.

Fresh hosted CI at c0ffb0f47 found one current-roadmap vocabulary violation
(corrected to Celery composition) and two lanes failed before checkout on an
anonymous public-ECR Redis Data limit exceeded response. Use the identical
official Redis OCI index from Docker Hub instead: independently fetched bytes
hash to the same pinned 520775a41a63e77e06c73e35d2fd9cc15921a609516818796b4ecbb813078bc7.
Only the two registry prefixes and exact structural expectation change; all
services, digest, health checks, test selection and caps remain unchanged.
New-source CI verification is required; those failed lanes ran no tests.

Fresh CLI public-contract CI then reached the current backend successfully but
rejected its selected external POST policy locally as `invalid_api_response`.
The CLI still decoded the removed catalogue schema. The bounded caller repair
uses a strict closed external-policy/registry DTO, rejects the historical active
catalogue shape and retains the existing public authority, replay and transport
controls. Focused Go packages and five HTTP contract tests pass. The strengthened
real PostgreSQL public-socket node publishes a genuine Operator-authorized POST
registry entry, derives one nonempty locked binding and passes in 96.64 seconds
at code/test head `84087f49245482ecf775a6d68dc83a849f9ebe0a`, schema head
`0036_selected_checker_flow`, with complete isolated database/role cleanup. It
uses the actual current backend JSON rather than a copied nested fixture. This
record-only descendant changes no tested CLI or test bytes. The prior hosted
143-pass/one-fail run is retained as the failing-before discriminator.

At clean `a9547a49b42c246d355b818e63c68ed85fa6270a`, the unchanged canonical
`run_test_lanes.py --collect-only` collected 8,887 unique nodes in 228.06 seconds,
with zero deselections and complete, nonoverlapping assignment to all ten lanes.
Both namespaced AUTH families are retained: three selected PRE contracts and
96 post-submit-routing nodes. Producer manifest and per-lane inventories are in
`/tmp/pilot04-a954-collection-canonical/`; raw collection output is
`/tmp/pilot04-a954-collection-canonical.log`, with generated metadata in
`/tmp/pilot04-a954-collection-metadata.json`. This is collection proof, not
backend test execution or lane-runtime evidence.

All eleven MCP selected-fragment tests passed in 37.93 seconds against a fresh
backend OpenAPI command. A deliberately added counterfeit ActionId produced the
intended one drift-check failure with ten other checks passing in 1.24 seconds.
Logs are `/tmp/pilot04-a954-mcp-current-canonical.log` and
`/tmp/pilot04-a954-mcp-wrong-enum.log`. Canonical capture is from backend source
`3fde44797607d4c187dc62f93876e6ae70d5c555`; this repair leaves that backend code
unchanged. The local contract tests reuse the existing MCP 2.2.0 environment,
with the backend command in the locked backend environment; hosted SDK/wire and
full required CI proof remain separate. Five unaffected snapshot files retain
exact bytes, source and hashes; all nine operations are unchanged. Initial
harness setup failures (invalid output-parent layout and an incompatible backend
MCP SDK for test conftest) are retained in raw logs and are not test results.

Hosted e7 CLI checks found one formatting-only failure in the public policy
regression. Apply the repository formatter; Python AST equality before/after
confirms no test behavior change, preserving the native 8408 producer proof.

The fixed Unix checker provider is now resolved only when a locked external
entry executes. Nineteen focused runtime and selected-PRE tests pass: an empty
PRE policy runs the actual verified-archive default with no grant or provider
construction, while a nonempty policy with absent settings opens its ART grant
and returns the existing recoverable `implementation_unavailable` category.
The production empty-POST request/completion route also passes against real
PostgreSQL with absent service settings, zero persisted external members and
complete database/role cleanup (`/tmp/pilot04-optional-runtime-post.log` and
`.json`). Strict partial-setting validation and the sole fixed provider remain
unchanged. Full final-head hosted CI remains required.

At clean `769d117a7230af053ac7ff63c52f6b35b674c21b`, the entire existing MCP
package selection passed 367 tests in 47.56 seconds using the existing local
MCP 2.2.0 environment. Its two baseline environment-gated skips remain exactly
the fresh backend OpenAPI comparison and clean-wheel independence proof; each
has a separate required hosted invocation. Declarative schemas, exact GET wire,
projection, invalid response and post-revocation controls execute in this suite.
The old invalid-total negative is unchanged; the representative positive fixture
alone now matches the backend's exact 80. Raw output is
`/tmp/pilot04-permission-pg-mcp-package.log`. This is not hosted SDK 2.3 wire or
container/build proof.

Existing lightweight workflow controls passed all 20 tests in 2.309 seconds
(`/tmp/pilot04-permission-pg-lightweight.log`). Independently fetched official
Docker Hub PostgreSQL 16 OCI index bytes are 10,237 bytes and hash exactly to
`33f923b05f64ca54ac4401c01126a6b92afe839a0aa0a52bc5aeb5cc958e5f20`
(`/tmp/pilot04-postgres-33f923-dockerhub-manifest.json`). Reversing only the four
provider-prefix replacements yields byte-identical original workflow text:
backend two services, CLI one and MCP one. All version/digest, health, PostgreSQL
configuration, resource bounds, job dependencies and required checks are retained.
No container or image layers were provisioned for this source repair. Actual
new-source hosted service startup, SDK/wire, build and full CI remain required.
