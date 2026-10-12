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
sole external envelope, derives its lease and
execution deadlines from the exact locked images, recomputes the ART-owned
manifest before execution, and retains the complete selected result for
restart/replay. The existing production outbox registry now owns the evaluation
request handler alongside assignment invalidation, leases worker-owned ART
material only during execution, and creates the configured Rust adapter only
for a selected request. New TASK submission composition now requires selected
POST custody and refuses an unresolved legacy admission instead of executing
it; no old request/result runtime or decoder remains. Admission,
routing completion and remediation fixtures now exercise the selected PRE/POST
owners. Both obsolete executable catalogues and their isolated callers and
tests are removed together with obsolete contracts; stored immutable evidence
remains intact without an old runtime reader. F-020 recovery now proves that registration alone cannot
activate the retained warning-bearing generation and that only an exact
registered binding in a corrected, linked approval can activate. The combined
native journey now exercises real PostgreSQL 16, MinIO, the Rust service and the
digest-pinned image across pass, work-failure, infrastructure/restart/fresh
verification and POST evidence paths with database, object-store and workspace
cleanup.

## Bounded change

### Allowed

- Final dead-contract removal permits the obsolete CHECKERS modules
  `api/pre_submit.py`, `api/post_submit.py`, `api/historical_post_submit.py`,
  `api/policy_compilation.py` and `post_submit_contracts.py`, their unused exports
  in `api/__init__.py`, and this record. Production consumers now use the sole
  external contracts and canonical packet/value primitives. Remove these
  unreferenced catalogue/planner/DTO implementations rather than aliases or
  replacement decoders. Preserve current public ports, schema identifiers,
  stored records, migrations, AUTH and immutable evidence. Acceptance is no
  production reference to the removed modules, current app/contract imports,
  Ruff, full collection, focused current-owner controls and the final native
  journey. Architecture reviewers inspect the combined removal; risk is L1.

- Project POST-policy custody accepts only the locked external-image policy.
  This repair permits `backend/app/modules/projects/post_policy/custody.py`
  and this record: remove the obsolete catalogue union, read fallback and
  activation fallback while retaining exact operation receipts, sidecar hashes,
  authority, lineage and caller-owned transactions. No stored row deletion,
  migration, alternate decoder, deployment or merge is authorized by this
  scope. Native current-policy public reads/approval/replay/revocation and
  activation controls, Ruff and relevant owner checks verify the removal.
  The lead independently inspects the final diff; affected architecture and
  authority reviewers replay the combined candidate. Risk is L1 because
  policy custody remains fail-closed and governs activation.

- Administrative permission-read fixture reconciliation permits only
  `backend/tests/authorization/admin_access/test_admin_reads_postgresql.py`
  and this record. Replace the obsolete exact permission total 78 with 80,
  reflecting the selected PRE execute/finalize permissions. Preserve role,
  response, authority and observation assertions. No product, migration,
  workflow, test selection or implementation change is permitted. Acceptance
  is both existing public administrative reads on real PostgreSQL, plus Ruff
  and whitespace checks. The low-risk review checks the exact diff and native
  evidence. This fixture correction has no additional roadmap impact.

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
- Bounded hosted-suite reconciliation may update
  `backend/tests/retained_material_fixtures.py`,
  `backend/tests/projects/guide_compilation/test_capability_growth_postgresql.py`,
  `backend/tests/projects/guide_compilation/test_live_cutover_postgresql.py`,
  `backend/tests/projects/guide_activation/test_admission.py`, and the existing
  Retained-material callers
  must use the current typed TASK submission-context port; worker tests must
  await the current async composition helper; activation admission tests use
  the current constructor. Historical migration fixtures may preserve raw rows
  and predecessor shapes, but cannot reconstruct an executable catalogue DTO
  or feed retained rows into the current scheduler.
