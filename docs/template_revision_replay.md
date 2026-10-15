# Human Review Revision Replay Template

> Planned human-Review response/resolution contract; genuine decision integration
> remains #554 work. Implemented checker remediation acknowledges its TASK
> preparation and requires no ReviewFinding response or FindingResolution.

## Episode

- task ID:
- originating `needs_revision` Review ID:
- prior Submission ID/version:
- source TaskAssignment ID:
- target TaskAssignment ID:
- assignment-local revision round/limit:
- original PostgreSQL requested-at/deadline:

Each assignment starts at round 0. Every committed `needs_revision` starts a
fresh window under the failed attempt's locked RevisionPolicy. Only a committed
immutable successor Submission ends it; upload, admission, repair and replay do
not. Cap exhaustion refuses a successor while preserving the current deadline.
At expiry, the intended shared policy retains immutable rejection evidence,
releases the assignment and returns TASK to `ready` without synthetic Review or
new economic facts. Human integration must use genuine Review provenance.

## Revision Context Preparation

| Field | Value |
|---|---|
| preparation ID | `<uuid>` |
| preparation sequence | `<integer>` |
| predecessor preparation ID | `<uuid or null>` |
| current head ID | `<uuid>` |
| context digest | `<sha256>` |
| outcome | `kept`, `rebased`, or `blocked` |
| direction | `forward`, `backward`, or `null` |
| prior guide ID/version/activation sequence | `<values>` |
| next guide ID/version/activation sequence | `<values>` |
| prior/next source, submission/checker, review, revision, and task-execution policies | `<bounded references>` |
| prior submitter ContributionPolicyVersion | `<uuid>` |
| next submitter ContributionPolicyVersion | `<uuid>` |
| change summary | `<contributor-visible summary>` |
| audit event ID | `<uuid>` |

The reviewer consumes the context stamped on the revised Submission and does
not perform a separate rebase. The completed reviewer contribution retains the
originating ReviewLease version. This preparation records the complete selected
next-attempt context and may atomically rebase the continuing Task and
TaskAssignment; the next Submission and ReviewLease use that exact version.

## Immutable Finding Responses

Every unresolved blocking finding requires one SubmissionFindingResponse.

| ReviewFinding ID | Kind | Required Change | Response Text | Finalized Evidence Binding ID |
|---|---|---|---|---|
| `<uuid>` | `blocking` or `advisory` | `<required change>` | `<what changed or bounded rebuttal>` | `<uuid or null>` |

## Later Immutable Resolutions

Completed by the later Review without editing the finding or response.

| ReviewFinding ID | Revised Submission ID | Result | Rationale | Evidence Binding ID |
|---|---|---|---|---|
| `<uuid>` | `<uuid>` | `resolved`, `unresolved`, or `not_applicable` | `<bounded rationale>` | `<uuid or null>` |

## Checker Readmission

- revised Submission ID/version:
- acknowledged preparation head/digest:
- current CheckerRun ID:
- routing outcome:
- preferred prior reviewer ID:
