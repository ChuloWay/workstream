# Observability Foundation — Safe API And Worker Diagnostics

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Add one provider-neutral, privacy-bounded diagnostics pipeline for the API and prefork Celery workers without changing product authority or claiming a deployed monitoring service.

## Intent

### Problem being solved

Workstream has validated HTTP request and correlation IDs, sanitized point logs,
and a few bounded in-process counters, but no shared runtime composition for
structured logs, traces, or exportable metrics. API requests, broker publication,
and Celery execution therefore cannot be followed through one diagnostic trace,
and operators have no repository-owned configuration or failure contract for an
OTLP collector.

### Why this work matters

The v0.1 release bar requires an observable and recoverable path. Diagnostics
must help investigate that path without becoming lifecycle truth, an authority
input, a source of sensitive content, or a new reason for product work to fail.
This change establishes the smallest practical foundation: safe structured
logs, sampled traces, bounded metrics, API/worker correlation, and operational
guidance. It does not build a monitoring platform.

### Current behavior

- `app.core.api_controls.RequestContextMiddleware` validates or generates
  `X-Request-ID` and `X-Correlation-ID`, retains them in the ASGI scope, returns
  them on responses, and emits constant failure messages with correlation IDs.
  It does not bind those IDs to a process-safe logging or tracing context.
- `app.main.create_app` composes FastAPI and the request-context middleware but
  has no telemetry provider or structured logging composition.
- `app.workers.celery_app` already owns Celery composition and initializes the
  artifact runtime in `worker_process_init`. Worker logging is otherwise
  Celery's default, and no trace or validated diagnostic ID crosses broker
  headers.
- Broker calls use JSON messages and deterministic task IDs where the owning
  workflow defines them. The durable outbox owns its own persisted
  `correlation_id`; it has no persisted W3C trace context, so a delayed recovery
  scan cannot reconstruct the original in-memory trace.
- `app.adapters.auth.metrics` and `app.modules.artifacts.metrics` provide bounded
  in-process counters and structured metric events. There is no shared
  OpenTelemetry meter/export path.
- `backend/uv.lock` resolves FastAPI 0.141.1. Native FastAPI OpenTelemetry begins
  in 0.142.0; the repaired 0.142.2 implementation was inspected as a candidate
  and rejected below in favor of the narrower explicit capture boundary.
- FastAPI 0.142.2 native telemetry includes raw `url.query` on HTTP spans and can
  emit exception messages and stack traces as OpenTelemetry logs. The official
  Celery instrumentor can record exception messages, stacks, and retry reasons.
  Neither default is safe enough to export directly under this repository's
  content boundary.
- FastAPI native telemetry does not capture request headers or bodies as span
  attributes by default, but it extracts the process-global propagator and
  records raw path/query values before route selection. Its provider injection,
  `logs=False`, `metrics=False`, `auto_configure=False`, and route-template
  updates are usable only behind the application-owned exporter allowlist.
- `app.adapters.project_agents.openai_agent_sdk` explicitly keeps the OpenAI
  Agents SDK's tracing disabled and sensitive trace inclusion false.

## Bounded change

### Allowed

- `.commitrail/changes/observability-foundation.md`: durable intent, boundary,
  proof, and material review disposition.
- `backend/pyproject.toml` and `backend/uv.lock`: add only the OpenTelemetry SDK
  and OTLP HTTP/protobuf exporter required by this design. Keep the resolved
  FastAPI version unless an unrelated lock resolution moves it within the
  existing constraint; neither native FastAPI telemetry nor contrib/Celery
  auto-instrumentation is used.
- `backend/.env.example`: public, credential-free example settings for log
  level, OTLP endpoint, and trace sample ratio, with the API and worker sharing
  the same deployment environment while using distinct fixed service names.
- `backend/app/core/config.py`: typed, bounded diagnostics configuration and
  validation. Collector endpoints must be absolute HTTP(S) URLs without
  embedded credentials, query strings, or fragments.
- `backend/app/core/observability.py`: one small composition owner for safe JSON
  formatting, context-local diagnostic IDs, explicit OpenTelemetry resources
  and providers, local-budget sampling, safe span export, closed application
  metrics, traceparent-only Celery propagation hooks, and bounded shutdown.
