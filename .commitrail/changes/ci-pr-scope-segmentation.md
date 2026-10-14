# Select CI by verified change impact

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Draft and ready pull requests execute conservatively selected affected tests and integration contracts, with exact selected-execution proof; main and cross-cutting or uncertain changes retain complete-suite proof.

## Approved takeover scope

The human explicitly expanded this same PR to address ready-PR runtime, rather
than shipping draft-only optimization and creating another PR. The earlier
draft-only design and evidence below describe the starting implementation, not
the final acceptance contract. No performance or readiness claim is made for
the expanded implementation until measured.

### Implementation plan

1. Reuse the existing static import parser, test catalogue, isolated PostgreSQL
   runner and evidence validators. Build a conservative reverse dependency
   closure from both base and head, including package initializers, relative
   imports, test support and fixtures. Include directly changed test modules.
   Model, migration, AUTH, common infrastructure, dependency, fixture and CI
   control changes force complete execution. Unmapped files, dynamic dependency
   uncertainty, parsing failure and missing Git history also force full scope.
   Explicit non-backend surfaces select their own integration workflows; only
   positively classified ordinary documentation may omit runtime execution.
2. Select whole test modules within existing semantic lanes; do not change
   tests, pytest assertions or lane ownership to manufacture savings. Retain
   full collection inventory and distinguish intentionally unselected modules
   from deselected/skipped tests inside a selected invocation. Every selected
   node must complete exactly once, with existing isolation and cleanup proof.
3. Bind selection to exact base/head and selector inputs, record reasons and
   omitted modules, and independently recompute selection at evidence fan-in.
   Extend existing runner/merge/validator owners, not an alternative unchecked
   test runner. Keep default full-suite validation unchanged. Full runs on
   main remain mandatory. Full fallback remains possible on any PR.
4. Keep required fan-in fail-closed for scope classification, static checks,
   selected backend execution, CLI/external contracts and real API integration.
   Repair producer/consumer attempt binding for immutable MinIO artifacts so
   failed-job retries consume the exact successful producer artifact safely.
5. Prove selection with dependency/deletion/rename/fixture/unknown-input
   controls, mutation probes, independent collection reconciliation and
   representative full-suite comparison. Measure selection and runtime on
   concrete changes before enabling narrower merge proof. If discovery shows
   an impact boundary cannot be justified, use full fallback and say so.

### Expanded allowed files and acceptance

In addition to the original scope below: existing lane runner, evidence merger
and independent validator with their focused tests; a cohesive CI dependency
analysis module and its regression tests if the existing parser cannot own
selection; CLI reusable workflow and its workflow-integrity tests for artifact
retry custody; affected behavior-ownership registration and operations docs.
No application behavior, test deletion, timeout increase, coverage gate,
branch-protection change, external CI service or historical-result cache.

Acceptance requires safe selection on ready PRs, transitive consumer inclusion,
base/head graph union for removed edges, full fallback on uncertainty, exact
selected-node completion, mandatory main full runs, and measured examples of
omitted unrelated work. A narrow run must not be reported as full-suite proof.
Five minutes is a measurement target for bounded changes, not a promise for
cross-cutting changes. Both full and selected paths need executed evidence.

Risk remains L1. Required focused review covers CI integrity, dependency and
module boundaries, test delta and documentation. Plan review precedes the
expanded implementation. The human review focus is whether omitted tests have
a defensible dependency reason and whether fresh complete selected proof is
required before merge. Product roadmap impact remains absent: this is an
engineering workflow change, not a newly exposed Workstream capability.

### Selection and evidence contract

- Full fallback: AUTH/identity, artifact custody, compensation/contribution
  economics, ORM/models, schemas, migrations/DDL, common configuration/database
  or composition roots, fixtures/plugins/conftests, dependency/build inputs,
  CI/evidence controls, non-Python backend assets, deleted tests and unknown
  paths. Both graphs must resolve a uniquely owned ordinary source before
  production narrowing is eligible. Unmodelled production/external edges force
  full execution, not just the API drill.
- Materialize immutable base Python sources in a private temporary Git tree;
  parse base and tested merge-tree without importing either. Union reverse
  edges, resolving relative imports, both symbol/module forms of `from`
  imports, package initializers and local test-support imports. Ambiguity is
  uncertainty. Use the head catalogue/collection for executable test nodes.
