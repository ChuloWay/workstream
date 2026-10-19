# PILOT-06B — Terminal benchmark negative runtime proof

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: The existing terminal-benchmark runsc proof executes PRE-valid negative packages for no-op, reference failure, reference instability, forced memory exhaustion and a capacity-spoof control, while every nonzero fixed-recipe builder exit is classified as infrastructure or capacity rather than contributor work.

## Intent

Close the remaining #493 evidence gap without adding another runner. The merged
checker already proves one successful package and service-interruption cleanup,
but its hosted matrix does not execute the retained negative result paths or a
forced memory limit. This change extends that same isolated, offline runsc
proof so #555 can consume real outcome evidence rather than helper-only result
mapping.

## Current behavior

- `external_checkers/workstream-terminal-benchmark-checker/src/main.rs` admits
  only one byte-exact Dockerfile: pinned Python base, fixed directory setup,
  `COPY workspace/`, and a non-root final user. POST projects only
  `.dockerignore`, that Dockerfile and `workspace/program.py`; no submitted
  build instruction remains.
- `external_checkers/workstream-checker-service/src/terminal_benchmark.rs`
  currently maps a non-capacity Kaniko exit to the completed work finding
  `build_failed`. Under the admitted recipe, that exit cannot be attributed to
  a contributor-controlled build step. Base/cache/runtime/storage faults are
  infrastructure or capacity.
- `experiments/terminal_benchmark_project_checkers/proof.sh` executes one
  interrupted and one successful `ledger-reconcile` POST through the existing
  isolated DIND/runsc service. `build_matrix.py` and `verify_evidence.py` bind
  exactly those attempts and their fixed evidence inventory.
- The public corpus already contains a starter that fails and a reference that
  passes. Its native calibration includes an ineffective-test mutation, but
  that mutation has not run through the real container service.

## Bounded change

### Allowed

- This standalone Commitrail record.
- `external_checkers/workstream-checker-service/src/terminal_benchmark.rs` for
  the fixed-recipe builder classification and its focused Rust regressions.
- `experiments/terminal_benchmark_project_checkers/**` for deterministic
  PRE-valid negative package preparation, request execution, matrix reduction,
  evidence verification and focused tests.
- `.github/workflows/terminal-benchmark-project-checkers.yml` only as needed to
  execute and retain the expanded existing proof on an ephemeral GitHub-hosted
  runner; preserve the current event, permissions, exact-head checkout,
  concurrency, cleanup and evidence upload model. Its `pull_request.paths`
  selection must include this record directly.
- `docs/roadmap_status.md` and the experiment README for the resulting bounded
  development evidence and its remaining deployment boundary.

### Not allowed

- No new runner, registry, service, checker phase, generic evaluator framework,
  broad #496 CI expansion, production activation or deployment.
- No changes to authorization, lifecycle routing, acceptance, contribution,
  registry persistence, migrations, shared catalogues or public APIs.
- No submitted network access, host Docker socket, extra Linux capabilities,
  relaxed runsc/profile checks, larger production limits or weaker cleanup.
- No edits to the reviewed public corpus packages. Negative packages are
  deterministic proof fixtures derived from the exact tracked
  `ledger-reconcile` package inside the proof's root-owned staging custody.
- No fake `build_failed` package. A PRE-invalid Dockerfile is intake evidence,
  and missing/corrupt image or runtime material is infrastructure evidence.
- No live cloud, credentials or private benchmark material.

## Design and decisions

### Fixed-recipe builder classification

