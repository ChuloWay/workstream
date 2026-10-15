# Task Status Template

> Checker revision context and timeout receipts are implemented. Planned human
> Review fields remain unavailable until their own release gates.

## Task

- task ID:
- project ID:
- current state: `DRAFT | SCREENING | READY | CLAIMED | IN_PROGRESS | SUBMITTED | EVALUATION_PENDING | REVIEW_PENDING | NEEDS_REVISION | ACCEPTED | REJECTED | CANCELLED`
- bounded terminal reason, when applicable:
- current TaskAssignment ID/status:
- canonical submitter ActorProfile ID:

## Guide And Submission Context

- task guide lock:
- latest Submission ID/version:
- Submission guide ID/version/activation sequence:
- server-derived artifact hash:
- current CheckerRun ID/outcome:

## Review State

- ReviewQueueEntry ID/state:
- active ReviewLease ID:
- canonical reviewer ActorProfile ID:
- latest immutable Review ID/decision/reason:
- current revision preparation head ID/digest/outcome/direction:
- unresolved blocking ReviewFinding IDs:
- latest FindingResolution IDs:

## Accept State

- FinalAcceptance ID, only on accept:
- source Review ID and Submission ID:
- accepted submitter ActorProfile ID:
- reviewer `completed_review` ContributionRecord ID:
- submitter `accepted_submission` ContributionRecord ID, sourced from
  FinalAcceptance only:

## Rejection, Revision Limits Or Administrative Cancellation

- reject: source human Review ID, bounded reason, blocked TaskAssignment ID;
- revision cap: `revision_limit_reached`, further resubmission refused, current
  deadline and assignment retained;
- revision timeout: `revision_deadline_expired`, immutable TASK rejection receipt,
  released assignment, task returned to `ready`, no synthetic Review;
- legacy revision cancellation: `legacy_revision_context_unrecoverable`,
  evidence-linked reconciliation finding, no synthetic Review.

## Compensation

- reviewer award ID or explicit unpaid result:
- submitter award ID or explicit unpaid result, accept only:
- fulfillment status remains separate from task/assignment state:

## History

| Time | State | Canonical Actor/Service Reference | Reason | Audit Event |
|---|---|---|---|---|
| `<time>` | `<state>` | `<actor>` | `<reason>` | `<uuid>` |
