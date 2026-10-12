# Backend CI Measured Lane Balance

- Initiative: `None`
- Durable disposition: `Complete`
- Intended merge outcome: The existing ten backend lanes have measured execution
  headroom while retaining the full test inventory and all isolation/evidence gates.

## Intent

The user approved reducing CI turnaround before continuing product integration.
Successful Backend run `38239242806` took 25m26s and completed 9,204 tests. Its
slowest recorded lane took 1,154.789s against the existing 1,200s deadline.
Main runs `38220929859` and `38224762176` interrupted different TASK lanes at
1,201s, leaving 10 and 35 nodes unfinished. Raising the deadline hides this
headroom problem. Installation and the short parallel workflows are not the
dominant measured cost.

The previous logs retained only the 25 slowest pytest phases. They could not
support a complete cost model. Before this change, each family assigned nodes using the first byte of
SHA-256 modulo its lane count; node counts do not represent execution cost.

## Bounded change

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

## Acceptance criteria

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

## Risk and review routing

Risk: `L1` (CI test selection and evidence). Required plan review and final
`ci_integrity`, `qa`, `test_delta`, `architecture`, `reuse_dedup`, `security`
and proportionate `documentation` review. Shared checks run once; focused
reviewers inspect exact frozen targets and unchanged evidence owners.

Human review focus: exact inventory/isolation preservation, simple deterministic
allocation, measurement provenance, and actual hosted headroom. No new human
decision or external authority is required for this bounded change.

## Evidence

The command regression rejects the original truncated duration flag before the
runner change. The diagnostic-only implementation passes 117 focused command,
catalogue and evidence tests. No allocation or runtime improvement is claimed
from those checks; hosted timing measurements remain required.

The first diagnostic run (`38271067999`, attempt 1) retained complete phase
tables for nine lanes but timed out TASK A after 445 of 470 nodes at
1,201 seconds. No assertion failure or cleanup failure was reported, and the
process did not reach its final duration report. This failed attempt is
headroom evidence, not a complete timing baseline or a performance success.
The controlled same-head retry completed TASK A in 883.546 seconds. The final
baseline uses nine successful attempt-1 bundles and TASK A from attempt 2.
That substantial run-to-run variation is retained; a successful retry is not
evidence that allocation alone caused or fixed the original timeout.

### Measured allocation

Hosted run `38271067999` at merge `55e4409b74fc4d873c57fa474d19f7214f52bc9f`
has the same tree (`ebd4fbc9039117e637aefbfc0c6f2916a3cbf3be`) as diagnostic
head `a95913ea2398d87f87ccae8040ba67323ad0bbca`. The existing independent
validator accepted the selected bundles: 9,204 collected/completed nodes, no
skips/deselections, successful isolation cleanup, and 27,612 distinct phase
records (one setup/call/teardown per node).

The retained manifest SHA-256 is
`68db5c27e92abfbd832921d0016daf7bd72929dfa6fce2e574382eb1397b84c3`.
The extracted per-node timing CSV SHA-256 is
`0f6b0a62bf754dd79d41eade4671e99e89f3f63f690e7db461582018a1bae8d6`.
Logs range from about 162 KB to 1.1 MB. They have no per-line timestamps, so
final-report overhead cannot be isolated from other non-phase work; step end
bounds report completion. The first timeout preceded report generation.

For each existing family, replay seeds 0 through 255 using the first byte of
`SHA256(f"{seed}:{nodeid}")` modulo its unchanged eligible lane count. Fit the
four PROJECT lanes and C/D-only intake jointly; fit SHARED and TASK separately.
Minimize the largest rounding-adjusted replay time, then squared replay times,
then numeric seeds. The selected constants are:

| Family | Seed |
| --- | ---: |
| SHARED A/B | 41 |
| PROJECT A/B/C/D | 114 |
| PROJECT intake C/D | 178 |
| TASK A/B/C | 181 |

Pytest prints phases to hundredths of a second. Replay each lane as observed
elapsed time plus moved-in rounded cost minus moved-out rounded cost. Unchanged
node rounding cancels. Add a conservative bound of 0.015 seconds per moved-node
incidence plus 0.001 seconds for elapsed rounding. Select only a candidate whose
largest upper bound is below the unchanged optimized-lane maximum. These are
**rounding-only baseline-replay intervals**, not runtime confidence intervals;
they do not bound hardware, ordering, residual overhead, or commit-seeded node
identity variation.

The optimized-lane baseline maximum is 1,109.281 seconds; the candidate's largest
rounding-only upper bound is 1,035.537 seconds. SHARED nominal replay is about
999 seconds, PROJECT at most 919 seconds, and TASK at most 948 seconds. The
unchanged schema lane took 1,090.644 seconds; its concurrent ordinary/admin
units are excluded from summed-phase elapsed prediction. This existing lane
limits the expected full-run speedup and exceeds the advisory 1,000-second
target. No new performance gate or guarantee is introduced. The final PR evidence
must report two full same-candidate hosted executions, including variability;
this baseline replay alone does not establish an actual speedup.

Replaying the retained manifest through the implemented assignment preserves
all 9,204 node/module/execution-kind identities exactly once, with 4,924
reassignments inside existing eligible families. The same comparison rejects
a deliberately dropped node, duplicate node and foreign-family assignment.
The focused command/catalogue/evidence suite and required final reviewer/hosted
results are recorded against the reviewable PR head.
