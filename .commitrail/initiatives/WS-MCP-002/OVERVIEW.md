# WS-MCP-002: Independently Deployed MCP Adapter

- Disposition: Planned
- Current change: [Planning proposal](WS-MCP-002-PLAN.md)

## Purpose

Expose agreed Workstream operations to MCP clients through a small, separately
deployed Python service. The adapter calls the running Workstream HTTP API.
Workstream owns identity resolution, product permissions, business rules,
persistence, audit and operation replay.

This is a fresh initiative. The closed contributor MCP PR #149 remains
historical design evidence; its implementation and old contribution process
are not the baseline for this work.

## Current sources and boundaries

The proposal was reconciled with main `d9a66470`. Read
[CONTRIBUTING.md](../../../CONTRIBUTING.md), the
[capability ledger](../../../docs/roadmap_status.md),
[architecture lockdown](../../../docs/architecture_lockdown.md) and
[authorization specification](../../../docs/spec_authorization_service.md)
before each implementation change.

The maintainer requested a separately deployable adapter and a planning PR
before implementation. These supplied designs inform this proposal:

| Design | Relevant contract |
| --- | --- |
| Workstream MCP interactive design, baseline `c69ff85` | 27 tools, 12 reads, 15 mutations, 14 required operation keys; no resources or prompts; setup and access only |
| Flow-Identity-v0.1-Interactive.html, 10 September 2026 | Human-only identity baseline; one issuer and JWKS; resource-specific access tokens; product-owned permissions |
| Flow-Identity-Human-and-Agent-Experience.html, 11 September 2026 | Future agent identity and delegation direction; explicitly not implemented v0.1 behavior |

These HTML files are external design inputs, not proof of deployed services.
Their relevant requirements are recorded here so review does not depend on
local Downloads paths. The maintainer should confirm the interpretation below.

The 27 handler names from the MCP design existed at inspected `2c95d4e2`.
That is not full schema or route proof. The later main delta adds hidden
proposal authorization; PR #400 proposes public guide-review operations and
PR #395 changes guide setup behavior. Neither open PR is assumed merged.
Before implementation, inspect current open PRs and verify every selected
method, path, schema, header, response and permission against current owners.

## Proposed first release

Start with the 27 setup/access tools in the supplied MCP design:

- Own profile read/update and own authorization context.
- Permission and administrative role definitions.
- Administrative grant listing, issue, revocation and actor grant history.
- Actor and identity-link reads and lifecycle controls.
- Project create/read, draft guide create/update, review/revision policy writes.
- Contributor candidates and project grant issue/list/read/revoke.

All admitted clients see the agreed catalogue; the API decides whether each
invocation is allowed. A visible administrative tool grants no authority.
The first implementation record will freeze the exact names and schemas after
the API inventory is checked. Missing or changed contracts become explicit
dependencies, not simulated production behavior.

Tasks, submissions, reviews and ContributionRecord reads belong to later
agreed changes when their public contracts are ready. An adapter cannot create
a ContributionRecord directly. The backend lifecycle owns those facts.

## Design

```text
Registered MCP client
  -> adapter: validate credential and typed tool input
  -> fixed Workstream HTTP API operation
  -> API: resolve caller, authorize, enforce lifecycle and persist
  -> adapter: validate response and return bounded structured result
```

Propose one separate Python package and container in this repository, with its
own dependencies, entry point and tests. It must install and start without
installing the backend, and restart without redeploying Workstream. Package
placement is for review; independent deployment does not require a new repo.

Use the official Python MCP SDK v2, verifying and locking the exact release
when implementation begins. Target protocol `2026-07-28` and test agreed client
versions. Let the SDK own protocol parsing and transport behavior.

Keep a small server, typed tool catalogue, HTTP client, authentication boundary,
configuration and error mapping. Use fixed routes and one configured API
destination. No private backend imports, database access, local role engine,
arbitrary-URL tool, login service, worker or production substitute API.
ADR 0014 governs any changes to backend-owned integrations; this external
HTTP client must not import backend factories to reuse private internals.

## Identity contract

Flow v0.1 uses Better Auth for sign-in and OAuth state and Rust for canonical
subjects and final signing. Products consume one public issuer and JWKS.
The proposed issuer domain is not proof of a deployed test environment.

Preregistered clients use authorization code with PKCE or the documented device
flow. Session reuse can avoid another sign-in, but each resource needs its
appropriate access token. An ID token is for the client, not product API access.
The adapter does not receive or store human refresh tokens. Client renewal
follows Flow's strict rotation contract; lost refresh success requires
reauthorization, not blind replay.

