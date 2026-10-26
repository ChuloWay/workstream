# POST model provider selection

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Model-backed POST checks select their supported provider from the locked project profile; OpenRouter-only deployments need no OpenAI credential.

## Intent

The approved project checks determine whether inference is needed. Ordinary POST
checks must remain independent of models. For inference, the provider/model is a
profile choice, not an OpenAI requirement imposed by the proxy. Preserve shared
project budgets, exact paid-call custody, immutable evidence and no blind retry.

## Current behavior

`configured_model_provider` accepts only `openai_responses/responses.v1` and its
factory registers only OpenAI. Setup already supports OpenRouter. Hosted proxy
composition and entrypoint require both provider secrets regardless of selection.
The optional model execution wrapper already passes ordinary checks through.

## Bounded change

### Allowed

- `backend/app/adapters/checkers/{__init__,model_runtime,model_provider,openrouter_model_provider}.py`: profile-driven typed provider composition and bounded OpenRouter POST adapter.
- `backend/app/adapters/model_usage/openrouter.py`, affected imports in `backend/app/adapters/project_agents/{setup_model_handler,openai_agent_sdk,omnicore_agent}.py` and removal of `backend/app/adapters/project_agents/openrouter_policy.py`: share existing provider HTTP/metadata/pricing/request controls without duplicating setup behavior.
- `backend/app/interfaces/checker_model_provider.py`: distinguish bounded response IDs from slash-qualified model identities.
- `backend/tests/checkers/model_provider/{test_openai_responses,test_openrouter}.py`, `backend/tests/checkers_model_calls/{test_model_runtime,test_proxy_orchestration,test_composed_execution,test_setup_model_handler,test_setup_model_handler_postgresql}.py`, `backend/tests/test_omnicore_agent_sdk.py`: discriminating provider, custody and non-model regressions.
- `deploy/hosted/{compose.inference.yml,compose.model-openai.yml,compose.model-openrouter.yml,preflight.py,release.env.example,README.md}`, `docker/backend/release-entrypoint.sh`, `scripts/test_hosted_release_config.py`, affected `scripts/test_hosted_release_images.py`: mount/load only configured provider credentials, preserving role separation and cached-image proof.
- `backend/.env.example`, `README.md`, `docs/operations_checker_models.md`, `docs/roadmap_status.md`: reconcile supported configured providers and actual proof limits.
- Exact registrations in `.ci/behavior-ownership/partition.v1.json`, `backend/scripts/{behavior_ownership,test_lane_catalogue}.py`, and `backend/tests/{test_behavior_ownership,test_ci_lane_catalogue}.py` where required for changed/new files; regenerate canonical digests without weakening gates.
- This change record.

### Not allowed

- No new budget/account/authorization subsystem, routing/acceptance changes, provider fallback, hidden paid retry or deletion of retained evidence.
- No POST model requirement for ordinary checkers. No checker image redesign or takeover of active PR #677.
- No new CI workflows/lanes, weaker assertions/skips/timeouts, dependency additions or compatibility aliases.
- No paid live calls until the existing account allowance is reconciled; controlled HTTP/provider tests establish this repair first.

## Design and decisions

Use the existing typed `CheckerModelProvider` factory. OpenAI retains its current
stored Responses behavior; OpenRouter uses one bounded non-streaming Chat
Completions request, exact model identity and locked parameters. Reuse the setup
provider's current metadata/pricing and request controls through a shared adapter
module. Metadata refusal happens before dispatch. Transport/response ambiguity
retains an uncertain effect and cannot create again; OpenRouter recovery never
pretends a response ID alone is retrievable. Successful synchronous completion
uses existing ART custody, settlement and replay.

Provider secret file paths remain the deployment inputs. Enable one or both
provider-specific secret overlays from those explicit paths, require the selected
setup provider's secret, and reject missing/invalid configured secrets. No extra
provider selector is needed at deployment: POST uses its immutable profile.
Only `openai_responses/responses.v1` and `openrouter/chat_completions` are
supported POST pairs. Validate the pair before reading only its credential.
Unknown pairs fail closed with no fallback. Shared code contains only concrete
OpenRouter HTTP/read, direct-model/routing, metadata/pricing and usage primitives;
setup retains its DTOs, tools, canonical ART and replay. The checker owns strict
single-assistant-text choice/status parsing. Recovery returns UNAVAILABLE with
zero network I/O. Remove the superseded policy module and update all callers;
retain no import alias.

