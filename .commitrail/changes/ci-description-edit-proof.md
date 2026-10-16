# ci-description-edit-proof — Stop PR description edits cancelling Backend proof

- Initiative: None
- Durable disposition: `Planned`
- Intended merge outcome: editing a PR title or description no longer cancels a
  running Backend proof, while a base-branch retarget still starts fresh proof.

## Intent

CI-EVT-002 subscribed Backend to `pull_request` `edited` events so that a base
retarget reruns proof against the new base. Title and description edits were
accepted as a conservative rerun cost. Combined with `cancel-in-progress`,
each edit also cancels the full run already in progress. On 2026-10-16 this
cancelled runs on #585 and three consecutive runs on #587 (head `ec7a7ea57`),
whose leftover jobs then appeared as failures.

## Current behavior

`.github/workflows/backend.yml` uses one concurrency group per PR with
`cancel-in-progress: true` and treats every `edited` event like a push.

## Bounded change

### Allowed

- Give title/description-only edits a run-specific concurrency group.
- Skip `scope`, and therefore all proof jobs, for those edits.
- Make the required `test` job of such a run wait for, and mirror, the newest
  other Backend run on the same head whose `scope` job executed.
- Grant the workflow `actions: read` for that lookup; update the workflow gate
  test and `docs/operations_backend_testing.md`.

### Not allowed

- Changing behavior for pushes, base retargets, reopen or draft-state events.
- Reporting success without an executed proof run for the same head.

## Design and decisions

Skipping the edit run outright was rejected: a skipped required check counts as
passing, so the newest `test` check run could hide an earlier failure. Mirroring
keeps the required check equal to the real proof. When no executed run exists
for the head, or it does not complete within the job timeout, the mirror fails.
A base retarget sets `github.event.changes.base`, so it keeps the shared group
and full proof.

## Acceptance criteria

- [x] Workflow gate test asserts the edit group, `actions: read`, the `scope`
      condition and the mirror step.
- [ ] A description edit on a PR leaves its running Backend proof uncancelled
      and its `test` check reports that proof's result.

## Risk and review routing

- Risk class: `L1` (required-check behavior).
- Required reviewers: CI integrity and the CI owner of #566.
- Human review focus: whether mirroring the newest executed run is the right
  proof rule for a description-only edit.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Workflow contract | `python3 -m unittest scripts.test_lightweight_agent_gates` | 29 passed | Hosted behavior proved on this PR |
| CI catalogue contracts | `pytest tests/test_ci_lane_catalogue.py tests/test_ci_test_lanes.py tests/test_ci_scope_selection.py` | 122 passed | None |
| Workflow syntax | `actionlint .github/workflows/backend.yml` | No new findings | None |

## Review findings

None yet.

## Reconciliation

- Current-source reconciliation: based on `main` after #575 and #585.
- Next usable boundary: None.
- Remaining risks: a mirror run occupies one runner while it waits.