- The selected-only contract cleanup may update CHECKERS public API value types,
  execution, result classification, repository, coordination and retry owners,
  plus `backend/app/modules/tasks/post_submit_routing/evaluation_guard.py` and
  focused selected-flow tests. The current boundary accepts only the selected
  external request/result schemas. Stored historical rows remain immutable and
  readable as raw history, but cannot acquire a lease, execute, retry, finalize
  or publish a completion. Selected replay compares the same exact TASK owner
  projection and full locked selected-policy body as initial reservation.
  TASK, assignment and Submission lock order, terminal eligibility, denial
  semantics and persisted historical facts remain unchanged.

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
rewritten or deleted. No historical catalogue decoder or executable compatibility
path remains. Unsupported queue envelopes and locked policy bodies fail closed;
they cannot select a checker implementation. Existing nullable storage columns
preserve original facts without adding an old writer or reader. Native checks
require the complete guide, policy,
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

The migration-only archive scope includes
`backend/tests/fixtures/pilot04_predecessor_rows.json.gz`,
`backend/tests/historical_submission_fixtures.py`, and the existing retry and
replacement migration tests. Replace executable pinned-source writers and the
raw DTO facade with checksum-bound stored rows and explicit snapshot selection.
Fixture restoration is restricted to an owned isolated test database. It must
restore trigger/FK settings, validate foreign keys and named material custody,
and compare every restored row before any migration assertion receives data.
Restoring terminal archive facts is setup evidence, not proof of a current or
predecessor writer. The archive records capture/schema provenance; no product
runtime, deployment, retained-row deletion or permissive current guard is added.
Wrong checksums, unowned targets, changed schema/rows and unsupported fixture
variants must refuse. Independent CI/QA review and the preserved real PostgreSQL
migration invariants verify this fixture replacement.

Current history and queue fixtures also replace built-in failure-name switches
with normalized registered-image verdicts. Allowed producer paths are
`backend/tests/checkers/execution/storage_fixture.py`,
`backend/tests/submission_fixtures.py`, `backend/tests/retained_material_fixtures.py`,
the project bootstrap helpers in `backend/tests/test_tasks.py`,
`backend/tests/projects/{policy_bundle_fixtures.py,unified_policy_fixtures.py}`,
and `backend/tests/committed_guide_fixtures.py`. Register and bind the exact POST
image before guide approval and TASK release. Preserve admitted immutable bytes
in the existing scripted provider for the test session factory, and traverse
current ART reads, grants, CHECKERS phase AUTH and finalization for both verdicts.
Do not retrofit locked policies, synthesize failed members, translate old names,
or add compatibility arguments. Consumer assertions remain independently owned.
Required real PostgreSQL controls cover failed/passing generations, currentness,
bounded history and review non-admissibility. Scripted provider evidence does
not claim MinIO or real container execution. Independent root review covers this
test-fixture author repair; production, DDL and public route changes are prohibited.

The final caller trace includes `backend/app/modules/checkers/{history.py,
execution_results.py,api/history.py}`, the existing history privacy expectation,
and `backend/tests/checkers/execution/test_storage.py`. Remove retired catalogue
message lookup and severity-policy classification from history reads. Render
bounded messages from normalized status, admit the persisted selected `error`
severity, and mark required failed image members as blocking. Keep concealed
internal findings, exact parent selectors, immutable rows and read authority.
A real failed registered-image result must be readable by both contributor and
management projections without raw image messages; the regression must fail on
the prior reader. Independent authority/architecture review checks the caller
repair. Risk remains L1; no public route or stored-data rewrite is added.

At clean `c4d590c7b706bacf926c324f587dffdaef0f4924`, the native SQL identity
substitution controls, empty-policy production request/completion acceptance,
and failed selected-result history regression passed (4 cases, 106.13 seconds).
These tests use controlled normalized image results with real PostgreSQL,
ART material and AUTH custody; they do not replace the real Rust image journey.
Restoring only the previous history reader and message table in a temporary
checkout makes the exact history regression fail with `KeyError` (42.98 seconds).
Both runs confirmed database, role and MinIO cleanup. Raw evidence is
`/tmp/pilot04-root-current-history-identity21.{log,json}` and
`/tmp/pilot04-root-history-prior-reader-mutant21.{log,json}`; the temporary
counterfactual checkout is removed. Public history schema controls passed two
cases separately. Later changes require affected evidence reconciliation.

