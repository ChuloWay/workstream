# Local Agent Loop Stack

This runbook extends the [local pilot stack](local-pilot.md) so that one
persistent Compose project can accept agent work through the existing public
contributor flow. It adds the external checker service, a networkless proof
checker image and the operator steps that register the checker, provision
service identities, configure a no-human-review project and activate the
acceptance lifecycle.

It uses only existing public APIs and owner operations. It does not create a
guide, approve policies, bypass the checker or write lifecycle facts directly.
Guide compilation, which selects the registered checker into the locked
pre-submission and post-submission policies, is a separate decision and is a
placeholder step below.

## What the overlay adds

`docker-compose.agent-loop.yml` is an overlay for `docker-compose.yml`:

| Service | Profile | Purpose |
|---|---|---|
| `checker-volumes-init` | `backend` | One-shot root step that makes the material and socket volume roots private (`0700`) and owned by `LOCAL_UID:LOCAL_GID` |
| `checker-registry` | `agent-loop` | Loopback-only OCI registry, so the daemon records a platform-manifest digest |
| `checker` | `agent-loop` | The existing Rust checker service (`docker/checker/Dockerfile.release`) in `docker-dev` isolation with the `runc` runtime |

The overlay also gives the API, Celery worker and beat services two shared
named volumes:

- **Material root.** The volume `<project>-checker-material` is mounted at its
  own Docker daemon path, `/var/lib/docker/volumes/<project>-checker-material/_data`,
  in the API, Celery worker, beat and checker containers. The checker starts each
  checker image with `docker run --mount type=bind,src=<material path>`. The
  daemon resolves that source in the Docker VM (or on the Linux host), so the
  path must be identical everywhere. `WORKSTREAM_ARTIFACT_SCRATCH_ROOT` and
  `WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT` both name it, as the settings
  require. This assumes Docker's default `/var/lib/docker` data root; rootless
  Docker or a custom data root needs a different path.
- **Socket.** `WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET` is
  `/run/ws-checker/checker.sock` on a separate named volume. Do not move it to a
  host bind mount: Docker Desktop host-shared paths refuse `chmod` on Unix
  sockets, and the service sets its socket to `0600`. Socket paths must also
  stay within 107 bytes.

The checker runs as `LOCAL_UID:LOCAL_GID`, the same identity as the API and
Celery worker, because the socket is `0600` and the service requires each grant
directory to be owned by its sandbox UID. It has no network, a read-only root,
no capabilities and `no-new-privileges`. It mounts the Docker socket, which is
root-equivalent access to the daemon: use this profile only on a development
machine you control. Docker Desktop exposes the socket inside containers as
`root:root 0660`, so the default `WORKSTREAM_DOCKER_SOCKET_GID` is `0`. On a
Linux host, set it to the `docker` group ID (`getent group docker`).

Docker Desktop on Apple Silicon (including M4) can advertise OpenSSL CPU
features that crash PyCA's bundled OpenSSL with `SIGILL`. The backend
development image already sets `OPENSSL_armcap=0`, so the API, Celery worker and beat
use the generic implementation. The checker service (Rust and the Docker CLI)
and the proof checker (standard-library Python without TLS) do not load that
OpenSSL, so the overlay adds no further default.

## Configure the checkout

