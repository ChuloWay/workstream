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
- Read-only OCI inspection found that the original corpus `FROM` digest
  `sha256:4766d8...` was an image index. The final reviewed #576 dependency at
  `e6a55d26b` uses its exact linux/amd64 platform manifest
  `sha256:6e13e65c55e33adf203d77ee371cf8bf5d81bd4902ef07565721f46bf44917af`
  and the exact reviewed Dockerfile recipe. PRE must require that platform
  manifest and recipe; it must not silently accept the index.
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
    infrastructure outcomes; and
  - keep one nonblocking lifetime lock on the validated private socket parent,
    refuse a live listener or foreign/link path, recover only a connection-
    refused socket with the same owned inode, and remove the current owned
    socket on clean shutdown without deleting a substituted path.
- `backend/app/modules/artifacts/preparation.py`,
  `backend/app/modules/artifacts/post_submit_materialization.py`, and their
  existing focused tests only for one narrow extension of the current
  `ArtifactScratchManager` grant:
  - before every POST external grant publication, raise that workspace's fixed
    total byte reservation to the existing 512 MiB per-workspace maximum and its
    entry reservation to the manager's existing fixed maximum-entry ceiling;
    the runtime allowances are those ceilings minus the sealed workspace and
    grant overhead;
  - publish one empty `runtime/` sibling beside the sealed `workspace/`, bind its
    derived byte/entry allowances and existing grant owner UID/GID/mode into the
    request-bound grant manifest, and keep it `0700` for that same OS identity
    already shared by ART and the checker service; and
  - keep that directory under the existing workspace TTL, aggregate quota,
    no-follow cleanup, failed-cleanup retention and dead-process recovery. This
    is not a second scratch ledger or artifact reference.
- Focused Rust and existing backend fixtures/tests for contract parsing, package
  rules, request/path substitution, exact cache identity, no-op pass, reference
  fail, instability, missing or mutated cache, build exit,
  timeout/OOM/disk/output bounds, cancellation, SIGKILL/restart recovery and
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
- No second scratch owner, service-private scratch root, durable build artifact,
  arbitrary caller-selected scratch size, or public/DB/registry schema change.
  The narrow ART grant extension is a concrete prerequisite in this PR because
  the builder cannot safely emit its temporary image without it and the
  extension has no useful standalone product behavior.

## Design and decisions

Use one phase-aware Rust project image with two immutable registry entries. PRE
finishes in the ordinary checker sandbox. POST first validates the same package
contract and emits one canonical private plan bound to the external request.
After parsing, the trusted service attaches it to the already verified in-memory
grant. The service accepts exactly this plan version and no arbitrary stages: one offline build, one starter test, and three fresh reference
tests. It converts observations into the existing final result family. Project
paths and commands remain image-owned; Docker/runsc custody, image import,
limits and cleanup remain service-owned.

### Strong-profile authority

Registration and project-policy selection alone do not grant the stronger
builder profile. Administrator-owned service configuration separately contains
one closed authorization tuple: exact POST registry entry ID, entry digest,
checker platform-manifest digest, `terminal_benchmark_build_oracle.v1` profile
version, Kaniko/base/cache identities, and fixed phase limits. The service first
validates the ordinary request and grant, then requires every element of this
tuple before it accepts a continuation. It also requires the checker-returned
plan to repeat only facts present in its ordinary stdin: the request digest,
registry entry ID and digest, checker image digest, configuration digest and
profile version. After parsing, the trusted service attaches the plan to its
already verified in-memory grant ID and binding digest before continuation; it
does not ask the checker to echo a grant fact the image never receives. A grant
substitution fails before launch. A conventional image, a PRE entry, or another
registered POST image returning the same JSON receives `invalid_output` and no
builder launch. Their ordinary one-sandbox execution remains unchanged. Plan
fields cannot add commands, mounts, phases, capabilities, network or resource
limits; the service supplies those values from the closed profile.

### ART-owned scratch and crash recovery

