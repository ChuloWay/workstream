# MCP Runtime Dependency Security — Resolve Current Alerts

- Initiative: `None`
- Durable disposition: `Complete`
- Intended merge outcome: The independently packaged MCP adapter lock resolves the issue #565 alert snapshot to a supported patched runtime dependency version without changing adapter behavior.

## Intent

Resolve the current MCP adapter runtime dependency alerts before the hosted v0.1 release. The private alert dashboard remains the source of detailed findings; this public record states only the bounded repository outcome and proof needed to review it.

## Current behavior

`mcp_server/uv.lock` selects a transitive runtime dependency version that the private dependency dashboard reports in affected ranges. The owner constraint in the existing MCP dependency graph already permits the supported patched release, so `mcp_server/pyproject.toml` does not require a compatibility or policy change.

## Bounded change

### Allowed

- `.commitrail/changes/mcp-runtime-dependency-security.md`: this standalone intent, scope, evidence, and review record.
- `mcp_server/uv.lock`: resolver-generated update only for the exact affected package and metadata that the selected resolver must regenerate.

### Not allowed

- MCP runtime source, contracts, tool catalogue, tests, API behavior, authorization semantics, or package contents.
- `mcp_server/pyproject.toml` constraint changes unless new resolver evidence first requires a reviewed plan amendment.
- CI or workflow changes, unrelated upgrades, manual lock edits, alert dismissal, or public disclosure of private alert evidence.
- Backend dependency changes; they have a separate package boundary and pull request.

## Design and decisions

Use the normal `uv` resolver with a package-specific upgrade so unaffected locked versions remain fixed. Inspect the resulting package/version set against the base lock and reject unrelated dependency additions or version churn. Preserve the existing owner constraint because it admits the supported fix. A manual lock edit was rejected because it would bypass resolver custody; a combined backend/MCP PR was rejected because their package graphs and behavior evidence differ.

## Acceptance criteria

- [x] A private reviewed inventory maps every MCP snapshot alert to its manifest, selected version, direct/transitive relationship, runtime/dev scope, available fix, affected owner boundary, and disposition without exposing dashboard-only evidence publicly.
- [x] Every MCP alert in the issue snapshot resolves outside its affected range using a supported patched version corroborated by canonical advisories.
- [x] `uv` regenerates the lock reproducibly through a package-specific upgrade, with no manual lock editing, unrelated dependency additions, or unrelated version churn.
- [x] A fresh isolated environment installs from the frozen MCP lock with runtime and development dependencies.
- [x] Existing MCP authentication, gateway, protocol, packaging, lint, typecheck, unit, contract-drift, and hosted integration checks preserve required behavior without skips or weakened assertions; the MCP frozen-lock package/container lanes provide exact adapter-lock custody while pip-resolved backend integration remains supplemental.
- [x] The final branch reconciles current `main` and open PR #518 before push so its MCP package work is neither overwritten nor misrepresented.
- [x] Public records and PR text contain no credentials, private dashboard links, private alert identifiers, or non-public exploit detail.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `security`, `qa`, and `ci_integrity`
- Human review focus: Minimal resolver delta, canonical patched range, transitive JWT compatibility in the MCP SDK graph, frozen install reproducibility, PR #518 reconciliation, and absence of CI weakening.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Every snapshot alert has a reviewed disposition | Private inventory reconciled to the creation-time snapshot, current lock graph, and canonical advisories | Complete; every selected target is outside its affected range | Private evidence remains outside Git and public PR text |
| Plan is bounded and executable | Internal plan review against the base lock, SDK owner graph, and issue #565 contract | Passed with low residual risks | Hosted package/container and integration proof remained pending at plan review |
| Lock has only intended resolver changes | Package-specific `uv lock --upgrade-package pyjwt`; `uv lock --check`; base/head package-set and lock diff inspection | Passed; one transitive package changed version and no package was added or removed | Canonical advisories and dashboard must be reconciled again after merge |
| Patched graph installs cleanly | Fresh temporary `UV_PROJECT_ENVIRONMENT` with `uv sync --frozen --extra dev`; installed-version inspection | Passed | Hosted platform and integration matrices remain CI custody |
| MCP source behavior remains compatible | Frozen-lock Ruff, strict mypy, and non-integration suite locally and in the hosted package lane | Passed: Ruff and mypy clean; 367 passed, with the two custody-split tests executed separately below | Standalone wheel resolution remains outside frozen-lock custody |
| Installed wheel and container are independent | Build sdist and wheel; install the wheel in a fresh environment; run `test_package_independence.py` with that interpreter; build and exercise the independent container | Passed locally and in the hosted package lane; the focused wheel test passed | The wheel intentionally resolves from its declared owner constraints rather than claiming lock custody |
| MCP contracts match the backend | Run `test_contract_drift.py` with a backend interpreter supplying live OpenAPI; run hosted real API-to-MCP lifecycle parity | Passed locally and in hosted CI: contract comparison and both isolated lifecycle suites passed | Pip-resolved hosted backend integration is supplemental and does not establish exact backend-lock custody |
| Exact candidate has proportionate review | Combined security, QA, and CI-integrity review bound to the clean candidate tree | Passed with no findings in any track | Standalone wheel installation follows the upstream SDK's broad transitive range; the frozen lock and observed wheel proof selected the patched release |

## Review findings

The bounded plan review passed with low residual risks. It required explicit separation between exact MCP frozen-lock custody and the independently resolved installed-wheel proof, and retained hosted package/container and real-API checks as completion evidence.

The combined exact-candidate security, QA, and CI-integrity review passed with no findings. It independently confirmed a two-file resolver delta, no package-set churn, the canonical patched range, no direct Workstream MCP JWT use, unchanged gateway behavior and CI, and successful frozen-lock package/container plus real-API jobs. Its non-blocking residual is that standalone wheel metadata inherits the upstream MCP SDK's broad transitive JWT range; the frozen lock and observed clean-wheel installation both selected the patched release.

## Reconciliation

- Current-source reconciliation: Merged current `main` at `2c1f7517c285437c6adad27f2c3425212a615373`. Open PR #518 remains at `9243fab6f19b41436f16759d2824c108b047b9f0` and changes MCP package inclusion metadata but does not change dependency constraints or the lock; recheck overlap if it merges before this pull request.
- Roadmap impact: None. This repair changes a selected transitive dependency version without changing an MCP capability, exposure, completed scope, remaining product gate, or next product dependency.
- Next usable boundary: Merge this MCP repair, re-read the default-branch alert dashboard, and retain explicit ownership of any remaining snapshot alert.
- Remaining risks: Post-merge default-branch alert reconciliation remains pending. A future standalone wheel installation could be constrained to another release allowed by the upstream MCP SDK rather than using this lock; the hosted clean-wheel proof selected the patched release.