Follow [Configure one checkout](local-pilot.md#configure-one-checkout) first.
Then add these lines to the ignored `.env`:

```bash
COMPOSE_FILE=docker-compose.yml:docker-compose.agent-loop.yml
COMPOSE_PROFILES=backend,agent-loop
WORKSTREAM_CHECKER_REGISTRY_HOST_PORT=15000
WORKSTREAM_CHECKER_CONFIG_FILE=./.local-agent-loop/checker-service.json
# Linux only: WORKSTREAM_DOCKER_SOCKET_GID=<docker group id>
```

`COMPOSE_FILE` makes every `docker compose` command in this checkout include
the overlay. Port 5000 is often taken
by macOS AirPlay, so choose an unused registry port. `.local-agent-loop/` is
ignored by Git.

## Bring up the profile

Start the `backend` profile and the registry, but not the checker yet. The
checker service refuses to start without at least one cached image:

```bash
docker compose --profile backend up --build --wait
docker compose up --wait checker-registry
```

Build and publish the proof checker, then write the checker-service
configuration and the two registry bodies. Run this on the Docker host from the
repository root:

```bash
set -a; . ./.env; set +a
python3 external_checkers/harnessy_proof/publish_local.py \
  --registry "localhost:$WORKSTREAM_CHECKER_REGISTRY_HOST_PORT" \
  --compose-project "$COMPOSE_PROJECT_NAME" \
  --sandbox-uid "$LOCAL_UID" --sandbox-gid "$LOCAL_GID" \
  --out-dir .local-agent-loop
docker compose up --build --wait checker
docker compose ps
```

The script pushes with `--provenance=false --sbom=false`, so the registry holds
one platform manifest instead of an index. It pulls that exact digest so the
daemon's `RepoDigests` contain it. `ps` must show `checker` healthy. If the
checker restarts, `docker compose logs checker` prints one bounded reason such
as `configured runtime unavailable` or `material root is not private`.

If the Docker credential helper hangs during `pull` or `push`, run the command
with an empty client configuration, for example
`DOCKER_CONFIG="$(mktemp -d)" docker compose ...`.

Rebuilding the proof checker changes its digest. Rerun `publish_local.py`,
recreate the checker with `docker compose up --wait --force-recreate checker`,
and register the new digest; existing registry entries are immutable.

## Create operators and service identities

Use the [local pilot identity steps](local-pilot.md#create-distinct-identities-and-grant-authority)
for `API_URL`, `curl_with_token`, `new_key` and the one-time Access
Administrator bootstrap. This runbook uses these Flow subjects:

| Subject | Role |
|---|---|
| `local-access-admin` | Access Administrator (bootstrap) |
| `local-operator` | system `operator`: checker registry and lifecycle |
| `local-manager` | system `project_manager` |
| `local-finance` | system `finance_authority` |
| `agent-claude` | project `submitter` |

Build the CLI from this checkout; an older build may lack the `operations`
commands. `ws_as` signs a short-lived token for one subject and passes it only
through the CLI's environment. A personal `workstream-local --as SUBJECT`
wrapper that does the same is equivalent:

```bash
(cd cli && go build -trimpath -o ../.local-agent-loop/workstream ./cmd/workstream)
ws_as() {
  local subject="$1"; shift
  WORKSTREAM_API_URL="$API_URL" \
  WORKSTREAM_TOKEN="$(docker compose exec -T backend python scripts/issue_local_flow_token.py --subject "$subject")" \
    ./.local-agent-loop/workstream "$@"
}
actor() { ws_as "$1" whoami -o json | jq -r .actor_profile_id; }
ADMIN_ID="$(actor local-access-admin)"
OPERATOR_ID="$(actor local-operator)"
MANAGER_ID="$(actor local-manager)"
FINANCE_ID="$(actor local-finance)"
AGENT_ID="$(actor agent-claude)"
ADMIN_TOKEN="$(docker compose exec -T backend python scripts/issue_local_flow_token.py --subject local-access-admin)"
docker compose exec -T backend python scripts/bootstrap_access_administrator.py \
  --actor-profile-id "$ADMIN_ID" --execute
grant_system_role() {
  curl_with_token "$ADMIN_TOKEN" --fail --silent --show-error -X POST \
    -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
    -d "{\"target_actor_profile_id\":\"$1\",\"role\":\"$2\",\"scope_type\":\"system\",\"reason\":\"Local agent loop\"}" \
    "$API_URL/api/v1/admin-role-grants" | jq
}
grant_system_role "$OPERATOR_ID" operator
grant_system_role "$MANAGER_ID" project_manager
grant_system_role "$FINANCE_ID" finance_authority
```

Provision the fixed service identities used by guide upload, PRE/POST checking,
routing to FinalAcceptance, assignment reconciliation and materialization. The
script calls `POST /api/v1/service-actors` with the administrator's own
authority and a stable `Idempotency-Key` per identity. A rerun reports
`provisioned` again (the exact replay), an identity created earlier under
another subject reports `existing`, and any other outcome reports
`failed:<status>:<code>` with a nonzero exit. It waits for `Retry-After` when the
administrative rate limit (30 mutations per minute by default) is reached:

```bash
docker compose exec -T backend python scripts/provision_local_service_actors.py \
  --admin-subject local-access-admin
```

## Register the proof checker

Registration needs a current system `operator` grant. Each body is an
`ExternalCheckerRegistrySpec` for one phase with the exact platform-manifest
digest. Keep each key with its file; replaying the same key and body returns the
same immutable entry:

```bash
PRE_KEY="$(uuidgen | tr 'A-Z' 'a-z')"
POST_KEY="$(uuidgen | tr 'A-Z' 'a-z')"
ws_as local-operator operations checker registry register \
  --input .local-agent-loop/registry-pre.json --idempotency-key "$PRE_KEY" -o json
ws_as local-operator operations checker registry register \
  --input .local-agent-loop/registry-post.json --idempotency-key "$POST_KEY" -o json
```

The equivalent API call is
`POST /api/v1/operations/external-checker-registry` with an `Idempotency-Key`
header and the same body.

Registration publishes an immutable definition. It does not select, enable or
run the checker for any project.

### What the proof checker checks

`external_checkers/harnessy_proof/checker.py` reads `proof.json` at the root of
the submitted ZIP and returns `external_checker_result.v1`. Each failed rule is
one `error` finding on `proof.json`, and the verdict is `failed` exactly when an
error finding exists:

| Field | Rule |
|---|---|
| `schema` | equals `harnessy.work.proof.v1` |
| `commit_sha` | 40 hexadecimal characters |
| `pr_url`, `ci_run_url` | `https://github.com/...` without credentials or port |
| `ci_conclusion` | equals `success` |
| `merged` | the JSON value `true` |

**Trust caveat.** The checker has no network access. It checks only what
`proof.json` claims. It does not confirm that the pull request, commit or CI
run exist, that the CI run belongs to the commit, or that the pull request was
merged. A passing verdict means well-formed claims, not independently verified
work. Pair it with human review, or with a checker that has trusted access to
the evidence, when the claim itself must be trusted.

## Create the manager project and the agent submitter

```bash
PROJECT_KEY="$(uuidgen | tr 'A-Z' 'a-z')"
ws_as local-manager project create --name 'Agent loop' --slug agent-loop \
  --idempotency-key "$PROJECT_KEY" -o json
```

Record the returned `id` as `PROJECT_ID`. The agent's actor profile was
created by its first `whoami` (`AGENT_ID` above). Issue its project `submitter`
grant and confirm the agent sees only that role:

```bash
jq -n --arg agent "$AGENT_ID" '{
  target_actor_profile_id: $agent, role: "submitter",
  qualification: {
    skills_snapshot: {availability: "unavailable", reference_ids: [], unavailable_reason: "no_record"},
    reputation_snapshot: {availability: "unavailable", reference_ids: [], unavailable_reason: "no_record"},
    prior_project_work_refs: [], external_expertise_refs: []},
  reason: "Local agent submitter"}' > .local-agent-loop/agent-grant.json
ws_as local-manager project role-grant issue "$PROJECT_ID" \
  --input .local-agent-loop/agent-grant.json --idempotency-key "$(uuidgen | tr 'A-Z' 'a-z')" -o json
ws_as agent-claude project access "$PROJECT_ID" -o json
```

## Set review, revision and contribution policies

Review and revision policies belong to a draft guide. Declare the guide as in
the [CLI guide steps](../../cli/README.md#declare-a-guide-and-its-setup-inputs)
and record `GUIDE_ID`. Then attach the policies with the manager's token. The
first version uses `If-Match: "no-current-policy"`:

```bash
MANAGER_TOKEN="$(docker compose exec -T backend python scripts/issue_local_flow_token.py --subject local-manager)"
GUIDE_ROOT="$API_URL/api/v1/projects/$PROJECT_ID/guides/$GUIDE_ID"
curl_with_token "$MANAGER_TOKEN" --fail --silent --show-error -X PUT \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
  -H 'If-Match: "no-current-policy"' \
  -d '{"human_review_required":false,"review_preference_window_seconds":3600,"review_lease_duration_seconds":1800,"allowed_decisions":["accept","needs_revision","reject"]}' \
  "$GUIDE_ROOT/review-policy" | jq
curl_with_token "$MANAGER_TOKEN" --fail --silent --show-error -X PUT \
  -H "Content-Type: application/json" -H "Idempotency-Key: $(new_key)" \
  -H 'If-Match: "no-current-policy"' \
  -d '{"max_revision_rounds":2,"revision_deadline_hours":48,"allowed_resubmission_states":["needs_revision"]}' \
  "$GUIDE_ROOT/revision-policy" | jq
```

With `human_review_required:false`, passing required checks invoke the same
authorized FinalAcceptance operation that a human `accept` uses. No Review or
reviewer contribution is created.

Finance publishes an UNPAID ContributionPolicy for the project:

```bash
printf '{"name":"Agent loop contributions"}\n' > .local-agent-loop/policy-name.json
printf '%s\n' '{"rules":[{"contribution_type":"accepted_submission","compensation_mode":"unpaid","definitions":[]},{"contribution_type":"completed_review","compensation_mode":"unpaid","definitions":[]}]}' \
  > .local-agent-loop/policy-rules.json
ws_as local-finance project contribution-policy create "$PROJECT_ID" \
  --input .local-agent-loop/policy-name.json --idempotency-key "$(uuidgen | tr 'A-Z' 'a-z')" -o json
ws_as local-finance project contribution-policy update "$PROJECT_ID" POLICY_ID VERSION_ID \
  --input .local-agent-loop/policy-rules.json --idempotency-key "$(uuidgen | tr 'A-Z' 'a-z')" -o json
ws_as local-finance project contribution-policy publish "$PROJECT_ID" POLICY_ID VERSION_ID \
  --idempotency-key "$(uuidgen | tr 'A-Z' 'a-z')" -o json
```

## Placeholder: compile, approve and activate the guide rules

> **Not covered here.** Selecting `harnessy.work_proof` into the locked
> pre-submission and post-submission policies is guide compilation, followed by
> the manager's separate PRE and POST approvals and guide activation. How rule
> setup works for this stack is being decided separately. Until it is, no task
> can be created for the project, and the contributor flow below cannot run.
> Provider-backed compilation needs `OPENAI_API_KEY`; see the
> [local pilot guide upload](local-pilot.md#declare-and-upload-a-real-guide-document)
> and the [CLI approval steps](../../cli/README.md#approve-an-exact-pre-submission-proposal).

## Move the acceptance lifecycle from shadow to live

Automatic FinalAcceptance commits new effects only while the joint review
lifecycle is `live`. A new database starts `disabled`. The script runs the owner
`JointLifecycleController` with the operator's own AUTH decision, one committed
transition per step (`disabled -> shadow -> live`). Rerunning at the target
phase prints `unchanged`:

```bash
docker compose exec -T backend python scripts/transition_review_lifecycle.py \
  --actor-profile-id "$OPERATOR_ID" --phase shadow
docker compose exec -T backend python scripts/transition_review_lifecycle.py \
  --actor-profile-id "$OPERATOR_ID" --phase live
```

Going live is refused while any retained FinalAcceptance lacks a valid routing
receipt. Leaving `live` uses the owner's draining path and is not part of this
script.

## Contributor flow for the agent

After guide activation and task release, the agent works as `agent-claude`:

```bash
ws_as agent-claude task ready "$PROJECT_ID" -o json
ws_as agent-claude task claim TASK_ID --idempotency-key "$CLAIM_KEY" -o json
ws_as agent-claude task start TASK_ID --idempotency-key "$START_KEY" -o json
ws_as agent-claude task requirements TASK_ID -o json
# work.zip contains proof.json at its root, plus whatever the guide requires
ws_as agent-claude task prepare TASK_ID --assignment ASSIGNMENT_ID \
  --file work.zip --idempotency-key "$PREPARE_KEY" --summary 'Completed work'
ws_as agent-claude task submit TASK_ID --assignment ASSIGNMENT_ID \
  --admission READY_ADMISSION_ID --summary 'Completed work'
ws_as agent-claude submission findings SUBMISSION_ID -o json
ws_as agent-claude contributions --project "$PROJECT_ID" -o json
```

Keep each key with its command. A pending preparation is repeated with the same
command, key and bytes. The [CLI contributor steps](../../cli/README.md#prepare-submit-and-inspect-contributor-work)
define replay and revision behavior.

## Stop or dispose

`docker compose down` keeps the project's volumes, including the material
volume, the registry and the generated digests. To delete everything this
project owns, confirm the project name first, as in
[Stop, retain or dispose](local-pilot.md#stop-retain-or-dispose), then:

```bash
docker compose down --volumes
docker image rm "$COMPOSE_PROJECT_NAME-checker:local" \
  "localhost:$WORKSTREAM_CHECKER_REGISTRY_HOST_PORT/harnessy-proof:local"
```

Checker containers that the service started carry the label
`workstream.external-checker=true`; the service removes them after each run and
on startup.
