# Public guide input to governed contribution proof

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Replace the approved-guide shortcut in the bounded public runtime drill with public guide upload, asynchronous setup, separate manager approvals and exact policy activation, preserving both outcome branches.

## Intent

Issue #552 closes the integration gap between existing guide setup and the public
contributor journey. The first usable v0.1 path must start with original guide
bytes and task examples, not injected approved policy rows. This is integration
proof and owner-scoped defect repair, not a new setup or acceptance subsystem.

## Starting behavior

The starting base `82a46ff3c` included #549 public intake and #550 false-guide
activation; reconciliation now includes main `2c1f7517c` and #570 CLI submission.
`experiments/pilot04_external_checker_runtime/run_public_journey_probe.py` runs
real API, MinIO, Redis, prefork workers, Beat and external checker images, but
`_one_mode` arranges compilation and approved policy facts through `source_case`.
`backend/scripts/guide_document_api_drill.py` covers real public upload and live
setup separately. `backend/scripts/guide_compilation_e2e.py` provides a scripted
external runtime behind the canonical adapter port. Neither composes the whole
journey from public source documents to contribution facts.

## Bounded change

### Allowed

- `experiments/pilot04_external_checker_runtime/run_public_journey_probe.py` and
  narrowly scoped companion guide-input/runtime helpers in that directory:
  replace fixture setup, retain downstream custody/outcome assertions.
- `experiments/pilot04_external_checker_runtime/README.md`: exact invocation,
  input, evidence, resource cleanup and limitations.
- `backend/scripts/guide_compilation_e2e.py` only where sharing existing scripted
  provider behavior avoids duplicate source/custody rules; callers must retain
  their current supported contracts.
- Focused drill tests under `scripts/test_public_guide_journey*.py` or existing
  affected test owners; root tests must not silently require a backend install.
- This record, README, affected current roadmap and ARCH/POL navigation: connected
  local proof versus hosted deployment and held evaluator work.
- Product fixes only after a concrete integration failure is reproduced and its
  exact owner/files, requirement and discriminating regression are added here
  and reviewed before implementation.

### Not allowed

No direct guide, compilation, policy, activation, Task, Submission or acceptance
fixture writes for the connected setup path. No weakened AUTH/custody guards,
new approval semantics, fallback routes, provider discovery, live model claim
from recorded output, private project documents, CI gate changes, evaluator
expansion, payment delivery, contributor lease work, frontend or CLI work.
Checker registry, initial identity/service provisioning, and the existing project
points unit plus AUTH-governed adapter binding remain explicit isolated
infrastructure preconditions. They cannot supply guide/policy facts, create
awards, activate fulfillment, or justify new public routes.
Held #492/#493/#496 remain held. Security #565 and pagination #497 are separate.

## Design and decisions

Extend the existing real runtime drill; remove its superseded approved-guide
bootstrap mode rather than maintain parallel fixture/public journeys. Use only
synthetic shareable guide originals with at least one meaningful task example.
Exercise actual Celery delivery and the canonical runtime adapter port with an
explicitly recorded test provider in the isolated worker entry point. The
production composition must not gain a test switch or fallback constructor.
The recorded provider opens exact ART-granted documents and returns the existing
closed proposal schema; production owners perform compilation/finalization.
The recorded provider must observe the exact normalized task examples, not
merely read documents. Assert their retained hash on the guide and source
snapshot, and bind the runtime-observed full input to the stored compilation
input hash (raw compilation context is not stored).
Public reads supply every manager decision target. Public PUT review-policy and
revision-policy operations set the exact true/false and revision configuration
with If-Match and idempotency headers; replay preserves their identity and a
stale selector cannot mutate them. PRE approval and POST approval remain
separate; Finance publishes ContributionPolicy through its
public owner and PM activates the exact context. Existing downstream public
claim, preparation, submission, selected POST, retry/replay and outcome proof
remain authoritative.

Use read-only database observations to prove complete lineage and no premature
or duplicate effects. An optional provider suggestion is advisory; a required
unsupported capability cannot silently disappear or authorize activation.
Insufficient source and provider failure must remain distinct. Prefer existing
owner tests for already-proven negative boundaries, adding only missing
connected proof and regressions for discovered defects.

## Acceptance criteria

- [x] Original guide upload and task examples drive real async setup; no direct
  compiled/approved/active row insertion supplies the public journey.
- [x] Setup stops at proposal; independent public PM PRE/POST approvals and
  Finance publication precede exact public activation, including replay.