The admitted build context contains three verified regular files, and the exact
Dockerfile has no submitted `RUN`, build argument or dependency acquisition.
The service continues to distinguish an observed builder OOM or trusted Kaniko
storage/PID exhaustion as `capacity_exceeded`. Any other builder nonzero becomes
`implementation_unavailable`; the dead completed-work `build_failed` branch is
removed. Oracle output is contributor-controlled, so it can no longer promote
the strings `no space left on device` or `resource temporarily unavailable` to
capacity. Oracle capacity requires Docker's `State.OOMKilled=true`; any other
nonzero follows the existing candidate/reference status rules. A fake-Docker
regression drives the real `run_builder` command path
through success, capacity and ordinary nonzero exits, then the existing SDK
result constructor proves the public infrastructure classification. The oracle
mapping regression continues to cover no-op, reference failure, instability and
a contributor-output capacity-spoof control.

### Proof packages

One bounded preparation helper copies the exact HEAD-bound public package into
fixed named proof variants using no-follow regular-file reads, a closed eight
file/four directory inventory, count/byte ceilings and atomic publication in
the existing quota-backed, root-owned proof state. It changes only these reviewed text files:

- `no-op-pass`: replace `tests/test_task.py` with a nonempty successful test so
  the unchanged starter exits zero and yields `starter_unexpectedly_passed`.
- `reference-failure`: replace `solution/program.py` with a deterministic
  failing program; the unchanged starter fails first and the reference then
  yields `reference_failed`.
- `reference-instability`: retain the real assertions and emit the fresh
  container hostname only after a successful reference run. The candidate
  still fails; unique container identities make successful reference output
  digests differ and yield `reference_unstable` without randomness.
- `memory-capacity`: run a deterministic memory allocation beyond the immutable
  request limit before test evaluation; builder and oracle containers set the
  same exact Docker memory and combined memory-plus-swap ceiling, so host swap
  cannot satisfy the allocation. The real oracle must report
  `capacity_exceeded`; the matrix must bind the exact labeled Docker `oom` event
  and owned resources must be absent afterward.
- `capacity-spoof`: emit the formerly trusted capacity phrase and exit exactly
  2. The real response must be `implementation_unavailable`, never
  `capacity_exceeded`, and no reference may launch. This distinguishes the
  spoof from the ordinary status-1 starter failure and proves package-controlled
  output cannot claim a trusted enforcement signal.

The helper emits a canonical fixture inventory binding base HEAD, variant name,
changed path and SHA-256. Focused tests reject extra variants/files, symlinks,
source substitution, unsafe modes, over-budget content and a mutation that
would let any variant bypass PRE. The actual checker image runs PRE for every
variant before POST; a variant with PRE findings is a proof failure.

### Matrix and infrastructure proof

The existing successful and interruption attempts remain. After restart
cleanup, the harness executes the five variants sequentially through the same
Python ART grant and Rust service. Each response must have the exact request
identity, expected completed finding or infrastructure code, runsc isolation,
the complete image/runtime/sandbox isolation receipt and empty ART/Docker
ownership afterward. Launch reduction cross-binds the result request digest
to the exact
builder/candidate/reference prefix for each outcome and rejects missing, extra
or reordered attempts.

For missing-material classification, the harness removes one harness-owned
local approved-base alias only after all package cases, positively confirms its
absence, and executes one final request. The response must be
`infrastructure_failed/implementation_unavailable`, with no builder or oracle
launch and no work finding. The proof does not mutate the sealed cache bytes,
pull from the network, or remove any unowned image.

The evidence schema is revised in place, with fixed per-case result/ART files,
bounded launch/command/event streams, a canonical matrix summary and the
existing complete owned cleanup receipt. Verification rejects omission,
substitution, unknown files, wrong head, wrong classifications, insufficient
resource evidence and cleanup ambiguity.

The expanded workflow has one 90-minute job deadline. Step deadlines total at
most 80 minutes: checkout 5, exact-head bind 2, tool install 15, prepare 20,
matrix 25, stage 2, cleanup 5, final verification 3 and upload 3. The run command
uses one 1,500-second outer deadline across all requests; individual immutable
600-second request deadlines and 700-second adapter bounds remain subordinate to
it. Even if every preceding step consumes its ceiling, the always-run cleanup
has its full five minutes and the job retains ten minutes of aggregate margin.
The first hosted run must record actual phase durations before any later budget
reduction; no case receives an unbounded or resettable workflow allowance.

