# Decision 0015: Project Contributor Roles Are Independent

## Status

Accepted for implementation planning.

## Context

The earlier authorization plan stored `submitter`, `reviewer`, or a combined
role on one active ProjectRoleGrant per actor and project. That couples two
independently revocable capabilities and forces role replacement when a
contributor gains or loses only one capability.

## Decision

The v0.1 persisted ProjectRoleGrant values are exactly:

```text
submitter
reviewer
```

A contributor may hold both independent active grants. Each grant has its
own qualification snapshot, immutable history, issue/revoke evidence, and
transaction-time revalidation. Grant issue never replaces an unrelated role.
Regrant after revocation creates a new immutable row.

No administrative grant implies any project contributor role. A submitter cannot
act as the sole reviewer of their own work even when they separately hold a
reviewer grant.

Adjudicator grants and adjudication operations are excluded from v0.1.
A future separately approved initiative must define the
lifecycle before AUTH can register and activate exact actions.

## Consequences

- The database permits at most one active grant for each actor, project, and
  role.
- Submitter revocation is consumed by task-assignment reconciliation.
- Reviewer revocation is consumed by review-lease and queue reconciliation.
- Revoking one contributor role does not change another contributor role or an
  AdminRoleGrant.
- The prior combined-role portion of Decision 0012 is superseded. Its identity,
  local-role ownership, and deny-by-default authorization decisions remain in
  force.
