# PILOT-01 — Isolated Local API And Worker Stack

- Initiative: `None`
- Durable disposition: `Complete`
- Intended merge outcome: A developer can start one checkout-isolated API, prefork worker, scheduler, PostgreSQL, Redis and MinIO stack and use existing Flow-style local authentication and authorization operations.

## Intent

Provide the base runtime needed to exercise real pilot workflows on a developer
host. The stack must use the existing artifact, authentication, authorization
and durable-worker owners so local convenience cannot become a second product
path.

## Current behavior

`docker-compose.yml` provides PostgreSQL, Redis, MinIO and an optional API. Its
API port and MinIO port are fixed, artifact storage is disabled, local auth uses
one development identity, and there is no Compose worker or scheduler. The
canonical worker topology and recovery schedule already live in
`backend/app/workers/celery_app.py`; local Flow-HMAC signing, the trust-root CLI,
and authorized grant APIs already exist in the real API drills and backend.

## Bounded change

### Allowed

- Configure `docker-compose.yml`, `docker/backend/Dockerfile.dev` and the root
  `.env.example` for a project-scoped six-service local stack with configurable
  published ports and non-root writable scratch.
- Add a local-only MinIO bucket readiness helper, extract the existing
  Flow-HMAC test signer for reuse by its real API drill, and add a CLI wrapper
  with focused tests.
- Add `docs/engineering/local-pilot.md` for clean start, identities, existing authority bootstrap, project/guide setup, recovery, isolation and teardown.
- Reconcile only the Docker/local-storage quickstart in `README.md` with the
  required ignored root environment and six-service stack.
- Reconcile only the affected local-runtime and pilot claims in `docs/roadmap_status.md`.
- Add the focused helper test to the existing shared-foundation CI catalogue;
  do not change lane selection or gate behavior.
- Register the three executable local helpers in the exact behavior-ownership
  partition and allow only that additive shared-target transition.
- Teach the stale-authorization documentation check to recognize the exact
  Docker Compose `worker` service-token positions used by this runbook, with
  positive command cases and negative human/identifier/argument controls.
- Add this standalone change record.

### Not allowed

- Database migrations, ORM models, backend routes, authority contracts, new authentication modes, direct database bootstrap writes or authorization bypasses.
- Runner, model-proxy, checker-sandbox, frontend, cloud, hosted or production bootstrap work.
- A fabricated approved guide, a complete contributor-journey claim, or changes to the existing solo-worker guide drill.
- Destructive or cross-project Docker cleanup; all commands remain scoped to an explicit Compose project.

## Design and decisions

Compose reuses the backend development image for API, worker and beat. The
worker selects the existing prefork lifecycle, and beat consumes the recovery
schedule already owned by the Celery application. API startup provisions and
verifies only the configured checkout-local MinIO bucket before migrations and
application startup; the application and worker still access bytes only through
the canonical `ArtifactStore`.

Every published host port is interpolated from the ignored checkout-local
`.env`. Compose's project name scopes containers, the default network, retained
database/broker/object volumes and bounded scratch. Local tokens contain
identity facts and empty role claims; the existing irreversible trust-root
bootstrap and authorized grant APIs remain the only way to confer authority.

## Acceptance criteria

