# WS-ARCH-001-CP07 — Bind and activate one complete guide generation

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: one hidden, deny-default PROJECTS operation atomically
  activates the explicitly approved guide generation and binds its selected
  published ContributionPolicyVersion; AUTH-12H supplies live activation authority later.

## Intent

Connect the delivered unified guide setup, separate pre/post approvals and CP06
selected-policy validator. The manager's exact approved generation must become
one immutable guide binding, without selecting a newer policy behind their back.
CP07A on main `6e7e157b` repaired the prerequisite cross-owner lock order.
This is one activation operation, not a separate binding workflow.

## Current behavior

`ProjectService.validate_activation_ready` validates the approved unified chain
but retains an obsolete PaymentPolicy parameter and bypass flag. Its sole
production caller, `authorization_reads`, already excludes payment. The dormant
activation write was removed; `guard_guide_lineage_and_lifecycle` rejects all
lifecycle changes. `ProjectGuide` has exact review/revision selectors but no CON
binding. Creation produces a draft Project, while active-guide reads require an
active Project. CP06's public validator accepts an exact policy/version and
`guide_activation` purpose under Project/CON/resource locks. It grants no authority.

`GuideProposalRepository` and `PostPolicyRepository` already own finalization,
current-generation and separate approval custody. Reuse them and existing
CHECKERS catalogue/planning validation. No inference, document retrieval or
actual Task/Submission/CheckerRun is required for activation.

## Bounded change

### Allowed

- PROJECTS `api/guide_activation.py` and a focused `guide_activation/` owner
  package for contracts, operation custody, repository and service; PROJECTS
  models/schemas/readiness/read composition and exact adapter root wiring.
- A PROJECTS-owned local CON validation contract and application adapter using
  only CON's public API; existing CHECKERS public planners/catalogues.
- One `0023` activation-custody migration, exact Alembic head/graph and measured
  strict schema fingerprint updates; model registration and affected fixtures.
- Remove PaymentPolicy readiness parameters/branch and dead builder/input/response
  declarations after tracing consumers; update affected callers and tests.
  Retained PaymentPolicy persistence and downstream economic consumers remain
  until their own replacement; this command never uses them.
- Focused PROJECTS tests, real PostgreSQL custody/concurrency/replay/migration
  tests and necessary shared prerequisite fixtures, exact lane/debt inventories;
  canonical guide/AUTH/CON docs, README, roadmap and initiative navigation.

### Not allowed

- Activate an AUTH action or public HTTP route; sufficiency authority cannot
  authorize activation. No new grant, role, broad permission or service actor.
- TASK/assignment/Submission policy lineage cutover, acceptance/routing runtime,
  agents, provider calls, new compilers or a second policy-selection algorithm.
- Compatibility aliases, payment bypass flags, duplicate readiness paths,
  historical-lineage fabrication, retained-data deletion or weakened test gates.

## Design and decisions

1. Use immutable typed requests selecting the complete approved post-policy
   target (which already includes compilation, source/setup generation, both
   catalogue identities and upstream approval), its exact approval receipt,
   review/revision selectors and hashes, guide mutation generation, explicit
   CON policy/version and expected previous active guide. Reject malformed,
   missing, stale and mixed-project selectors; do not infer latest selections.
2. Introduce a narrow nominal activation authorization participant, default
   unavailable. Enter its authority scope before owner locks, then lock Project
   and the existing finalized proposal chain. Consume exact resource-bound
   authority after all readiness/CON facts are locked. The participant owns
   authority locks and fresh replay checks; PROJECTS owns product writes and the
   caller-owned root transaction. AUTH-12H implements the live participant.
3. Reuse canonical current-upstream/post-approval custody and catalogue checks;
   revalidate registered implementation/configuration through existing CHECKERS
   planning and post-policy contracts without executing work. Reconcile the
   shared readiness helper and active-guide read callers in place. Keep false
   `human_review_required` unavailable without coercion; initial true activation
   has no dependency on a live automated acceptance operation or an existing task.