- `backend/app/core/api_controls.py`: bind the existing validated request and
  correlation IDs for the duration of the ASGI request and annotate the active
  span without changing validation, response, or error behavior.
- `backend/app/main.py`: pass the immutable built route inventory to one
  application-owned ASGI instrumentation path and manage the app-owned runtime
  through lifespan.
- `backend/app/workers/celery_app.py`: pass the immutable registered task
  inventory to application-owned Celery signal instrumentation, initialize
  providers only after `worker_process_init`, and flush/shut down in bounded
  worker hooks without disturbing artifact-runtime ownership.
- `backend/app/modules/outbox/delivery.py`: after the canonical envelope is
  loaded, annotate only the current diagnostic span with its already-persisted,
  bounded outbox correlation ID. Do not store trace context or change delivery,
  authorization, digest, retry, or handler behavior.
- `backend/tests/test_observability.py`, `backend/tests/test_api_controls.py`,
  `backend/tests/test_config.py`, and focused existing outbox tests only where
  needed: observable privacy, correlation, fail-open, lifecycle, real-prefork,
  duplicate-instrumentation, and bounded-cardinality proof.
- `docs/engineering/observability.md` and the existing README logs section:
  operator configuration, interpretation, limitations, troubleshooting, and
  on-demand profiling guidance.
- `docs/roadmap_status.md`: reconcile only the affected platform-foundation and
  release-proof claims after implementation is frozen, distinguishing code
  capability from collector configuration and deployment. The lead will
  reconcile this shared file with concurrent product work before PR readiness.

### Not allowed

- Authentication, authorization, task, checker, review, revision,
  contribution, compensation, or acceptance lifecycle behavior.
- New permissions, source/acceptance writers, database tables, migrations,
  durable product references, audit-event fields, signed hashes, or changes to
  existing immutable evidence.
- Persisting `traceparent`, `tracestate`, baggage, trace IDs, or span IDs in the
  outbox or any business record. Diagnostic IDs never grant authority.
- Request/response bodies, guide/task/prompt/ZIP content, raw query strings,
  signed URLs, credentials, tokens, cookies, SQL text/parameters, exception
  messages, stack traces, or arbitrary logging extras in emitted diagnostics.
- Record, actor, user, project, request, correlation, broker-message, trace, or
  span IDs as metric attributes. Metric labels are limited to registered route
  templates, a fixed HTTP method/status/outcome vocabulary, registered Celery
  task names, and fixed service role. Values outside those exact registries and
  vocabularies collapse to one fixed `other`/`unmatched` value.
- FastAPI native or contrib telemetry, the official Celery auto-instrumentor,
  OpenAI Agents SDK tracing, database/client auto-instrumentation, an always-on
  profiler, a vendor SDK, dashboards, alerting rules, a collector fleet, or
  mandatory external monitoring infrastructure.
- Live or paid provider calls, real credentials, production `.env` access, CI
  workflow changes, global coverage gates, or weakened tests.

## Design and decisions

### Target behavior

The API and every prefork Celery child emit one-line structured logs with stable
service/environment/severity/event fields and, when present, the already
validated request ID, correlation ID, trace ID, and span ID. Exactly one HTTP
server span and one closed set of application-owned HTTP metrics are produced
per request. Application-owned Celery signal handlers create one child-local
consumer span and one task-duration measurement and propagate only W3C
`traceparent` plus validated Workstream diagnostic UUIDs through broker headers.
A missing, misconfigured, slow, or unavailable collector cannot block startup,
requests, tasks, or shutdown beyond the configured bound.

### Design chosen

`app.core.observability` owns explicit application-created tracer and meter
providers plus one explicit ASGI middleware. Native FastAPI telemetry was
evaluated and rejected: even with native logs, metrics, and automatic export
disabled, it first records raw path/query values, consumes process-global
propagation, and requires an export rewrite to establish the closed field
contract. The explicit middleware starts one fresh local trace, records no
headers, URL, query, body, exception, dependency, serialization, or background
task content, and closes the span with only normalized method, registered route
template, status class, outcome, and validated diagnostic IDs. It records the
matching application-owned metrics from the same normalized values. There is no
native/contrib compatibility path or runtime switch. The API service name is
fixed to `workstream-api` and the worker service name to `workstream-worker`,
with application version and deployment environment as bounded resource
attributes.

