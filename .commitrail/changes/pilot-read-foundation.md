# [PILOT-READ-1] — Stored attempt outcomes and per-finding checker evidence

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Submissions, assignments and post-submit checker runs store the outcome, timestamp and per-finding facts that the PILOT read APIs project, through the existing TASK and CHECKERS owners and the single external checker result contract, without changing who decides an outcome; successful intake returns its nonblocking feedback.

## Intent

The PILOT read-API issue asks every client to show a person their attempts,
what happened and what to do next. Main stores too little to answer honestly:
the reads would have to invent or re-derive outcomes. This change makes those
facts durable at the moment the existing owners decide them, so the later read
PRs are pure projections.

It is the first of three PRs for the read-API issue:

1. This change: stored facts, the checker result finding shape, successful
   intake feedback, B1 and B2.
2. Contributor reads A1–A6 and the B3 task-list filters.
3. Project Manager and Finance reads C1–C9 (including activation readiness) and D1.

The human decided the split, the contract extension, stored columns with
backfill over read-time derivation, and how a coverage gap is routed: to human
review when the locked ReviewPolicy requires it, otherwise back to the
contributor without spending a revision round. A hold that could leave a task
in `evaluation_pending` indefinitely was explicitly rejected.

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

- Change the finding shape of the one canonical `external_checker_result.v1`
  contract in place, for unreleased v0.1, across the Python contract, Rust SDK
  and checker service, pilot04 experiment checker, fixtures and CLI decoders.
  Findings gain a required `check_id`, an optional `line` (only with a `path`)
  and the `coverage_incomplete` level. The verdict rule is unchanged: `failed`
  exactly when an `error` finding exists. No second contract identifier,
  version-transition guard or compatibility parser exists.
- Add immutable `checker_result_findings` rows written in the existing
  finalization transaction and verified against the stored result by the
  existing deferred terminal-custody trigger.
- Route a completed result with no failed member and at least one
  `coverage_incomplete` finding by the task's locked ReviewPolicy: `allow_review`
  (to `review_pending`) when human review is required, otherwise
  `needs_revision`. Classification reads the policy through an injected
  PROJECTS review-mode port; terminal SQL custody recomputes the same route.
- Record such a return as `needs_revision` with `status_reason`
  `checker_coverage_incomplete` and exclude it from every revision-round count
  (capacity guard, revision-preparation guard, TASK preparation, submission
  context and replay). The next attempt keeps the source's current round, so
  `next_revision_round` allows 0. A genuine failure keeps its normal
  accounting even beside a coverage finding. Consecutive coverage
  returns keep the first return's revision window (Python and the PostgreSQL
  preparation guard), so a repeated gap still reaches the revision deadline.
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
- Return the existing bounded PRE results projection on successful
  preparation and exact replay (`pre_submission_results`), from the retained
  terminal facts, and print nonblocking findings in the CLI.
- Update the Go CLI strict decoders (history, checker results, pre-submit
  feedback findings, successful preparation feedback, revision context round)
  and their integration fixtures.
- Update the authorization OpenAPI field-set assertions, the CI lane catalogue
  for the new test modules (keeping main's measured project-lane allocation of
  the batch-transition journeys, and pinning the two new stored-outcome proof
  modules to project lanes A and C after hosted lane D crossed its 1200-second
  deadline with main at 1148 seconds), the journey probe's outcome assertions, the Alembic
  environment head pin, and current docs (README revision-round sentence,
  checker framework, data model, lifecycle state machine, first-user flows,
  roadmap).
- Constrain finding paths to safe relative archive paths in Python and the Rust
  SDK, and require both location keys in the Rust SDK so its digest matches
  Python's.
- Batch the per-row evidence and per-run result queries the history reads
  already issue, removing their N+1 shape.
