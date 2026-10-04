# Observability Foundation — Safe API And Celery Diagnostics

- Initiative: None
- Durable disposition: Complete
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
logs, sampled traces, bounded metrics, API/Celery correlation, and operational
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
  level, OTLP endpoint, and trace sample ratio, with the API and Celery process sharing
  the same deployment environment while using distinct fixed service names.
- `backend/app/core/config.py`: typed, bounded diagnostics configuration and
  validation. Collector endpoints must be absolute HTTP(S) URLs with canonical
  ASCII DNS/IP hosts and valid ports, without embedded credentials, paths,
  query strings, fragments, whitespace, control characters, Unicode,
  percent-encoding, or ambiguous numeric hosts. Production-like environments
  require HTTPS; validation errors remain fixed and input-free.
- `backend/app/interfaces/observability.py` and
  `backend/app/adapters/observability.py`: one ADR 0014 typed export capability
  extending `ExternalServiceAdapter`, its immutable exporter bundle, the sole
  typed `ExternalServiceAdapterFactory` registration, and the sole concrete
  OTLP HTTP exporter/metric-reader construction path.
- `backend/app/core/diagnostic_logging.py`: closed JSON formatting,
  context-local diagnostic IDs, and reference-safe process logging ownership.
- `backend/app/core/observability.py`: explicit OpenTelemetry resources and
  providers, local-budget sampling, safe span export, closed HTTP metrics, and
  bounded shutdown using only an already-composed typed export adapter. Core
  must not import or construct concrete OTLP exporters/readers or inspect
  collector configuration.
- `backend/app/core/celery_observability.py`: trusted-broker traceparent
  propagation with a complete validated private diagnostic tuple, child-owned
  task context/spans/metrics, public signal registration, and Celery-parent
  logging setup without parent exporters.
- `backend/app/core/api_controls.py`: bind the existing validated request and
  correlation IDs for the duration of the ASGI request and annotate the active
  span without changing validation, response, or error behavior.
- `backend/app/main.py`: call only the canonical observability adapter-package
  builder, pass the immutable built route inventory to one application-owned
  ASGI instrumentation path, and manage the app-owned runtime through lifespan.
- `backend/app/workers/celery_app.py`: explicitly compose only the canonical
  narrow observability adapter builder, pass the immutable registered task
  inventory to application-owned Celery signal instrumentation, construct the
  adapter/exporters and providers only after `worker_process_init`, and
  flush/shut down in bounded Celery process hooks without disturbing
  artifact-runtime ownership.
- `backend/app/modules/outbox/delivery.py`: retain the single annotation owner
  after `_begin_invocation` loads the canonical envelope and its transaction
  commits. The repair may clarify or guard that seam but must not add an
  annotation to expired-attempt `recover`, persist trace context, or change
  delivery, authorization, digest, retry, or handler behavior.
- `backend/tests/test_observability.py`,
  `backend/tests/test_observability_otlp.py`,
  `backend/tests/observability_test_support.py`,
  `backend/tests/test_celery_observability.py`,
  `backend/tests/test_api_controls.py`, `backend/tests/test_config.py`, and
  `backend/tests/test_artifact_architecture.py` plus focused existing
  `backend/tests/outbox/test_delivery_postgresql.py` and
  `backend/tests/outbox/test_recovery_postgresql.py`: observable privacy,
  adapter ownership, correlation, fail-open, lifecycle, real-prefork,
  duplicate-instrumentation, committed recovery, and bounded-cardinality proof.
- `backend/scripts/test_lane_catalogue.py`,
  `backend/scripts/behavior_ownership.py`,
  `backend/scripts/identifier_generation_classifications.json`,
  `backend/tests/test_ci_lane_catalogue.py`, and
  `.ci/behavior-ownership/partition.v1.json`: register the diagnostics tests
  once on the hosted schema/architecture lane with measured headroom, and add
  exact ownership entries for every production diagnostics module, including
  the new typed interface and concrete adapter, without
  changing lane count, caps, or workflow. The three existing routing-request
  proof modules may move together from task C to the schema lane to repair the
  measured timeout; preserve their exact-once inventory and every assertion.
- `docs/engineering/observability.md`, `docs/architecture_data_model.md`, and
  the existing README logs section: operator configuration, interpretation,
  limitations, troubleshooting, on-demand profiling guidance, and accurate
  references from retained product evidence to privacy-bounded diagnostics.
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
- Treating a valid traceparent or private diagnostic tuple as authentication.
  Direct broker publication is inside the broker credential/ACL trust boundary;
  this change adds no signing, publisher-authentication, or authority subsystem.
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
- Configurable or caller-provided OpenTelemetry resource attributes, including
  application version, `OTEL_RESOURCE_ATTRIBUTES`, and `OTEL_SERVICE_NAME`.
- Direct concrete OTLP exporter/reader construction outside the sole registered
  adapter, a second construction path, generic service locator, mutable global
  registry, compatibility alias, or fallback provider.
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
`traceparent` plus validated Workstream diagnostic UUIDs through broker headers
inside the credentialed, ACL-restricted broker publisher boundary. A consumer
uses parentage only for a registered task carrying the complete valid tuple;
every partial, malformed, or unregistered case starts a fresh local root. The
tuple is not authentication and never supplies product authority.
A missing endpoint disables export. An invalid endpoint fails startup with a
fixed error that cannot echo its input. After valid configuration, a slow or
unavailable collector cannot block requests, tasks, or shutdown beyond the
configured bound.

