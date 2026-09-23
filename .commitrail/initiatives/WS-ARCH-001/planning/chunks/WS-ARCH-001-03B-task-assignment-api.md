# Chunk Contract: WS-ARCH-001-03B TASK Assignment API

Status: coordination contract after completed 03A and CP08. Risk: L1.
Outcome: bounded TASK metadata, queues, actor-specific projections and assignment
recovery through owner ports. Each implementation child supplies exact proof.

The bounded [project-grant repair](../../../../changes/task-project-grant-authorization.md)
already owns canonical contributor claim/start/work-context, separate management
work-context and system-Operator start authority. Reuse its command/port and
assignment transaction, not a second claim implementation. CP08 completes the contribution-policy attempt locks and minimal writers.
The [03B2 child](../../WS-ARCH-001-03B2.md) supplies hidden contributor-ready
queue facts and pagination, without live AUTH or HTTP exposure. The [03B8 child](../../WS-ARCH-001-03B8.md) completes hidden task audit evidence.
[03B9](../../WS-ARCH-001-03B9.md) completes hidden exact-assignment invalidation;
03C retains its real feature authority, producer wiring and registration. The
[03B3 child](../../WS-ARCH-001-03B3.md) delivers hidden all-state management
and status-only operational queue facts.
The [03B4 child](../../WS-ARCH-001-03B4.md) delivers hidden contributor and
management task detail; reuse its fixed projections and visibility facts.
The [03B5 child](../../WS-ARCH-001-03B5.md) replaces the already-authorized
contributor and manager work-context responses using those facts and exact
receipt-selected review/revision/ContributionPolicy identities.

The [03B6 child](../../WS-ARCH-001-03B6.md) supplies explicit management, operational
and audit locked-context projections through the existing historical resolver.
The retained management-capable HTTP route uses the same management implementation;
its token-role/creator authority remains a named 03C dependency. Operational/audit
reads stay internal.

The reconciled CP08 chunk owns contribution-policy fields and the minimal
existing screening/claim/Submission copy paths together after ARCH-03A. This
chunk consumes those complete frozen attempt facts; it must not reimplement the
writers or select current CON policy during ordinary claim. Preserve the
screening-time lock and existing authority/transaction ownership.

Allowed: dependency-gated assignment invalidation and
public facts, focused tests, composition adapters, deny-only route
declarations, boundary ledgers and current documentation. Not allowed: duplicate
lineage writers, project-policy evaluation, checker planning, ART custody, AUTH
decisions, compatibility paths, public cutover or human revision semantics.

Reuse delivered ready, management and operational queue facts, 03B4 detail and
03B5 work context; declare remaining
replacement task surfaces against hidden owner commands; ARCH-03C owns their exact activation and live route switch.
Do not leave an unowned route step between public ports and user-visible
behavior. The queue must filter project/visibility before counts and cursors.
Reuse the completed 03B6 locked-context field contracts and 03B8 bounded audit
evidence contract. The [03B7 child](../../WS-ARCH-001-03B7.md) supplies immutable contributor and management submission requirements using one historical translator; contributor visibility follows the shared TASK lock. The retained requirements route keeps its current authority wrapper. 03C supplies separate action/permission declarations;
03B3 supplies the management/operational queue facts; 03B8 supplies the covered Audit
task-evidence facts; their live authority remains 03C. Scope filtering precedes counts, cursors and
serialization; operational status never includes contributor-private detail.
For every one of these surfaces,
no projection selects a permission using a token role or leaks another
principal's fields. Preserve authorized PM reads when replacing old routes.

Preserve pre-submit authority invalidation: exact submitter-grant revocation
or actor/link suspension/deactivation closes claimed/in-progress assignments
as `authority_revoked`, returns the task to READY, clears `assigned_to` and
retains history. The operation verifies exact cause event, actor, grant/link,
project and role, is idempotent, and does not restore work on reactivation.
Another eligible submitter may then claim normally. Wrong-role events and
already-submitted/evaluation/review history cannot be rewritten. Downstream
needs-revision obligations and manager reassignment remain REV-owned work;
there is no new direct manager assignment feature here.

AUTH-OUTBOX-01, CON-02B and AUTH-OUTBOX-02 supply shared committed delivery
and dispatcher authority. 03B9 consumes the complete committed envelope and
holds the OUTBOX event/attempt fence through the hidden TASK effect transaction.
AUTH invalidation audit rows still are not dispatched events. Actor-wide
invalidation needs bounded per-project/per-assignment TASK fan-out; TASK and
REV effects cannot share an implicit acknowledgement. The hidden handler
requires its own feature authority port; real fixed-service authority and
production registration remain 03C.
03C must wire AUTH invalidation events durably in their originating transaction;
a response hint such as `auth13_assignment` is not a delivered reconciliation.

Reuse and extend `TaskSubmissionContextPort`, `TaskSubmissionContextFacts`, and
`SubmissionCreationCommand`. Do not introduce parallel assignment,
contributor, predecessor, locked-context, or Submission vocabulary unless a
reviewed current-main delta proves the existing public type cannot carry it.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

The completed CP08 screening/claim/Submission lineage and concurrency proofs
remain required regressions, not duplicate writers for this parent. For each
remaining child, verify focused unit/PostgreSQL and public composition tests,
boundary validators, Ruff and hosted coverage. Required reviews are selected
from the child's actual architecture, security, product/ops, QA, senior and
test-delta impact.

## Current bounded sequence

1. [ARCH-03B1](../../WS-ARCH-001-03B1.md): remove TaskService's private PROJECTS
   draft/display reads using the existing port and immutable exact-guide facts.
   Its public response shapes and authorization remain unchanged. The separate
   pre-submit context consumer is explicitly outside this metadata cutover.
2. 03B2/03B3 hidden queues, 03B4 detail, 03B5 work context, 03B6 locked context,
   03B7 requirements and [03B8 bounded audit evidence](../../WS-ARCH-001-03B8.md)
   are complete. Existing public audit/recovery readers remain required until
   their explicit 03C authority replacement.
3. [03B9](../../WS-ARCH-001-03B9.md) hidden assignment invalidation is complete.
   Next is ARCH-03C producer wiring, exact feature AUTH and public activation.
   No parallel worker or fabricated claim value substitutes for those dependencies.

## Merge state

- Outcome on merge: `planned`
