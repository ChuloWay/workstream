# WS-ARCH-001-CP08 — Bind initial work attempts to the approved contribution policy

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: Screening stamps the exact activated contribution-policy version; claim and Submission copy it with relational and immutable-evidence safeguards.

## Intent

Complete the approved ARCH-03A -> CP08 sequence. A policy reference is useful only
when the existing writers supply it atomically. This change joins the schema and
minimal screening/assignment/Submission writers; no schema-only half-cutover.

## Current behavior

Main `7bc76ede` includes ARCH-03A's complete active/frozen PROJECTS context, including
receipt-bound review/revision semantics. Migration head is
`0023_guide_activation_custody`. `TaskService` still discovers private PROJECTS
policy rows and requires the superseded PaymentPolicy. `AuthorizedTaskCommands`
uses that private context for claim/start/work-context. Hidden
`TaskSubmissionCreationService` also calls it before preparing final authority.
The Task/Assignment/Submission models have no contribution-policy version stamp.
The Submission builder currently delays its already-known assignment identity
until ART supplies bundle linkage. CP08 separates required TASK assignment
lineage from the three ART references staged in that same transaction.

## Bounded change

### Allowed

- `backend/app/modules/tasks/{models,repository,service,authorized_commands,submission_composition,schemas,router}.py` and `api/{submission_context,submission_command}.py`: exact policy stamps, canonical copies, context cutover and directly affected response fields.
- `backend/app/modules/tasks/policy_context.py` only if separating the existing context/readiness logic removes service coupling; no second context implementation.
- `backend/app/adapters/tasks/__init__.py`, existing API dependency/composition roots and exact existing Submission composition callers: inject PROJECTS and CHECKERS ports with required dependencies, no fallback constructors.
- `backend/app/modules/projects/models.py`: unique guide/project/selected-version key for the exact TASK foreign key.
- `backend/app/modules/checkers/models.py`: nullable retained payment-version field, so remaining downstream packet prerequisites do not require invented payment versions. This does not claim canonical hidden Submission-to-CheckerRun integration.
- `backend/app/modules/authorization/{submission_consumption,submission_creation_authorization}.py`: bind the exact attempt contribution version into existing prepared/final Submission authority; no new action or permission.
- One `0024` Alembic revision: same-project/stable-identity constraints, immutable policy stamps, retained-data validation and justified derivation/refusal. Update `backend/alembic/env.py` current-head acceptance and exact migration-graph tests. No prior migration or frozen baseline edits: baseline parity is checked at revision 0001, not head.
- Existing affected TASK/ART/AUTH public-value constructors and test fixtures: populate required exact fields from actual activated guides and assignments. Remove tests solely protecting superseded payment-policy readiness; preserve authorization, real-ZIP, recovery, rollback, immutable-history and concurrency assertions.
- Focused `backend/tests/tasks/` lineage/migration tests and existing task, Submission composition, authorization/task-authority, artifact and policy-context tests. Exact ownership/lane/debt registrations only when needed, no gate relaxation.
- This record, adopted CP08 contract, initiative navigation, README and affected canonical data-model/operations/roadmap sections. Update ignored sheet exports if present.

### Not allowed

No new public operation, contribution-policy selector at claim/Submission,
checker execution/provider call, automated acceptance, compensation fulfillment,
revision operation, compatibility branch, retained-data deletion or fabricated
policy lineage. CP09 owns remaining physical economic-schema removal once its
remaining consumers are removed. ARCH-03B/03C own broader task read/queue and
authorization cutovers; this change preserves existing authority boundaries.

## Design and decisions

1. Add required lineage to non-draft tasks, assignments and Submissions:
   `WorkstreamTask.locked_contribution_policy_version_id`,
   `TaskAssignment.submitter_contribution_policy_version_id`, and
   `Submission.contribution_policy_version_id`. Bind project/Task/assignment/
   contributor identity with stable composite keys. Task requires a guide version
   whenever its contribution stamp is populated, and binds `(project_id,
   locked_guide_version,locked_contribution_policy_version_id)` to the selected
   guide triple. CP08 permits the initial null-to-exact Task stamp only during
   draft-to-screening and rejects later Task stamp changes. Future authorized
   complete-context rebase must replace that guard together with the Assignment
   guard. A direct-SQL valid-successor substitution test proves this boundary.
   Assignment carries its owning `project_id`, bound to Task and
   ContributionPolicyVersion, and freezes Task/project/contributor identity.
   Insert-time assignment equality verifies the then-current Task stamp.
   Submission requires assignment identity and its copied contribution stamp at
   construction, with a stable assignment/task/contributor FK. An INSERT guard
   locks the assignment and compares the exact stamp immediately. There is no
   permanent FK to the assignment's mutable future policy value. Assignment ID,
   Task/contributor identity and the copied Submission stamp are immutable.
   The existing artifact shape check covers only the three ART-owned references:
   all-null while staged, or all-present. The hidden production service must
   consume ART and fill all three in its root transaction before returning;
   CP08 does not introduce a database-wide ART-completeness claim ahead of its
   later materialization owner. CP08 rejects assignment stamp changes; a future
   authorized rebase replaces the Task and Assignment guards together. Closed
   assignments cannot be restamped.