### Design chosen

`app.interfaces.observability` owns the minimal typed export contract:
`ObservabilityExportAdapter` extends `ExternalServiceAdapter` and returns one
immutable `ObservabilityExporterBundle` containing one span exporter and one
metric reader. `app.adapters.observability` is the sole concrete provider. Its
composition builder creates one instance-local
`ExternalServiceAdapterFactory[ObservabilityExportAdapter]`, explicitly
registers only `otlp_http`, creates the selected adapter, and then discards the
factory. Composition roots import only that builder; neither the factory nor a
registry is passed into core. Missing endpoint configuration returns disabled
export before factory creation and is the only non-adapter branch.

The OTLP adapter creates both concrete resources as one owned operation. If
construction fails after either resource exists, it starts independent shutdown
for every constructed resource, waits only the configured bound, and raises a
stable `ExternalServiceConfigurationError` containing only the adapter identity.
A cleanup that outlives that bound retains the existing safe-logging lease until
the cleanup thread exits. On success, ownership transfers in the immutable
bundle to `ObservabilityRuntime`. API composition builds the adapter at
lifespan composition. Celery composition stores only a narrow typed builder and
invokes it after `worker_process_init`; no adapter, exporter, reader, factory,
SDK provider, or exporter thread crosses fork. Runtime has no direct
exporter/reader injection or construction path; focused tests use the same port
with a fake adapter.

`app.core.observability` owns explicit application-created tracer and meter
providers plus one explicit ASGI middleware, receiving only that typed adapter.
Native FastAPI telemetry was
evaluated and rejected: even with native logs, metrics, and automatic export
disabled, it first records raw path/query values, consumes process-global
propagation, and requires an export rewrite to establish the closed field
contract. The explicit middleware starts one fresh local trace, records no
headers, URL, query, body, exception, dependency, serialization, or background
task content, and closes the span with only normalized method, registered route
template, status class, outcome, and validated diagnostic IDs. It records the
matching application-owned metrics from the same normalized values. There is no
native/contrib compatibility path or runtime switch. The API service name is
fixed to `workstream-api` and the Celery service name to `workstream-celery`,
and export resources contain exactly that fixed name plus the bounded
deployment environment. Configurable `app_version`, `OTEL_SERVICE_NAME`,
`OTEL_RESOURCE_ATTRIBUTES`, process environment metadata, and arbitrary
instrumentation-scope metadata are never copied into spans or metrics;
`service.version` is omitted rather than sanitized or projected.

Public HTTP ignores inbound `traceparent`, `tracestate`, and baggage and starts a
fresh random local trace. Trace sampling uses a local trace-ID ratio sampler
with a validated ratio, so caller-chosen IDs and remote sampled flags cannot
override the Workstream budget. Internal Celery publication propagates the
locally created traceparent only after removing all prepopulated traceparent,
tracestate, baggage, and private diagnostic headers, and adds canonical
request/correlation UUIDs from the current context. A receiver accepts that
remote parent only for an exact registered task with a valid traceparent and
both valid UUID headers; otherwise it starts a fresh local root and uses
canonical fallback diagnostic IDs. Direct raw publication is trusted only
through broker credentials and publisher ACLs. The tuple is deliberately not a
MAC or proof of publisher identity, and this change adds no signing or
authentication subsystem. Within that operational trust boundary, the child
continues the same trace and sampling decision. A small
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
once per process and select the request-bound runtime; Celery providers remain
child-owned after fork.

Application-owned Celery receivers use only public signal APIs. `task_prerun`
first clears any abandoned diagnostic/span context, validates the private UUID
headers and registered task before accepting traceparent, starts one consumer
span from the accepted parent or a fresh local root, binds fresh child-owned
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
label, authority fact, or new persisted value. Process restart/recovery uses the
existing pending-event scan and worker delivery path: the scan starts a new root
disconnected from the original business trace, and canonical publication makes
delivery its child within that recovery trace. `deliver`/`invoke` reaches the
same post-commit annotation seam, where only the delivery span gains the stored
correlation. Expired-attempt `recover` and completed or duplicate delivery remain
unannotated. Before/after database snapshots and
model/schema inspection prove that the diagnostic seam adds no trace field and
changes no payload, digest, authorization input, repeated effect, or product
decision; only canonical delivery-custody changes are permitted.

`app.core.config._canonical_observability_endpoint` is the single strict-origin
owner used before every Pydantic validation path, including direct values,
environment variables, and dotenv input. It accepts only bounded canonical
ASCII DNS labels or canonical `ipaddress` IPv4/IPv6 hosts and ports 1 through
65535. It allows at most one root slash and canonicalizes that slash away. It
rejects whitespace/control/Unicode/percent-encoding, credentials, other paths,
raw query/fragment delimiters even when empty, trailing dots,
empty/underscore/overlong or leading/trailing-hyphen labels, ambiguous
whole-host decimal/hex numeric labels, and malformed numeric, IPv6, or port
forms.
It does not resolve DNS or reject private addresses because internal collectors
are valid operator-owned destinations. Every rejection raises the same
input-free error after the raw value is discarded. The nearby private MinIO
normalizer is intentionally not reused: it owns a looser S3-specific endpoint
contract that does not close the reported DNS/IPv4 gap, while tightening it
would change artifact-provider behavior outside this repair. No generic endpoint
framework is introduced.