Credential matrix: disabled proxy admits no provider file paths or overlays;
enabled inference setup requires its configured provider file, with the second
optional; enabled manager-authored setup requires at least one provider file.
Only nonempty allowlisted file paths select overlays. Every configured file is
metadata-validated, mounted and conditionally loaded only in model-proxy; absent
providers are never mounted/exported. Clear ambient provider keys first. Cover
OpenRouter-only, OpenAI-only and dual-provider configurations.

## Acceptance criteria

- [ ] An OpenRouter POST profile dispatches through the real adapter/HTTP parser with no OpenAI credential; an OpenAI profile still selects its adapter; unsupported profiles deny.
- [ ] Exact model/usage/output bounds, pricing metadata and no routing fallback or automatic paid retry are enforced; malformed/nonterminal/foreign-model output cannot settle as success.
- [ ] Persisted success settles/replays once with exact ART evidence; lost/ambiguous output stays held without a second paid invocation; provider recovery never creates.
- [ ] Ordinary POST checks construct no model provider and spend no model budget.
- [ ] OpenRouter-only, OpenAI-only and dual-provider hosted composition/entrypoint load only configured secrets; missing selected credentials fail closed; other roles receive none.
- [ ] Existing OpenAI/setup behavior, current AWS proof policy, authorization and immutable custody remain protected.
- [ ] Current docs/default examples describe optional model checks and supported profile-based dispatch accurately.

## Risk and review routing

- Risk class: L1 (paid provider effects, secrets and external-adapter composition).
- Required reviewers: security, architecture, reuse_dedup, qa, test_delta, documentation, ci_integrity.
- Human review focus: provider selection vs optional model use, secret boundaries, and conservative uncertain-effect handling without automatic retries.

## Evidence

Plan review precedes implementation. Named regressions in `test_openrouter.py`
cover metadata refusal before POST, one bounded nonstreaming dispatch with fixed
routing/plugins, exact single-choice/status parsing, identity/usage/output
substitution, uncertain no-second-POST and recovery with zero I/O.
`test_model_runtime.py` covers both exact profile pairs, selected-key isolation,
unknown-pair denial, and client close. Extend existing `test_composed_execution.py`
with a controlled real OpenRouter HTTP adapter to prove PostgreSQL/ART success
settlement/replay and held ambiguous response with no redispatch. Existing ordinary
POST no-model tests remain and are exercised. Setup contract tests protect extraction.
Hosted tests cover disabled/single/dual credentials in rendered Compose and the
real entrypoint, rejection of missing selected credentials and role isolation.

Commands (backend commands run from `backend/` with the existing test environment):

```sh
python -m pytest tests/checkers/model_provider tests/checkers_model_calls/test_model_runtime.py tests/checkers_model_calls/test_proxy_orchestration.py tests/checkers_model_calls/test_setup_model_handler.py -q
python scripts/run_isolated_tests.py --metadata-json /tmp/post-provider-pg.json --timeout-seconds 900 -- python -m pytest tests/checkers_model_calls/test_composed_execution.py tests/checkers_model_calls/test_setup_model_handler_postgresql.py -q
ruff check app/adapters/checkers app/adapters/model_usage app/adapters/project_agents app/interfaces/checker_model_provider.py tests/checkers/model_provider tests/checkers_model_calls
python scripts/module_boundaries.py
python scripts/authorization_boundary.py
python scripts/behavior_ownership.py
python -m pytest tests/test_ci_lane_catalogue.py tests/test_behavior_ownership.py -q
```

Repository-root commands:

```sh
python -m unittest scripts.test_hosted_release_config scripts.test_hosted_release_images
python scripts/check_commitrail_records.py --base-ref origin/main
python scripts/check_markdown_links.py
python scripts/check_stale_workstream_wording.py
git diff --check
```

Required proof: controlled HTTP tests through
the actual parser, profile/factory composition, real PostgreSQL/ART settlement and
replay, credential-free hosted rendering/entrypoint tests, existing affected setup
and OpenAI regressions, static boundaries/catalogues, links, stale wording and full
hosted CI. Live provider and full project journey remain separately qualified.

## Reconciliation

Base: current main `a3c98c3571c6de4a6f4ce5ca6f3560b5cb32f7f6`, including merged #676
and AWS proof fix. Coordinate shared hosted files with active #677 without
editing its worktree. No database migration: existing profile/SQL model identities already allow slash-qualified names through 160 characters. Response IDs stay slash-free through 256 characters.
Next usable boundary: deploy the configured provider repair with project POST
implementations and run the approved real-project drill.
