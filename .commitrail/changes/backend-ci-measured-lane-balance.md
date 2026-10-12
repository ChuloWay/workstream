# Backend CI Measured Lane Balance

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: The existing ten backend lanes have measured execution
  headroom while retaining the full test inventory and all isolation/evidence gates.

## Intent and evidence

The user approved reducing CI turnaround before continuing product integration.
Successful Backend run `38239242806` took 25m26s and completed 9,204 tests. Its
slowest recorded lane took 1,154.789s against the existing 1,200s deadline.
Main runs `38220929859` and `38224762176` interrupted different TASK lanes at
1,201s, leaving 10 and 35 nodes unfinished. Raising the deadline hides this
headroom problem. Installation and the short parallel workflows are not the
dominant measured cost.

Current logs retain only the 25 slowest pytest phases. They cannot support a
complete cost model. Each family currently assigns nodes using the first byte
of SHA-256 modulo its lane count; node counts do not represent execution cost.

## Bounded plan

1. Retain complete pytest phase durations (`--durations=0 --durations-min=0`)
   in the existing diagnostic logs for ordinary and schema-admin execution.
   Output is bounded by the selected nodes and at most setup/call/teardown rows.
   Measure emitted bytes and final-output overhead; keep timing diagnostic,
   never authority. Do not fit seeds from interrupted or incomplete baseline
   evidence. If final printing cannot finish inside the unchanged deadline,
   use the existing pytest plugin's phase reports to persist bounded timing
   incrementally rather than extending the deadline.
2. Run the unchanged allocation in hosted CI to obtain complete timings. Bind
   those observations to the exact commit, manifest and successful lane evidence.
3. Replay measured node costs against deterministic assignments within existing
   eligible lane families. Prefer a small explicit family-level hash seed over
   a large per-test weight table or runtime scheduling subsystem. New tests must
   still receive a deterministic assignment without manually supplying timing.
4. Apply only a measured candidate with improved predicted headroom. Replay the
   exact baseline manifest through both assignment algorithms: its node IDs and
   execution kinds remain identical and occur exactly once, and only eligible
   lane assignments may change. Independently collect the candidate's canonical
   inventory and verify its own complete execution; never compare commit-seeded
   raw parameter IDs as if they were invariant across commits.
5. Run focused allocation/command/evidence tests, discriminating omission and
   duplicate/invalid-family probes, internal review, and fresh complete hosted CI.
   Require two complete hosted executions of the same final candidate SHA to
   assess variability. Report actual improvement and variability; predictions
   are not runtime proof.

Collection-time UUID fixture IDs include the commit identity. The offline
before/after proof therefore replays one exact retained manifest through both
allocation functions; it does not claim identical raw parametrized IDs across
different commits. Fresh candidate CI must collect and verify its own complete
manifest. Fit results from one machine/run are uncertain; final measurement
must establish real headroom despite this identity and runner variance.

## Scope and preserved boundaries

Allowed files:

- `backend/scripts/run_test_lanes.py`: complete duration output and deterministic
  assignment using the existing catalogue; no new execution mechanism.
- `backend/scripts/test_lane_catalogue.py`: small explicit family allocation
  constants if supported by the measurement.
- `backend/tests/test_ci_test_lanes.py`, `backend/tests/test_ci_lane_catalogue.py`,
  `backend/tests/test_test_lane_evidence.py`: relevant retained command, exact
  inventory and allocation regression proofs.
- This change record and `docs/operations_backend_testing.md` for the actual
  diagnostic and allocation contract (including current PROJECT C/D intake
  placement, which its prose still incorrectly calls A/C).
- `docs/roadmap_status.md`: reconcile affected CI allocation/timing statements
  (including the stale nine-lane statement); no product capability changes.

Not allowed: product code, migrations, dependency/runner/provider purchases or
switches, new workflows or lanes, database fixture changes, shared mutable
databases, timeout increases, skipped/deselected tests, coverage changes,
weakened validators, branch protection changes, cache trust changes, dynamic
plugins, runtime timing-based selection, or removal of real PostgreSQL/MinIO/Redis
proof. Broad collection/static-check deduplication is a later measured slice.

## Acceptance and verification

- Every ordinary/admin command emits complete phase durations without changing
  selected node IDs, plugins, coverage or isolation arguments.
- Assignment is deterministic, restricted to each module's existing eligible
  lanes, and preserves the complete inventory and execution kinds exactly once.
- The ten lanes, 1,200s deadline, services, write settings, cleanup and independent
  aggregate collection remain unchanged.
- Hosted baseline and candidate evidence identify exact trees, full collection
  and completion, no skipped/deselected nodes, cleanup and timing. Aim for each
  lane below roughly 1,000s; this is an advisory performance target, not a new
  gate or a promised result. A missed target requires inspecting the cause rather
  than reporting an unmeasured speedup.
- Run focused pytest command/catalogue/evidence tests, Ruff, diff checks,
  markdown links, Commitrail and stale wording checks. Verify the changed command
  test rejects the previous truncated duration output, and the allocation proof
  rejects a dropped/duplicated node or assignment outside its family.
- Assess the capability ledger before readiness. This change adds no product
  capability; update only an affected measured CI statement, not product status.

Risk: `L1` (CI test selection and evidence). Required plan review and final
`ci_integrity`, `qa`, `test_delta`, `architecture`, `reuse_dedup`, `security`
and proportionate `documentation` review. Shared checks run once; focused
reviewers inspect exact frozen targets and unchanged evidence owners.

Human review focus: exact inventory/isolation preservation, simple deterministic
allocation, measurement provenance, and actual hosted headroom. No new human
decision or external authority is required for this bounded change.
