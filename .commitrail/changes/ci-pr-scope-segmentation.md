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

The Backend preflight, semantic lanes and aggregate API job also install from
the manifest with independent `pip` resolution. That means a hosted green run
does not prove the exact dependency graph selected by `backend/uv.lock`, which
is required for lock-only dependency maintenance such as PR #568.

## Bounded change

### Allowed

- `.github/workflows/backend.yml`: add a fail-closed scope planner; run selected
  components for draft PRs; preserve the complete suite for ready PRs and main;
  move source-wide Ruff/docstring checks to the existing preflight job once;
  install a pinned `uv` tool and run preflight, semantic lanes and aggregate API
  proof from a fresh frozen all-extras backend lock environment.
- `backend/scripts/select_ci_scope.py` and focused tests: deterministically map
  an exact base-to-head changed-file set to conservative draft CI components.
- `backend/scripts/behavior_ownership.py` and
  `.ci/behavior-ownership/partition.v1.json`: register the new selector as an
  eligible shared CI-control module in the repository-owned partition.
- `scripts/test_lightweight_agent_gates.py`: prove trigger, status, empty-scope,
  partial-scope and full-suite fan-in behavior.
- `docs/operations_backend_testing.md`: document draft feedback versus required
  ready/main proof and rerun behavior.
- This standalone change record.

### Not allowed

- No test deletion, skip, deselection, timeout increase, coverage or assertion
  weakening.
- No product, backend runtime, locked dependency version, migration or
  authorization change.
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

Each affected Backend job installs pinned `uv 0.10.7`, performs
`uv sync --frozen --all-extras`, and executes every subsequent Python, Ruff,
pytest, docstring and coverage command through `uv run --frozen`. The cache
contains only uv downloads and is keyed by the exact backend lock plus workflow;
the environment itself is recreated for every job. CLI packaging remains owned
by its reusable workflow and is outside this lock-custody amendment.

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
- [x] Backend preflight, every semantic lane and the full-suite/API fan-in
  install from `backend/uv.lock` with frozen all-extras resolution, and focused
  workflow tests reject unlocked installs or commands escaping that environment.

## Risk and review routing

- Risk class: L1
- Required reviewers: CI integrity and test delta; documentation for the changed operations guide.
- Human review focus: the draft/ready trust boundary, conservative path mapping,
  empty-selection behavior and preservation of the stable required check.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Scope selection is deterministic and fail-closed | `PYTHONPATH=backend ... pytest -q backend/tests/test_ci_scope_selection.py scripts/test_lightweight_agent_gates.py -k 'not postgres_storage_guard_rejects_wrong_mounts_and_write_settings'` | 48 passed, 1 deselected, including a real-Git rename-out-of-backend probe and non-draft diff-skip probes; the deselected pre-existing Bash 3 host probe passes on hosted Linux and fails unchanged on base locally. | Hosted event expressions still require GitHub execution proof. |
| Required fan-in rejects missing selected proof | Focused selector/workflow tests and embedded shell truth-table probes | Passed, including failure, cancellation, skip and unexpected-success cases. | Branch-protection configuration remains repository-admin state. |
| Complete merge proof is unchanged | `pytest` lane catalogue, runner and evidence contract modules | 149 passed. | Hosted ready-PR Backend execution remains required. |
| Repository process/docs remain valid | Markdown, stale-contract and reviewer-contract checks | Passed; 200 Agent Gates tests passed locally, with only the same 9 pre-existing macOS Bash 3 subtest failures seen on base. | Hosted Linux is authoritative for that host-specific probe. |
| Behavior-ownership partition remains exact | `python -m scripts.behavior_ownership validate` plus focused ownership tests | Selector is registered as one shared eligible target; validation passes. | Future eligible modules remain fail-closed through the same partition gate. |
| Hosted Backend commands use the selected lock | Workflow regression tests require pinned `uv`, `uv sync --frozen --all-extras`, lock-keyed download caches and `uv run --frozen` for every affected command | Local workflow, YAML, Ruff and focused regression checks pass after current-main reconciliation. | Hosted runner and package-index availability remain external. |
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

The first hosted ready-PR run then rejected the new selector as an unregistered
eligible module in the exact behavior-ownership partition. The selector is now
registered as one shared CI-control target, the partition digest is renewed,
and the partition validator plus its 160 focused tests pass.

Later review identified that the affected Backend jobs still resolved the
manifest independently of the selected lock, so hosted CI could not prove a
lock-only dependency repair. The workflow now recreates a frozen all-extras uv
environment in each affected job and binds all subsequent commands to it. The
download cache remains an optimization only and cannot replace or mutate that
fresh environment.

External review noted that `main()` previously calculated a Git diff before
checking the event type. On a push or newly created branch, the base ref can be
an all-zero SHA or unreachable, causing `git diff` to fail. The selector CLI
now skips Git diff calculation entirely for non-draft events (protected pushes
and ready PRs), allows omitting base/head refs on those events, and requires
base/head refs only for draft pull requests when changed paths are not supplied.

## Reconciliation

- Current-source reconciliation: Merged current main `2c1f7517c`, including the
  first-layer acceptance changes (PR #550) and CLI submission work (PR #570),
  and preserved its ten-lane catalogue, behavior-ownership partition and Backend
  proof contracts. No overlap with CI-segmentation or frozen-lock changes.
- Next usable boundary: Measure draft feedback and full ready-PR runtime after hosted execution; rebalance lanes only in a separate measured change if still needed.
- Remaining risks: GitHub-hosted runner and registry availability remain external dependencies; no product roadmap capability changes.
