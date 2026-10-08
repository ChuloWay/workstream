# Backend CI Cache And Timing Diagnostics

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: Backend CI reuses an exact content-addressed MinIO
  source image and pip download cache while retaining every semantic test,
  fail-closed aggregate, and useful per-test duration evidence.

## Intent

Reduce repeated setup work in the required Backend workflow and retain enough
timing evidence to rebalance slow lanes from measurements. This change targets
only deterministic downloads/build inputs and diagnostics; it does not trade
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
  runner OS/architecture and exact `docker/minio/**` content, retaining exact
  per-run artifact identity, checksums and live provider verification.
- `.github/workflows/backend.yml`: enable only setup-python's pip download cache
  for the exact backend dependency/workflow inputs; every job still performs a
  fresh install into its fresh hosted Python environment.
- `backend/scripts/run_test_lanes.py`: retain all pytest duration diagnostics in
  the already authenticated per-lane logs without changing selection or timeout.
- `scripts/test_lightweight_agent_gates.py` and
  `backend/tests/test_ci_test_lanes.py`: focused positive and adversarial
  regressions for cache identity, fresh installs, runtime verification, artifact
  identity, and lane duration options.
- `CONTRIBUTING.md`: concise operator guidance for failed-job reruns, same-head
  evidence reuse, repeated timeout diagnosis, and fresh CI after source/base
  changes, with explicit limits on what the cache optimization can improve.
- This standalone Commitrail record.

### Not allowed

- No product source, migrations, dependencies, test catalogue/partition, lane
  count, test selection, skips, coverage behavior, timeout, retry, runner
  permission, concurrency, service image or branch-protection change.
- No installed virtual-environment cache, broad restore prefix, commit-SHA MinIO
  cache key, unverified image reuse, affected-only tests or hidden failures.
- No lane/DAG redesign or performance/capacity claim before hosted measurement.

## Design and decisions

The reusable MinIO tar is a deterministic product of the pinned Docker context
and runner platform. Its cache key therefore uses only a version, runner OS and
architecture, and `hashFiles('docker/minio/**')`. The cache has no restore
prefix. Every workflow attempt still publishes a SHA-and-attempt-named artifact
after loading the tar, checking the image version, starting it, probing health,
and producing a checksum that every consumer verifies.

`actions/setup-python` owns a pip download cache keyed by Python/platform and
the hashes of `backend/pyproject.toml` plus this workflow, which includes the
separate exact Ruff pin. It does not cache an installed environment. Existing
`pip install` commands remain mandatory in preflight, every lane and aggregation.

The lane runner changes `--durations=25` to `--durations=0`; pytest retains all
nontrivial setup/call/teardown timings in the existing authenticated log. A lane
terminated by the unchanged deadline may not emit the final duration summary,
so completion evidence and interruption metadata remain the authority.

The operator guidance treats rerun as evidence recovery, never a green-result
loop. Removing the observed 145-second rebuild when its exact context is
unchanged does not solve 17-minute queue waits or 20-minute lanes and does not
promise an eight-minute Backend completion time.

## Acceptance criteria

- [ ] Unchanged MinIO Docker context on the same runner OS/architecture uses one
  exact cache key across commits; any context or platform change misses it.
- [ ] MinIO cache restore has no broad prefix and cannot bypass image load,
  version execution, live health probe, per-run artifact name or checksum.
- [ ] Backend jobs cache pip downloads only and still run the existing fresh
  package installation commands from exact dependency inputs.
- [ ] Ordinary and schema-admin lane commands request complete duration
  diagnostics while retaining the same exact node list, coverage, isolation,
  timeout, log and evidence contracts.
- [ ] The nine lanes, full inventory, fan-in failure propagation, CLI dependency,
  aggregate validation, permissions and timeouts are unchanged.
- [ ] Contributor guidance permits only failed-job reruns for a diagnosed
  same-head transient, explains aggregate revalidation of successful lane
  evidence, and requires diagnosis or fresh current-tree CI in the other cases.
- [ ] Focused workflow/runner tests and mutation probes fail when cache identity,
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
| Cache custody | Focused lightweight workflow tests plus cache-key/runtime-verification mutation probes | Planned | A real cross-commit hit requires hosted runs |
| Lane diagnostics | Focused lane-command tests plus duration-option mutation probe | Planned | A timed-out pytest process cannot print its final duration table |
| Full gate preservation | Workflow inventory/fan-in tests and exact diff inspection | Planned | Root owns hosted aggregate validation |

## Review findings

None yet.

## Reconciliation

- Current-source reconciliation: Based on `main` at
  `72b83ffc2f0fcb29efdc68f6babaee884ab7d4dd`; no product or migration owner is
  affected.
- Next usable boundary: Measure fresh and cross-commit hosted runs before any
  lane rebalance or further DAG change.
- Remaining risks: GitHub-hosted cache availability and queue time vary outside
  repository control; no improvement is claimed until measured.