Operational documentation treats profiling as a short, explicitly scoped local
or incident procedure using approved runtime tools. No profiler dependency,
daemon, endpoint, or continuous capture is added.

The operator contract distinguishes failure sources rather than promising one
event for every SDK path. Adapter construction and application-owned
provider/lifecycle failures emit the fixed `observability_export_unavailable`
event. OTLP SDK HTTP/protocol failures are reduced by safe logger ownership to
the fixed `opentelemetry.error` event. Neither path renders endpoint, response,
exception, or credential content, and neither changes request/task outcomes.
Deployment guidance requires TLS in production-like environments, secret
injection for any collector headers, broker publisher and collector/log-query
ACLs, process egress limited to the collector, encryption at rest where the
backend retains diagnostics, a finite approved retention/deletion policy, and a
release drill that verifies privacy canaries, correlation, outage behavior,
deletion, and the outbox trace gap. Repository support does not claim these
deployment controls are active.

### Alternatives considered

- FastAPI native telemetry was rejected because its pre-route raw path/query
  capture and process-global propagation make the closed capture boundary
  depend on rewriting a broader framework span. One explicit ASGI
  span/measurement path is smaller and directly testable.
- FastAPI and Celery contrib/automatic instrumentation were rejected because
  they add broader callbacks and attributes than the contract. The official
  Celery failure/retry callbacks render exceptions/reasons, and its duration
  metric includes raw Celery hostname; disconnecting private callbacks would be
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

- [x] Serialized OTLP span and metric payloads contain exactly the fixed
      `service.name` and bounded `deployment.environment.name` resource keys.
      Hostile `app_version`, `OTEL_SERVICE_NAME`, and
      `OTEL_RESOURCE_ATTRIBUTES` canaries are absent; no `service.version` is
      emitted.
- [x] Core imports no concrete OTLP exporter or periodic reader and accepts only
      the typed `ObservabilityExportAdapter`. API and post-fork Celery roots use
      the one adapter-package builder and one instance-local typed factory;
      tests use the same port with a fake adapter. Partial bundle construction
      starts bounded independent cleanup for every constructed exporter/reader,
      retains safe logging until delayed cleanup exits, and raises only a stable
      identity-bearing, input-free external-service error.
- [x] The strict endpoint owner accepts only canonical bounded ASCII DNS/IP
      origins and valid ports, canonicalizes one root slash, rejects invalid
      DNS, ambiguous decimal/hex numeric hosts, IPv6, port, whitespace, control,
      Unicode, percent-encoded, credential, path, and raw query/fragment forms
      including empty delimiters, and produces one input-free error through direct,
      environment, dotenv, and model validation paths.
- [x] The single explicit ASGI path produces exactly one HTTP server span and
      the closed application-owned HTTP metrics per request; FastAPI native and
      contrib instrumentation are absent.
- [x] API logs and exported spans reuse the exact validated HTTP request and
      correlation IDs under concurrent requests, and the formatter/provider
      state is not mutated per request or replaced by repeated/overlapping app
      factory lifespans.
- [x] A real prefork Celery child initializes its adapter, exporter bundle, and
      providers after fork, extracts the
      producer trace and validated diagnostic IDs through application-owned
      public signal handlers, and executes under the same trace; repeated
      initialization produces one consumer span and one metric without Celery
      hostname.
- [x] A privacy-canary probe across structured logs, captured exported spans,
      and metrics proves credentials, bodies, guide/task/prompt/ZIP content,
      signed URLs, raw query values, SQL parameters, exception messages/stacks,
      arbitrary extras, span events, and span links are absent. The real OTLP
      protobuf proof starts with hostile event/link content, and independent
      event-retention and link-retention mutants each fail that proof.
- [x] Privacy-canary logging tests use the real configured Uvicorn access/error,
      Celery task/retry/error, Kombu/OpenTelemetry, SQLAlchemy, Workstream, and
      unknown logger paths with sensitive data placed separately in `msg`,
      interpolation arguments, exception objects, and extras; output contains
      only registered constant event values. SQLAlchemy and its engine logger
      keep a `WARNING` minimum without weakening stricter configured levels, so
      routine statement/transaction logs are not amplified by diagnostics.
- [x] Metric attribute keys and values remain in the closed low-cardinality set
      across requests and tasks with different record/user/project/request IDs.
      Unknown methods, routes, task names, exception classes, and outcome values
      map to one fixed `other`/`unmatched` category.
