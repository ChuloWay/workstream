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
- `backend/app/adapters/model_usage/openrouter.py`, affected OpenRouter imports in `backend/app/adapters/project_agents/**`: share existing provider HTTP/metadata/pricing/request controls without duplicating setup behavior.
- `backend/app/interfaces/checker_model_provider.py`: distinguish bounded response IDs from slash-qualified model identities.
- `backend/tests/checkers/model_provider/**`, `backend/tests/checkers_model_calls/**`, affected setup-provider tests: discriminating provider, custody and non-model regressions.
- `deploy/hosted/{compose.inference.yml,compose.model-openai.yml,compose.model-openrouter.yml,preflight.py,release.env.example,README.md}`, `docker/backend/release-entrypoint.sh`, `scripts/test_hosted_release_config.py`, affected `scripts/test_hosted_release_images.py`: mount/load only configured provider credentials, preserving role separation and cached-image proof.
- `backend/.env.example`, `README.md`, `docs/operations_checker_models.md`, `docs/roadmap_status.md`: reconcile supported configured providers and actual proof limits.
- Exact behavior-ownership and test-lane catalogue registrations under `.ci/`, `backend/scripts/behavior_ownership.py` and their catalogue tests where required for changed/new files; regenerate canonical digests without weakening gates.
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
Unknown profile providers fail closed. No ambient credential fallback.

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
- Required reviewers: security; architecture/reuse; QA/test delta; documentation; CI integrity for exact catalogue registrations.
- Human review focus: provider selection vs optional model use, secret boundaries, and conservative uncertain-effect handling without automatic retries.

## Evidence

Plan review precedes implementation. Required proof: controlled HTTP tests through
the actual parser, profile/factory composition, real PostgreSQL/ART settlement and
replay, credential-free hosted rendering/entrypoint tests, existing affected setup
and OpenAI regressions, static boundaries/catalogues, links, stale wording and full
hosted CI. Live provider and full project journey remain separately qualified.

## Reconciliation

Base: current main `a3c98c3571c6de4a6f4ce5ca6f3560b5cb32f7f6`, including merged #676
and AWS proof fix. Coordinate shared hosted files with active #677 without
editing its worktree. No database migration is planned unless discovery proves
an existing persisted contract prevents the required exact provider identity.
Next usable boundary: deploy the configured provider repair with project POST
implementations and run the approved real-project drill.
