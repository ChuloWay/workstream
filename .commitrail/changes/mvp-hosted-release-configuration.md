# MVP Hosted Release Configuration

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Provide one reviewable single-host Linux release
  configuration for the immutable Workstream API, prefork Celery worker, Beat
  scheduler and existing external-checker service without claiming deployment
  or hosted proof.

## Intent

The existing Compose stack is deliberately development-only. It mounts source,
installs development dependencies, enables Uvicorn reload, uses local Flow-HMAC
verification and depends on MinIO. The first automated MVP needs a separate
release configuration that composes the already implemented API, durable worker
and external-checker runner owners with production-like settings.

This change packages and validates that composition. It does not provision a
host, cloud service, IAM policy, database, broker, collector or checker image,
and it does not establish that a hosted environment is healthy or recoverable.
The connected hosted evidence remains in issue #555 after the dependent
registry, recovery, AWS-storage and project-checker work is merged and an
approved environment is available.

## Current Owners And Gap

- `backend/app/core/config.py` owns application, Flow, artifact, scratch,
  checker-socket, Celery and observability setting validation.
- `backend/app/workers/celery_app.py` owns prefork process initialization,
  queues, Beat schedules, scratch cleanup and bounded diagnostic export.
- `external_checkers/workstream-checker-service` owns exact cached-image
  verification, `runsc` readiness, the no-network/non-root/capability-free
  read-only sandbox, registry-supplied CPU/memory/PID/disk/deadline/output
  limits, normalized failure classification and cleanup.
- `docker-compose.yml` and `docker/backend/Dockerfile.dev` own only the local
  development stack.

No release image or topology currently composes those owners without the local
source mount, reload, development packages, local authentication and MinIO.

## Bounded change

### Allowed files

- `.commitrail/changes/mvp-hosted-release-configuration.md`
- `.dockerignore` (release build inputs only)
- `docker/backend/Dockerfile.release`
- `docker/backend/release-entrypoint.sh`
- `docker/checker/Dockerfile.release`
- `deploy/hosted/compose.yml`
- `deploy/hosted/compose.py`
- `deploy/hosted/release.env.example`
- `deploy/hosted/checker-service.example.json`
- `deploy/hosted/preflight.py`
- `deploy/hosted/README.md`
- `scripts/test_hosted_release_config.py`
- affected hosted-runtime claims only in `docs/roadmap_status.md`

### Prohibited changes

- Product routes, lifecycle logic, authorization, database models or
  migrations, checker execution source, registry behavior, resource-limit
  ownership, Celery task behavior, or artifact-storage implementation.
- Development Compose behavior, CI workflows, root README, CLI behavior or
  frontend behavior.
- AWS account, IAM, bucket, database, broker, collector, DNS, TLS, Docker daemon
  or host provisioning; credential access; billable resource creation; actual
  deployment; PR merge.
- Ad hoc checker launchers, another image/cache resolver, direct product-row
  writes, test helpers in product configuration or compatibility paths.
- Claims that rendered configuration, local image builds or development `runc`
  results establish hosted `runsc`, AWS custody, Flow identity, diagnostic,
  backup/restore or connected-journey proof.

## Design And Security Boundaries

The release uses externally published digest-qualified API and checker-service
images. Separate release Dockerfiles provide locked build targets without
source mounts, development extras or reload. API, worker and Beat run from the
same exact backend image. The release configuration points to externally
managed PostgreSQL and Redis endpoints and does not provision their services.

The API and worker share a fixed private host scratch path and checker Unix
socket with the external-checker service. The path inside every relevant
container is identical to its absolute host path because the checker service
passes that path to the host Docker daemon. The existing runner validates the
private root, sealed grant material, configured non-root UID/GID, exact cached
platform manifest and config image ID. Its release configuration fixes
`runtime=runsc` and `isolation_mode=gvisor`.

The checker service receives the host Docker socket so it can invoke the
existing trusted launcher. That socket grants host-level daemon control. gVisor
protects the untrusted checker workload; it does not protect the host from a
compromised checker-service controller. The topology therefore requires a
dedicated runner host and trusted daemon, restricts the checker service to the
exact Docker-socket group, publishes no runner port, and gives the controller no
network. This change does not claim to reduce Docker-controller authority.

