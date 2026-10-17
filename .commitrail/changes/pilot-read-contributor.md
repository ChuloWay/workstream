# [PILOT-READ-2] — Contributor work reads and task-list filters

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: A contributor reads their projects, claimed work, attempts, intake preparations and totals across projects through six read-only, separately authorized operations, and a Project Manager filters the project task list, all as projections of records the existing TASK, CHECKERS, ART, PROJECTS, compensation and AUTH owners already keep.

## Intent

Every client needs to show a contributor their own work and what to do next.
Today each contributor read is scoped to one known task or submission, so a
client must already know every task ID. This change adds the cross-project
contributor reads A1–A6 and the B3 filters from the PILOT read-API issue,
once, in the API, with one response shape for every client.

It is the second of three PRs for the issue (PR1 #575 stored the facts these
reads project; PR3 adds the Project Manager and Finance reads C1–C9 and D1).

## Current behavior

- Contributor reads are per resource: `GET /tasks/{id}/work-context`
  (`authorized_commands.contributor_work_context`), `GET /tasks/{id}/submissions`
  and `GET /submissions/{id}` (`api/deps/history.py`), each under a current
  exact-project Submitter grant. There is no list across tasks or projects.
- The only self-scoped list is `GET /actors/me/contributions`
  (`contribution.read_self`). `GET /actors/me/authorization-context` reads one
  known project.
- `POST /tasks/{id}/submission-bundle-preparations` is the only preparation
  surface; its state lives in CHECKERS `selected_pre_submit_runs` and ART
  durable intents/admissions. Nothing reads a preparation back.
- `GET /projects/{id}/tasks` pages every project task by `(created_at, id)` with
  no filters; its `status` and the operational queue's `status` are untyped
  strings.
- `read_contributor_revision` selects and projects one task's revision context
  with four queries, so a list would issue them per row.
- PR1 stored `submissions.attempt_status/status_reason/decided_at/updated_at`,
  `task_assignments.started_at/updated_at` and DB-maintained
  `workstream_tasks.updated_at`, with contributor `(contributor_id, updated_at, id)`
  indexes.

## Bounded change

### Allowed

- Six new active AUTH actions mapped per
  `docs/operations_roles_permissions.md`: `actor.project.list`
  (`actor.profile.read_self`, any human, own grants only) and
  `actor.assignment.list`, `actor.submission.list`, `actor.work_summary.read`,
  `task.submission_bundle_preparation.list`,
  `task.submission_bundle_preparation.read` (`submission.read_own`, Submitter).
  One closed AUTH evaluator for the six reads; catalogue counts, active
  boundary, audit resource types, docs and the MCP contract snapshot that
  embeds the action enum. Migration `0050_contributor_reads` extends only the
  closed audit action/permission vocabulary so the decisions can be recorded
  (the `0033_contribution_reads` precedent), and adds
  `ck_workstream_tasks_status` so the stored task status is the closed
  vocabulary the reads project; it changes no data, and a row outside the
  vocabulary fails the migration rather than a later read.
- Routes `GET /actors/me/projects`, `/actors/me/assignments`,
  `/actors/me/submissions`, `/actors/me/summary`,
  `/tasks/{task_id}/submission-bundle-preparations` and
  `/tasks/{task_id}/submission-bundle-preparations/{preparation_id}`, composed in
  `app/api` from owner ports in one REPEATABLE READ response transaction.
- TASK: a contributor work read port (assignments, submissions, summary
  counts, task resolution for preparation reads), a pure `next_action` rule,
  typed task, assignment and attempt status enums, and the B3 filters on the
  management queue. Batch the revision projection so the work context and the
  assignment list share one implementation.
- CHECKERS: a contributor read of selected PRE runs. ART: the preparation
  projection and an intake finding count beside the existing contributor
  intake projection.
- compensation: award totals per instrument and unit. PROJECTS: name, status
  and active guide identity for a bounded project set.
- Signed `limit`/`cursor`/`next_cursor` pagination bound to actor, filters and
  order through the existing AUTH cursor codec.
- CLI commands, decoders and integration fixtures for the six reads and the
  B3 flags; lane catalogue, behavior-ownership partition, docs and roadmap.

### Not allowed

- No product write, lifecycle rule or stored column; no migration beyond the
  audit vocabulary. No new expiry, outcome or status that the owners do not
  already record.
- No change to who may read a single task, submission or preparation.
- No disclosure from a project where the caller holds no current Submitter
  grant, and no record of another contributor.
