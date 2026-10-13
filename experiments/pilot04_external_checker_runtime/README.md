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