## Acceptance criteria

- [x] A source-level invariant and real `run_builder` regression prove that the
  fixed admitted recipe has no contributor-controlled failing build step;
  non-capacity builder exits return `implementation_unavailable`, and builder
  OOM or trusted Kaniko capacity signals return `capacity_exceeded`. This is a
  command-path classification regression, not a claim that every resource has
  been exhausted in a real container.
- [x] The exact project checker image accepts every derived variant under PRE
  before any POST continuation launches.
- [x] A real runsc candidate returns the completed work finding
  `starter_unexpectedly_passed` for the ineffective-test variant.
- [x] Real runsc references return `reference_failed` and
  `reference_unstable` for the respective variants, with the instability case
  using distinct fresh container identities and successful exits.
- [x] A real runsc memory case returns infrastructure `capacity_exceeded`, with
  an exact labeled OOM event and no work finding. A
  contributor-controlled capacity phrase cannot produce that classification.
- [x] A real missing harness-owned approved-base image returns infrastructure
  `implementation_unavailable` before builder/oracle launch and without network
  fallback.
- [x] Every result-bearing case binds its exact request/result/isolation facts
  and launch prefix. The interrupted case separately proves adapter failure,
  ART unwind, restart cleanup and unowned-control preservation; unknown or
  partial attempts fail the reducer and verifier.
- [x] Interrupted and successful controls still pass unchanged, the unowned
  control survives, and final workflow cleanup proves DIND/registry absence,
  XFS unmount, loop detach and deletion of raw state.
- [x] Focused unit/mutation tests discriminate fixture substitution, omitted
  cases, wrong classification, loosened launch expectations and weakened
  cleanup; locked Rust workspace tests and the hosted exact-head proof pass.
- [x] The roadmap and issue handoff distinguish this hosted development proof
  from exact registration, approved activation, production-limit selection and
  deployed Workstream operation owned by #555.

## Risk and review routing

- Risk class: L1 — bounded untrusted-code isolation, resource classification,
  evidence workflow and cleanup behavior.
- Required reviewers: architecture and reuse for the existing-runner boundary;
  security for isolation, fixture custody and missing-image handling; CI
  integrity for pull-request execution/evidence/cleanup; QA and test delta for
  feasible discriminating negative cases; documentation for roadmap and honest
  proof limits.
- Human review focus: accept the fixed-recipe conclusion that `build_failed` is
  unreachable contributor blame, inspect each real package mutation and exact
  result, and verify no privilege/network/limit relaxation or deployment claim.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Previous proof boundary | Inspect merged #594 service, PRE contract, workflow, matrix and run `39058870579` | The existing successful and interrupted controls were retained; this change adds the negative cases without replacing their custody or cleanup proof | Historical baseline evidence does not itself prove the new cases |
