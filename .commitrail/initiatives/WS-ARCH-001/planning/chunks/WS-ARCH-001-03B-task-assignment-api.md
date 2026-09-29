# Chunk Contract: WS-ARCH-001-03B TASK Assignment API

Durable disposition: Complete. Risk: L1.

This completed coordination contract covers TASK metadata, queues, actor-specific
projections and assignment recovery through owner ports. Its implementation
children are complete; it is not a skeleton or an instruction to restart work.
The subsequent ARCH-03C children delivered exact authority and public TASK
exposure through 03C7. AUTH-18 delivers public manager guide activation/context;
hidden approved-guide intake is delivered by ARCH-03D. ARCH-04B hidden exact
post-submit input is delivered; ARCH-04B2 output custody is next in the
[current dependency contract](../PLAN.md#current-dependency-contract).

## Delivered boundaries

- [ARCH-03B1](../../WS-ARCH-001-03B1.md) replaces TaskService's private PROJECTS
  draft/display reads with the existing port and immutable exact-guide facts.
- [03B2](../../WS-ARCH-001-03B2.md) and
  [03B3](../../WS-ARCH-001-03B3.md) provide contributor-ready, management and
  operational queues. [03B4](../../WS-ARCH-001-03B4.md) provides contributor and
  management detail; [03B5](../../WS-ARCH-001-03B5.md) provides work context with
  exact receipt-selected review/revision/ContributionPolicy identities.
- [03B6](../../WS-ARCH-001-03B6.md) provides distinct management, operational and
  audit locked-context projections through one historical resolver.
  [03B7](../../WS-ARCH-001-03B7.md) provides immutable submission requirements;
  [03B8](../../WS-ARCH-001-03B8.md) provides bounded task audit evidence.
- [03B9](../../WS-ARCH-001-03B9.md) provides exact-assignment invalidation.
  [03C1](../../WS-ARCH-001-03C1.md) supplies its fixed-service authority and
  [03C2](../../WS-ARCH-001-03C2.md) supplies atomic originating publication and
  registered delivery with enforced prefork topology.
- [03C3](../../WS-ARCH-001-03C3.md) supplies manager task create/screen/release
  authority. Public queues, detail/requirements, locked contexts and audit history
  are delivered by [03C4](../../WS-ARCH-001-03C4.md),
  [03C5](../../WS-ARCH-001-03C5.md), [03C6](../../WS-ARCH-001-03C6.md) and
  [03C7](../../WS-ARCH-001-03C7.md), respectively. Their exact authority replaces
  the former token-role/creator wrappers; operational/audit reads are publicly
  exposed only through their separately authorized projections.

The [project-grant repair](../../../../changes/task-project-grant-authorization.md)
owns canonical contributor claim/start/work-context, separate management work
context and system-Operator start authority. CP08 delivered the frozen
contribution-policy attempt fields and minimal screening/claim/Submission writers
after ARCH-03A. These remain the shared owners, not additional work for this parent.

## Preserved owner and safety contracts

Reuse the existing command ports and assignment transaction. Do not duplicate
lineage writers, select today's CON policy during ordinary claim, or introduce
parallel assignment, contributor, predecessor, locked-context or Submission
vocabulary. Preserve the screening-time lock and caller-owned transactions.
`TaskSubmissionContextPort`, `TaskSubmissionContextFacts` and
`SubmissionCreationCommand` remain the typed boundaries for their consumers.

Scope and visibility filtering precede queue counts, cursors and serialization.
Operational status excludes contributor-private detail. Projections never choose
a permission from token roles or disclose another principal's fields. Preserve
exact-authorized Project Manager reads and distinct operational/audit authority.

Pre-submit authority invalidation closes only the exact claimed/in-progress
assignment affected by submitter-grant revocation or actor/link
suspension/deactivation, records `authority_revoked`, returns the task to READY,
clears `assigned_to` and retains history. It verifies the committed cause event,
actor, grant/link, project and role, is idempotent, and does not restore work on
reactivation. Another eligible submitter may claim normally. Wrong-role events,
replacement assignments and submitted/evaluation/review history cannot be rewritten.

The shared AUTH-OUTBOX/CON dispatcher owns delivery. TASK consumes the committed
envelope and holds its event/attempt fence through the effect transaction; AUTH
invalidation audit rows alone are not dispatched events. Originating publication
uses bounded per-project/per-assignment fan-out. TASK and REV effects cannot
share an implicit acknowledgement. No parallel worker, fabricated claim value,
or response hint substitutes for committed delivery custody.

## Remaining work and verification

No implementation remains under this parent. Approved-guide intake uses its own
bounded contract and the delivered ports; public admitted Submission and durable
post-submit execution remain separate. TASK public exposure does not imply those
surfaces are live. Human revision obligations and manager reassignment remain
REV-owned; this contract adds no direct manager assignment feature.

Retain the completed CP08 lineage/concurrency regressions and the 03B/03C
isolation, authority, rollback, delivery and public-composition proof. Child change
records preserve their implementation evidence; they are not an active-work queue.
Future changes use current owner contracts and impact-selected reviews rather
than reopening this completed parent.
