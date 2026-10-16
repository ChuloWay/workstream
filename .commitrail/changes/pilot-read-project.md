# [PILOT-READ-3] — Project Manager and Finance reads

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: A Project Manager reads a project's guides, guide documents, activation readiness, submissions, assignments, summary, task import batches and failed intake preparations, and Finance lists every contribution policy version, through ten read-only, separately authorized operations that project records the existing PROJECTS, TASK, CHECKERS, ART, compensation, CON and AUTH owners already keep.

## Intent

A Project Manager running a pilot needs to see the whole project, not one
known task at a time, and Finance needs every contribution policy version, not
only the current one. This change adds the C1–C9 and D1 reads from the PILOT
read-API issue, once, in the API, with one response shape for every client.

It is the third of three PRs for the issue (PR1 #575 stored the facts these
reads project; PR2 #577 added the contributor reads A1–A6 and the B3 task-list
filters, and is the template this change follows).

## Current behavior

- Guides: `POST /projects/{id}/guides` and the guide mutation, compilation,
  sufficiency and activation operations exist; `GET /projects/{id}/active-guide`
  reads only the active guide. No route lists guides, reads one guide with its
  declared documents and policy values, or reads back an uploaded guide
  document (only `POST .../documents/{document_id}/content` uploads one).
- Activation: `GuideActivationService.activate` checks every precondition and
  raises the first failure with its refusal code. There is no dry run.
- Submissions and assignments: management reads are per task
  (`GET /projects/{id}/tasks/{task_id}/submissions`, task detail). There is no
  project-wide submission or assignment list and no project summary.
- Task import: `GET /projects/{id}/task-import-batches/{batch_id}` reads one
  batch; there is no list.
- Intake preparations: PR2 lets a contributor read their own preparations on
  one task. Nothing lists a project's failed preparations.
- Contribution policies: `GET /projects/{id}/contribution-policies/current`
  and `/{policy_id}` read selected versions under Finance; there is no list of
  all versions.
