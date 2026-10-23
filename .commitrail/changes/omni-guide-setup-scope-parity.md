# Omni guide setup scope parity

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: OmniCoreAgent guide setup generates only supported checker specification fields and corrects known invalid output within one bounded attempt; the current checker-only setup API, worker, and lane-catalogue proofs also pass together.

## Intent

The first hosted guide setup drill needs useful PRE/POST checker proposals from either registered inference runtime. The merged OpenAI SDK adapter restricts generated output and permits bounded correction, while the Omni adapter still prompts with the historical result schema and terminalizes malformed draft or final output immediately. Shared final validation rejects out-of-scope output; this change does not alter acceptance authority.

The merged checker-only setup contract also exposed stale API source-evidence, Celery test-state, and shared test-catalogue assertions. Their focused repairs are included in this one integration PR; source PRs [#666](https://github.com/Flow-Research/workstream/pull/666) and [#667](https://github.com/Flow-Research/workstream/pull/667) retain the original review history.

## Bounded change

- Allowed: `backend/app/adapters/project_agents/omnicore_agent.py`, the restricted-schema helper in `backend/app/adapters/project_agents/compilation_draft.py` only for the native Pydantic schema shape, actual-SDK tests in `backend/tests/test_omnicore_agent_sdk.py`, `backend/tests/test_api_contract_e2e.py`, `backend/tests/projects/guide_compilation/test_live_worker.py`, `backend/tests/projects/guide_compilation/test_worker_topology.py`, the independent fingerprint in `backend/tests/test_ci_lane_catalogue.py`, and this combined record.
- Prohibited: project-agent contract or storage changes, authorization/approval changes, checker execution changes, provider route or retry changes, production Celery changes, CI lane membership/selection/workflow changes, live inference, credentials, and remote product mutations.

## Acceptance criteria

- Acceptance: Omni presents the restricted generated schema in draft and review; a known invalid draft or final response receives safe bounded correction in the same attempt; corrected output must satisfy the shared contextual validation and reopen assigned originals in its phase; exhausted corrections fail closed; total timeout, model turns, tool quotas, provider attempts, circuit facts, and native cleanup stay bounded. Actual SDK boundary tests demonstrate correction, scope rejection, and failure exhaustion.
- Integration proof: the API drill verifies exact original references with an empty checker inventory; the worker fixture restores broker mode before the guarded hard-timeout case; the independent lane fingerprint matches the merged shared member without changing lane membership; the combined Backend and public API drills complete on one head.

## Risk and review routing

- Risk class: L1, untrusted model output and guarded external runtime behavior.
- Verification: focused actual SDK and API tests, ordered worker regressions, full Backend and public API drills on the combined head, format/lint/type checks as available; diff, Commitrail, stale wording, Markdown links, and roadmap impact inspection.
- Required review: architecture, security, QA, test delta, and CI integrity for the test-custody and catalogue changes. Plan review preceded product code.
- Human review focus: restricted schema parity, distinction between corrected known output and provider retry, aggregate turn accounting and source reopening; exact API source evidence, Celery broker-mode restoration, and the independent shared-lane fingerprint.

## Plan

1. Reuse `generated_compilation_schema`, `CompilationDraftParser`, `contextual_output_issue`, and `validate_project_guide_runtime_result` from existing owners.
2. Keep one guarded transport and attempt deadline. Count each new logical model request across fresh Omni agents. For draft and review, pass only that phase's unused turns to the next agent; refuse correction with zero turns. Preserve the draft/review split and existing physical provider-attempt ceiling of `maximum_turns * OMNICORE_PROVIDER_ATTEMPTS` across native retries and corrections.
3. Keep one capability instance so tool-call and output quotas stay aggregate. Reset a local source-open set before every native run; count only successful offset-zero reads that returned text or proved an empty original, as in the OpenAI adapter. Validate each completed candidate against that run's source-open set. On known invalid output, build a bounded correction prompt containing safe issue codes and the original setup context. Allow at most two corrections total; propagate ambiguous SDK/provider failures without replay.
4. Test corrected draft, corrected final, exhaustion of correction/turn budget, provider retry versus correction, and retained aggregate tool quota through the real Omni SDK against a synthetic loopback provider. Freeze and review the exact clean candidate.

## Plan review

Initial L1 review blocked on explicit aggregate-turn and per-run source proof. The revised algorithm above addresses both before product code.

The first SDK run exposed a shape difference: OpenAI's strict SDK schema requires `setup_notes`, while Pydantic's native schema leaves it optional. The existing restriction helper unconditionally removed that field from `required`. Its scoped repair will remove it only when present, preserving identical output restriction for both schema sources.

## Evidence

The actual Omni SDK loopback tests exercise valid draft/review, exact restricted schema presentation in both initial phase prompts, native provider retries, malformed output, correction of draft and final output including a schema-valid contextual rejection, historical-scope rejection, cross-phase correction and logical-turn exhaustion, per-run source reopening, and retained tool quotas. A pre-existing foreign-source fixture now terminates after the first failed draft read; the second review read is no longer reached because every draft is context validated before review.

- Omni SDK test file: 55 passed after the focused review repair, with one upstream Pydantic warning. An earlier concurrent rerun crashed inside the installed `tiktoken` native extension after 30 passing cases; the final complete file rerun passed.
- Shared draft/parser suite in the mutually exclusive OpenAI SDK environment: 24 passed. Its initial execution in the Omni environment could not import the intentionally absent `agents` package; this is an environment extra boundary, not a test failure of the helper.
- Ruff lint and format checks passed for changed Python files. `git diff --check`, stale wording, and changed Markdown link checks passed.
- No paid model inference, remote product mutation, or hosted proof was performed.

Roadmap assessment: no new public route, enabled runtime, deployed provider, or setup capability is introduced. The current capability ledger already describes strict checking in both phases and separates local qualification from hosted operation. This PR repairs the Omni implementation to honor that existing claim; no roadmap text or spreadsheet export changes are needed.

## Source repair evidence and reconciliation

- [#666](https://github.com/Flow-Research/workstream/pull/666) identified a stale API-drill assertion that indexed `result.requirements[0]` after checker-only setup correctly returned no project checks. The repair retains one exact neutral read and invocation, asserts the empty requirement inventory, and checks source item, original document version, and digest directly. The pre-fix `IndexError` was reproduced; 58 focused API/setup tests passed, and independent mutations to each source-reference field failed the assertion.
- [#667](https://github.com/Flow-Research/workstream/pull/667) traced a prefork timeout regression to eager Celery settings left on a cached task app by an earlier test fixture. The repair uses existing `sync_task_settings` at fixture entry and exit, asserts broker mode before the hard-timeout case, and preserves provider-once, acknowledgement, and durable-uncertainty checks. The baseline ordered pair had one pass and one `DID NOT RAISE` failure; the repaired pair passed. Both affected modules passed 25 tests with only the separate Redis probe deselected in that focused run. A full isolated `project_lifecycle_c` lane passed 436 nodes with no skips or deselections using PostgreSQL, Redis, and MinIO; hosted aggregate proof remains required.
- The same #667 investigation found the independent shared-lane fingerprint lagged the merged `test_setup_checker_scope.py` member. Removing only that member reconstructs the old 258 count and digest; the corrected assertion expects 259 members and the current digest without changing lane membership. Its 58-test module passed, and a missing-member mutation failed the assertion.
- Combined hosted preflight and `shared_foundations_c` exposed one additional test-structure failure: the broker-mode guard grew the prefork hard-timeout test from 119 to 121 lines. Removing its redundant local `uuid4` and `TaskPool` imports reuses the existing module imports, preserves every timeout, acknowledgement, invocation and durable-fence assertion, and avoids introducing structural debt or changing the frozen ledger. The full structural validator passed, and the ordered eager-delivery/prefork-timeout pair passed both tests on isolated PostgreSQL. The first local validator process exited 139 without diagnostics; its complete faulthandler rerun passed without a crash.

The source PRs retain their original review history; their repair changes were cherry-picked into this branch under new commit IDs. Their standalone new records are consolidated here so the single combined PR has one bounded Commitrail record. No product capability, public route, runtime registry, or hosted deployment claim changes.
