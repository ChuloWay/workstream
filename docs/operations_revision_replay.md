# Revision Replay

## Status And Purpose

This contract covers controlled revision and the remaining human Review
integration. Human decision composition remains unavailable until its owning
REV work and exact AUTH activation complete. Checker-remediation replacement
uses public preparation and admission-backed Submission operations with a frozen
next-attempt context; it does not make human Review decisions available.

Revision replay preserves an immutable answer to three questions: what the
reviewer required, how the submitter responded, and how a later reviewer
resolved each issue. No participant edits a prior Review, finding, response, or
resolution.

## Review-Rooted Preparation

Human revision begins from one immutable `Review(needs_revision)`. Checker
remediation begins from the exact authorized current CheckerRun failure and its
routing manifest. Both require a frozen next-attempt preparation; checker
remediation never fabricates a Review, finding, reviewer contribution or human
actor.

Before contributor access, Workstream appends a RevisionContextPreparation. It
compares the prior Submission's complete stamped governing context with the
currently active applicable Project Guide/source, submission-artifact,
pre-submit/post-submit checker, review, revision, task-template/task-execution,
and submitter ContributionPolicy context:

- every exact component match: `kept`;
- all changed valid active components: `rebased` together, with `forward` or
  `backward` recorded where the component is ordered;
- missing, incomplete, inconsistent, revoked, or unsafe context: `blocked`.

The preparation keeps every exact component match and rebases every changed
valid component as one selected context. Any missing, incomplete, inconsistent,
revoked, or unsafe component blocks the whole preparation. It freezes the
selected context, context digest, prior Submission, originating Review, source
and target TaskAssignments, prior/next submitter ContributionPolicyVersion, and
change summary. Task Context returns the validated head, not moving selectors.
No rebase occurs during review; the reviewer reads the context stamped on the
leased Submission.

The completed reviewer contribution uses the originating ReviewLease version.
Successful human revision preparation may atomically rebase the continuing
Task and TaskAssignment for the next submission attempt. Earlier Submissions
and ReviewLeases remain immutable; the next Submission and ReviewLease use the
rebased version. The decision,
reviewer contribution/award, task/assignment effects, preparation or blocked
outcome, audit/outbox, and visible state commit once or roll back together.

## Submitter Response

For each unresolved blocking ReviewFinding, the assigned submitter creates one
immutable SubmissionFindingResponse containing:

- finding ID;
- response text and concrete change summary;
- optional finalized evidence binding;
- exact preparation head ID and digest;
- target Submission and TaskAssignment lineage.

Advisory findings may be answered but do not block resubmission unless the locked
policy explicitly requires a response. Vague aggregate “fixed all” text cannot
replace per-finding responses. The distinct checker-remediation path uses only
contributor-safe checker messages/fixes and requires no fabricated
ReviewFinding response or resolution.

## Resubmission And Checks

A human-Review Submission N+1 acknowledges the exact preparation head/digest,
links its immediate predecessor, and stamps the complete frozen context. A
checker-remediation Submission N+1 binds the exact final needs-revision CheckerRun
and its preparation, without a ReviewFinding response. Public ZIP preparation
requires `X-Revision-Preparation-Id` and `X-Revision-Preparation-Sha256`; the ready
admission retains that acknowledgement for final creation. Initial intake omits
both. Both paths rerun the normal finalization and checker
spine. Only a current successful `allow_review` may create a new queue entry.

Human Review return initially prefers the reviewer who requested revision. The
distinct corrected checker path enters open routing. Expiry,
decline, or invalidation opens the entry without resetting queue age.

## Reviewer Resolution

The later Review appends one FindingResolution for every required prior finding:

- `resolved`;
- `unresolved`;
- `not_applicable`.

Each resolution carries bounded rationale and optional evidence. It never edits
the original finding or submitter response. A new guide-grounded issue becomes a
new ReviewFinding on the later Review.

## Limits And Recovery

The initial Submission is round 0; a limit of 2 permits revisions 1 and 2.
Each committed contributor-fixable failure starts a fresh window using the
failed attempt's locked policy and database time. Eligibility ends at the exact
deadline. Infrastructure retries spend no round; duplicate delivery, replay and
context repair preserve the original window. A reached revision limit or
deadline blocks further preparation and
`submission.create`. At expiry, the durable timeout operation records rejection
of the outstanding attempt, releases its assignment and returns the task to
`ready`. It preserves original Submission and finding evidence and creates no
synthetic Review, contribution or award. Task/assignment changes, immutable
timeout evidence, audit and outbox publication intent commit atomically.

The recurring worker scan uses PostgreSQL server time and recovers overdue
opportunities after downtime. Duplicate deliveries and old jobs recheck exact
source, assignment and status under TASK-first custody; they cannot reject a
newer submission or release another claimant. A new claimant starts round 0
with their own allowance while task-global Submission versions remain ordered.

A blocked or invalid context preparation can be repaired only by appending one
successor through covered-manager repair. For checker-rooted preparations,
`POST /projects/{project_id}/tasks/{task_id}/revision-context/repair` takes
`parent_preparation_id`, `parent_preparation_sha256`, a bounded `reason`, and an
`Idempotency-Key`. It records the exact parent and authorized child atomically.
Repair cannot bypass limit/deadline exhaustion. The contributor work-context
read exposes the frozen change summary and current eligibility.

If a retained routing manifest has no preparation, the same endpoint accepts
`routing_manifest_id` and `reason` instead of the parent pair. This explicit
manager operation records the missing root using the original failure's window;
ordinary routing replay does not create it. An expired or exhausted source stays
blocked. Exact repair replay returns its original preparation identity and
window after fresh authorization, with eligibility evaluated against the current
source and preparation head.

## Required Proof

A human-Review revision cannot return to human review unless every unresolved
blocking finding has one response, the exact preparation is still current,
Submission lineage is immediate and same-task, evidence bindings are finalized,
and the new `allow_review` CheckerRun is current for that Submission.

A checker-remediation replacement uses the exact authorized needs-revision
routing manifest for the immediate predecessor's current completed CheckerRun.
ART evidence and admission, TASK dispatch and final AUTH resources retain the
server-selected `checker_remediation_manifest_id`; the new Submission links its
predecessor and admission without a duplicate cause field. It uses the frozen
next-attempt context, reruns full pre-submit intake, and has no human Review or
ReviewFinding response requirement. A later current `allow_review` result can
enter the ordinary review route only under its locked ReviewPolicy. A later
retry cannot rewrite the committed cause.