2. Screening resolves complete active PROJECTS facts in the same transaction,
   verifies installed pre-submit planning and post-submit catalogue capability,
   then stamps the receipt-selected policy identity and existing exact locks.
   Ready verifies the frozen context and both installed plans before writes.
   Historical reads do not rerun availability or use current CON selection.
3. Claim copies the already frozen Task policy to the new assignment. Hidden
   Submission creation copies the exact active assignment stamp, not the latest
   guide or CON policy. Public immutable TASK facts include these identities and
   reject inconsistent assignment/task references and require UUID policy identities. Add the task stamp to `LOCKED_CONTEXT_REQUIRED_FIELDS`, so the existing claim authorization digest binds it. PROJECTS activation receipt contribution identity must equal the task stamp on claim and both task/assignment stamps on Submission.
4. Replace the affected private policy/payment loading and stamping paths with
   the existing PROJECTS port. Existing project/guide display metadata reads may
   remain as an explicitly identified ARCH-03B dependency; they cannot select or
   authorize policies. Remove obsolete payment-policy readiness and the payment
   section from the affected work-context/locked-context projections. Retain
   stored economic evidence needed by separately scoped downstream consumers.
   `Submission.locked_payment_policy_version` and the directly consuming
   `CheckerRun.locked_payment_policy_version` become nullable (Task already is);
   retain existing values and MATCH SIMPLE foreign keys for the CP09 cutover.
   Never fabricate a payment version for new unified-guide work.
   Remaining CHECKERS/REV packet fields and their test-only stored prerequisites
   are an explicit ARCH-04B/04C dependency. Their canonical materialization does
   not exist yet and cannot move before CP08/03C without creating a sequence
   cycle. Downstream fixture rows copy exact assignment/CON custody, keep ART
   references absent and prove only their downstream owner's existing behavior.
   They never call themselves admission/creation proof, patch canonical hidden
   submissions afterward, or promote caller package hashes into verified facts.
   Production-writer proofs separately use real ART admission and require all
   three resulting references. No production alternate writer is added.
5. Inject dependencies through existing composition roots. One TASK context
   operation serves its existing triggers; no ad hoc factory or second parser.
6. Preserve Task/assignment -> AUTH actor/control -> Project -> Attempt -> Request
   -> Guide lock ordering wherever those owners participate. In hidden Submission
   creation prepare final authority before taking PROJECTS locks; all preparation,
   validation, insertion, ART linkage and authority consumption remain inside the
   existing root transaction. Start the prepared-handle `try/finally` before the
   PROJECTS call, so any custody failure closes it. TASK public facts carry exact
   task and assignment policy IDs with equality validation; AUTH resource facts
   retain the assignment contribution version in their digest. Claim locks Task then active assignment, prepares/consumes AUTH, then reads PROJECTS frozen context. Submission locks Task, assignment and latest Submission before AUTH preparation, then PROJECTS, insertion, ART consumption and final AUTH consumption. Existing role issuance takes actor/grant locks before Project and never TASK; this ordering avoids introducing Project-to-actor inversions.
7. Before any upgrade DDL, refuse if any Task has `status <> 'draft'`,
   any TaskAssignment exists, or any Submission exists. There is no defensible
   historical contribution stamp in prior screening audit; do not reconstruct it.
   Preserve draft tasks and all guide/policy/activation/audit evidence unchanged.
   On refusal, schema, rows and Alembic marker must remain unchanged. Downgrade
   likewise refuses before DDL if any Task stamp, Assignment or Submission exists;
   also refuse if retained nullable payment values cannot satisfy the restored
   non-null constraints. Never delete data to make migration possible.
8. `needs_revision` is the only future complete-context rebase boundary. CP08
   proves at most narrow selector-schema capability; it does not claim complete
   authorized rebase while old Submission-to-Task context FKs remain.

