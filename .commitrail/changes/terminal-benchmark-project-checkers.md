# Terminal benchmark project checkers and isolated calibration

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: One digest-pinned terminal-benchmark checker image validates the agreed package before Submission and drives an offline Kaniko build plus fresh isolated no-op/reference/stability runs after Submission, with exact registration specifications for the existing registry.

## Intent

Deliver the bounded deterministic portion of #493 for the first approved
Terminal-Bench-style task-authoring project. The project checker must turn the
shareable #576 package contract into actionable PRE findings and real POST
build/calibration evidence through the existing external-checker service. It
must not decide acceptance, create lifecycle facts, or claim hosted deployment.

This change exists because the selected runtime can execute a conventional
digest-pinned checker against verified read-only material, but it cannot yet
perform the approved PILOT-00 sequence for a submitted environment: root-inside-
gVisor Kaniko over a sealed offline cache followed by separate non-root gVisor
oracle sandboxes. Giving the checker a host container socket or running uploaded
code on the host would break the established boundary.

## Current behavior

- `external_checkers/workstream-checker-service/src/main.rs` verifies an ART
  grant, resolves one administrator-cached platform manifest, and starts one
  non-root, capability-free, networkless checker container with the verified
  workspace mounted read-only. It accepts only the normalized
  `external_checker_result.v1` response.
- `experiments/pilot00_gvisor_offline/` proved a small bounded Kaniko build and
  separate oracle under `runsc`. It is a development feasibility harness, not
  a production project checker or representative sizing proof.
- `pilots/terminal_benchmark/` on the stacked #576 branch supplies five original
  packages, independent tests/reference solutions and reviewed local expected
  outcomes. Its verifier intentionally executes only trusted repository assets
  and is not an uploaded-code admission authority.
- Read-only OCI inspection found that the proposed corpus `FROM` digest
  `sha256:4766d8...` is an image index, while #493 requires the exact cached
  linux/amd64 platform manifest. The current corresponding platform manifest is
  `sha256:6e13e65c55e33adf203d77ee371cf8bf5d81bd4902ef07565721f46bf44917af`.
  The #576 owner must reconcile that input before the real PRE originals can
  honestly pass; this checker change must not silently accept the index.
- The existing registry and selected PRE/POST owners already bind immutable
  image/configuration/schema/resource identities, verified input lineage,
  normalized findings, infrastructure outcomes and isolation receipts. #580
  owns the supported Operator mutation/readback path; #555 owns registration,
  activation and the connected local/hosted journey.

## Bounded change

### Allowed

- This change record for the final bounded intent, evidence and reconciliation.
- `external_checkers/workstream-terminal-benchmark-checker/**` for one Rust
  project image that:
  - returns final PRE results for the agreed required members, exact task
    metadata/commands, UTF-8/text and bounded project rules, `.dockerignore`,
    digest-pinned `FROM`, and approved final-stage base family/platform identity;
  - returns one strict request-bound POST build/oracle plan whose relative paths,
    fixed command, reference overlay and repetition count come from the agreed
    project contract; and
  - never receives a host socket, network, secret, provider coordinate or
    lifecycle authority.
- `external_checkers/workstream-checker-sdk/**` only for strict canonical types,
  digests and cross-image/service validation of the private build/oracle plan.
  The existing public `external_checker_request.v1` and
  `external_checker_result.v1` envelopes remain unchanged.
- `external_checkers/workstream-checker-service/**` only for a closed
  `terminal_benchmark_build_oracle.v1` continuation of an already authorized
  checker invocation:
  - require an administrator-configured authorization that binds the exact POST
    registry entry ID/digest and checker platform-manifest digest to this one
    execution profile; an arbitrary registered image or PRE entry cannot request
    builder root, added capabilities or an oracle launch;
  - resolve exact administrator-configured Kaniko and approved base platform
    manifests without pulling;
  - run the builder as root only inside the configured sandbox with the four
    PILOT-00 capabilities, no network/socket/secret, read-only input/cache and
    bounded CPU, memory, PID, deadline and ephemeral disk;
  - stream the attempt-specific output image into the trusted daemon without a
    durable product reference, bind its observed digest to the request, and
    remove it after the attempt;
  - run the unchanged starter once and require its tests to fail, then run the
    reference overlay three times in fresh non-root, capability-free,
    networkless, read-only-root sandboxes; and
  - return one normalized final result, classifying contributor Dockerfile or
    oracle conclusions as work findings and missing cache/runtime, launch,
    deadline, capacity, malformed output or uncertain cleanup as the existing
    infrastructure outcomes.
