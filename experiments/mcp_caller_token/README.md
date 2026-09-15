# Local caller-token MCP experiment

This tests one concrete hypothesis, not a production MCP implementation:
an individual caller's bearer travels in each MCP HTTP request, and the adapter
forwards it to Workstream, which authenticates and returns that caller's profile.

The adapter and OpenAI Agents SDK client run separately. The real drill uses
unmodified Workstream and a freshly migrated, isolated PostgreSQL database.
It uses locally signed fixture identities, never real users or production tokens.
MCP receives no signing key, database credential or shared administrator token.

## Run

Use the repository's installed backend environment (`uv sync --frozen --extra dev`
from `backend/` if it is not already installed). Dependencies are already pinned
there; this experiment changes no package requirements. From repository root:

```bash
MCP_DRILL_PYTHON="$PWD/backend/.venv/bin/python"
"$MCP_DRILL_PYTHON" -m pytest experiments/mcp_caller_token/test_server.py -q
MCP_DRILL_OUTPUT=$(mktemp -d /tmp/workstream-mcp-evidence.XXXXXX)
cd backend
WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@127.0.0.1:5433/workstream \
  "$MCP_DRILL_PYTHON" scripts/run_isolated_tests.py \
  --metadata-json "$MCP_DRILL_OUTPUT/metadata.json" --timeout-seconds 180 -- \
  "$MCP_DRILL_PYTHON" ../experiments/mcp_caller_token/drill.py
```

Use your local PostgreSQL port (this machine's existing service uses `55437`).
The URL above is the Docker development credential, not a production secret.
The runner owns database/role creation and removal; its metadata must report
`cleanup_complete: true`. Never point this at a deployed service. The drill
terminates only its own API/MCP processes and removes its private temporary logs.

`drill.py` is a separate SDK client process from `server.py`, and additionally
executes `client.py` as a standalone subprocess. It compares direct HTTP and MCP
for two unprivileged fixture callers, concurrent requests, every returned profile
field (except changing admission timestamps), negative credentials, tool schema,
unknown tools and warm request latency. Focused tests additionally prove no
dispatch on injected arguments, no credential retention, no redirects, safe
denials, request/response limits and loopback/Origin protection.

## Optional model-driven client

For a separately running **local test** API/MCP pair, `client.py` accepts
`MCP_EXPERIMENT_URL` (loopback origin) and `MCP_EXPERIMENT_CALLER_TOKEN` through
its process environment. With no model setting it directly calls the tool using
the OpenAI Agents SDK—no OpenAI API key or model request is needed.

Setting `MCP_EXPERIMENT_MODEL` explicitly opts into `Runner.run` with the configured
OpenAI API credentials. Do not put either credential in prompts, tool arguments,
command-line arguments or Git. SDK tracing is disabled. This optional path sends
the fixture profile result to the configured model provider, not the Flow token.
Do not infer a successful model-driven run from the transport drill. The automated
drill intentionally does not load `.env` or make model calls.

## What this does not establish

- A working passthrough request does not prove compliance with standard remote
  MCP authorization. This is deliberately an isolated experiment of that pattern,
  not a silently adopted replacement for the existing MCP proposal.
- Local HMAC verification needs no Flow network endpoint. Production Workstream
  has separate JWKS/introspection configuration; its network behavior is not
  measured here.
- No OAuth discovery, exchange/delegation, live Flow integration, public hosting,
  ChatGPT hosted-MCP connection or production latency is claimed.
- One self-profile tool does not certify project permissions, lifecycle changes,
  all Workstream APIs or all MCP clients. No public rollout follows this test.

Keep the [MCP proposal](../../.commitrail/initiatives/WS-MCP-002/OVERVIEW.md)
and [experiment record](../../.commitrail/changes/mcp-caller-token-experiment.md)
distinct. This experiment changes no roadmap capability or product exposure.