The build output and context use a `runtime/` directory inside the same private
`ArtifactScratchManager` extraction workspace that already owns `workspace/`.
Before publishing any POST external grant, ART atomically raises that
workspace's byte reservation from the verified expanded-byte count to the
existing 512 MiB per-workspace maximum and raises its entry reservation to the
manager's existing fixed maximum-entry ceiling. The runtime byte allowance is
`512 MiB - verified expanded bytes`. The runtime entry allowance is the fixed
entry ceiling minus the `workspace/` directory entry, every sealed member below
it, `.external-checker-grant.json`, and the `runtime/` directory entry that the
same no-follow cleanup walk will count. Neither value is caller selected; the
whole reservation still obeys the existing aggregate byte ceiling, free-space
floor, entry ceiling and TTL. ART
then creates `runtime/` descriptor-relatively with no-follow checks, keeps it
`0700` for the existing OS identity already shared by ART and the checker
service, and records both allowances plus observed UID/GID and modes in the
signed grant manifest. The ordinary service does not mount this directory into
checker containers; only the separately authorized continuation may use it. The
opaque grant reference remains only an ID and binding digest; neither backend
nor response exposes a path. If either larger reservation or directory
publication cannot be proven, the invocation stops as infrastructure failure
before the service call.

The service may write only the bound `runtime/` child. Before every projected
directory or regular-file creation it charges one entry and the copied bytes to
the two grant allowances. It then charges the candidate-tar entry, creates that
single empty file and reserves every remaining byte before builder launch. The
builder inherits an `RLIMIT_FSIZE` hard ceiling equal to that reservation, so an
exact-limit write is admitted and the next byte fails in the writer rather than
creating unmetered residue. The service also rejects a zero-length or oversized
tar before image load. The builder's separate writable-root bound does not
enlarge the ART reservation.

Ownership follows the existing call order. On normal completion, timeout,
cancellation or disconnect, the Rust service settles its owned Docker resources
before sending or closing the socket response. The live Python grant context
then revokes the manifest and no-follow deletes the workspace before the
materializer exposes an evaluation to CHECKERS. A grant/workspace cleanup error
discards any already received result, retains ledger custody for retry and wins
as infrastructure failure. A service-only SIGKILL produces adapter failure and
the still-live Python context synchronously unwinds ART scratch; service restart
uses the trusted labels and fixed repository/tag namespace to sweep Docker
residue. If the Python ART owner
also dies, the existing TTL plus dead-owner reaper cleans the workspace. No
service-to-ART callback or second cleanup dependency is introduced.

Every service-created Docker container has exact trusted labels for deployment
owner, request digest, grant ID, attempt nonce and resource kind. The temporary
image tag uses only the fixed administrator-configured repository plus the
service-generated hexadecimal attempt nonce. Normal cleanup removes those exact
names before returning. Startup recovery selects containers by the owner label,
then validates the complete label set and owned name before deletion; it scans
only the fixed repository and accepts only valid attempt tags whose inspected
image still reports that exact tag and the same listed image ID. It never relies
on ART runtime files, which
may already be gone after a service crash, and never removes an image outside
the fixed repository. The Docker reaper uses one cleanup deadline and leaves
ambiguous resources quarantined as infrastructure failure rather than claiming
cleanup.

Removal never treats a failed Docker command or failed inspect as proof of
absence. Work, emergency and startup paths require a successful exact
container/image inventory query with no matching entry. If emergency cleanup
still cannot establish absence, the service sends no result and terminates its
listener before another request can start. Restart, under socket-parent
custody, reconciles both conventional checker containers and the project
profile's labeled containers/images before admission. Conventional names must
match their attempt label exactly; project builder/candidate names must match
their attempt label exactly and reference names additionally allow only
iterations zero through two.

### Physical build and oracle separation

The service never gives the builder the original ART grant. It creates
`runtime/build-context/` by reopening the sealed `workspace/` descriptor-
relatively with `O_NOFOLLOW`, rehashing every copied source against the grant
manifest, and projecting exactly `.dockerignore`, `environment/Dockerfile` and
`workspace/**`. It rejects missing, extra, special, linked, changed or
out-of-budget entries, seals and reinventories the projection, then mounts only
that directory into Kaniko. `solution/**`, `tests/**`, the grant root, and the
absolute submitted Dockerfile path are physically absent from the builder
namespace. The Dockerfile must match the exact recipe in the reviewed
`e6a55d26b` corpus, including the linux/amd64 base platform-manifest digest; PRE and
POST both reject any other recipe before building.

