# pm-award-read — Project Managers read award totals; Operators do not

- Initiative: None
- Durable disposition: `Planned`
- Intended merge outcome: a covering Project Manager sees the project's award
  totals in the C6 summary without a Finance grant, and the Operator role no
  longer holds `compensation.award.read`; the roles table, the role policy and
  the reads agree.

## Intent

The maintainer decided on 2026-10-18 that Project Managers may read
compensation awards and Operators may not. This supersedes the PILOT-READ-3 C6
default, which required an exact-project Finance Authority grant
(`pilot-read-project.md`). Before this change the role policy (`policy.py`)
gave both Project Manager and Operator `compensation.award.read`, while the
roles table said neither held it. No action consumed either grant.

## Current behavior

- `policy.py` grants `compensation.award.read` to Operator, Project Manager,
  Finance Authority and Audit Authority.
- C6 `GET /projects/{project_id}/summary` returns `award_totals: null` unless the
  evaluator also locks an exact-project Finance Authority grant. It then binds
  that grant into the recorded decision through an evaluated-resource return
  that runs through read dispatch and the kernel.
- The roles table says Project Manager and Operator have no award read.

## Bounded change

### Allowed

- Remove `compensation.award.read` from the Operator role.
- C6 always returns the project's award totals to an authorized caller.
  Remove the Finance grant lookup, `award_totals_grant_id`, the grant's
  `award_totals_visible`, and the evaluated-resource return in read dispatch
  and the kernel, which existed only for that disclosure.
- `award_totals` becomes a required list in the API and the CLI decoder.
- Update the tests, the external API drill role contract, the CLI README, the
  roles table, the authorization spec and the roadmap; regenerate the
  structure-debt ledger.

### Not allowed

- Contribution-policy authority: create, update, publish and retire stay
  Finance Authority only.
- Any change to Finance Authority or Audit Authority award read, or to the
  contributor's own A6 totals.
- New actions, permissions or migrations.

## Design and decisions

- Publishing a ContributionPolicy stays with Finance Authority. A Project
  Manager already creates tasks and, by default, accepts work; letting the
  same role set payouts would remove the independent check on money. A small
  team can give one person both grants on a project.
- C6 stays a Project Manager action (`project.task.manage`). Finance and Audit
  Authority still cannot call it, although they hold award read; they read
  awards through the existing contribution reads.
- Permissions are resolved from `policy.py` at request time. No migration
  stores role permissions, so no data changes.

## Acceptance criteria

- [x] A covering Project Manager receives `award_totals` (empty without
      awards) and the decision matches only the Project Manager grant.
- [x] Finance, Operator and Audit Authority cannot read the summary.
- [x] The Operator role definition no longer lists `compensation.award.read`.
- [x] The CLI rejects a summary whose `award_totals` is missing or null, and
      prints each total.
- [ ] Hosted Backend and CLI lanes pass.

## Risk and review routing

- Risk class: `L1` (authorization role policy and a public response shape).
- Required reviewers: security/authorization.
- Human review focus: Project Manager award visibility; Operator losing award
  read.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Evaluator and adapter | `pytest tests/authorization/test_management_read_scope.py` | 101 passed | None |
| Role definitions | `pytest tests/test_authorization.py -k role_policy_and_definition_responses_are_exact` | passed | None |
| CLI | `go build`, `go vet`, `go test ./internal/...`; `test_manager_reads_http.py`, `test_contributor_reads_http.py` | passed (12) | None |
| PostgreSQL C6 | `tests/project_reads/test_work_authority.py` | hosted CI | Hosted lanes |

## Review findings

Internal security review: no blocker or major finding. No caller gains C6
access; every read evaluator returns the same six values and the kernel
unpacks them; Operator lost no consumed authority; the recorded decision
digests the resource sent, with the Project Manager grant matched. Two minor
stale comments were fixed: the C6 route docstring (published as the OpenAPI
description) and the CLI `ProjectSummary` comment.

## Reconciliation

- Roadmap: C6 and the dependency map now state that summary award totals use
  the Project Manager grant.
- Next usable boundary: unchanged.
