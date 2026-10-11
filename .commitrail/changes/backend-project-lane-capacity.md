# CI-PROJECT-CAPACITY — Execute the complete project test pool with bounded headroom

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: Four isolated project lanes execute the unchanged canonical test union exactly once, within the existing timeout and native database contract.

## Intent

Source PR520's current project C lane timed out with passing tests still pending.
Increase execution capacity rather than retrying until a runner passes or raising
the timeout. This is a separate CI-owner change; PR520's product candidate stays
frozen and no import functionality is implemented here.

## Current behavior

The implementation base is `35314a926503fae889e548ac5dae1c3c9e1a2ee7`, preserving
main's incoming checker-completion and CLI approval owners. The measured earlier
main is `a51cf06ccb5ab85f2c41528855f537d4362ec26b`. Before this change, the catalogue
in `backend/scripts/test_lane_catalogue.py` partitions project nodes across A/B/C.
`tests/test_projects.py` and `tests/test_guide_document_intake.py` use A/C after a
previous three-way allocation overloaded B. The workflow has nine lanes total,
an unchanged 1,200-second lane cap, and a complete aggregate evidence validator.
Ordinary lanes use private PostgreSQL 16 with exactly 2 GiB of tmpfs data and
`fsync`, `full_page_writes` and `synchronous_commit` enabled; the schema lane uses
disk. Each lane retains real MinIO and unique database/role/bucket cleanup.

Three independently downloaded hosted artifact sets show:

| Candidate and backend run | Project A seconds | Project B seconds | Project C seconds | C collected/completed |
|---|---:|---:|---:|---:|
| Source `8993b12d`, run `38049464143`, actual merge `139ed341` | 864.247 | 1091.090 | 1172.680 | 758/758 |
| Main `a51cf06c`, run `38056091618` | 1116.157 | 941.370 | 1144.803 | 754/754 |
| Source `7a3551e7`, run `38056709666`, actual merge `5dfb6501` | 1095.897 | 1079.869 | 1200.961, interrupted | 760/668 |

All three project pools contain 2,205 nodes. Main and the latest source have the
same normalized node multiset: UUID-backed parameter identities change with the
head and move six nodes between B/C. The interrupted bundle has no individual
phase durations, so its first unfinished node is not evidence of a deadlock.
Main/prior source's completed logs preserve only the slowest 25 durations; their
largest shared calls are approximately 10 seconds rather than one cap-sized call.

PG initialization (20/13/17 seconds), dependency installation (26/22/27 seconds)
and MinIO startup (5/5/5 seconds) occur before the lane runner cap. Prior source
and main's runner overhead above pytest is 27.27/25.18 seconds. Provisioning does
not explain the latest exhaustion. These measurements establish insufficient
capacity margin; they do not prove a specific current node's elapsed time.

## Bounded change

### Allowed

- `backend/scripts/test_lane_catalogue.py`: add project D to the existing project
  partition group; preserve the existing A/C exception for the two broad modules.
- `.github/workflows/backend.yml`: execute ten complete lanes, download their
  authenticated artifacts, combine exactly ten regular coverage files and
  require ten complete results in hosted timing/aggregate checks.
- Existing `run_test_lanes.py`, `merge_test_lane_evidence.py` and
  `validate_test_lane_evidence.py`: update affected exact inventory consumers.
  The runner and merger already derive their inventory from the shared catalogue;
  their existing implementations are retained. No timing extension is included.
- Existing CI lane/catalogue/merge/evidence tests and affected ownership
  expectations: protect the exact canonical union and newest-attempt custody.
- `scripts/test_lightweight_agent_gates.py`: preserve its strict independent
  workflow matrix assertion with the added project D entry.
- `docs/operations_backend_testing.md` and this record: reconcile the declared
  lane count and evidence protocol without changing product capability claims.

### Not allowed

- Product owner, API, AUTH, ART, TASK, SQL, migration or provider behavior changes.
- Test removal, skip/deselection, reduced authority/concurrency cases, relaxed
  cleanup/coverage custody, predicate suppression or weakened native settings.
- Timeout increase, weakened thresholds, synthetic database proof, caching away
  schema/owner guards, success from partial evidence, or blind failed-lane retry.
- Source PR520 edits, publication before scope/impact review, merge or issue closure.

## Design and decisions

1. Reuse the existing exact-node SHA partition algorithm with four candidates
   for the ordinary project group. Keep the broad Projects/intake A/C group;
   moving it wholesale to B would repeat a measured failure without evidence.
