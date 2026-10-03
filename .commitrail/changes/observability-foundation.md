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
  in 0.142.0; 0.142.2 includes the startup-failure repair needed for the
  non-blocking diagnostics contract.
- FastAPI 0.142.2 native telemetry includes raw `url.query` on HTTP spans and can
  emit exception messages and stack traces as OpenTelemetry logs. The official
  Celery instrumentor can record exception messages, stacks, and retry reasons.
  Neither default is safe enough to export directly under this repository's
  content boundary.
- `app.adapters.project_agents.openai_agent_sdk` explicitly keeps the OpenAI
  Agents SDK's tracing disabled and sensitive trace inclusion false.

## Bounded change

### Allowed

- `.commitrail/changes/observability-foundation.md`: durable intent, boundary,
  proof, and material review disposition.
- `backend/pyproject.toml` and `backend/uv.lock`: upgrade to FastAPI 0.142.2 or
  newer within the existing `<1.0` bound and add only the OpenTelemetry SDK,
  OTLP HTTP/protobuf exporter, and official Celery instrumentation required by
  this design.
- `backend/.env.example`: public, credential-free example settings for log
  level, OTLP endpoint, and trace sample ratio, with the API and worker sharing
  the same deployment environment while using distinct fixed service names.
- `backend/app/core/config.py`: typed, bounded diagnostics configuration and
  validation. Collector endpoints must be absolute HTTP(S) URLs without
  embedded credentials, query strings, or fragments.
- `backend/app/core/observability.py`: one small composition owner for safe JSON
  formatting, context-local diagnostic IDs, explicit OpenTelemetry resources
  and providers, sampling, safe span export, bounded metric views, Celery
  propagation hooks, and bounded shutdown.
- `backend/app/core/api_controls.py`: bind the existing validated request and
  correlation IDs for the duration of the ASGI request and annotate the active
  span without changing validation, response, or error behavior.
- `backend/app/main.py`: pass explicit native FastAPI telemetry settings and
  manage the application-owned runtime through lifespan. Native logs and
  automatic environment configuration remain disabled.
- `backend/app/workers/celery_app.py`: initialize providers and the official
  Celery instrumentor only after `worker_process_init`, then flush/shut down in
  bounded worker shutdown hooks without disturbing artifact-runtime ownership.
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
- Record, actor, user, project, request, correlation, task, trace, or span IDs
  as metric attributes. Metric labels are limited to fixed route templates,
  HTTP method/status/error class, registered Celery task name, and service role.
- FastAPI contrib/ASGI auto-instrumentation alongside native telemetry, OpenAI
  Agents SDK tracing, database/client auto-instrumentation, an always-on
  profiler, a vendor SDK, dashboards, alerting rules, a collector fleet, or
  mandatory external monitoring infrastructure.
- Live or paid provider calls, real credentials, production `.env` access, CI
  workflow changes, global coverage gates, or weakened tests.

## Design and decisions

### Target behavior

The API and every prefork Celery child emit one-line structured logs with stable
service/environment/severity/event fields and, when present, the already
validated request ID, correlation ID, trace ID, and span ID. The API uses
FastAPI's native HTTP spans and metrics exactly once. Celery uses the official
instrumentor in each initialized child and propagates W3C trace context plus
validated Workstream diagnostic IDs through broker headers. A missing,
misconfigured, slow, or unavailable collector cannot block startup, requests,
tasks, or shutdown beyond the configured bound.

### Design chosen

`app.core.observability` owns explicit application-created tracer and meter
providers. FastAPI receives those providers with `logs=False` and
`auto_configure=False`; no second FastAPI instrumentation library is installed.
The API service name is fixed to `workstream-api` and the worker service name to
`workstream-worker`, with application version and deployment environment as
bounded resource attributes.

Trace sampling uses parent-based ratio sampling with a validated ratio and a
small fixed batch queue, batch size, schedule delay, OTLP request timeout, and
shutdown deadline. A sanitizing exporter boundary copies only approved span
names, context, timing, status code without description, links without
attributes, and an explicit attribute allowlist. It drops span events and raw
resource attributes before any in-memory test exporter or OTLP exporter sees
them. This removes FastAPI query/path input and Celery exception/retry content
while preserving route templates, registered task names, HTTP outcomes, safe
diagnostic IDs, and causal trace context. Export construction and export errors
are reduced to constant local diagnostic events.

Metrics use explicit SDK views whose retained attributes are closed and bounded.
HTTP request duration/active-request metrics and Celery task duration are
exportable; record and identity values never become labels. Existing auth and
artifact metric owners remain unchanged in this chunk rather than gaining a
second counter implementation.