Final cleanup also permits `backend/scripts/behavior_ownership.py`, its existing
PILOT-04 partition transition test and `.ci/behavior-ownership/partition.v1.json`.
Retire exactly the five removed checker contracts and two removed ART PRE
writers; admit only the canonical value and PRE packet owners. Regenerate the
current partition with its existing protected base. Preserve all other target
assignments and refusal of unrelated additions/removals. The focused transition
test and architecture/ownership checks verify this metadata reconciliation;
it changes no runtime behavior or test selection.

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

Refreshed frozen-head native evidence at 953e9f9ab452f982160ff12d1d8ca8794e4564bf:
production empty POST with absent external settings passed 1 test in 49.19s.
This supersedes the earlier optional-runtime sidecar whose recorded HEAD was
e7 while the author tested uncommitted changes; do not attribute that earlier
run to the later frozen commit. The configured Rust/MinIO flow also passed at
953 with the same c2d957 platform image: default and external PRE rejection,
passing atomic Submission/dispatch through POST and completion to review_pending,
restart/replay and unavailable-service recovery via fresh verified bytes. Both
isolated runners record schema0036 and completed DB/role/MinIO cleanup; runtime
remains local runc/docker-dev. Later README/roadmap reconciliation is prose-only.

Correction dispatch loads the immutable checker projection in its own explicit
root after capturing AUTH context and ending identity reads. Its product request
still starts in a fresh transaction and rechecks current manager authority before
committing or publishing. The former dependency assumed identity resolution had
left a root open: a valid detached identity and fresh request session raised
`ExternalCheckerRegistryUnavailable` before reaching either admission or denial.
The existing public manager-handoff regression reproduces that failure at
`2f1f46930` in 23.18 seconds with isolated schema `0036` and cleanup complete;
the targeted trace locates the missing registry-read transaction. Final proof
uses the normal public owner, with diagnostic exception capture removed.


### TASK/ART single execution flow cleanup

The current TASK and ART consumers now accept only the closed external POST policy
and selected PRE run custody. TASK admission/replay no longer decodes catalogue
checker content, and ART material selection requires selected PRE admission and the
exact submitted external policy. ART removed its obsolete PRE evidence writer,
invocation store, phase wrapper, old capability issuance, and durable publication
and replay branches. Immutable historical models and columns remain retained;
these are not executable checker contracts.

The selected PRE materializer still requires the committed lease, callback-scoped
genuine ART grant, exact generation/manifest/bytes and default input digest before
execution. The mounted failed-PRE projection accepts only selected execution facts
and retains the existing sanitized default and external findings. The existing
AUTH protocol fields remain stable, but runtime submission admission rejects an
old evidence-set lineage. No migration or catalogue fallback is added.

Validation at this source checkpoint: TASK/ART Ruff and Python compilation pass;
current owner/DTO imports pass. Native and broader current-flow checks remain
required after the CHECKERS composition and selected fixture repairs are combined.
This checkpoint does not claim hosted suite readiness.


### Current ART projection and runtime proof reconciliation

ART input selection now uses the single POST context identity and requires its
hash to equal the retained submitted external policy digest. Binding authority
projects the sole selected PRE run and a constant null historical evidence key,
matching the unchanged authorization protocol. The private durable put result and
publish call expose one selected run only. PRE execution input requires the lease
attempt, request digest and genuine ART grant port, with no optional old plan.

The selected PRE unit arrangement now uses canonical reservation and committed
lease facts instead of the retired plan/invocation claim. It retains real scratch
inspection and the callback grant and proves that substituting the default packet
fails before byte access or external invocation. The actual Rust end-to-end probe
constructs its registry specs from the pure external contract helper; it no longer
imports the obsolete PRE arrangement merely for a spec. The open PRE schema,
digest pinning and resource limits remain the same.

