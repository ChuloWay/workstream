# Reduce avoidable CI work without weakening proof

- Initiative: None
- Durable disposition: Planned
- Risk class: L1
- Intended merge outcome: conservative client/documentation component selection,
  frozen backend dependencies, correct retry-artifact custody and less redundant
  schema rebuilding. Backend changes retain complete execution.

## Intent

The human authorized completing the CI repair in PR #566, including ready PRs.
Do not ship complexity that does not reduce work. Five minutes remains a target,
not a delivered result or permission to omit uncertain tests.

Import-based backend selection implemented at `0586a9e64` failed CI-SEL-001:
source readers, registries and injected ports can consume changed code without
import edges. The `bb0b861e4` safety repair falls back to full execution on the
actual application. A runtime-footprint alternative also failed review because
shared fixtures can persist state consumed by later tests without execution in
those tests' contexts. Both designs are rejected. Their history remains in Git;
remove the selected-mode implementation rather than weaken its probe.

Final review also found that the reusable CLI contract resolved its Backend
Ruff and pytest tooling outside `backend/uv.lock`, so lock-only maintenance was
not fully proven by a hosted green run.

## Bounded change

1. Simplify `backend/scripts/select_ci_scope.py` and Backend workflow to the
   component matrix below. Remove `ci_test_impact.py`, `ci_selection_receipt.py`,
   `probe_ci_selection.py`, their exclusive tests and ownership registrations.
   Remove selected-mode additions from the existing lane runner, merger and
   validator; preserve their full-run contracts.
2. Retain MCP reusable-workflow required fan-in, CLI MinIO successful-producer
   attempt binding, frozen uv environments, and one source-wide preflight for
   Ruff/docstring checks. Keep strict Git path validation, no-renames diff,
   full fallback on unavailable history, and base-retarget event coverage.
3. Remove the blanket `postgres_schema_contract` marker from
   `backend/tests/tasks/post_submit_routing/test_storage.py`. Its ordinary tests
   retain canonical schema verification, transactional reset and teardown proof.
   Preserve current main's contribution storage tests unchanged: merged #573
   already removed their redundant rebuilds and explicitly rolls back its two
   mutation controls. Do not reintroduce those markers during reconciliation.
4. Update affected workflow/selector/evidence tests, ownership registration and
   `docs/operations_backend_testing.md` together. Reconcile current main before
   final verification. No product roadmap impact: no capability or public API
   changes, and no claim that CI work completes a product gate.

The reusable CLI contract keeps its independent Go build, while its Backend
Ruff checks, isolated runner and five pytest groups use the same pinned frozen
all-extras environment as the other affected Backend jobs.
The reusable MCP real-API job also checks and installs `backend/uv.lock` frozen;
its OpenAPI subprocess, isolated runner and both lifecycle suites execute in
that Backend environment. The adapter retains its own frozen environment and
independent wheel-install proof.

| Change/event | Required runtime |
|---|---|
| Main push | Complete backend and supporting contracts |
| Backend, CI control, unknown or cross-cutting PR | Complete backend and supporting contracts |
| CLI-only PR | CLI real API/PostgreSQL/S3 contract and MinIO |
| MCP-only PR | MCP contract, included in Backend required fan-in |
| Mixed CLI/MCP/docs | Union of required client contracts |
| Only `README.md`, `CHANGELOG.md`, `docs/**/*.md`, or `.commitrail/changes/**/*.md` | No runtime; Agent Gates remains |

Draft and ready PRs use the same component rules. Event-derived `draft-test`
cannot satisfy required `test`; marking ready starts the required check.
Selected components must succeed, omitted components must be skipped, and
scope failure, cancellation or unexpected results must fail the final check.

## Prohibited changes

No application, migration, dependency-version, authorization, fixture bypass,
timeout increase, coverage quota, branch-protection or merge-authority changes.
No test deletion except proof exclusively for the rejected selected-mode
implementation. No assertion weakening, skipped failures or partial execution
reported as complete proof. No new selector/evidence service or paid runner.

## Acceptance criteria

- Test the component matrix for draft and ready events, including mixed paths,
  invalid paths, renames, empty/unavailable diffs and null-base main pushes.
- Execute fan-in truth tables for success, failure, cancellation, skip, unknown
  and unexpected success. Preserve MCP result and MinIO retry custody.
- Preserve all thirteen full-run lanes from current main: exact fresh collection/completion once,
  no skips/deselections, cleanup, coverage artifacts, real API drill and
  no mixing of incompatible artifact attempts.
- Check removed selected-mode imports, flags, artifacts and registrations have
  no remaining consumers. Run affected runner/merger/validator/catalogue tests.
