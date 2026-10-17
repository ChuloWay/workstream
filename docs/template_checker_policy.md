# Post-Submit Checker Policy Template

## Project

`<project name>`

## Policy Version

`v1`

## Scope

This template governs durable internal checker runs after a submission is created, locked, and ready for the pre-review gate.

It does not define pre-submit intake. `PreSubmitCheckerPolicy` is generated from `EffectiveProjectSubmissionArtifactPolicy`.

## Design Boundaries

Revision closure, readiness, and lifecycle movement are lifecycle guards in v0.1. Do not add them as checker policy names unless they are present in the registered checker list.

## Required Project Checks

Select registered external POST images against the acceptance requirements in
this project's guide. Every approved POST binding is required; an empty approved
binding set is valid. Checker results are evidence for the authorized outcome
owner, not checker-owned acceptance or a human review decision.

| Requirement | Registry entry and digest | Configuration | Purpose |
| --- | --- | --- | --- |
| `<guide requirement ID>` | `<exact registered POST entry and digest>` | `<schema-valid configuration>` | `<what evidence this image supplies>` |

Task-local `acceptance_criteria` is optional and may be omitted or null. The
project guide must still define acceptance requirements. Do not select the removed
`check_acceptance_criteria_present` checker or treat missing optional task-local
text alone as a setup defect.

## Compiler Contract

The trusted compiler projects the exact approved external POST bindings into the
canonical `PostSubmitCheckerPolicy` body and hash. The body contains
`schema_version: external_post_submit_policy.v1`, ordered `entries` and
`policy_sha256`. Each binding identifies its requirement, POST stage, immutable
registry publication, configuration and configuration digest. Validation rejects
substituted identities, invalid configuration, wrong stages and stale hashes.

The removed built-in catalogue and its eight defaults are not executable policy
options. Stored predecessor bodies retain immutable provenance only; they do not
provide a runtime decoder or fallback execution path. See the current
[post-submit compiler contract](architecture_checker_framework.md#post-submit-compiler-boundary)
and [external registry contract](architecture_checker_framework.md#external-checker-registry-and-selected-policies).

## Pre-Submit Boundary

Pre-submit intake remains separate: Workstream defaults run first, followed by
approved external PRE images on ART-verified read-only files. A failed required
check returns bounded findings before Submission creation. The exact approved
PRE and POST policies are separately locked; a POST image cannot replace intake
custody or grant acceptance authority. See the
[current checker framework](architecture_checker_framework.md).

## Contributor-Visible Messages

Contributors may see:

- checker name
- status
- severity
- safe failure message
- suggested fix

Contributors must not see:

- hidden evaluator logic
- private reviewer notes
- confidential source metadata
- internal checker routing tokens such as `allow_review`, `checker_retry`, or
  `task_setup_blocked`
- post-submit checker policy provenance fields

## Recovery Contract

Blocking checker outcomes are not overridden into review readiness. Current
selected completed results are `allow_review` or `needs_revision`; infrastructure
failure is `not_evaluated` and may use the implemented authorized Operator retry.
The classifier cannot emit `task_setup_blocked`; manager-visible setup-fault hold
and repair remain future safety work. Existing Operator retry requires:

- actor
- matched grant and permission
- exact resource scope
- timestamp
- checker name
- reason
- evidence

Operator retry creates a new attempt and preserves every prior checker result. It cannot create a human review decision.

## Review Cadence

Review this checker policy weekly during the pilot.