- [x] Original task examples and their normalized hash/snapshot commitment
  reach the actual worker runtime unchanged.
- [x] Source document, setup/proposal, policies, activation, Task, Submission,
  checker and outcome identifiers/hashes form one exact retained lineage.
- [x] Default true reaches `review_pending` without acceptance/economic facts;
  false reaches exactly one shared FinalAcceptance and submitter contribution
  with the applicable awards, no fabricated Review/reviewer contribution.
- [ ] Insufficient source, provider failure, required unsupported capability,
  correction, stale completion, cross-project access and replay have explicit
  authoritative proof; new integration defects have discriminating regressions.
- [x] Real runtime cleanup releases every owned database, storage prefix,
  scratch area, worker, broker and subprocess; failure is bounded and reported.

## Risk and review routing

- Risk class: L1, cross-owner integration proof using real policy/AUTH/runtime.
- Required reviewers: architecture/security; QA/test_delta; documentation and
  product_ops for source-to-outcome scope and claims. CI integrity only if an
  actual gate change becomes necessary (not currently allowed).
- Human review focus: no fixture shortcut, real async execution, exact locked
  lineage, independent approvals, realistic outcome proof and honest limits.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing shortcut identified | `_one_mode` and guide API drills inspected | Confirmed and removed | Partial public runs exposed the bounded repairs below |
| Connected journey | Clean `f197b7b84` isolated public journey, recorded inference | Passed both outcomes, correction, replay/restarts, late revocation and cleanup | No hosted Flow/S3/gVisor or live model claim |
| Failure boundaries | Existing owner tests plus focused new drill tests | Connected failure cases passed; uncertain-recovery authority regression repair pending | Exact nodes mapped below |
| Repository integrity | Lint, boundaries, links, Commitrail, full hosted CI | Scoped checks passed; final hosted completeness pending recovery-test repair | No sampling or weakened gates |

## Reconciliation

- Current-source reconciliation: main `2c1f7517c` includes #550 and #570. The
  manifest renewal/replay guarantees and the CLI's explicit submission and
  findings surface are preserved. Parallel #565/#497 own their separate
  branches and PRs; the existing CLI agent owns #499.
- Next usable boundary: #555 hosted operation and pilot after connected proof.
- Remaining risks: Recorded inference proves integration, not model quality;
  local identity, MinIO and development container isolation are not deployment.

## Compilation phase lock repair

The connected run on `175551c19` reached real setup execution and reproduced a
second PostgreSQL `40P01`: public diagnostic reading held Project and waited for
Guide, while accepted-result persistence held Guide and its compilation INSERT
waited for the Project foreign key. Both isolated database and MinIO cleanup
completed. Reservation-only proof does not establish the remaining phases.

The reviewed repair extends the same order across mutation roots:
AUTH actor/link, Project, Attempt/request, Guide/Setup, then child writes.
Additional allowed files are
`backend/app/modules/projects/guide_compilation/repository.py`,
`backend/app/modules/projects/guide_compilation/projections.py`, and
`backend/tests/projects/guide_compilation/test_live_cutover_postgresql.py`.
The already allowed compilation service performs current execution preflight
before the existing Project lock and exact child-lineage locks for fence,
accepted/invalid result recording and persistence. Result-bound prepare/consume
remains after exact facts are locked. Projection and finalization already prepare
AUTH first; their existing shared lock routines acquire Project before children.
The shared finalization reader also serves prepared proposal mutations. No
manifest or read-only execution-state reader gains mutation authority or a new
lock order; no 503 retry conceals a deadlock.

Required proof pauses each of compilation persistence, sufficiency projection
and finalization before its child INSERT, starts an authorized public setup read
in an independent session, observes the worker blocking that read, then requires
both operations to finish with one retained result chain. Removing the execution
Project lock must make the persistence case fail at its intended completion
assertion. Existing reservation, manager-read, replay and revocation proofs remain
required, followed by the full connected runtime. Architecture/security and
QA/test-delta review must cover the combined ordering, including shared callers.

### Recovery replay test correction (QA-567-RECOVERY-001)

The authorized PostgreSQL recovery test still encoded a superseded pre-cutover
assumption that uncertain replay bypassed AUTH. The bounded test-only repair may
change only
`backend/tests/projects/guide_compilation/test_authorized_recovery_postgresql.py`
and this record; production code, CI, specifications, and other support remain
unchanged.

The corrected proof must use the real fixed-service execution composition and
fresh preflight on every fence boundary. The first fence permits dispatch; an
authorized restart returns the same receipt with dispatch prohibited, stages no
new execute audit evidence, and leaves the request operation, attempt,
compilation, outbox, and uncertain-attempt facts unchanged. A discriminating
real-PostgreSQL case revokes the fixed-service identity link after the first
fence and requires uncertain replay to raise the public authorization denial
while retaining the same uncertain facts and zero new effects. Fixture teardown,
not an invented reactivation, ends that scenario. Focused real-PostgreSQL proof
plus QA/test-delta and security review are required; no fallback, AUTH bypass, or
status-only fast path is admitted.

## Focused failure-proof map

All paths below are relative to `backend/tests/`. Run named existing nodes with
`.venv/bin/python -m scripts.run_isolated_tests --metadata-json
/tmp/ws552-owner-proof.json --timeout-seconds 600 -- .venv/bin/python -m pytest -q tests/<node-path>`
from `backend/`, with the supported isolated PostgreSQL/MinIO environment. No
existing node is counted as connected public proof merely because it passes.

| Boundary | Exact existing proof or planned connected observation | Expected effect boundary |
|---|---|---|
| Insufficient source | `projects/guide_compilation/proposals/test_postgresql.py::test_blocked_result_allows_correction_but_never_approval` | Blocked report, no approval; a canonical correction successor is permitted |
| Uncertain provider | `projects/guide_compilation/test_hidden_orchestrator_postgresql.py::test_uncertain_provider_failure_never_redispatches` | PROVIDER_UNRESOLVED, one provider call, no invented success |
| Accepted-result recovery | Same module `::test_accepted_result_recovers_without_a_second_provider_call` | Existing retained result resumes without additional inference |
| Required missing capability | `projects/guide_activation/test_postgresql.py::test_checker_registration_requires_corrected_approval_before_activation` | No activation until registered implementation, corrected proposal and separate approvals |
| Stale completion | `projects/guide_compilation/test_live_cutover_postgresql.py::test_stale_delivery_rejects_before_any_compilation_effect` | Before provider/configuration and before new audit/product effects |
| Foreign-project reads | `projects/guide_compilation/proposals/test_public_api.py::test_public_package_denies_other_roles_and_scopes` | Public concealed denial under wrong grant/project |
| Exact examples | `projects/guide_compilation/test_task_examples_postgresql.py::test_required_examples_reject_before_product_effects_then_exact_replay` plus new connected runtime comparison | Missing examples deny; normalized examples/hash reach worker unchanged |
| Connected correction/replay | Planned `_public_guide_setup` in the updated runtime drill: one real PM correction, explicit dispatch, successor read, old-result preservation and exact request replay | Generation advances only once; source document/example commitment remains exact and stale source approval cannot activate |

Run the extended real runtime proof using the existing isolated runner with
`python ../experiments/pilot04_external_checker_runtime/run_public_journey_probe.py
--image-reference <owned-digest> --service-binary <built-local-service>
--broker-url <owned-loopback-redis> --work-dir <private-disposable-directory>`.
Its two branches cover source upload, worker setup, public policy configuration,
separate approval/publication, activation and downstream outcomes. This is an
explicit recorded-provider local drill; #555 retains live hosted-provider proof.

## Plan-review corrections

The first review identified omitted compensation infrastructure prerequisites,
public review/revision policy configuration, exact task-example observation and
an insufficiently specific negative-proof map. The plan above now specifies
all four; no production code was changed before resolving them.

## Connected-drill defect repair

The isolated connected drill reproduced PostgreSQL SQLSTATE `40P01`: the
public latest-setup read held Project and waited for Guide, while compilation
reservation held Guide and its attempt INSERT waited for the Project foreign-key
lock. This is a product defect, not an inference failure.

Additional allowed files are
`backend/app/modules/projects/guide_compilation/service.py` and
`backend/tests/projects/guide_compilation/test_automatic_request.py`.
Use the existing ProjectRepository parent lock after prepared AUTH and before
Guide/Setup admission. Both automatic and correction requests use that
transaction; durable replay retains its existing authority validation. Do not add a Project lock
to the shared manifest reader or weaken diagnostic/AUTH locks.

The focused PostgreSQL regression pauses real attempt reservation immediately
before INSERT, starts the authorized public latest-setup read, observes its lock
wait from an independent session, then releases reservation. Both operations must
finish, with one attempt, one request operation and one request authorization
event. Removing the parent lock must make that same scenario fail. Inspect shared
request/replay consumers for ordering conflicts; preserve caller transaction and
exact replay behavior.