Focused selected PRE processor, current ART factory/admission publication and
short-root execution service checks pass (11 cases). Ruff and diff whitespace
checks pass. This is author verification; independent review and the final clean
combined PostgreSQL/MinIO/real-image journey remain required, as does full hosted
CI. No migration or provider proof is claimed by this checkpoint.

### Hosted selected-test reconciliation

The hosted cutover artifacts expose obsolete catalogue test callers alongside
real owner defects. This test-only repair replaces live fixture references to
removed structural request/consumer/result contracts with selected external
contracts and deletes cases whose sole purpose is built-in catalogue execution.
Immutable retained data remains; no historical runtime/DTO path is restored. Authority, full lineage, lease/lock, cleanup, rollback, exact replay and
review-source proof must remain. No aliases, fallback providers, skips, selector,
timeout, migration or production edits are allowed.

Allowed files: this record; backend/tests/checkers/execution/{support.py,
test_concurrency.py,test_coordination.py,test_execution.py};
backend/tests/checkers/post_submit/{test_requirement_dispositions.py,
test_public_boundary.py}; backend/tests/authorization/post_submit/{test_live_authority.py,
test_timeout.py}; backend/tests/test_post_submit_materialization.py;
backend/tests/test_post_submit_selection.py; backend/tests/test_agent_runtime.py;
backend/tests/tasks/post_submit_routing/{support.py,test_evaluation_guard.py,
test_evaluation_currentness.py}; backend/tests/reviews/decision/support.py.
Parent/peer owns admin permission counts, TASK port fixture wiring, current
owner corrections, compilation coordinator awaits and migration baselines.

Acceptance: updated live tests target the sole selected execution contract;
retained required checks keep their discriminating negatives; deleted obsolete
semantics have an explicit retained-proof mapping. Focused pure/current-contract
checks and native authority/material/locking cases are required, followed by the
lead's complete canonical suite. Risk is test-integrity: independent test-delta
review checks each deletion and preserves authority/evidence behavior.

Additional causal test scope (peer confirmed disjoint):
backend/tests/checkers/execution/{test_material_lineage.py,test_storage.py,
material_storage_helpers.py,storage_fixture.py};
backend/tests/authorization/post_submit/test_receipt_custody.py;
backend/tests/authorization/task_locked_context/test_visibility.py. These repair
selected result/member SQL fixture shapes and retain current closed-policy
visibility, immutable lineage and action receipt controls. The unsupported raw
envelope guard is retained at the current owner entry. Retained raw row migration
custody remains peer-owned proof.

Explicit user cleanup supersedes prior retained-runtime/decoder test preservation.
Allowed additional files: backend/tests/checkers/post_submit/support.py and
removal of test_configuration.py, test_input_bounds.py, test_request.py and
test_result_contract.py in that directory. These obsolete tests enforce removed
historical catalogue/rule request contracts, not current selected execution.
Current selected PRE/POST/default tests retain exact closed input/result bounds,
phase/id/digest/stage binding, infrastructure/work separation and no acceptance.
Stored immutable data remains; no active historical DTO/factory/terminal executor
path is recreated. The unsupported raw envelope negative retains the no alternate
execution boundary. Exact module inventory deletion is coordinated with the lead
for the final canonical exhaustive suite; no test selection/cap is weakened.

Deleted semantic families: built-in catalogue configuration/selection, old
structural request DTO field/aggregate bounds, nine-member generic result shapes,
and disabled mandatory catalogue readiness. Required current proof remains in
checkers/external/{test_contracts.py,test_policy.py,test_selected_pre_submit.py,
test_selected_post_submit.py}, checkers/default/{test_contract.py,test_execution.py} and unified
project guide compilation contract tests (unknown/stale/stage/typed config).
Authority, callback lifetime, post-I/O revocation, cleanup failure, crossed native
lineage/receipts, exact replay, complete selected member closure and review-source
mutation tests are updated rather than removed.

