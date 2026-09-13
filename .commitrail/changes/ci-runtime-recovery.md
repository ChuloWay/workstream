# CI runtime recovery without reducing proof

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Reduce full Backend runtime through cheaper equivalent database resets and balanced allocation of the existing seven hosted lanes.

## Intent

Restore usable full-CI feedback while retaining every behavior test, real PostgreSQL
and MinIO, exact schema checks, authorization boundaries and coverage floors.
The user explicitly rejects solving slow CI by relaxing its checks or timeouts.

## Current behavior

Main `ed29a99e` runs seven lanes. Hosted run `34778489901` took 24m09s:
Project A consumed almost 20 minutes, task lanes about six minutes each, and
schema about three. Run `34775201545` retried Project A after the runner's
1200-second limit; its full workflow took about 40 minutes. Queueing was seconds.
The ordinary reset owner sends 52 separate trigger-disable and 52 enable
commands per reset. Fingerprinting and real isolation must remain in place.

## Bounded change

### Allowed

- `backend/tests/conftest.py`, `backend/tests/test_database_reset.py`: batch only
  equivalent trigger-management round trips within the existing reset transaction;
  add structural and PostgreSQL regression proof.
- `backend/scripts/{run_test_lanes,test_lane_catalogue,merge_test_lane_evidence,validate_test_lane_evidence}.py`
  and directly affected lane/evidence tests: allocate three project lanes, one
  task lane, two shared-foundation lanes and one schema lane. Preserve exact
  recursive inventory, unique node assignment, trusted manifest and evidence.
- `.github/workflows/backend.yml`: match those seven lanes, downloads and timing
  inventory. No timeout or required-status changes.
- `scripts/test_lightweight_agent_gates.py`: reconcile the exact seven-lane
  workflow assertion without reducing its completeness checks.
- `docs/operations_backend_testing.md`, `docs/roadmap_status.md` and this record:
  describe the same test guarantees and intended merged allocation accurately.

### Not allowed

No product, authorization, migration, dependency or backend-contract changes.
No skipped/deselected tests, coverage-floor reductions, test-body weakening,
schema-verification caching/removal, fsync changes, shared mutable databases,
new runner provider, additional permission system or automatic merge.
Do not add a second execution-unit/evidence framework or more hosted jobs.

## Design and decisions

Batch each phase of existing quoted `ALTER TABLE` statements using asyncpg's
multi-command execute. Keep the separate phases, failure hook, owned-target check,
full setup/teardown fingerprints, truncate/bootstrap and transaction unchanged.
Cancellation or a SQL failure must still roll back trigger and row changes.

Reassign the existing seven-job budget to measured dependency-family work:
three PROJECT partitions instead of two and one TASK lane instead of two.
PROJECT work was approximately 1774 runner-seconds versus TASK's 559 in the
latest hosted sample. This is a measured allocation hypothesis, not a promised
wall-time result. Deterministic within-family partitioning remains; all nodes
must execute exactly once. Retire removed lane names from active tooling/docs.

Do not increase the 1200-second execution deadline. Do not substitute local-machine
timing for hosted evidence. Broader test-layer changes and reducing repeated
coverage execution are outside this repair unless a concrete prerequisite appears.

## Acceptance criteria

- Exactly seven hosted lanes and the unchanged complete test inventory run.
- Each reset sends two trigger-management batches containing every existing
  statement; guard enablement, protected state and bootstrap state are preserved.
- Failure/cancellation/drift tests still reject and restore as before.
- Manifest and aggregate validators reject omitted, duplicate, crossed, stale,
  failed or unclean lane evidence under the new allocation.
- All full hosted tests and existing coverage gates pass on the candidate tree.
- Compare hosted critical-path/setup/test/aggregate timings to the cited runs;
  report remaining costs honestly rather than declare an unmeasured target met.

## Risk and review routing

- Risk class: L1
- Required reviewers: CI integrity, QA/test delta, architecture/security for
  database-reset semantics, documentation for changed operating instructions.
- Human review focus: equivalent isolation and full proof at lower runtime.

## Evidence

Plan review precedes implementation. Run focused lane/evidence tests and real
`tests/test_database_reset.py` through the existing isolated runner, including
failure/cancellation probes; then lint, documentation/record checks and full hosted
Backend CI. Hosted baseline evidence is inspected, not a performance guarantee.

## Reconciliation

Product-builder changes remain separately owned; do not modify product files.
Roadmap impact is engineering execution only, with no new product capability.
Next usable boundary is the same full backend proof with measured lower latency.
