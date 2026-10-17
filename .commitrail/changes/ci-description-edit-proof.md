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
- Make the required `test` job of such a run mirror the newest other Backend
  run on the same head whose `scope` job executed, without waiting for that
  run's prerequisites.
- Grant the workflow `actions: read` for that lookup; update the workflow gate
  test and `docs/operations_backend_testing.md`.

### Not allowed

- Changing behavior for pushes, base retargets, reopen or draft-state events.
- Reporting success without an executed proof run for the same head.

## Design and decisions

Skipping the edit run outright was rejected: a skipped required check counts as
passing, so the newest `test` check run could hide an earlier failure. Mirroring
keeps the required check equal to the real proof. When no executed run exists
for the head, the mirror fails.

The first version waited up to 70 minutes for the proof run to complete. The
second hosted probe (below) showed that this fails on a busy day and holds one
of the organization's 20 concurrent job slots while it waits. The mirror now
reads the proof run's final check (`test` or `draft-test`) instead:

- If that check has completed, the mirror reports its result.
- If that check has not been created yet, the mirror fails at once. The proof
  creates its check later, after the mirror's own check, so the proof's result
  becomes the newest one and replaces the failure.
- If that check exists but has not completed, the mirror waits for that one
  short job, for at most 30 minutes.

Failing, rather than passing, while proof is unfinished means a cancelled proof
can leave a PR red but never green without proof.
A base retarget sets `github.event.changes.base`, so it keeps the shared group
and full proof.

The mirrored run must be bound to this PR number and base branch through the
run's `pull_requests` record, and only the check name this PR currently needs
(`test`, or `draft-test` while a draft) is accepted. Fork PR runs carry no
`pull_requests` binding, so fork PRs keep the previous rerun-on-edit behavior
rather than accept an unbound proof. Branch and job names reach `jq` as typed
arguments, not filter text.

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

An automated security review of the first version found that matching only the
head SHA could mirror a run from another PR or base, or accept `draft-test` for
a ready PR. Both are fixed by the PR/base binding and exact check-name rule.

The first hosted probe on #593 edited the description during proof: the
running proof was not cancelled, and both edit runs skipped every proof job
while their `test` jobs waited to mirror it.

The second hosted probe (head `5218ec8db`, 2026-10-16) edited the description
at 17:56 UTC while five other PRs saturated the runner limit. The proof run
38943336385 was not cancelled, but its `test` job did not start until 19:54.
Both edit runs timed out waiting and reported failure at 19:27 and 19:30; the
proof's passing `test` at 20:17 then became the PR's current check. This led
to the fail-fast rule above.

## Reconciliation

- Current-source reconciliation: based on `main` after #575 and #585.
- Next usable boundary: None.
- Remaining risks: after a description edit, the PR shows a failed `test`
  until the proof run's own `test` check completes. The replacement relies on
  GitHub using the newest check run of a given name; the 2026-10-16 probe
  showed the later passing check superseding two earlier failures.
