# WS-MCP-002-PLAN: Review the MCP Adapter Approach

- Initiative: WS-MCP-002
- Durable disposition: Planned
- Intended merge outcome: Record a bounded MCP proposal and its unresolved decisions before runtime implementation.

## Intent

The maintainer requested that the proposed MCP approach be reviewed in a
Commitrail PR. [The overview](OVERVIEW.md) records the design and proposed PR
boundaries in simple language.

## Current behavior

Workstream owns authorization and lifecycle behavior through its backend.
The [roadmap](../../../docs/roadmap_status.md) distinguishes live, hidden and
planned capabilities. The previous MCP PR is closed. The supplied 27-tool
design and human/agent identity documents describe intended integrations, not
live runtime proof. This proposal is reconciled with main `d9a66470`.

## Bounded change

### Allowed

- This planning record and `OVERVIEW.md` in this initiative directory.
- One WS-MCP-002 navigation row in `.commitrail/INDEX.md`.

### Not allowed

- Application, dependency, authentication, API, database or workflow changes.
- Activating hidden endpoints or future agent delegation.
- Treating this proposal as a completed MCP implementation.

## Design and decisions

Use one initiative overview, linked above, and this one change record.
The runtime proposal is a separately deployed HTTP adapter. Alternatives and
open credential decisions are described in the overview. Do not revive the
old multi-file `.agent-loop` process or add a duplicate specification.

## Acceptance criteria

- [x] The proposal explains deployment, API ownership and first-release scope.
- [x] Human v0.1 and future agent behavior are explicitly distinguished.
- [x] Credential transport uncertainty and API drift are visible for review.
- [x] Proposed PR boundaries include tests and concrete release evidence.
- [x] Only planning and navigation files change.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security/auth and docs; review the proposal, not runtime correctness.
- Human review focus: first-release scope, repository placement and credential contract.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
| --- | --- | --- | --- |
| Current process followed | CONTRIBUTING.md, Commitrail template and planning skill inspection | One overview, one record and one index row | Human agreement remains on the PR |
| Identity scope distinguished | Both supplied Flow HTML design records | Human baseline and future agent limits recorded | Live issuer integration is unproved |
| Changes remain planning-only | `git diff --stat origin/main` and `git diff --check` | Required before submission | No runtime execution is claimed |
| Records and links are valid | `python3 scripts/check_commitrail_records.py --base-ref origin/main`; `python3 scripts/check_markdown_links.py` | Required on committed candidate | Tooling/host limits reported in PR |

## Review findings

The initial prose could imply that token exchange was a selected solution.
The overview now leaves the MCP-to-API credential contract explicitly
unresolved and requires owner agreement. The external designs do not provide
an implemented exchange API. Independent reviewer conclusions, when available,
belong to the PR and must not be inferred from this correction.

## Reconciliation

- Current-source reconciliation: AUTH proposal authority merged in main; public proposal routes in PR #400 and setup work in PR #395 remain separate owner work. Recheck them before implementation.
- Roadmap impact: none; this records a proposal without changing any product capability or activating an implementation. No no-op roadmap edit.
- Next usable boundary: agreed credential contract and a concrete foundation change record.
- Remaining risks: unresolved resource registration, changing API schemas and unavailable live identity proof. These are questions for review, not accepted runtime risks.
