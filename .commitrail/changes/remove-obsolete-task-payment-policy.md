# Remove obsolete TASK payment policy storage

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: TASK and Submission no longer retain or expose the superseded guide-keyed PaymentPolicy path; current ContributionPolicy and award lineage remain unchanged.

## Intent and current behavior

The user requested removal of TASK's obsolete `base_amount`, `currency`,
`payout_type` and `locked_payment_policy_version`, together with the unused
`payment_policies` table and mutable repository methods. Workstream is unreleased
v0.1; these are earlier development remnants, not a compatibility requirement.
Public TASK mutation responses and the CLI decoder still advertise the fields.
Submission construction copies the obsolete stamp. CHECKERS already removed it.
Guide test fixtures still insert PaymentPolicy by default despite no production
writer; tests of that mutable upsert preserve obsolete behavior.

## Design and boundaries

Remove the model, exports, repository upsert/read, TASK columns/response fields,
Submission stamp and associated named foreign/unique constraints. Remove affected
CLI response fields, fix all consumers and fixtures, and reconcile current specs.
Use an additive Alembic migration after 0022: lock affected tables, refuse upgrade
if any PaymentPolicy row or non-null removed TASK/Submission value exists, then
remove empty obsolete storage with explicit constraint/column/table operations.
Check retained Submission stamp first, then each TASK field, then policy rows,
with distinct refusal messages so valid FK parents do not mask child probes.
Lock/preflight TASK command receipts too: refuse obsolete keys at the response
root or nested claim task, including null values. These immutable receipts must
not be rewritten. Make TASK response/replay DTOs reject unexpected fields rather
than silently discard them; preserve exact authorized current-shape replay.
Do not use CASCADE, invent replacement terms or delete retained data. The guarded
refusal is a migration safety boundary, not a compatibility implementation.
Downgrade remains prohibited, consistently with the current v0.1 migration chain.
Retain the historical baseline/migration chain as migration history, not runtime.

Current ContributionPolicy identities, immutable contribution/award terms,
compensation-unit semantics, authorization, task assignment, locked guide/review/
revision/checker lineage, artifact custody and atomic acceptance are unchanged.
A response-only removal would leave the mutable storage path behind and is
therefore insufficient. A baseline rewrite would discard upgrade proof and is
not selected. This standalone cleanup does not advance first-layer runtime steps
or introduce another payment subsystem.

## Allowed files

- PROJECTS `models.py`, `repository.py`, and aggregate `app/db/models.py` exports.
- TASK `models.py`, `schemas.py`, `submission_composition.py`, stale service docstring.
- One migration `0023_remove_task_payment_policy.py`, Alembic env head recognition,
  graph/current-head tests and focused migration tests.
- Exact affected backend fixtures/tests: projects guide fixtures, test_projects,
  test_tasks, test_submission_composition, artifact binding/admission fixtures,
  TASK contribution/submission lineage and work-context/privacy tests; keep
  required rejection/privacy assertions even when the obsolete field disappears.
- `tests/conftest.py` reset-table list and recomputed schema fingerprint; both
  PROJECTS and AUTH guide-activation PostgreSQL modules; TASK command-replay tests
  and authorization task-read/privacy assertions. Historical 0008 tests remain.
- Existing lane catalogue/inventory and ownership registration only for new proof.
- CLI typed TASK response, decoder and command renderer, plus affected
  contract/integration fixtures. Preserve strict unexpected-field rejection.
- Current PROJECTS/TASK/Submission/CHECKERS specs, data-model/README/roadmap claims
  affected by the removal; this record. Historical records remain unchanged.

## Prohibited changes

No new payment policy, default or replacement field, alias/fallback, retained-data
rewrite, authority expansion, route addition, contribution/award schema change,
checker behavior change, public intake activation, CI gate weakening or unrelated
cleanup. Do not remove a test's authorization, privacy, immutable-lineage or
transaction proof merely because its fixture contains a removed field.

## Acceptance and verification

1. No production model/repository/response/CLI consumer retains the obsolete path.
   Public TASK create/screen/release/claim/start/start-override responses and
   stored replay payloads omit all four fields; exact locked
   ContributionPolicy lineage and task behavior remain valid.
2. Real PostgreSQL upgrade removes the named table, columns and constraints when
   empty while preserving existing task/submission/current policy facts. Schema
   metadata matches migrations. No dangling trigger/function dependency remains.
3. Independently populated obsolete policy row, each TASK field and Submission
   stamp and obsolete root/nested receipt keys refuse upgrade without changing retained data; assertions identify the
   intended migration refusal. Test setup uses the pre-migration schema and valid
   parent lineage, not an unrelated FK failure. Valid empty control succeeds. Build the isolated predecessor directly at0022,
   never downgrade; seed valid policy/TASK/Submission relations without disabling
   guards. Use actual migration operations for each refusal and full Alembic
   upgrade for the positive control. Test direct/nested replay substitutions
   against an otherwise valid receipt and retain authorized replay controls.
4. Remove obsolete mutable-upsert tests and payment-only activation assertions;
   retain closed request-shape rejection, privacy, current contribution lineage,
   and guide immutability proofs. Replace fixtures with current policy setup,
   not another payment-policy compatibility helper.
5. Focused PostgreSQL migration/public TASK tests, CLI tests, Ruff, module/AUTH
   boundaries, test structure/ownership/lane inventory, docs links/stale wording
   and Commitrail pass. Hosted full-suite completeness remains required.

## Risk and review

L1 bounded schema/public-contract cleanup with data-preservation and compensation
adjacency. Before implementation: focused architecture/security and QA/test-delta
plan review. Before readiness: those tracks plus CI-integrity and docs/product-ops.
Shared checks run once on a clean target; reviewers inspect scoped risk and
relevant unchanged current compensation owners. Human focus: no data deletion,
complete consumer removal and preserved ContributionPolicy/award truth.
The user authorized this removal; no additional product decision is required.