4. Call CON through an injected PROJECTS-local port. Always request
   `guide_activation`, verify returned exact identity/purpose and preserve its
   locks. Never use revision adoption to admit a retired or stale selection.
5. Persist an immutable activation operation and complete result, correlated
   with exact actor/link/grant and consumed audit decision. The existing audit
   schema already admits `project.guide.activate` / `project.guide.manage`;
   registration is not live evaluator authority. Hidden tests supply controlled
   participants and real audit persistence, without claiming live AUTH activation.
6. Bind non-null CON identity for successful activation, preserve exact existing
   review/revision selectors, supersede only the expected prior active guide,
   and promote a draft Project to active in the same transaction. Unavailable
   Project states deny. One active guide per project remains enforced.
7. Completed replay verifies immutable request/result custody and fresh scoped
   authority, returns the original receipt and creates no new effects. It must
   remain possible after the guide is superseded or CON policy retired; replay
   is not a new binding and must not silently consult current policy selection.
8. Migration guards tie lifecycle writes to exact immutable activation custody,
   enforce same-project CON foreign keys, reject missing/extra/mismatched rows,
   and preserve retained data. Drafts cannot require a policy before selection.
   Do not manufacture CON lineage for existing rows. Resolve enforcement for
   retained active rows explicitly in plan review before implementation; old
   unbound rows cannot satisfy the new activation/read contract.

## Acceptance criteria

- A real, complete draft project/guide with both approvals, current catalogues,
  complete true review/revision policies and a published complete CON version
  activates atomically with exact selectors, source/generation and audit custody.
- No default authority, wrong/copied participant or receipt, wrong actor/project,
  stale guide/setup/approval/policy generation, missing component, unsupported
  checker/configuration, false human-review setting or CON eligibility failure
  produces a guide binding, lifecycle change or committed activation operation.
- No PaymentPolicy or payment bypass argument is needed; obsolete exclusive
  tests are removed while required lifecycle/hash/authority tests remain.
- Real PostgreSQL tests exercise concurrent activation, CON publication/retirement
  and binding suspension using observed locks and valid fixtures. Success after
  activation must remain readable. Failures at final consumption/persistence and
  caller rollback leave the complete prior state unchanged.
- Same-key exact replay after lost response returns original evidence once;
  changed payload/actor and revoked authority deny. Supersession/retirement
  does not rewrite the original receipt or rebind its policy.
- Direct SQL rejects incomplete/mismatched activation custody and later binding
  changes. Migration roundtrip preserves unrelated schema, downgrade refuses
  retained activation evidence, and upgrade never invents historical bindings.
- No live endpoint/action or downstream TASK/Submission capability is claimed.

## Risk and review routing

L1: guide lifecycle, authorization, immutable policy lineage and database
atomicity. Required plan and implementation tracks: architecture/reuse,
security, QA/test delta, documentation/product operations, and CI integrity for
migration/inventory changes. Human focus: one complete activation operation;
no mistaken setup authority, current-policy substitution or partial commit.
The schema/service/tests span several existing owners; this cohesive boundary
needs more than the default 500-line guideline. Keep each owner package bounded
and do not expand into downstream task activation or general authorization work.

## Evidence

Lead runs focused tests, negative controls isolating each protected boundary,
real PostgreSQL interleavings and migration/rollback proof; then lint, module/AUTH/
structure/ownership checks, exact lane inventory, links/stale wording and
Commitrail checks. Hosted CI supplies full test completion and coverage (changed
subsystems >=90%, no skips/deselections or weakened existing floors). Reviewers
inspect a clean exact target and compatible lead-produced proof. No runtime
success is claimed by this plan; commands/results and current review state live
in the PR trust summary.

## Reconciliation

The adopted CP07 skeleton is planning history, not an executable contract.
This record replaces its ambiguous non-null-at-creation and payment wording;
retained-schema enforcement is the remaining plan-review decision. The next
usable boundary after this hidden command is AUTH-12H's exact live activation
composition, followed by CP08 and task lineage work in the adopted sequence.
