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
- [ ] API, worker and beat share one `s3_compatible` MinIO configuration and project-scoped scratch; startup creates and verifies the private bucket.
- [x] The token CLI emits distinct, short-lived Flow-HMAC identities without authority claims.
- [x] The runbook uses the existing trust-root and grant operations, prepares a draft project for guide upload, and does not fabricate guide approval.
- [ ] Two differently named stacks can run simultaneously; stopping one does not stop or erase the other.
- [ ] Linux proof exercises live API, prefork worker, beat recovery, PostgreSQL, Redis and MinIO behavior.
- [x] Docker Desktop/macOS support is documented with explicit unverified runtime limits when no macOS host is available.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `architecture`, `security`, `product_ops`, `documentation`, `qa`, `test_delta`
- Human review focus: Compose process topology, bucket startup/readiness, secret and authority boundaries, project isolation, retained-volume teardown semantics, and the limits of the live guide/macOS evidence.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Rendered isolation and topology | `docker compose --profile backend config` | Six services, prefork worker, configurable loopback ports and project-scoped resources render from one local `.env`. | Runtime proof is still required. |
| Local helper contracts | `uv run --project backend --locked --extra dev pytest -q backend/tests/test_local_pilot_scripts.py backend/tests/test_api_contract_e2e.py` | 18 tests pass, including the unchanged API-drill token consumers. | This focused test does not replace the live MinIO/API proof. |
| CI catalogue custody | `uv run --project backend --locked --extra dev pytest -q backend/tests/test_ci_lane_catalogue.py` | 42 tests pass; the new module belongs to the shared-foundation partition. | Hosted lane execution remains external. |
| Linux live stack | Commands in `docs/engineering/local-pilot.md` | Pending the active pinned-source MinIO and backend build. | Docker Engine Linux only; no macOS host is available. |
| Two-stack isolation | Two explicit Compose project names and disjoint ports, then project-scoped teardown | Pending live execution. | Single Linux Docker daemon, not two physical hosts. |

## Review findings

Material findings are recorded here only when they change the durable design or
remaining boundary.

## Reconciliation

- Current-source reconciliation: Base and open pull requests were inspected at `c0c4fe70`; open PRs #485, #486 and #487 do not supply or overlap this runtime stack.
- Next usable boundary: Use the stack for genuine guide setup/recovery and cross-project authorization proof, then complete the public pilot journey in its separately owned chunks. Runner and model-proxy services remain deferred to PILOT-04/PILOT-05.
- Remaining risks: A real Docker Desktop/macOS run and a provider-backed completed guide setup were not available on this Linux host and must not be inferred from Compose or Linux evidence.
