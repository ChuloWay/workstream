# [PILOT-08] — Complete controlled contributor revision

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Govern checker-driven revision with assignment-scoped caps, fresh deadline windows, atomic complete-context rebase, contributor-visible change summaries, explicit repair and durable timeout rejection/release/reclaim, preserving historical evidence and a shared handoff for human revision.

## Intent

An initial Submission is round 0. A policy allowing two revisions permits
rounds 1 and 2, for three submissions total. Retry and duplicate delivery do
not spend a round. Issue #495 records the settled product decision.

## Current behavior

TASK routes exact checker failure to needs_revision and admits a successor
without applying RevisionPolicy.max_revision_rounds. ART and TASK already
resolve the exact complete PROJECTS context. Submission.version is consecutive
and immutable; no second counter is needed.

## Delivery scope

The user explicitly requested one complete PILOT-08 PR, with independently
reviewed stage commits. PR #569 therefore contains the cap stage and remaining
revision work together; additional stage PRs are not planned. Human decision
creation remains owned by #554; this work supplies its reusable revision
handoff, and does not claim live human decision delivery before that owner lands.

## Bounded change

### Allowed

- TASK public submission-context rule and canonical submission creation.
- ART preparation and its public error mapping; TASK public error mapping.
- Exact PM revision-repair AUTH action, typed facts and audit participant/closure.
- TASK revision preparation, immutable source/target context records, eligibility,
  backend contributor reads and authorized blocked-context recovery.
- PROJECTS active/historical typed context reads and composition adapters needed
  by the existing TASK routing transaction; no alternate lifecycle writer.
- Affected TASK, CHECKERS and ART retained-lineage constraints and models,
  INSERT-only currentness guards, migrations/head/schema registration.
- Exact revision context acknowledgement through existing intake and submission
  contracts; existing read authority and public error mapping.
- Focused cap, replay, concurrency and SQL regressions using existing fixtures,
  including registration in the CI lane catalogue and its ownership assertion.
- Affected current lifecycle specification, roadmap and this record.
- TASK-owned timeout outcome and assignment release/reclaim, exact internal AUTH,
  audit and outbox participants, recurring durable worker scan and registration.
- Shared OUTBOX immutable not-before append custody, exact logical-key read,
  replay-safe expiry registration, bounded unknown-effect retry for the exact
  expiry event type/version, initialization from PostgreSQL time, SQL projection
  guards and immutable unknown-effect receipt truth. Other delivery rules remain.
- Assignment-scoped revision accounting and new-claim intake across TASK/ART/
  CHECKERS, preserving task-global immutable Submission ordering and evidence;
  derive the local round from assignment submissions without a second counter.
- TASK-owned bounded discovery of retained current revision sources, fixed-service
  recovery authority, immutable root or exact missing-event registration, and
  corresponding lifecycle audit/SQL closure. Discovery preserves the source
  manifest's original deadline and never rebases the continuing task.
- Reconcile the merged CLI submission/context commands with the revision contract.

### Not allowed

