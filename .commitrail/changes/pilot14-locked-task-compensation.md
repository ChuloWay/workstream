# [PILOT-14] — Show locked task compensation before claiming

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Authorized project Submitters and Reviewers see exact compensation terms from each task's locked ContributionPolicyVersion in ready-work and contributor task-detail reads.

## Intent

Let a contributor evaluate a task's compensation before claiming it without
granting Finance-policy access or resolving the project's current policy.

## Current behavior

`ReadyTaskSummary` and `ContributorTaskDetail` omit compensation. TASK stores
`locked_contribution_policy_version_id` when screening a task, while the
Finance-authorized ContributionPolicy read exposes internal identifiers that
must not cross a contributor response. `task.queue.read` and `task.read`
currently accept only an active exact-project Submitter grant.

## Bounded change

### Allowed

- CONTRIBUTIONS public locked-terms contracts and their owner repository/adapter.
- TASK ready queue and contributor detail contracts, projections, composition,
  and existing AUTH read guards for active exact-project Submitter or Reviewer
  grants.
- CLI `task ready` and `task show` response validation and text display.
- Focused real-PostgreSQL and CLI HTTP process proof, current API/CLI,
  authorization, compensation and roadmap documentation, required test-lane
  catalogue registration, and this record.

### Not allowed

- Policy creation, locking, publication, retirement, payment, award creation,
  fulfillment, adapter-binding behavior, route keys or binding status.
- Migrations, task-specific term editing, Finance read access, new permissions,
  lifecycle states, parallel owner implementations, or private cross-owner imports.
- PILOT-13 guide-read implementation, PR #504 dispatch work, deployment, merge,
  issue closure, or another implementation chunk.

## Design and decisions

CONTRIBUTIONS exposes one bounded public read port that projects only a locked
version UUID and the two complete contribution rules. Each rule is either the
literal `unpaid` or an immutable award list containing only `instrument`,
`unit`, and exact decimal-string `quantity`. TASK supplies only the version UUID
stored on each task and embeds the detached result in ready/detail responses.
The existing ready/detail authority paths accept either active exact-project
contributor role; claim/start and other Submitter operations remain unchanged.

PR #505 overlaps TASK command/router schemas, CLI client/docs and roadmap files.
This change is implemented independently from its immutable head, preserves its
guide-read additions during the required post-merge reconciliation, and adds no
migration.

## Acceptance criteria

- [x] Unpaid locked rules show `unpaid` for both contribution types in ready and detail responses.
- [x] Paid manual-export fixtures show each exact instrument, unit and decimal-string quantity.
- [x] Publishing a successor policy cannot move an already-released task's displayed terms.
- [x] Active exact-project Submitters and Reviewers see identical terms; absent, revoked and foreign-project roles receive the existing concealed response.
- [x] Responses and CLI output contain no adapter binding ID, route key, binding status, policy lifecycle status or other Finance internals.
- [x] CLI `task ready` and `task show` validate and display the block through public HTTP.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, QA, test delta, reuse/dedup, documentation
- Human review focus: locked-version lineage, exact-role concealment, exact decimals, and the narrow cross-owner projection.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Locked compensation is exact and concealed | Isolated real-PostgreSQL locked terms, ready/detail/work-context/public-queue and changed AUTH matrix tests | Passed: 2 locked-term cases, 60 owner projection cases and 7 matrix cases | Full hosted suite remains CI-owned. |
| CLI validates and renders public output | Built CLI HTTP process tests plus `go test ./...`, `go vet ./...`, `go mod verify` and build | Passed: 12 process cases and all Go checks | None after the post-reconciliation exact-head run. |
| Repository contracts remain consistent | Ruff, compile, and architecture/module boundary tests | Passed: 39 architecture tests and focused static checks | Agent Gates and full hosted CI remain external evidence. |

## Review findings

The architecture check found that the first TASK response contract directly
referenced the CONTRIBUTIONS result type. TASK now owns its immutable response
DTO and maps from the existing CONTRIBUTIONS public port in repository
composition; the full module-boundary suite passes. Remaining exact-head
impact-routed review is coordinated by the lead.

## Reconciliation

- Current-source reconciliation: Rebased on `main` at `3fa0dfb9`, preserving
  PR #504 submission dispatch; reconcile with merged PR #505 before final freeze.
- Next usable boundary: Human merge of this bounded PR; payment and fulfillment remain separate work.
- Remaining risks: None beyond final PR #505 reconciliation, independent review and hosted CI.