- [x] Public HTTP ignores incoming `traceparent`, `tracestate`, and baggage,
      starts a random local trace, and applies only the configured local sample
      ratio. The canonical Redis publisher strips forged trace and private
      headers before emitting the current internal `traceparent` plus two
      canonical UUID diagnostic headers. Only a registered task with that
      complete valid tuple can parent a consumer; partial, malformed, or
      unregistered cases start a fresh local trace whose identity/sampling is
      not inherited. Baggage and tracestate never reach child context.
- [x] An invalid endpoint fails startup with a fixed error that does not retain
      or echo input. A missing endpoint disables export; exporter construction
      failure, real OTLP HTTP 503/refusal/timeout, force-flush failure, and
      shutdown failure do not change HTTP/task outcomes and remain within
      tested bounds. A successful local receiver decodes the SDK's real protobuf
      payload; this proves transport and serialization, not a deployed collector.
- [x] Repeated `create_app` use and repeated Celery signal setup do not duplicate
      handlers, providers, instrumentation, spans, or metric readers.
- [x] Two sequential tasks in one real prefork child prove normal, failure, and
      retry exits reset all span/diagnostic tokens; a second task with missing or
      malformed headers cannot inherit the first task's IDs or trace context.
- [x] A task failure carrying an exception whose `__str__` raises is handled by
      Workstream telemetry without calling that method or changing the task's
      product outcome.
- [x] Direct API-to-Celery work retains causal trace context through the trusted
      broker-publisher boundary. Outbox recovery
      honestly begins a new trace and adds the existing persisted correlation ID
      only on the delivery child after canonical scan publication reaches the
      existing post-`_begin_invocation` commit seam; the scan root remains
      disconnected from the original business trace, and expired-attempt recovery and
      duplicate/completed delivery add no annotation, and no business row,
      payload, digest, schema, authorization input, repeated handler effect, or
      product outcome changes beyond canonical delivery custody.
- [x] The OpenAI Agents SDK remains configured with tracing disabled and
      sensitive trace data disabled.
- [x] Operator docs distinguish implemented instrumentation from configured
      export and deployed monitoring, document safe OTLP credentials through
      runtime environment only, state the broker ACL trust boundary and outbox
      trace gap, describe actual constant construction/lifecycle events versus
      safe SDK network-error events, require collector/log backend access
      control, encryption, finite retention/deletion verification and a release
      outage/privacy/correlation drill, and keep profiling on demand.
- [x] Focused tests, the relevant existing API/Celery/outbox tests, lint,
      dependency-lock verification, markdown links, stale-wording scan, and the
      repository's applicable deterministic gates pass.

### Behavior ownership and named proof