- Guide setup integration (#552), export pagination (#497), dependencies (#565)
  or unrelated CLI expansion.
- Human queue/lease/decision creation, general claim inactivity expiry,
  redundant counters, retained-data rewrites,
  compatibility paths, deployment or merging.

## Design and decisions

Use one TASK-owned pure capacity check over verified locked PROJECTS facts,
including exact revision policy identity. Apply it after current authority in
preparation and before creating new Submission facts. Exact committed replay
retains its original path. The SQL INSERT guard requires positive consecutive predecessor lineage, reads
only the immutable exact policy, and creates no explicit row locks or lifecycle
writers. Historical rows remain
unchanged. Task-global Submission versions remain ordered, but revision accounting
must be scoped to the current assignment so a new claimant receives round 0.

## Remaining design decisions

Deadline timing uses PostgreSQL time and is frozen from the governing source
policy. The user confirmed a fresh window for each committed fixable failure.
Exact replay, duplicate delivery and repair preserve the original window. No contributor claim lease is introduced.

The user subsequently confirmed automatic revision timeout: append the expired
attempt's rejection outcome, release its assignment and return the task to ready.
This supersedes the earlier no-automatic-closure restriction. A seven-day policy
uses 168 hours; PostgreSQL supplies all eligibility timestamps. A successful
immutable resubmission ends its predecessor's window, while the next fixable
failure starts another. ZIP upload alone does not end it. Cap exhaustion refuses
another revision; the outstanding deadline still governs automatic release.

Use a TASK-owned operation with fresh exact service authority, TASK-first locks,
immutable timeout evidence and atomic assignment/task/audit/outbox changes. A
durable recurring scan recovers overdue work after downtime; duplicate delivery
and stale jobs cannot change a newer attempt or assignment. New claimants receive
their own initial attempt and revision allowance. Do not rewrite prior evidence,
fabricate Reviews, or create contribution/award effects on timeout.

Historical attempt rows must stop referencing mutable TASK policy stamps while
retaining direct immutable owner references and INSERT-time exact-context
checks. Rebase selects one complete approved active PROJECTS context, updates
the continuing task/assignment atomically, and retains old/new lineage in an
immutable preparation. Missing/inconsistent context produces a readable blocked
head rather than a partial rebase. Replays never reselect active policy.

## Acceptance criteria

- [x] max=2 permits initial0, revision1 and revision2; the next attempt receives
  revision_limit_reached without PRE/provider work or durable creation effects.
- [x] The final new-write boundary also enforces the cap; an old ready admission
  cannot bypass it. Exact committed replay remains successful.
- [x] Direct SQL cannot insert an over-cap Submission; rollback leaves prior
  immutable facts unchanged.
- [x] Existing stale-cause and concurrent replacement tests still pass.

- [ ] Fixable completion prepares one immutable source-rooted next-attempt
  context; all changed policies rebase together or the operation is blocked.
- [ ] Deadline and cap refusal leave no successor/partial rebase and are visible
  through authorized contributor reads; infrastructure retries spend no round.
- [ ] Contributor context exposes a bounded immutable change summary; intake
  and final creation bind the exact prepared context and reject stale heads.
- [ ] Repair appends an authorized successor without editing earlier evidence;
  restarts, duplicate delivery and races cannot branch preparation history.
- [ ] Historical submissions/checker evidence remain unchanged/readable after
  rebase. PostgreSQL direct-write and intermediate-lock-wait tests protect this.
- [ ] Human revision can consume the shared core with distinct genuine Review
  provenance; live human decision integration remains coordinated with #554.
- [ ] PostgreSQL-time expiry records rejection, releases the assignment and
  returns the task to ready with one immutable audit/outbox outcome.
- [ ] A new claimant completes round 0 and their own allowed revisions after
  expiry without inheriting the old allowance or changing old evidence.
- [ ] Real intermediate-lock-wait tests cover expiry/resubmission, duplicate
  workers and stale jobs after reclaim; API/worker restart and outbox failure
  recover the exact outcome without partial state or economic effects.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture/reuse, security, QA/test delta, documentation.
- Human review focus: off-by-one semantics, locked policy custody, concealment,
  replay and SQL enforcement; complete-context atomicity, authorized recovery and immutable history.

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
records as a prerequisite for rebase. The expanded scope replaces those backward
references with immutable-owner custody and INSERT-time currentness checks.
Review also identified non-positive Submission versions as a SQL cap bypass;
the insert guard now validates positive consecutive lineage. The final-write
regression arranges a real ready admission without the new application cap,
retaining all existing authority, checker and artifact guards. Its SQL probe
uses the canonical writer with only the application cap removed, avoiding
unrelated uniqueness or stale-lineage rejections.

## Reconciliation

- Current-source reconciliation: merged main 2c1f7517c includes supported false
  activation and the CLI submission journey. Checker remediation shares revision
  limits by the explicit product decision, superseding the human-only wording.
- The working candidate implements deadline handling, guarded complete-context
  rebase, contributor change summaries and repair, assignment-scoped rounds,
  atomic timeout receipts/outcomes and retained-source recovery. These are not
  delivered capabilities until the complete candidate passes review and merges.
- Interim validation: the CLI submission HTTP suite passed 14 tests. An isolated
  PostgreSQL run proved due expiry, immutable submission preservation, assignment
  release, rejected-status projection and outcome acknowledgement, then failed
  retained-source recovery at audit input validation. This is partial evidence,
  not final-head approval; recovery, crash/retry and concurrency checks remain.
- Remaining risks: complete cross-owner retained lineage and lock-order proof,
  final independent reviews and required CI. Live human decision creation remains
  the separate #554 dependency.