- Reconcile with #573 as migration 0049 after `0048_revision_exhaustion`:
  zero-revision policies and paused setup-blocked deadlines stay as #573 built
  them. Every exhaustion round count uses one SQL round helper that excludes
  coverage returns, and a coverage return on the final permitted attempt
  returns the work instead of exhausting it. The consecutive-coverage window is
  supplied to #573's PostgreSQL revision clock by one `revision_window_origin`
  function instead of a Python copy. Exhaustion records the attempt as
  `rejected` with `revision_limit_reached` through the same guarded transition.
- Refuse the 0049 upgrade, before any change, while a retained checker result
  or selected PRE terminal holds a finding that the required `check_id` or safe
  path rule would reject on replay, with a retained-state regression.

### Not allowed

- No change to who decides an outcome or to AUTH actions; no new endpoints.
- `submissions.status` keeps its intake-liveness meaning; no replay or guard
  that reads it changes behavior.
- No second result contract identifier, version-transition machinery,
  compatibility parser or fallback path.
- No substitution of a checker image for an existing task lock.
- No human review decision writes (#554); no fabricated Review.
- No change to checker-authored message exposure: reads keep fixed worker
  messages.

## Design and decisions

- `attempt_status` (`evaluation_pending | review_pending | accepted |
  needs_revision | rejected`) is a separate column rather than new values of
  `submissions.status`, because seven Python checks and a SQL guard use
  `status = 'submitted'` as liveness inside routing, acceptance and their exact
  replays. Changing those values would break replay of decided attempts.
- `accepted` is written inside the shared TASK accepted-effects operation, so
  every acceptance trigger (the false-policy route now, human `accept` later)
  records it once.
- Each attempt-status transition is guarded in SQL by the evidence of the
  owner that decided it: an `allow_review` or `needs_revision` routing manifest,
  a FinalAcceptance for the submission, or a revision expiration receipt for
  `needs_revision → rejected` with reason `revision_deadline_expired`.
- `check_id` is required so every stored finding is attributable to the
  check that produced it. `coverage_incomplete` is evidence about the checker,
  not the contributor, so it never costs a revision round.
- A coverage return spends no round, which alone would let a persistent gap
  return the work forever. Keeping the first return's window across
  consecutive coverage returns bounds that loop with the existing revision
  expiry instead of adding a separate coverage cap (human decision).
- The review requirement is the task's locked ReviewPolicy, read through the
  PROJECTS port that TASK routing already uses. The completion coordinator
  returns the stored routing, which terminal custody already verified against
  that policy, instead of recomputing it.

## Acceptance criteria

- [ ] A result with `check_id`, `path`, `line` and each level round-trips
  from the checker contract through stored findings to both checker-result reads.
- [ ] Successful preparation and its exact replay return the same bounded
  intake results, including nonblocking coverage findings, without rerunning
  PRE; the CLI decodes and prints them; the attempt still awaits evaluation.
- [ ] An error beside a coverage finding records no coverage reason, spends
  round one and uses the policy window; the test fails without the
  `failed_count=0` guard.
- [ ] `coverage_incomplete` without errors reaches `review_pending` under a
  true ReviewPolicy and returns to the contributor under a false one, recorded
  as `checker_coverage_incomplete` keeping the current round; it never
  auto-accepts and never leaves the task in `evaluation_pending`. Consecutive
  coverage returns keep the first window, and later failures still spend the
  full locked allowance.
- [ ] Routing, false-policy acceptance and revision expiry write the matching
  `attempt_status`/`decided_at`/`status_reason` atomically; SQL rejects each
  transition without its evidence and rejects edits to a final status.
- [ ] Start writes `started_at`; `updated_at` moves on every committed change
  to tasks, assignments and submissions, including raw SQL updates.
- [ ] The migration backfills existing rows and the PostgreSQL schema
  fingerprint and baseline checks pass.
- [ ] Existing routing, acceptance, expiry and replay suites pass unchanged in
  behavior; Go CLI decoders accept the new fields.
- [ ] Under a zero-revision policy a coverage return keeps round 0 without
  exhausting, and the next genuine failure exhausts immediately and records
  `rejected`/`revision_limit_reached`; #573's exhaustion, pause and expiry
  suites pass on the merged chain.
- [ ] The 0049 upgrade refuses retained checker or selected PRE findings
  without `check_id` before changing the database, and accepts live evidence.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `architecture`, `security`, `qa`, `test_delta`,
  `product_ops`, `documentation`
- Human review focus: the `attempt_status` versus `status` split; coverage-gap
  routing and its round exemption; requiring `check_id` and safe paths.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Behavior and custody | Focused backend suites through `run_isolated_tests.py` on PostgreSQL 16 | Recorded in the PR | Hosted lanes run in CI |
| Contract parity | Rust SDK tests and Go CLI tests | Recorded in the PR | None known |

## Review findings

- All six tracks reported no High findings at the first candidate. The shared
  Medium was that coverage returns, which spend no round, could loop without
  bound. The human chose keeping the first return's window, and it is implemented
  in Python and SQL.
- The replay of the window change found no defect. Its Medium test gap (a
  second return routed after the first deadline, plus a shared-deadline expiry)
  is now covered. Contributor finding counts now use the same filters as
  contributor history.
- Human reconciliation of #575: one canonical contract identifier (the v1/v2
  distinction and the retained-v1 refusal were removed); successful intake
  feedback; a discriminating mixed error-plus-coverage regression; corrected
  round wording. CodeRabbit's competing-manifest and stale-ORM suggestions were
  rechecked: lifecycle locking prevents competing routing manifests and no
  caller reads stale ORM outcome fields, so no machinery was added.