Application secrets are mounted as private files and loaded through one explicit
role mapping. The API receives database, broker, rate-limit and pagination
secrets; the worker receives database, broker and OpenAI secrets because it
hosts setup jobs; Beat receives only the broker secret. The loader rejects an
unknown role or missing role-required file, clears possible ambient secret
values, requires nonempty regular files with the running identity and mode
`0400`, never evaluates file content, never logs it and removes every selector
before executing the application. The operator must protect host ownership and
modes; release preflight checks file presence, ownership/mode and nonzero size
without reading content. No local-HMAC, development-auth, MinIO/static-AWS
credential or debug setting is accepted by the release profile.

Docker Compose gives shell variables precedence over `--env-file`. Both
preflight rendering and every documented Compose operation therefore use the
same small wrapper environment constructed only from the parsed, allowlisted
release file plus fixed process-path values. Ambient image, Flow URL, secret
path, Compose selector and Docker daemon selector values are never forwarded.

Preflight stays release-specific. It checks digest-qualified service images,
the fixed mount/path relationship, private host inputs, exact gVisor/runsc
configuration, configured cache identities, local Docker runsc registration
and the point-in-time presence of matching locally cached images. The health
check covers only the canonical socket and registered runsc runtime; the runner
revalidates exact cache identity for each execution. Preflight uses the existing
application settings and checker runtime owners rather than duplicating their
domains. Preflight cannot attest the active cloud
identity, absence of extra IAM permissions, external service availability,
diagnostic delivery, backup/restore recoverability or live product health.

Issue #582 owns AWS provider activation and proof. This configuration wires the
non-secret AWS S3 profile, region, bucket, prefix, virtual addressing,
workload-identity mode and method plus the canonical release ID, exact IAM
role/policy ARNs, trust-policy digests, bootstrap principal and bucket-policy
digest into the shared API/Celery/Beat Settings environment. It also requires
explicit operation, complete-read and persistence timeout settings; the example
values are unmeasured and do not assert a live result. Format, partition/account
coherence, required distinct identities, eligibility math and runtime
enforcement remain with #582's canonical application owner rather than being
duplicated in preflight. The role-isolated proof-job profile remains pending the
stable #493 integration and is not invented as another release service here.

## Acceptance criteria

- [ ] Release build targets use digest-pinned bases and committed Python/Rust
  locks, omit development dependencies and do not run Uvicorn reload.
- [x] Rendered release topology contains exactly the existing API, prefork
  worker, Beat and checker-service process roles, all from digest-qualified
  images, with no source mount, MinIO, embedded PostgreSQL or embedded Redis.
- [x] API and worker use the identical fixed absolute scratch and checker-socket
  paths; the checker service uses the same host-visible material path.
- [x] The checker service is non-root, read-only, networkless, attached only to
  the exact Docker-socket group, and health checks only its canonical socket and
  registered `runsc` runtime. Full preflight checks cache identity once and the
  existing runner revalidates it for each execution.
- [x] Real Flow verification and AWS workload identity are required; local auth,
  local Flow-HMAC, static AWS keys, MinIO and debug settings fail preflight.
- [x] Every AWS-backed API, worker and Beat Settings process receives the same
  required release digest and exact role, policy, trust and bucket-policy
  identities without treating those non-secret values as live proof.
- [x] Required secrets are mounted and loaded only for their API, worker or Beat
  role and are never printed or evaluated; absent, unrelated, broad-mode,
  wrong-owner or empty files fail closed.
- [x] API, worker and Beat have bounded health/restart/drain configuration;
  runner/cache absence fails closed and existing product owners retain
  infrastructure-result classification.
- [x] The operator guide covers preparation, non-disclosing preflight,
  migration/start, API/runner/worker readiness, drain/restart, supported forward
  recovery and environment-owned PostgreSQL backup/restore verification without
  deleting immutable product or artifact data.
- [x] Focused tests distinguish every unsafe configuration above from one valid
  fixture and validate the rendered Compose topology without deploying it.
