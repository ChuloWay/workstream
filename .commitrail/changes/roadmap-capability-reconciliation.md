# Reconcile capability summaries with delivered work

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Current roadmap summaries, dependency branches and MCP navigation agree with merged capabilities; contribution instructions require proportionate same-PR reconciliation.

## Intent

Readers must distinguish implemented, publicly exposed and deployed behavior
without reconstructing old PRs. Repeated summaries have drifted: MCP packaging
is delivered, guide setup has public operations, and acceptance has two triggers.

## Bounded change

Allowed: `docs/roadmap_status.md`, `AGENTS.md`, `CONTRIBUTING.md`,
`.commitrail/INDEX.md`, the current WS-MCP-002 overview and first change record,
and this record. No product code, policies, tests, CI, historical archives,
new automation, approval gates or additional roadmap files.

## Design and decisions

Reconcile against merged PRs 418 and 430, the MCP package/workflow, public guide
routers, hidden activation and existing shared acceptance contracts. Keep one
capability ledger, concise summaries and links to detailed evidence. Preserve
existing historical evidence rather than deleting it or copying it into more
status pages. Clarify the existing review obligation instead of adding a gate
or a second post-merge documentation PR.

## Acceptance criteria

- Roadmap distinguishes public guide setup from hidden terminal activation.
- The dependency map shows true/human and false/automated branches converging
  on shared acceptance; neither planned branch is claimed live.
- MCP one-tool packaging is delivered; deployment and remaining tools are not.
- MCP current records and index agree without marking the whole initiative complete.
- Instructions require affected summaries, diagrams, next boundaries and
  navigation to agree, with no-op edits and transient state still prohibited.
- Existing links and preserved historical evidence remain accessible.

## Risk and review routing

- Risk class: L2 (documentation reconciliation; no product semantics change).
- Required reviewers: documentation, with contribution-instruction clarity.
- Human review focus: accurate exposure/deployment distinctions and simple
  maintenance expectations, not new process machinery.

## Verification

Compare claims to merged code and contracts; run Markdown links, stale wording,
Commitrail validation and diff checks. Review counterexamples: an implemented
but undeployed tool must not become planned, and false-policy acceptance must
not gain a human-review prerequisite. No local spreadsheet exports are present.
Hosted checks and exact-head review evidence belong in the PR.

## Reconciliation

Current main includes ARCH-03B9. ARCH-03C remains the next product integration
boundary; this correction does not start it. MCP deployment and later bindings
remain separately bounded work. No runtime certification is added by these docs.
