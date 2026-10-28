# WS-GHPROOF-001-04 — Forge-neutral facts read in POST evaluation

- Initiative: WS-GHPROOF-001
- Durable disposition: Complete
- Intended merge outcome: For a selected POST binding that opts into forge facts, WorkStream reads the claimed change's `workstream.forge_change_facts.v1` facts from the configured repository through the forge facts port and places them in the checker request input; forge failures end as recoverable infrastructure failures and never pass. The port is forge-neutral, with GitHub as its only provider.

## Intent

Chunk 03 made the checker compare proofs with facts, but no production path
supplied them, so every evaluation failed with `facts_missing`. This change
supplies them. Owner decision 21 (28 October 2026) also requires that
WorkStream not be coupled to GitHub: chunk 02's GitHub-named port is replaced
by a forge-neutral one before any caller depends on it.

## Current behavior

- `app/interfaces/github_facts.py` defines a GitHub-specific port and
  `workstream.github_facts.v1` value; nothing calls it.
- `SelectedPostSubmitProcessor` never reads facts.
- The GitHub adapter's per-request timeouts did not bound a whole read: a slow
  response could run past `github_facts_total_deadline_seconds`, and facts
  finished after the deadline were still returned (Codex review finding on
  PR #682).

## Bounded change

### Allowed

- `backend/app/interfaces/forge_facts.py` (replaces `github_facts.py`).
- `backend/app/adapters/github/` (maps GitHub into the neutral facts; absolute
  time limit), `backend/app/adapters/checkers/__init__.py` and
  `backend/app/adapters/tasks/__init__.py` (composition).
- `backend/app/modules/checkers/api/external_policy.py`,
  `selected_post_submit_execution.py`, `execution.py`.
- Tests: `test_github_facts_adapter.py`, `checkers/external/test_policy.py`,
  `checkers/external/test_selected_post_submit.py`.
- Ownership catalogue entries for the renamed port; `.env.example`; the
  runbook, roadmap and initiative records.

### Not allowed

- Checker network access, the checker service, ART custody of facts (05),
  hosted credentials (06), lifecycle routing, account pausing or overrides
  (07), Harnessy's proof format, a second forge provider.

## Design and decisions

- **Forge-neutral port (decision 21).** Capability `forge_facts`; provider key
  is the forge name (`github`). `ForgeChangeFacts` carries `forge`,
  `repository`, `change_number`, `change_url`, the change state, author,
  reviews (lowercase neutral states; reviewer `kind` user, bot or other),
  changed files (`path`, `previous_path`), and required checks with
  `required_producer`, `judged` results (`producer`, `sha`) and `run_url`.
  A provider that cannot prove a fact reports null, and the checker fails
  closed on it. A `success` with no judged result is invalid. Commit names may
  be SHA-1 or SHA-256. GitHub-specific mapping (App ids become
  `github_app:<id>`, the Actions run URL, the canonical pull request URL that
  GitHub's `html_url` must equal) lives only in the GitHub adapter. Settings
  keep GitHub names because they configure the GitHub provider.
- **Selection.** A binding selects facts with `workstream_forge_facts_version:
  "v1"`, a supported `forge`, a canonical `repository` and a `base_branch`,
  validated when the binding is locked; the published configuration schema
  must declare the selection key, as for evaluation context (#677). PRE
  bindings cannot select it.
- **Which change.** The worker reads `proof.json` (at most 64 KiB, listed as a
  file in the verified manifest) and its `pr_url`, parses it with the single
  `parse_change_url(forge, url)`, and reads facts only when the repository
  equals the configured one (case-insensitively), always naming the configured
  repository. A missing, oversized, malformed or foreign claim, or a change the
  forge does not have, yields no facts and the checker fails with
  `facts_missing`. Integrity errors reading the verified file propagate.
- **Failures.** Unavailable or inconsistent forge reads, credential or
  permission refusal, missing required checks, an unconfigured or unknown
  provider, and no resolver all end as `implementation_unavailable`; protocol
  and incomplete reads as `invalid_output`. Both are infrastructure failures an
  Operator can retry; the checker never runs, so nothing passes.
- **Time.** The provider wraps the whole read in an absolute timeout and
  discards facts completed after its deadline. The selected POST budget
  reserves 120 seconds (the settings maximum) per binding that selects facts.
- **Composition.** A lazy resolver from the forge facts factory is passed to
  the delivery and reconciliation executors; a provider is constructed only
  when a binding selects it.
- Rejected: keeping GitHub names with a later rename (decision 21), a
  compatibility alias for `github_facts`, a project-level repository setting,
  reading facts for the repository named in the claim.

## Acceptance criteria

- [x] Selected facts reach the checker request input under `forge_facts`, and
  the request input digest binds them.
- [x] Unusable claims (no proof, invalid JSON, deep nesting, non-object, no
  URL, another repository, a trailing slash, another forge's URL) read no
  facts; an unselected binding never calls the resolver.
- [x] Every forge failure class maps to its infrastructure code and the
  checker does not run.
- [x] Selection is rejected for wrong version, unsupported forge, invalid
  repository or branch, PRE phase, or an undeclared schema key; the budget
  reserves the facts read.
- [x] The GitHub provider emits neutral facts, including account kinds, review
  states, both judged results of an unbound check and the canonical run URL,
  and rejects a non-canonical pull request URL.
- [x] A stalled or late read raises facts-unavailable; both regressions fail
  on the previous adapter.

## Risk and review routing

- Risk class: L1. It supplies the evidence automatic FinalAcceptance relies on.
- Required reviewers: security, architecture, QA.
- Human review focus: which repository is read, every failure ending as
  infrastructure and never as a pass, the neutral facts shape, and the budget.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Adapter, policy and processor behavior | `pytest tests/test_github_facts_adapter.py tests/checkers/external/test_policy.py tests/checkers/external/test_selected_post_submit.py` (macOS, Python 3.12, outside the Linux lockfile) | 128, 25 and 30 passed; the 2 database-backed tests need CI | Database-backed and Linux-only suites run in CI |
| No regression in checker suites | `pytest tests/test_github_facts_adapter.py tests/checkers/` with and without this change | Identical failure set (42 environment failures: Postgres and Linux sockets) | CI is authoritative |
| Deadline regressions are discriminating | New deadline tests against the previous adapter | Both fail | — |
| Lint | `ruff check` on changed Python files | Pass | — |

## Reconciliation

- Builds on chunk 03 (PR #683), reworked to the same neutral contract.
- Roadmap: the agent-loop entries now say POST evaluation reads forge facts;
  hosted credentials, custody and guide bindings remain.
- Next usable boundary: chunk 05 (durable custody) and chunk 06 (hosted
  credentials and end-to-end drill).
- Remaining risks: until chunk 07, a protected-path change fails instead of
  waiting for human acceptance; Harnessy's proof still names `pr_url`.
