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
  (the `0033_contribution_reads` precedent); it changes no data.
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
  exactly the rows whose projection changed. A closed assignment projects only
  the contributor's own facts: no task status, revision or later task locks,
  because those then describe someone else's work. A3 uses the stored
  submission stamp and its PR1 index; A1 and A5 have no `updated_since`.
- `updated_since` is inclusive (`>=`); cursors carry the last row's
  `(timestamp, id)` and are HMAC-bound to actor, filters, limit and order.
- `next_action` is server computed by one pure rule: closed assignments
  `none`; claimed `start`; in progress `prepare_submission`; submitted,
  evaluation pending or review pending `awaiting_evaluation`; needs revision
  `revise` only when the latest attempt is `needs_revision` and the revision
  context is `ready`, otherwise `none`.
- A2 revision fields are the work-context `revision_context` projection: one
  batched `read_contributor_revisions` now serves both reads.
- A preparation is a selected PRE run. `outcome` is `pending`, `passed`,
  `failed` or `infrastructure_failed`; `state` adds intake storage progress
  (`checking`, `checks_failed`, `infrastructure_failed`, `storing`, `ready`,
  `submitted`, `stale`). Findings reuse the contributor intake projection.
  No `expires_at` is returned: v0.1 stores no preparation expiry (ready
  admissions turn stale on context change, not time), and inventing one would
  be a new lifecycle rule.
- B3 `import_batch_id` selects native batch membership, not the free-text
  source column; `assignee_actor_id` selects the current assignee.
- Latency budget: no budget existed, so this change sets one list page or
  summary within 1 second on 10,000 tasks and 20,000 submissions on the
  isolated PostgreSQL test database. The keyset reads use PR1's contributor
  `(contributor_id, updated_at, id)` indexes; no new index was needed at the
  measured scale.
- Reads run in the caller's ordinary request transaction like the existing
  queue and history reads; a page and its batched revision/latest-attempt
  queries are separate statements, so a concurrent transition can show in one
  and not the other until the next read.
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

- Recorded in the PR after the internal reviewer tracks run.

## Reconciliation

- Current-source reconciliation: stacked on PR1 (#575) at `cac15136d`. Main
  has since merged #573 (revision exhaustion and paused revision time), which
  conflicts with PR1; this change inherits that reconciliation through the
  shared revision projection and assignment status enum.
- Next usable boundary: PILOT-READ-3 Project Manager and Finance reads
  C1–C9 and D1.
- Retained state needing explicit handling: a retained selected PRE terminal
  body whose findings lack `check_id` (PR1) fails validation when a preparation
  read parses it.
