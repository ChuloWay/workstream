# [PILOT-08] — Complete controlled contributor revision

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Complete checker-driven contributor revision with assignment-scoped caps, fresh locked-policy PostgreSQL deadline windows, atomic complete-context rebase, contributor acknowledgement/change summaries, authorized repair and durable timeout rejection/release/reclaim, while preserving immutable history and the same intended policy for future genuine human Review integration.

## Intent

Each assignment starts at round 0. A policy allowing two revisions permits
rounds 1 and 2, for three submissions total on that assignment. Task-global
Submission versions remain consecutive. Infrastructure retries and exact replay
create no Submission and spend no round. Issue #495 records the cap decision.

Every committed contributor-fixable `needs_revision` starts a fresh window from
PostgreSQL time and the failed attempt's exact locked RevisionPolicy. Only a
committed immutable successor Submission ends that window. Upload, prechecks,
ready admission, duplicate delivery, repair and replay do not reset or end it.
At expiry, TASK retains immutable rejection evidence, releases the outstanding
assignment and returns the task to `ready`, atomically with AUTH/audit/outbox
custody and without new economic facts. Cap exhaustion refuses a successor but
leaves the outstanding deadline in force. New claimants receive round 0 and
their own allowance. This settled timeout policy supersedes earlier statements
that normal revision exhaustion requires manager cancellation.

## Delivery boundary

PR #569 delivers one complete PILOT-08 outcome through the existing TASK/ART/
CHECKERS/PROJECTS owners. The cap, rebase, acknowledgement, repair, expiry,
recovery and assignment-scoped accounting are one bounded change; separate
stage PRs are not the intended delivery.

The checker source is implemented through its exact routing manifest and
CheckerRun. Human decision integration remains #554 work. Its future genuine
Review trigger must consume the same intended revision policy with distinct
Review provenance; this PR does not claim human decision delivery or fabricate
Reviews, findings, reviewer contributions or human actors.

## Bounded change

### Allowed

- TASK public submission-context rules and canonical admission-backed creation,
  including assignment-scoped rounds, currentness, final-write capacity and
  exact committed replay.
- ART preparation, verified admission/evidence and public error mapping;
  CHECKERS attempt lineage constraints; affected retained records, INSERT-only
  guards, model registration and Alembic revisions 0040–0046. Historical facts
  retain immutable owner references instead of mutable TASK stamp references.
- TASK-owned immutable complete-context preparations, PROJECTS typed active/
  historical reads and composition adapters, atomic next-attempt TASK/assignment
  rebase, contributor-safe change summaries and exact intake acknowledgement.
- Exact covered-PM repair authority, typed resource facts, immutable repair
  chain/idempotency, audit closure and public project-scoped repair endpoint.
- TASK-owned expiry and retained-source recovery, exact fixed-service AUTH,
  PostgreSQL timestamps, immutable timeout receipts, task/assignment release,
  audit/outbox closure, recurring Celery scan and selected delivery registration.
- Shared OUTBOX immutable not-before custody, exact logical-key lookup,
  replay-safe scheduling and bounded retry only for the exact expiry event;
  existing delivery rules remain authoritative for other event types.
- Focused application, public API/CLI, SQL, migration-resume, rollback,
  lock-wait/concurrency, restart, recovery and replay regressions in existing
  fixtures and CI lane ownership. Migration initialization must safely resume
  after a commit-before-acknowledgement interruption.
- Reconcile affected MCP committed contract snapshots and access-read assertions
  with the changed canonical permission/action catalogues and resource digests;
  no new MCP tool or parallel lifecycle writer.
- Reconcile CLI context/preparation/history consumption and current README,
  lifecycle, queue, data model, policy, runbook, glossary, templates and roadmap.
- Narrow stale-review contract rules/regressions distinguishing permitted
  deadline rejection receipts from prohibited cap-only rejection or synthetic
  reject Reviews; register the regression in the existing lightweight
  `.github/workflows/agent-gates.yml` step without weakening unrelated gates.

- Remove the superseded planned cap/deadline manager-closure action, its contract,
  exclusive tests and current documentation. Retain historical migration/audit
  evidence; current audit reads use stored strings and need no compatibility alias.
