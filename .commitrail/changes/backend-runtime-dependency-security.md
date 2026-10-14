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
- `.github/workflows/backend.yml`: use the frozen backend lock in the three existing backend install paths and commands, retaining every job, lane, timeout, service, gate, and fan-in.
- `scripts/test_lightweight_agent_gates.py`: guard exact lock freshness, frozen all-extras installation, frozen command execution, and unchanged gate structure.

### Not allowed

- Runtime source, API contracts, tests, schemas, migrations, authorization, storage semantics, or product lifecycle changes.
- `backend/pyproject.toml` constraint changes unless new resolver evidence first requires a reviewed plan amendment.
- New CI jobs or workflows, path selection, lane or timeout changes, gate relaxation, dependency catalogue changes, unrelated upgrades, manual lock edits, alert dismissal, or public disclosure of private alert evidence.
- MCP adapter dependency changes; they have a separate package boundary and change record.

## Design and decisions

Use the normal `uv` resolver with package-specific upgrades so unaffected locked versions remain fixed. Inspect the resulting package/version set against the base lock and reject unrelated dependency additions or version churn. Preserve the existing manifest ranges because they already admit the supported fixes. A manual lock edit was rejected because it would bypass resolver custody; a combined backend/MCP PR was rejected because their package graphs and behavior evidence differ. The hosted suite must execute this exact graph: pin the already reviewed `uv` version, reject stale manifest/lock pairs with `uv lock --check`, install all extras with `uv sync --frozen --all-extras`, and run every existing backend command through `uv run --frozen`. This narrowly transplants PR #566's frozen-install semantics without its draft path-selection feature; later reconciliation must preserve the lock-freshness check.

## Acceptance criteria

- [x] A private reviewed inventory maps every backend snapshot alert to its manifest, selected version, direct/transitive relationship, runtime/dev scope, available fix, affected owner boundary, and disposition without exposing dashboard-only evidence publicly.
- [x] Every backend alert in the issue snapshot resolves outside its affected range using supported patched versions corroborated by canonical advisories.
- [x] `uv` regenerates the lock reproducibly through package-specific upgrades, with no manual lock editing, unrelated dependency additions, or unrelated version churn.
- [x] A fresh isolated environment installs from the frozen backend lock with all runtime, agent, and development dependencies.
- [ ] Existing authentication/JWT, Alembic, HTTP/storage, lint, and the complete backend suite run from the fresh frozen-lock environment without skips or weakened assertions; pip-resolved hosted backend lanes remain supplemental compatibility evidence rather than exact-lock custody. All existing hosted jobs, ten semantic lanes, timeouts, services, evidence validation, API E2E, and fan-in remain required.
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
| Affected runtime behavior remains compatible | Backend lint plus focused and complete backend tests from the fresh frozen-lock environment, including owned PostgreSQL/S3 resources; pip-resolved hosted backend checks as supplemental compatibility evidence | Frozen-lock authentication/JWT selection: 60 passed; Ruff passed. Complete frozen-lock suite and hosted checks remain pending | Hosted lanes do not currently establish exact backend lock custody |

## Review findings

The exact-head resolver and frozen-workflow implementation reviews found no open findings. Reconciliation against merged PR #567 passed with no blob conflict or scope drift; hosted frozen-lock readiness remains pending.

## Reconciliation

- Current-source reconciliation: Based on `main` at `80be493914392512cb5a7d663b9b7e3ebb1c4ac0`; merged PR #567 authorization, project, and test owners are preserved unchanged, and open dependency PRs were inspected for overlapping lock paths.
- Roadmap impact: None. This repair changes selected dependency versions without changing a capability, exposure, completed scope, remaining product gate, or next product dependency.
- Next usable boundary: Merge this backend repair, re-read the default-branch alert dashboard, and retain explicit ownership of any remaining snapshot alert.
- Remaining risks: Complete-suite execution from this exact frozen lock, hosted checks on the reconciled head, and post-CI exact-head evidence replay remain pending. This repair reuses only PR #566's frozen-install semantics; PR #566 remains independently responsible for draft path selection, and later reconciliation must retain `uv lock --check`.