- The manager task list `GET /projects/{id}/tasks` (with PR2's B3 filters) is
  the only project-wide management list.

## Bounded change

### Allowed

- Ten new active AUTH actions owned by `PILOT-READ-3` and mapped per
  `docs/operations_roles_permissions.md`: `project.guide.list`,
  `project.guide.read`, `project.guide.activation_readiness.read` and
  `project.guide.document.read` (`project.guide.manage`);
  `project.submission.list`, `project.assignment.list`, `project.summary.read`,
  `project.task.import_batch.list` and
  `project.submission_bundle_preparation.list` (`project.task.manage`), all
  Project Manager; `contribution.policy.list` (`compensation.policy.manage`,
  Finance Authority). One closed AUTH evaluator, its request, grant, position
  and port types, adapter and factory, read dispatch, audit resource types,
  runtime resource union, concealment mapping, catalogue counts and active
  boundary, docs and the MCP contract snapshot that embeds the action enum.
  Migration `0051_project_reads` extends only the closed audit
  action/permission vocabulary (the `0050_contributor_reads` precedent); it
  changes no data.
- Routes, composed in `app/api` from owner ports in one REPEATABLE READ
  response transaction: `GET /projects/{project_id}/guides`,
  `/guides/{guide_id}`, `/guides/{guide_id}/activation-readiness`,
  `/guides/{guide_id}/documents/{document_id}/content`, `/submissions`,
  `/assignments`, `/summary`, `/task-import-batches`,
  `/submission-bundle-preparations` and `/contribution-policies`.
- PROJECTS (work package 1): a guide list and guide detail read reusing the
  existing guide, document and review/revision policy responses and the latest
  setup run; an activation-readiness read that shares one conditions function
  with `GuideActivationService.activate` (activate raises the first unmet
  condition, readiness returns them all, without locks, consumption, replay
  reservation or writes); ART: split the task guide document open into resolve
  and verify-and-stream so the guide document content read reuses it.
- TASK (work package 2): a project-wide submission list sharing the
  contributor submission row builder and evidence stamp, an assignment list
  sharing the A2 row builder and batched `read_task_revisions`, summary counts
  beside `count_work`, and a task import batch list with one grouped member
  count query; compensation: project award totals beside `read_award_totals`;
  CHECKERS: a project post-submit infrastructure-failure count.
- CHECKERS/ART (work package 3): a project-scoped selected PRE run query and
  the shared preparation projection with the contributor and a finding count,
  no findings or file contents; CON: a contribution policy version list
  beside the existing current and exact-version reads.
- Signed `limit`/`cursor`/`next_cursor` pagination bound to caller, project,
  resource, filters and order through the existing AUTH cursor codec.
- Test packages `tests/project_reads/` and the AUTH evaluator tests; CLI
  commands, decoders and integration fixtures; lane catalogue,
  behavior-ownership partition, docs and roadmap.

### Not allowed

- No product write, lifecycle rule or stored column; no migration beyond the
  audit vocabulary. No new status or outcome the owners do not already record
  (C1 exposes the stored guide statuses only).
- No change to who may read a single task, submission, guide or policy, and
  no change to activation itself beyond extracting its shared conditions.
- No disclosure to a contributor, Operator, Audit Authority or Access
  Administrator through these reads, and no award totals without an
  exact-project Finance Authority grant.
- No listing of these actions in `/actors/me/authorization-context`.
- No frontend, no MCP tool for these reads.

## Design and decisions

- Authority: one closed evaluator for all ten actions. The nine Project
  Manager reads accept only a current Project Manager grant covering the
  project (system or exact); `contribution.policy.list` accepts only a
  covering Finance Authority grant, the same scopes as the existing
  `contribution.policy.read`. The kernel locks actor, matched grant and
  Project in that order; no contributor grant and no other administrative
  role is admitted. Every denial is the concealed 404.
- Guide and guide-document reads name the selected record as the AUTH
  resource inside the project; the owner proves the record belongs to the
  project after the decision and returns the concealed 404 otherwise, as PR2
  does for another contributor's preparation.
- Single-record and summary reads (C2, C3, C6, C9) accept no cursor. Paged
  reads require the cursor secret before any decision is recorded.
- The cursor position, grant and port types mirror PR2's contributor read
  seam. They are separate types because the request carries a project and
  resource rather than an actor-wide scope; the codec, digest shape and
  verification order are shared.
- Defaults chosen (pending user override):
  - C1 exposes the stored guide statuses `draft`, `active` and `superseded`;
    no `retired` guide status exists.
  - C3 assumes the current published contribution policy version; none is an
    unmet condition.
  - C6 award totals appear only when the caller also holds a current
    exact-project Finance Authority grant (the PILOT-10 precedent); the
    adapter locks that grant with the decision. Acceptance rate is accepted
    over decided attempts (accepted, needs_revision, rejected); checker
    infrastructure failures count post-submit checker runs whose status is
    `infrastructure_failed`.
  - C8 `outcome` accepts all four typed values (`pending`, `passed`,
    `failed`, `infrastructure_failed`).
  - The new actions are not listed in `/actors/me/authorization-context`.
- OPEN, pending human decision:
  - Whether C5 shows a Project Manager closed assignments, and with which
    projection (PR2 projects only the contributor's own facts on a closed
    assignment).
  - The Project Manager award-read conflict: `policy.py` gives Project Manager
    `compensation.award.read` while the roles table says Project Manager has
    no compensation award read. C6 follows the roles table until decided.
- Latency budget: the PR2 budget applies, one list page or summary within
  1 second on 10,000 tasks and 20,000 submissions on the isolated PostgreSQL
  test database, with indexed queries and no per-row queries.

## Acceptance criteria

- [ ] Each endpoint is in the OpenAPI with its own action ID (roles per
  `docs/operations_roles_permissions.md`) and typed enums.
- [ ] Each endpoint has authorization tests: allowed role, denied role and
  concealed resource.
- [ ] Pagination keeps a stable order without gaps or duplicates, rejects a
  cursor reused with other filters, and `updated_since` returns exactly the
  changed rows.
- [ ] C5 `revision` equals the work-context `revision_context`.
- [ ] C3 returns the same refusal code as real activation for every reason
  (table test: `unmet[0].code == activate().error_code`), with no side
  effects.
- [ ] List pages and the summary stay within the budget on 10,000 tasks and
  20,000 submissions.
- [ ] CLI and MCP contract snapshots are current; the journey probe still
  passes.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `security`, `architecture`, `qa`, `test_delta`,
  `reuse_dedup`, `documentation`
- Human review focus: the Project Manager coverage rule (system or exact) and
  the Finance-only policy list; award totals behind an exact-project Finance
  grant; the two OPEN items; C3 sharing activation's conditions without side
  effects.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| AUTH evaluator and adapter | `tests/authorization/test_management_read_scope.py`, catalogue and audit contract tests | Recorded in the PR | PostgreSQL custody runs in the focused suites |
| Authorization, pagination, projection | Focused backend suites through `run_isolated_tests.py` on PostgreSQL 16 | Recorded in the PR | Hosted lanes run in CI |
| Scale | 10k-task/20k-submission latency test | Recorded in the PR | Hosted runner timing differs |
| CLI | Hosted `cli-public-contract` | Recorded in the PR | No local Go 1.27 toolchain |

## Reconciliation

- Current-source reconciliation: stacked on PILOT-READ-2 (#577). The audit
  migration is `0051_project_reads` after `0050_contributor_reads`; the
  public schema fingerprint is recomputed after the migration runs on
  PostgreSQL 16.
- Next usable boundary: the PILOT read-API issue is complete; live human
  review and revision follow per the delivery priority.
- Retained state needing explicit handling: none known beyond PR2's retained
  selected PRE body note.
