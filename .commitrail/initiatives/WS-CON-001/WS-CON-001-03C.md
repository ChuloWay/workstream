# CON-03C — Immutable contribution and award storage

- Initiative: `WS-CON-001`
- Durable disposition: `Planned`
- Intended merge outcome: Store exact contribution sources and fixed awards without activating contribution creation, acceptance or fulfillment.

## Intent and current behavior

The human wants the complete claim/upload/check/outcome path, including automatic
acceptance when the locked policy permits it, followed by human review/revision.
CON needs immutable contribution and award storage before its shared transaction
participant. The merged Review and FinalAcceptance sources now exist. They remain
storage foundations without originating decision/acceptance authority custody.
Policy versions, rules, definitions and adapter bindings are already persisted.

This current record reconciles the adopted CON-03C predecessor contract with
merged REV-04A/04B. It does not call those foundations live runtime acceptance.
Canonical behavior remains [CON specification](../../../docs/spec_contribution_compensation.md).

## Bounded change

### Allowed

- `backend/app/modules/contributions/records/{__init__,models,schemas}.py`:
  ContributionRecord storage and strict immutable input, no repository/service.
- `backend/app/modules/compensation/awards/{__init__,models}.py`:
  CompensationAward storage, no fulfillment or external adapter operation.
- `backend/app/db/models.py`, `backend/alembic/env.py`,
  `backend/alembic/versions/0015_contribution_awards.py`.
- `backend/tests/contributions/records/{__init__,support,test_contracts,test_storage,test_migration}.py`.
- Existing fixture support: `backend/tests/tasks/post_submit_routing/support.py`,
  `backend/tests/post_submit_materialization_helpers.py`,
  `backend/tests/pre_submit_test_helpers.py`,
  `backend/tests/projects/unified_policy_fixtures.py`,
  `backend/tests/projects/guide_activation/{pg_support,compensation_fixtures}.py`.
  Thread an explicit `contribution_awards` instrument tuple through the real
  source chain before activation. Extend publication/binding fixture options to
  create real Finance-authorized money/points units, bindings and definitions
  for both contribution types. Existing unpaid/default controls remain intact;
  no production authority is mocked and no frozen policy is edited.
- Existing Review/FinalAcceptance immutability tests only if the added FK
  requires CASCADE to retain exact trigger reachability; preserve assertions.
- `backend/tests/conftest.py`, `backend/tests/test_alembic.py`: reset, immutable
  table inventory, measured fingerprint and linear upgrade inventory only.
- `backend/scripts/test_lane_catalogue.py`, `backend/tests/test_ci_lane_catalogue.py`:
  register new foundation tests in the existing schema lane, preserving all nodes.
- `backend/scripts/behavior_ownership.py`, `backend/tests/test_behavior_ownership.py`,
  `.ci/behavior-ownership/partition.v1.json`: exact declaration registration.
- This record, current CON/REV/ART/AUTH/POL/ARCH overviews, current AUTH/POL/ARCH
  plans/maps, ARCH-04E contract and `.commitrail/INDEX.md` for next-boundary claims.
- README, glossary, roadmap, architecture data model, CON/review/artifact specs,
  authorization activation custody; ignored local roadmap exports if present.

### Not allowed

No runtime writer/reader, repository, endpoint, AUTH action, acceptance/Review
composition, task effects, provider calls, outbox or obligation allocation.
No compatibility path, new source entity, retained-data deletion, fake authority
receipt, award adjustment/deletion, reputation or payment activation.

## Design

Two tables use native UUID keys and UUIDv7 record IDs, restrictive FKs, PostgreSQL
creation times and UPDATE/DELETE/TRUNCATE immutability. No new framework.

ContributionRecord has the canonical project/task/Submission/contributor,
contribution type, exclusive source IDs, artifact hash and exact policy version.
Reviewer records require an actual Review and its exact lease/reviewer/frozen
reviewer policy. All three completed decisions may earn reviewer contribution.
Submitter records require FinalAcceptance and the exact Submission assignment,
submitter and frozen submitter policy, never inference from a Review decision.
Each Review or FinalAcceptance can source at most one corresponding record;
contributor ID is not part of uniqueness. Shared joins verify actual project,
Submission/task, assignment and frozen policy. Artifact hash equals the canonical
ART content selected by the Submission binding/admission, not package_hash.
Historical published/retired policy versions are valid; current selectors and
current binding availability must not rewrite frozen economics.

