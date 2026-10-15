# ADR 0009: Review Decisions Are Canonical

## Status

Accepted

## Context

Workstream review results drive task state, revision loops, contribution
records, conditional compensation awards, and reputation signals.

If projects invent their own review outcome labels, downstream lifecycle rules become ambiguous.

Automated checker results also influence workflow routing before human review. That routing is not the same thing as a human review decision.

## Decision

The only canonical stored review decision values are:

- accept
- needs_revision
- reject

Display labels may render these as "Accept", "Needs revision", and "Reject", but persisted records, audit events, API payloads, and analytics must use the canonical stored values.

`Escalated` is not a review decision value.

Every valid human decision appends one immutable `Review`. Every submitted
`ReviewFinding` and every later `FindingResolution` is immutable; later rounds
append history rather than updating it. An `accept` Review additionally creates
one internal immutable `FinalAcceptance`. Only that fact can source the
submitter `accepted_submission` ContributionRecord. `needs_revision` and
`reject` create no FinalAcceptance and no submitter contribution.

Offline calibration, suspected fraud, compensation holds, or registered
recovery may create separate evidence or audit records, but they do not replace
the reviewer decision contract. Authorization recovery never creates a review
decision. Adjudication is a future separately approved lifecycle and adds no
v0.1 decision or state.

Checker routing recommendations use a separate contract. The current selected
completion classifier emits `allow_review` or `needs_revision`; infrastructure
failure is `not_evaluated` and follows the separately authorized retry owner.
A checker cannot accept or reject work.

Retained contracts and historical evidence also use `checker_retry` and
`task_setup_blocked`. Their presence does not activate a selected production
outcome. The current classifier cannot emit `task_setup_blocked`; a
manager-visible setup-fault hold and repair workflow remain future safety work,
as recorded in the [capability ledger](roadmap_status.md).

`allow_review` must not be stored as `accept`. It is checker evidence of no
blocking issue, not a product decision or permission. TASK reads the exact
Submission-locked ReviewPolicy: true permits human admission; false invokes
the [same shared acceptance operation](spec_review_lifecycle.md#finalacceptance)
under its own exact authority after validating all required evidence. Only an
actual human Review stores an `accept` review decision. The false branch
creates FinalAcceptance and the submitter contribution without any Review,
ReviewLease or reviewer contribution. CHECKERS still cannot accept or reject
work. Runtime activation remains governed by the reviewed lifecycle authorization;
implemented behavior and hosted readiness are tracked separately in the
[capability ledger](roadmap_status.md).

Retained `task_setup_blocked` evidence must not be relabeled as `needs_revision`.
It denotes a problem with locked project setup, not contributor work. Future
manager hold/repair must preserve that distinction and exact locked lineage;
this decision does not authorize changing an already-submitted task's rules.

`needs_revision` can appear in both contracts, but the source must be explicit:

- checker-caused revision: `outcome_source = auto_checker`, `review_decision_id = null`
- human reviewer revision: `outcome_source = human_review`, `review_decision_id = <review decision id>`

Checker-caused remediation follows CheckerResult lineage and does not enter the
Review-rooted revision-preparation chain. Only the human-review case creates the
immutable Review, findings, reviewer contribution, and
`RevisionContextPreparation` episode defined by the active review contract.

## Consequences

Positive:

- task state transitions remain simple
- review analytics can compare decisions across projects
- human revision preparation has one Review-rooted entry point
- contribution logic can depend on immutable Review and FinalAcceptance facts
- automated checker routing cannot accidentally masquerade as human acceptance or rejection

Tradeoff:

- special handling must be modeled as workflow, audit, dispute, or registered
  recovery records instead of extra review decisions
- code and docs must name checker routing fields clearly so reviewers do not confuse them with review decision fields
