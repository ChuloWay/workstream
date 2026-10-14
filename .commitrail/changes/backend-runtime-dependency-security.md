# Backend Runtime Dependency Security — Resolve Current Alerts

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: The backend lock resolves the issue #565 alert snapshot to supported patched runtime dependency versions without changing Workstream behavior.

## Intent

Resolve the current backend runtime dependency alerts before the hosted v0.1 release. The private alert dashboard remains the source of detailed findings; this public record states only the bounded repository outcome and proof needed to review it.

## Current behavior

`backend/uv.lock` selects runtime dependency versions that the private dependency dashboard reports in affected ranges. `backend/pyproject.toml` already permits supported patched releases, so the manifest does not require a compatibility or policy change.

## Bounded change

### Allowed

- `.commitrail/changes/backend-runtime-dependency-security.md`: this standalone intent, scope, evidence, and review record.
- `backend/uv.lock`: resolver-generated updates only for the exact affected packages and metadata that the selected resolver must regenerate.
- `.github/workflows/backend.yml`: use the frozen backend lock in the three existing backend install paths and commands, retaining every job definition, timeout, service, gate, and fan-in while adding only the three measured matrix entries.
- `scripts/test_lightweight_agent_gates.py`: guard exact lock freshness, frozen all-extras installation, frozen command execution, and unchanged gate structure.
- `backend/scripts/test_lane_catalogue.py`: use the existing deterministic partitioner to add one capacity lane inside each saturated shared, project, and task family; remove the superseded hotspot exceptions without moving any node across semantic families.
- `backend/scripts/validate_test_lane_evidence.py`: independently enforce the exact 13-lane count and three shared-S3 owners so catalogue or workflow drift still fails closed.
- `backend/scripts/run_isolated_tests.py`: include shared C in the existing shared-S3 namespace contract so the added lane retains correct MinIO isolation.
- `backend/tests/test_ci_lane_catalogue.py`: prove the 13 lane owners, exact suite union, uniqueness, semantic-family confinement, and rejection of a missing or duplicated lane.
- `backend/tests/test_test_lane_evidence.py`, `backend/tests/test_merge_test_lane_evidence.py`, and `backend/tests/test_isolated_database_runner.py`: update the canonical lane inventory and shared-S3 ownership used by authenticated evidence, aggregate retry, and isolation proofs; retain every validation and failure case.
- `docs/operations_backend_testing.md` and `docs/roadmap_status.md`: describe the current 13-lane hosted proof topology and its unchanged evidence contract without changing product capability claims.

### Not allowed

- Runtime source, API contracts, product behavior tests, schemas, migrations, authorization, storage semantics, or product lifecycle changes.
- `backend/pyproject.toml` constraint changes unless new resolver evidence first requires a reviewed plan amendment.
- New CI job definitions or workflows, path selection, semantic-family changes, more than the three measured capacity lanes, timeout changes, test deletion or skipping, gate relaxation, dependency catalogue changes, unrelated upgrades, manual lock edits, alert dismissal, or public disclosure of private alert evidence.
- MCP adapter dependency changes; they have a separate package boundary and change record.

## Design and decisions

Use the normal `uv` resolver with package-specific upgrades so unaffected locked versions remain fixed. Inspect the resulting package/version set against the base lock and reject unrelated dependency additions or version churn. Preserve the existing manifest ranges because they already admit the supported fixes. A manual lock edit was rejected because it would bypass resolver custody; a combined backend/MCP PR was rejected because their package graphs and behavior evidence differ. The hosted suite must execute this exact graph: pin the already reviewed `uv` version, reject stale manifest/lock pairs with `uv lock --check`, install all extras with `uv sync --frozen --all-extras`, and run every existing backend command through `uv run --frozen`. This narrowly transplants PR #566's frozen-install semantics without its draft path-selection feature; later reconciliation must preserve the lock-freshness check.

The first exact-lock hosted run and its single unchanged failed-job probe both exhausted the retained 1,200-second semantic-lane cap in shared A and project D without an assertion failure, skip, deselection, or cleanup failure; project A passed the probe. The first repairs rebalanced measured whole modules only within the existing shared or project family. They retained complete test membership, coverage, services, commands, authenticated evidence, timeout, and aggregate fan-in. Node-specific exceptions, a timeout increase, repeated retries, or moving a module across semantic families would conceal the capacity defect rather than repair it.

The first reviewed rebalance cleared shared A and nine complete semantic lanes, but project D again reached the cap after 574 of 598 nodes. Its remaining 24 nodes were the lexical tail of `tests/test_projects.py`; they located the capacity boundary rather than a product or module defect. Correct all-phase timing from the successful frozen project C lane attributed 150.38 seconds to its 125 nodes from that module. A supplemental successful main run used the same source and complementary 131 node IDs but a different dependency graph, so its 160.13-second module timing could size the move but could not prove frozen compatibility. The next reviewed repair moved the whole 256-node module from the project C/D candidates to project A/B/C. Measured per-node redistribution estimated receiving-lane wall times near 949, 847, and 1,015 seconds; the subsequent hosted run showed that module-only placement remained insufficient.

