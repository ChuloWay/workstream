# [PILOT-08] Immediate exhaustion and governed revision windows

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Complete issue #495 with project-policy zero-revision support, immediate assignment exhaustion, a finite project-approved contributor allowance per task, explicit contributor/PM outcomes, and PostgreSQL-time pause/resume of setup-blocked revision windows.

## Intent and settled policy

The revision limit belongs to the project's immutable RevisionPolicy. Each task
and Submission uses its locked policy version; no per-task revision-limit input
or override is authorized. The PM must explicitly supply a finite integer N >= 0.
An assignment permits initial Submission 0 and revisions 1 through N. Only a
committed Submission uses an attempt.

A fixable failure on the final allowed attempt exhausts that assignment in the
same transaction. It creates no next-revision preparation or deadline window.
Contributors and covered PMs see a terminal exhausted outcome, with no further
submission action for that assignment. Timeout is a separate terminal reason.

The task returns to ready after exhaustion/timeout only within a required finite
PM-approved contributor allowance. Its usage is cumulative across failed or
timed-out assignments and cannot reset through reclaim. At its allowance the
task is held for PM action and a durable notification is recorded. A replacement
assignment starts its own round 0. Policy configuration and usage are distinct;
task-local usage does not create a task-local revision policy.

When another revision is permitted, freeze the complete approved context at
failure and keep/rebase/block it atomically. A blocked setup context immediately
notifies the PM and pauses the contributor's PostgreSQL-time allowance. Repair
resumes remaining time rather than starting a fresh window. A block at the
start preserves the full allowance. Duplicate events and repair/recovery cannot
add time. A later genuine failed Submission starts its own fresh policy window.

Infrastructure, provider and budget failures never spend a revision or start a
contributor revision window. They retain bounded durable recovery semantics.

## Bounded implementation

### Allowed files and owners

- PROJECTS RevisionPolicy input, approval/correction, semantic/hash custody,
  activation and public locked-policy contracts; the existing setup proposal
  and affected fixtures/contracts must carry required policy values explicitly.
- TASK canonical routing, revision preparation/repair/recovery/expiry, claim,
  assignment/submission lineage, repository guards, and authorized contributor/
  covered-PM reads. Extend existing owner operations and typed public ports.
- AUTH/AUDIT/OUTBOX contracts, bindings, deferred closure and registered handlers
  needed for the exact exhaustion/pause/hold effects and PM notification custody.
- One forward migration chain after current main, ORM constraints/registration,
  schema fingerprint, preflight and retained-data upgrade proofs. Preserve old
  immutable policy/history bytes and identifiers; never invent PM authorization
  or a default allowance for retained policy versions lacking new configuration.
- Affected CLI/MCP public schema snapshots and existing displays required by the
  changed backend contract; coordinate with issue #499 rather than duplicating
  unrelated contributor UX work.
- Focused positive/negative real API/PostgreSQL/outbox/storage proofs, exact test
  ownership, affected current specifications/runbooks/README and roadmap. Remove
  superseded cap-waits-for-expiry assertions and replace their real guarantees.

### Prohibited changes

- Per-task revision-cap configuration, implicit/unlimited PM policy values,
  migration recreation or rewriting retained evidence, compatibility aliases or
  parallel lifecycle writers, fabricated Reviews or economic outcomes.
- Human-review activation, model proxy or coding evaluator implementation,
  general contributor claim leases, unrelated CI optimization, the separate
  optional-criteria screening repair (#489), deployment or automatic merge.
- Weakened authority, mutable historical outcomes, skipped tests, increased CI
  timeouts, retry-until-green or unreviewed boundary exceptions.

## Acceptance and verification

- Explicit N=0 is accepted from public policy input through activation and SQL;
  omission/negative/unlimited values fail. Attempt 0 admits normally and its
  fixable failure exhausts immediately with no revision preparation/window.
- N=2 permits exactly attempts 0, 1, 2. Last-attempt failure exhausts immediately;
  retries and pre-submit failures never charge a round.
- Canonical task/assignment/Submission reads expose exhaustion, timeout, setup
  pause and eligible revision distinctly without cross-actor/project leakage.
- Required contributor allowance is policy-owned, cumulative and race-safe;
  claim/reclaim cannot bypass it. Boundary failure holds the task and notifies
  the PM with one source-bound durable effect.
- Block/repair preserve exact remaining PostgreSQL time; stale expiry events,
  duplicate workers and service recovery cannot expire paused/newer work or
  extend its allowance. Original immutable source/preparation history survives.
- Real PostgreSQL intermediate waits cover both contenders/winners for
  submission/terminal failure/expiry, pause/repair and concurrent claim, with
  complete participant rollback, exact replay, revocation and foreign-resource
  denial. Notifications and unknown acknowledgements use durable outbox custody.
- Fresh and intermediate upgrades preserve rows, hashes and linear graph;
  direct SQL cannot evade the final invariants. Include missing newly-required
  configuration and retained pre-follow-up windows in migration/recovery proof.
- Run focused checks, applicable repository gates and full hosted CI. Record
  exact heads, commands, failures and cleanup; old counts do not qualify a new
  candidate. Hosted-broker deployment rehearsal remains issue #555.

## Risk and review

High risk: project policy provenance, financial-context lineage, concurrency,
service authorization, immutable migration history and worker recovery.
Architecture/migration, security, QA/test-delta, documentation, and reuse reviews
must cover a frozen candidate and distinct unowned changes. Shared checks run
once; relevant reviewers inspect the resulting evidence. CI-integrity review is
required if workflow/evidence-selection behavior changes.

Human review focus: policy ownership, no invented retained-policy default,
immediate exhaustion without a phantom window, exact paused-time accounting,
task contributor allowance boundaries, terminal evidence and safe recovery.
