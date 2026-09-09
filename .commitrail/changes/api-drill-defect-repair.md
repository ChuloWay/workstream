# API drill defect repair

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Reject the five observed invalid API inputs with 422 and preserve valid project, guide, and two-role authority behavior.

## Intent

The [drill findings](../../docs/engineering/external-api-drill-findings.md) record
five historical 503 responses. The starting main exposed unbounded project
name/slug and guide version, explicitly nullable guide content, and unsupported
adjudicator role values. The existing storage limits are 200/120/50 characters.
Only submitter and reviewer project grants belong to current v0.1.

## Bounded change

Allowed files and responsibility:

- `backend/app/modules/projects/schemas.py`: the three existing bounds and
  omitted-versus-null guide content validation only.
- `backend/app/modules/authorization/{schemas,models,project_role_service}.py`,
  `backend/app/modules/actors/schemas.py`, `backend/app/modules/audit/schemas.py`:
  close current role vocabulary to submitter/reviewer.
- `backend/alembic/versions/0014_project_role_scope.py`: incremental, transactional
  narrowing of role and audit contracts, preserving other installed rules.
- `backend/alembic/env.py`, `backend/tests/test_alembic.py`: recognize the new
  incremental revision while retaining every existing supported migration entry.
- Existing migration tests in `backend/tests/authorization/contribution_policies/`,
  `backend/tests/authorization/guide_compilation/`, and
  `backend/tests/projects/guide_compilation/`: update only current-head expectations
  for the additive revision, preserving explicit historical targets and assertions.
- `backend/scripts/test_lane_catalogue.py`,
  `backend/tests/test_ci_lane_catalogue.py`: enroll the new test modules in
  existing hosted lanes without changing selection or coverage policy.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: refresh exact existing debt
  fingerprints/spans after shrinking touched legacy tests; no new exceptions.
- `.ci/behavior-ownership/partition.v1.json`,
  `backend/scripts/behavior_ownership.py`, `backend/tests/test_behavior_ownership.py`:
  enroll only the transferred drill in the existing shared target partition;
  preserve protected-base custody and reject adjacent unapproved targets.
- `backend/tests/test_projects.py`, `backend/tests/test_authorization.py`,
  `backend/tests/test_api_drill_repairs.py`,
  `backend/tests/migrations/test_project_role_scope.py`, `backend/tests/conftest.py`:
  behavior regressions, migration evidence and schema fingerprint if required.
- `backend/scripts/external_api_drill.py`, `scripts/test_external_api_drill.py`,
  `backend/scripts/admin_api_drill.py`, `backend/scripts/admin_guard_probe.py`,
  `scripts/test_admin_api_drill.py`,
  `docs/engineering/external-api-drill.md`,
  `docs/engineering/external-api-drill-findings.md`: transferred harness and
  provenance-preserving verification documentation.
- Current role descriptions in `docs/spec_authorization_service.md`,
  `docs/glossary.md`, `docs/architecture_lockdown.md`,
  `docs/roles_permissions.md`, `docs/operations_roles_permissions.md`,
  `docs/operations_authorization_service.md`, `docs/architecture_data_model.md`,
  `docs/spec_review_lifecycle.md`, `docs/operations_reviewer_workflow.md`,
  `docs/operations_project_operating_manual.md`,
  `docs/decision_0015_project_contributor_roles_are_independent.md`,
  `docs/roadmap_status.md`, `docs/spec_contribution_compensation.md`,
  `docs/decision_0012_workstream_authorization_service.md`,
  `docs/decision_0016_contribution_compensation_boundary.md`,
  `docs/architecture_brief/workstream_architecture_brief.md`, and this record.

Not allowed: product-builder setup/compilation changes, baseline rewrite,
retained-data deletion, new permissions, adjudication implementation, relaxed
audit guards, compensation/review/revision features, broad compatibility cleanup,
raw logs or secrets, root local handoff, automatic merge.

## Design and plan

1. Apply existing length limits at Pydantic request validation. Reject explicit
   null guide content before mutation while omission preserves stored content;
   keep summary independently nullable and align OpenAPI.