Public HTTP ignores inbound `traceparent`, `tracestate`, and baggage and starts a
fresh random local trace. Trace sampling uses a local trace-ID ratio sampler
with a validated ratio, so caller-chosen IDs and remote sampled flags cannot
override the Workstream budget. Internal Celery publication propagates the
locally created traceparent and the child continues the same decision. A small
fixed batch queue, batch size, schedule delay, OTLP request timeout, and
shutdown deadline bound resource use. A sanitizing exporter
boundary copies only approved span names, context, timing, status code without
description, links without attributes, and an explicit attribute key/value
allowlist. Registered HTTP route and Celery task inventories bound names and
values; unknown method, route, task, operation, error, or span values map to one
fixed category. It drops span events and raw resource attributes before any
in-memory test exporter or OTLP exporter sees them. This removes FastAPI
path/query input and Celery exception/retry content while preserving registered
route templates, registered task names, bounded HTTP outcomes, safe diagnostic
IDs, and causal trace context. Export construction and export errors are
reduced to constant local diagnostic events.

Application-owned HTTP request and Celery task metrics admit values through
exact runtime registries: the built FastAPI route inventory, the Celery task
registry, a fixed HTTP method set, status class, and fixed outcome vocabulary.
Unknown values map to `unmatched` or `other` before recording. Metrics use SDK
views as a second key allowlist. Request duration/active-request and task
duration are exportable; record and identity values never become labels.
Existing auth and artifact metric owners remain unchanged in this chunk rather
than gaining a second counter implementation.

The logging configuration is installed idempotently once per process, never
mutated per request, and uses context variables for concurrent isolation. Its
JSON formatter never calls `LogRecord.getMessage()`. It maps an exact registry
of Workstream static message templates to fixed event codes and discards their
arguments; all Uvicorn access/error, Celery task/retry/error, Kombu,
OpenTelemetry, SQLAlchemy, and unknown logger records map by logger family and
severity to fixed event codes without rendering `msg`, `args`, `exc_info`,
stack text, or arbitrary extras. The formatter's output fields and event values
are therefore both closed. Request middleware binds and resets service,
environment, and its current IDs around the whole ASGI call. Process-wide
handler installation is reference-safe and app providers remain app-owned, so
overlapping/repeated application factory lifespans neither replace another
app's provider nor add handlers. Celery publication copies only canonical UUID
IDs into private broker headers; task entry rejects malformed values and falls
back to the canonical Celery task UUID for diagnostic context.

Core diagnostics holds a private traceparent-only propagator for trusted
internal broker transport and never replaces OpenTelemetry's process-global
propagator. Public HTTP does not extract trace context. Broker publication
strips any pre-existing `traceparent`, `baggage`, `tracestate`, and private
diagnostic headers, then emits only the current internal `traceparent` and two
canonical UUID diagnostic headers. API-side publication hooks are installed
once per process and select the request-bound runtime; worker providers remain
child-owned after fork.

Application-owned Celery receivers use only public signal APIs. `task_prerun`
first clears any abandoned diagnostic/span context, validates the private UUID
headers, starts one consumer span from traceparent, binds fresh child-owned
context tokens, and starts a monotonic duration. Normal `task_postrun`,
`task_failure`, and `task_retry` converge on one idempotent exit that records a
fixed outcome without inspecting the exception/reason, ends the span, records
one normalized metric, and resets every token. Missing or malformed headers use
the canonical task UUID for both diagnostic IDs and cannot inherit prior task
state. A hostile exception `__str__` is never invoked by Workstream telemetry.

Providers and instrumentation state are created after Celery's prefork child
startup; the parent owns no exporter threads. Shutdown first performs a bounded
flush and then closes child providers without making completion of product work
depend on exporter success. Repeated app factories or signals do not add
duplicate handlers, providers, spans, or metrics.

The outbox remains a deliberate partial-linkage boundary. Direct broker
publication keeps the live trace context. Periodic recovery or process restart
starts a new trace because W3C context is not durable. Once delivery loads the
canonical envelope and `_begin_invocation` exits its transaction successfully,
`OutboxDelivery.invoke` calls only the generic core span annotator with the
existing bounded `correlation_id`. It is not reinterpreted as a trace ID, metric
label, authority fact, or new persisted value.

