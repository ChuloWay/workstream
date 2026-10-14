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
3. Narrow blanket `postgres_schema_contract` markers in
   `backend/tests/contributions/records/test_storage.py` and
   `backend/tests/tasks/post_submit_routing/test_storage.py`. Retain the marker
   on `test_reviewer_award_definition_substitution` (dynamic function replacement)
   and only the `remove_guard=True` parameter (trigger removal). Ordinary tests
   use the unchanged canonical schema check, transactional reset and teardown
   verification. Leaked schema changes still fail and trigger recovery.
4. Update affected workflow/selector/evidence tests, ownership registration and
   `docs/operations_backend_testing.md` together. Reconcile current main before
   final verification. No product roadmap impact: no capability or public API
   changes, and no claim that CI work completes a product gate.

| Change/event | Required runtime |
|---|---|
| Main push | Complete backend and supporting contracts |
| Backend, CI control, unknown or cross-cutting PR | Complete backend and supporting contracts |
| CLI-only PR | CLI real API/PostgreSQL/S3 contract and MinIO |
| MCP-only PR | MCP contract, included in Backend required fan-in |
| Mixed CLI/MCP/docs | Union of required client contracts |
| Positively classified ordinary Markdown documentation | No runtime; Agent Gates remains |

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
- Preserve all ten full-run lanes: exact fresh collection/completion once,
  no skips/deselections, cleanup, coverage artifacts, real API drill and
  no mixing of incompatible artifact attempts.
- Check removed selected-mode imports, flags, artifacts and registrations have
  no remaining consumers. Run affected runner/merger/validator/catalogue tests.
- Run both complete storage modules against PostgreSQL 16 and MinIO, including
  both DDL controls. Compare identical representative tests before/after with
  coverage enabled; report setup/call/teardown separately. Preserve exact nodes
  and all assertions. Coverage percentages remain diagnostic only.
- Run lint, markdown links, stale wording and Commitrail checks. Final hosted
  execution and focused internal reviews must pass before readiness.

## Risk and review routing

Required reviews: CI integrity and test delta/docs against a clean exact head.
Human focus: defensible component omissions, unchanged full-suite proof and
measured runtime benefit—not an unsupported five-minute claim.

## Evidence

Prior focused selector, evidence and workflow tests passed, but their passing
results did not prove complete dependency selection. The adversarial failure
above supersedes any earlier selected-backend readiness claim.

Hosted run `38593205795` at `0586a9e64` failed: project_lifecycle_a reached its
existing 1,200-second bound and schema_contracts was cancelled. No full-suite
success is claimed. The two-test local baseline passed in 344.62 seconds,
including 155.92 seconds of setup/teardown. The identical coverage-enabled
after-run timed out at 600 seconds under heavy shared-host load; both runs
confirmed database, role and MinIO cleanup. This is not evidence of a speedup.
Complete-module correctness and final hosted timing proof remain pending.

After simplification, 174 selector/catalogue/runner/evidence tests passed;
the expanded draft/ready component matrix passed 47 tests, and 27 workflow
integrity tests passed. These precede reconciliation with main `80be49391`;
final exact-head checks remain required. Ruff, links and Commitrail checks passed.

The marker plan received focused feasibility review: both actual schema
mutations retain rebuild isolation; ordinary tests retain verified reset.
Earlier draft-only and backend-selection plans are superseded, not additional
acceptance contracts.
