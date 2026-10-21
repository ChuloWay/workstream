# External checker test harness isolation

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Run every Rust workspace test with isolated harness scheduling while retaining explicit concurrency proofs.

## Intent

The external checker CI failure occurs while launching a freshly written test
executable. A diagnostic of the same unchanged code captured `ETXTBSY`. The
kernel-limit test forks the multithreaded Rust harness without exec, retaining
other threads' open file descriptors until the child exits. A controlled
probe reproduces the file-busy error while that child retains a write descriptor
and succeeds after it exits. Even an exploratory self-exec replacement failed
parallel stress in another fixture; it was discarded rather than shipped as a
complete fix.

## Bounded change

Allowed files are this record, `.github/workflows/backend.yml`, the existing
workflow contract assertion in `backend/tests/test_ci_lane_catalogue.py`, and the
focused checks explanation in `docs/operations_backend_testing.md`. The existing Rust
workspace command adds `-- --test-threads=1`, serializing independent test cases.
Tests requiring concurrency still create and join their own threads. All Rust
source, assertions, workspace members and test selection remain unchanged.

Do not change CLI branches, production handling, limits, timeouts, test selection,
workflow triggers, required status, or add retries. The independent project-page
timing failure does not authorize relaxing its one-second budget.

## Acceptance criteria

- All 52 workspace tests run, with zero ignored or filtered tests and ordinary
  failure propagation; the SDK, service and terminal benchmark checker remain
  selected.
- Real kernel exact-size and oversize rejection proof remains unchanged.
- The concurrency tests retain their explicit client/worker threads and checks.
- Existing workflow and gate contract tests pass. No fail-open fan-in or skip is
  added. Removing the serial-harness flag makes the existing workflow contract
  assertion fail on the original command.
- The original service suite passes repeated serial runs; this is bounded
  stability evidence, not a guarantee against every future environment failure.

## Risk and review routing

- Risk class: L1, required CI command scheduling.
- Reviewers: CI integrity, QA/test delta and focused documentation review.
- Human focus: complete test selection, explicit concurrency retained, and exit
  propagation; only incidental overlap between independent tests is removed.

## Evidence

- Unmodified Rust workspace: 52 passed, zero ignored/filtered, using the final
  serial command. Service suite: 20 consecutive serial runs passed (38 tests each).
- Default parallel harness previously reproduced executable-file-busy failure;
  a proposed self-exec repair also failed parallel stress and was discarded.
- Current-main PostgreSQL project-read scale test: passed without changing its
  one-second budget; previous offending continuation page took 0.578 seconds.
  Isolated database/role cleanup completed. This focused run is not a full hosted
  suite or MinIO proof.
- An optional local Clippy run with `-D warnings` rejects an unchanged large enum;
  it is not an existing required check and this repair does not suppress it.

## Reconciliation

Based on main `6573eb80b`. No product capability, route, ownership or next-boundary
change: the capability roadmap needs no edit. CLI integration stays with its
existing owner. The revised heads of the affected CLI PRs need fresh CI; old
failing runs are not relabeled as passing. The small additional Rust job duration
is the cost of isolating process-global tests, not a relaxed test deadline.