| Behavior | Owner | Named test |
|---|---|---|
| Valid IDs, invalid IDs, an unmatched route, and an exception route each produce exactly one HTTP server span, one request-duration measurement, and balanced active-request increment/decrement measurements, with no FastAPI-native or contrib span/metric names or providers | `app.main` composition with the one explicit `app.core.observability` ASGI path | `tests/test_observability.py::test_api_emits_exactly_one_http_span_and_metric_set_for_every_route_outcome` |
| Concurrent requests retain their own validated request/correlation IDs in logs and spans and reset both contexts after completion | `app.core.api_controls.RequestContextMiddleware` with core child-owned diagnostic context tokens | `tests/test_observability.py::test_concurrent_api_diagnostic_context_is_isolated` |
| Public `traceparent`, `tracestate`, baggage, caller-chosen trace IDs, and sampled flags cannot select the local trace identity or override the local sample decision | Core explicit ASGI trace start and local root sampler | `tests/test_observability.py::test_public_propagation_and_sampling_input_cannot_control_local_trace` |
| Serialized OTLP trace and metric protobuf resources contain only fixed `service.name` and bounded `deployment.environment.name`; hostile `app_version`, standard OTEL environment resource overrides, and `service.version` are absent | Core closed resource construction plus sanitizing span/metric export boundary | `tests/test_observability_otlp.py::test_serialized_otlp_payload_has_exact_resource_allowlist` |
| Hostile span event and link names, attributes, and trace state are absent from real serialized OTLP protobufs, and retaining either field independently fails the wire-level privacy assertion | Core sanitizing span exporter before the actual OTLP HTTP adapter | `tests/test_observability_otlp.py::test_serialized_otlp_payload_has_exact_resource_allowlist` plus isolated mutation runs of the production `events` and `links` stripping assignments |
| One instance-local typed factory registers only `otlp_http`; composition roots use its builder, core has no concrete OTLP imports or direct exporter/reader injection path, and fake tests use the same adapter port | `app.interfaces.observability`, `app.adapters.observability`, and API/Celery composition roots | `tests/test_artifact_architecture.py::test_concrete_adapter_construction_has_one_composition_path` and `tests/test_observability_otlp.py::test_runtime_uses_only_the_typed_export_adapter` |
| Failure after partial exporter-bundle construction closes every created span/metric resource, keeps the existing safe logger until detached cleanup exits, and raises one stable identity-bearing input-free external-service error | Concrete OTLP export adapter construction owner plus refcounted core logging lease | `tests/test_observability_otlp.py::test_partial_export_bundle_construction_closes_owned_resources` and `tests/test_observability_otlp.py::test_partial_cleanup_retains_safe_logging_after_bounded_runtime_shutdown` |
| Repeated and overlapping app lifespans keep distinct app providers and one process log handler | `app.main` composition with `app.core.observability` runtime | `tests/test_observability.py::test_overlapping_app_lifespans_keep_owned_providers_and_one_log_handler` |
| API startup, exporter-thread, request, Celery-parent, and Celery-child logs carry exactly one fixed process role outside and inside diagnostic context | Reference-counted process logging ownership composed by API and Celery roots | `tests/test_observability.py::test_overlapping_app_lifespans_keep_owned_providers_and_one_log_handler`, `tests/test_observability.py::test_real_loggers_and_hostile_exception_never_render_sensitive_values`, and `tests/test_celery_observability.py::test_celery_parent_logging_is_safe_without_parent_exporters` |
| Adapter/exporter/provider threads are absent in the Celery parent and initialized in the real child only | `app.workers.celery_app` post-fork adapter-builder and `worker_process_init` composition | `tests/test_celery_observability.py::test_real_celery_prefork_correlates_api_and_resets_sequential_task_context` |
| Real Redis publication through the canonical `apply_async` path removes forged trace/baggage/private headers and emits only the current local traceparent plus both canonical UUID fields | Core before-publish hook composed by API/Celery roots | `tests/test_celery_observability.py::test_real_celery_prefork_correlates_api_and_resets_sequential_task_context` |
| Only a registered task carrying valid traceparent, request ID, and correlation ID receives parentage; partial, malformed, or unregistered tuples start a random local root and cannot inherit the supplied remote sampled flag | Child-only Celery receiver validation and local ratio sampler | `tests/test_celery_observability.py::test_celery_parent_requires_registered_task_and_complete_private_tuple` and `tests/test_celery_observability.py::test_real_celery_prefork_correlates_api_and_resets_sequential_task_context` |
| Direct API-to-Celery publication through the credentialed broker boundary creates one server-to-consumer parent-child trace; the tuple is diagnostic metadata and no product authority consumes it | Core publisher/receiver hooks composed by API and Celery roots | `tests/test_observability.py::test_api_to_celery_trace_is_parent_child_and_headers_are_allowlisted` plus `tests/test_celery_observability.py::test_real_celery_prefork_correlates_api_and_resets_sequential_task_context` |
| Repeating Celery receiver setup leaves one receiver set, one child provider/reader set, one consumer span, and one task metric measurement | Idempotent core signal registration with child-owned Celery runtime | `tests/test_celery_observability.py::test_repeated_celery_receiver_setup_does_not_duplicate_spans_or_readers` |
| One task duration metric uses a registered task name plus fixed outcome and never hostname or IDs | Core task metric with immutable task inventory supplied by Celery composition | `tests/test_observability.py::test_api_to_celery_trace_is_parent_child_and_headers_are_allowlisted` plus `tests/test_celery_observability.py::test_real_celery_prefork_correlates_api_and_resets_sequential_task_context` |
| Normal, failure, retry, missing-header, and malformed-header task exits cannot leak context to the next task in one child | Core public Celery signal receivers and child-owned context tokens | `tests/test_celery_observability.py::test_sequential_task_failures_and_retries_reset_every_context_token` plus `tests/test_celery_observability.py::test_real_celery_prefork_correlates_api_and_resets_sequential_task_context` |
| Core diagnostics stays acyclic and imports no Celery composition or product module | Composition-root boundary | `tests/test_observability.py::test_observability_core_has_no_worker_or_module_imports` |
| Existing outbox correlation annotates only after the canonical invocation marker and envelope transaction commit; before/after snapshots prove no business row, payload, digest, schema, or authorization input changes, and structure checks prove no persisted trace fields | `app.modules.outbox.delivery.OutboxDelivery.invoke` calling generic core annotation | `tests/outbox/test_delivery_postgresql.py::test_diagnostic_annotation_follows_committed_invocation_envelope` |
| A committed pending event selected after process restart starts a scan root disconnected from the original business trace; canonical before-publish headers make delivery its child, only delivery gains the stored correlation after independently visible invocation commit, and expired/duplicate/completed controls remain unannotated with no repeated effect or noncanonical database change | Existing outbox scan/publish/deliver/invoke composition; no recovery-specific telemetry hook | `tests/outbox/test_recovery_postgresql.py::test_pending_recovery_trace_annotates_only_after_committed_invocation` |
| Every exported API/Celery span and metric has only closed keys and normalized values | Core explicit ASGI/Celery instrumentation and sanitizing exporter | `tests/test_observability.py::test_complete_export_sets_are_closed_and_bounded` plus `tests/test_observability.py::test_unknown_http_method_and_varied_ids_collapse_to_one_exact_metric_series` and `tests/test_celery_observability.py::test_unknown_task_and_state_values_collapse_to_one_exact_metric_series` |
| Dynamic logger data and hostile exception stringification never enter Workstream diagnostics | Core closed log-event map and signal exits | `tests/test_observability.py::test_real_loggers_and_hostile_exception_never_render_sensitive_values` |
| Safe logging suppresses real SQLAlchemy statement and transaction INFO output, retains sanitized warning/error events through overlapping leases, and restores both owned logger snapshots after the final release | Core reference-counted logging owner with a SQLAlchemy-family `WARNING` floor | `tests/test_observability.py::test_sqlalchemy_query_logs_are_suppressed_until_final_safe_logging_release` |
| The bounded Celery task-name inventory exactly covers every registered Workstream task from the configured Celery modules | Celery composition root supplying the immutable task inventory | `tests/test_celery_observability.py::test_observed_task_inventory_matches_every_registered_workstream_task` |
| Canonical localhost/DNS/IPv4/IPv6 origins, one optional root slash, and valid ports pass; ambiguous decimal/hex whole-host forms, raw empty query/fragment delimiters, malformed numeric/IP/port, Unicode/percent-encoded/whitespace/control, underscore, trailing-dot, empty/overlong, and leading/trailing-hyphen hosts fail with the same input-free error through kwargs, environment, dotenv, and model-validation paths; production-like environments require HTTPS | Sole strict observability-origin owner in typed settings validation | `tests/test_config.py::test_ambiguous_numeric_host_forms_cannot_fall_through_dns_validation`, `tests/test_config.py::test_observability_endpoint_requires_canonical_http_origin_across_settings_sources`, `tests/test_config.py::test_invalid_observability_endpoint_fails_startup_without_retaining_input`, and `tests/test_config.py::test_production_like_observability_endpoint_requires_https_without_retaining_input` |
| Failure after provider assignment clears provider and instrument references, closes owned resources, and leaves force-flush disabled | Core runtime partial-start cleanup | `tests/test_observability.py::test_failure_after_provider_assignment_clears_every_runtime_reference` |
| A local HTTP receiver decodes real SDK-produced trace and metric OTLP protobufs; separate 503, refusal, and delayed-response cases remain bounded for an API request and one registered local/eager Celery task, preserve the HTTP response and exact task result/invocation count, and emit only documented input-free safe events; the separate Redis proof owns prefork claims | Typed OTLP adapter plus core runtime/export lifecycle and safe logging owner | `tests/test_observability_otlp.py::test_real_otlp_http_transport_is_sanitized_and_fail_open` |
| Explicit runtime shutdown returns before the process-exit bound, normal interpreter exit does not re-enter owned providers, and an SDK-atexit mutant is caught with a blocking shutdown stack | Core provider ownership with SDK exit hooks disabled | `tests/test_observability.py::test_bounded_runtime_shutdown_returns_before_process_exit`, `tests/test_observability.py::test_owned_providers_do_not_register_unbounded_interpreter_exit_hooks`, and `tests/test_observability.py::test_process_exit_probe_rejects_sdk_atexit_shutdown_registration` |
| The OpenAI Agents SDK remains configured with both tracing and sensitive trace data disabled | Existing `app.adapters.project_agents.openai_agent_sdk` owner, unchanged by diagnostics composition | `tests/test_agent_runtime.py::test_unified_compilation_uses_scoped_tools_and_strict_output` |
| Operator guidance matches environment keys and actual failure events, names broker/collector/log-query ACLs, TLS/encryption, egress, finite retention/deletion, non-authority, partial outbox linkage, implementation/deployment distinction, and the release privacy/correlation/outage/deletion drill while keeping profiling on demand | `docs/engineering/observability.md`, README logs section, and typed diagnostics settings | `tests/test_observability.py::test_operator_docs_match_runtime_observability_contract` |

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
- Why: The change is bounded to diagnostics but crosses API and prefork Celery
  composition, dependency lock, sensitive-data export, and shutdown behavior.