| Fixed-recipe classification | Trace the exact PRE Dockerfile and projected builder context through `validate_fixed_text`, `project_build_context` and `run_builder`; Backend `external-checker-runtime` job `117655838847` in run `39120606770` | PASS on exact source head `1136e8f78936c9878ace4242ac262ac6223fa4a2`: 5 SDK, 38 service and 9 project-image tests. The service tests include fixed-recipe builder classification and exact memory/swap command construction | Fake-Docker command tests remain source-level evidence; the hosted matrix below supplies real Docker/runsc behavior |
| Fixture and evidence contracts | Hosted preparation in run `39120606782` executes `test_prepare_variants`, `test_verify_evidence`, `test_runtime_proof` and `test_execute_post_contract` | PASS on exact head `1136e8f78936c9878ace4242ac262ac6223fa4a2`: 34 proof/verifier tests and 3 staged contract tests, including the root-only custody cases | Focused validation is bounded to the checked-in public package and proof environment |
| Real negative/resource matrix | Path-scoped `Terminal benchmark project checker proof` run `39120606782`, job `117655263940`, artifact `12133689792` | PASS on exact head `1136e8f78936c9878ace4242ac262ac6223fa4a2`: PRE accepted all five variants; runsc POST produced `starter_unexpectedly_passed`, `reference_failed`, `reference_unstable`, trusted OOM `capacity_exceeded`, spoofed-text `implementation_unavailable`, and missing-base `implementation_unavailable`; prepare took 87 seconds and the matrix 127 seconds | Development DIND/runsc evidence is not deployed production proof; forced PID exhaustion remains unproved |
| Evidence and cleanup closure | Exact-head artifact `12133689792`; workflow log SHA-256 `ba423a794c642401efb5eedfa52f88fde01ee088ffe942226822ebe95174b381` | Matrix v2 binds all seven result-bearing request/launch/result/isolation sequences and the labeled OOM event. Its separate interrupted entry proves adapter failure, ART unwind, restart cleanup and unowned-control preservation. Cleanup proves DIND/registry/resource absence, XFS unmount, loop detach and raw-state deletion; upload zip digest is `b708f2a0b08ed0149da304713b63571df84dd604224240b17da055721aefc7f9` | Exact terminal registration, approved activation, production-limit selection and the #555 deployed journey remain separate |

## Review findings

- Discovery finding: a genuine contributor `build_failed` package is infeasible
  under the exact PRE recipe. Fabricating one would either violate PRE or relabel
  missing trusted infrastructure as contributor work. The plan therefore makes
  that invariant executable and narrows the service classification.
- Plan finding `PLAN493-NEG-001`: oracle stdout/stderr is contributor-controlled,
  so a phrase cannot establish PID or storage enforcement. Oracle capacity is
  narrowed to Docker OOM state; a real phrase-spoof case is required. The
  existing 32-PID launch boundary remains verified, but forced PID exhaustion
  is explicitly unproved until a trusted runtime-owned hit signal exists.
- Plan findings `CI-493-NP-01/02`: the workflow must select this new record and
  must use the explicit 90-minute job/80-minute step budget above so expanded
  proof execution cannot consume cleanup time.
- Implementation finding `QA493-NEG-001`: memory exhaustion was initially
  under-specified because Docker swap could extend the memory ceiling. Builder
  and oracle commands now set equal memory and memory-swap limits, and both the
  Rust command regression and wrapper profile checks bind the exact value.
- Implementation finding `QA493-NEG-002`: the first evidence contract did not
  cross-bind every matrix request digest to its result or compare the complete
  isolation receipt. Contract v2 derives the receipt from verified image facts
  and fixed service identity, and the final verifier rejects digest or receipt
  substitution.
- The first hosted attempt exposed missing outer stdin forwarding for the real
  PRE image. The dedicated PRE transport now uses outer `docker exec -i`, with
  an exact argv and byte-for-byte stdin regression. A later test-only fixture
  repair created its declared temporary directory before writing. Exact-head
  locked Rust and full hosted proof runs passed after both repairs.

## Reconciliation

- Current-source reconciliation: based on `origin/main` at
  `51b86807111ff25b067402219ba0b533e0750f3e`; merged #594 owns the checker and
  proof harness. Later main changes must be inspected before readiness.
- Durable outcome: the bounded negative runtime proof and its exact evidence are
  complete. The standalone change does not close issue #493's deployment work.
- Next usable boundary: #555 registers and activates the exact checker entry,
  chooses production limits and runs the connected deployed contribution drill.
- Remaining risks: GitHub-hosted isolated DIND/runsc remains development proof;
  production topology, limits and operational recovery require #555. The
  configured PID ceiling remains exact, but a forced PID-limit hit is not
  classified as capacity because the current Docker/runsc seam exposes no
  trusted enforcement event comparable to OOM.
