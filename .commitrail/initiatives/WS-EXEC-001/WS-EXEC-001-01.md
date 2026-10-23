# WS-EXEC-001-01 — Production Smol node lifecycle

- Initiative: WS-EXEC-001
- Durable disposition: Complete
- Intended merge outcome: execute existing registered checker images in fresh Smol microVMs through the existing typed execution boundary, with prepared sessions and recoverable exact-owner cleanup.

## Intent

Replace the qualification-only path with the production runtime mechanism needed
by upload preparation and durable POST execution. This boundary is a prerequisite;
the initiative is complete only after public upload/admission/worker proof.

## Current behavior

The Rust service runs each verified ART grant through `execute_container`, accepts
one socket connection at a time and closes runtime vocabulary over runsc/runc.
Existing owner files and startup cleanup protect Docker container ownership.

## Bounded change

### Allowed

- `external_checkers/`: production Smol driver, generic static guest launcher,
  configuration/cache provisioning, bounded session protocol and focused tests.
- `backend/app/interfaces/external_checker_execution.py`,
  `backend/app/adapters/checkers/`, and their focused tests: unchanged execute transport,
  fixed factory composition and closed Smol health/receipt validation. Project
  preparation remains private inside Rust execute; the typed prepare/inspect/
  default handle belongs only to boundary 2's ART-owned port.
- `backend/scripts/checker_image.py`, shared manifest validation and Smol cache
  provisioning commands, plus their tests: one canonical platform identity rule.
- `backend/scripts/test_lane_catalogue.py`: register the new cache test module
  in the existing shared-foundations lane; preserve strict suite completeness.
- `backend/scripts/behavior_ownership.py` and its canonical partition: register
  the two new image/cache command modules without relaxing target completeness.
- Affected checker receipt validators, configuration, execution contract docs,
  capability ledger and this initiative/index: truthful runtime support.

### Not allowed

- Changing project limits, authorization, locked policy, artifact custody,
  contributor-work semantics, final acceptance or economic effects.
- Claiming upload/guest-ART integration complete in this first boundary.
- Importing the experiment into production or forwarding host Docker/credentials
  into checker VMs; managed services, runtime plugin discovery, broad cleanup.
- Editing the separately owned uncommitted model-runtime implementation.

## Design and decisions

One service instance selects one deployment-level engine. Add the closed pair
`runtime="smolvm"`, `isolation_mode="smol-microvm"` alongside the existing
`runsc/gvisor` and `runc/docker-dev` pairs. Keep the sole CHECKERS
`external_checker_execution/unix_socket` factory path. No project runtime
selector, discovery, fallback engine or generic command API. ART's separate
narrow trusted-intake port (boundary 2) reuses the private Rust engine, not the
project-image execution capability.

Use verified prebuilt local image archives bound to platform manifest/config
identities. A static guest launcher runs the image's configured entrypoint and
command without requiring Python. It enforces requested CPU/memory, bounded PIDs,
non-root UID/GID, dropped capabilities, read-only root/input and bounded private
scratch. Host cgroups bound VMM overhead separately. Missing enforcement fails
readiness; no silent limit rounding or vCPU-only CPU claims.

### Preparation and custody contract

Preparation always reserves one trusted intake VM during upload, including
zero-project-checker policies. Project images are not speculatively prewarmed:
multiple PRE bindings execute in locked order after default passes, each with
fresh state. The same private lease machinery supports project execution, but
Python CHECKERS gets only typed execute, never a universal VM handle.

The future ART adapter owns an opaque nonserializable process-local handle on a
private live socket. The node lease binds owner epoch, random lease ID, trusted
intake image/platform/config and default behavior identities, phase, resource
tuple, locked policy digest, monotonic deadline plus restart expiry, and later
the sealed archive hash/size and manifest-bound reservation identity. Preparation
creates no artifact grant, checker reservation or result. Boundary 2's distinct
inspect/extract and post-reservation default operations preserve the sequence
specified in the overview. PRE/POST share that ART seam and scratch owner.

Node states: preparing -> ready -> executing -> cleaning -> closed. Preparation
failure, peer EOF, explicit abort, cancellation, expiry and success all enter
cleaning. Execution consumes once; wrong owner/epoch/image/resource/phase/policy,
expired or replayed handles fail without launching. At most three retries of a
known pre-launch preparation failure are allowed within the original deadline,
only after confirmed VM/cgroup absence. Launched or unknown checker outcomes
never retry in this layer. Existing durable job owners decide later retries.

An independent OS guardian process per lease survives controller SIGKILL, observes
controller/socket ownership and absolute expiry, then performs exact-owner
cleanup. Startup reconciles persisted owned leases before readiness. Capacity
counts preparing, ready, executing and cleanup-unconfirmed resources; bounded
connection admission rejects excess work as recoverable infrastructure failure.
Cleanup uncertainty closes node admission, retains capacity, cancels active
sessions through their guardians, and requires confirmed VM AND cgroup absence
before readiness resumes. Persistent node-owner locking prevents two controllers
from reconciling each other's active leases. Foreign VM/cgroup controls survive.

### ART seam frozen for boundary 2

The pinned intake image reuses canonical ZIP safety and default implementations.
Inspection/extraction precedes selected reservation; default execution follows
its committed lease. Extracted bytes return as bounded raw file streams into
ART-allocated quota scratch, verified against the sealed manifest. Project images
only consume existing read-only grants. The service-owned intake image and default
behavior digest appear in health and intake receipts and cannot be selected or
asserted by a project checker. No production host ZIP/default fallback remains.