The follow-up cleared project D, but a fresh full run placed seven of the nine non-schema lanes at 1,032 seconds or above and timed out shared A, project A, and task B/C. One unchanged failed-job probe distinguished runner variance from capacity: shared A and task B passed, while project A and task C repeated the cap with zero skips, deselections, assertion failures, or cleanup failures. The exact successful and partial evidence puts the shared family at 2,274 seconds, the project family above 4,396 seconds, and the task family above 3,081 seconds. Add shared C, project E, and task D and repartition every node through the existing SHA-256 owner rule across its unchanged family. Exact current-node timing maps projected maxima of 773, 864, and 805 seconds for shared, project, and task respectively before 20–54 seconds of observed setup and runner overhead. The fresh hosted run remains decisive; these measurements bound the plan rather than guarantee a result.

## Acceptance criteria

- [x] A private reviewed inventory maps every backend snapshot alert to its manifest, selected version, direct/transitive relationship, runtime/dev scope, available fix, affected owner boundary, and disposition without exposing dashboard-only evidence publicly.
- [x] Every backend alert in the issue snapshot resolves outside its affected range using supported patched versions corroborated by canonical advisories.
- [x] `uv` regenerates the lock reproducibly through package-specific upgrades, with no manual lock editing, unrelated dependency additions, or unrelated version churn.
- [x] A fresh isolated environment installs from the frozen backend lock with all runtime, agent, and development dependencies.
- [ ] Existing authentication/JWT, Alembic, HTTP/storage, lint, and the complete backend suite run from the fresh frozen-lock environment without skips or weakened assertions; pip-resolved hosted backend lanes remain supplemental compatibility evidence rather than exact-lock custody. All existing hosted jobs, 13 semantic lanes, timeouts, services, evidence validation, API E2E, and fan-in remain required.
- [ ] The measured lane repair retains every one of the original 8,899 nodes exactly once, accounts separately for any new structural proof nodes, reports the fresh canonical total, and has zero skips or deselections across 13 lanes under the 1,200-second cap and each node's existing shared, project, task, or schema family.
- [ ] Public records and PR text contain no credentials, private dashboard links, private alert identifiers, or non-public exploit detail.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `security`, `qa`, and `ci_integrity`
- Human review focus: Minimal resolver delta, canonical patched ranges, JWT verification compatibility, backend network/storage and migration behavior, frozen install reproducibility, and absence of CI weakening.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Every snapshot alert has a reviewed disposition | Private inventory reconciled to the creation-time snapshot, current lock graph, and canonical advisories | Passed | Private evidence remains outside Git and public PR text |
| Plan is bounded and executable | Internal plan review against the base lock, owners, and issue #565 contract | Passed | No runtime proof before implementation |
| Lock has only intended resolver changes | `uv lock --check` plus base/head package and lock diff inspection | Passed on the reconciled head; four intended package selections changed and no package was added or removed | Canonical advisories and dashboard must be reconciled again after merge |
| Patched graph installs cleanly | Fresh temporary `UV_PROJECT_ENVIRONMENT` with `uv sync --frozen --all-extras`, followed by installed-distribution and import inspection | Passed on the reconciled head | Hosted platform matrix remains CI custody |
| Affected runtime behavior remains compatible | Backend lint plus focused and complete backend tests from the fresh frozen-lock environment, including owned PostgreSQL/S3 resources; pip-resolved hosted backend checks as supplemental compatibility evidence | Frozen-lock authentication/JWT selection: 60 passed; Ruff passed. The hosted workflow runs the complete suite from the exact frozen lock; GitHub checks retain its execution evidence | Pip-resolved runs predating this change are supplemental compatibility evidence only |
| Exact-lock lane capacity is bounded without weakening the suite | Authenticated lane manifests, complete phase timings, cleanup records, structural ownership tests, and a fresh complete hosted run | The module rebalances proved insufficient even though they cleared project D. The final bounded plan adds one lane per saturated semantic family and retains every timeout, service, command, evidence check, and fan-in. Focused catalogue/evidence/namespace checks passed (149 tests), and lightweight workflow gates passed (22 tests and 92 subtests) from the isolated frozen environment | Original-node custody, the fresh canonical total, projected margin, and complete compatibility remain subject to exact-head manifest replay and hosted proof |

## Review findings

The exact-head resolver and frozen-workflow implementation reviews found no open findings. Reconciliation against merged PR #567 passed with no blob conflict or scope drift. `WS565-QA-01`, `WS568-CI-01`, and `WS568-REC-01` are closed. Both focused lane-capacity CI-integrity and test-delta plan reviews passed with no findings; the second review withdrew an incomplete teardown-only timing rationale and accepted the corrected all-phase evidence. GitHub checks remain the transient readiness record.

## Reconciliation

- Current-source reconciliation: Based on `main` at `80be493914392512cb5a7d663b9b7e3ebb1c4ac0`; merged PR #567 authorization, project, and test owners are preserved unchanged, and open dependency PRs were inspected for overlapping lock paths.
- Roadmap impact: CI topology only. The current capability ledger records the expanded 13-lane frozen-lock proof topology; product capability, exposure, completed scope, remaining product gates, and product dependencies are unchanged.
- Next usable boundary: Merge this backend repair, re-read the default-branch alert dashboard, and retain explicit ownership of any remaining snapshot alert.
- Remaining risks: Default-branch alert reconciliation remains a post-merge operational step. This repair reuses only PR #566's frozen-install semantics; PR #566 remains independently responsible for draft path selection, and later reconciliation must retain `uv lock --check`.