Validate signature, issuer, audience, `at+jwt`, `client_id`, admission scope,
`subject_kind=human` and bounded timestamps according to the agreed profile.
Flow's design sets access lifetime at most 300 seconds and tolerance at most
30 seconds. Resolve identity by `(iss, sub)`, never matching email. Known
consumer-validation gaps must be checked with the backend owner, not silently
reimplemented as product authority in MCP.

**Unresolved integration decision:** the separately deployed MCP resource and
Workstream API need an agreed resource registration and downstream credential
contract. The identity designs do not establish this hop. Do not assume a
shared audience, add token exchange, or accept an API-only token at MCP.
Agree a contract consistent with the MCP audience requirements before coding
authentication. Preserve the actual caller; never replace them with an
administrator or privileged service account.

Tokens stay outside tool schemas, results, URLs, logs and trace attributes.
Keep credentials per request and block credential-bearing redirects. Product
grants remain live API decisions. Issuer suspension is separate: offline JWT
validation may retain the documented expiry/tolerance window, at most 330
seconds. Do not promise immediate global revocation from signatures alone.

### Future agents

The agent design proposes registration and human approval once at Flow.
Agents authenticate with their own credentials preserving agent and human
identity. In Workstream, distinct identity links point to the human's existing
ActorProfile. Linking grants no permission.

Every action needs the human's current authority, the particular agent's
explicit delegation, project permission for agent callers and normal lifecycle
guards. Workstream owns these checks and caller/delegation audit evidence.
MCP preserves the verified caller and consumes future public APIs.

Claim names, registration/enrollment, delegation APIs, absent-human onboarding
and revocation propagation are still unspecified. First release is human-only;
agent support needs a separate agreed boundary. An AI-assisted client using
human credentials does not implement this distinct agent identity model.

## Errors, replay and operation

Preserve required operation keys and policy `If-Match` selectors unchanged.
Clients retain their mutation key before dispatch. A timeout after dispatch
may mean the write completed: return uncertain execution and do not repeat it
automatically with a new key. A stale policy selector remains a conflict.
The initial catalogue lacks a dedicated policy-selector recovery read; settle
the supported recovery path without using a write as a read.

Return safe API status, errors and correlation metadata. Distinguish admission
failure, invalid tool input, API denial/conflict, dependency failure and unknown
execution. Do not expose raw exceptions or claim a successful MCP exchange
proves a successful product operation.

Bound request/response sizes, timeouts and connections. Use TLS in deployment.
Liveness reports process health; dependency/readiness checks must not create
actors or mutate business records. Log safe tool names, duration, outcomes and
correlation identifiers. Optional Logfire feedback-loop work is separate.

## Proposed PR boundaries and proof

1. **Foundation and one profile read:** independent package/container, SDK,
   agreed credential boundary and HTTP mapping. Prove one real request path,
   invalid-token denial, user isolation and independent startup.
2. **Profile and access tools:** complete selected profile, administrative and
   actor operations. Prove current API authorization, lifecycle denial and
   safe responses for each operation.
3. **Project setup and participation:** complete the selected project, guide,
   policy and project-grant tools. Prove cross-project denial, revocation,
   same-key replay, conflicting payloads and stale policy selectors.
4. **Release proof:** verify the agreed full catalogue through real HTTP and
   Flow test credentials, supported clients, key rotation, dependency outages
   and deployment instructions. Tests and security checks begin in PR 1;
   this boundary closes integration evidence, not deferred basic safety.

Every implementation PR gets one concrete change record defining files,
acceptance criteria, reviewers and executable checks. Do not create all future
records now. Preserve repository lint, type, coverage and CI requirements.
Use mocks for controlled failures and live API tests for authority claims.
Fixture-signed tokens do not prove deployed Flow integration. Future agent
tests must cover delegation, human grant removal, project restrictions,
attribution and revoked links that cannot be recreated by reconnecting.

## Decisions requested

1. Confirm the 27-tool setup/access first release and human-only baseline.
2. Confirm separate package/container placement in this repository.
3. Agree MCP/API resource registration, downstream credentials, preregistered
   clients and the test environment with the identity/backend owners.

Main risks are contract drift, unresolved credential transport, accidentally
exposing hidden APIs, retrying completed writes and treating future agents as
live behavior. Before starting the foundation, resolve decision 3 and freeze
its tested API inventory. Scope and approval remain human decisions.

## Protocol references

- [Official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