- Human review focus: the closed export/log/metric field sets; whether the
  outbox partial-linkage boundary is honest and useful; fail-open and bounded
  shutdown behavior; duplicate instrumentation prevention; and wording that
  separates implemented, configured, exported, and deployed capabilities.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing API IDs and sanitized failures are reusable | Inspect `app.core.api_controls.RequestContextMiddleware` and `tests/test_api_controls.py` | Reused through one canonical UUID validator and context-local binding | Diagnostic IDs remain non-authoritative |
| Celery telemetry must initialize after fork | Inspect `app.workers.celery_app` hooks and real-prefork focused proof | Application providers and signal state are child-owned after `worker_process_init` | Collector deployment remains operational work |
| Native FastAPI defaults are broader than the closed capture contract | Inspect FastAPI 0.142.2 `fastapi.telemetry._asgi` and `_api` source | Confirmed raw `url.query` span attribute and exception log content; native telemetry rejected for this change | No runtime dependence on native telemetry remains |
| Explicit ASGI instrumentation is the selected HTTP implementation | Compare FastAPI 0.142.2 source with the required capture allowlist | One small application-owned span/metric path avoids raw pre-route capture and global HTTP propagation | No native/contrib fallback or compatibility path remains |
| Official Celery auto-instrumentation exceeds the privacy/cardinality boundary | Inspect OpenTelemetry Celery 0.66b0 source | Confirmed exception/retry string rendering and `flower.task.runtime.seconds` hostname label; application-owned public signal receivers selected and exercised through a real prefork process | Dependency upgrades require replay of the privacy and duplicate-instrumentation proofs |
| No trace context can honestly survive current durable outbox recovery | Inspect outbox envelope/model/Celery delivery and all broker publication call sites | Confirmed: business correlation exists, W3C context is not persisted | New trace after restart/recovery is intentional |
| External review repair boundary | Inspect exported resources, concrete OTLP imports/construction, endpoint parsing, broker signal handlers, outbox scan/delivery/recovery, tests, and operator guide at `667f98ea9aff44a4437ef983e67e1c9e63aa55e2` | Removed `service.version`, installed one ADR 0014 adapter path, strict origins, trusted-broker tuple validation, real OTLP HTTP/protobuf and PostgreSQL recovery proof, and access/retention guidance | Exact-head implementation review and hosted CI remain pending |
| Application behavior and tests | Focused API, Celery, controls, configuration, topology, agent-runtime, ownership, architecture, identifier-inventory, real Redis prefork, local OTLP HTTP/protobuf, and isolated PostgreSQL outbox proofs | Prior 300-test baseline passed; at repair head `1c950651`, 225 focused tests including all seven OTLP cases and real Redis prefork proof, the isolated PostgreSQL scan/delivery recovery proof, and 227 repository-contract tests pass. At subsequent repair head `9ad8ae15`, 30 observability/real-Redis tests, three process-exit probes, one isolated PostgreSQL recovery test, and 123 architecture/preflight tests plus the direct validators pass | Real collector deployment remains outside repository proof |
| Dependency integrity | `cd backend && uv lock --check` with the committed SDK/exporter lock | Locked dependency graph passes | Hosted CI remains final environment proof |