2. Remove unsupported role options from shared input/output/filter vocabulary
   and audit projections. Use an additive migration over current main, narrowly
   amend installed contracts, and fail safely if incompatible retained data
   prevents narrowing; never silently delete or relabel history.
3. Add exact-limit Unicode, oversize, null/omission/summary, state readback,
   same-key recovery, supported-role and unsupported-role regressions.
4. Run isolated PostgreSQL proof, harness tests, lint and repository checks;
   freeze a clean candidate, run focused internal reviews, fix valid findings,
   publish one PR, and verify complete hosted tests/coverage and external review.

## Acceptance criteria

- Integrate the previously reviewed twenty-actor drill without duplicating its
  HTTP/server/isolation harness or losing external-review discovery/cleanup fixes.
- Reproduce bootstrap, role/scope/lifecycle denials and all four last-admin
  count guards on the repaired candidate. Preserve rollback-only owner probes
  and isolated off-by-one mutants; do not count them as HTTP capabilities.
- Rerun both drill entry points against fresh owned databases at the integrated
  clean Git target. Retain raw evidence outside Git, record target provenance
  in the PR, and update the roadmap with verified scope and remaining limits.

- Oversize name, slug and guide version return 422; exact limits and Unicode
  persist unchanged; replay/conflict and duplicate behavior remain intact.
- Explicit null content returns 422 without state/replay advancement; omitted
  content preserves text, valid replacement succeeds, summary accepts null.
- Adjudicator input returns 422 without grant/access; only submitter/reviewer
  appear in current public and persistence contracts.
- Migration preserves existing supported data and audit guards, and fails
  atomically on incompatible retained rows.
- Historical evidence remains attributed to its actual original target.
- Product builder work is preserved; one reviewed PR awaits human merge.

## Risk and review routing

- Risk class: L1 (bounded authorization and database contract narrowing).
- Required reviewers: security; architecture (schema/model/database parity);
  QA and test_delta (combined assignment); documentation; ci_integrity for
  additive enrollment of new regression modules and drill targets in existing
  lanes/partitions. The administrator harness additionally requires focused
  security and QA/test-delta review; documentation reviews the roadmap evidence.
- Human review focus: two-role scope, safe retained-data migration behavior,
  invalid-input atomicity, and historical evidence limits.

## Evidence

Lead runs relevant isolated PostgreSQL regressions and helper tests, Ruff,
Commitrail validation, stale wording and Markdown link checks. Hosted Backend
must run all test lanes, preserve global 78% and applicable subsystem 90% floors.
The five repairs do not certify every API or establish MCP readiness.

Named regression evidence:
- `test_api_drill_request_limits_are_exposed_in_openapi` verifies published bounds,
  optional non-null content, and independently nullable summary.
- `test_exact_unicode_project_and_guide_limits_persist_unchanged` and overflow
  regressions verify character limits, fresh persisted state and same-key recovery.
- `test_guide_content_null_has_no_state_then_recovery_and_omission_succeed`
  verifies content/timestamp preservation and absent replay reservation on denial.
- `test_unsupported_adjudicator_role_is_rejected_without_grant` verifies a valid
  active-human target, role-specific 422, no grant, and same-key reviewer recovery.
- `tests/migrations/test_project_role_scope.py` exercises installed SQL role/audit
  contracts, exact downgrade/re-upgrade restoration, and atomic retained-history
  refusal. Existing project/authorization suites cover supported grants and audit.

## Review findings and decisions

Plan review passed with low risks and required explicit OpenAPI assertions and
retained-history refusal proof. Migration verification exposed PostgreSQL's
parsed constraint spelling and SQLAlchemy's name-prefix convention; the repair
uses checked transformations of installed definitions and exact constraint names.
It retains the already-narrow generic audit fact allowlist. CI review found
stale structure-ledger entries and legacy-test growth; new rejection assertions
were moved to the focused regression module (including the audit guard's exact
privacy-safe TypeError contract), touched legacy tests shrank without
losing assertions, and existing debt fingerprints were refreshed. The schema fingerprint is generated on CI's PostgreSQL 16: comparison with
PostgreSQL 17 found only three namespace-identity renderings (`pg_catalog.json`
versus `json`) differed across 4,670 objects. The check retains one exact
PostgreSQL 16 fingerprint, with no normalization or alternate accepted hashes.
Hosted migration regressions also exposed stale current-head expectations; these
now name the additive revision while retaining historical migration targets and
all custody assertions. External review hardened drill discovery and bounded
server cleanup, with focused failure-preservation regressions. Current review,
exact-head checks, and external findings are recorded in the PR.