- [x] Compose declares API, prefork worker, beat, PostgreSQL, Redis and MinIO with API, database, broker and both MinIO ports configurable.
- [x] API, worker and beat share one `s3_compatible` MinIO configuration and project-scoped scratch; startup creates and verifies the private bucket.
- [x] The token CLI emits distinct, short-lived Flow-HMAC identities without authority claims.
- [x] The runbook uses the existing trust-root and grant operations, prepares a draft project for guide upload, and does not fabricate guide approval.
- [x] Two differently named stacks can run simultaneously; stopping one does not stop or erase the other.
- [x] Linux proof exercises live API, prefork worker, beat recovery, PostgreSQL, Redis and MinIO behavior.
- [x] Docker Desktop/macOS support is documented with explicit unverified runtime limits when no macOS host is available.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `architecture`, `security`, `product_ops`, `documentation`, `qa`, `test_delta`
- Human review focus: Compose process topology, bucket startup/readiness, secret and authority boundaries, project isolation, retained-volume teardown semantics, and the limits of the live guide/macOS evidence.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Rendered isolation and topology | `docker compose --profile backend config`; Compose-resolved project name plus label-filtered resources | Six services, prefork worker, configurable loopback ports and four project-scoped volumes render; supported name/resource inspection commands execute successfully. | Compose rendering is Linux-host evidence only. |
| Local helper contracts | `uv run --project backend --locked --extra dev pytest -q backend/tests/test_local_pilot_scripts.py backend/tests/test_api_contract_e2e.py` | 19 tests pass, including the unchanged API-drill token consumers and a transient first-listener retry. | This focused test supplements the live MinIO/API proof. |
| CI catalogue custody | `uv run --project backend --locked --extra dev pytest -q backend/tests/test_ci_lane_catalogue.py` | 42 tests pass; the new module belongs to the shared-foundation partition. | Hosted lane execution remains external. |
| Repository gate custody | `python3 scripts/check_stale_authorization_docs.py`; `python3 -m unittest scripts.test_lightweight_agent_gates`; behavior-ownership validation and focused partition test | Technical Compose service tokens pass while comments, option/command arguments, identifiers and human authority prose remain rejected; the ownership partition adds exactly the three shared local helpers and rejects a fourth target. | Hosted gate replay remains external. |
| Linux live stack | Pinned-source build, six-service `up --wait`, Celery inspect, public Flow identity/bootstrap/grant calls, real PDF upload, MinIO `HEAD`/`GET` and forced worker/beat restarts | All six services become healthy; the worker reports prefork concurrency two and `pong`; five distinct humans, all six fixed service actors, two projects and two scoped submitter grants use existing public operations; the 855-byte guide object survives restart with its digest unchanged; the same durable setup ID remains reserved when missing provider credentials stop compilation; beat recovers from `SIGKILL` with its retained schedule. | No provider credential was available, so a successful model-backed compilation is not claimed. Docker Engine Linux only; no macOS host is available. |
| Runtime image contract | Backend image build and no-dispatch runtime construction; missing-credential construction probe; fresh UID 501/GID 20 scratch-volume write | The committed Agents SDK extra is installed; dummy-key construction succeeds without provider I/O; absent credentials fail closed; an existing Debian numeric group and non-root UID own and write the copied-up scratch volume without broad permissions. | Actual provider dispatch remains outside this proof. |
| Two-stack isolation | `ws-pilot-runtime-dev` and `ws-pilot-runtime-peer` with disjoint ports, label-scoped inspection, full-profile shutdown/restart and exact peer disposal | Both six-service stacks are healthy together. Stopping the primary leaves peer API, worker topology, PostgreSQL head, Redis marker and MinIO marker intact; restarting the primary restores its two projects, Redis marker and guide object; peer disposal leaves the primary healthy. | Single Linux Docker daemon, not two physical hosts. |

## Review findings

Full-stack lifecycle commands include the backend profile, and resource
inspection resolves the project name through Compose rather than an unexported
shell variable. The image installs the committed agent runtime and supports an
existing numeric host group. Worker and beat PID files are container-local,
while scratch artifacts and the beat schedule remain project-volume state. The
runbook provisions all six existing guide/artifact service identities and
secures ignored environment copies before secrets are added.

## Reconciliation

- Current-source reconciliation: Base and open pull requests were inspected at `c0c4fe70`; open PRs #485, #486 and #487 do not supply or overlap this runtime stack.
- Next usable boundary: Use the stack for genuine guide setup/recovery and cross-project authorization proof, then complete the public pilot journey in its separately owned chunks. Runner and model-proxy services remain deferred to PILOT-04/PILOT-05.
- Remaining risks: A real Docker Desktop/macOS run and a provider-backed completed guide setup were not available on this Linux host and must not be inferred from Compose or Linux evidence.