- [x] Roadmap wording distinguishes prepared release configuration from pending
  hosted deployment, resource measurement and recovery evidence.

## Verification Plan

1. Run focused unit tests for the secret loader contract and release preflight,
   including hostile ambient interpolation, exact AWS evidence flow to every
   Settings process, role/mount isolation and mutated tag/local-auth/static-key/
   non-runsc/cache/path/mode cases.
2. Render `deploy/hosted/compose.yml` with disposable placeholder identities and
   secret files; assert service commands, immutable images, mounts, security
   options, health checks and absence of development services/settings.
3. Build both release images from the committed locks. Inspect the backend image
   for production dependencies and commands and the checker-service image for
   the exact compiled binary and Docker client.
4. Run repository formatting, Markdown-link, stale-wording and Commitrail
   checks. Assess local sheet constraints only if roadmap exports are present.
5. Freeze one clean candidate and route architecture, security, product/ops,
   QA, documentation, test-delta and senior-engineering review. Add CI-integrity
   review only if CI or deterministic gate wiring changes.

Actual runsc workload execution, selected project images, AWS calls, Flow token
verification, collector behavior, resource measurements, drain/restart under
load and backup/restore execution require the approved hosted environment and
remain parent #555/#583 evidence rather than local configuration proof.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `architecture`, `security`, `product_ops`, `qa`,
  `documentation`, `test_delta`, `senior_engineering`
- Conditional reviewer: `ci_integrity` only if workflow or gate wiring changes
- Human review focus: Docker-socket host authority; dedicated runner-host
  assumption; same-path material custody; secret ownership and non-disclosure;
  fail-closed Flow/AWS settings; socket/runsc health and point-in-time cache
  proof; worker drain and restart;
  retained-data backup/forward-recovery semantics; honest separation of
  configuration, deployment and live proof.

## Plan Review

Author assessment: the existing owners support the proposed composition without
new product abstractions, and the fixed paths, private file checks, digest-only
identities, exact cache validation and dedicated-host requirement make the
bounded plan testable. The Docker-controller trust boundary remains material,
so the overall change stays L1 rather than being characterized as low risk.

Lead review disposition: `PASS`. Keep source-image builds separate from
operator-supplied digest release runs; execute the secret loader in tests for
malformed paths, empty files, no evaluation and no content logging; leave
application-setting and checker-runtime health validation with their existing
owners. Live infrastructure evidence is unavailable by design and remains
explicitly provisional.

## Evidence

Source/configuration candidate checks:

- `python3 -m unittest -v scripts.test_hosted_release_config`: eleven focused
  tests pass, including required AWS evidence custody in each rendered backend
  process, hostile ambient Compose rendering/operation and executed role-specific
  secret-loader failure/non-evaluation/non-disclosure cases.
- `uvx ruff@0.15.22 check deploy/hosted/preflight.py deploy/hosted/compose.py
  scripts/test_hosted_release_config.py`,
  `/bin/sh -n docker/backend/release-entrypoint.sh` and `git diff --check` pass.
- `python3 scripts/check_markdown_links.py` passes for the three changed
  Markdown files; stale Workstream/artifact/authorization wording and Commitrail
  record checks pass. No local spreadsheet export is present to reconcile.
- Historical evidence: `docker build --file docker/checker/Dockerfile.release --tag
  workstream-checker-release:test .` passes with locked Cargo and two compiler
  jobs. Local image ID
  `sha256:fe6d6905d1d600d3957536301aded948b03a72448fa4b8193d60760df5d14362`
  runs as UID/GID 10001, reports Docker CLI 29.1.3 and loads the compiled service
  binary. This is a local image ID, not a published repository digest or release
  identity.

The earlier backend and checker image builds predate the latest merged backend
and Rust SDK source plus this loader hardening and are historical evidence only.
Exact-source rebuild and inspection remain queued behind the shared proof
workload. AWS, Flow, runsc workload, selected
checker-image, diagnostics, recovery and backup/restore proof remain unavailable
by design; no deployment or hosted readiness is claimed.