First focused pure scope passed 5 tests in 21.53s before the backend selected-only
API checkpoint; raw /tmp/pilot04-selected-test-pure-current.log. The wider caller
collection failure from module-level old output fixture imports is retained at
/tmp/pilot04-selected-test-pure-first.log. Full composed collection/native proof
remains required after peer source/shared fixture cleanup; this is not green CI.

The TASK-to-ART selected-source query now requires the exact immutable
selected_post_submit_policy_body. Its privacy test asserts that field is present,
while exact raw guide/review/revision policy bodies, package URI, summary and
attestation remain absent. The previous blanket policy_body substring assertion
rejected the required selected policy projection; exact project selectors and
no FOR UPDATE read contract remain unchanged.

Further current test-consumer scope, explicitly handed off by the peer: backend/
tests/checker_output_admission_helpers.py, tests/test_tasks.py,
tests/test_checker_output_custody.py, tests/test_submission_bundle_preparation_recovery.py,
tests/checkers/execution/test_completion_contract.py, removal of
tests/checkers/test_phase_service.py. The obsolete phase adapter is removed;
selected PRE ownership and selected POST consumer/current completion tests retain
phase isolation, canonical result binding and no unchecked callback shortcut.
Output reservation fixtures derive exact stored current request facts, not a
constructed unrelated catalogue request. Unsupported output access remains denied.

Further explicit lead scope: backend/tests/test_pre_submit_evidence_relock.py and
backend/tests/test_submission_bundle_admission.py; peer handoff also permits
backend/tests/checkers/external/test_selected_preparation_command.py. Remove only
old evidence writer/pass-capability publication phases. Retain current adapter,
preflight-denial-before-bytes, TASK/actor/PROJECT/grant order, root-only authority,
header/media, status projection and cleanup controls. Post-byte drift moves to
the actual selected preparation command and proves no coordinator execution or
durable intent on failed relock. Exact selected admission capability single-use,
construction/substitution and locked lineage remain in
test_selected_pre_submit_coordination.py; selected command/service and actual
root Rust/MinIO failure/replay evidence cover no admission on work/infrastructure
failure. No old writer or live historical factory is reconstructed.

The zero-member/locked-one-image direct SQL negative now binds fresh final AUTH
to the same counterfeit facts and bypasses request validation only for that
exact counterfeit, simulating a faulty application. This prevents a mismatched
valid AUTH digest from masking the locked-policy completeness guard. The normal
request validator remains active for every other result; the final positive
control uses the original complete result. No product checks are weakened.

### Selected-only migration-test caller reconciliation

Explicit lead/peer ownership permits test-only edits to
`backend/tests/checkers/execution/test_material_migration.py`,
`backend/tests/checkers/execution/test_checker_retry_migration.py`,
`backend/tests/tasks/post_submit_routing/test_requests.py` and removal of
`backend/tests/historical_checker_metadata.py` after its only caller is converted
by the raw predecessor-fixture owner. Preserve retained-row equality, failed
preflight rollback, observed migration/writer exclusion and the Operator-receipt
supersession guard. Archived JSON is updated and hashed as raw facts; current
product decoders never accept it. The live completion-denial fixture uses the
sole selected current-reference API. No production, migration, fingerprint,
workflow, cap or skip changes are allowed. Acceptance requires fresh full
collection after the peer raw producer checkpoint, focused current contracts,
and isolated native migration/SQL controls where the claim depends on Postgres.
This is author test reconciliation, requiring lead/QA review in the complete
candidate; it does not establish hosted readiness.

### Deleted-test inventory reconciliation

Lead authorizes `backend/scripts/test_lane_catalogue.py` and
`backend/tests/test_ci_lane_catalogue.py` solely to remove the five modules
deleted above: the old phase-service test and built-in POST configuration, input,
request and result tests. Remove the matching four POST exact-set entries. All
remaining modules, exhaustive discovery, ten lanes, partition algorithm, markers,
execution caps and required CI controls remain unchanged. Canonical collection
and exact inventory tests must pass; CI/test-delta reviewers inspect the deleted
module basis in the complete candidate. No current selected/default or custody
test is omitted.

