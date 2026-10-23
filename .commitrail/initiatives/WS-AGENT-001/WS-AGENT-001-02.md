# WS-AGENT-001-02 — Real OmniCoreAgent adapter qualification

- Initiative: WS-AGENT-001
- Durable disposition: Planned
- Intended merge outcome: Qualify an actual OmniCoreAgent adapter and synthetic
  SDK loop through the same Workstream runtime contract for later registration.

## Intent

The user requires a second actual runtime to prove core independence. This change
qualifies that native loop without making it selectable for production. It consumes
the neutral tools/configuration from [01](WS-AGENT-001-01.md). It cannot change
PROJECTS/ART policy, custody schema or approval logic to fit OmniCoreAgent.
Published OmniCoreAgent 0.6.0 supports async tools/OpenRouter, but has different
request/retry mechanics and dependencies from the current OpenAI Agents SDK.

## Bounded change

Allowed: the unregistered new adapter in
`backend/app/adapters/project_agents/`, its typed effective profile, isolated SDK
test environment, focused actual-SDK contract tests and synthetic loopback proof.
Prohibited: core/schema changes for SDK mechanics, SDK monkeypatches/forks,
provider-specific document evidence, global credential switching, silent fallback,
stacked retries, automatic host/filesystem tools, or a speculative third adapter.
Also prohibited in this chunk: production factory registration, hosted selection,
release/runtime setting changes, and provider calls containing real, private or
user-supplied guide material.

## Design

Pin published `omnicoreagent==0.6.0` (MIT; Python >=3.12,<3.15;
wheel SHA256 `76f191b79f5aa1bc1b7dea354643c692071454a603097fe3ca69a875e749d74a`).
Use its public `OmniCoreAgent`, `ToolRegistry`, async `run` and cleanup APIs. Keep
in-memory per-attempt sessions and explicitly disable skills, subagents, offload,
workspace tools, code mode and content telemetry. Offer only the shared document
read/search tools. Validate returned JSON using the same Workstream validator.

OmniCoreAgent 0.6.0 does not expose OpenRouter request-body options through its
public model configuration. Use its documented per-instance `base_url` seam with
one adapter-owned, per-attempt loopback transport guard. The SDK connects only to
an ephemeral `127.0.0.1` listener under a high-entropy attempt-capability path.
The guard accepts a bounded `POST` only at that path. It constant-time checks the
inbound bearer value against the already-loaded credential but never copies or
trusts that header for forwarding; outbound authorization is rebuilt from the
stored credential. Its closed HTTP envelope permits only the captured pinned-SDK
`Host`, `Authorization`, `Content-Type`, `Content-Length`, `Accept`,
`Accept-Encoding`, `User-Agent`, `Connection`, `HTTP-Referer` and `X-Title`
headers under exact count/name/value byte caps. The last three must equal the
pinned capture (`keep-alive`, `https://litellm.ai`, `liteLLM`); the guard ignores
the two informational values and closes every response server-side regardless of
the client's connection preference. It requires identity content encoding and
JSON media type, and rejects cookies, forwarding headers and transfer encoding.
Method, path, active connection count, total request count and each
accept/read/write deadline are bounded by the immutable profile and remaining
whole-run time.

The guard parses exactly one JSON object while rejecting duplicate keys,
non-finite numbers, oversized bodies and trailing data. Its pinned-SDK input
schema allows only
`model`, `messages`, `temperature`, `max_tokens`, `top_p`, `stream`, `tools`,
`tool_choice` and the exact SDK-generated `usage:{"include":true}`; it rejects
`models`, `route`, `plugins`, `transforms`, unexpected
metadata/session/trace fields, non-function or server tools and every extension
field. The model must be the fixed qualified model, streaming must be false, and
the tools must be the exact closed schemas for the two registered document tools.
Message count and string/array depth are bounded. System and user messages are
closed `{role, content}` string objects; assistant messages add only bounded
OpenAI function `tool_calls` with closed `{id, type, function:{name, arguments}}`
objects and string-or-null content; tool messages add only `tool_call_id` and
bounded string content. Tool names and JSON argument strings remain subject to
the SDK tool registry and the Workstream tool schemas.

The guard builds a new upstream object from those validated fields rather than
forwarding the accepted body. It injects the exact model, exact tool schemas and
OpenRouter `provider` policy with `allow_fallbacks=false` and
`data_collection=deny`. It uses the shared qualified OpenRouter policy to request
disablement of `web`, `file-parser`, `response-healing`, `armor`,
`pareto-router` and `context-compression`. OpenRouter rejects an `enabled` field
for `alignment`, so alignment must instead be disabled and protected from request
override in the provider account. The guard rebuilds the captured
`usage:{"include":true}` without forwarding the inbound object.
`data_collection=deny` is a provider-routing constraint, not a zero-data-retention
claim. OpenRouter account or organization defaults can enable plugins and can
prevent request overrides; the adapter cannot inspect that control through the
model endpoint. Hosted activation therefore remains pending until an agreed
deployment-owned control proves that the credential's defaults cannot add a
plugin. The guard derives trusted `Authorization`,
`Content-Type` and `Accept` headers itself and forwards once to the fixed HTTPS
OpenRouter chat-completions origin with redirects disabled, proxy environment
ignored and no cookies. It does not trust any inbound header as upstream state
and accepts no model-, request- or environment-selected upstream. It retries
nothing, logs and stores no body, and returns only a bounded provider response
plus the status and retry metadata needed by the SDK-native loop. All request,
response and error bodies have byte caps enforced before parsing or buffering.

