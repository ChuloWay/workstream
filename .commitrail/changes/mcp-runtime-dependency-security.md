# MCP Runtime Dependency Security — Resolve Current Alerts

- Initiative: `None`
- Durable disposition: `Planned`
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

- [ ] A private reviewed inventory maps every MCP snapshot alert to its manifest, selected version, direct/transitive relationship, runtime/dev scope, available fix, affected owner boundary, and disposition without exposing dashboard-only evidence publicly.
- [ ] Every MCP alert in the issue snapshot resolves outside its affected range using a supported patched version corroborated by canonical advisories.
- [ ] `uv` regenerates the lock reproducibly through a package-specific upgrade, with no manual lock editing, unrelated dependency additions, or unrelated version churn.
- [ ] A fresh isolated environment installs from the frozen MCP lock with runtime and development dependencies.
- [ ] Existing MCP authentication, gateway, protocol, packaging, lint, typecheck, unit, contract-drift, and hosted integration checks preserve required behavior without skips or weakened assertions; the MCP frozen-lock package/container lanes provide exact adapter-lock custody while pip-resolved backend integration remains supplemental.
- [ ] The final branch reconciles current `main` and open PR #518 before push so its MCP package work is neither overwritten nor misrepresented.
- [ ] Public records and PR text contain no credentials, private dashboard links, private alert identifiers, or non-public exploit detail.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `security`, `qa`, and `ci_integrity`
- Human review focus: Minimal resolver delta, canonical patched range, transitive JWT compatibility in the MCP SDK graph, frozen install reproducibility, PR #518 reconciliation, and absence of CI weakening.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Every snapshot alert has a reviewed disposition | Private inventory reconciled to the creation-time snapshot, current lock graph, and canonical advisories | Pending | Private evidence remains outside Git and public PR text |
| Plan is bounded and executable | Internal plan review against the base lock, SDK owner graph, and issue #565 contract | Pending | No runtime proof before implementation |
| Lock has only intended resolver changes | `uv lock --check` plus base/head package and lock diff inspection | Pending | Canonical advisories and dashboard must be reconciled again after merge |
| Patched graph installs cleanly | Fresh temporary `UV_PROJECT_ENVIRONMENT` with `uv sync --frozen --extra dev` | Pending | Hosted platform and integration matrices remain CI custody |
| MCP behavior remains compatible | Existing auth, gateway, protocol, packaging, contract-drift, lint, mypy, and unit checks from the MCP frozen lock; hosted package/container and integration checks | Pending | Pip-resolved backend integration does not establish exact backend-lock custody |

## Review findings

Pending implementation and exact-head review.

## Reconciliation

- Current-source reconciliation: Based on `main` at `82a46ff3c5f21e3cdf762cf505d61d84531a7c80`; PR #518 overlaps the MCP package area and must be reconciled before the final push.
- Roadmap impact: None. This repair changes a selected transitive dependency version without changing an MCP capability, exposure, completed scope, remaining product gate, or next product dependency.
- Next usable boundary: Merge this MCP repair, re-read the default-branch alert dashboard, and retain explicit ownership of any remaining snapshot alert.
- Remaining risks: Pending implementation evidence and exact-head review.