- Production parsing/dynamic uncertainty forces full. Uncertain test/support
  modules are always retained with their reverse consumers for source changes;
  unresolved support ownership forces full. Include all tests under the
  changed owner's closed test-subtree map. Source-reading/path/registry/string
  controls are mandatory sentinels; unmapped non-import consumers force full.
  This mapping is not a replacement for backend module authorization policy.
- The planner freshly collects the full canonical pytest inventory before
  deriving selected whole modules, exact nodes and nonempty lanes. Hash-based
  lane partitioning is resolved from collected nodes, not module ownership.
  Zero-node and admin-runner-only selections fall back to full execution.
- Preserve full-manifest and default full-validator semantics. Selected mode
  has a distinct versioned receipt binding event base SHA, PR head SHA, tested
  merge-tree SHA, selector/input digests, selected/omitted modules and exact
  nodes, reasons and nonempty lanes. Shared validation primitives may be
  extracted; do not duplicate or relax the full validation owner.
- Selected lanes freshly collect and derive their exact subset. Selected
  fan-in independently collects the full inventory, recomputes selection and
  requires exact receipt agreement and exactly the expected nonempty bundles.
  Missing history or disagreement at fan-in fails; no late full fallback can
  excuse omitted execution. Every selected node completes exactly once, with
  no skipped/deselected nodes, shared namespaces or missing cleanup/coverage.
- Artifact identities bind mode, selection digest, tested tree, lane and
  producer attempt. Retrying selects newest evidence for each expected lane,
  never mixing selections or borrowing full/shadow evidence. MinIO consumers
  bind the immutable successful producer attempt, not their retry attempt.

| Change/event | Runtime selection | Required supporting checks |
|---|---|---|
| Main push | Full | Existing complete backend/CLI/external/API evidence |
| Unknown or cross-cutting PR | Full | Same complete evidence |
| Eligible backend source PR | Dependency/owner/sentinel closure | Static preflight, real API, mapped CLI/external consumers |
| Ordinary test-only PR | Changed modules and known reverse consumers | Preflight and exact selected evidence |
| CLI PR | CLI integration | Its real API/PostgreSQL/S3 proof and MinIO |
| External-checker PR | External runtime and mapped backend consumers | Explicit port integration, otherwise full fallback |
| MCP PR | MCP integration | MCP workflow result must join required fan-in before backend omission |
| Positively classified ordinary docs | No runtime | Existing required Agent Gates |

Draft and ready use the same impact rules but publish `draft-test` and required
`test`, respectively. Mixed changes union all required components. Preflight
remains required whenever backend code/tests participate. MinIO runs whenever
a selected integration consumer needs it. Full suite and real integration
proof remain mandatory on main and on every full-fallback PR.

### Executed-proof plan

Before narrowing ready checks, run a controlled selected-path probe inside
this PR's full run (the CI-control diff itself must select full). A temporary
Git fixture provides base/head with a static leaf, its failing affected test
and an unrelated test; exercise collection, runner, merge and independent
validation, compare against full execution, and prove the unrelated omission.
Add deletion/rename, removed import, initializer, fixture/plugin, dynamic
support, source-path/string and unknown-owner counterexamples. Use a real
PostgreSQL/MinIO selected integration sample to prove execution/cleanup custody,
including cancelled/missing/foreign/latest-failed evidence. Full-shadow results
on identical tested source distinguish selection correctness from runtime
speed. No selected-mode enablement based solely on unit/static assertions.

## Superseded draft-only baseline (historical context)

The sections below retain the prior author's bounded design and evidence.
Their checked criteria and ready-always-full statements are historical; the
approved takeover contract above is the sole current acceptance plan.

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

The required `test` status is reserved for ready PRs and main pushes. Draft
runs publish `draft-test`, so their partial success cannot satisfy branch
protection on the same commit after a ready transition. Both names come from
the event context, independent of planner success. Partial draft runs may pass
only when every selected component succeeds. Marking ready selects all lanes,
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
  produce a separate `draft-test` status, never the required `test` status.
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

Takeover review found a same-commit transition gap: draft feedback used the
required `test` context, whose completed result remains until dependency-gated
full verification creates its replacement. Reserve that name for full runs and
name draft feedback independently from trusted event state. Focused workflow
proof must reject removal of this separation; no branch-protection change,
test exclusion, or timeout increase is authorized by this repair.

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
