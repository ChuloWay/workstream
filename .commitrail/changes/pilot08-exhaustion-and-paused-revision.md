# [PILOT-08] Immediate exhaustion and governed revision windows

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Complete issue #495 with project-policy zero-revision support, immediate assignment exhaustion, automatic return to ready after exhaustion or timeout, explicit contributor/PM outcomes, and PostgreSQL-time pause/resume of setup-blocked revision windows.

## Intent

The revision limit belongs to the project's immutable RevisionPolicy. Each task
and Submission uses its locked policy version; no per-task revision-limit input
or override is authorized. The PM must explicitly supply a finite integer N >= 0.
An assignment permits initial Submission 0 and revisions 1 through N. Only a
committed Submission uses an attempt.

A fixable failure on the final allowed attempt exhausts that assignment in the
same transaction. It creates no next-revision preparation or deadline window.
Contributors and covered PMs see a terminal exhausted outcome, with no further
submission action for that assignment. Timeout is a separate terminal reason.

The failed Submission has a terminal rejection outcome and its assignment closes
on exhaustion or timeout; the task returns to ready in the same transaction.
Any otherwise eligible contributor may claim it, including a previous claimant.
A replacement assignment starts at round 0 under the task's locked project
RevisionPolicy. There is no cumulative contributor limit, new policy field,
platform limit, reclaim exclusion or PM hold for repeated failures. Retain the
original Submission bytes, findings and assignment outcome as immutable history.

When another revision is permitted, freeze the complete approved context at
failure and keep/rebase/block it atomically. A blocked setup context immediately
records durable PM attention visible in the covered task read and pauses the contributor's PostgreSQL-time allowance. Repair
resumes remaining time rather than starting a fresh window. A block at the
start preserves the full allowance. Duplicate events and repair/recovery cannot
add time. A later genuine failed Submission starts its own fresh policy window.

Infrastructure, provider and budget failures never spend a revision or start a
contributor revision window. They retain bounded durable recovery semantics.

## Bounded change

### Allowed files and owners

- PROJECTS RevisionPolicy input, approval/correction, semantic/hash custody,
  activation and public locked-policy contracts; the existing setup proposal
  and affected fixtures/contracts must carry required policy values explicitly.
- TASK canonical routing, revision preparation/repair/recovery/expiry, claim,
  assignment/submission lineage, repository guards, and authorized contributor/
  covered-PM reads. Extend existing owner operations and typed public ports.
- AUTH/AUDIT/OUTBOX contracts, bindings, deferred closure and registered handlers
  needed for the exact exhaustion/pause/release effects and PM-attention outbox/read custody.
- One forward migration chain after current main, ORM constraints/registration,
  schema fingerprint, preflight and retained-data upgrade proofs. Preserve old
  immutable policy/history bytes and identifiers; never invent PM authorization
  or rewrite retained policy values.
- Affected CLI/MCP public schema snapshots and existing displays required by the
  changed backend contract; coordinate with issue #499 rather than duplicating
  unrelated contributor UX work.
- Focused positive/negative real API/PostgreSQL/outbox/storage proofs, exact test
  ownership and its exact behavior-partition registration. Balance the new
  wall-clock proofs and the existing `test_revision_expiry.py` and
  `test_task_batch_transitions.py` modules within the five project lanes, using
  measured runtime. The retained-pause and pause-race modules may likewise move
  only among project lanes. To recover measured schema-lane headroom, move
  exactly the six pure static architecture/inventory modules
  `test_artifact_architecture.py`, `test_module_boundaries.py`,
  `test_authorization_boundary.py`, `test_test_structure_boundary.py`,
  `test_identifier_inventory.py`, and `test_record_id_collection.py` into the
  existing shared-foundation partition. Permit the existing manifest builder to
  use an explicit owner-tuple order only after validating the same exact unique
  lane membership, so the two retained historical cases distribute to separate
  measured lanes. `backend/scripts/run_test_lanes.py` may change only that
  membership validation and deterministic tuple selection; collection,
  execution, timeout, isolation, evidence, and cleanup behavior remain fixed.
  In `test_revision_clock_sql.py` and `test_revision_pause_races.py`, use one
  45-second fixture window for the four real PostgreSQL deadline waits after the
  staged transaction or named lock is observed. Keep the actual database sleep,
  deadline crossing, lock participants, rollback, and durable-state assertions.
  In `contributions/records/test_storage.py`, remove the module-wide schema-owner
  marker: its two DDL mutation paths explicitly roll back, while the ordinary
  fixture verifies the canonical schema and rebuilds plus fails if either leaks.
  Rebalance only retained-pause, revision-expiry, and task-batch nodes from the
  resulting complete phase evidence.
  Preserve every test node, all 13
  required lanes and existing timeouts; affected current
  specifications/runbooks/README and roadmap. Remove
  superseded cap-waits-for-expiry assertions and replace their real guarantees.

### Prohibited changes

- Contributor limits or failure-count PM holds, per-task revision-cap configuration,
  implicit/unlimited revision-policy values,
  migration recreation or rewriting retained evidence, compatibility aliases or
  parallel lifecycle writers, fabricated Reviews or economic outcomes.
