# WS-AUTH-001 — Current pre-review activation plan

The [cross-owner dependency contract](../../WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
owns current delivery order through `allow_review`. The
[preserved plan](../pre-cutover/PLAN.md) retains completed history; its broad
AUTH-13/14 cutovers are not additional implementation work.

- AUTH-12I/12J/12B2 are complete. POL-04B consumes their exact adapters.
- [AUTH-12F4](chunks/WS-AUTH-001-12F4-submission-policy-approval.md) follows
  hidden POL-05A approval/provenance and precedes POL-05B.
- [AUTH-12G](chunks/WS-AUTH-001-12G-post-submit-checker-policy-mutations.md)
  is delivered by the [combined record](../WS-AUTH-001-12G.md), following hidden
  POL-06A post-policy operations. POL-06B public wiring and POL-07B internal
  phase composition are delivered.
- [AUTH-12H](../WS-AUTH-001-12H.md) delivers exact-project manager authority after
  completed POL-07B phase composition, CP06 validation and CP07 guide binding.
  ARCH-03A internal guide context, CP08 lineage/minimal writers, ARCH-03B1
  historical reads, ARCH-03B2/03B3 hidden queue facts and ARCH-03B4 hidden
  contributor/management detail are delivered. ARCH-03B5 replaces the existing
  authorized work-context responses with distinct current task facts and exact
  locked policy references.
  ARCH-03B projections through 03B8 are complete. Hidden exact assignment
  invalidation is delivered by 03B9; ARCH-03C1 exact feature authority is complete.
  ARCH-03C2 atomic originating producer wiring and first registration come next;
  public TASK activation remains separately bounded.
- CP05 owns exact ContributionPolicy-action activation after merged CP04B.
- CP08 delivered the minimal lineage writers. ARCH-03B8 hidden task audit
  evidence and 03B9 hidden assignment invalidation are complete. ARCH-03C owns
  public TASK activation after completed 03C1 exact feature authority and
  planned 03C2 originating-transaction event production/registration.
  [AUTH-13 is superseded](chunks/WS-AUTH-001-13-task-assignment-cutover.md).
- ARCH-04D alone activates post-submit materialization/output and CHECKERS
  execution/finalization after ARCH-04B/04B2/04C; historical AUTH-14 and XINT-06B
  cannot start in parallel. ARCH-03B/03C explicitly own task queue/read and
  pre-submit invalidation; downstream REV queue/reconciliation remains separate.

For 12F4/12G, use their current child contracts rather than the old storage model;
the current POL-05A/06A operations determine authoritative resource facts,
replay identity and separate downstream storage. AUTH consumes public facts,
never creates policy storage or mutates a finalized setup row. Each mutation
binds actor/link/grant or exact fixed service, project, operation/correlation,
compilation/component/approval identities, session and transaction. Test
cross-project, stale generation, substituted action/resource, revoked authority,
concurrent replay and rollback before activating the live adapter.

The bounded [task project-grant repair](../../../changes/task-project-grant-authorization.md)
replaces contributor claim/start/work-context authority, adds separate management
context and reasoned system-Operator start, and removes self-activated eligibility
and public JSON-packet Submission creation. Admission-backed creation stays hidden.
ARCH-03B/03C must reuse these exact actions and command owners while completing
public access/authority cutover and live wiring for delivered hidden invalidation; CP08
already delivered ContributionPolicyVersion lineage. Do not restore eligibility
or register replacement aliases.

## WS-AUTH-001-OUTBOX-01 — unavailable dispatcher contract

Disposition: Complete. [Contract and proof](../WS-AUTH-001-OUTBOX01.md).
The closed catalogue registers planned `outbox.dispatch` solely for fixed
`workstream.outbox.dispatcher`. Migration 0026 admits this identity without
provisioning it or enabling execution. The canonical ACTORS public vocabulary
replaces the removed transitional import module in all affected callers.

Pure facts bind the exact event/project, payload digest, generation, worker owner,
UTC lease and claim/invoke/finalize phase. Finalize additionally binds the exact
OUTBOX-owned outcome digest. The nominal preparation/consume interface uses the
existing public decision type and rejects handle copying/serialization. It has
a live implementation delivered by OUTBOX-02. CON-02B supplies persisted
claim/lease/recovery mechanics; OUTBOX-02 supplies fresh authority and exact facts/session/root-transaction checks
for each phase. No handle survives commit, lease wait or handler/provider I/O.
The existing protected permission catalogue exposes metadata only; no human role
or effective action gains dispatcher authority.

## WS-AUTH-001-OUTBOX-02 — exact dispatcher activation

Disposition: Complete. [Contract and proof](../WS-AUTH-001-OUTBOX02.md).
The exact hidden CON-02B mechanics now use fixed-dispatcher authority,
phase/resource/actor/project matching, immutable decision bindings and bounded
prefork workers. Unprovable existing attempts are refused, with no fictional
backfill or retained-data deletion. Production feature registration remains
empty: each handler needs its own authorization. ARCH-03B9 supplies hidden
assignment invalidation; ARCH-03C1 completes its real feature authority.
ARCH-03C2 next owns atomic originating-transaction-only producer wiring and
first registration with enforced prefork topology. Never backfill or dispatch retained
invalidation rows whose transaction-start timestamps do not prove mutation chronology.
Missing dispatcher provisioning denies work, not startup or provisioning access.

Both boundaries require focused architecture/security/QA review and affected
CI/docs review. Human focus: a dispatcher can deliver a request but cannot
authorize its product effect. These current contracts replace no product
owner and create no new planning-permission gate.

## TASK post-submit acceptance custody

ARCH-04E2 owns the proposed `task.post_submit.route` contract for the fixed
`workstream.task.post_submit_router`. Its false/pass consequence reuses the
[shared acceptance sequence](../../../../docs/spec_review_lifecycle.md#finalacceptance),
not a new FinalAcceptance or CON materialization action. The typed resource
binds the exact committed claim, immutable Submission, current checker
run/generation/result and outputs, locked false ReviewPolicy, assignment and
contribution-policy lineage, and intended derived effects. Consume fresh
transaction-bound authority; checker/dispatcher allows cannot substitute.
Acceptance must satisfy the canonical false-readiness contract above, including
rejection of any applicable approved `human_review` requirement disposition.
CP07/12H enforce ARCH-04F remediation availability and valid scoped controller
generation as activation prerequisites, not additional route-resource facts;
runtime still consumes the shared lifecycle fence required by that contract.
True permits human admission only. Activation of the false consequence waits
for the hidden REV/CON/TASK atomicity and terminal-currentness proofs; the
service never receives human `review.decision` or generic contribution access.
