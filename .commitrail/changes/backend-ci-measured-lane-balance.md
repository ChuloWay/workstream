# Backend CI Complete Timing Diagnostics

- Initiative: `None`
- Durable disposition: `Complete`
- Intended merge outcome: Existing backend lanes retain complete phase timings
  for evidence-based optimization. Test allocation and execution gates remain
  unchanged; this change does not establish a CI speedup.

## Intent

The user approved reducing CI turnaround before continuing product integration.
Successful Backend run `38239242806` took 25m26s and completed 9,204 tests; its
slowest lane took 1,154.789s against the 1,200s deadline. Main runs
`38220929859` and `38224762176` timed out TASK lanes with unfinished tests.
The old 25-phase reports could not support a complete cost model.

Complete measurement is useful, but a fitted allocation must demonstrate a
repeatable benefit before changing thousands of test placements. Two hosted
executions of the measured seed candidate did not establish that benefit.
The final change retains diagnostics and restores the existing allocation.

## Bounded change

1. Request `--durations=0 --durations-min=0` in ordinary and schema-admin pytest
   commands, retaining all setup/call/teardown durations. Timing remains
   diagnostic; it cannot select tests or authorize incomplete execution.
2. Extend the existing command regression to require both flags exactly once
   and reject truncated output. Retain the deterministic allocation proof across
   node ordering and manifest head metadata.
3. Correct current lane counts and intake-family documentation. Document that
   complete phase output is bounded by the selected inventory and does not
   override the deadline. Record measurement limitations honestly.
4. Keep original exact-node hashing, eligible lane families, ten lanes and
   1,200-second cap. Remove the experimentally selected seeds and their
   seed-only assertion rather than preserve an unproven alternative path.
5. Run focused tests and shared checks, freeze the candidate, obtain affected
   internal reviews, and verify fresh complete hosted CI. The two-run performance
   experiment is complete; the narrowed change requires fresh correctness proof,
   not another performance claim or repeated fitting until a fast run appears.

## Scope

Allowed files:

- `backend/scripts/run_test_lanes.py`: complete diagnostic output only; restore
  existing assignment after the rejected experiment.
- `backend/scripts/test_lane_catalogue.py`: correct stale partition comments;
  remove experimental constants.
- `backend/tests/test_ci_test_lanes.py`,
  `backend/tests/test_ci_lane_catalogue.py`,
  `backend/tests/test_test_lane_evidence.py`: focused retained command,
  deterministic allocation and exact-inventory proof.
- This record, `docs/operations_backend_testing.md`, and
  `docs/roadmap_status.md`: accurate diagnostic and lane-count claims.

Prohibited: product code, migrations, dependencies, runner purchases, new lanes
or workflows, database-fixture changes, shared mutable databases, larger
timeouts, skipped/deselected tests, weakened coverage/evidence/cleanup gates,
branch protection or cache trust changes, runtime timing-based selection, or
removal of real PostgreSQL/MinIO/Redis proof. Broader static-check/fixture
optimization is a separate measured change, not silently added here.

## Acceptance criteria

- Both command paths emit complete durations with unchanged selected node IDs,
  plugins, coverage and isolation arguments. The command regression fails on
  the former truncated flags.
- Original deterministic allocation remains restricted to existing eligible
  families, preserving inventory and execution kinds exactly once.
- No tests or failure boundaries are removed. The discarded seed-only assertion
  describes an abandoned implementation, not a required product behavior.
- Focused command/catalogue/evidence tests, Ruff, diff checks, Markdown links,
  Commitrail and stale wording checks pass.
- Fresh hosted evidence identifies the exact tested tree, full collection and
  completion, no skips/deselections, successful cleanup and timing.
- Assess the capability ledger: only stale lane counts change; no product
  capability or measured speedup is claimed.

## Risk and review routing

Risk: `L1` (CI command/evidence boundary). Required focused `ci_integrity`, `qa`,
`test_delta`, `architecture`, `reuse_dedup`, `security` and documentation review.
Shared checks run once; reviewers inspect the exact frozen target and unchanged
owners. Human focus: complete-suite/isolation preservation, bounded diagnostic
output, unchanged allocation and honest measurement limits.

## Evidence

### Measurement and rejected allocation

Diagnostic run `38271067999` used merge
`55e4409b74fc4d873c57fa474d19f7214f52bc9f`, tree
`ebd4fbc9039117e637aefbfc0c6f2916a3cbf3be`, identical to diagnostic head
`a95913ea2398d87f87ccae8040ba67323ad0bbca`. Independent validation accepted
9,204 collected/completed nodes, zero skips/deselections, cleanup, and 27,612
phase records. Nine successful attempt-1 bundles plus TASK A from attempt 2
form the complete baseline. TASK A initially timed out after 445/470 nodes at
1,201s before final reporting; its controlled retry took 883.546s. The retry
is variance evidence, not an optimization result.

The retained manifest SHA-256 is
`68db5c27e92abfbd832921d0016daf7bd72929dfa6fce2e574382eb1397b84c3`;
per-node timing CSV SHA-256 is
`0f6b0a62bf754dd79d41eade4671e99e89f3f63f690e7db461582018a1bae8d6`.
Logs were about 162 KB–1.1 MB. Without per-line timestamps, final-report overhead
cannot be separated precisely from collection, provisioning, cleanup and other
residual time. Printed phase rounding also limits precision.

A bounded 256-seed search per eligible family selected SHARED=41, PROJECT=114,
PROJECT intake C/D=178 and TASK=181. Exact-manifest replay preserved all 9,204
node/module/execution-kind tuples once, moved 4,924 eligible nodes, and rejected
omitted, duplicate and foreign-family rows. Its predicted optimized-lane upper
bound was 1,035.537s, versus observed baseline maximum 1,109.281s. That bound
covered rounding only, not runner/order variance; unchanged schema took
1,090.644s.

Two complete hosted runs of candidate
`3619e59d0a0bd3212aa8261eeaa1375c8ddddff3` (run `38280323529`, attempts 1 and 2)
passed. Their slowest lanes took approximately 1,128.55s and 1,080.86s. Workflow
times were about 25m31s and 22m13s. These inconsistent differences do not establish
a repeatable speedup. Only 71 raw node IDs changed between baseline and candidate,
representing about one second of phase cost; runner/order variation dominates
that identity difference. The architecture/reuse evidence review recommended
removing the seed change if the repeat remained similarly inconclusive.

The final implementation therefore keeps complete timing diagnostics and the
original allocation. Hosted evidence and current reviewer receipts are recorded
in the PR trust bundle, without relabeling the experimental executions as proof
of the final narrowed commit. Future optimization must use these measurements
and retain the complete suite; this PR does not promise a faster runtime.