- Noted, not a defect: the stored-coverage-finding clause in the attempt guard
  and backfill is defence in depth. Terminal custody already makes a
  zero-failure `needs_revision` imply such a finding, so tests cannot
  discriminate the clause.
- Observed outside scope: on the public bundle-preparation route, an upload
  that is not a readable ZIP fails archive inspection before any pre-submit
  check runs, and `SubmissionArchiveRejectedError` surfaces as a 500 instead of
  actionable feedback. Left for a separate change.

## Reconciliation

- Current-source reconciliation: merged with main at #573
  (`ce60d0f02`); this migration follows `0048_revision_exhaustion` in one chain.
- Next usable boundary: PILOT-READ-2 contributor reads A1–A6 and B3.
- Retained state needing explicit handling: the migration rewrites no checker
  evidence. A retained `checker_runs.result_json` or selected PRE
  `terminal_json` whose findings lack `check_id` (or carry an unsafe path)
  would fail current validation on replay, so 0049 refuses to upgrade such a
  database before changing it and names the affected rows; v0.1 recreates it.
  Rewriting the digest-bound results would forge evidence, so no transition
  exists. The intake copy in `submission_bundle_durable_intents` is compared
  byte-for-byte with the checked PRE terminal, never re-parsed. Runs completed
  before 0049 have no finding rows, so their reads show one entry per member.
  Whether hosted data holds affected rows was not inspected; the refusal makes
  that visible at upgrade instead of as replay failures.
- The pilot04 checker image source changed (`check_id`, `line`); an image built
  from the previous source emits findings the contract now rejects as invalid
  output, never a silent pass. No repository fixture pins a real image digest
  (setup fixtures use synthetic digests and controlled execution). The image was
  not rebuilt here because the sandbox cannot reach Docker Hub for its base.
- Remaining risks: human review decisions do not write `attempt_status` yet.
  #554 must extend the attempt-status guard (`review_pending` to `accepted`
  through the shared acceptance effects already works; `review_pending` to
  `needs_revision`/`rejected` needs Review evidence) before human
  `needs_revision` reuses revision expiry. The Go CLI changes are not compiled
  locally (no Go 1.27 toolchain in the authoring sandbox); hosted CLI CI proves
  them.
