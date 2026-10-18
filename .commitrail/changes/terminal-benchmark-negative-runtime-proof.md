# PILOT-06B — Terminal benchmark negative runtime proof

- Initiative: None
- Durable disposition: Planned
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

- [ ] A source-level invariant and real `run_builder` regression prove that the
  fixed admitted recipe has no contributor-controlled failing build step;
  non-capacity builder exits return `implementation_unavailable`, and builder
  OOM or trusted Kaniko capacity signals return `capacity_exceeded`. This is a
  command-path classification regression, not a claim that every resource has
  been exhausted in a real container.
- [ ] The exact project checker image accepts every derived variant under PRE
  before any POST continuation launches.
- [ ] A real runsc candidate returns the completed work finding
  `starter_unexpectedly_passed` for the ineffective-test variant.
- [ ] Real runsc references return `reference_failed` and
  `reference_unstable` for the respective variants, with the instability case
  using distinct fresh container identities and successful exits.
- [ ] A real runsc memory case returns infrastructure `capacity_exceeded`, with
  an exact labeled OOM event and no work finding. A
  contributor-controlled capacity phrase cannot produce that classification.
- [ ] A real missing harness-owned approved-base image returns infrastructure
  `implementation_unavailable` before builder/oracle launch and without network
  fallback.
- [ ] Every case binds its exact request/result/isolation facts, launch prefix,
  ART unwind and positive Docker/image absence; unknown or partial attempts fail
  the reducer and verifier.
- [ ] Interrupted and successful controls still pass unchanged, the unowned
  control survives, and final workflow cleanup proves DIND/registry absence,
  XFS unmount, loop detach and deletion of raw state.
- [ ] Focused unit/mutation tests discriminate fixture substitution, omitted
  cases, wrong classification, loosened launch expectations and weakened
  cleanup; locked Rust workspace tests and the hosted exact-head proof pass.
- [ ] The roadmap and issue handoff distinguish this hosted development proof
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
| Current proof boundary | Inspect merged #594 service, PRE contract, workflow, matrix and run `39058870579` | One successful and one interruption path are implemented and hosted-green | Negative packages and forced memory exhaustion are not exercised |
| Fixed-recipe feasibility | Trace exact PRE Dockerfile and projected builder context through `validate_fixed_text`, `project_build_context` and `run_builder` | No contributor-controlled build instruction exists after PRE | Plan review must confirm source metadata/path/storage cannot produce a distinct work failure |
| Fixture contracts | Focused stdlib tests for variant preparation, retained inventory and PRE request/result binding | Source checks pass; root-custody cases require the hosted root phase | Source tests do not replace hosted runsc execution |
| Result classification | Locked Rust workspace tests including real builder command-path regression | Planned | Fake Docker proves mapping, not Docker/runsc behavior |
| Real negative/resource matrix | Existing path-scoped hosted workflow on exact PR head | Planned | Development runner evidence is not deployed production proof |
| Evidence closure | Matrix reducer, evidence verifier, owned cleanup receipt and mutation probes | Planned | Production activation and #555 journey remain separate |

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

## Reconciliation

- Current-source reconciliation: based on `origin/main` at
  `51b86807111ff25b067402219ba0b533e0750f3e`; merged #594 owns the checker and
  proof harness. Later main changes must be inspected before readiness.
- Next usable boundary: #555 registers and activates the exact checker entry,
  chooses production limits and runs the connected deployed contribution drill.
- Remaining risks: GitHub-hosted isolated DIND/runsc remains development proof;
  production topology, limits and operational recovery require #555. The
  configured PID ceiling remains exact, but a forced PID-limit hit is not
  classified as capacity because the current Docker/runsc seam exposes no
  trusted enforcement event comparable to OOM.