The exact composed source `e8b5ae1d6f31c414f962e5bff1646788eed536fc` passed
the native locked-one-image/self-consistent-zero-member SQL control in 22.93
seconds on installed `0036`. Fresh AUTH binds the same counterfeit, SQL refuses
completed custody, all run/member/completion writes roll back, and the restored
complete result finalizes. DB, role and MinIO cleanup all passed. This closes the
focused policy-completeness proof; broader native/full hosted checks remain
required. Raw evidence: `/tmp/pilot04-selected-e8b-zero-native.log` and `.json`.
The earlier installed-function syntax failure remains a failed prerequisite
attempt, not a counterfeit-result proof.

Fresh full discovery on the raw-producer composition collected 8,731 tests with
one import error: the current default-checker test still imported its packet
from the deleted PRE DTO module. The current-consumer test scope therefore
includes `backend/tests/checkers/default/test_execution.py` for the exact neutral
`api.pre_submit_material.SubmissionPacketView` import correction only. All four
default checks and their controls remain required; no deleted DTO is restored.

### Same-count selected-result SQL identity controls

Lead authorizes two additional native controls in the already-owned
`backend/tests/checkers/execution/test_storage.py`: a self-consistent foreign
registry UUID (outer and normalized member agree) and a substituted observed
platform image digest under the unchanged locked one-image policy. Each must
first fail the real current request validator, then simulate a faulty validator
only for that exact counterfeit. Fresh final AUTH binds the same counterfeit;
forcing all deferred constraints must refuse the write, preserve run/member/
completion/audit facts on rollback, and permit the restored valid result. These
controls test SQL custody independently of the application guard. No product or
DDL edits, mismatched earlier AUTH evidence, fixture bypass, or weakened checks
are permitted; the sole migration author owns any reproduced SQL repair.

Current-consumer scan found a body-local import missed by collection: the
already-owned PROJECT post-policy PostgreSQL test patched the removed phase
wrapper as its no-execution sentinel. Replace only that sentinel with
`PostSubmissionExecutor.evaluate_post_submission`. Preserve actual approved
external policy, proposal finalization, provider/document denial, derive/approval
replay and unchanged finalization state. This is a required current isolation
control, not obsolete catalogue behavior; the old wrapper is not restored.

### Plain archived migration consumers

Lead assigns migration consumers to this lane and raw execution/base producers
to the QA/backend owners. Allowed test paths: execution/test_material_migration;
authorization/post_submit/test_migration; tasks/post_submit_routing/{test_migration,
test_outcome_migration}; reviews/{packet,decision,acceptance,lifecycle}/test_migration;
contributions/records/test_migration; the existing reviews/acceptance and
contributions/records historical_support helpers; and one migration-only
`backend/tests/migration_ancestor_rows.py` for literal ancestor queue, lease,
packet and Review rows. Keep these separate from current packet/review fixtures.
No dict-versus-current compatibility switch, old model facade, archived service
subprocess, production or migration edits are allowed. Plain request/result/
material/lease dictionaries and direct SQL carry predecessor facts only. Preserve
retained-row equality, immutability, preflight refusal and observed writer locks;
current public/native tests own current execution and economic behavior. Risks
remain L1 fixture/custody reconciliation, requiring QA/test-delta review, fresh
collection and discriminating native predecessor checks before readiness.

The raw migration consumers no longer call the current packet fixture's alternate
factory hook. Its now-unused `completed_source_factory` parameter is removed from
`backend/tests/reviews/packet/support.py`; the current fixture always uses the
same canonical `completed_source`. This exact helper cleanup adds no raw/current
switch, changes no current source behavior and retains all current packet tests.

The two identity controls reproduced missing native custody at clean `154062bde`:
all deferred constraints accepted the foreign registry UUID and image digest
while the current request validator rejected them. Both failed with the intended
`DID NOT RAISE` in 62.64 seconds, with complete resource cleanup. The sole schema
author supplied the exact policy identity guard; the controls now pin its
`checker terminal selected policy differs` message and SQLSTATE `23514`, not an
unrelated integrity error. Affected native replay follows that frozen DDL; the
original failed evidence is retained.