## Acceptance criteria

- Real unified guide without a PaymentPolicy can screen and reach ready; the
  exact selected ContributionPolicyVersion is stamped before claimability.
- Claim and hidden Submission creation copy the exact task/assignment policy,
  without CON lookup or a current-guide substitution.
- Missing, foreign-project and inconsistent stamps reject at service and direct
  PostgreSQL boundaries; otherwise valid wrong-stamp probes reach the intended
  guard. Submission cannot be inserted without exact assignment/policy lineage;
  a failed ART consumption rolls back the production creation transaction.
- Previously closed assignment and Submission stamps are immutable and remain
  valid after successor guide activation or policy retirement.
- Frozen reads still work after catalogue rollout; screening/ready with an
  unavailable pre- or post-submit implementation deny without status, lineage,
  assignment or audit writes.
- Authorization, concurrent claim/role issuance/guide activity and rollback are
  proven with real owners. No new lock cycle or duplicate assignment/Submission.
- Migration preserves draft tasks and exact guide/policy/activation evidence,
  and atomically refuses any earlier non-draft task, assignment or Submission
  before DDL; all row snapshots and the Alembic marker remain unchanged on refusal.
  New constraints and payment-column nullability agree with ORM metadata.
- Old affected policy/payment context path is deleted and all affected callers
  use the canonical port; remaining dependencies are named explicitly.

## Risk and review routing

- Risk class: L1 (schema, policy lineage, authorization-adjacent transactions).
- Plan: architecture/reuse schema inventory and security/QA lock/fixture
  feasibility, then review the completed combined contract before product code.
- Implementation: architecture/reuse, security, QA/test-delta, product/operations,
  documentation and CI-integrity for migrations, tests and exact registrations.
- Human review focus: correct provenance rather than current-policy guessing,
  same-transaction copy/rollback, stable historical references, no obsolete
  payment readiness, and honest separation from later revision/public cutovers.

## Evidence

Use real PostgreSQL screening/claim/Submission tests, direct-SQL malformed and
foreign stamps, retained migration preserve/refuse cases, real-AUTH concurrency,
exact immutable public-contract tests and independent guard-removal probes.
Lead runs shared Ruff, module/AUTH boundaries, ownership/test structure, docs/link
and stale-wording checks once on the candidate. Hosted full lanes/coverage must
pass with zero skips/deselections and changed subsystems >=90%. Record exact
commands and review freshness in the PR; no secrets/private guide material.

## Reconciliation

- Current source: ARCH-03A/#415 is merged; its exact receipt and hash validation
  is reused, not reimplemented. Open #410 is unrelated CI impact reporting.
- Next usable boundary: ARCH-03B/03C task readiness/read/authorization cutover,
  following the adopted sequence; no next chunk begins automatically.
- Plan finding dispositions: SEC-CP08-PLAN-01 is addressed by exact UUID facts,
  claim digest inclusion and prepared Submission resource binding;
  SEC-CP08-PLAN-02 by AUTH-before-PROJECTS ordering and handle cleanup.
  CP08-ARCH-001 is addressed by the explicit refusal predicate;
  CP08-ARCH-002 by required initial assignment identity and immediate stamp validation,
  replacing the unnecessary deferred coupling to ART references.
  CP08-ARCH-003 is retracted: baseline resources describe frozen 0001, not head.
- Named future proofs: draft/evidence migration preservation; pre-DDL refusal with
  row/schema/marker snapshots; wrong same-project assignment stamp; missing or
  mismatched Submission assignment/stamp; exact committed stamp immutability;
  canonical hidden creation with complete ART references; isolated downstream
  CheckerRun payment nullability (not canonical materialization integration); role issuance versus claim in both
  lock orders; claim versus successor activation; two competing claimants;
  duplicate hidden Submission creation against one predecessor. These are planned
  runtime proofs, not claims of tests already executed.

### Scoped dependency correction

Implementation-time fixture tracing found that the earlier proposed universal
deferred ART-completeness guard would force CHECKERS/REV fixture migration before
their ARCH-04B/04C replacement exists. Those chunks depend on CP08 and ARCH-03C.
The correction strengthens TASK's own initial assignment/policy requirements,
keeps ART's existing three-reference staging contract, and leaves its unfinished
consumer replacement explicit. It neither adds compatibility behavior nor
weakens the hidden writer's required ART consumption. This replaces the earlier
plan assumption that assignment identity must wait for artifact consumption.
