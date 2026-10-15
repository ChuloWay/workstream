# [PILOT-READ-1] — Stored attempt outcomes and per-finding checker evidence

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Submissions, assignments and post-submit checker runs store the outcome, timestamp and per-finding facts that the PILOT read APIs project, through the existing TASK and CHECKERS owners and an extended external checker result contract, without changing who decides an outcome.

## Intent

The PILOT read-API issue asks every client to show a person their attempts,
what happened and what to do next. Main stores too little to answer honestly:
the reads would have to invent or re-derive outcomes. This change makes those
facts durable at the moment the existing owners decide them, so the later read
PRs are pure projections.

It is the first of three PRs for the read-API issue:

1. This change: stored facts, the extended checker result contract, B1 and B2.
2. Contributor reads A1–A6 and the B3 task-list filters.
3. Project Manager and Finance reads C1–C9 (including activation readiness) and D1.

The human decided the split, the contract extension, stored columns with
backfill over read-time derivation, and routing `coverage_incomplete` to a
manager-visible hold.

## Current behavior

- `ExternalCheckerFinding` (`backend/app/modules/checkers/api/external.py`)
  carries only `code`, `level` (`info|warning|error`), `message`, `path`. No
  `check_id`, `line` or `coverage_incomplete` exists anywhere in the repository.
  The Rust SDK `Finding` matches.
- `checker_results` stores one row per checker member. Individual findings exist
  only inside `checker_runs.result_json`; `warning_count` is always 0.
- `classify_result` routes any failed member to `needs_revision`, else
  `allow_review`; `allow_review` auto-accepts under a false ReviewPolicy even
  when a checker could not evaluate part of the work. `task_setup_blocked` is
  declared in contracts but never produced.
- `submissions.status` is only ever written as `submitted` and is used as an
  intake-liveness guard by TASK, ART and SQL custody. There is no `decided_at`,
  `status_reason` or `updated_at`; history synthesizes `rejected` from
  `task_revision_expirations` at read time.
- `task_assignments` has no `started_at` or `updated_at`; start exists only as
  an audit transition. `workstream_tasks.updated_at` is maintained by the ORM
  only, so raw SQL updates do not move it.
- `ContributorCheckerResult`/`ManagementCheckerResult` have no `check_id`,
  `path` or `line`; `ContributorSubmissionHistory.status` is an untyped string.

## Bounded change

### Allowed

- Replace `external_checker_result.v1` with `external_checker_result.v2` in the
  Python contract, Rust SDK, fixtures, pilot04 experiment checker and SQL
  custody. Findings gain a required `check_id`, an optional `line` (only with a
  `path`) and the `coverage_incomplete` level. The verdict rule is unchanged:
  `failed` exactly when an `error` finding exists.
- Add immutable `checker_result_findings` rows written in the existing
  finalization transaction and verified against the stored result by the
  existing deferred terminal-custody trigger.
- Route a completed result with no failed member and at least one
  `coverage_incomplete` finding to `task_setup_blocked`: no completion event, no
  TASK routing, no acceptance; the task stays `evaluation_pending`. Extend the
  existing Operator checker retry to accept that terminal hold as a source.
- Add `attempt_status`, `status_reason`, `decided_at` and DB-maintained
  `updated_at` to `submissions`, set by the existing deciding operations
  (dispatch, post-submit routing, shared false-policy acceptance, revision
  expiry), with SQL transition and evidence guards and a backfill.
- Add `started_at` (set by the existing start transition) and DB-maintained
  `updated_at` to `task_assignments`; make `workstream_tasks.updated_at`
  DB-maintained. Backfill from audit and existing timestamps.
- B1: checker-result reads list one entry per stored finding with `check_id`,
  `path`, `line` and the `coverage_incomplete` status; members without findings
  keep one entry. B2: typed submission `status`, stored `status_reason`,
  `decided_at` and `finding_counts` on both history projections.
- Update the Go CLI strict decoders (history, checker results and the 422
  pre-submit feedback findings) and their integration fixtures for B1/B2, the
  authorization OpenAPI field-set assertions, the CI lane catalogue for the new
  test modules, the journey probe's outcome assertions, and current docs.
- Batch the per-row evidence and per-run result queries the history reads
  already issue, removing their N+1 shape.

### Not allowed

- No change to who decides an outcome or to AUTH actions; no new endpoints.
- `submissions.status` keeps its intake-liveness meaning; no replay or guard
  that reads it changes behavior.
- No parallel v1/v2 result contract or compatibility alias.
- No human review decision writes (#554); no fabricated Review.
- No change to checker-authored message exposure: reads keep fixed worker
  messages.

## Design and decisions

- `attempt_status` (`evaluation_pending | review_pending | accepted |
  needs_revision | rejected`) is a separate column rather than new values of
  `submissions.status`, because seven Python checks and a SQL guard use
  `status = 'submitted'` as liveness inside routing, acceptance and their exact
  replays. Changing those values would break replay of decided attempts.
- Each attempt-status transition is guarded in SQL by the evidence of the
  owner that decided it: an `allow_review` or `needs_revision` routing manifest,
  a FinalAcceptance for the submission, or a revision expiration receipt for
  `needs_revision → rejected` with reason `revision_deadline_expired`.
- `check_id` is required in v2 so every stored finding is attributable to the
  check that produced it. `coverage_incomplete` is evidence about the checker,
  not the contributor, so it never costs a revision round.
- A coverage hold remains recoverable through the existing Operator retry
  rather than a new workflow. Contributors do not see held results, matching
  the existing `task_setup_blocked` visibility rule.

## Acceptance criteria

- [ ] A v2 result with `check_id`, `path`, `line` and each level round-trips
  from the checker contract through stored findings to both checker-result reads.
- [ ] `coverage_incomplete` without errors yields `task_setup_blocked`, no
  completion event, no acceptance, task still `evaluation_pending`, and an
  Operator retry succeeds from that hold.
- [ ] Routing, false-policy acceptance and revision expiry write the matching
  `attempt_status`/`decided_at`/`status_reason` atomically; SQL rejects each
  transition without its evidence and rejects edits to a final status.
- [ ] Start writes `started_at`; `updated_at` moves on every committed change
  to tasks, assignments and submissions, including raw SQL updates.
- [ ] The migration backfills existing rows and the PostgreSQL schema
  fingerprint and baseline checks pass.
- [ ] Existing routing, acceptance, expiry and replay suites pass unchanged in
  behavior; Go CLI decoders accept the new fields.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `architecture`, `security`, `qa`, `test_delta`,
  `product_ops`, `documentation`
- Human review focus: the `attempt_status` versus `status` split; routing
  coverage gaps to a hold under false ReviewPolicy; requiring `check_id`.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Behavior and custody | Focused backend suites through `run_isolated_tests.py` on PostgreSQL 16 | Recorded in the PR | Hosted lanes run in CI |
| Contract parity | Rust SDK tests and Go CLI tests | Recorded in the PR | None known |

## Review findings

Recorded after internal review.

## Reconciliation

- Current-source reconciliation: based on main at the PILOT-08 merge (#569).
- Next usable boundary: PILOT-READ-2 contributor reads A1–A6 and B3.
- Remaining risks: human review decisions still do not write `attempt_status`
  until #554 composes them.
