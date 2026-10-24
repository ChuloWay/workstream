# WS-GHPROOF-001-03 — Harnessy proof checker GitHub comparison mode

- Initiative: WS-GHPROOF-001
- Durable disposition: Complete
- Intended merge outcome: The networkless `harnessy.work_proof` checker compares `proof.json` with WorkStream-supplied `workstream.github_facts.v1` facts when its binding configuration names a GitHub repository and base branch, reporting one error finding per mismatch, and its v2 registry bodies validate that configuration.

## Intent

A hand-written `proof.json` passes today. Once WorkStream supplies GitHub facts
(chunk 04), this mode makes a faked proof fail, while the checker stays
networkless and credential-free.

## Current behavior

- `external_checkers/harnessy_proof/checker.py` checks only proof shape and
  ignores the request `configuration` and `input`.
- `external_checkers/harnessy_proof/publish_local.py` publishes
  `{"type": "object"}` configuration and input schemas, default version `v1`.
- `docs/engineering/local-agent-loop.md` documents shape mode only.

## Bounded change

### Allowed

- `external_checkers/harnessy_proof/checker.py`, `publish_local.py` (standard
  library only).
- `backend/tests/checkers/external/test_harnessy_proof_checker.py` (already in
  the lane catalogue).
- `docs/engineering/local-agent-loop.md` sections on publishing and on what the
  proof checker checks.

### Not allowed

- Backend runtime, POST wiring, the GitHub adapter (chunk 02), checker network
  access, the checker service, ART custody, or Harnessy's proof format.

## Design and decisions

- **Input shape.** WorkStream places the facts object in the request `input`
  under `github_facts`, beside the normalized POST input fields, so the request
  digest binds them. The object is exactly chunk 02's
  `GitHubPullRequestFacts.model_dump(mode="json")`: `schema_version`,
  `repository`, `pull_request_number`, `state`, `merged`, `merge_commit_sha`
  (null unless merged), `base_ref`, `head_sha`, `required_checks`
  (`name`, `app_id`, `conclusion`), `fetched_at` and `responses`.
- **Mode selection.** Configuration `{}` with no facts is shape mode, unchanged.
  Configuration `{"github_repository": "owner/name", "base_branch": "<branch>"}`
  requires facts. Facts without configuration are compared except the
  configured repository and base branch.
- **Findings.** Shape rules still run. Each mismatch is one `error` finding with
  code `harnessy.proof.github.<name>`: `repository`, `base_branch`, `pr_url`,
  `pr_repository`, `pull_request_number`, `merged`, `merge_commit_sha`, one
  `required_check` per non-success check, `facts_missing`, `facts_invalid` and
  `configuration`. Repository comparisons are case-insensitive, as GitHub
  names are; the commit SHA is compared in lower case. GitHub-provided check
  names in messages are bounded to 200 printable characters.
- **Fail closed.** Required but missing or malformed facts produce an error
  finding and a `failed` verdict, never a pass. Chunk 04 maps a facts-fetch
  failure to an infrastructure failure before the checker runs, so a GitHub
  outage does not become a contributor-visible failure.
- **Registry schemas.** POST `configuration_schema` accepts `{}` or both keys
  together (`dependentRequired`, no other keys, repository pattern). PRE accepts
  only `{}` because PRE never has facts. POST `input_schema` constrains
  `github_facts.schema_version` when present; the checker validates the rest.
- **Version.** `publish_local.py` defaults to capability version `v2`, because
  the registry entry for `v1` is immutable and the behavior and schemas changed.
- Rejected: a second ART mount for facts (owner decision), and making
  `github_facts` required in the POST input schema (it would break shape-mode
  bindings).

## Acceptance criteria

- [x] A proof matching the facts passes.
- [x] Each mismatch (repository, PR repository, PR number, PR URL form, merged,
  merge commit SHA, base branch) reports exactly its finding.
- [x] Each failed, missing or pending required check reports its own finding.
- [x] Required facts that are missing or malformed fail; incomplete
  configuration fails.
- [x] Shape mode is unchanged; `main()` passes configuration and input through.
- [x] Published v2 registry bodies validate through
  `ExternalCheckerRegistrySpec` and accept or reject configuration and input as
  documented.

## Risk and review routing

- Risk class: L1, it changes acceptance evidence for automatic FinalAcceptance
  once wired.
- Required reviewers: security, QA, documentation.
- Human review focus: the finding set, failing closed on missing facts, and
  strict `success` for required checks.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Comparison rules and result contract | `pytest tests/checkers/external/test_harnessy_proof_checker.py` | 56 passed | Facts shape agreement with chunk 02 is documented, not cross-tested; chunk 04 should add that test |
| Lint | `ruff check` on the test module and `external_checkers/harnessy_proof/` | Pass | — |
| Docs | Markdown link and stale wording checks | Pass | — |

The image was not rebuilt or run: Docker was out of scope for this change.

## Review findings

None recorded.

## Reconciliation

- Current-source reconciliation: based on WS-GHPROOF-001-01 over `main` after
  PR #674; independent of chunk 02.
- Roadmap: no impact. The local agent loop keeps shape mode until chunk 04
  supplies facts, so its stated trust limit is unchanged.
- Next usable boundary: chunk 04 POST wiring.
- Remaining risks: until chunk 04, configuring comparison mode fails every POST
  check with `facts_missing`.