Operational documentation treats profiling as a short, explicitly scoped local
or incident procedure using approved runtime tools. No profiler dependency,
daemon, endpoint, or continuous capture is added.

### Alternatives considered

- FastAPI native telemetry was rejected because its pre-route raw path/query
  capture and process-global propagation make the closed capture boundary
  depend on rewriting a broader framework span. One explicit ASGI
  span/measurement path is smaller and directly testable.
- FastAPI and Celery contrib/automatic instrumentation were rejected because
  they add broader callbacks and attributes than the contract. The official
  Celery failure/retry callbacks render exceptions/reasons, and its duration
  metric includes raw worker hostname; disconnecting private callbacks would be
  brittle and could duplicate application metrics.
- Exporting framework spans unchanged was rejected because native FastAPI can
  include raw query data and official Celery instrumentation can include
  exception/retry content.
- Persisting W3C trace context in outbox events was rejected because it would
  expand business evidence and signed/digested payloads for a diagnostic
  concern. The documented partial trace plus existing outbox correlation ID is
  the smaller safe boundary.
- A Prometheus endpoint, vendor agent, dashboard stack, or mandatory collector
  was rejected as deployment expansion. OTLP HTTP/protobuf keeps the runtime
  provider-neutral and optional.
- SQL, HTTP client, object-store, and model-provider auto-instrumentation was
  rejected for this chunk because it expands privacy and cardinality risk. The
  OpenAI SDK's existing sensitive tracing disablement remains intact.
- Default composite propagation and parent-based sampling were rejected because
  baggage/tracestate can carry arbitrary input and a remote sampled bit must not
  override the local sampling budget.

### Boundaries preserved / what must not change

- Durable audit and immutable lifecycle evidence remain authoritative.
- Request/correlation headers retain their existing validation and response
  contract.
- Product transactions, retries, outbox claims, handler invocation, and atomic
  outcomes are unchanged even when telemetry is disabled or broken.
- OpenTelemetry propagation is diagnostic transport metadata only and never an
  authorization, replay, idempotency, ordering, or ownership input.
- The collector endpoint is optional. Implementation, deployment configuration,
  collector availability, and operator dashboards are separate claims.

## Acceptance criteria

- [ ] The single explicit ASGI path produces exactly one HTTP server span and
      the closed application-owned HTTP metrics per request; FastAPI native and
      contrib instrumentation are absent.
- [ ] API logs and exported spans reuse the exact validated HTTP request and
      correlation IDs under concurrent requests, and the formatter/provider
      state is not mutated per request or replaced by repeated/overlapping app
      factory lifespans.
- [ ] A real prefork Celery child initializes providers after fork, extracts the
      producer trace and validated diagnostic IDs through application-owned
      public signal handlers, and executes under the same trace; repeated
      initialization produces one consumer span and one metric without worker
      hostname.
- [ ] A privacy-canary probe across structured logs, captured exported spans,
      and metrics proves credentials, bodies, guide/task/prompt/ZIP content,
      signed URLs, raw query values, SQL parameters, exception messages/stacks,
      and arbitrary extras are absent.
- [ ] Privacy-canary logging tests use the real configured Uvicorn access/error,
      Celery task/retry/error, Kombu/OpenTelemetry, SQLAlchemy, Workstream, and
      unknown logger paths with sensitive data placed separately in `msg`,
      interpolation arguments, exception objects, and extras; output contains
      only registered constant event values.
- [ ] Metric attribute keys and values remain in the closed low-cardinality set
      across requests and tasks with different record/user/project/request IDs.
      Unknown methods, routes, task names, exception classes, and outcome values
      map to one fixed `other`/`unmatched` category.
- [ ] Public HTTP ignores incoming `traceparent`, `tracestate`, and baggage,
      starts a random local trace, and applies only the configured local sample
      ratio. Broker propagation emits only that internal `traceparent` plus the
      two canonical UUID diagnostic headers; baggage and tracestate canaries do
      not reach child context or outbound headers.
- [ ] Missing endpoint, invalid endpoint, exporter construction failure,
      collector refusal/timeout, force-flush failure, and shutdown failure do
      not change HTTP/task outcomes; startup and shutdown remain within tested
      bounds.
