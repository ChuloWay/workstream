# Local agent loop self-host profile

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: An opt-in Compose overlay, a networkless proof-claim checker image and small operator scripts let one persistent local stack run the existing checker service, register a checker and activate the acceptance lifecycle, leaving guide-rule selection as the named remaining step.

## Intent

Let a developer keep one persistent local Workstream stack that accepts agent
work through the supported public contributor flow (claim, start, prepare,
submit) with automatic checking and, for `human_review_required=false`, the
shared authorized FinalAcceptance. The stack must use existing owners: the Rust
checker service, the registry API, service-actor provisioning and the joint
lifecycle controller. It must not fabricate guide, policy, acceptance or
contribution facts.

## Current behavior

- `docker-compose.yml` runs API, worker, beat, PostgreSQL, Redis and MinIO. It
  has no checker service. The hosted composition has one
  (`deploy/hosted/compose.yml`, `checker-service`) with host paths and `runsc`.
- `backend/app/core/config.py` requires `WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT`
  to equal `WORKSTREAM_ARTIFACT_SCRATCH_ROOT` when the socket is configured.
- `external_checkers/workstream-checker-service` validates a private `0700`
  socket parent and material root, requires each grant root to be owned by the
  sandbox UID, and starts checkers with `docker run --mount type=bind,src=...`,
  which the daemon resolves on its own filesystem.
- `experiments/pilot04_external_checker_runtime/` proves the selected runtime
  in disposable harnesses, seeding some service actors directly and moving the
  lifecycle through test support (`tests/reviews/lifecycle/transition_support.py`).
- `POST /api/v1/service-actors` and `POST /api/v1/operations/external-checker-registry`
  are the supported provisioning and registration operations.

## Bounded change

### Allowed

- `docker-compose.agent-loop.yml`: opt-in overlay with a volume-init step, a
  loopback registry and the `checker` service built from
  `docker/checker/Dockerfile.release`; shared material and socket named volumes
  for API, worker and beat.
- `external_checkers/harnessy_proof/`: the proof checker, its Dockerfile and a
  host-side publish helper that writes the service configuration and registry
  bodies.
- `backend/scripts/provision_local_service_actors.py` and
  `backend/scripts/transition_review_lifecycle.py`, with focused tests.
- `docs/engineering/local-agent-loop.md`, a link from `local-pilot.md`, the
  roadmap entries, `.gitignore` for generated local configuration, and the test
  lane catalogue entry with its fingerprint.

### Not allowed

- Changes to the base `docker-compose.yml`, the backend runtime, checker
  service source, lifecycle controller, authorization catalogue or migrations.
- Guide compilation, policy approval or activation shortcuts; direct SQL writes;
  fabricated Reviews, acceptances or contributions.
- Touching other Compose projects' containers or volumes.

## Design and decisions

- **Overlay, not base edits.** The API, worker and beat need a different
  scratch root and two new environment values only when the checker is used.
  Compose cannot add environment to a service conditionally by profile, and an
  empty socket value would fail settings validation. An overlay selected by
  `COMPOSE_FILE` keeps the base stack unchanged.
- **Material root at the daemon path.** The checker passes the grant path to
  the daemon as a bind source. A named volume mounted at its own
  `/var/lib/docker/volumes/<name>/_data` path makes that source identical in
  every container and on the daemon. This assumes the default data root.
- **Socket on a named volume.** Docker Desktop host-shared paths refuse `chmod`
  on Unix sockets, and the service sets `0600`. The path is 28 bytes, well
  within the 107-byte AF_UNIX limit.
- **Same UID everywhere.** The socket is `0600` and grant roots must be owned by
  the sandbox UID, so API, worker, beat, checker and the sandbox run as
  `LOCAL_UID:LOCAL_GID`. A one-shot root step makes the two volume roots `0700`.
- **Docker socket group.** Docker Desktop exposes the socket as `root:root
  0660`; the checker adds GID 0 by default (`WORKSTREAM_DOCKER_SOCKET_GID`).
  This is root-equivalent daemon access, acceptable only for a local profile.
- **`OPENSSL_armcap=0`.** Already set in the backend development image; the Rust
  service, Docker CLI and the standard-library proof checker do not load
  PyCA's OpenSSL, so no further default is added.
- **Proof checker trust.** It is networkless and checks only the claims in
  `proof.json`. The runbook states this limit.
- **Operator scripts.** Service actors use the public API with a deterministic
  `Idempotency-Key` per identity and a bounded `Retry-After` wait. The
  lifecycle script runs the owner controller with the operator's own AUTH
  decision and supports only the forward `disabled -> shadow -> live` path.
- Rejected: a separate local checker Dockerfile (the release image runs under
  `user:` override), host bind mounts for socket or material, and a combined
  "self-host" bootstrap command that would hide authority decisions.

## Acceptance criteria

- [x] The checker service starts healthy on Docker Desktop and the backend
  adapter reads its health over the shared socket.
- [x] The proof image, published by platform-manifest digest, executes through
  the composed service and returns passing and failing verdicts.
- [x] PRE and POST registry entries register, replay exactly and deny a
  non-operator.
- [x] Service identities provision, replay and report `existing`; a
  non-administrator is denied.
- [x] The lifecycle moves `disabled -> shadow -> live`, reruns are no-ops, a
  non-operator is denied and leaving `live` is refused.
- [x] A draft guide accepts `human_review_required:false`, and Finance publishes
  an UNPAID ContributionPolicy.
- [ ] UNPAID FinalAcceptance through the persistent stack: blocked until guide
  rules select the checker (activation readiness reports
  `post_policy_unavailable`).

## Risk and review routing

- Risk class: `L1` (Docker socket mount and checker isolation configuration in a
  local-only profile; operator scripts that drive authorization-bound owners).
- Required reviewers: `security`, `senior_engineering`, `documentation`, `qa`.
- Human review focus: the root-equivalent Docker socket grant, the
  default-data-root assumption for the material path, and the proof checker's
  trust limit.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Checker logic and result contract | `tests/checkers/external/test_harnessy_proof_checker.py` | Passes; results validate through `ExternalCheckerExecutionResult.model_validate_json` | None for the stated rules |
| Script behavior | `tests/test_local_pilot_scripts.py` | Passes | Live behavior shown only by the drill |
| Docker Desktop runtime | Separate Compose project drill on Apple Silicon (see PR) | Health, two real executions, registration, provisioning, lifecycle | Intel Docker Desktop and native Linux not run |
| Persistent-stack FinalAcceptance | Not run | Blocked by guide rules | Remains |

## Review findings

See the PR for internal reviewer findings and their disposition.

## Reconciliation

- Current-source reconciliation: based on `main` at the time of the PR; no
  owner contracts changed.
- Next usable boundary: decide guide-rule setup that selects
  `harnessy.work_proof` for PRE and POST, then run the UNPAID false-mode
  FinalAcceptance drill on the persistent stack.
- Remaining risks: root-equivalent Docker socket access in the local profile;
  proof claims are not independently verified.