2. For the frozen latest source manifest, this mapping yields A645/B485/C622/D453
   instead of A787/B658/C760, retaining all 2,205 project nodes once. This is a
   deterministic assignment calculation, not a runtime prediction or PASS claim.
3. The canonical collector, manifest digest, raw parameter IDs, per-lane collected
   and completed identities, numeric attempt selection, native cleanup and full
   union verification remain authoritative. Any missing D bundle fails closed.
   Existing successful nine-lane evidence remains historical evidence only.
4. Derive runtime expectations from the reviewed catalogue where it already owns
   inventory; update intentional independent workflow cardinality assertions to
   ten. Do not replace exact counts with a permissive minimum or accept arbitrary
   artifacts. Review every consumer before implementation.
5. Keep the existing bounded slowest-25 phase diagnostic. The repair changes
   execution capacity without expanding evidence output; interruption still
   invalidates completion regardless of timing or successfully finished nodes.

## Acceptance criteria

- [ ] Independent canonical collection produces the same exact-node union before
  and after partition change at one reviewed head; every node belongs to one lane.
- [ ] Existing catalogue, runner, evidence and merge tests pass; missing/duplicate
  nodes, missing D, wrong head, wrong digests, interrupted execution or unclean
  metadata are rejected. Old partition mutation fails a meaningful affected check.
- [ ] Native storage/reset/authority behavior and all 1,200-second caps remain
  byte-identical. Ten required hosted lanes complete with zero skips/deselection;
  the independent aggregate validates their exact union and cleanup.
- [ ] Actual hosted per-lane timings are recorded, with honest headroom and runner
  variance limits. A further timeout triggers diagnosis rather than automatic retry.

## Risk and review routing

- Risk class: `L1` (complete evidence and execution allocation change).
- Required reviewers: QA/test delta and architecture/reuse for canonical inventory,
  workflow cardinality and artifact consumers; security only if timing output
  expands sensitive output or changes the existing private-file boundary.
- Human review focus: complete union, ten required lanes, unchanged native/cap
  contract, independent aggregate and truthful interruption diagnostics.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Prior/main/current capacity | Download nine lane bundles for runs 38049464143, 38056091618 and 38056709666; inspect summary, node and job-step timing | Measurements above; latest C timed out and cleaned DB/role/MinIO | Current individual phase times were not retained |
| Proposed allocation | Reapply the existing hash function to actual merge 5dfb6501's canonical manifest with four project candidates | 2,205 project nodes, A645/B485/C622/D453 | No implementation or hosted runtime result |
| Affected repair controls | `pytest -q tests/test_ci_lane_catalogue.py tests/test_ci_test_lanes.py tests/test_test_lane_evidence.py tests/test_merge_test_lane_evidence.py` | Exact 51ed6e543: 148 passed in 37.29 seconds; old nine-lane partition mutant failed the retained inventory assertion | Full hosted execution pending |
| Exact canonical union | Independent validator collection; old/new catalogue projection at the same 51ed6e543 head | 8,946 nodes unchanged; non-project assignment unchanged; project A646/B487/C622/D450; no app/DDL/CLI/MCP changes | Allocation is not a runtime prediction |
| Repository checks | Configured docstrings, full backend Ruff, Commitrail, links and stale contract guards | Passed; the initial process batch exposed a strict nine-entry Agent Gates matrix fixture, now updated to require D | Final affected process result in PR; full hosted gates pending |
| Full integration | Complete hosted ten-lane run and independent aggregate | Pending; no complete PASS claim | Actual frozen merge, all node/cleanup evidence and measured headroom required |

## Review findings

The latest source run is not complete PASS evidence. Eight successful lanes and
cleanup cannot replace the 92 unfinished project C nodes. No assertion failure
or specific deadlock is claimed from that interrupted artifact. The affected
controls now require project D, reject its missing/foreign bundles, duplicated
completion and interrupted execution, and refuse an invalid newest D attempt
even when an older D bundle passed. Existing shared-lane controls remain.

## Reconciliation

- Current-source reconciliation: cleanly integrated main 35314a926 before
  implementation; its production, test owners and delivered documentation are
  preserved. Source PR520 stays frozen at 7a3551e7.
- Next usable boundary: reviewed CI allocation repair, then exact frozen source
  integration and full hosted evidence; atomic import remains a separate chunk.
- Remaining risks: hosted runner variance and absent current per-node timing;
  four-way allocation still requires measured native and complete hosted proof.