## Review findings

- `ARCH-OBS-001`: remove duplicate Celery instrumentation and its overlapping
  duration metric. Resolved in plan by excluding the official instrumentor and
  selecting one application-owned public-signal implementation.
- `ARCH-OBS-002`: define child-owned diagnostic context cleanup for every task
  exit. Resolved in plan with entry clearing, child-owned tokens, one idempotent
  normal/failure/retry exit, and two-task real-prefork leakage proof.
- `ARCH-OBS-003`: keep dependency direction explicit. Resolved in plan by
  passing immutable route/task inventories from composition roots and
  prohibiting core imports of workers/product modules.
- `ARCH-OBS-004`: bind every behavior to an owner and a discriminating test
  whose assertions prove count, causality, cleanup, or composition directly.
  Resolved in the behavior ownership table with separate named proofs for HTTP
  count/outcomes, concurrent context isolation, public propagation and local
  sampling, API-to-Celery parentage/header allowlisting, repeated receiver
  setup, retained OpenAI tracing disablement, and operator-doc consistency;
  runtime evidence remains pending.
- `SEC-OBS-001`: prevent exception/retry string rendering by Workstream
  telemetry. Resolved with constant outcomes, no exception events or status
  descriptions, and hostile-`__str__` proof through the real logger/task paths.
- `SEC-OBS-002`: remove duplicate/raw Celery metrics, especially raw hostname
  and unregistered task values. Resolved by excluding the official instrumentor
  and emitting one application metric through the immutable task inventory.
- `SEC-OBS-003`: prevent callers from controlling trace identity or sampling.
  Resolved by ignoring all public propagation input, starting a random local
  root, and applying only the locally configured root-sampling budget.
- `SEC-OBS-004`: correct the security finding identifiers and preserve their
  original disposition in this record. Resolved by the mapping above; the
  security replay found no remaining runtime blocker.
- `DOCS/OPS-OBS-001`: preserve the fixed process role on logs emitted outside
  request/task context, including API startup, Celery parent, and exporter
  threads. Resolved with reference-counted process ownership and the sole
  `workstream-api` / `workstream-celery` role names.
- `DOCS-OBS-002`: make the operator contract actionable. Resolved with the exact
  span and metric inventory, units, attribute semantics, and a practical
  privacy, correlation, outage, and outbox-discontinuity drill.
- `SEC-OBS-IMPL-001`: prevent plaintext production-like collector transport.
  Resolved by requiring HTTPS in staging, preview, prod, and production while
  retaining HTTP for local/test use and fixed input-free validation errors.
- `REUSE-OBS-001`: remove duplicate request UUID validation. Resolved by ASCII
  decoding at the HTTP boundary and delegation to `canonical_uuid_text` with
  the existing API error behavior retained.
- `QA-OBS-001` / `TD-OBS-001`: prove value cardinality rather than key shape
  alone. Resolved with varied-ID BREW requests and unregistered Celery
  task/state values that assert the exact collapsed span and metric series.
- `QA-OBS-002`: clear stale runtime state after failures that occur after
  provider assignment. Resolved by one reset owner and proof that all provider
  and instrument references clear, resources close, and force-flush stays
  disabled.
- `EXT-OBS-001`: configurable `app_version` currently reaches
  `service.version`. Resolved: remove `service.version` and prove the
  exact serialized span/metric resource allowlist against OTEL environment
  canaries.
- `EXT-OBS-002`: concrete OTLP exporters/readers are currently built in core.
  Resolved: move the sole construction path behind an ADR 0014 typed
  adapter/factory, preserves post-fork ownership, and proves partial-construction
  cleanup.
