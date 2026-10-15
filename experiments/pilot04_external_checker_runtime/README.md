# PILOT-04 external checker runtime probe

This fixture is only for the bounded local service proof. Its image is pushed
to an isolated local registry so Docker exposes an OCI repository digest. The
Rust service starts it by that exact platform-manifest digest in explicit
`docker-dev` mode, with no network, a read-only root, no capabilities, numeric
UID/GID 65532, bounded resources, and the callback-scoped ART workspace as its
only read-only material mount.

The checker returns the published `external_checker_result.v2` envelope. It
fails its own result if the expected verified file differs, effective
capabilities are nonzero, a Docker socket exists, the root is writable, or a
network connection succeeds. This small Linux fixture does not establish
hosted gVisor readiness, representative checker sizing, or product routing.

`run_selected_post_probe.py` composes the same service with the selected POST
owner against an already migrated isolated PostgreSQL database. It registers
the supplied platform-manifest digest, builds a real locked policy, creates an
immutable Submission through the existing TASK/ART path, mounts the verified
archive through the callback-scoped POST grant, and requires the normalized
result, isolation receipt, database finalization, and workspace cleanup. The
database must be disposable and independently cleaned by the caller; the probe
does not create or drop it.

`run_selected_end_to_end_probe.py` exercises PostgreSQL and MinIO through
selected PRE admission, immutable Submission/initial dispatch and production
request/completion handlers. It requires default-secret rejection and an actual
external PRE image rejection to preserve `in_progress` with no new Submission.
The latter uses `project-rejected.txt` as a fixture project rule, implemented
only inside the image. It also tests unavailable-service recovery through fresh
verified bytes and restarted completion delivery with exact replay. This hidden
owner drill does not provide public contributor upload/CLI, false-guide
activation or hosted gVisor deployment proof. Run it through the isolated-test
runner so owned database, role and MinIO cleanup are checked.

The companion `run_public_journey_probe.py` starts with public project/guide
creation, original synthetic Markdown bytes and two task examples. The public
upload dispatches real Celery setup. Its explicit `guide_worker` entry point
selects a recorded inference adapter through the existing typed runtime port;
production composition has no test switch. The adapter reads the actual scoped
ART document grant and checks exact bytes, normalized examples and correction
feedback. Stored source commitments and the runtime-observed canonical input
hash must agree. This proves integration, not model reasoning or hosted inference.

The manager configures review/revision policies through public conditional PUTs,
reads the proposal, separately approves PRE and POST, and activates the exact
publicly discovered context. Finance creates and publishes ContributionPolicy
through its public API. The human-review branch also exercises a manual setup
correction, successor discovery, predecessor preservation and request replay.
Infrastructure prerequisites are the immutable PRE/POST image registrations,
local Flow-compatible human/service identities and, for the compensated branch,
a project points unit and existing AUTH-governed adapter binding. They do not
inject guide, proposal, policy, Task, Submission, acceptance or award facts.
Locally signed tokens do not certify the hosted Flow Identity service.

The companion uses a live loopback API,
the public manager guide activation, project submitter grant, and task lifecycle, contributor ZIP
preparation and canonical Submission POST, and a real Redis-backed prefork
Celery worker and Beat scheduler for artifact and outbox delivery. The isolated
run sets the supported artifact scan interval to 10 seconds and requires a
retained scheduler audit before public intake; no manual scanner dispatch can
make a preparation ready. After a bounded timeout, the probe may publish the
exact pending verifier for private diagnosis and then unconditionally fails.
OUTBOX keeps its production 60-second Beat scan. The probe only observes its
ordinary first delivery and due retry through retained project-scoped worker
attempts and dispatch decisions; it publishes a duplicate message only after
acknowledgment to prove replay refusal.
It checks actionable intake
failure from both Workstream defaults and the selected external PRE image,
verified immutable admission, a selected POST failure routed to
`needs_revision` and an exact public replacement, and passing POST routing under
both locked review modes. It checks exact false-mode FinalAcceptance and
submitter contribution/award evidence and replay. The false-mode completion
first runs while the acceptance lifecycle is legitimately in shadow, requiring
one known safe OUTBOX retry with no governed effects. The probe stops the
owned prefork worker, moves the authorized lifecycle to live, then restarts a
fresh worker while Beat remains active; the same due event must succeed exactly
once through ordinary scheduled delivery. It then moves the authorized
lifecycle through draining, disabled, and shadow, submits a second public task,
and waits for its real selected POST result and first known non-live completion
retry. With the worker stopped, a Flow-linked access administrator publicly
revokes the fixed routing service link. The lifecycle returns to live before a
fresh worker starts; scheduled redelivery must close as an unknown invocation,
with no second-task routing, acceptance, contribution, or award and no change
to the first task's accepted evidence. This exercises revocation after checker
I/O, not a fabricated checker result or direct database mutation. The phase-aware
`post-rejected.txt` rule lives only in this small checker fixture. The drill
must keep guide activation guards and database triggers
enabled. PostgreSQL, MinIO, Redis, the digest registry, Rust checker service,
and API/worker/Beat processes belong to one disposable local run; the isolated-test
runner owns database/role/MinIO namespace cleanup. This still does not certify
hosted gVisor, arbitrary checker quality, live human review, or deployment.

Run from `backend/` with the backend environment installed, disposable PostgreSQL,
MinIO, Redis and a local digest registry. Build `workstream-checker-service` from
`external_checkers/Cargo.toml`; build/push this directory's Dockerfile and use its
registry-resolved digest, not a tag. Set the supported isolated-runner admin URL
and MinIO endpoint; the runner allocates and removes its own database, role,
bucket and prefix. Redis and registry must be owned by this drill, and the caller
must remove those containers after the run. Never use a deployment broker.

```sh
PYTHONPATH=.:tests:.. .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json /tmp/guide-journey-cleanup.json --timeout-seconds 1500 \
  --lane guide-journey -- \
  .venv/bin/python ../experiments/pilot04_external_checker_runtime/run_public_journey_probe.py \
  --image-reference 'localhost:<port>/<repository>@sha256:<manifest-digest>' \
  --service-binary /absolute/path/to/workstream-checker-service \
  --broker-url redis://127.0.0.1:<owned-port>/0 \
  --work-dir /tmp/guide-journey-private-run
```

Use a new metadata path and work directory for each run. Diagnostics stay in the
private work directory; the final JSON contains custody identifiers and outcomes,
not guide contents, tokens or provider credentials. Check `cleanup_complete`,
`database_cleanup_complete` and `minio_cleanup_complete` in the runner metadata.
The drill stops owned API, worker, Beat and Rust processes even on failure.
The removed approved-guide bootstrap mode is not an alternate entry path.
