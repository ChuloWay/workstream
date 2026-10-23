# WS-AGENT-001-02 — Real OmniCoreAgent adapter qualification

- Initiative: WS-AGENT-001
- Durable disposition: Planned
- Intended merge outcome: Qualify and register the actual OmniCoreAgent adapter,
  keep both incompatible SDK closures isolated, and make the selected runtime
  explicit in CI and immutable backend images.

## Intent

The user requires a second actual runtime to prove core independence and remain a
real selectable alternative. This change qualifies and statically registers that
native loop, then binds each incompatible SDK closure to an explicit test and image
environment. It consumes the neutral tools/configuration from
[01](WS-AGENT-001-01.md). It cannot change
PROJECTS/ART policy, custody schema or approval logic to fit OmniCoreAgent.
Published OmniCoreAgent 0.6.0 supports async tools/OpenRouter, but has different
request/retry mechanics and dependencies from the current OpenAI Agents SDK.

## Bounded change

Allowed: the new adapter and static registration in
`backend/app/adapters/project_agents/`, its typed effective profile, isolated SDK
test environments, focused actual-SDK contract tests and synthetic loopback proof;
the existing project-setup Celery task's hard process limit and focused prefork
termination proof, its runtime-aware prefork topology guard, and the public guide
API drill's worker pool; the shared Celery Redis visibility configuration and
no-prefetch startup check; the existing backend Dockerfiles and entrypoint; local and hosted
composition, preflight, shutdown bounds and release examples;
backend/CLI/MCP/release-image
workflows and their test-lane/evidence owners; release-image verification and
focused tests; and this record. The current initiative overview/index and
`docs/roadmap_status.md` may be reconciled only for the resulting durable
capability and next boundary. The dependency change may touch only
`backend/pyproject.toml` and `backend/uv.lock` plus the focused installation tests.
Prohibited: core/schema changes for SDK mechanics, SDK monkeypatches/forks,
provider-specific document evidence, global credential switching, silent fallback,
stacked retries, automatic host/filesystem tools, or a speculative third adapter.
Also prohibited: another factory or registry path, runtime discovery, a new queue
or process framework, S3 implementation changes, all-extras installation, provider
calls containing real/private/user-supplied guide material, and configuration that
merely asserts unobservable provider-account state.

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

The guard parses exactly the declared bounded body as one JSON object while
rejecting duplicate keys, non-finite numbers and oversized bodies. It closes the
connection after one request, so bytes beyond the declared body cannot be parsed
or forwarded. Its pinned-SDK input
schema allows only
`model`, `messages`, `temperature`, `max_tokens`, `top_p`, `stream`, `tools`,
`tool_choice` and the exact SDK-generated `usage:{"include":true}`; it rejects
`models`, `route`, `plugins`, `transforms`, unexpected
metadata/session/trace fields, non-function or server tools and every extension
field. The model must equal the trusted model in the attempt runtime
configuration, streaming must be false, and
the tools must be the exact closed schemas for the two registered document tools.
Message count and string/array depth are bounded. System and user messages are
closed `{role, content}` string objects; assistant messages add only bounded
OpenAI function `tool_calls` with closed `{id, type, function:{name, arguments}}`
objects and string-or-null content; tool messages add only `tool_call_id` and
bounded string content. Tool names and JSON argument strings remain subject to
the SDK tool registry and the Workstream tool schemas.

