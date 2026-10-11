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
grant, and the exact four-behavior Workstream default checker. The selected PRE
processor now runs the default before each locked external image over one
genuine prepared-ART callback, but its durable result and admission caller are
not selected yet. The admission binder now carries an unchanged byte/manifest
comparison into the default checker with exact predecessor and current locked
rules instead of treating that default behavior as an early ART rejection.
The selected result contract now has one canonical digest over the default,
ordered external results and observed isolation, plus a database-timed lease
and terminal latency body suitable for the durable owner. Its reservation
digest binds the contributor identity, TASK/assignment, genuine ART attempt
and prepared generation, approved policy/default, complete default input and
server-owned archive/manifest identity before the lease is issued.
The selected durable owner is now modeled separately from the retained legacy
evidence decoder: its UUIDv7 run identifier is the genuine PRE attempt identity,
so selection does not reserve through or foreign-key to the obsolete invocation
store. The coordinator takes TASK custody before CHECKERS state, issues a
database-timed generation lease, finalizes one terminal body, and mints a
process-local one-use admission capability only for a complete pass. Its
ordered work budget is derived from the default plus each locked image deadline
and service cleanup margin and must fit ART's configured custody deadline.
The selected execution workflow now prepares fixed-service authority before
TASK/CHECKERS locks, commits the database-timed lease before exposing material,
executes through one exact process-local ART capability with no transaction
open, then uses a distinct short root to authorize and finalize the exact result
or one closed recoverable infrastructure outcome.
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
for a selected request. Native SQL custody and the live worker journey remain
unfinished.
Production still uses the older pre/post catalogues.

## Bounded change

### Allowed

- This record and affected current PILOT-04 architecture, roadmap and owner docs.
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
compatibility runtime.

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

- [ ] Approval binds the default behavior digest and every project binding to
  an exact immutable registry row, phase, image, schemas, configuration and
  limits; substitutions and stale approvals fail closed.
- [ ] Activation enforces exact F-020 requirement/stage/generation coverage and
  retains false-policy and warning-acknowledgment guards.
- [ ] F-020 recovery is proven by register -> recompile -> approve -> activate
  in one current generation; registration alone and wrong generation, stage,
  requirement, registry digest or stale approval remain blocked.
- [ ] ART verifies server receipt identity and a bounded safe manifest before
  any project image reads material.
- [ ] The default checker runs exactly four blockers; absent summary and
  attestation remain warning-only.
- [ ] Every required pre image passes before admission consumption. Work
  findings create no Submission/dispatch and keep the task `in_progress`;
  infrastructure failures remain recoverable and consume no attempt.
- [ ] Passing preparation invokes the existing caller-owned atomic operation
  and commits Submission, `evaluation_pending` and initial dispatch together.
- [ ] Required post images consume immutable Submission custody, persist
  normalized evidence and never decide acceptance.
- [ ] Timeout, cancellation, crash/restart, changed policy/material,
  cross-project access and duplicate delivery cannot create partial effects;
  latency and queue/execution lineage are retained, and restart requires fresh
  server-verified uploaded material rather than a reconstructed scratch handle.
- [ ] Retained old evidence remains readable without rewriting hashes; unresolved
  old execution cannot cross into the new runtime and requires authorized policy
  transition.
- [ ] Both obsolete catalogues, implementations, callers and obsolete tests are
  removed without a fallback or parallel runtime.
- [ ] A real PostgreSQL 16, MinIO and Rust-service journey proves pass, work
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
| Selected POST scheduler compatibility | `pytest -q backend/tests/checkers/external/test_selected_post_submit.py backend/tests/checkers/execution/test_results.py backend/tests/checkers/execution/test_completion_contract.py backend/tests/checkers/post_submit/test_request.py backend/tests/test_submission_bundle_admission.py`; focused Ruff | 82 passed; one discriminated owner accepts retained legacy and selected request/result envelopes, selected leases cover the ordered image budget and finalization margin, ART recomputes the selected manifest, and the exact result envelope remains the replay authority | Production outbox registration, native selected columns/constraints and live Rust worker proof remain pending |
| Production delivery registration and owner boundaries | `pytest -q backend/tests/architecture/test_module_boundaries.py backend/tests/test_artifact_architecture.py backend/tests/outbox/test_contracts.py`; focused Ruff and a direct registry construction probe | 116 passed; the existing production outbox registry exposes assignment invalidation and evaluation request handlers, selected Rust configuration is lazy, and PRE coordination stays behind CHECKERS' public adapter root | Database-backed legacy/selected delivery and worker restart proofs remain pending |
| Owner/caller trace | PROJECT approval/activation, ART preparation/admission, TASK composition and CHECKERS dispatch | In progress | Persistence delta and migration ordinal await actual linear predecessor |
| End-to-end replacement | Real PostgreSQL/MinIO/Rust public and worker journey | Not run | Implementation incomplete |

## Reconciliation

- Current-source reconciliation: implementation starts at PR538 head
  `7453a0d8c5664cfd486872a381899f3755393004`; final publication will reconcile
  actual merged `main` and intervening owners.
- Next usable boundary: full selected checker journey; no component-only merge.
- Remaining risks: exact durable external pre-attempt/result projection may
  require a successor migration. Numbering and fingerprints resolve only
  against the actual linear graph; no competing ordinal is reserved here.