### Current external-policy and normalized-verdict consumers

Lead/QA handoff permits current caller changes in
`backend/tests/projects/post_submit_fixtures.py`, actual test bodies only in
`backend/tests/test_tasks.py`, `backend/tests/authorization/task_authority/test_submission_policy.py`,
`backend/tests/tasks/test_project_display.py`, `backend/tests/tasks/test_locked_context.py`,
`backend/tests/authorization/submission_history/{test_reads,test_privacy}.py` and
`backend/tests/test_review_queue_persistence.py`. QA owns producer/helper definitions
and the registry-before-activation bootstrap. Use explicit approved image specs
for work-failing/member-visible fixtures and normalized passed/failed verdicts;
never translate old built-in names or create failed evidence under an empty policy.
Remove only obsolete platform catalogue assertions, retaining exact locked policy
identity, corrupted-read refusal, zero effects, privacy, parent isolation, stable
successor display and current generation guards. Current registered capabilities
replace old catalogue labels in summaries. No source, migration, CI, cap or skip
changes are authorized. Native verification follows combined QA producer freeze.

### Remaining raw migration callers

Lead authorizes the final caller paths: `backend/tests/tasks/test_payment_policy_migration.py`,
`backend/tests/tasks/test_submission_lineage.py`, `backend/tests/checkers/execution/test_migration.py`
and `backend/tests/tasks/post_submit_routing/test_migration.py`. The literal
base handoff also requires the single admission-ID dictionary access in
`backend/tests/tasks/submission_dispatch/test_migration.py`. Replace attribute
access over archived request/result facts with dictionary indexing. The packet
custody upgrade uses the literal revision-0021 Submission snapshot supplied by
the backend owner, never the current preparation callback on a predecessor
schema. Preserve every retained-row, preflight, immutability and negative
assertion; no production, producer, migration, compatibility helper, test cap or
selection changes. Collection and native predecessor proof follow the frozen
literal-base handoff. Both strengthened identity controls passed at exact
clean `e947161412b1a7dcc85ffcb0a7bac75922c4cab8` in 34.94 seconds with the exact
guard message and SQLSTATE `23514`, installed schema 0036 and complete cleanup.
Plain archived material supplies its semantic manifest digest; the payment
migration uses the canonical session engine, without reintroducing fixture DTOs
or engine facades.

The frozen literal-base handoff removes unused `provision_checker` keywords
from the owned execution/material/AUTH migration tests. The existing
`backend/tests/contributions/records/historical_support.py` selects the explicit
paid snapshot for the actual installed predecessor revision (0015, 0018 or
0024) through the canonical session owner. Its unused award-shape and arbitrary
option parameters are removed: unsupported shapes fail at the function boundary,
not by silently dropping requested awards. Preserve the two/four exact award
assertions and complete/incomplete retained-award refusal; no runtime policy or
award synthesis, producer, schema or test-selection changes.
The same owned raw migration files remove the obsolete current-writer seeding
column/restore calls and imports. Literal snapshots must load into the exact
installed predecessor schema, without temporary current ART/remediation columns.
Every migration assertion and row/custody/lock check remains in place; the shared
helper owner removes unused definitions after its remaining consumers are traced.

### Scratch format cutover cleanup

User explicitly requires no backward compatibility in the selected checker flow.
Allowed files: `backend/app/modules/artifacts/preparation.py` and
`backend/tests/test_artifact_preparation.py`. Remove the superseded scratch marker
upgrade, version-2 ledger coercion, and their upgrade-only test. Retain current
marker/ledger validation, concurrent initialization, bounded scratch custody and
restart recovery. No retained business data, authorization, migration schema,
provider runtime, CI selection or resource limits change. Verify the full scratch
preparation test module and independent affected source review before readiness.

