# WS-ARCH-001-CP07 — Bind and activate one complete guide generation

- Initiative: WS-ARCH-001
- Durable disposition: Complete
- Intended merge outcome: one hidden, deny-default PROJECTS operation atomically
  activates the explicitly approved guide generation and binds its selected
  published ContributionPolicyVersion; AUTH-12H supplies live activation authority later.

## Intent

Connect the delivered unified guide setup, separate pre/post approvals and CP06
selected-policy validator. The manager's exact approved generation must become
one immutable guide binding, without selecting a newer policy behind their back.
CP07A on main `6e7e157b` repaired the prerequisite cross-owner lock order.
This is one activation operation, not a separate binding workflow.

## Baseline assessed before implementation

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
  models/schemas/readiness/read composition, canonical Project row-lock refresh,
  shared owner-local catalogue comparison, existing guide mutation ledger and
  repository, and exact adapter root wiring.
- A PROJECTS-owned local CON validation contract and application adapter using
  only CON's public API; existing CHECKERS public planners/catalogues.
- Exact activation resource parity in existing AUDIT schemas and AUTH audit domain
  vocabularies/target mapping; no action activation or new audit path.
- One `0023` activation-custody migration, exact Alembic head/graph and measured
  strict schema fingerprint updates; canonical `app/db/models.py` registry reuse
  from `app/db/session.py`, with fresh-process API/worker mapper tests and affected fixtures.
- Remove PaymentPolicy readiness parameters/branch and dead builder/input/response
  declarations after tracing consumers; update affected callers and tests.
  Retained PaymentPolicy persistence and downstream economic consumers remain
  until their own replacement; this command never uses them.
- Focused PROJECTS tests, real PostgreSQL custody/concurrency/replay/migration
  tests and necessary shared prerequisite/API-drill fixtures, exact lane/debt/behavior-ownership inventories;
  canonical guide/AUTH/CON and data-model docs, current data-flow view, README,
  roadmap and initiative navigation.

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
   unavailable. Acquire the full authority scope (control, caller, link, grant)
   before Project or product rows, then Project, draft/proposal/current approvals,
   and CON policy/version/graph/bindings. Prepare and consume exact resource-bound
   authority only after all readiness/CON facts are locked; close the prepared
   handle in `finally`. The strong immutable receipt binds actor, identity link,
   matched administrative grant, scope, audit decision and resource digest.
   The participant owns
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
   The bridge imports only CON public APIs; outer composition injects its port.
   Do not import the CON adapter root from the PROJECTS adapter root: CON already
   depends on PROJECTS eligibility, so that would introduce a cycle. Runtime DB
   composition imports the existing full model registry before mapped instances
   are created. API and standalone workers must resolve the new cross-owner FKs
   without relying on Alembic or pytest having imported other model owners.
5. Extend `GuideMutationIdempotencyRecord` and `GuideMutationRepository` for
   `project.guide.activate`; do not create a second replay ledger. Reuse the
   actor/action/key namespace, pending-to-committed reservation and immutable
   response. Add activation-only exact binding, prior guide/generation and prior
   Project status fields as needed, with action-specific shape constraints.
   Extend the existing mutation guard and custody functions for this action.
   The committed ledger operation and complete result are the canonical immutable
   binding, correlated with exact actor/link/grant and consumed audit decision. The existing audit
   schema already admits `project.guide.activate` / `project.guide.manage`;
   its privacy resource allowlist does not admit the canonical
   `project_guide_activation` token yet. Add only that resource token in 0023
   using the existing shape-preserving constraint update pattern; no action or
   permission expansion. Add the same token to existing AUDIT `_RESOURCE_TYPES`,
   AUTH `AuthorizationDecisionResourceType` and `CONTEXT_DIGEST_RESOURCE_TYPES`.
   Extend `project_authority_audit_target` with an exact activation-context branch
   returning the project scope, guide activation resource/id and project target;
   do not broaden `GUIDE_BOUND_PROJECT_MANAGER_ACTIONS` or activate the action.
   Verify Python schema/domain/SQL parity. Registration is not live evaluator authority. Hidden tests supply controlled
   participants and real audit persistence, without claiming live AUTH activation.
6. Bind non-null CON identity for successful activation, preserve exact existing
   review/revision selectors, supersede only the expected prior active guide,
   and promote a draft Project to active in the same transaction. Unavailable
   Project states deny. One active guide per project remains enforced.
7. Completed replay verifies immutable request/result custody and fresh scoped
   authority, returns the original receipt and creates no new effects. It must
   remain possible after the guide is superseded or CON policy retired; replay
   is not a new binding and must not silently consult current policy selection
   or invoke the draft-only `GuideProposalRepository.lock` path.