Separately, the drill poller must observe the existing in-flight
`provider_outcome_unresolved` marker until completion or its bounded deadline.
It must not retry HTTP 503 or other terminal errors. Focused pure tests cover
in-flight completion, bounded unresolved state and propagation of real failures.
This repair retains the original L1 reviewers and introduces no new subsystem.
The bounded plan replay passed before implementation; final code review remains
required after PostgreSQL and connected-runtime proof.

## Focused repair verification

The isolated PostgreSQL automatic-request module completed 29 tests, including
concurrent public latest-setup observation, replay, revocation and request custody.
Database and MinIO cleanup completed. The pre-repair-method probe reproduced the intended deadlock/503 failure with
cleanup complete. The connected runtime rerun stopped at external service health
before product operations; this focused result is not full journey proof.
The pure drill tests passed five cases, including source commitment substitutions
and bounded observation without hiding terminal errors. Initial hosted
`project_lifecycle_a` exceeded its 1,200-second bound, so full-suite evidence is
incomplete and must be refreshed on the repaired candidate.

## Lock-order review correction

The first repair passed the automatic-service regression but put Project before
AUTH. Focused architecture review traced a same-manager inversion against existing
AUTH-first guide/policy mutations. It also confirmed public diagnostic reads lock
that same actor after Project. The final bounded correction must therefore align
both paths as actor/link authority custody before Project before Guide/Setup.

Additional allowed files:
- `backend/app/modules/authorization/kernel.py`: a narrow serialized-admin-read
  actor prelock, using the existing owner repository; no authorization decision,
  authority token, bypass, or cached grant is issued.
- `backend/app/modules/projects/authorization_reads.py`: invoke that prelock
  before diagnostic parent locks; retain final `require` on exact locked facts,
  current grant validation and transactional authorization evidence.
- `backend/tests/projects/diagnostic_read_fixtures.py` and
  `backend/tests/projects/test_diagnostic_read_composition.py`: update the owner
  fixture and prove prelocking cannot substitute for final authorization.
- The already allowed automatic-request test module: add real same-manager
  guide mutation versus public diagnostic-read concurrency, observe the
  intermediate actor-lock wait, and prove omission of read prelocking recreates
  the deadlock. Retain automatic reservation concurrency and revocation proofs.

Existing human mutation ordering remains unchanged. No shared manifest reader,
policy, action availability, or authorization permissions change. The narrow
review recommendation above supersedes the earlier Project-before-AUTH plan.

## AUTH structural repair

CI caught pre-lock growth in the oversized authorization kernel while checking
the lock-order correction. This bounded repair extracts the existing
project-manager preparation without changing its lock order, control-lock rule,
allowed role or exact-project guard.

- Allowed files: `backend/app/modules/authorization/kernel.py`,
  `backend/app/modules/authorization/prepared_admin_authority.py`, the generated
  `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`, and this change record.
- Prohibited changes: authorization policy, action classification, lock order,
  role or scope semantics, test-structure thresholds, validator behavior,
  exceptions, and new compatibility paths or aliases.
- Acceptance: `lock_project_manager_authority` has the same call shape as the
  existing admin locker; a kernel-local fail-closed selector admits only the
  current admin-mutation and guide-bound manager action sets; `_prepare_prelocked`
  uses one uniform locker call; the superseded method is removed; both the
  kernel file and frozen `_prepare_prelocked` debt genuinely shrink; generated
  debt inventory and focused authority behavior remain in parity. The diagnostic
  actor prelock is the module-level AUTH function
  `prelock_serialized_admin_read_actor(authorization, action_id)`, retaining its
  closed read-action check and human actor/link lock without expanding the
  kernel's public class-method contract or issuing a decision, token or grant.
- Risk remains L1 because authorization locking is touched. Architecture and
  security review from the parent repair remain required; add focused CI-integrity
  review for the generated debt transition. QA/test-delta, documentation and
  product-operations review remain attached to the parent change.
- Human review focus: source-equivalent lock/control/grant ordering, the closed
  selector union, unchanged guide-manager denial semantics, genuine debt shrink,
  and no CI policy relaxation.