The same cleanup authorizes deleting the now-unused `add_current_art_seed_column`
and `restore_predecessor_evidence_schema` functions from
`backend/tests/migration_fixtures.py` after the raw callers were reconciled.
A repository search found no remaining callers. The separately consumed project
guide fixture context remains unchanged; no shared live consumer is deleted.

The first scratch-module run passed 93 current cases and exposed one remaining
obsolete version-two normalization test. Remove that upgrade-only test as part
of the same authorized cutover; rerun the complete current scratch module.

### Retained dispatch upgrade assertion reconciliation

The composed native batch passed three retry/replacement migration controls and
exposed the dispatch test's outdated additive-column assertion after upgrading
to current 0036. In `backend/tests/tasks/submission_dispatch/test_migration.py`,
replace the single 0034-column allowlist with the exact 0034/0036 columns on
Admissions, Submissions and CheckerRuns. Every added value must remain NULL;
all retained rows/values, counts, authority and no-dispatch assertions remain
exact. No automatic/dynamic column exclusion, backfill, schema change, relaxed
selection or skip. Rerun the failed node and independently review the delta.

### Archived project ownership query

The native paid-0018 discriminator at clean `70424eedb` passed archive and checker
source preparation but stopped on a fixture assumption that Submission stores a
project ID. The raw ancestor query now joins its stored TASK for that field,
matching the schema owner without a request fallback or invented column. Every
remaining Submission field used by this helper is checked against the canonical
model. All migration assertions and actual SQL guards remain unchanged; only the
same paid discriminator is rerun after this repair.

### Retired PRE database write refusal

The current-schema cutover now refuses every new write through the retained PRE
attempt/evidence tables while preserving their immutable rows for historical
inspection. New bundle intent and admission rows must carry selected PRE lineage;
valid archived evidence can no longer open the removed writer path. The five
legacy trigger functions are reduced to unconditional SQLSTATE 55000 retained-data
refusals, so no catalogue reconstruction or attempt-completion implementation
remains executable at the current head. An archived 0034 source regression clones
each old row shape and proves intent, admission, attempt, evidence, result and
attempt-update refusal with byte-exact retained-row equality. The installed-body
test validates every PL/pgSQL function and asserts these functions contain only
the refusal contract. A fresh PG16 install reached the canonical fingerprint
boundary after all function validators and measured
`f510310623f222209cbbee89291edb8e1582d65ddaf9d173d534dd796ab68991` in
199.51 seconds; isolated database, role and MinIO cleanup all completed. This
measurement used the uncommitted repair tree and is fingerprint evidence, not a
frozen-head positive runtime claim. Current selected PRE/Submission/POST native
flow must pass again after integration.

### Archived terminal member envelope

The literal terminal fixture now encodes raw archived member columns with the
required `post_submit_structural_result` protocol tag, matching the predecessor
0008 SQL reconstruction. Supplied counts, routing, severity and material remain
literal; a conflicting supplied tag refuses. The pure bare-member control passes
and fails on the prior helper at the intended envelope equality assertion.
Ruff and diff checks pass. This repairs fixture serialization only; the completed
0008 native migration discriminator remains required before claiming that path.

### Captured service principal prerequisites

The static predecessor archive now carries the exact project-neutral POST service
actor `01a13047-9e70-7b29-a0c9-f30981caec3b` and active identity link
`01a13047-9e71-7f5e-88ea-ee2d1b04ac68` in the 15 applicable 0010-through-0024
snapshots. Both rows were captured by writer `926b4ef118db3708e50d1869db5ee78a79e5b5de`
in the named `0034_checker_retry_source` snapshot; provenance therefore describes
these snapshots as composite captures rather than claiming every row came from
one fresh database. No retry run, audit, grant, receipt or project-bound row is
copied. A decoded old/new comparison proves exactly 30 supplemental rows and
identical seeds, revisions, tables and values everywhere else. The archive is
checksum-bound at `25560b75796f84cff46bb506abdcd4b9cc2b7535411096fdbbec921d245d95e9`.
This supplies a retained predecessor identity prerequisite; canonical migration
and receipt proof remains required.
