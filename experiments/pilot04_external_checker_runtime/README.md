# PILOT-04 external checker runtime probe

This fixture is only for the bounded local service proof. Its image is pushed
to an isolated local registry so Docker exposes an OCI repository digest. The
Rust service starts it by that exact platform-manifest digest in explicit
`docker-dev` mode, with no network, a read-only root, no capabilities, numeric
UID/GID 65532, bounded resources, and the callback-scoped ART workspace as its
only read-only material mount.

The checker returns the published `external_checker_result.v1` envelope. It
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

The companion `run_public_journey_probe.py` starts after a deliberately scripted
canonical guide compilation and its separately approved policies. Its guide
documents have fixture custody; the probe does not certify a live model call,
real source-document upload, or a general-purpose work judge. It registers this
directory's small deterministic PRE/POST checker image by its exact local
registry digest. The tested human identities are stored actors with locally
signed Flow-compatible tokens, not a hosted Flow Identity service.

From that explicit precondition, the companion must use a live loopback API,
the public manager guide activation and task lifecycle, contributor ZIP
preparation and canonical Submission POST, and a real Redis-backed prefork
Celery worker for artifact and outbox delivery. It checks actionable intake
failure from both Workstream defaults and the selected external PRE image,
verified immutable admission, a selected POST failure routed to
`needs_revision` and an exact public replacement, and passing POST routing under
both locked review modes. It checks exact false-mode FinalAcceptance and
submitter contribution/award evidence and replay. The phase-aware
`post-rejected.txt` rule lives only in this small checker fixture. The drill
must keep guide activation guards and database triggers
enabled. PostgreSQL, MinIO, Redis, the digest registry, Rust checker service,
and API/worker processes belong to one disposable local run; the isolated-test
runner owns database/role/MinIO namespace cleanup. This still does not certify
hosted gVisor, arbitrary checker quality, live human review, or deployment.