The guard builds a new upstream object from those validated fields rather than
forwarding the accepted body. It injects the exact configured model, exact tool schemas and
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
model endpoint. Before any real guide uses OpenRouter, the operator must
independently confirm that account and organization defaults cannot force an
enabled plugin or prevent the request-level disables, especially for alignment.
This is an external account prerequisite shared by both adapters, not a boolean
setting the repository can verify or a privacy claim inferred from request flags.
Before enabling either inference runtime for real guide material, the deployment
operator must retain a dated release-evidence record outside application
configuration. It identifies the exact OpenRouter account, organization/workspace
and credential scope; inventories every available plugin, default and override
lock; records the verifier and approving operator; and demonstrates that each
plugin is disabled or permits the adapter's request-level disable. Renew that
evidence whenever the account, organization, workspace, credential scope, plugin
catalogue/default or override policy changes. Static runtime registration and
synthetic tests do not satisfy this operational gate. The guard derives trusted
`Authorization`,
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
A cancellation-resistant pinned-SDK or forwarding task therefore reaches the
existing Celery prefork fail-stop boundary rather than an unbounded worker. Reuse
the OUTBOX hard-limit pattern on `compile_project_guide`: exact 7,260-second hard
limit (the maximum configured 7,200-second run plus a fixed 60-second shutdown
margin), `acks_on_failure_or_timeout=true`, the existing late acknowledgement and
worker-loss rejection, no soft limit, and hosted prefork enforcement. The prefork
parent acknowledges hard timeout without Celery retry; the already-fenced attempt
stays provider-uncertain and is not automatically redispatched. A process-pool
probe makes a pinned-SDK-equivalent cleanup task ignore cancellation, observes hard
termination and child replacement, and proves the same attempt is not invoked
again. This adds no queue or task topology.
This 7,260-second ceiling is a fail-stop backstop, not the normal request timeout;
the attempt's persisted `timeout_seconds` remains the smaller ordinary whole-run
deadline. Add a project-setup topology owner parallel to the existing OUTBOX
pattern: when the selected runtime uses inference, worker startup and task entry
require a non-eager prefork process consuming the default queue and reject direct,
eager, solo, thread or greenlet execution before model construction. The guide API
drill moves its default-queue consumer from solo to prefork without consuming the
OUTBOX queue. Hosted worker `stop_grace_period` and the shutdown wrapper timeout
become 7,320 seconds, leaving a fixed 60-second parent drain/reap margin after the
hard task limit. Release tests bind these values so operator shutdown cannot bypass
the hard-timeout acknowledgement path and turn it into worker-loss redelivery.
Set one immutable 7,380-second Celery visibility timeout, leaving another fixed
60-second margin above hosted drain. Apply it to the shared app's
`broker_transport_options`, `result_backend_transport_options` and app-level
`visibility_timeout`, so workers, Beat and every publisher sharing the Redis broker
advertise the same value; no environment override may shorten it. Project-setup
startup/task validation and hosted preflight inspect the effective value and reject
independent drift. The required ordering is
`Redis visibility 7,380 > hosted drain 7,320 > task hard limit 7,260 > ordinary
attempt deadline`. A time-scaled real Redis/prefork late-ack probe must first show a
short visibility value redelivers before the task boundary, then show the supported
ordering keeps one delivery through hard-timeout acknowledgement and child
replacement. This covers Celery's shortest-visibility-wins rule for every
Workstream participant using that broker.
Because Redis visibility starts when a message is reserved rather than when a
prefork child begins it, the shared app also pins
`worker_disable_prefetch=true`. Inference project-setup startup/task validation
requires the effective Redis transport and no-prefetch behavior; it rejects
brokers where Celery ignores this control. This prevents a third long task from
aging invisibly in the parent while both concurrency-two children are occupied,
without adding another queue. Hosted preflight and release tests bind the same
transport and setting. The real Redis discriminator saturates two children and
publishes at least a third long late-ack task: its bad control demonstrates early
redelivery of a reserved waiting message, while the supported control proves the
third message is not reserved until a process is available and then remains one
delivery through hard-timeout acknowledgement.
A hanging probe must cover the case where upstream consumes the complete body and
never responds. A fake upstream is injectable only by trusted test composition,
must be loopback-only, and is never accepted from product configuration.

Keep SDK-native completion retries as the only retry owner and record the exact
observed effective profile. Enforce the common whole-run deadline and tool/output
bounds in the adapter/capability; prove cancellation terminates native tasks.
Keep the SDK's full prompt-injection guardrail enabled, but set its public
`max_input_length` configuration to the existing Workstream
`maximum_manifest_bytes` bound. Workstream continues to reject oversized prompt
and review bytes before provider contact; the SDK's smaller default must not block
a valid bounded draft from reaching the review phase.
Acquire the existing process-local model circuit during `admit_execution`, before
the durable dispatch fence. Generalize only that owner's effective-profile and
failure-classification inputs; do not add a second circuit or retry loop. Each
native logical model request holds one admission across all SDK retries, records
one failure only when those retries end in a transient provider outcome, resets
health on success, and excludes cancellation and non-transient output/runtime
failures. Every close path releases its lease. Prove an open circuit rejects before
the fence and that the OpenAI adapter's existing retry/circuit behavior is
unchanged.
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

