# Backend CI Cache And Timing Diagnostics

- Initiative: `None`
- Durable disposition: `Complete`
- Intended merge outcome: Backend CI reuses an exact content-addressed MinIO
  source image and pip download cache while retaining every semantic test,
  fail-closed aggregate, and useful per-test duration evidence.

## Intent

Reduce repeated setup work in the required Backend workflow and retain enough
timing evidence to rebalance slow lanes from measurements. This change targets
only exact cache-identity inputs and diagnostics; it does not trade
test or evidence coverage for a faster green result.

## Current behavior

`.github/workflows/backend.yml` builds the source-pinned MinIO image once per
commit because its cache key includes `github.sha`. Backend jobs create fresh
Python environments and repeatedly download the same dependency inputs. The
semantic runner retains each lane log but reports only the 25 slowest pytest
phases, limiting later balancing evidence.

GitHub Backend run `37784941972` on PR #507 is the measurement source for this
slice. Its first MinIO job spent 145 seconds building after a cache miss. Lane
jobs also repeatedly spent about 25--28 seconds installing backend dependencies,
and queued for materially different periods. These measurements describe that
run only; this record makes no hosted performance claim before a candidate run.

## Bounded change

### Allowed

- `.github/workflows/backend.yml`: make the MinIO tar cache key depend on the
  runner OS/architecture, exact `docker/minio/**` content and workflow recipe,
  retaining exact per-run artifact identity, checksums and live provider
  verification.
- `.github/workflows/backend.yml`: restore a pip download cache for the exact
  backend dependency/workflow inputs and save it only after trusted-main
  validation; every job still performs a fresh install into its fresh hosted
  Python environment.
- `backend/scripts/run_test_lanes.py`: retain all pytest duration diagnostics in
  the existing redacted per-lane diagnostic logs without changing selection or
  timeout or treating those logs as fan-in evidence.
- `scripts/test_lightweight_agent_gates.py` and
  `backend/tests/test_ci_test_lanes.py`: focused positive and adversarial
  regressions for cache identity, fresh installs, runtime verification, artifact
  identity, and lane duration options.
- `docs/operations_backend_testing.md`: extend the canonical failure/rerun owner
  with the exact failed-job command, repeated-timeout diagnosis, fresh-current-
  tree rule and explicit limits on what the cache optimization can improve.
- `CONTRIBUTING.md`: link contributors to that canonical Backend rerun guidance
  without copying its operational contract.
- This standalone Commitrail record.

### Not allowed

- No product source, migrations, dependencies, test catalogue/partition, lane
  count, test selection, skips, coverage behavior, timeout, retry, runner
  permission, concurrency, service image or branch-protection change.
- No installed virtual-environment cache, broad restore prefix, commit-SHA MinIO
  cache key, unverified image reuse, affected-only tests or hidden failures.
- No lane/DAG redesign or performance/capacity claim before hosted measurement.

## Design and decisions

The reusable MinIO tar has an exact recipe/platform cache identity: a version,
runner OS and architecture, and a hash of `docker/minio/**` plus the workflow
that owns the build command. Rare workflow-only edits intentionally invalidate
the cache. A cold rebuild is not guaranteed byte-identical because the Docker
recipe consumes live apt repositories. Pull requests can restore only; a cache
miss is saved only after a trusted `main` push verifies the built image. The
cache has no restore prefix. Every workflow attempt still publishes a
SHA-and-attempt-named artifact after loading the tar, checking the image version,
starting it, probing health, and producing a checksum that every consumer verifies.

Pinned cache restore/save actions manage a pip download directory keyed by
Python/platform and the hashes of `backend/pyproject.toml` plus this workflow,
which includes the separate exact Ruff pin. Pull requests restore only; the
validated preflight on a trusted `main` push may save a miss. No installed
environment is cached. Existing `pip install` commands remain mandatory in
preflight, every lane and aggregation.

The lane runner changes `--durations=25` to `--durations=0`; pytest retains all
nontrivial setup/call/teardown timings in the existing diagnostic log. A lane
terminated by the unchanged deadline may not emit the final duration summary,
so completion evidence and interruption metadata remain the authority.

The operator guidance treats rerun as evidence recovery, never a green-result
loop. Removing the observed 145-second rebuild when its exact context is
unchanged does not solve 17-minute queue waits or 20-minute lanes and does not
promise an eight-minute Backend completion time.

## Acceptance criteria

- [x] Unchanged MinIO Docker context and Backend build workflow on the same
  runner OS/architecture use one exact cache key across commits; any context,
  workflow or platform change misses it.
- [x] MinIO cache restore has no broad prefix and cannot bypass image load,
  version execution, live health probe, per-run artifact name or checksum.
- [x] Pull requests never save MinIO or pip caches; only a verified trusted-main
  miss can populate a key that later pull requests restore.
- [x] Backend jobs cache pip downloads only and still run the existing fresh
  package installation commands from exact dependency inputs.
- [x] Ordinary and schema-admin lane commands request complete duration
  diagnostics while retaining the same exact node list, coverage, isolation,
  timeout, log and evidence contracts.
- [x] The nine lanes, full inventory, fan-in failure propagation, CLI dependency,
  aggregate validation, permissions and timeouts are unchanged.
- [x] Contributor guidance permits only failed-job reruns for a diagnosed
  same-head transient, explains aggregate revalidation of successful lane
  evidence, and requires diagnosis or fresh current-tree CI in the other cases.
- [x] Focused workflow/runner tests and mutation probes fail when cache identity,
  verification, fresh installation, duration output or required gates weaken.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `ci_integrity`, `qa`, `test_delta`
- Human review focus: Cross-commit cache trust and invalidation, fresh-install
  preservation, exact artifact/runtime verification, unchanged gate propagation,
  and whether duration output remains diagnostic rather than authoritative.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Measured bottlenecks | Inspect PR #507 Backend run `37784941972` job/step timestamps from `/tmp/ws-ci-507-jobs.json` | MinIO build took 145 seconds; repeated lane installs took about 25--28 seconds | Hosted queue and runner variability are uncontrolled |
| Cache custody | `python -m unittest -v scripts.test_lightweight_agent_gates`; checksum-verified actionlint 1.7.7; cache-key and invalid-context mutants | 19 workflow gates passed; candidate linted cleanly; both mutants were rejected | A real cross-commit hit requires a trusted-main seed and later hosted run |
| Lane diagnostics | Focused lane/evidence pytest batch plus duration-option mutant | 123 tests passed; reverting both commands to `--durations=25` failed the exact lane-command regression | A timed-out pytest process cannot print its final duration table |
| Full gate preservation | Workflow inventory/fan-in tests, exact diff inspection, Commitrail and Markdown gates | Existing lane count, selection, timeouts, permissions, fan-in and fresh installs remain; repository gates passed | Root owns hosted aggregate validation |

## Review findings

Initial workflow review found that `runner.temp` is not an allowed workflow-level
`env` context. Each existing identity step now exports `PIP_CACHE_DIR` through
`GITHUB_ENV` before installation; actionlint and an invalid-context mutant prove
that regression is rejected. Cache trust review also changed both caches to
restore-only on pull requests and save-on-miss only after trusted-main
verification.

## Reconciliation

- Current-source reconciliation: Based on `main` at
  `72b83ffc2f0fcb29efdc68f6babaee884ab7d4dd`; no product or migration owner is
  affected.
- Next usable boundary: Measure fresh and cross-commit hosted runs before any
  lane rebalance or further DAG change.
- Remaining risks: GitHub-hosted cache availability and queue time vary outside
  repository control; no improvement is claimed until measured.
