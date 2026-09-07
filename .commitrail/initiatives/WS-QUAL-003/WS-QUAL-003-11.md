# WS-QUAL-003-11 — Replay proof consistency

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: realistic replay lookup proof and explicit retained-case rationale, without pausing independent product implementation.

## Intent

Correct permissive fixtures found by the follow-up audit. Test quantity and green
coverage are not evidence that each case earns its maintenance cost.

## Current behavior

Submission-policy repository fixtures return an existing operation from namespace
fallback while reporting that same operation missing. Five cases therefore pass
even if operation lookup is removed. Sufficiency tests manufacture disappearance
after an insert or conflict without a supported deletion/transaction boundary.

## Bounded change

### Allowed

- This record, `OVERVIEW.md`, and records `WS-QUAL-003-09.md` and `WS-QUAL-003-10.md`.
- `backend/tests/projects/submission_policy_mutations/test_repository.py`.
- A rationale table in this record covering the existing submission-policy family.
- `backend/tests/projects/sufficiency_mutations/test_replay_repository.py`.

### Not allowed

Production, schema, migration, CI, coverage-floor, public-interface, real
PostgreSQL-test or product implementation changes. No AUTH race repair here.
Do not edit the product worktree or make this cleanup its prerequisite.

## Design and decisions

Exact-operation fixtures resolve that operation and prohibit namespace fallback.
A separate different-operation/same-human-key conflict proves legitimate fallback
and exact selectors. Preserve existing SQL predicate proofs independently.
Remove the two unsupported disappearance simulations, not production guards.
Replace them with realistic same-actor/key pending and committed conflict
classification and changed-request rejection. The merged hosted coverage has
never entered this repository's conflict classifier (lines 94, 105, 106), while
covering the two impossible disappearance simulations. This is a distinct missing
behavior boundary, not a request to recover coverage through arbitrary faults.
Retain create/update identity and reservation-disposition matrices: these public
entry points have separate orchestration and error propagation, so each must
reject every listed substitution/state. Shared helpers alone do not establish
entry-point equivalence. Retain system/project scope crossed with both commands
because persisted action and grant provenance differ. Reject count-driven pruning.

## Acceptance criteria

- Exact pending/committed operation tests fail if operation lookup is bypassed.
- Changed operation facts deny without namespace fallback.
- A different operation in the same human namespace denies; fallback selectors
  and lookup order are exact, and insertion lookup is unused.
- Removing fallback is detected by that conflict test, not by fixture setup.
- Unsupported disappearance cases are removed with their proof limits recorded;
  real contention, rollback and completion guards remain tested and unchanged.
- Sufficiency conflict controls resolve the exact actor/action/key request and
  distinguish pending, committed and changed request digest without row insertion.
- Each retained submission-policy test has a rationale; parameter matrices name
  their distinct branches or deliberate interactions, without claiming all guards.
- Changed modules remain below 500 lines and tests below 120 lines.

## Risk and review routing

- Risk class: L1, bounded authorization-adjacent test evidence.
- Required reviewers: combined QA/test-delta; security for retained substitution
  rationale; documentation and CI-integrity for removal/coverage custody.
- Human review focus: meaningful proof, honest limits, no product pause.

## Evidence

Local: focused submission-policy and sufficiency repository tests, joint family
collection, Ruff, Commitrail validation, Markdown links, stale wording and diff
checks. Out-of-tree targeted mutations must distinguish missing operation lookup
and missing fallback. Hosted Backend owns full-suite PostgreSQL execution,
canonical node inventory, global coverage and unchanged per-file 90% floors.
Exact-head results belong in the PR, not as transient status in this record.

## Review findings

The prior audit exposed fixture inconsistency, not a demonstrated runtime defect.
Controlled SQL ports establish query composition and classification only; they
do not establish database isolation or exhaustive rejection of every custody field.

## Reconciliation

- Current-source reconciliation: based on merged PR375; product POL-04A2 owns
  separate files. Coordinate the shared overview wording only.
- Next usable boundary: separate AUTH race diagnosis; no automatic start.
- Remaining risks: most repository tests still require semantic audit. Existing
  transaction proof limitations in record 10 remain open.
