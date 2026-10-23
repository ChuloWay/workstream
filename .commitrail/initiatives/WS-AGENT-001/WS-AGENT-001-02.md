# WS-AGENT-001-02 — Real OmniCoreAgent adapter qualification

- Initiative: WS-AGENT-001
- Durable disposition: Planned
- Intended merge outcome: Select OmniCoreAgent or OpenAI Agents SDK through the same Workstream runtime contract, with OpenRouter and the same governed document tools.

## Intent and current behavior

The user requires a second actual runtime to prove core independence. This change
consumes the neutral tools/configuration from [01](WS-AGENT-001-01.md). It cannot
change PROJECTS/ART policy, custody schema or approval logic to fit OmniCoreAgent.
Published OmniCoreAgent 0.6.0 supports async tools/OpenRouter, but has different
request/retry mechanics and dependencies from the current OpenAI Agents SDK.

## Bounded change

Allowed: the new adapter and its registration in `backend/app/adapters/project_agents/`,
its typed effective profile at composition, isolated optional SDK dependency/lock
and release/test environment selection, focused actual-SDK contract tests, runtime
settings examples and current guide/runtime/deployment documentation.
Prohibited: core/schema changes for SDK mechanics, SDK monkeypatches/forks,
provider-specific document evidence, global credential switching, silent fallback,
stacked retries, automatic host/filesystem tools, or a speculative third adapter.

## Design

Pin published `omnicoreagent==0.6.0` (MIT; Python >=3.12,<3.15;
wheel SHA256 `76f191b79f5aa1bc1b7dea354643c692071454a603097fe3ca69a875e749d74a`).
Use its public `OmniCoreAgent`, `ToolRegistry`, async `run` and cleanup APIs. Keep
in-memory per-attempt sessions and explicitly disable skills, subagents, offload,
workspace tools, code mode and content telemetry. Offer only the shared document
read/search tools. Validate returned JSON using the same Workstream validator.

Keep SDK-native completion retries as the only retry owner and record the exact
observed effective profile. Enforce the common whole-run deadline and tool/output
bounds in the adapter/capability; prove cancellation terminates native tasks.
Do not claim unsupported per-request timeout or provider-store settings. Capture
outbound calls, telemetry behavior and exact tool inventory before real material.
Use the worker's one configured provider credential; do not accept per-request
keys or change other runtimes' global clients/defaults. Qualify any SDK-internal
environment assignment against the existing identical worker credential; it must
not introduce a different key or broaden exposure.

Install in a separate locked SDK environment from OpenAI Agents SDK: OmniCore's
LiteLLM currently requires `openai<3`, whereas the OpenAI environment pins 3.11.0.
Use the same core source and dependency lock with explicit environment selection,
not relaxed dependency verification or a parallel Workstream implementation.

## Acceptance criteria

- Same contract suite against both actual SDK loops: tools, source isolation,
  output validity, malformed output, quotas, cancellation, retry counts and privacy.
- Removing the neutral tool boundary or substituting a foreign source must fail
  the intended assertion, not an earlier fixture/schema guard.
- A synthetic live OpenRouter tool round trip and original-guide run complete in
  each selected SDK environment, with identical core contracts and no core edits.
- No hosted file/container calls, persistent SDK session, unexpected tool or
  telemetry endpoint. Retention claims match observed/provider-documented behavior.
- Switching runtime changes adapter/environment selection only; it cannot change
  authority, policy selection, proposal approval or retained attempt evidence.

## Risk, review and evidence

L1. Architecture/reuse, security, QA/test delta, dependency/CI integrity and docs
review the exact implementation. Human focus is actual native loops, honest SDK
bounds and no data leakage. SDK source/dependency inspection is complete; runtime
qualification is not yet run. Required proofs include captured HTTP, hanging
transport/tool cancellation, separate locked installation and live guide evidence.

## Reconciliation

Depends on 01's merged or reviewed exact contract. After qualification, return to
the existing hosted contribution journey. No historical setup attempt is rerun,
and no current issue is closed on adapter tests alone.