Register `omnicore_agent` statically beside `openai_agents_sdk` in the existing
single typed adapter composition root. Importing the adapter module must remain
safe without its native SDK; selecting it in the wrong environment reaches the
existing actionable configuration error before dispatch. There is no discovery,
fallback or alternate factory. The qualified Omni profile records
`sdk_environment=omnicore` and `process_sdk_exclusive=true`; construction requires
Python >=3.12, OmniCoreAgent 0.6.0, LiteLLM 1.106.2, OpenAI 2.54.0 and the already
present `OPENROUTER_API_KEY`. Terra remains the synthetic qualification model.
Hosted model selection remains independently configurable under the existing
provider/model format rules, but adapter admission and hosted preflight reject
every colon-suffixed OpenRouter variant, including `:online`, `:nitro`, `:floor`
and `:free`, and every case-insensitive `openrouter/*` router identifier rather
than stripping or rewriting it. The guard binds the exact remaining ordinary model
for the attempt. Only Terra has synthetic provider qualification in this change;
another operator-selected ordinary model is selectable but remains unqualified
until separately proven.

Both backend Dockerfiles accept one required exact SDK-environment build argument,
`agents` or `omnicore`, and install only that uv extra. The release image contains
a root-owned immutable marker naming the installed environment. Before loading a
provider credential or starting any role, the release entrypoint requires
`openai_agents_sdk` to match `agents`, `omnicore_agent` to match `omnicore`, and
allows the non-inference `manager_authored` runtime in either image. The existing
single digest-qualified backend image still serves API, worker, Beat, parser and
proof roles; the operator chooses the reviewed digest matching the configured
inference runtime. No service, queue or task topology changes. Local Compose passes
the explicit build selection and defaults to the current Agents environment. The
marker/runtime tuple is validated before reading provider credentials.
`manager_authored` must use the exact `none/none/none` provider/API/model tuple and
loads no provider secret; either inference runtime loads only its matching provider
credential after the marker check succeeds.

Hosted preflight accepts the Omni runtime only with OpenRouter and chat completions,
while retaining the existing validated provider/API/model rules for the Agents
runtime and the neutral manager-authored path. It rejects cross-runtime options,
colon-suffixed OpenRouter variants and `openrouter/*` router identifiers; image and
runtime mismatches remain an entrypoint startup failure. The hosted example and
operations text describe both image choices and the shared OpenRouter account
plugin prerequisite; they add no unverifiable attestation setting.

Every existing CI `--all-extras` installation becomes an explicit `agents` or
`omnicore` selection with environment-specific cache identity. The current semantic
lanes remain the Agents environment and execute the real OpenAI Agents SDK suite
and the Omni-unavailable proof exactly once. One required Python 3.12 Omni job
installs only `omnicore` plus development tools, runs `uv pip check`, executes the
real Omni synthetic SDK suite without skips exactly once, and proves the Agents
adapter is unavailable there. Environment-specific modules are declared in the
test-custody catalogue and reconciled with the dedicated job so completeness cannot
silently omit them. CLI and MCP contract jobs use the current Agents environment.

The Omni job also starts the existing source-pinned MinIO service and runs the
complete `tests/test_s3_artifact_store.py` suite. This proves the bounded
aiobotocore/botocore uplift in the environment where LiteLLM adds boto3. The release
workflow builds both backend variants, and the existing verifier checks each
immutable marker and exact package closure: Agents contains OpenAI Agents 0.24.0
and OpenAI 3.37.0 without OmniCoreAgent/LiteLLM; Omni contains OmniCoreAgent 0.6.0,
LiteLLM 1.106.2 and OpenAI 2.54.0 without OpenAI Agents. The existing connected
hosted AWS proof must pass with the actually selected image before any deployed
image claim; synthetic CI does not replace it.

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
  run remains behind operator confirmation and retained deployment evidence for
  the account-default prerequisite.
- A valid draft larger than OmniCore's default input cap reaches the independent
  review phase under the existing Workstream byte bound; an oversized Workstream
  prompt still fails before provider contact.
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
- Exhausted transient Omni native retries count once in the existing shared model
  circuit; success resets it, cancellation and non-transient failures do not count,
  and a second runtime is rejected before the durable fence. The unchanged OpenAI
  retry/circuit suite also passes.
- Adapter and hosted-preflight negatives reject colon model variants and
  case-insensitive `openrouter/*` routers without rewriting persisted identity;
  tests identify Terra as the sole provider-qualified model in this change.
- A cancellation-resistant cleanup probe reaches the exact prefork hard limit,
  terminates and replaces the child, acknowledges without transport retry, retains
  the fenced attempt as provider-uncertain and proves no repeat invocation.
- Default-queue solo/eager/direct workers cannot execute an inference setup task;
  the public guide drill and hosted worker use validated prefork, hosted drain is
  exactly 60 seconds longer than the 7,260-second hard limit, and tests reject
  either timeout drifting independently.
