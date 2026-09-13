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
live runtime proof. This proposal is reconciled with main `016061f1`.

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
- Human review focus: credential contract, maintainer API-list handoff and joint catalogue freeze, and completeness of the conformance/release proof.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
| --- | --- | --- | --- |
| Current process followed | CONTRIBUTING.md, Commitrail template and planning skill inspection | One overview, one record and one index row | Human agreement remains on the PR |
| Identity scope distinguished | Both supplied Flow HTML design records | Human baseline and future agent limits recorded | Live issuer integration is unproved |
| Changes remain planning-only | `git diff --stat origin/main`; `git diff --check origin/main` | PASS: three planning/navigation files; no whitespace errors | No runtime execution is claimed |
| Wording follows repository rules | `python3 scripts/check_stale_workstream_wording.py` | PASS: stale wording check passed | Document scan only |
| Markdown links resolve | `python3 scripts/check_markdown_links.py` | PASS: three changed Markdown files checked | Does not prove remote service availability |
| Commitrail structure is valid | `/opt/homebrew/Caskroom/miniforge/base/bin/python3.12 scripts/check_commitrail_records.py --base-ref origin/main` | PASS: committed planning records passed validation | Existing macOS tooling uses markdown-it-py 3.0.0, not the pinned Linux environment; hosted Agent Gates remains separate proof |

## Review findings

The maintainer's PR #401 addendum confirms in-repository independent packaging
and the human-only 27-tool release. The overview now includes the exact dispatch
path, serialization and retry rules, ten conformance suites, contract-drift
checks and the real HTTP/API/PostgreSQL parity drill. These are future acceptance
requirements, not executed runtime evidence. Credential transport remains
unresolved. The maintainer subsequently confirmed that authorized declared API
response fields are allowed, including values also present in the request;
credentials remain forbidden and sensitive content stays out of diagnostics.
The overview records this confirmed policy, conditional `Mcp-Name` requirements,
and `Cache-Control: no-store` for authenticated success/error responses with
proxy/CDN and caller-isolation tests. It also records the maintainer-owned API
list as a dependency: map and jointly freeze the catalogue after the handoff,
without independently reconstructing the list. These changes address the
related CodeRabbit inventory, caching and header findings at the planning level;
no runtime conformance or completed inventory is claimed.

CodeRabbit identified evidence cells describing required checks instead of
their observed outcomes. The table now records the executed check results and
the local tooling limitation. The overview also restores the fuller review
document, including examples and test explanations, while retaining the current
Commitrail structure and main-reconciliation findings.

The initial prose could imply that token exchange was a selected solution.
The overview now leaves the MCP-to-API credential contract explicitly
unresolved and requires owner agreement. The external designs do not provide
an implemented exchange API. Independent reviewer conclusions, when available,
belong to the PR and must not be inferred from this correction.

## Reconciliation

- Current-source reconciliation: main `016061f1` includes PR #400 public proposal review, pre-submission approval, correction and manual dispatch. Account for its API/schema changes in the binding inventory without expanding the agreed 27 tools. Recheck PR #395 and other concurrent owner work before implementation.
- Roadmap impact: none; this records a proposal without changing any product capability or activating an implementation. No no-op roadmap edit.
- Next usable boundary: maintainer API-list handoff, exact tool mapping and joint catalogue freeze, agreed credential contract, then a concrete foundation change record.
- Remaining risks: unresolved resource registration, changing API schemas and unavailable live identity proof. These are questions for review, not accepted runtime risks.