- [ ] Repeated `create_app` use and repeated Celery signal setup do not duplicate
      handlers, providers, instrumentation, spans, or metric readers.
- [ ] Two sequential tasks in one real prefork child prove normal, failure, and
      retry exits reset all span/diagnostic tokens; a second task with missing or
      malformed headers cannot inherit the first task's IDs or trace context.
- [ ] A task failure carrying an exception whose `__str__` raises is handled by
      Workstream telemetry without calling that method or changing the task's
      product outcome.
- [ ] Direct API-to-Celery work retains causal trace context. Outbox recovery
      honestly begins a new trace and adds the existing persisted correlation ID
      only after the canonical envelope is loaded; no business row, payload,
      digest, schema, or authorization input changes.
- [ ] The OpenAI Agents SDK remains configured with tracing disabled and
      sensitive trace data disabled.
- [ ] Operator docs distinguish implemented instrumentation from configured
      export and deployed monitoring, document safe OTLP credentials through
      runtime environment only, state the outbox trace gap, and keep profiling
      on demand.
- [ ] Focused tests, the relevant existing API/Celery/outbox tests, lint,
      dependency-lock verification, markdown links, stale-wording scan, and the
      repository's applicable deterministic gates pass.

### Behavior ownership and named proof

| Behavior | Owner | Named test |
|---|---|---|
| Repeated and overlapping app lifespans keep distinct app providers and one process log handler | `app.main` composition with `app.core.observability` runtime | `tests/test_observability.py::test_overlapping_app_lifespans_keep_owned_providers_and_one_log_handler` |
| Exporter/provider threads are absent in the Celery parent and initialized in the real child only | `app.workers.celery_app` `worker_process_init` composition | `tests/test_observability.py::test_real_prefork_initializes_telemetry_only_in_child` |
| One task duration metric uses a registered task name plus fixed outcome and never hostname or IDs | Core task metric with immutable task inventory supplied by Celery composition | `tests/test_observability.py::test_worker_task_metric_is_single_and_has_no_hostname_or_ids` |
| Normal, failure, retry, missing-header, and malformed-header task exits cannot leak context to the next task in one child | Core public Celery signal receivers and child-owned context tokens | `tests/test_observability.py::test_real_prefork_sequential_tasks_cannot_inherit_diagnostic_context` |
| Core diagnostics stays acyclic and imports no worker or product module | Composition-root boundary | `tests/test_observability.py::test_observability_core_has_no_worker_or_module_imports` |
| Existing outbox correlation annotates only after the canonical invocation marker and envelope transaction commit | `app.modules.outbox.delivery.OutboxDelivery.invoke` calling generic core annotation | `tests/outbox/test_delivery_postgresql.py::test_diagnostic_annotation_follows_committed_invocation_envelope` |
| Every exported API/worker span and metric has only closed keys and normalized values | Core explicit ASGI/Celery instrumentation and sanitizing exporter | `tests/test_observability.py::test_complete_export_sets_are_closed_and_bounded` |
| Dynamic logger data and hostile exception stringification never enter Workstream diagnostics | Core closed log-event map and signal exits | `tests/test_observability.py::test_real_loggers_and_hostile_exception_never_render_sensitive_values` |
| Collector refusal, timeout, flush failure, and shutdown failure remain bounded and do not change request/task outcomes | Core exporter/runtime lifecycle | `tests/test_observability.py::test_collector_failure_is_bounded_and_product_flow_succeeds` |

## Risk and review routing

- Risk class: L1
- Urgency: No delivery SLA supplied.
- Work type: infrastructure, architecture, dependency, security/privacy, test,
  and documentation.
- Required reviewers: `architecture`, `security`, `qa`, `test_delta`,
  `documentation`, `reuse_dedup`, and `senior_engineering`. No CI workflow,
  product-operations lifecycle, schema, payment, or authorization reviewer is
  routed by this scope.
- Human gate: Lead plan review before application edits; human merge approval
  after exact-head proof and review.
- Budget posture: Sol high with this record, exact diff, and focused owners only;
  Astra remains lead.
- Why: The change is bounded to diagnostics but crosses API and prefork worker
  composition, dependency lock, sensitive-data export, and shutdown behavior.