The produced image is attempt-specific evidence, not a reproducible artifact:
Kaniko timestamps mean identical inputs need not produce identical tar bytes.
The service loads the bounded attempt tar under the owned temporary identity,
inspects its image ID, and uses that observed ID only for the bound oracle runs.
Candidate runs receive the produced image plus a read-only tests mount and no
grant or reference path. Reference runs receive the same image and tests plus
only the single declared `solution/program.py` mounted over the candidate
program. Each run is a fresh non-root, capability-free, networkless, read-only-
root container with its own bounded tmpfs. Absolute paths cannot reach the
original grant because it is not mounted in either namespace.

### One aggregate budget

The immutable request registry's `cpu_millis`, `memory_bytes`, `deadline_ms` and
`maximum_output_bytes` are ceilings for the entire invocation, including its
continuation. Closed profile values may be smaller and can never enlarge them.
Phases are sequential; the next container is not created until the prior one is
confirmed removed. Each phase's CPU and memory limits are at most the request
ceilings, and the sum for concurrently live service-owned containers is also at
most those ceilings. PID, tmpfs, writable-root and ART scratch bounds are fixed
profile limits within the same request and scratch ceilings.

The service computes one monotonic absolute work deadline before cache checking
or the checker launch. Checker planning, context projection, offline build,
image load and all four oracle runs consume its remaining time; no phase or
retry resets it. One byte meter likewise aggregates checker output, builder and
Docker control logs, every oracle's stdout/stderr and the final normalized
result under `maximum_output_bytes`; it is never reset per resource or phase.
This includes the initial image inspection and container create plus every
subsequent Docker work command. Blocking Docker control commands poll the
client connection and stop their CLI process on disconnect. When cleanup first
becomes necessary, every CLI stop, emergency container remove and image unload
shares the existing 10-second
`CLEANUP_TIMEOUT` and a separate fixed 256 KiB cleanup-output ceiling. Both fit
inside the existing 60-second adapter cleanup margin and neither resets per
resource.

### Sealed offline cache

The trusted service configuration binds a canonical absolute cache root; owner
UID/GID; exact root, directory and regular-file modes; sorted relative-file
inventory with per-file byte count and SHA-256; total count and bytes; canonical
inventory digest; exact operating system and architecture; and exact repository,
platform-manifest media type/digest and config image ID for both the Kaniko
builder and approved base. The root and every member must be administrator-owned
and free of symlinks or special files.

At startup and immediately before each build, the service opens the configured
root without following links, walks and fully rehashes every member descriptor-
relatively, and requires the complete canonical inventory: no missing, extra,
changed, linked, wrong-owner or wrong-mode entry and exact count, bytes and
digest. It also inspects the locally cached builder/base images and requires the
bound platform and config identities. Any mismatch is infrastructure failure
before Docker create. The cache is mounted read-only; the service performs a
second complete inventory check before returning to detect concurrent mutation.
There is no pull, registry lookup or network fallback on a miss.

A present but invalid submitted Dockerfile/build or a completed oracle
conclusion is a work finding. Missing or substituted trusted builder/base/cache
material, launch/runtime unavailability, deadline or resource exhaustion,
malformed output, or failed/uncertain cleanup uses an existing recoverable
infrastructure category and cannot become a work verdict.

The five fixed corpus packages calibrate behavior, while registration
configuration records the manager-agreed project version, allowed task IDs,
size/forbidden rules, approved base identity and repetition count. Until #576 is
merged and manager agreement is recorded, these are proposed inputs and cannot
be described as active policy. Final proof must be rebased/reconciled onto the
then-current `main`; the stacked corpus commits are dependency input, not this
change's implementation diff.