- Focused Rust fixtures/tests for contract parsing, package rules, request/path
  substitution, exact cache identity, no-op pass, reference fail, instability,
  missing cache, build exit, timeout/OOM/disk/output bounds, disconnect and
  complete owned cleanup. Tests may consume the fixed #576 corpus read-only;
  they must not make its trusted native verifier a production authority.
- A bounded local probe under `experiments/terminal_benchmark_project_checkers/**`
  for actual image build, service execution and retained evidence when the
  repository lead allocates Docker capacity.
- Exact immutable PRE and POST registration specifications, including schemas,
  resource ceilings, configuration, built platform-manifest digest and source
  provenance, stored outside the image build context so the image digest has no
  self-reference. They are handoff inputs, not registry writes.
- Only affected checker architecture/operations and `docs/roadmap_status.md`
  claims, clearly separating local execution, hosted execution, registration and
  deployment.

### Not allowed

- No change to Submission, TASK, review, revision, FinalAcceptance,
  ContributionRecord, compensation, authorization, policy approval, checker
  selection, database schema or public API/CLI behavior.
- No registry mutation or alternate registration path; #580 owns the supported
  Operator operation and #555 owns use of these specifications.
- No generic workflow runner, arbitrary command graph, model judge, plugin
  discovery, second checker service, host execution of uploaded code, host
  Docker/containerd socket in any sandbox, network fallback or mutable image
  resolution.
- No changes to #576 corpus assets without explicit coordination with their
  owner and manager agreement. No private Terminal-Bench/Snorkel material.
- No CI topology, hosted deployment, secret, merge or issue-closure change.
- If a bounded builder/oracle scratch path cannot satisfy the existing aggregate
  quota and crash-cleanup owner without expanding ART or registry contracts,
  stop for a revised reviewed boundary instead of adding an ad hoc filesystem.

## Design and decisions

Use one phase-aware Rust project image with two immutable registry entries. PRE
finishes in the ordinary checker sandbox. POST first validates the same package
contract and emits one canonical private plan bound to the external request and
verified grant. The trusted service accepts exactly this plan version and no
arbitrary stages: one offline build, one starter test, and three fresh reference
tests. It converts observations into the existing final result family. Project
paths and commands remain image-owned; Docker/runsc custody, image import,
limits and cleanup remain service-owned.

Registration and project-policy selection alone do not grant the stronger
builder profile. The service configuration must separately bind the exact POST
registry entry ID, entry digest and image platform-manifest digest to
`terminal_benchmark_build_oracle.v1`, the exact Kaniko/base cache identities and
fixed builder/oracle limits. A conventional or PRE image returning a plan is
invalid output and receives no second launch. A configured entry cannot change
its paths into arbitrary commands or ask for more phases, capabilities, network,
mounts or resources. The original request deadline is the total wall-clock
ceiling across checker planning, build, image import, four oracle containers and
cleanup; phase ceilings must fit within it. Cleanup uses its existing separate
bounded margin and a failed or uncertain cleanup can never become a work verdict.

The builder uses the reviewed PILOT-00 Kaniko identity and only the configured
linux/amd64 platform-manifest cache. The submitted Dockerfile cannot select a
different family or platform. A present but failing submitted build is a work
finding. Missing or substituted trusted builder/base/cache material is
`material_unavailable` or `implementation_unavailable`; deadlines and exhausted
memory/PID/disk use the existing closed infrastructure categories. Networking is
never enabled to repair a miss.

The produced image is attempt-specific evidence, not a reproducible artifact:
Kaniko timestamps mean identical inputs need not produce identical tar bytes.
The service hashes the exact attempt output, loads it under an owned temporary
identity, uses it only for the bound oracle runs, and removes all containers,
temporary image identities and scratch before returning. Candidate oracle runs
never receive `solution/`; reference runs mount only the declared reference file
over the candidate program and mount tests separately. Each run gets a fresh
container and writable temporary workspace within its fixed limits.

The five fixed corpus packages calibrate behavior, while registration
configuration records the manager-agreed project version, allowed task IDs,
size/forbidden rules, approved base identity and repetition count. Until #576 is
merged and manager agreement is recorded, these are proposed inputs and cannot
be described as active policy. Final proof must be rebased/reconciled onto the
then-current `main`; the stacked corpus commits are dependency input, not this
change's implementation diff.

Rejected alternatives are a host socket in the checker, Docker-in-Docker inside
the project image, host execution of package Python, treating the native corpus
verifier as admission, and a general DAG/job protocol. Each either breaks the
trust boundary or adds a broader subsystem than the one concrete build/oracle
sequence requires.

