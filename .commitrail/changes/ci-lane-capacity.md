# ci-lane-capacity — Stop hosted Backend lanes crossing their deadline

- Initiative: None
- Durable disposition: `Planned`
- Intended merge outcome: Backend runs 16 semantic lanes with a 1500-second
  lane deadline, so hosted runner speed variation no longer fails complete,
  passing lanes on `main` or pull requests.

## Intent

Backend lanes are failing on time, not on tests. On 2026-10-16 the `main`
merges of #573 (`ce60d0f02`) and #578 (`62021e6d9`) both failed only because
`project_lifecycle_e` was interrupted at 1201 seconds. PR #575 then failed on
D, then B/C, then B/E, each time with every executed test passing. The human
chose more lanes first, then a longer deadline.

## Current behavior

`backend/scripts/test_lane_catalogue.py` defines 13 lanes: three shared, one
`schema_contracts`, five project and four task. `.github/workflows/backend.yml`
gives each lane `--timeout-seconds 1200`. Across seven hosted `main` runs
(2026-10-14 to 2026-10-16) the five project lanes had medians of 755–1077
seconds and maxima of 1026–1201 seconds; the same lane varied by up to 50%
between runs. `schema_contracts` reached 1202 seconds once and
`task_lifecycle_d` 1059 seconds.

## Bounded change

### Allowed

- Add `project_lifecycle_f`, `project_lifecycle_g` and `task_lifecycle_e`.
- Re-place five measured project module overrides onto the new lanes.
- Raise the lane deadline to 1500 seconds in the workflow and runner default.
- Update the fan-in lane count (13 to 16), CI catalogue tests and pinned
  expectations, and `docs/operations_backend_testing.md`.

### Not allowed

- Changing semantic family ownership or test membership.
- Skipping, deselecting or weakening any test, lane check or evidence check.
- Splitting `schema_contracts`, which owns whole-schema transitions.

## Design and decisions

Seven project lanes and five task lanes give 16 lanes. A Backend run then stays
within the organization's free-plan limit of 20 concurrent hosted jobs, together
with its preflight, external-checker, CLI and MCP jobs.

The override placement comes from a simulation over the 9202 nodes and recorded
call/setup/teardown durations of the green `main` run at `34501cd64`, using the
runner's own node hash. Keeping the five-lane overrides would leave D at 973
seconds; the chosen placement gives the seven project lanes 621–737 seconds and
the task lanes 515–639 seconds. `schema_contracts` stays one lane at about 990
seconds.

The 1500-second deadline absorbs the observed runner-speed variation on top of
the lighter lanes. The job timeout remains 45 minutes.

Rejected: redistributing within five project lanes. #566 and a later attempt on
#575 each moved the timeout to another lane, because the family's total test
time is close to its combined budget.

## Acceptance criteria

- [x] 16 lanes cover the recursive test inventory exactly once.
- [x] Fan-in requires 16 lane bundles and 16 coverage files.
- [x] Lane deadline is 1500 seconds.
- [ ] A hosted Backend run passes every lane within the deadline.

## Risk and review routing

- Risk class: `L1` (CI gate structure).
- Required reviewers: CI integrity and the CI owner of #566.
- Human review focus: lane count against hosted runner concurrency, and
  whether 1500 seconds is the right deadline.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Catalogue, runner and fan-in contracts | `pytest tests/test_ci_lane_catalogue.py tests/test_ci_test_lanes.py tests/test_ci_scope_selection.py tests/test_test_lane_evidence.py tests/test_merge_test_lane_evidence.py` | 250 passed | None |
| Lane balance | Simulation over `34501cd64` hosted durations | Project 621–737 s, task 515–639 s | Hosted speed varies run to run |

## Review findings

None yet.

## Reconciliation

- Current-source reconciliation: based on `main` at `34501cd64` (#566).
- Next usable boundary: rebase open Backend PRs, including #575, onto this.
- Remaining risks: a lane can still exceed 1500 seconds on an unusually slow
  runner; lane timings in the uploaded bundles show when to rebalance again.
