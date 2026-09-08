# Chunk Contract: WS-ARCH-001-CP08 — Task Attempt Policy Lineage Foundation

Status: proposed non-executable skeleton after CP07. Risk: L1.

TASKS adds its public immutable facts and persistence constraints for
`WorkstreamTask.locked_contribution_policy_version_id`,
`TaskAssignment.submitter_contribution_policy_version_id`, and
`Submission.contribution_policy_version_id`. It adds no readiness, claim,
assignment-creation, Submission-creation, or revision command behavior.

ARCH-03B remains the sole behavior owner: readiness writes the Task lock, claim
copies it to TaskAssignment, and Submission creation stamps the assignment's
attempt version. Ordinary claim performs no CON lookup. ReviewLease later
copies only the Submission stamp. Human `needs_revision` remains the sole
controlled same-Task/TaskAssignment rebase boundary for the next attempt.

This chunk owns only TASK aggregate schema, repository persistence, immutable
public facts, and constraint tests;
it imports no PROJECTS, CON, AUTH, ART, CHECKERS, or REV internals.

Explicitly define when a draft Task may lack the lock and require the complete
lineage before claimability/assignment/Submission. Preserve all other locked
guide, intake, post-submit, review and revision facts; this field addition is
not permission to overwrite an existing context or infer policy for retained
work. Resolve migration strategy from the actual current baseline and retained
rows; missing lineage must not be fabricated to satisfy a non-null constraint.
The bounded implementation records that inventory and fails closed if the
required source evidence is absent.

Use same-project relational keys for the policy and stable Task/Assignment/
Submission identity. Enforce creation-time equality to the locked assignment
in the database and make the Submission policy stamp immutable thereafter.
Do not foreign-key an immutable Submission's policy to its mutable Assignment
current-policy value: a later human revision must rebase the continuing Task
and Assignment without rewriting prior Submissions. Likewise closed historical
assignments must not be forced to follow a later Task lock. Current-attempt
equality guards must permit the complete authorized atomic rebase while
rejecting partial or unrelated updates. Reuse existing lineage/immutability
guards before proposing another attempt entity.

Prove exact same-project lineage constraints, immutable Submission stamp,
round-trip public facts, missing/foreign identifier denial, migration parity,
and no new readiness/claim command or CON lookup. Run real PostgreSQL constraint
tests that directly insert a mismatched stamp, rebase the continuing Task and
Assignment while preserving old Submissions/closed assignments, create the
next Submission with the new stamp, and attempt to rewrite prior evidence.
Run boundary
checks and hosted coverage; architecture, security, QA and
product/operations review the field/state boundary. ARCH-03B supplies the
later command and race proof, not this schema foundation.

## Merge state

- Outcome on merge: `planned`
