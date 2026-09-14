# Retry-safe semantic-lane evidence selection

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: partial CI retries select each lane's latest attempt without losing earlier successful lanes or weakening evidence validation.

## Intent and current behavior

Backend artifacts currently reuse one SHA/lane name across attempts. In run
34881720409 the older incomplete schema artifact had a higher artifact ID than
the successful retry. Name-based download selected that incomplete bundle and
the existing merger correctly rejected it. Contributors should not need an
empty commit and full rerun to recover from that selection error.

## Bounded change

Allowed: `.github/workflows/backend.yml`, the existing
`backend/scripts/merge_test_lane_evidence.py`, its tests and workflow inventory
tests, this record and relevant CI documentation. No product code, dependencies,
new permissions, test exclusions, coverage floors or evidence-guard weakening.

## Design

Name lane and aggregate artifacts with the GitHub run attempt. Download all
matching lane attempts from this run into separate artifact directories; never
merge their files. The existing merger selects the greatest numeric attempt per
lane (bounded by the current attempt and exact SHA), then validates that bundle.
Reuse a prior lane only when it has no newer artifact. A latest incomplete or
corrupt bundle fails closed, never falls back. Record selected attempts for
diagnostics and use the selected bundles for timing too.

Rejected: artifact-ID ordering (observably not chronological), overwriting or
deleting diagnostic artifacts, all-lane reruns, and scanning for any passing
older bundle. No compatibility path for old artifact names is introduced;
existing runs retain their original workflow definition.

## Acceptance and proof

- Partial retry replaces only rerun lanes; aggregate-only retry reuses lanes.
- Numeric attempt 10 beats 9 regardless of ID/list/directory order.
- Missing/foreign/malformed/future attempts, symlinks and wrong SHA reject.
- Latest failed/incomplete/corrupt evidence rejects despite an older pass.
- Existing manifest, digest, node completeness, isolation and coverage checks
  remain blocking; selected lane timing follows the same selection.
- Focused merger and workflow inventory tests, negative-control regression,
  hosted full Backend, link/stale and Commitrail checks. Replay real failed-run
  artifact metadata to demonstrate why ID ordering is invalid.

## Risk and review

L1 CI change. Plan review first; CI-integrity and QA/test-delta review the frozen
implementation, including evidence selection and fail-closed behavior. Human
focus: safe reuse across partial retries without hiding new failures.

## Reconciliation

Product roadmap impact: none; no product capability, exposure or dependency
changes. GitHub retains check/approval authority. This does not repair external
registry outages or claim a CI runtime target has been met.

Plan review required canonical positive attempt names (no leading-zero aliases),
the same strict selector for timing and evidence, and no fallback from invalid
newest bundles. All are implemented. Measured Backend wall time on a retry is
retry-inclusive: it starts at the earliest selected lane, including any wait
between attempts; it is not fresh-run execution latency.