- Extract affected ART/REV custody-documentation invariants from the oversized
  authorization test module into their domain test module, preserve exact assertion
  mappings, and shrink the existing structural-debt entry; no new exception or
  limit change.
- Add focused service-denial, stored-resource substitution, direct-SQL receipt
  custody and participant-failure rollback proofs for expiry and recovery.

### Not allowed

- Guide setup integration (#552), export pagination (#497), dependencies (#565)
  or unrelated CLI/MCP expansion.
- Human queue/lease/decision creation, general claim inactivity expiry,
  redundant counters, retained-data rewrites, compatibility paths, deployment
  or merge.

## Design and custody

Reuse TASK's existing authority and routing transaction. Apply one pure capacity
rule to verified exact locked-policy facts at preparation and canonical new
Submission creation. SQL enforces positive consecutive predecessor lineage and
assignment-scoped allowance using immutable policy custody. Exact committed
replay recovers stored identity through its existing replay path.

Preparation compares one complete approved active PROJECTS context with the
failed attempt's immutable context. All valid changed components rebase together
or the entire preparation is blocked. The immutable root freezes source, cap,
deadline and prior/target context. Authorized repair appends one successor to the
exact current head without changing history or the original window. Replays
never reselect the active guide. Contributor reads expose the frozen summary
and current PostgreSQL-time eligibility; intake/final creation bind the exact
head ID/digest and reject stale context.

Expiry uses TASK-first locks and fresh exact service authority, verifies the
outstanding source/assignment/window, appends `TaskRevisionExpiration`, marks
that assignment `revision_expired` with its release timestamp, clears the
assignee and returns TASK to `ready`. Its receipt, AUTH evidence, audit and
outbox publication intent commit together. Submission history projects rejection
from the immutable receipt without changing the stored Submission. Duplicate
workers, repaired heads, stale jobs and new claimants retain exact identity and
cannot branch, move a deadline or release someone else's assignment.

Recurring retained-source recovery schedules missing preparation/expiry intent
from the original manifest timestamp and locked policy. It may freeze an
unchanged context or blocked root, never authorize an automatic rebase. Exact
already-scheduled work is a no-op. Due OUTBOX intent survives worker downtime;
retry exhaustion or rejected authority remains observable rather than being
reported as successful expiry. A seven-day policy means 168 hours. No contributor
claim lease, timeout Review or contribution/award/fulfillment effect is added.

## Acceptance criteria

These criteria describe the complete intended outcome. Unchecked items require
final candidate evidence; source inspection or historical stage results do not
establish a current runtime pass.

- [ ] max=2 permits assignment-local initial0, revision1 and revision2; the next
  attempt receives `revision_limit_reached` before PRE/provider or durable
  creation effects. A new claimant receives their own allowance.
- [ ] Canonical final creation and direct SQL cannot bypass cap/currentness;
  exact committed replay remains successful and rollback preserves prior facts.
- [ ] Each committed fixable failure freezes one source-rooted preparation and
  original PostgreSQL-policy deadline. Only immutable resubmission ends it.
- [ ] Complete context is kept/rebased/blocked atomically; historical Submission,
  checker and review/economic evidence remains unchanged/readable after rebase.
- [ ] Contributor reads expose bounded changes/eligibility; intake and final
  creation require the exact prepared head/digest and reject stale heads.
- [ ] Authorized repair appends a non-branching successor; duplicate delivery,
  replay, races and restart cannot reset the window or select a new replay target.
- [ ] PostgreSQL-time expiry retains one immutable rejection receipt, releases
  the exact assignment and returns TASK to ready with atomic AUTH/audit/outbox
  closure and no synthetic Review or economic facts.
- [ ] Independent-session lock-wait tests cover expiry/resubmission, duplicate
  workers, repaired heads and stale jobs after reclaim; worker/API interruption,
  commit-before-acknowledgement, outbox failure and migration resume recover exact
  effects without partial state.
- [ ] Recurring retained-source discovery schedules the original window without
  rebase, handles missing roots/events and keeps denied/dead-letter work visible.
- [ ] Real public preparation/submission/context/history and CLI flows bind the
  acknowledgement and show timeout/reclaim outcomes; MCP snapshots match the
  canonical backend contracts without adding tools.
- [ ] Current docs agree on shared intended checker/human policy and accurately
  retain #554 human integration as future work; applicable focused and full
  hosted checks and required internal review support the final candidate.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture/reuse, security, QA/test delta, documentation.
- Human review focus: off-by-one assignment rounds, locked source policy,
  immutable context/history, exact replay, SQL enforcement, authorization and
  concealment, complete-context atomicity, timeout/reclaim custody and restart.

## Evidence

Earlier cap-stage evidence at `49ca2fbf8` is historical and limited to that
stage. It does not prove the expanded preparation, deadline, recovery or reclaim
outcome and does not establish the current candidate's checks. Final verification
must cover affected retained lineage, PostgreSQL lock waits and rollback,
registered durable workers, exact AUTH/audit/outbox closure, migration resume,
CLI public contracts and unchanged MCP catalogue consumers. Hosted full-suite
and realistic public durable-runtime evidence remain required.

Documentation reconciliation inspects the production TASK preparation/expiry/
recovery models and operations, public repair router, contributor context/history
projections, CLI flags and immutable outbox not-before custody. It claims document
consistency, not execution of runtime acceptance criteria. Current-source
reconciliation includes merged supported false activation and CLI submission
owners; checker remediation shares revision limits by the explicit product
decision. The settled policy above governs both checker and future genuine human triggers.


The repair verification includes four real PostgreSQL expiry/final-submission
and missing-root recovery cases at `10d2e01ad541656adfcf326aab2cff4751b531d0`
(4 passed), and four service-authority, stored-resource, direct-SQL custody and
participant-rollback cases at `c6e18927a0c98c6e1ae69a45da66a73a88dd5e97`
(4 passed). Both isolated runs exited successfully and confirmed isolated database/role
cleanup. Their runners did not provision or probe a MinIO provider. Those runs preceded the later expiry audit-reference ORM representation repair
and its notice comparison through the typed receipt snapshot; the incoming AUTH change extracts human
manager authority and orders guide reads. These are focused runtime proofs,
not an exact-final-head full-suite claim.

The race commands select
`test_due_expiry_and_ready_final_submission_wait_for_task_lock`, both parameters
of `test_final_submission_commit_boundary_serializes_expiry`, and
`test_concurrent_missing_root_recovery_commits_one_complete_effect` from the
submission-dispatch tests through `scripts/run_isolated_tests.py`. They observe
actual PostgreSQL waits, test both legal winners, and prove absent staged
submission/dispatch effects after a late commit. Security verification selects
`tests/tasks/submission_dispatch/test_revision_expiry_security.py`; authority
revocation is serialized by retained AUTH row locks, not an unsupported mutation
inside the transaction already holding those locks.

Migration verification covers nine graph, intermediate-resume and invalid-stamp
cases, including real upgrades from 0044 and 0045 to head. MCP verification
passes the actual backend-generated 82-permission catalogue through the adapter
and retains unknown-contract rejection. The CLI process checks pass for both
affected modules. The graph duplication, CLI formatting and docstring gate are
repaired without weakening checks. Current templates, lifecycle, compensation
ADR/specification and authorization custody documentation distinguish delivered
checker behavior from future genuine human-source integration. The retired
manager-closure action has no runtime alias; historical audit data remains intact.

Required hosted checks and independent review on the final PR head remain the
merge evidence. Local test counts alone do not establish full-suite completion.


Hosted run `38591662471` at `f918bbe1102c5ca22e26ff8b5fb6cd6cf1835ad8`
exposed affected integration fixtures still bypassing preparation acknowledgement,
stale projection/guard inventories, and mismatched ORM audit-reference UUID
representation. The repair keeps native PostgreSQL UUID storage, aligns the ORM
with AUDIT's string representation and compares typed notice snapshots. Tests
construct canonical revision contexts, retain exact denial/rollback assertions,
and upgrade historical schemas before running current runtime owners. The
identifier-generation inventory retains the same two transport-token owners
with their current expression fingerprints. This failed run is diagnostic
evidence, not merge approval; replacement focused proofs and full required CI
must pass on the repaired head.