Rejected alternatives are a host socket in the checker, Docker-in-Docker inside
the project image, host execution of package Python, treating the native corpus
verifier as admission, a service-private scratch ledger, and a general DAG/job
protocol. Each either breaks an existing trust/cleanup boundary or adds a
broader subsystem than the one concrete build/oracle sequence requires. The ART
grant extension stays in this PR because it has no independent useful behavior:
the exact POST execution needs one ledger-owned output path before the service
can safely adopt the PILOT-00 mechanism.

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
- [ ] The builder context contains exactly `.dockerignore`,
  `environment/Dockerfile`, and `workspace/**`; it cannot read `solution/**`,
  `tests/**`, the original grant, or an absolute submitted Dockerfile path.
  Descriptor-relative copy and a second exact inventory reject links, special
  files, substitutions, additions and byte changes before launch.
- [ ] One request-bound work deadline and one aggregate output meter cover
  planning, initial create/inspect, build, import, Docker control and every oracle
  run without per-phase reset. Sequential container CPU/memory values and any
  concurrent total never exceed the immutable registry ceilings. All emergency
  cleanup shares one 10-second deadline and separate 256 KiB output ceiling
  within the existing 60-second cleanup margin.
- [ ] ART reserves the existing fixed 512 MiB workspace total and manager fixed
  maximum-entry total before POST grant publication, then binds byte and entry
  allowances after sealed workspace/grant overhead. Exact-limit runtime creation
  succeeds; limit-plus-one fails before residue; normal and reaper cleanup remove
  every admitted tree without exceeding the same entry count. The candidate tar
  entry and every remaining byte are reserved before launch, and a kernel file-
  size ceiling rejects the first excess byte inside the writer.
- [ ] `test_post_result_is_hidden_until_grant_workspace_cleanup_completes`
  proves the service settles Docker resources before its socket response and the
  Python grant/materializer revokes and deletes scratch before exposing the
  result to CHECKERS.
- [ ] `test_service_sigkill_fails_adapter_and_live_art_unwinds_workspace`
  proves service death fails transport, the live Python owner synchronously
  unwinds scratch, and restart removes only its labeled/prefixed Docker residue.
- [ ] `test_dead_art_owner_is_reaped_after_ttl` proves Python-owner death is the
  distinct case handled by the existing TTL plus dead-owner workspace reaper.
- [ ] `test_art_cleanup_failure_discards_received_result_and_retains_ledger_custody`
  proves cleanup failure wins over an already received result and preserves the
  reservation for retry.
- [ ] Grant substitution produces no continuation launch. Conventional and PRE
  images continue to receive only the ordinary request stdin and cannot gain the
  stronger profile even if their output copies its plan shape.
- [ ] Cache tests mutate one blob and independently cover extra, missing,
  symlink/special, wrong-owner and wrong-mode entries; each fails before Docker
  create with no pull. Startup recovery removes seeded stale containers and
  temporary images with the exact owned labels/fixed repository while leaving an
  unowned control resource untouched.
