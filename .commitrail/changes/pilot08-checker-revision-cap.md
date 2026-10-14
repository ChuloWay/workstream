# [PILOT-08] — Enforce the locked checker revision cap

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Reject checker-remediation submissions beyond the task’s locked revision allowance before PRE execution and at immutable Submission creation.

## Intent

An initial Submission is round 0. A policy allowing two revisions permits
rounds 1 and 2, for three submissions total. Retry and duplicate delivery do
not spend a round. Issue #495 records the settled product decision.

## Current behavior

TASK routes exact checker failure to needs_revision and admits a successor
without applying RevisionPolicy.max_revision_rounds. ART and TASK already
resolve the exact complete PROJECTS context. Submission.version is consecutive
and immutable; no second counter is needed.

## Bounded change

### Allowed

- TASK public submission-context rule and canonical submission creation.
- ART preparation and its public error mapping; TASK public error mapping.
- One migration enforcing the same cap on new Submission INSERT, its Alembic
  head registration and schema proof.
- Focused cap, replay, concurrency and SQL regressions using existing fixtures,
  including registration in the CI lane catalogue and its ownership assertion.
- Affected current lifecycle specification, roadmap and this record.

### Not allowed

- Guide setup integration (#552), export pagination (#497), dependencies (#565)
  or CLI implementation (#499).
- Deadline enforcement, policy rebase, change summaries, human queue/decisions,
  automatic rejection/cancellation, new counters, retained-data rewrites,
  compatibility paths, deployment or merging.

## Design and decisions

Use one TASK-owned pure capacity check over verified locked PROJECTS facts,
including exact revision policy identity. Apply it after current authority in
preparation and before creating new Submission facts. Exact committed replay
retains its original path. The SQL INSERT guard requires positive consecutive predecessor lineage, reads
only the immutable exact policy, and creates no explicit row locks or lifecycle
writers. Historical rows remain
unchanged. Submission version minus one is the consumed revision number.

## Acceptance criteria

- [x] max=2 permits initial0, revision1 and revision2; the next attempt receives
  revision_limit_reached without PRE/provider work or durable creation effects.
- [x] The final new-write boundary also enforces the cap; an old ready admission
  cannot bypass it. Exact committed replay remains successful.
- [x] Direct SQL cannot insert an over-cap Submission; rollback leaves prior
  immutable facts unchanged.
- [x] Existing stale-cause and concurrent replacement tests still pass.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture/reuse, security, QA/test delta, documentation.
- Human review focus: off-by-one semantics, locked policy custody, concealment,
  replay and SQL enforcement; later deadline/rebase scope remains explicit.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing owner reuse | TASK/ART/PROJECTS source inspection and focused tests | Reuses existing locked-context calls; authority and exact replay preserved | Deadline/rebase remain out of scope |
| Schema delta | PostgreSQL 16 canonical catalog comparison | Only new guard function, namespace identity and trigger differ; removing them reproduces the predecessor hash | Hosted repetition required |

Focused verification of the implementation recorded at `49ca2fbf8`:

- `pytest -q tests/architecture/test_module_boundaries.py tests/test_ci_lane_catalogue.py tests/test_submission_composition.py tests/tasks/submission_dispatch/test_revision_capacity.py`: 111 passed, no skips/deselections. Isolated PostgreSQL database cleanup completed.
- Earlier replacement, public-intake and Alembic checks: nine passed. The new cap journey also passed together with composition checks before the scalar-boundary repair.
- Removing only the application cap makes the new regression fail at the expected 409 refusal (actual 500). The probe wrapper incorrectly expected 422; this proves regression sensitivity, not the cause or contract of the fallback response.
- Ruff, markdown links, stale review/wording and Commitrail validation passed.

The isolated runner captured parent SHA `df05787d4` before the repair was
committed; the tested working-tree changes are recorded in `49ca2fbf8`. No
implementation edits followed that commit. Hosted full-suite evidence remains
a PR merge gate rather than a claim established by focused test counts.

## Review findings

CI also identified an invalid PROJECTS import in the TASK public API and an
unregistered regression module. The helper now accepts scalar locked-policy
facts projected by its existing callers, and the test has explicit CI lane
ownership. The dedicated boundary and lane checks pass.

Scope review identified mutable TASK-lock foreign keys on retained attempt
records as a prerequisite for later rebase. This PR does not change those keys.
Review also identified non-positive Submission versions as a SQL cap bypass;
the insert guard now validates positive consecutive lineage. The final-write
regression arranges a real ready admission without the new application cap,
retaining all existing authority, checker and artifact guards. Its SQL probe
uses the canonical writer with only the application cap removed, avoiding
unrelated uniqueness or stale-lineage rejections.

## Reconciliation

- Current-source reconciliation: main 82a46ff3 includes supported false activation;
  #550 is no longer a dependency. Checker remediation now shares revision limits
  by the explicit product decision, superseding the older human-only wording.
- Next usable boundary: deadline handling, guarded complete-context rebase and
  contributor change summary, then human-source integration with #554.
- Remaining risks: complete PILOT-08 is not delivered by cap enforcement alone.