- No project-wide or Finance reads (PR3).

## Design and decisions

- Visibility: `/actors/me/*` work reads return only the caller's own rows in
  projects where the caller holds a current Submitter grant, the same rule as
  per-task submission history. A `project_id` filter for a project without
  that grant is the concealed 404. `GET /actors/me/projects` lists projects
  where the caller holds an exact-project admin or contributor grant; a
  system-scoped admin grant adds its role to each listed project but does not
  list every project (no project-list route is invented).
- A2 rows are ordered and filtered by an activity time: the greatest of the
  assignment, own latest submission and own revision preparation stamps, plus
  the task stamp while the assignment is active. So `updated_since` returns
  every row whose stored facts changed. A projection that changes only with
  database time (a revision deadline passing turns `revise` into `none`) moves
  no stamp and reappears with the next stored change. A closed assignment
  projects only the contributor's own facts: no task status, revision or later
  task locks, because those then describe someone else's work. A3 rows change
  at the later of the submission stamp and the CHECKERS evidence stamp of the
  current run (completion, or queueing of a retry run): findings commit with
  their run before TASK routing restamps the submission, and the finding
  counts change at that moment. A1 and A5 have no `updated_since`.
- `updated_since` is inclusive (`>=`); cursors carry the last row's
  `(timestamp, id)` and are HMAC-bound to actor, filters, limit and order.
- `next_action` is server computed by one pure rule: closed assignments
  `none`; claimed `start`; in progress `prepare_submission`; submitted,
  evaluation pending or review pending `awaiting_evaluation`; needs revision
  `revise` only when the latest attempt is `needs_revision` and the revision
  context is `ready`, otherwise `none`.
- A2 `revision` is the work-context `revision_context` object itself, so a
  paused clock (`deadline_at` null, remaining allowance), a zero-round policy
  and every disposition carry over unchanged. One batched `read_task_revisions`
  keyed by task and assignment serves the work context, management task detail
  and the assignment list; an assignment ID determines its task, project and
  contributor through the manifest and preparation foreign keys. Assignment
  status includes `revision_exhausted`.
- `next_action` takes the revision disposition, not the frozen preparation
  outcome, because disposition is what decides whether revising is allowed
  now.
- A preparation is a selected PRE run. `outcome` is `pending`, `passed`,
  `failed` or `infrastructure_failed`; `state` adds intake storage progress
  (`checking`, `checks_failed`, `infrastructure_failed`, `storing`, `ready`,
  `submitted`, `stale`). Findings reuse the contributor intake projection.
  No `expires_at` is returned: v0.1 stores no preparation expiry (ready
  admissions turn stale on context change, not time), and inventing one would
  be a new lifecycle rule. A passed preparation whose storage ended in a
  terminal failure keeps `state=storing`; its `storage_status` carries the
  failure, as on the existing preparation response.
- B3 `import_batch_id` selects native batch membership, not the free-text
  source column; `assignee_actor_id` selects the current assignee.
- Latency budget: no budget existed, so this change sets one list page or
  summary within 1 second on 10,000 tasks and 20,000 submissions on the
  isolated PostgreSQL test database. A2 and A3 order by a computed activity
  time that no index serves; they are bounded per-contributor sorts over the
  contributor-scoped indexes, measured by the scale test. No new index was
  needed at that scale.
- Consistency: every response reads one REPEATABLE READ snapshot. The
  snapshot starts after committing the request's actor-resolution transaction,
  so a service actor's staged last-seen touch persists even when the read is
  then denied or unavailable, as it does for an allowed read. Task
  resolution, the AUTH decision, the page and its batched revision,
  latest-attempt, finding-count, compensation and award queries all see the
  same committed state, so summary counts and award totals agree, as in the
  contribution export.
- Incremental A3 needs the CHECKERS evidence time in the same statement that
  orders and filters the page, so `evidence_stamps()` is an owner port that
  returns a selectable for TASK to join. It is a bounded exception for this
  one read, not a pattern for other ports.
- A per-task read for a task the caller never held is the concealed 404
  before any AUTH decision. A preparation ID on the caller's own task that
  belongs to another contributor records the task-scoped ALLOW and then
  returns the concealed 404; nothing of it is disclosed.
- The project list reads the caller's exact grants without locking them; it
  displays only the caller's own grants and authorizes nothing else.