## Reconciliation

Original source is main `fa49529b` (PR #391); no open PRs at that initial inspection. The product
builder worktree is separate and clean at inspection. Additive migration avoids
rewriting its baseline. Roadmap role exposure will be reconciled in this PR.
Next usable boundary: human merge, then orchestrator reruns exact-main HTTP drill
and extends remaining field coverage. No next implementation chunk is started.

The human subsequently authorized the orchestrator to take over PR #392 and
integrate the administrator drill with these repairs. This is the single combined
change record; the separate local drill record is consolidated here, not another
permission or delivery step. Preserve the repair's OpenAPI discovery and bounded
cleanup hardening when extending its shared runner. Current target and execution
results belong in the PR, not a claim that historical runs used the latest head.

## Integrated drill scope and historical evidence

The drill exists to establish observed external-client behavior for an MCP
proposal, not to certify routes from schema existence or seeded internal fixtures.
It uses a synthetic local Flow-compatible issuer with the real verifier, fresh
owned PostgreSQL databases, twenty HTTP-created profiles and the existing local
bootstrap CLI. All later mutations use HTTP. Artifact storage and automatic setup
execution remain disabled: deployed Flow, S3, model execution, unified setup and
end-to-end acceptance are outside this proof. Never use production credentials,
an existing database, hidden routes, product SQL writes, or disabled guards.

The shared harness inventories every discovered OpenAPI operation and nested
field, distinguishes successful calls, denials, failures and untested operations,
retains failures across later successes, checks response types and state readback,
and keeps reports create-once outside Git without tokens or raw response bodies.
Scenario callback reuse avoids a second server/credential/database lifecycle.

Bootstrap proof covers invalid targets, unchanged dry-run, concurrent one-winner
execution, atomic grant/control/audit state and later conflicts. Administrator
proof covers five role definitions and scopes, self-grant/revoke, project scope,
idempotency/replay, lifecycle changes and concurrent cross-admin revocation.
Submitter/reviewer grants include cross-project denials and no administrative
privilege. Catalogue membership never claims unavailable finance/task operations.

Rollback-only owner subprocesses load actual stored actors/links/grants under the
canonical control lock and exercise grant revocation, profile suspension,
deactivation and identity-link revocation count guards. One/two-admin states,
backup suspension/link revocation, restoration and final cross-revocation are
distinct assertions. In separate ephemeral subprocesses, exactly one `<= 1`
comparison is changed to `< 1` for each owner; each must fail its exact checks.
No source file or live API process is mutated. Pre/post authority and audit
snapshots must match. These checks are not additional HTTP operations.

Historical execution `8969ae5d93168e8529ee584de66095c65322dd8f` recorded twenty
profiles and 352 checks with no unexpected failures or incomplete groups, seven
stored authority configurations, and three detected off-by-one mutants. The
profile mutant failed both suspension and deactivation. Owned database/role
cleanup completed. This evidence predates the integrated repair and is not
relabeled as proof for its head. The original external drill findings and their
separate historical provenance remain in the linked findings document.

Verification commands (repository root unless noted):

```sh
backend/.venv/bin/python -m unittest scripts.test_admin_api_drill scripts.test_external_api_drill
PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m pytest backend/tests/test_behavior_ownership.py backend/tests/test_ci_lane_catalogue.py -q
python3 scripts/check_commitrail_records.py --base-ref origin/main
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
```

Run both entry points through the [isolated drill commands](../../docs/engineering/external-api-drill.md)
with distinct report/metadata paths and fresh databases. Inspect exact target,
clean worktree, source hashes, result, failure groups and cleanup separately.
Hosted Backend remains the full-suite/coverage authority. A completed bounded
drill does not complete the remaining all-field audit or MCP capability handoff.