- Human review focus: the closed export/log/metric field sets; whether the
  outbox partial-linkage boundary is honest and useful; fail-open and bounded
  shutdown behavior; duplicate instrumentation prevention; and wording that
  separates implemented, configured, exported, and deployed capabilities.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing API IDs and sanitized failures are reusable | Inspect `app.core.api_controls.RequestContextMiddleware` and `tests/test_api_controls.py` | Confirmed at base `176952e6624244bdc405bac973ce6c4abddb0dae` | No logging/tracing context exists yet |
| Worker telemetry must initialize after fork | Inspect `app.workers.celery_app` hooks and OpenTelemetry prefork guidance | Confirmed; application providers and signal state will be child-owned after `worker_process_init` | Runtime proof remains future implementation evidence |
| Native FastAPI defaults are broader than the closed capture contract | Inspect FastAPI 0.142.2 `fastapi.telemetry._asgi` and `_api` source | Confirmed raw `url.query` span attribute and exception log content; native telemetry rejected for this change | No runtime dependence on native telemetry remains |
| Explicit ASGI instrumentation is the selected HTTP implementation | Compare FastAPI 0.142.2 source with the required capture allowlist | One small application-owned span/metric path avoids raw pre-route capture and global HTTP propagation | No native/contrib fallback or compatibility path remains |
| Official Celery auto-instrumentation exceeds the privacy/cardinality boundary | Inspect OpenTelemetry Celery 0.66b0 source | Confirmed exception/retry string rendering and `flower.task.runtime.seconds` hostname label; application-owned public signal receivers selected | Signal-order and cleanup behavior remain future runtime evidence |
| No trace context can honestly survive current durable outbox recovery | Inspect outbox envelope/model/worker and all broker publication call sites | Confirmed: business correlation exists, W3C context is not persisted | New trace after restart/recovery is intentional |
| Application behavior and tests | Future focused pytest nodes plus existing API, Celery topology, and outbox suites | Pending implementation | Real collector deployment remains outside repository proof |
| Dependency integrity | `cd backend && uv lock --check && uv sync --locked --extra dev --extra agents` on the supported matrix | Pending implementation | Hosted CI remains final environment proof |

## Review findings

- `ARCH-OBS-001`: choose one HTTP implementation rather than a native/custom
  runtime fallback. Resolved in plan by selecting the explicit ASGI path only.
- `ARCH-OBS-002`: avoid official Celery instrumentation teardown through private
  callback internals and duplicate metrics. Resolved in plan with
  application-owned public signal receivers.
- `ARCH-OBS-003`: keep dependency direction explicit. Resolved in plan by
  passing immutable route/task inventories from composition roots and
  prohibiting core imports of workers/product modules.
- `ARCH-OBS-004`: bind every behavior to an owner and named discriminating test.
  Resolved in the behavior ownership table; runtime evidence remains pending.
- `SEC-OBS-001`: start public requests from fresh locally sampled traces so
  caller-selected trace IDs/flags cannot force export. Resolved in plan; public
  propagation input is ignored.
- `SEC-OBS-002`: make child context cleanup explicit across normal, failure,
  retry, missing, and malformed header paths. Resolved in plan with child-owned
  tokens, idempotent exits, and sequential real-prefork proof.
- `SEC-OBS-003`: prove hostile exception formatting is never invoked by the
  diagnostics path and ensure outbox correlation follows committed custody.
  Resolved in plan and named proof; runtime evidence remains pending.

No application implementation begins until architecture and security reviewers
replay this amended plan.

## Reconciliation

- Current-source reconciliation: Based on main commit
  `176952e6624244bdc405bac973ce6c4abddb0dae`. Shared README and roadmap wording
  will be reconciled with concurrent product work before PR readiness.
- Next usable boundary: Implement this one bounded diagnostics foundation after
  lead plan review; deployment-specific collectors, dashboards, alerts, and SLOs
  remain separate operational work.
- Remaining risks: Celery signal ordering and OpenTelemetry SDK/exporter
  internals can change across dependency upgrades, so privacy, cleanup, and
  duplicate-instrumentation tests must bind the selected lock. An unavailable
  collector is deliberately tolerated, which
  means operators must monitor collector health outside product request flow.