- MCP exposes no task, submission or preparation tool, so its only contract
  change is the action enum in the authorization-context snapshot.

## Acceptance criteria

- [ ] Each endpoint is in the OpenAPI with its own action ID and typed enums.
- [ ] Each endpoint has authorization tests: allowed role, denied role,
  concealed resource, and another contributor's records never returned.
- [ ] Pagination keeps a stable order without gaps or duplicates, rejects a
  cursor reused with other filters, and `updated_since` returns exactly the
  changed rows.
- [ ] A table-driven test covers `next_action` over every combination of task
  status, assignment state, latest submission and revision outcome.
- [ ] A2 revision fields equal the work-context `revision_context`.
- [ ] List pages and the summary stay within the budget on 10,000 tasks and
  20,000 submissions.
- [ ] CLI commands decode every read and the B3 filters; MCP contract
  snapshots are current; the journey probe still passes.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `security`, `architecture`, `qa`, `test_delta`,
  `reuse_dedup`, `documentation`
- Human review focus: the Submitter-grant visibility rule; closed-assignment
  projection; omitting `expires_at`; the latency budget value.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Authorization, pagination, projection | Focused backend suites through `run_isolated_tests.py` on PostgreSQL 16 | Recorded in the PR | Hosted lanes run in CI |
| Scale | 10k-task/20k-submission latency test | Recorded in the PR | Hosted runner timing differs |
| CLI | Hosted `cli-public-contract` | Recorded in the PR | No local Go 1.27 toolchain |

## Review findings

Human review at `79868e14d` and internal security, architecture, qa,
test_delta, documentation and reuse_dedup tracks at `fcbfa9562`.

- Fixed: incremental A3 reads used only the submission stamp, so findings
  committed before routing were missed (evidence stamp, interval test);
  assignment schemas rejected `revision_exhausted`, zero-round limits and a
  paused clock (A2 now returns `revision_context`; whole-object parity,
  paused zero-round and exhausted closed-claim regressions); the record
  promised REPEATABLE READ while runtime used ordinary transactions (one
  snapshot per response); CLI decoders accepted malformed findings and task
  statuses (existing validators reused, process regressions); a missing
  compensation entry or execution facts raised a 500 instead of the typed
  503; the chain-head rule was copied (one shared predicate); no test replayed
  a cursor as another actor; stale reconciliation and roadmap wording.
  Replay at `47b08e1da`: an isolation-level and two retryable-503
  regressions, the A3 order label and activity-time field descriptions were
  added; the service-actor touch and the selectable port are recorded above.
- Recorded, not changed: per-task decision evidence and the unlocked project
  list (Design and decisions); `state=storing` after a terminal storage
  failure (Design and decisions); preparation finding counts use the existing
  intake count rule beside the intake projection rather than a second rule;
  `TaskStatus` is the closed API vocabulary of the stored task statuses,
  including `accepted`, which the transition constants do not list; the
  `next_action` table derives its expected value by rule, with explicit cases
  for `revise`; `updated_since` returning an assignment after a new own
  submission or revision preparation follows from the same activity
  expression the task-stamp test exercises.

- Second review (`1657511a`): the cursor digest binds `filters` for every
  list, so continuation cursors issued before this change stop decoding; v0.1
  is unreleased and keeps no compatibility path for development cursors.
  Added focused proof for every preparation outcome and custody state, real
  non-empty award totals and their exact decimal wire form, and a second
  session committing findings during one snapshot read.
- CodeRabbit (`203d0fb1`): the closed `TaskStatus` had no stored constraint.
  Every task-status writer stays inside it; `ck_workstream_tasks_status` now
  enforces it in PostgreSQL, and a test keeps the constraint equal to the API
  vocabulary.

## Reconciliation

- Current-source reconciliation: based on main at `7b3dd58df` (PR1 #575, #573
  revision exhaustion and paused revision time, #585 lane capacity, #586,
  #587 and #591 unreadable-ZIP feedback, whose roadmap row keeps both changes,
  #593 and #518). The audit
  migration is `0050_contributor_reads` after `0049_attempt_outcome_findings`;
  main's single-task revision read and this change's batch are one
  implementation; the assignment list carries #573's exhausted status and
  paused clock.
- Next usable boundary: PILOT-READ-3 Project Manager and Finance reads
  C1–C9 and D1.
- Retained state needing explicit handling: a retained selected PRE terminal
  body whose findings lack `check_id` (PR1) fails validation when a preparation
  read parses it.
