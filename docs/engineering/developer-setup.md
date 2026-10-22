# Developer Setup

This guide holds the complete local setup for the Workstream backend. The
[README](../../README.md#run-workstream-on-your-computer) has a short Docker quick start.

The supported backend setup uses CPython 3.11 or 3.12. The pinned Docker image
provides the Linux environment for macOS and Windows contributors. Guide
originals are stored in ArtifactStore and read by the configured agent runtime;
the backend does not run a separate guide extractor.

## Docker Workflow (Recommended)

Prerequisites are Git, Docker Engine, and Docker Compose v2. From the repository
root, create the ignored checkout-local configuration, give it a unique
`COMPOSE_PROJECT_NAME`, replace every `change-me` value and select unused host
ports. The [local pilot runbook](local-pilot.md) documents
secret generation, identities, grants, isolation and teardown.

```bash
cp .env.example .env
chmod 600 .env
```

The `chmod` command applies to Linux, macOS and Git Bash. PowerShell users must
restrict the copied file to their Windows user with an equivalent private NTFS
ACL before adding secrets.

Then build the native-architecture Linux images and start the API, prefork
Celery process, scheduler, PostgreSQL, Redis and MinIO:

```bash
docker compose --profile backend up --build --wait
```

Then verify the API with the command for your shell:

```bash
# macOS, Linux, or Git Bash
curl --fail http://127.0.0.1:<WORKSTREAM_API_HOST_PORT>/api/v1/health
```

```powershell
# PowerShell
Invoke-RestMethod http://127.0.0.1:<WORKSTREAM_API_HOST_PORT>/api/v1/health
```

Replace the placeholder with the port selected in root `.env`. The expected
response is `{"status":"ok"}`. The backend applies Alembic migrations before
serving and all published services bind only to host loopback. API, Celery process and
beat use the same S3-compatible MinIO and local Flow-HMAC settings. Startup
creates and verifies the checkout-local bucket; authority still comes only from
the existing trust-root and grant operations.

The pinned image supports Linux x86_64 and aarch64. On Docker Desktop, it runs
inside the Docker VM.

Run focused checks in the same containerized environment:

```bash
docker compose run --rm --no-deps backend python -m pytest -q tests/test_app.py tests/test_guide_formats.py tests/test_guide_runtime_workspace.py
docker compose run --rm --no-deps backend ruff check app tests scripts
```

Dependency changes require a rebuild:

```bash
docker compose build backend
```

## Native Linux Workflow

Use this path only with CPython 3.11 or 3.12 on Linux glibc 2.27 or newer and
an x86_64 or aarch64 machine. Docker is still used for backing services.
Confirm that `python3 --version` reports Python 3.11 or 3.12 before creating
the environment. Install uv 0.12.3 and use the
committed lockfile; an unconstrained pip install is not a supported setup path.
Create and secure the root Compose configuration before its first command, as
described in the [local pilot runbook](local-pilot.md). Give it
a unique project name, replace every required secret and choose unused backing
service host ports. The separate `backend/.env` configures the native process.

```bash
cp .env.example .env
chmod 600 .env
# Edit root .env before continuing.
docker compose up -d --wait postgres redis
cd backend
cp .env.example .env
chmod 600 .env
# Edit backend/.env before continuing.
python3 --version
uv --version
uv sync --locked --extra dev --python python3
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn app.main:app --reload
```

The v0.1 schema starts at the single `0001_uuid7_v01` Alembic revision.
Development databases stamped with any earlier revision are intentionally not
upgradeable: delete and recreate the local database, then run `alembic upgrade
head`. Workstream never rewrites or compatibility-stamps an old database.

Verify the API from another terminal with:

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
```

Both files are ignored. In `backend/.env`, set `WORKSTREAM_DATABASE_URL` to the
root file's PostgreSQL password and selected loopback host port, and set
`WORKSTREAM_CELERY_BROKER_URL` to its Redis loopback host port. When native
artifact storage is enabled, also select the MinIO profile and copy the root
file's bucket and credentials while using the selected MinIO API host port in
the loopback endpoint. These native process URLs use `localhost`; Compose
containers continue to use internal service names and ports. The `chmod`
commands are for POSIX shells; PowerShell users need equivalent private NTFS
ACLs.

## Native Unified Guide Inference

Set `WORKSTREAM_PROJECT_AGENT_MODEL=gpt-5.6-terra` (or your chosen supported model)
and `OPENAI_API_KEY` in ignored `backend/.env`. Runtime, provider/API protocol,
model and instructions are separate settings in `backend/.env.example`.
Prepare the ignored root `.env` as described in the Docker workflow and start
backing services using its port and credential settings. Put native backend and
provider settings in ignored `backend/.env`, then install the agent runtime and
load that file into API and Celery worker:

```bash
docker compose up -d --wait postgres redis minio
cd backend
uv sync --locked --extra dev --extra agents
uv run --env-file .env uvicorn app.main:app --reload
# In another terminal, from backend/:
uv run --env-file .env celery -A app.workers.celery_app worker --pool=prefork -Q celery --beat --loglevel=info
```

The model key must be in the process environment; `--env-file` supplies it without
shell-exporting or printing it. For connected guide testing, start Postgres,
Redis and MinIO, create the private bucket as described below, and enable the
S3-compatible settings in `.env`. The disabled-store first-run profile does not
support guide artifact ingestion. Committed original-document readiness runs one compilation
and stops at findings and draft proposals; manager review/approval remains separate.

Project guides do not need to repeat platform upload limits. Setup leaves absent
project-specific file, expanded-package, compressed-archive and entry-count
limits null. ART still enforces its configured platform safety limits and storage
admission quotas. An explicit project limit adds a restriction; it cannot relax
platform enforcement. Platform defaults are not copied into frozen project policy.

## Logs, Shutdown, And Reset

The API and prefork Celery process emit privacy-bounded structured logs and can export
explicit traces and metrics to an optional OTLP HTTP/protobuf collector. See the
[observability operations guide](observability.md) for the
configuration, safe field contract, failure behavior, outbox trace boundary,
and on-demand profiling procedure. Implemented instrumentation does not imply a
collector or monitoring service is configured or deployed.

```bash
docker compose --profile backend logs -f backend worker beat
docker compose --profile backend down
```

For the native workflow, stop Uvicorn with `Ctrl+C` before running
`docker compose down` for the backing services.

Database recreation is destructive and must be scoped to your disposable local
environment. First stop its API, Celery workers and scheduler. Confirm the Compose
project name, database host/port and attached volume with `docker compose ps` and
`docker volume inspect <exact-volume-name>`. Do not reset a shared environment or
another worktree's services. Remove only the verified disposable PostgreSQL volume
after stopping that Compose project's containers; do not use `down --volumes`,
which also removes artifact storage.

The UUIDv7 schema uses the distinct, Compose-project-scoped
`workstream_postgres_uuid7_data` volume. Starting it does not convert or erase the
old development volume. Once you have verified that the old volume is disposable
and has no remaining consumers, it can be removed separately by its exact name.
Compose also uses a fresh `workstream_redis_uuid7_data` volume so jobs from the
discarded database are not reused. For subsequent database resets, reset only
that environment's owned queue volume before restarting Celery workers; external
Redis configurations require their own verified private queue reset. Use a fresh
private artifact bucket/namespace for the new database;
do not delete retained/shared S3 or MinIO objects as part of a database reset.

## Backing Services And Artifact Storage

Workstream uses Postgres locally and in CI. It uses Celery with Redis for
durable local project setup jobs and automatic pre-review checker gates. MinIO
provides the S3-compatible artifact protocol in local development and CI. Start
the local services with:

```bash
docker compose up -d --wait postgres redis minio
```

MinIO is built from verified, pinned upstream source using the shared
[development/CI image recipe](../../docker/minio/README.md), rather than an unavailable
vendor image. The first build needs network access and compilation resources;
later builds reuse Docker's cache. CI builds or restores this image once and
shares it across the existing backend jobs. This does not change the hosted
AWS S3 provider or delete existing artifact volumes.

Set every published host port in the ignored root `.env`: API, PostgreSQL,
Redis, MinIO API and MinIO console. Native-backend users must put the same
selected backing-service ports in `backend/.env`; containerized services always
use the internal DNS names and ports.

MinIO uses checkout-local static credentials and the private bucket selected in
root `.env`. API startup creates and verifies that bucket before migrations;
the application and Celery process continue to access objects only through the
canonical `ArtifactStore`. Configure a native runtime with the exact
[artifact storage settings](../spec_artifact_storage_service.md#s3-compatible-adapter)
and the same private bucket.
The repository-managed MinIO port is bound to host loopback. A Workstream
process running on a separate non-production container network may instead use
an operator-controlled private MinIO endpoint; that remains development/test
protocol proof and never qualifies as hosted-provider activation evidence.
Native AWS S3 accepts workload-identity configuration but remains
runtime-ineligible until live deployment proof is approved; startup fails with
`artifact_provider_live_proof_required` before credential probing or provider
I/O.

The local development URL uses the password and PostgreSQL host port selected
in the ignored environment files:

```text
postgresql+asyncpg://workstream:<password>@localhost:<port>/workstream
```

Destructive real API drills use the separate local test database:

```text
postgresql+asyncpg://workstream:<password>@localhost:<port>/workstream_test
```

One project-guide compilation proposes sufficiency findings and separate
pre-submission and post-submission policies through the OpenAI Agents SDK adapter.
Use the locked installation and environment-loading commands in
[Native Unified Guide Inference](#native-unified-guide-inference).

New compilation results also include `classification_rationale` for every atomic
requirement and one typed `check_specification` for each supported or missing
PRE/POST check. PRE is reserved for static and other checks that can reliably
finish within 60 seconds before Submission creation; it may still use durable
execution and polling. Longer or model-based work belongs to background POST.
The compiler infers checks from required outcomes rather than requiring guide
authors to label automation or stages. A missing registered implementation stays
an engineering gap in a warning-ready draft and blocks activation; only a real
guide blocker prevents the draft.

The SDK adapter first produces a private structured candidate, then uses a fresh model context
to check it against the original documents and return the corrected proposal.
Both phases expose the same strict JSON Schema. The private draft must satisfy
JSON syntax and structural limits; canonical content constraints are checked
diagnostically so review can correct them. Diagnostics contain bounded field
paths and a fixed code, never rejected values or exception messages. Only the
reviewed output passes through canonical Pydantic and owner validation for
acceptance. The draft is never persisted, projected or accepted.
Both phases share one attempt, workspace, client, overall timeout and aggregate
model-turn/hosted-tool budgets. The draft can use at most half the configured turn
allowance; review receives the unused remainder. The serialized review input
(original credential-free context plus candidate) must fit `maximum_manifest_bytes`;
an oversized candidate is terminal invalid output. The review must reopen every
cited original, and every assigned original for a ready proposal; draft-phase
opens cannot satisfy review access.
A review failure, cancellation, invalid result or exhausted budget does not publish
the unchecked draft. This is a bounded phase of the same attempt, not a retry of
an uncertain or terminal invocation. PM review and approval remain separate.

The specification is validated as data: execution mode and duration, material
inputs, ordered checks, pass conditions, coded findings, positive and negative
cases, runtime dependencies and infrastructure failures must agree. Current
images are offline and do not implicitly receive task/guide prose or model access.
Older retained results remain readable with the new fields absent; new results
cannot use that historical omission. Invalid new output ends terminally and is
diagnosed without logging guide or model content.

The Celery worker captures runtime, model provider, model, API, instructions,
timeout, document limits and tool budgets on the attempt before execution. Credentials stay in
the Celery worker environment. `WORKSTREAM_PROJECT_AGENT_INSTRUCTIONS` and
`WORKSTREAM_PROJECT_AGENT_INSTRUCTION_VERSION` configure trusted instructions;
omitting the text selects the repository's canonical compilation instructions.
The current adapter uses OpenAI Responses with a private Code Interpreter
workspace. `WORKSTREAM_PROJECT_AGENT_MODEL=gpt-5.6-terra` selects the model
independently of the runtime and instructions. Changing that setting requires
verifying the chosen model supports the configured tools and structured output.
`WORKSTREAM_PROJECT_AGENT_REQUEST_TIMEOUT_SECONDS` defaults to 300 seconds per
provider request. `WORKSTREAM_PROJECT_AGENT_RUN_TIMEOUT_SECONDS` defaults to 1,800
seconds for the whole run, including retry waits. The Agents SDK retries a model
request at most twice, with exponential backoff and jitter capped at 30 seconds.
Only proven pre-transmission failures, explicit temporary rate limits, or
provider-confirmed safe replay are eligible. Billing, authentication, invalid
output, denied document access, and unknown dispatched outcomes do not retry.
A process-local circuit opens after three exhausted transient model requests,
then admits one recovery probe after 60 seconds. Cleanup remains available.
The corresponding retry and circuit settings are listed in `backend/.env.example`.
The runtime adapter is selected through the shared typed adapter factory.

The local Celery command above includes Beat; start it before creating guide sources.

The Beat scheduler must run alongside the Celery execution processes so
artifact pending-work, verified guide-continuation and post-policy approval scans can recover
publication failures automatically.