- Run the affected routing storage module against PostgreSQL 16 and MinIO.
  Preserve current main's contribution storage mutation controls unchanged.
  Compare fixture invocation paths: five routing tests replace ten complete
  Alembic rebuilds with five transactional resets and five schema verifications.
  Preserve exact nodes and all assertions. Report comparable coverage-enabled
  setup/call/teardown timings when available; structural savings alone do not
  establish a wall-time speedup. Coverage percentages remain diagnostic only.
- Run lint, markdown links, stale wording and Commitrail checks. Final hosted
  execution and focused internal reviews must pass before readiness.
- Verify the reusable CLI contract preserves its Go build and runs all Backend
  Ruff and pytest commands through pinned `uv` with `--frozen` lock custody.
- Verify MCP OpenAPI and both real-API suites use the frozen Backend environment,
  preserve their exact suite arguments, and propagate failure and timeout exits.

## Risk and review routing

Required reviews: CI integrity and test delta/docs against a clean exact head.
Human focus: defensible component omissions, unchanged full-suite proof and
measured runtime benefit—not an unsupported five-minute claim.

## Evidence

Prior focused selector, evidence and workflow tests passed, but their passing
results did not prove complete dependency selection. The adversarial failure
above supersedes any earlier selected-backend readiness claim.

The final reusable-CLI repair passed 74 focused workflow/selector tests, 149
lane catalogue/evidence tests and 160 behavior-ownership tests locally. Its
regression tests fail when `uv sync` loses `--frozen` or when any of the five
isolated pytest groups loses its exact arguments. Hosted Linux remains the
authoritative exact-lock proof.

Hosted run `38593205795` at `0586a9e64` failed: project_lifecycle_a reached its
existing 1,200-second bound and schema_contracts was cancelled. No full-suite
success is claimed. The two-test local baseline passed in 344.62 seconds,
including 155.92 seconds of setup/teardown. The identical coverage-enabled
after-run timed out at 600 seconds under heavy shared-host load; both runs
confirmed database, role and MinIO cleanup. This is not evidence of a speedup.
These measurements do not prove complete-module correctness or a speedup;
hosted Linux proof remains required for every reviewable candidate.

After simplification, 174 selector/catalogue/runner/evidence tests passed;
the expanded draft/ready component matrix passed 47 tests, and 27 workflow
integrity tests passed. These are historical pre-reconciliation results from
before main `25d5c068a`; exact-head checks supersede them for readiness. Ruff,
links and Commitrail checks passed.

Current-main reconciliation retains its expanded thirteen-lane capacity and
Linux-only frozen dependency graph. The component selector builds its matrix
from that canonical lane catalogue, so complete backend proof automatically
requires every current lane without duplicating the lane list in the workflow.
The PostgreSQL storage guard uses explicit failure branches for invalid mounts,
capacity or write settings so Bash version differences cannot turn a failed
predicate into a successful job.

The original marker plan retained rebuild isolation on two mutation cases.
Current main supersedes that portion with explicit transactional rollback and
verified reset; only routing storage marker removal remains new in this PR.
Earlier draft-only and backend-selection plans are superseded, not additional
acceptance contracts.

The final external review found that the reusable CLI contract still resolved
its Backend Ruff and five pytest groups independently of the lock. Those Backend
commands now use the same pinned frozen environment, while independent Go
module verification, tests and binary build remain unchanged.
The Ruff commands still execute from the repository root with the Backend uv
project selected explicitly, preserving the CLI tests' original format rules.
The MinIO producer-attempt guard now exits explicitly on malformed values so its
fail-closed behavior does not depend on Bash `errexit` handling of `[[ ... ]]`.

Reconciliation with main `ce60d0f02` preserves all merged revision migrations,
all thirteen lanes and contribution storage mutation controls. At `13fec951e`,
366 focused selector/catalogue/runner/evidence/ownership tests and 101 workflow
and Commitrail tests passed. Ruff and behavior-ownership validation passed.
Independent documentation review corrected the contribution reset description,
made the Markdown allowlist explicit, and distinguished the recorded eight-minute
timing threshold from the aspirational five-minute goal. No exact-head wall-time
speedup has been established. Fresh hosted full-suite proof is required after
these final documentation corrections; earlier green runs do not qualify it.

Final CI review identified a remaining floating Backend install in MCP's real-API
job. It now uses the same frozen Backend lock for OpenAPI and lifecycle parity.
An extracted-workflow regression checks both exact suite invocations and error
propagation. All 29 focused workflow tests passed; removing frozen mode from
either the Backend install or child pytest invocation makes the new regression
fail. Ruff, Markdown links and Commitrail checks passed. This repair requires
a fresh complete hosted run.