## Acceptance criteria

The table records the acceptance map. Boundary 2 rows remain future proof;
executed node evidence and its limits are described below.

| Boundary | Required observable proof |
|---|---|
| Project execution | `smol_pre_python`, `smol_pre_native`, `smol_post_python`, `smol_post_native`: unchanged SDK through Python adapter, distinct PRE/POST material identities |
| Intake ordering (boundary 2) | `default_only_pre`, `ordered_pre_bindings`: upload overlaps trusted intake preparation; inspect before reservation, default after reservation, project checks after default; unused intake cleanup |
| Intake authority (boundary 2) | `project_cannot_supply_intake_receipt`, `pre_post_use_guest_intake`: pinned trusted image/behavior, exact raw archive, canonical malformed-ZIP corpus, no production host parse/extract |
| Session identity | `reject_prepared_substitution`: image, config/platform, resources, phase, policy, owner epoch, expiry and foreign lease rejection; `execute_once_no_unknown_retry` |
| Concurrency | `concurrent_at_capacity`, `capacity_rejection_cleans`: simultaneous independent connections, finite active slots and no VM/cgroup leaks on overflow |
| Guest resources | `cpu_quota_enforced`, `memory_and_pids_enforced`, `output_bounded`: adversarial execution, not config readback alone |
| Isolation | `nonroot_no_caps`, `readonly_material`, `hidden_cgroup_controls`, `network_denied`, `disk_vmm_ceiling`: malicious checker cannot mutate resource limits, input or host state |
| Recovery | `controller_kill_guardian_cleanup`, `startup_reconciles_owned`, `foreign_resources_survive`, `cleanup_uncertain_closes_readiness`: independent guardian lifetime and confirmed absence |
| Existing engines | Existing Docker/runsc service and adapter contract suite, including cancellation, exact grant identity and sanitized infrastructure outcomes |

## Evidence

Executed on the authorized isolated EC2 node with Smol 1.31.4 and real KVM:
`smol_runtime.py` passes Python and native PRE/POST requests, non-root/capability,
read-only input/root and image-device denial, CPU, memory, PID, scratch disk,
output and deadline enforcement. `smol_recovery.py` observes concurrent running
VMs at capacity, rejected overflow, disconnect cleanup, controller SIGKILL,
foreign VM/cgroup survival, failed deletion closing readiness, and restart
reconciliation. Cleanup checks exact VM records, lease files, VM disk paths and
cgroups. Python adapter execution also validates the returned runtime receipt.
These are synthetic ART grants, not public API/transaction/worker evidence.

The clean EC2 Rust workspace test and optimized build run as the non-root grant
issuer in an isolated build container. Python adapter and cache verification
suites cover existing transports and image substitution. PR evidence binds the
review candidate, commands, binary and image hashes and retained live outputs;
local compiler crashes are not reported as passing proof. Existing hosted
Docker configuration is unchanged and no gVisor deployment is claimed.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, qa, test_delta, documentation, reuse_dedup; CI integrity if workflows change.
- Human review focus: isolation enforcement, lease/ownership/restart races and exact image/material identity.

## Review findings

Plan corrections address WS-EXEC-PLAN-ARCH-001..004: two-phase ART custody,
separate typed capabilities, bounded preparation states, sole transport provider,
closed deployment engine values and atomic future proof cases. Architecture plan
review passed on `7a52412a2`; implementation review remains required.

## Implementation observations

The existing bounded subprocess collector is shared by Docker and Smol. Smol
runs under a delegated systemd controller subgroup; attempting to move children
from an unrelated SSH scope correctly fails. The node now refuses that topology
at startup. Guest swap is disabled in the qualified kernel (no swap-limit file);
bootstrap requires explicit zero SwapTotal when that interface is absent.

Smol hard-links imported archives into its private cache. An initial single-link
check rejected restart after a successful import; the regression now permits
read-only aliases while still checking every pinned byte and platform identity.
A trusted guest supervisor remains outside the workload cgroup to distinguish
OOM from checker failure before Smol tears down its execution namespace. Project
exit codes cannot forge that supervisor classification. These are observed
integration repairs, not claims that the complete initiative is delivered.
An optimized-build startup failure exposed an omitted KVM ioctl argument;
explicit zero now makes readiness reliable. Recursive `nodev` protects against
image-owned device files, with a narrow exception for the trusted `/dev` whitelist;
the live adversarial image includes a device file to exercise that denial.

The implementation review found and repaired: incomplete cache manifest graph
closure (ARCH/REUSE-SMOL-001); stale next-boundary wording (DOC-SMOL-001);
non-discriminating device and post-launch failure fixtures plus missing retry
proof (QA-TD-SMOL-001..003); and an io_uring path around the direct socket filter
(WS-EXEC-SEC-001). The cache now shares publisher validation, and native guest
proof requires io_uring denial before a socket operation can be submitted.

## Reconciliation

Hosted CI exposed an omitted cache-test catalogue entry before running its
lanes. Registering that module restores complete selection; no check, test,
service or exit-status requirement is weakened. CI integrity review covers
this additional affected owner.

- Current-source reconciliation: `733c752f7` adds the merged audit restore-path repair without changing these runtime owners.
- Next usable boundary: typed same-request preparation and canonical guest ART processing.
- Remaining scope: upload-overlapped trusted intake and public durable-worker proof remain boundaries 2 and 3. Independently owned model gateway integration remains separate until its stable boundary is available.
