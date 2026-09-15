# MCP caller-token experiment

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: A reproducible local-only experiment, not a deployed MCP adapter or a change to WS-MCP-002's credential contract.

## Intent and boundary

Test the human's concrete design: each caller supplies their own Flow-compatible
bearer in transport headers; a separate MCP process calls Workstream's public
self-profile API. Use the installed OpenAI Agents SDK as the separate client.
Distinguish observed API behavior from remote MCP authorization conformance.

Allowed: `experiments/mcp_caller_token/server.py`, `client.py`, `drill.py`,
`test_server.py`, `README.md` and this record. No backend runtime, dependency, CI, existing MCP
implementation contract, or product capability changes. No production tokens,
external deployment, tunnelling, shared privileged identity, invented exchange,
permission cache, database access from MCP, or token in tool arguments/model text.

## Plan

1. Reuse the existing local signed-token fixture and isolated PostgreSQL runner;
   start unmodified current Workstream on loopback with a dedicated database.
2. Start a loopback-only MCP server exposing one closed-empty profile tool. The
   API destination is fixed by local configuration, never by tool arguments.
3. From a separate OpenAI Agents SDK client, compare direct HTTP and MCP results
   for two users, concurrent isolation, missing/invalid/expired/wrong-audience
   credentials, and injected tool arguments. Preserve backend denial.
4. Measure repeated warm direct/MCP latency separately from connection setup.
   Report whether any Flow network call is needed by the fixture configuration.
5. Add an optional explicit model-driven client run; do not require a model call
   to test transport. Keep credentials out of prompts, results and tracing.

The passthrough experiment deliberately does not implement standard remote MCP
OAuth authorization. It cannot settle production credential design merely by
returning 200. No second OAuth design is fabricated for comparison.

Start unmodified `app.main:app`, not the guide-broker override in the existing
API drill. Reuse that drill's signed token, environment and port helpers only.
The low-level MCP SDK's per-invocation `server.request_context.request.headers`
owns the incoming Authorization header; never retain it in global/session state.
Denials are `CallToolResult(isError=True)` with a JSON text body containing only
`error: profile_request_failed` and the upstream HTTP `status`; no raw upstream
error or token-bearing exception is returned. The local HMAC fixture has no Flow
network request; production introspection policy is outside this proof.

Future verification commands (using the installed backend interpreter as PY):
`$PY -m pytest experiments/mcp_caller_token/test_server.py -q` from root;
`$PY scripts/run_isolated_tests.py --metadata-json /tmp/UNIQUE/metadata.json
--timeout-seconds 180 -- $PY ../experiments/mcp_caller_token/drill.py` from
backend, with the local admin DB URL supplied only to the isolation runner.
The README supplies a concrete mktemp-based invocation without fixed evidence
paths. SDK client discovery, negative cases and timing all run in that drill.

## Acceptance and verification

- Real HTTP processes and real isolated PostgreSQL, not a mocked Workstream API.
- The observed actor matches each caller, including concurrent calls.
- Invalid credentials never produce profile data; unknown arguments never select
  another actor or destination. No fallback credential or redirects.
- Tool errors preserve denial status without reflecting bearer tokens.
- Client works with the installed OpenAI Agents SDK; token is transport-only.
- Local request and response bounds, timeouts, loopback and no-store protections.
- Rerunnable commands and honest measurements documented with explicit limits.

## Risk and review

- Risk class: L1 (authentication experiment, strictly isolated).
- Required reviewers: security, architecture, QA/test delta (combined focused
  assignments allowed); plan review before execution.
- Human review focus: what the experiment proves versus standards compliance;
  no public deployment decision follows automatically.

## Reconciliation

Based on main after PR #412. The existing MCP proposal stays unchanged. The
roadmap has no product exposure change: an experiment is not a delivered MCP
capability. No spreadsheet export changes are needed.

## Evidence and limits

The local real-process drill passed all 13 named checks using OpenAI Agents SDK
0.22.2, OpenAI 3.11.0, MCP SDK 1.29.0 and HTTPX 0.28.1. Both actors were admitted
without grants and remained distinct across concurrent requests. All returned
profile fields matched direct HTTP except the expected advancing admission
timestamps. Seven invalid credential cases denied access. The standalone SDK
client subprocess also returned the correct actor.

An initial fixture expectation incorrectly assumed token email/name claims were
copied into editable actor profile fields. Source inspection showed admission
correctly initializes them to null; the test was corrected, not product code.

One warm sample of 12 calls per path measured direct median 397.07 ms and MCP
median 470.98 ms on this loaded developer machine. This is local observation,
not a production budget or an isolated estimate of adapter CPU overhead.
The live model-driven path remains optional and unexecuted. No remote OAuth or
production Flow certification is claimed. The existing MCP contract is unchanged.
