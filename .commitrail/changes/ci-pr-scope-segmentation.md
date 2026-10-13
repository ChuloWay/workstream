# Scope draft CI without weakening merge proof

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Draft pull requests run only affected Backend CI components while every ready pull request and main push retain the complete blocking Backend suite.

## Intent

Reduce avoidable pull-request runtime and parallel service-image pulls without
deleting tests or weakening the proof required before merge. Contributors need
fast, relevant feedback while work is draft; maintainers still need the exact
complete Backend suite on every mergeable candidate.

## Current behavior

`.github/workflows/backend.yml` starts MinIO, ten PostgreSQL/Redis semantic-lane
jobs, authorization preflight, the external checker runtime, the CLI contract
and the aggregate API drill for every pull-request event, including MCP-only,
documentation-only and draft work. Each semantic lane also repeats full Ruff
and docstring checks even though those checks are source-wide and identical.

Recent PR #518 failed before tests when parallel service startup hit an
anonymous registry rate limit. Current main already uses the official Docker
Hub image source instead of the exhausted ECR mirror; this change addresses the
remaining avoidable fan-out and repeated setup rather than adding another image
source.

## Bounded change

### Allowed

- `.github/workflows/backend.yml`: add a fail-closed scope planner; run selected
  components for draft PRs; preserve the complete suite for ready PRs and main;
  move source-wide Ruff/docstring checks to the existing preflight job once.
- `backend/scripts/select_ci_scope.py` and focused tests: deterministically map
  an exact base-to-head changed-file set to conservative draft CI components.
- `scripts/test_lightweight_agent_gates.py`: prove trigger, status, empty-scope,
  partial-scope and full-suite fan-in behavior.
- `docs/operations_backend_testing.md`: document draft feedback versus required
  ready/main proof and rerun behavior.
- This standalone change record.

### Not allowed

- No test deletion, skip, deselection, timeout increase, coverage or assertion
  weakening.
- No product, backend runtime, dependency, migration or authorization change.
- No path-based exemption for ready pull requests or main pushes.
- No passing required status when an expected selected component failed,
  cancelled or was skipped.
- No change to branch protection, merge authority or automatic merge.

## Design and decisions

An unprivileged planner checks out the exact pull-request merge tree and uses
`git diff` against the event's exact base SHA. Pushes to main and non-draft pull
requests always select the full suite. Draft pull requests use conservative
scope rules: backend runtime or CI-runner changes select all semantic lanes;
test-only changes select every lane that owns nodes from the changed module;
CLI and external-checker changes select their existing independent contracts;
unrelated MCP/docs-only changes select no heavy Backend component.

The required `Backend / test` status remains present for every run. Partial
draft runs may pass only when every selected component succeeds. A draft cannot
merge. Marking it ready emits a new pull-request event that selects all lanes,
the complete evidence merge, coverage diagnostics and API drill. Every later
push to a ready PR also runs the full suite.

The aggregate full-suite job remains unchanged in proof strength but receives a
new internal name; the stable required `test` job becomes a lightweight
fail-closed fan-in. Full runs require the aggregate job to succeed. Source-wide
Ruff and docstring checks move from each lane to authorization preflight so they
execute once and remain required.

## Acceptance criteria

- [x] Main pushes and non-draft pull requests select all ten semantic lanes,
  authorization preflight, external checker, CLI contract and full aggregate.
- [x] Draft MCP/docs-only changes start none of the heavy Backend components and
  still produce the stable required status.
- [x] Draft CLI-only, external-checker-only, backend test-only and backend
  runtime changes select their conservative expected components.
- [x] Unknown backend test modules and CI-runner changes fail safe to every
  semantic lane.
- [x] A selected component failure, cancellation or unexpected skip cannot
  produce a passing required status; empty draft scope is explicitly allowed.
- [x] Full-suite evidence still requires all ten lane artifacts, exact coverage
  combination and the real API drill.
- [x] Ruff and docstring checks execute once per relevant run, remain required,
  and are absent from semantic lane jobs.

## Risk and review routing

- Risk class: L1
- Required reviewers: CI integrity and test delta; documentation for the changed operations guide.
- Human review focus: the draft/ready trust boundary, conservative path mapping,
  empty-selection behavior and preservation of the stable required check.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Scope selection is deterministic and fail-closed | `PYTHONPATH=backend ... pytest -q backend/tests/test_ci_scope_selection.py scripts/test_lightweight_agent_gates.py -k 'not postgres_storage_guard_rejects_wrong_mounts_and_write_settings'` | 42 passed, 1 deselected, including a real-Git rename-out-of-backend probe; the deselected pre-existing Bash 3 host probe passes on hosted Linux and fails unchanged on base locally. | Hosted event expressions still require GitHub execution proof. |
| Required fan-in rejects missing selected proof | Focused selector/workflow tests and embedded shell truth-table probes | Passed, including failure, cancellation, skip and unexpected-success cases. | Branch-protection configuration remains repository-admin state. |
| Complete merge proof is unchanged | `pytest` lane catalogue, runner and evidence contract modules | 137 passed. | Hosted ready-PR Backend execution remains required. |
| Repository process/docs remain valid | Markdown, stale-contract and reviewer-contract checks | Passed; 200 Agent Gates tests passed locally, with only the same 9 pre-existing macOS Bash 3 subtest failures seen on base. | Hosted Linux is authoritative for that host-specific probe. |
| No test was deleted or deselected | Base-to-head diff and lane-catalogue ownership checks | No existing test deletion, skip or deselection. | Future catalogue changes remain guarded by the same ownership checks. |

## Review findings

Initial CI/test review found that Git rename detection could hide the deleted
backend source path when a file moved outside `backend/`. The selector now uses
no-renames diff semantics so both old and new paths remain visible, with a
real-Git regression proving that the backend scope stays selected. The same
review found a misplaced CLI guard loop that executed one character and passed
without discriminating the intended failure. The loop is restored to its
full-suite owner, while the new fan-in probe now exercises success, failure,
cancellation, skip, unknown and unexpected-success outcomes for every selected
component.

## Reconciliation

- Current-source reconciliation: Based on current main `945dd2bf9`, including the merged Docker Hub service-image source and ten-lane full-suite contract.
- Next usable boundary: Measure draft feedback and full ready-PR runtime after hosted execution; rebalance lanes only in a separate measured change if still needed.
- Remaining risks: GitHub-hosted runner and registry availability remain external dependencies; no product roadmap capability changes.