8. Add nullable guide selectors for exact CON policy/version and activation
   operation, with same-project composite foreign keys. Replace the existing
   `guide_lineage_lifecycle_guard` under the same name for INSERT and UPDATE:
   insertion requires draft/unbound; an update ending active requires complete
   non-null binding selectors and exact deferred committed activation custody.
   Admit draft-to-active and active-to-superseded lifecycle transitions only.
   Freeze bound selectors, including CON identity. No NOT VALID constraint or
   backfill is needed: untouched retained active rows stay unchanged; an explicit
   retained unbound predecessor may become superseded only when the same committed
   successor activation names it exactly, without fabricated predecessor lineage.
   Active-read composition must load the immutable operation and exact binding;
   unbound retained rows are unavailable. Reads do not rerun current CON eligibility.
9. Add a narrow deferred Project draft-to-active custody trigger requiring the
   same committed activation operation and final exact active bound guide.
   Extend existing Project insert custody to require draft: the creation service
   sets draft today, but its database custody does not enforce that status.
   Guide and Project transitions must resolve to the same ledger row. Active guide replacement
   leaves the Project active; the service denies other Project states. Do not
   introduce a general Project lifecycle subsystem. Extend only the existing
   isolated downstream fixture's named trigger suspension for this new guard;
   CP07 activation proofs must use the real custody path, never that helper.

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
- Direct SQL rejects active guide insertion, activation without committed exact
  custody, missing/foreign CON selectors, copied audit decisions, pending records
  at commit, partial Project/guide transitions and later binding mutation/deletion.
  Positive controls reach each targeted guard with other required facts intact.
- Upgrade an actual 0022 unbound active guide unchanged, prove active-read denial,
  and prove a fresh authorized activation can supersede it without backfill.
  Migration roundtrip preserves unrelated schema; downgrade refuses retained
  activation evidence. Fresh valid activation is readable after CON retirement.
- Prove the canonical activation audit resource can persist in PostgreSQL, an
  adjacent unsupported resource is rejected with otherwise valid facts, and
  downgrade refuses retained activation audit history as well as ledger evidence.
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
This record replaces its ambiguous non-null-at-creation and payment wording.
Plan review chose the existing guide lifecycle trigger, narrow Project activation
commit guard and existing guide mutation ledger to preserve one operation owner. The next
usable boundary after this hidden command is AUTH-12H's exact live activation
composition, followed by CP08 and task lineage work in the adopted sequence.


## Implementation proof map

- `backend/tests/projects/guide_activation/test_postgresql.py` proves complete
  activation without PaymentPolicy/Task/Submission prerequisites, serialized
  binding discovery, exact replay and read/replay after CON retirement.
- `test_successor.py` proves distinct guide versions, explicit predecessor
  selection, atomic supersession and replay of both immutable receipts. Its
  two-session successor case proves serialization and the resulting prior-state
  receipt. A separate unavailable-Project case proves refreshed state denies
  admission before downstream policy reads; later CON refresh cannot mask it.
- `test_rejections.py`, `test_admission.py` and `test_direct_sql.py` cover exact
  selector rejection, unavailable/invalid authority, close failure, caller
  rollback, forbidden direct lifecycle writes, missing commit custody and
  immutable binding/audit evidence. The missing-receipt test leaves all product
  pointers and consumed authority present and checks its specific deferred error.
  The standalone supersession test starts with a committed active guide, changes
  only status and supersession time, and requires the exact deferred missing-successor
  error at commit; rollback preserves the active guide and its immutable receipt.
  Malformed nested receipt tests preserve operational selections and matching
  command/facts/audit digests, require shape rejection and rollback, then prove
  the same valid input commits and remains readable. SQL preserves structural
  receipt validity; CON remains the owner of graph semantics.
- `test_concurrency.py` observes PostgreSQL blocking edges between activation
  and real Finance-authorized publication, retirement or binding suspension,
  and proves duplicate activation delivery has one effect.
- `test_migration.py` compares the prior schema after downgrade, preserves an
  actual pre-0023 unbound active guide through upgrade, denies its active read,
  and replaces it through a new guide without inventing prior custody. Retained
  ledger or audit evidence prevents downgrade.
- `test_audit_contract.py` checks exact Python audit vocabulary and target
  mapping without enabling the planned action. Direct-SQL tests check the
  corresponding database resource/privacy guards and model/FK parity.
- Existing `backend/tests/test_projects.py` active-guide body and policy
  immutability tests now invoke CP07 through `read_fixtures.py`; their assertions
  are retained. The API contract drill uses the same real hidden activation
  fixture; it no longer invents an active guide by suspending lifecycle guards.
  Only obsolete payment-readiness cases are removed.

Activation fixtures create document declarations through the real guide owner
and reuse committed-original, compilation, projection and finalization helpers.
They do not disable guide activation guards. Storage and model outputs are
scripted and queue readiness is an arranged prerequisite: this is database and
owner-composition proof, not live broker/provider proof. The activation authority
participant is deliberately test-only until AUTH-12H. Downstream tests that only
need a retained active row keep their explicit historical fixture; current
active-read proofs require real activation custody.

Fresh-process tests in `backend/tests/test_db_session.py` import the API and
standalone setup, post-policy and checker worker entry points, resolve every foreign key and configure all
mappers without pytest's preloaded model graph. The API drill uses canonical
package-qualified shared fixture imports, without adding search-path aliases.