- [ ] Simultaneous service startups serialize on the private socket-parent
  lock; restart recovers an owned stale socket while preserving a live
  listener, foreign file/link and path substituted before listener teardown.
  Socket-parent custody precedes Docker validation and recovery, so a losing
  full startup cannot inspect or clean the winner's resources.
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
| Existing owner and gap | Inspect PILOT-00, PILOT-04 service/SDK, ART grants, selected PRE/POST owners and #493/#576/#555 | The selected service had exact verified input and image custody but only one conventional checker launch; this change adds one exact-authorized terminal-benchmark continuation rather than a general runner | Representative execution pending |
| Platform pin feasibility | `docker buildx imagetools inspect --raw` for the proposed CPython and Kaniko digests, without pulling either image | Both proposed top-level digests are OCI indexes; linux/amd64 resolves to CPython `sha256:6e13e65c...` and Kaniko `sha256:c73ca67a...`; raw nonsecret manifests and SHA-256 commands are retained under `/tmp/workstream-493-python-*` | Trusted builder config must bind the full canonical cache inventory plus both platform manifests and config IDs |
| Corpus dependency | Merge `e6a55d26b`; run `python3 pilots/terminal_benchmark/verify_corpus.py` on the final reviewed #576 dependency | PASS in the corpus branch: all five originals report three reference passes plus starter and near-miss rejection; the malformed-input harness cases become bounded work failures; the atomic-import destructive-state mutant is rejected across three runs; all 46 manifest files match | This is explicitly `trusted_native_corpus_only`, not Docker/gVisor or production admission proof; parent assets remain outside this change's implementation diff |
| Scratch and cleanup owner | Inspect `ArtifactScratchManager` workspace ledger, TTL/dead-process recovery, no-follow deletion, external grant publication and selected POST call order | Existing owner already provides aggregate byte quota and per-workspace entry ceiling, durable workspace ownership, failed-cleanup retention and crash recovery. Rust settles Docker before socket response; the live Python context then revokes/deletes before exposing the evaluation. Service death and Python-owner death have distinct cleanup paths | Focused exact-limit, cleanup-order, SIGKILL and dead-owner proof pending |
| #582 ownership check | Coordinate exact paths and port ownership with the S3 activation owner | #582 does not touch `preparation.py` or `post_submit_materialization.py`; it owns provider-neutral ArtifactStore activation evidence and S3 composition, while this change reuses the separate existing ArtifactScratchManager/ledger without extending that activation port | Recheck after either branch changes its bounded files |
| Aggregate execution budget | Inspect request resource contract, selected POST budget and service timeout constants | Immutable registry resources include CPU, memory, deadline and output; the current adapter reserves one 60-second cleanup margin. Work uses one absolute deadline/output meter; emergency cleanup uses one 10-second deadline and separate 256 KiB output ceiling | Actual Docker cancellation/resource behavior remains to be exercised in the local matrix |
| Required Rust workspace gate | From `external_checkers/`: `CARGO_BUILD_JOBS=1 cargo fmt --all --check && CARGO_BUILD_JOBS=1 cargo test --workspace --locked` | PASS: 5 SDK, 34 service and 4 project-image tests. Service proof includes custody-first startup, disconnect/CLI stop, one cleanup budget, exact successful-absence queries, marker-preserving ambiguous removal, fatal admission stop, attempt-bound recovery names, production builder `fsize` arguments and kernel exact-byte/plus-one behavior | Pure/fake-Docker tests do not prove actual Docker/runsc behavior |
| Rust strict lint | `CARGO_BUILD_JOBS=1 cargo clippy --manifest-path external_checkers/Cargo.toml -p workstream-checker-service --all-targets -- -D warnings` plus blame and `.github/workflows/backend.yml` inspection | The repaired head reports only `clippy::large_enum_variant` at the unchanged pre-existing `GrantIdentity` (128-byte PRE versus 424-byte POST variant); no suppression or new diagnostic was introduced. The required `external-checker-runtime` CI lane runs locked workspace tests and formatting, not clippy | This optional local strict-clippy probe remains nonzero on that baseline warning; changing the existing serialized grant type is outside this bounded repair |
| Project image and SDK contracts | `CARGO_BUILD_JOBS=1 cargo test --manifest-path external_checkers/Cargo.toml -p workstream-terminal-benchmark-checker` and `CARGO_BUILD_JOBS=1 cargo test --manifest-path external_checkers/Cargo.toml -p workstream-checker-sdk` | PASS: 4 project-package tests over all five originals and 5 SDK contract/canonicalization tests | Real image execution remains pending |
| ART scratch integration | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /home/abiorh/flow/workstream_product_builder/backend/.venv/bin/python -m pytest -q -p pytest_asyncio.plugin tests/checkers/external/test_runtime.py` from `backend/` | PASS: 11 tests, including exact existing-ledger POST byte/entry reservation and cleanup | Does not by itself prove service/Python process-crash ordering |
| Real local matrix | Bounded project-checker probe over originals and work/infrastructure negatives | Future implementation proof; wait for lead-owned Docker capacity | Local `docker-dev` is not hosted gVisor proof |
| Current-source reconciliation | Merge current `main` at `a201d743`; inspect #575 result/findings and Python CHECKERS contracts; run focused existing checker tests | This branch contains the current result shape and no old/new compatibility path | Recheck after the final main reconciliation and hosted checks |

## Review findings

The first plan review was blocked before product edits. Its four valid findings
were: no concrete aggregate scratch/crash owner; no physically separated build
context; per-phase wording that did not prove one immutable request budget; and
an under-specified sealed-cache identity/revalidation boundary. This revision
assigns scratch to the existing ART ledger and TTL reaper, defines labeled
Docker/startup recovery, projects an exact no-follow context, uses one absolute
deadline/output meter with concurrent CPU/memory ceilings, and binds plus fully
rehashes a canonical offline-cache inventory. Focused architecture and security
plan replay is required on the frozen revision before product edits.

The first replay closed physical separation, aggregate registry ceilings and
canonical cache/Docker orphan ownership, then found three narrower wording gaps:
the service/ART cleanup order was reversed; the runtime byte allowance omitted
the existing entry ceiling; and the plan asked the image to echo an unseen grant
digest. This revision follows the actual socket/grant call order, binds and
meters both existing ART ceilings, and has the trusted service attach the parsed
plan to its verified in-memory grant. The final scoped replay was the remaining
prerequisite before product edits.

The final record-only replay passed at `6ad0fb456d8c55f750110e8d23f07e66349a9e8b`.
That verdict authorized this bounded implementation; it is plan evidence, not
runtime or acceptance proof.

The first implementation architecture/security review at
`cbbdd13851d0988cec77c3a6a33bd9e47daec222` found that Docker recovery
preceded listener custody (`ARCH493001`/`SEC493003`), the candidate tar was
metered only after the builder exited (`ARCH493002`/`SEC493001`), blocking
Docker attach did not observe a client disconnect (`SEC493002`), a runtime
inventory duplicated label/repository ownership (`ARCH493003`), and initial,
control and cleanup output did not share explicit aggregate budgets
(`ARCH493004`). This repair acquires socket-parent custody first; reserves the
tar entry and remaining ART bytes before launch with a hard file-size ceiling;
makes every work command cancellation-aware under the request deadline/output
meter; removes the redundant inventory; and gives all emergency cleanup one
bounded deadline/output budget. The affected reviewer tracks must replay on the
next clean candidate; these source repairs are not Docker or hosted runtime
proof.

The affected replay at `746881b3514f5e52c2703faf3c31a79b73f6c4e1` found
that nonzero remove plus nonzero inspect could be misread as absence
(`SEC493004`), recovered container names were not bound to the labeled attempt
(`ARCH493005`), and the kernel-only file-limit test did not prove the production
builder arguments (`TEST493001`). The repair requires successful exact
inventory absence, stops admission on unresolved cleanup, binds every recovered
name to its attempt and allowed reference iteration, and captures the real
builder command to prove the reserved `fsize` argument with a discriminating
guard. These remain source/fake-Docker claims until the real runtime matrix.

## Reconciliation

- Current-source reconciliation: This branch merged final reviewed corpus
  commit `e6a55d26b` and current `main` at `a201d743`, including #575's current
  finding/check result contract. The corpus carries the exact linux/amd64 base
  recipe, bounded harness failures, destructive-state regression and reviewed
  ownership, UTF-8 and UTC-overflow fixes. Parent corpus
  assets remain dependency input rather than this change's implementation diff.
- Next usable boundary: independent review of the source implementation, then
  the lead-coordinated local Docker development matrix and exact built-image
  registration specifications. #580 may register those specs, and #555 may
  combine registration with the public/hosted journey.
- Ownership reconciliation: #582 confirmed no file or port overlap. It owns
  provider activation evidence and S3 composition; this change owns only the
  existing ephemeral `ArtifactScratchManager` workspace/grant extension and must
  not depend on or extend #582's activation guard.
- Remaining risks: representative disk/resource ceilings, the actual built
  checker digest, exact approved linux/amd64 cache execution, cancellation and
  process-crash cleanup, and hosted `runsc` hardening remain unproved. This host
  exposes only `runc`; any later local Docker result is `docker-dev` evidence.