Track every listener, forwarding and cleanup task. On timeout or cancellation,
first close admission and the listener, cancel and await the native SDK run, then
cancel and await every in-flight forward and close its client before awaiting SDK
cleanup. A reserved bounded cleanup interval must complete this order; incomplete
cleanup is a runtime failure and the adapter cannot return while any local SDK,
listener, forwarding-client or tool task remains. Once a provider has accepted a
request, local cancellation cannot prove remote computation stopped; preserve the
orchestrator's post-fence provider-uncertain outcome rather than claiming it did.
A hanging probe must cover the case where upstream consumes the complete body and
never responds. A fake upstream is injectable only by trusted test composition,
must be loopback-only, and is never accepted from product configuration.

Keep SDK-native completion retries as the only retry owner and record the exact
observed effective profile. Enforce the common whole-run deadline and tool/output
bounds in the adapter/capability; prove cancellation terminates native tasks.
Do not claim unsupported per-request timeout or provider-store settings. Capture
outbound calls, telemetry behavior and exact tool inventory before real material.
Use the worker's one configured provider credential; do not accept per-request
keys or change other runtimes' global clients/defaults. Qualify any SDK-internal
environment assignment against the existing identical worker credential; it must
not introduce a different key or broaden exposure.

The OmniCore optional dependency selects a mutually exclusive worker image and
process: that image installs one project-agent SDK, the composition root constructs
only the selected adapter, and the existing worker process has no other LiteLLM
consumer. This is the concrete boundary containing OmniCore's SDK-owned LiteLLM
callback, telemetry and logging globals; do not add a queue/process framework or
snapshot and restore those globals around a run. Record the image/process
requirement in the effective profile and test selection before SDK construction.
An absent or different `OPENROUTER_API_KEY` fails before construction. The SDK's
assignment of the exact already-present byte string is permitted only when
equality is proved before and after construction, execution and cleanup.

Install in a separate locked SDK environment from OpenAI Agents SDK: OmniCore's
LiteLLM currently requires `openai<3`, whereas the OpenAI environment pins 3.37.0.
Use the same core source and dependency lock with explicit environment selection,
not relaxed dependency verification or a parallel Workstream implementation.
The shared project remains Python >=3.11,<3.13; the mutually exclusive `omnicore`
extra is Python >=3.12 and conflicts exactly with the `agents` extra. LiteLLM's
`boto3>=1.43.1` makes the former aiobotocore 3.7.0/botocore 1.43.0 pins
unsatisfiable, so the bounded dependency integration may lift only those pins to
aiobotocore 3.8.0/botocore 1.43.3. The existing real MinIO S3 protocol suite must
pass after that lift, and an AWS smoke remains required before any deployed-image
claim; this change does not alter the S3 implementation.

## Acceptance criteria

- Same contract suite against both actual SDK loops: tools, source isolation,
  output validity, malformed output, quotas, cancellation, retry counts and privacy.
- The adapter identity is exact. Compilation rejects a different
  `context.runtime_configuration`, compile-before-admit and compile-after-close;
  `aclose` is idempotent and is awaited after construction, admission, fence,
  run or cancellation failure as well as successful completion.
- Removing the neutral tool boundary or substituting a foreign source must fail
  the intended assertion, not an earlier fixture/schema guard.
- The actual OmniCore SDK completes a synthetic loopback tool round trip. An
  optional live OpenRouter probe may contain only generated non-sensitive synthetic
  content and cannot establish plugin/privacy qualification. A real original-guide
  run and selectable runtime remain behind deployment-owned account-default proof.
- No hosted file/container calls, persistent SDK session, unexpected tool or
  telemetry endpoint. Retention claims match observed/provider-documented behavior.
- Every captured upstream model request contains the exact enforced OpenRouter
  provider policy and explicit qualified request-level plugin disables; provider
  account evidence separately covers alignment. Independent mutations of
  every rejected field, duplicate key, header, model and tool form fail before
  upstream contact. A hostile local request cannot change the credential, model,
  tools, upstream URL, plugin, privacy or fallback policy, and cannot make the
  guard forward after cancellation or closure.
- The unmodified captured OmniCoreAgent 0.6.0 and LiteLLM 1.106.2 request is the
  positive guard control before independent header/body mutation cases. The guard
  rebuilds `usage:{"include":true}`, ignores the fixed informational headers and
  closes the response even though the pinned client requested keep-alive.
- Composition proves only one project-agent SDK is installed and selected in the
  worker image and that no other existing worker consumer imports LiteLLM.
  Credential bytes and environment membership remain unchanged through
  construction, both guide phases, cancellation and cleanup.
- Contract qualification changes no authority, policy selection, proposal approval
  or retained attempt evidence. Later runtime selection must remain an adapter and
  environment composition decision after the activation gate passes.

## Risk and review routing

L1. Architecture/reuse, security, QA/test delta, dependency/CI integrity and docs
review the exact implementation. Human focus is actual native loops, honest SDK
bounds and no data leakage.

## Evidence

SDK source/dependency inspection is complete; runtime qualification is not yet
run. Required proofs include captured HTTP, hanging transport/tool cancellation,
separate locked installation and synthetic native-loop evidence.
Adapter and synthetic qualification may proceed, but registration and hosted
activation remain pending while the OpenRouter account-default plugin control
above is unresolved; do not label the privacy profile passing before that control
has evidence.

## Reconciliation

Depends on 01's merged or reviewed exact contract. After qualification, return to
the existing hosted contribution journey. No historical setup attempt is rerun,
and no current issue is closed on adapter tests alone.