The approved plan is to move `_prepare_project_manager` unchanged into the
existing prepared-admin authority owner as `lock_project_manager_authority`,
then select it or `lock_admin_mutation_authority` through
`_prepared_admin_role_locker(action_id)`. Unknown actions raise `ValueError`
before any repository access. Existing public prepared consumers continue to
enter through `_prepare_prelocked`; no separate method consumer or alias remains.
The project diagnostic caller switches directly to the module function in its
separately owned integration delta; no compatibility class method remains.
The structural validator, focused pure prepared guide/compilation authority
tests, compilation and lint provide local evidence. Focused PostgreSQL and
CI-integrity review run after integration with the lead candidate.
This extraction changes no capability, exposure or delivery claim in
`docs/roadmap_status.md`, so the roadmap needs no edit for this scoped commit.

## Integrated repair proof

The clean `3dde907f3` repair passed five independent-session PostgreSQL races:
request reservation, same-manager guide mutation, compilation persistence,
sufficiency projection and finalization against the public latest-setup read.
Removing only the execution Project lock reproduced PostgreSQL deadlock and
failed the persistence case's HTTP 200 assertion with HTTP 503. Both runs
completed database and MinIO cleanup. The diagnostic and strict-kernel contract
selection passed 28 tests; structural-debt and module-boundary validation, lint,
links and stale-wording checks passed without policy or gate changes.
Focused architecture/security, QA/test-delta and CI-integrity reviews accepted
the bounded repair. This is not a passing connected-journey result: both complete
outcome branches and fresh hosted completeness remain required.

Reconciliation with #570 retains its CLI navigation and this change's ARCH
navigation; README and roadmap retain both changes. Backend code and tests are
unchanged by that merge. The next complete runtime proof uses the reconciled
candidate, and review must distinguish that proof from the earlier failed runs.

The reconciled runtime passed setup finalization, then correctly denied the
proposal read because its manager fixture had only system-scoped authority.
Proposal review, correction, approval and activation require an exact-project
manager grant. The initial authority fixture now grants that same manager the
created project's scope before setup; no product authorization rule changes.
This remains within the declared identity/grant infrastructure preconditions.
The failed run completed database and MinIO cleanup and is not success evidence.

## Current documentation reconciliation

The connected drill replaces the approved-guide fixture; reconcile current
canonical descriptions in the glossary, architecture lockdown/brief/system map,
product brief and user flows, project and authorization operating manuals,
checker architecture/specification/template, Task and artifact specifications,
current-system HTML diagram, roadmap and ARCH chunk map. These documentation
paths are allowed for this correction. Preserve explicitly historical proof at
`d5703d9c6`; recorded inference is not live model or hosted deployment proof.
The latest bounded run reached both outcomes but expired during final late-
revocation restart verification. Database and MinIO cleanup completed; owned
API/Celery children were stopped. It is incomplete evidence, not a full pass.
The next unchanged-runtime run receives a larger outer local-run allowance for
this loaded host; product deadlines, assertions and hosted CI limits are unchanged.

## Connected composition proof

The complete isolated invocation exited **0** at clean commit
`f197b7b8482eee6c2578217f434d90ad3a11c9b7`. The command described above used
a 3,000-second outer local-run allowance without changing product deadlines,
assertions or hosted CI limits. Its evidence is `/tmp/ws552-run-9.log` and
`/tmp/ws552-run-9.json` in the local review workspace.

- Public original upload, exact task examples, recorded inference through real
  Celery, a manager correction, separate PRE/POST approvals, Finance publication
  and guide activation all executed through their declared owners.
- The human-policy branch retained two Submissions and reached `review_pending`,
  with zero Review, FinalAcceptance, ContributionRecord or award facts.
- The automatic branch retained one Submission and reached `accepted`, with
  exactly one FinalAcceptance, submitter ContributionRecord and project-points
  award, and zero Review. The public contribution read matched the retained source
  and seven-point award.
- Failed intake, post-check remediation, exact replay, duplicate completion,
  prefork restart/recovery and late routing-authority revocation passed. The
  revoked completion dead-lettered without effects and preserved prior acceptance.
- Database and MinIO cleanup flags are true. The successful drill stopped its
  owned API, Celery and checker service; an independent process check found no
  remaining run-specific API/Celery processes. Run 8 required manual orphan
  process cleanup after its timeout and remains explicitly incomplete evidence.

This proves the local composition with recorded inference and development
containers. It does not prove model quality, hosted identity/S3/gVisor operation,
CLI continuation, live human review or payment fulfillment. Final test-only
repairs and documentation changes must preserve this runtime/product source
identity or receive new affected execution proof.