- The effective Redis broker, result-backend and app visibility values all equal
  7,380 seconds across worker, Beat and publishers. Startup/preflight rejects a
  shorter participant, and a real time-scaled Redis/prefork proof distinguishes
  early redelivery from the supported single-delivery hard-timeout path.
- Inference worker startup requires effective Redis
  `worker_disable_prefetch=true`. The concurrency-two/three-task Redis proof shows
  the third task is not reserved while both children are occupied, then remains a
  single delivery across its own hard-timeout boundary; preflight and release tests
  reject transport or no-prefetch drift.
- Static registration makes `omnicore_agent` selectable through the same typed
  factory and effective-profile path. The release marker rejects a mismatched SDK
  image before role startup, preserves `manager_authored` in either image and never
  causes both SDK closures to coexist.
- The parser remains runtime-neutral: its release role validates the immutable SDK
  image marker and scrubs ambient credentials without requiring runtime, provider or
  model settings. Inference-capable roles still reject a runtime/SDK mismatch before
  loading provider secrets.
- Provider-free `manager_authored` startup proves its exact `none/none/none` tuple
  requires no provider secret, while both inference runtimes validate the immutable
  marker before loading only their matching credential.
- CI selects the real Agents and Omni SDK suites exactly once with no skip or
  deselection hidden from completeness evidence. The opposite adapter fails with
  the actionable unavailable error in each mutually exclusive environment.
- Both release variants pass exact package-closure inspection. The complete real
  MinIO suite passes in the Omni environment, and the selected image completes the
  existing connected AWS proof before a deployed-image claim.
- The deployment runbook names the operator-owned OpenRouter plugin evidence,
  exact account/organization/workspace and credential scope, verifier/approver,
  catalogue/default/override checks and every renewal trigger; no application
  boolean pretends to attest external account state.
- Contract qualification changes no authority, policy selection, proposal approval
  or retained attempt evidence. Runtime selection remains an explicit adapter and
  immutable-image composition decision.

## Risk and review routing

L1. Architecture/reuse, security, QA/test delta, dependency/CI integrity and docs
review the exact implementation. The existing companion architecture and security
reviewers replay the amended dependency, registration, image, deployment,
hard-timeout and test-custody scope before implementation. Human focus is actual
native loops, honest SDK bounds, mutually exclusive package closure, fail-closed
image selection and no data leakage.

## Evidence

SDK source/dependency inspection and separate frozen resolution are complete. The
actual OmniCoreAgent 0.6.0 loopback suite exercises native tools, draft/review,
configured models, per-logical-request circuit admission, native retries,
malformed success/error sanitization, source substitution, quotas, cancellation
and cleanup. Focused proof also covers static registration, opposite-environment
failure, mutually exclusive dependency closure, provider-free `manager_authored`
composition, exact release markers, CI custody and a real Redis/prefork
concurrency-two/three-task fail-stop discriminator. The durable hard-timeout proof
retains the fenced attempt as `compilation_provider_uncertain`.

A lead-custodied provider-backed synthetic production-factory run at exact commit
`d0a14d292ff108a927cfd06fdd956debd92670c9` completed both draft and coverage
review through the actual OmniCore adapter with four successful provider responses
and two document reads. Its retained evidence contains only response sizes and JSON
shape, not response content. It used a synthetic guide without the database, S3 or
a durable worker, so it establishes neither original-guide nor hosted readiness.

The complete Omni-environment MinIO suite, both selected release-image builds and
parser isolation runs remain required before this record is complete. The selected-
image AWS proof remains required before a deployment claim. The repository
documents but cannot prove OpenRouter account defaults; real original-guide material
remains behind retained account/organization/workspace/plugin evidence and operator
confirmation. A generated-data provider call does not establish privacy or hosted
readiness.

The first exact-image Omni original-guide attempt reached health but stopped before
inference because the shared release entrypoint incorrectly required runtime/model
configuration for the isolated parser role. Its retained failure evidence records
`parser_exited`, successful cleanup and no inference request. A focused shell
regression now exercises a parser without runtime configuration in both SDK
environments, and release-image verification runs the same parser startup plus a
wrong-SDK worker denial before any provider secret can load. Exact rebuilt-image and
parser-isolation evidence remain required before retrying the live qualification.

## Reconciliation

Depends on 01's merged exact contract. Registration and image selection return to
the existing hosted contribution journey without another queue or runtime system.
No historical setup attempt is rerun, and no current issue is closed on adapter
tests or image builds alone.