- `EXT-OBS-003`: broker parentage requires an explicit trust boundary. Resolved:
  retain causal traces only for registered tasks with the complete
  canonical tuple, proves canonical publisher stripping and receiver fallback,
  and documents credential/vhost ACL trust without treating telemetry as auth.
- `EXT-OBS-004`: endpoint parsing accepts noncanonical hosts. Resolved: add one
  strict observability-origin owner and an input-free all-source host
  matrix without changing the S3 endpoint contract.
- `EXT-OBS-005`: mocked exporter failures do not prove the real network or
  serialization boundary. Resolved: add local OTLP HTTP/protobuf success,
  503/refusal/timeout, and real PostgreSQL pending-recovery proofs without
  claiming a deployed collector.
- `EXT-OBS-006`: operator guidance overstates failure-event uniformity and omits
  deployed access/retention controls. Resolved: document actual safe
  events plus broker/collector/log-query ACLs, encryption, finite deletion, and
  release-drill requirements as deployment work.
- Endpoint canonicalization replay: resolved ambiguous decimal/hex whole-host
  forms and raw empty query/fragment delimiters without rejecting ordinary DNS
  labels that merely begin with `0x`; all settings sources share the guard.
- Task outage replay: resolved the API-only proof gap by exercising one exact
  registered local/eager Celery task through the real typed OTLP adapter for
  503, refusal, and timeout while keeping the real-prefork Redis claim separate.
- Recovery propagation replay: resolved the dropped-header fixture by capturing
  canonical before-publish headers during the actual scan task and supplying
  them to the actual delivery task; the delivery is a child of the new scan root
  and remains disconnected from the original business trace.
- Logging-amplification replay: resolved SQLAlchemy INFO statement/transaction
  amplification by owning both the family and engine loggers with a `WARNING`
  floor, preserving stricter prior levels and exact final-lease restoration.
- Task-inventory replay: resolved drift risk by comparing the immutable observed
  task inventory with the actual registered Workstream task set.
- Hosted AUTH-boundary preflight: resolved the new oversized recovery-test item
  by extracting cohesive setup, scan/header, committed-annotation, trace-graph,
  and storage assertions while retaining the original named behavior and
  leaving the frozen debt ledger unchanged.
- Process-exit harness replay: diagnosed repeated startup misses as the spawn
  child re-importing the large test module before entering the target. The same
  startup and exit limits now exercise a lightweight target in the existing
  observability test support, with an early target-entry milestone and stack
  capture before runtime startup.
- OTLP fixture-isolation replay: the local/eager collector-outage task is
  application-local, never replaces the process current Celery app, and is
  explicitly removed at fixture exit so it cannot expand the shared Celery task
  registry or weaken the exact production inventory.
- Span privacy replay: hostile events and links now reach the real OTLP
  serialization boundary before sanitization, with independent retention
  mutants proving that each closed-field assertion detects disclosure.
- Architecture-guidance replay: the data-model guide references fixed safe
  events and validated correlation IDs rather than sensitive server logs, links
  the operator guide, and names the bounded retained setup evidence accurately.

Hosted schema-lane replay found the Celery task fallback's UUIDv4 site missing
from the exact generation inventory. The fallback is now classified as a
transport token: it supplies a process-local diagnostic ID only when no
canonical broker task ID exists and never mints or persists a product record.
The full identifier inventory is part of the frozen evidence.

Architecture and security plan replay established this capture boundary before
implementation. The foundation implements the amended design above.

## Reconciliation

- `REUSE-OBS-002`: production authentication startup and collector TLS validation
  use one immutable environment vocabulary owned by `app.core.config`; `main`
  imports it rather than maintaining a second policy list.

- Current-source reconciliation: Based on main commit
  `176952e6624244bdc405bac973ce6c4abddb0dae`. Shared README and roadmap wording
  describe this standalone foundation; concurrent product changes must be
  preserved when their merged main is incorporated.
- Next usable boundary: Configure secured diagnostic collection and exercise it
  in the release drill. Deployment-specific dashboards, alerts and SLOs remain
  operational work; this foundation changes no product lifecycle prerequisite.
- Remaining risks: Celery signal ordering and OpenTelemetry SDK/exporter
  internals can change across dependency upgrades, so privacy, cleanup, and
  duplicate-instrumentation tests must bind the selected lock. An unavailable
  collector is deliberately tolerated, which
  means operators must monitor collector health outside product request flow.

### Hosted lane timing repair

The hosted run at `84872b30` exhausted task C's unchanged 1,200-second
bound after 459 of 483 tests, with no assertion failure and 24 unfinished task
tests. Schema completed in 526.854 seconds; task A and B took 1,099.530 and
1,155.429 seconds. Move the three existing routing-request contract, repository
and storage proof modules together from task C to schema, which already owns
related routing storage contracts. Preserve all tests, exact-once membership,
partition hashing, lane count, timeout, coverage and completeness checks.

The focused catalogue test must prove the exact destination and reject missing,
duplicate and wrong-lane membership. CI-integrity and QA/test-delta review must
inspect this repair, followed by full hosted verification. This allocation
reduces the measured hotspot; it does not claim to eliminate runner variance.