## Acceptance criteria

- [ ] The agreed original packages pass PRE through the real image; mutations
  for missing members, project size, forbidden paths, malformed/mismatched
  metadata, unpinned/wrong-family/wrong-platform base and unsafe build context
  fail with bounded actionable findings and no package code execution.
- [ ] The exact retained packages pass POST through the real service: offline
  Kaniko build, unchanged starter rejection, reference pass and three fresh
  stable reference runs. Marker-only or omitted build/oracle implementations
  fail a focused regression.
- [ ] A genuine Dockerfile failure, reference failure, no-op pass and unstable
  repeated outcome produce distinct work findings; dependent phases are omitted
  explicitly rather than reported as independent passes or infrastructure.
- [ ] Missing/substituted builder or base cache, unavailable `runsc`, deadline,
  memory/PID/disk exhaustion, malformed output, disconnect and uncertain cleanup
  produce the existing recoverable infrastructure outcomes and no work verdict.
- [ ] Launch evidence proves no external network or host socket, exact cached
  platform identities, builder-only capabilities, non-root capability-free
  oracles, read-only inputs/root, fresh containers, fixed resources and complete
  cleanup. Local `docker-dev` evidence is labeled local; hosted proof remains
  #555/#583.
- [ ] Exact built image platform-manifest digest(s), canonical PRE/POST registry
  specs and approved configuration are independently validated by the current
  Python registry contract without writing the registry or depending on #580.
- [ ] Existing conventional external checker execution and PRE/POST result
  custody remain unchanged and pass their focused regressions.

## Risk and review routing

- Risk class: L1 (bounded high-risk untrusted build/test execution and trusted
  launcher extension; no product authority or lifecycle mutation).
- Required reviewers: architecture, security, reuse_dedup, qa, test_delta,
  senior_engineering, product_ops and documentation. CI integrity is required
  only if implementation changes workflow, lane or package-script custody.
- Human review focus: whether the service-private plan is the smallest safe
  bridge; exact service-profile authorization so arbitrary registered images
  cannot gain builder root/capabilities; cache/platform and submitted-path
  substitution; total budget and scratch custody; builder privilege;
  candidate/reference separation; offline/resource/cleanup enforcement;
  work-versus-infrastructure classification; manager-agreed configuration; and
  no cycle with #580/#555.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing owner and gap | Inspect PILOT-00, PILOT-04 service/SDK, ART grants, selected PRE/POST owners and #493/#576/#555 | The selected service has exact verified input and image custody but only one conventional checker launch; it cannot safely build a submitted Dockerfile or launch a separate oracle | Plan review and representative execution pending |
| Platform pin feasibility | `docker buildx imagetools inspect --raw` for the proposed CPython and Kaniko digests, without pulling either image | Both proposed top-level digests are OCI indexes; linux/amd64 resolves to CPython `sha256:6e13e65c...` and Kaniko `sha256:c73ca67a...` | #576 must correct the corpus `FROM`; trusted builder config must record the platform manifest and config image ID |
| Corpus dependency | `python3 pilots/terminal_benchmark/verify_corpus.py` on the reviewed #576 candidate | Pending on this worktree after dependency reconciliation | Trusted local calibration is not sandbox proof |
| Rust contracts and logic | `cargo fmt --all --check && cargo test --workspace --locked` in `external_checkers/` | Future implementation proof | Does not prove Docker/runsc behavior |
| Real local matrix | Bounded project-checker probe over originals and work/infrastructure negatives | Future implementation proof; wait for lead-owned Docker capacity | Local `docker-dev` is not hosted gVisor proof |
| Current-source reconciliation | Diff against merged #576 and current `main`; focused existing checker tests and repository gates | Future final proof | PR #575 result-contract merge state must be rechecked |

## Review findings

Plan review is required before product edits. No reviewer verdict is recorded yet.

## Reconciliation

- Current-source reconciliation: Discovery used stacked corpus candidate
  `a4bc11a1564d7c9f063f3d662b66a297edd6e7d3`; its owner has since merged current
  main into the dependency branch. This change must incorporate the final merged
  corpus and current main before final proof and must exclude parent corpus assets
  from its own implementation diff.
- Next usable boundary: plan review, manager agreement on #576 mechanical
  configuration, then bounded implementation; #580 may register the resulting
  exact specs, and #555 may combine registration with the public/hosted journey.
- Remaining risks: representative disk/resource ceilings, exact approved
  linux/amd64 base cache identity, and hosted `runsc` hardening remain unproved.