- Human-review activation, model proxy or coding evaluator implementation,
  general contributor claim leases, CI optimization beyond the exact measured
  ownership changes above, the separate
  optional-criteria screening repair (#489), deployment or automatic merge.
- Weakened authority, mutable historical outcomes, skipped tests, increased CI
  timeouts, retry-until-green or unreviewed boundary exceptions.

## Acceptance criteria

- Explicit N=0 is accepted from public policy input through activation and SQL;
  omission/negative/unlimited values fail. Attempt 0 admits normally and its
  fixable failure exhausts immediately with no revision preparation/window.
- N=2 permits exactly attempts 0, 1, 2. Last-attempt failure exhausts immediately;
  retries and pre-submit failures never charge a round.
- Canonical task/assignment/Submission reads expose exhaustion, timeout, setup
  pause and eligible revision distinctly without cross-actor/project leakage.
- Exhaustion and timeout atomically reject the failed Submission outcome, close
  the assignment and return the task to ready. A fresh claim starts round 0,
  including a claim by the same eligible actor; concurrent claims create only
  one active assignment. No cumulative contributor cap or PM hold is introduced.
- Block/repair preserve exact remaining PostgreSQL time; stale expiry events,
  duplicate workers and service recovery cannot expire paused/newer work or
  extend its allowance. Original immutable source/preparation history survives.
- Real PostgreSQL intermediate waits cover both contenders/winners for
  submission/terminal failure/expiry, pause/repair and concurrent claim, with
  complete participant rollback, exact replay, revocation and foreign-resource
  denial. Notifications and unknown acknowledgements use durable outbox custody.
- Fresh and intermediate upgrades preserve rows, hashes and linear graph;
  direct SQL cannot evade the final invariants. Include retained policy values and
  pre-follow-up windows in migration/recovery proof.
- Run focused checks, applicable repository gates and full hosted CI. Record
  exact heads, commands, failures and cleanup; old counts do not qualify a new
  candidate. Hosted-broker deployment rehearsal remains issue #555.

## Risk and review routing

- Risk class: L0

High risk: project policy provenance, financial-context lineage, concurrency,
service authorization, immutable migration history and worker recovery.
Architecture/migration, security, QA/test-delta, documentation, and reuse reviews
must cover a frozen candidate and distinct unowned changes. Shared checks run
once; relevant reviewers inspect the resulting evidence. CI-integrity review is
required if workflow/evidence-selection behavior changes.

Human review focus: policy ownership, no invented retained-policy default,
immediate exhaustion without a phantom window, exact paused-time accounting,
automatic return to ready, terminal evidence and safe recovery.

## Evidence

The committed regressions cover zero/two-revision policies, immediate exhaustion,
reclaim, immutable history, real-participant rollback, direct-SQL denial,
concurrent terminal deliveries, paused-clock precision and retained-window
recovery. Existing task-detail transaction tests also protect caller-owned pending
writes from read-triggered autoflush. The test inventory and behavior ownership
partition include every new module without reducing required checks. Hosted runs
`38714469748` and `38719063430` showed broad schema-runner inflation rather than
a stable hung node: the latter completed all but the final 84-node evidence
module, which took 3.65 seconds in the passing predecessor. The six static
modules named in scope took 178.34 seconds in that predecessor and distribute
their exact nodes across the three existing shared-foundation lanes. The four
project modules named in scope may move only between project lanes to preserve
the unchanged execution time budget.

Hosted run `38725245210` completed project A/B/D in 1,117.857/1,136.996/
1,022.338 seconds. Project E completed all 506 tests in 1,175.11 seconds before
the unchanged 1,200-second runner deadline interrupted finalization; project C
reached 421/474 with no failure. Its exact 53-node tail cost 56.56 phase seconds
in the preceding complete artifact. Four new real-deadline calls consumed about
126, 126, and 248 seconds across A and C. The contribution-record storage module
spent 94.01 setup/teardown seconds across 13 completed A/B/D/E nodes because its
module marker rebuilt the full schema twice per node. The bounded fixture and
marker changes retain the same tests and proof boundaries while removing those
measured fixed costs. Exact hash replay then assigns the measured expiry loads
across A/E/C/B/D and task-batch loads across E/D/A/B/C; it does not select tests
from runtime timing or change the lane inventory.

Fresh migration capture validates every installed SQL/PLpgSQL function before
recording the schema fingerprint. PostgreSQL proofs exercise actual transactions,
lock waits, migrations and durable outbox handlers. CLI process tests exercise the
public response boundary. Hosted CI runs the complete required suite and retains
per-node completion and cleanup evidence. Exact tested heads, commands, failures,
review results and remaining execution limits are recorded in PR #573; a test
name or passing source inspection is not a runtime qualification.

## Reconciliation

- Current-source reconciliation: follows merged #569 and preserves main's 13-lane CI and immutable history. The user's final decision removes every contributor-count limit or repeated-failure PM hold.
- Next usable boundary: human review and merge of this complete follow-up; future human-review trigger integration remains #554 and hosted-broker rehearsal remains #555.
- Merge qualification requires retained-data, API, concurrency, independent review and full CI evidence for the final candidate. This record describes the intended merged behavior and does not authorize merge or deployment.