Award rows bind the exact record and award definition, including its rule,
policy, project, contribution type, instrument, unit, quantity and adapter
binding. Only compensated rules yield awards. Quantity uses unscaled PostgreSQL
NUMERIC with existing positive/range/scale/whole-points rules and exact equality
to the immutable definition; no float conversion or rounding. At most one award
per contribution/instrument. Correlation ID is a caller trace UUID, not row ID.
There is no mutable fulfillment status. No separate award input DTO or writer
is needed before the CON participant: future code derives award fields directly
from canonical definitions.

SQL validators pin safe search_path and qualify protected tables/functions.
Missing/uncommitted parents fail closed; source-before-child in one transaction
is supported. Unique indexes arbitrate concurrent duplicates. No at-least-one
child requirement is introduced before CON-07 can own atomic composition.

Foundation rows confer no authority and have no product/economic consumers.
Before any production writer or fulfillment, originating Review/FinalAcceptance
receipt custody and shared fence/ordinal prerequisites must be installed. Their
upgrade must refuse retained pre-authority source or dependent CON rows unchanged;
never invent receipts or delete them. This extends the existing REV hardening
requirement, not a second authority system. Automated source polarity retains
REV's current limitation: do not fabricate an activated false-policy guide to
claim positive runtime proof. Both eventual triggers use the same participant.

## Acceptance criteria and proof

- Closed immutable contribution input rejects missing/mixed/wrong source shapes,
  extra fields, non-native UUIDs and malformed digest.
- Real Review/FinalAcceptance sources persist both contribution types with exact
  stored artifact, policy and ownership; review decisions accept/revise/reject
  all permit reviewer records, while non-accept cannot produce submitter source.
- Coherent sibling and foreign-project substitutions, wrong actor/lease/assignment,
  policy and artifact digest fail on the intended guard; a valid control follows.
- Real published compensated definitions yield exact money and points awards;
  unpaid rules yield no award; wrong definition/project/type/binding/unit/quantity
  rejects. Retired policy or suspended binding preserves already-frozen facts.
- Duplicate source/instrument rows fail; independent sessions prove commit and
  rollback uniqueness. Caller rollback removes tentative records and awards.
- DB clock and all three mutation operations preserve retained facts.
- `test_contribution_source_substitution` uses real coherent source rows, exact
  contribution guard errors, valid control and transactional removal of one
  exact source/actor equality; the negative assertion must reach DID NOT RAISE.
- `test_award_definition_substitution` separately varies exact copied economic
  fields, asserts the award guard, restores a valid control and transactionally
  removes the exact quantity equality; the mismatched quantity must then reach
  DID NOT RAISE. Both probes restore SQL through rollback.
- `test_unpaid_rule_rejects_award` attempts an actual award insertion for an
  unpaid contribution with an existing compensated definition from another
  valid policy/type. Check the explicit unpaid-rule error before definition
  matching, never manufacture an illegal definition under an unpaid rule.
- Missing-parent race against an uncommitted parent that rolls back leaves no
  child. Populated 0014 upgrade preserves parents; canonical downgrade refuses.
- Full hosted completeness remains required. Coverage is diagnostic only.

Concrete test fixture path: existing acceptance_source -> actual stored Review,
lease, verified Submission and policies -> insert_acceptance -> contribution ->
award. `contribution_awards=("money", "project_points")` flows from acceptance
through review/packet **options into the newly explicit completed_source option,
then material_fixture, approved_pre_submit_fixture and
create_standalone_unified_policy. Its publisher installs both rules and both
real instruments before publication/activation, using existing Finance services.
Empty tuple retains an unpaid control. Plan review traces these exact extensions.

Mandatory future activation tests (not current runtime claims):
`test_contribution_activation_refuses_retained_foundation` retains a complete
Review/FinalAcceptance/contribution/award graph, rejects activation and verifies
all rows unchanged with no receipt backfill/deletion;
`test_contribution_activation_empty_foundation` requires exact source authority,
shared fence/ordinal and the participant before any writer/consumer registration;
`test_participant_complete_award_set_and_rollback` proves the exact definition set
for compensated rules, zero awards for unpaid rules and whole-aggregate rollback.
CON-07 and source-authority composition must supply those proofs before exposure.

## Risk and review routing

Risk L1: bounded immutable economic history/schema. Architecture/reuse and
security plan reviews precede implementation. Implementation reviews cover
architecture/reuse, security, QA/test delta, CI integrity, docs/product operations.
Human focus: exact frozen economic source versus live authority; no automatic
payment or premature runtime consumer. Merge remains human-owned.

## Reconciliation

Merged main includes REV-04B source storage and its mandatory later authority
hardening. Current capability and next-boundary claims will advance together
with this intended merge outcome. Next: CON-07 participant after required shared
fence/ordinal and source-authority prerequisites are reviewed against code.
