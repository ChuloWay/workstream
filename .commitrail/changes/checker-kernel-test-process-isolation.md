# Backend test isolation and metadata check identity

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Isolate Rust harness scheduling and keep metadata edits from replacing required Backend proof.

## Intent

The external checker CI failure occurs while launching a freshly written test
executable. A diagnostic of the same unchanged code captured `ETXTBSY`. The
kernel-limit test forks the multithreaded Rust harness without exec, retaining
other threads' open file descriptors until the child exits. A controlled
probe reproduces the file-busy error while that child retains a write descriptor
and succeeds after it exits. Even an exploratory self-exec replacement failed
parallel stress in another fixture; it was discarded rather than shipped as a
complete fix.

A second failure was in the description-edit mirror: it published a failed
required `test` while the real proof was still queued. Metadata edits must not
replace, infer or manufacture that proof.

## Bounded change

Allowed files are this record, `.github/workflows/backend.yml`, the existing
workflow contracts in `backend/tests/test_ci_lane_catalogue.py` and
`scripts/test_lightweight_agent_gates.py`, and the
focused checks explanation in `docs/operations_backend_testing.md`. The existing Rust
workspace command adds `-- --test-threads=1`, serializing independent test cases.
Tests requiring concurrency still create and join their own threads. All Rust
source, assertions, workspace members and test selection remain unchanged.

For same-repository title/description edits only, couple a distinct non-required
dynamic final-check identity with a skipped job. Its expression selects
`metadata-only` if evaluated. Remove the mirror/polling
step. Preserve `test`/`draft-test`, dependencies and failure validation for actual
proof events, including base retargets and fork edits. Preserve workflow triggers
and the separate metadata concurrency group.

Do not change CLI branches, production handling, limits, timeouts, test selection,
required proof or branch protection, or add retries. The independent project-page
timing failure does not authorize relaxing its one-second budget.

## Acceptance criteria

- All 52 workspace tests run, with zero ignored or filtered tests and ordinary
  failure propagation; the SDK, service and terminal benchmark checker remain
  selected.
- Real kernel exact-size and oversize rejection proof remains unchanged.
- The concurrency tests retain their explicit client/worker threads and checks.
- Existing workflow and gate contract tests pass. No fail-open fan-in or proof
  omission is added. Removing the serial-harness flag makes the existing workflow contract
  assertion fail on the original command.
- The original service suite passes repeated serial runs; this is bounded
  stability evidence, not a guarantee against every future environment failure.
- Metadata-only runs never publish required `test` or `draft-test`. Event cases
  cover metadata, base retargets, forks, source/state changes and pushes. Mutating
  the distinct name or skip condition must fail the focused contract. Hosted
  verification must confirm the distinct skipped check.
- Actual proof aggregation continues to reject failed, cancelled, skipped or
  missing required components; no metadata success stands in for test execution.

## Risk and review routing

- Risk class: L1, required CI command scheduling and check identity.
- Reviewers: CI integrity, QA/test delta and focused documentation review.
- Human focus: complete test selection, explicit concurrency retained, and exit
  propagation; only incidental overlap between independent tests is removed.
  Metadata-only success cannot satisfy the required proof check.

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

- Workflow contracts cover the metadata/proof event matrix and retain the
  failed/cancelled/skipped prerequisite checks. Mutations replacing the distinct
  metadata name branch with `test` and removing the metadata skip guard each
  fail the intended regression assertion.
- Hosted metadata run `39617491644` completed skipped and emitted neither `test`
  nor `draft-test`. GitHub displayed the unevaluated name expression for its
  skipped final job. This is observed rendering, not a promised display format;
  the safety requirement is a distinct non-required identity in either case.

## Reconciliation

Based on main `6573eb80b`. No product capability, route, ownership or next-boundary
change: the capability roadmap needs no edit. CLI integration stays with its
existing owner. The revised heads of the affected CLI PRs need fresh CI; old
failing runs are not relabeled as passing. The small additional Rust job duration
is the cost of isolating process-global tests, not a relaxed test deadline.
