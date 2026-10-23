# Omni guide setup scope parity

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: OmniCoreAgent guide setup generates only the supported checker specification fields and can correct known invalid model output within one bounded attempt, matching the OpenAI SDK runtime's behavior.

## Intent

The first hosted guide setup drill needs useful PRE/POST checker proposals from either registered inference runtime. The merged OpenAI SDK adapter restricts generated output and permits bounded correction, while the Omni adapter still prompts with the historical result schema and terminalizes malformed draft or final output immediately. Shared final validation rejects out-of-scope output; this change does not alter acceptance authority.

## Bounded change

- Allowed: `backend/app/adapters/project_agents/omnicore_agent.py`, the existing restricted-schema helper in `backend/app/adapters/project_agents/compilation_draft.py` only to accept the native Pydantic schema shape, focused actual-SDK tests in `backend/tests/test_omnicore_agent_sdk.py`, this record, and factual current setup documentation if a capability claim changes.
- Prohibited: project-agent contract or storage changes, authorization/approval changes, checker execution changes, provider route or retry changes, live inference, credentials, and remote product mutations.

## Acceptance criteria

- Acceptance: Omni presents the restricted generated schema in draft and review; a known invalid draft or final response receives safe bounded correction in the same attempt; corrected output must satisfy the shared contextual validation and reopen assigned originals in its phase; exhausted corrections fail closed; total timeout, model turns, tool quotas, provider attempts, circuit facts, and native cleanup stay bounded. Actual SDK boundary tests demonstrate correction, scope rejection, and failure exhaustion.

## Risk and review routing

- Risk class: L1, untrusted model output and guarded external runtime behavior.
- Verification: focused actual SDK tests with loopback synthetic provider; relevant guide runtime tests, format/lint/type checks as available; diff, stale wording, markdown links, roadmap impact inspection.
- Required review: architecture, security, QA, test delta. Plan review precedes product code.
- Human review focus: restricted schema parity, distinction between corrected known output and provider retry, aggregate turn accounting, source reopening, and failure classification.

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