The logging configuration is installed idempotently once per process, never
mutated per request, and uses context variables for concurrent isolation. Its
JSON formatter emits a closed field set and never serializes `exc_info`, stack
text, logger arguments as separate fields, or arbitrary extras. Existing static
event messages remain visible. Request middleware binds and resets its current
IDs around the whole ASGI call. Celery publication copies only canonical UUID
IDs into private broker headers; task entry rejects malformed values and falls
back to the canonical Celery task UUID for diagnostic context.

Providers and instrumentation are created after Celery's prefork child startup,
as required by the official instrumentor. Shutdown first performs a bounded
flush and then closes providers/instrumentation without making completion of
product work depend on exporter success. Repeated app factories or signals do
not add duplicate handlers, providers, spans, or metrics.

The outbox remains a deliberate partial-linkage boundary. Direct broker
publication keeps the live trace context. Periodic recovery or process restart
starts a new trace because W3C context is not durable. Once delivery loads the
canonical envelope, its existing bounded `correlation_id` is added to the
current span for operator lookup; it is not reinterpreted as a trace ID, metric
label, authority fact, or new persisted value.

Operational documentation treats profiling as a short, explicitly scoped local
or incident procedure using approved runtime tools. No profiler dependency,
daemon, endpoint, or continuous capture is added.

### Alternatives considered

- FastAPI automatic environment setup was rejected because the application
  needs one explicit provider lifecycle, fail-open construction, and a privacy
  filter before export.
- Native FastAPI plus contrib FastAPI instrumentation was rejected because it
  duplicates spans and metrics. Native FastAPI telemetry alone owns HTTP
  instrumentation after the version upgrade.
- Exporting native spans unchanged was rejected because native FastAPI can
  include raw query data and Celery can include exception/retry content.
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

- [ ] FastAPI resolves at least 0.142.2 and receives explicit native telemetry
      providers with `logs=False` and `auto_configure=False`; no contrib FastAPI
      instrumentation or duplicate HTTP spans/metrics exist.
- [ ] API logs and exported spans reuse the exact validated HTTP request and
      correlation IDs under concurrent requests, and the formatter/provider
      state is not mutated per request.
- [ ] A real prefork Celery child initializes tracing after fork, extracts the
      producer trace and validated diagnostic IDs, and executes under the same
      trace; repeated initialization produces one consumer span and one metric.
- [ ] A privacy-canary probe across structured logs, captured exported spans,
      and metrics proves credentials, bodies, guide/task/prompt/ZIP content,
      signed URLs, raw query values, SQL parameters, exception messages/stacks,
      and arbitrary extras are absent.
- [ ] Metric attribute keys and values remain in the closed low-cardinality set
      across requests and tasks with different record/user/project/request IDs.
- [ ] Missing endpoint, invalid endpoint, exporter construction failure,
      collector refusal/timeout, force-flush failure, and shutdown failure do
      not change HTTP/task outcomes; startup and shutdown remain within tested
      bounds.
- [ ] Repeated `create_app` use and repeated Celery signal setup do not duplicate
      handlers, providers, instrumentation, spans, or metric readers.
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
| Worker telemetry must initialize after fork | Inspect `app.workers.celery_app` hooks and official OpenTelemetry Celery instrumentor documentation/source | Confirmed; official guidance requires provider and instrumentor setup after `worker_process_init` | Runtime proof remains future implementation evidence |
| Native FastAPI defaults are not privacy-safe enough | Inspect FastAPI 0.142.2 `fastapi.telemetry._asgi` and `_api` source | Confirmed raw `url.query` span attribute and exception log content; explicit `logs=False` plus export sanitization required | Future version drift must remain lock-tested |
| No trace context can honestly survive current durable outbox recovery | Inspect outbox envelope/model/worker and all broker publication call sites | Confirmed: business correlation exists, W3C context is not persisted | New trace after restart/recovery is intentional |
| Application behavior and tests | Future focused pytest nodes plus existing API, Celery topology, and outbox suites | Pending implementation | Real collector deployment remains outside repository proof |
| Dependency integrity | `cd backend && uv lock --check && uv sync --locked --extra dev --extra agents` on the supported matrix | Pending implementation | Hosted CI remains final environment proof |

## Review findings

Plan review and implementation findings will be recorded here after a clean
candidate exists. No application implementation begins before the lead reviews
this plan.

## Reconciliation

- Current-source reconciliation: Based on main commit
  `176952e6624244bdc405bac973ce6c4abddb0dae`. Shared README and roadmap wording
  will be reconciled with concurrent product work before PR readiness.
- Next usable boundary: Implement this one bounded diagnostics foundation after
  lead plan review; deployment-specific collectors, dashboards, alerts, and SLOs
  remain separate operational work.
- Remaining risks: FastAPI and Celery telemetry internals can change across
  dependency upgrades, so privacy and duplicate-instrumentation tests must bind
  the selected lock. An unavailable collector is deliberately tolerated, which
  means operators must monitor collector health outside product request flow.
