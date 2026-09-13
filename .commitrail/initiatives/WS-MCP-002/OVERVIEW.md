# WS-MCP-002: Workstream MCP Adapter Approach

- Disposition: Planned
- Prepared by: OxVictor
- Purpose: Review and agreement before implementation
- Repository baseline reconciled: `016061f1`
- Current change: [Planning proposal](WS-MCP-002-PLAN.md)

## 1. What I Understand We Are Building

I want to make Workstream available to MCP clients through a small service that calls the existing Workstream APIs. A user working from an MCP client should be able to perform supported Workstream actions under their own identity and permissions.

The adapter will be deployed separately. Updating or restarting it should not require redeploying Workstream. Workstream must still be running and reachable for its tools to complete API operations.

The wider experience includes creating projects, assigning contributors, working on tasks, submitting work, and reading contribution records. I propose delivering that experience in small stages, following the availability of the public backend contracts.

## 2. What I Have Checked

I have reviewed the current contribution guide, Commitrail guidance, architecture rules, roadmap, and the available Workstream MCP interactive design.

The MCP design is based on commit `c69ff85`. It describes 27 tools: 12 reads and 15 mutations, with operation keys required for 14 mutations. It exposes no resources or prompts and ends at project setup and access.

The corresponding handler names were present at the inspected `2c95d4e2` baseline. This is an initial check only. The maintainer will provide the public API list. After that handoff, I will map and verify its selected operations against the pinned code and tests before we jointly freeze tool definitions. A handler existing does not prove that its contract is unchanged.

The roadmap still distinguishes public capabilities from hidden implementations and planned work. A hidden backend service will not be treated as a public API available to the adapter.

I have also reviewed both complete Flow Identity designs. The architecture walkthrough, dated 10 September 2026, defines a human-only v0.1. The human and agent experience, dated 11 September 2026, defines an agreed future extension. Both are design records; neither claims that the integrations are deployed. I will keep that distinction clear in implementation and tests.

The planning PR is reconciled with main `016061f1`, including merged PR #400. Public guide proposal review, pre-submission approval, correction and manual dispatch are now exposed; their authorization, route and schema changes must be included in the pre-implementation inventory. This does not automatically add tools to the agreed 27-tool catalogue. PR #395 was separate setup work at the earlier review; check its current state and other open work before implementation. Open work is not proof that an API is live.

This is a fresh initiative. Closed contributor MCP PR #149 remains historical design evidence. Its runtime and old contribution process are not the implementation baseline. Main risks are API contract drift, the unresolved credential boundary, exposing hidden capabilities, unsafe mutation retries, and treating future agent support as available.

## 3. First Release Scope

The maintainer's [review addendum](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5653317895) confirms the 27-tool, human-only first release. Each binding still needs verification against the public API before implementation.

| Area | Proposed tools |
| --- | --- |
| Own profile and access | Read profile, update profile, read own authorization context |
| Authorization definitions | List permissions and administrative role definitions |
| Administrative grants | List, issue, revoke, and inspect an actor's administrative grants |
| Actor and identity access | Read actors and identity links; suspend, reactivate, or deactivate actors; revoke or reactivate identity links |
| Project setup | Create and read projects; create and update draft guides; set review and revision policies |
| Project participation | Find contributor candidates; issue, list, read, and revoke project grants |

Some of these are privileged tools. Their presence in the catalogue does not give the caller permission to use them. Workstream must authorize every invocation.

Task, submission, review, and ContributionRecord tools will be added through later agreed changes when their public contracts are ready. The adapter will never create a contribution record directly; it can only expose operations the backend authoritatively supports.

The first release will use the human identity baseline. Agent registration, agent credentials, and Workstream delegation require the future contracts described below before agent tools can be enabled. The first release will not include a login system, database access, background lifecycle workers, prompts, or replacement services for unavailable product APIs. Test doubles may simulate API responses in tests, but will not be a production fallback.

## 4. How the Adapter Will Work

```text
User through an MCP client
          |
          v
Standalone MCP adapter
  - checks the incoming credential
  - validates the selected tool's input
  - calls its fixed Workstream API operation
  - checks and returns the API result
          |
          v
Workstream API
  - resolves the caller's identity
  - checks current permissions and resource access
  - applies business rules
  - owns database changes, audit, and replay handling
```

Following the review addendum, the adapter stays in the Workstream repository as a separate Python package, with its own entry point, dependency lock, tests, container build, configuration and release instructions. This keeps review close to the API contracts while allowing separate deployment. Its only Workstream runtime dependency is a configured, reachable public API base URL. It must not access backend queues or invoke private or hidden handlers.

The runtime will communicate over HTTP and will not import Workstream's database models, private services, or application startup code. Its package must install and start without installing the backend. ADR 0014 continues to govern backend-owned integrations; the standalone adapter will not import private backend factories to reuse their internals.

The package will have a few clear responsibilities:

| Part | Responsibility |
| --- | --- |
| Server | Register tools and serve MCP requests using the official SDK |
| Authentication boundary | Validate incoming credentials and obtain the approved API credential |
| Tool contracts | Define accepted inputs, expected outputs, and fixed API mappings |
| HTTP client | Manage connections, timeouts, declared headers, and bounded responses |
| Error mapping | Return safe, accurate failures without leaking internal data |
| Configuration | Validate the API address, identity settings, and deployment limits |

I will use the official Python MCP SDK v2 and verify and lock the exact supported release when implementation starts. The SDK will handle protocol behavior. The intended protocol baseline is `2026-07-28`; supported clients will be recorded and tested explicitly.

## 5. Identity and Permissions

Flow Identity will remain responsible for issuing credentials. Workstream will remain responsible for deciding what the caller may do to a particular project or resource.

### Human access in v0.1

The shared design uses one public Flow issuer and one public key set, called JWKS. Better Auth handles sign-in, consent, and OAuth protocol state. The Rust identity core owns stable subject IDs and final token signing. The MCP adapter consumes that public contract; it will not call the private signer or build another authentication service.

A registered client signs the human in through Flow. Browser access uses an authorization code with PKCE, and the design also supports a device flow for CLI access. An existing Flow session can avoid another sign-in, but the client still requests an access token for the intended resource. An ID token identifies the user to the client; it is not the credential sent to a product API.

The proposed issuer is `https://identity.flowresearch.tech`, with one authoritative `/.well-known/jwks.json`. The design explicitly says deployment remains to be established, so these will be verified configuration values before live testing. Clients are preregistered in v0.1. Dynamic client onboarding, UserInfo, and profile/email scopes are deferred.

Token checks must follow the agreed Flow profile: signature, trusted issuer, intended audience, access-token type `at+jwt`, `client_id`, admission scopes, `subject_kind=human`, and bounded timestamps. The design limits access tokens to 300 seconds and verifier clock tolerance to 30 seconds. Identity resolution uses stable `(iss, sub)`, not email. The architecture also identifies token-type, client-ID, and maximum-lifetime validation as known Workstream consumer work; I will verify their current status and coordinate any backend gap with its owner.

For example, a signed-in user may read their own profile but still be denied when creating a project. Likewise, a grant for one project must not allow changes to another project. A scope or a cached list of permissions will not replace Workstream's live authorization checks.

The adapter will validate credentials before dispatching a protected tool. It will not accept a caller-supplied actor ID as a replacement for the authenticated caller. Target actor IDs remain valid inputs where the API explicitly requires them, such as granting another person project access.

One detail needs agreement before implementing authentication: which credential the adapter presents to the Workstream API. The MCP authorization specification requires an access token intended for the MCP resource. We should not assume that an API token can be accepted by the adapter, or that the same token is automatically valid at both services.

The Flow design describes resource-specific tokens but does not settle the separately deployed MCP-to-API credential boundary. It explicitly avoids adding a public token-exchange step in its current identity bridge. I will therefore confirm the resource registration and downstream credential contract with the Flow Identity and Workstream owners before implementing that part. I will not introduce token exchange, invent a shared audience, or treat forwarding the same token as already approved by these documents. The API request must preserve the correct caller without substituting a privileged service identity.

Tokens will remain outside tool arguments, results, URLs, logs, and trace attributes. Credentials will be kept per request so concurrent users cannot share authentication state. Sign-in and refresh belong to the registered client and Flow Identity. The adapter will not store the human's refresh token. The design uses strict refresh rotation without a retry grace period; a lost successful refresh response requires reauthorization rather than blindly retrying the consumed credential.

Issuer suspension and Workstream permission revocation are separate. The design allows an already-issued access token to remain valid until its expiry and allowed clock tolerance, bounded at 330 seconds. The adapter must not promise immediate global logout or suspension enforcement from offline signature checks alone. Workstream still checks its own current grants and identity state on guarded actions.

### Future agent access

The second document gives a clear future direction: a human registers and approves an agent once through Flow Identity. Flow verifies control of that agent. The agent then authenticates with its own credential, which identifies both the actual agent and the human it represents. It does not use the human's bearer token.

In the proposed Workstream model, the human and each agent have distinct `ActorIdentityLink` records pointing to the same human `ActorProfile`. Connecting the agent creates no permission by itself. The human must explicitly delegate permitted actions and project access inside Workstream.

For example, an agent may submit work only when the human currently has the required grant, that particular agent has submission delegation, the project permits an agent caller, and the normal lifecycle checks pass. Removing the human's grant or the agent's delegation must stop subsequent guarded actions. Workstream owns those checks and the audit record distinguishing the human principal from the actual agent caller.

The MCP adapter will preserve these identities when the contracts become available. It will not register relationships, create identity links itself, or calculate delegation permissions locally. The design leaves claim names, registration APIs, delegation APIs, onboarding without an existing human profile, and revocation propagation unresolved. Agent support therefore needs a later bounded change and real backend evidence. Using an AI-assisted MCP client with a human credential does not establish this separate agent identity model.

## 6. API Contracts and Failures

The public API list is a maintainer-owned handoff dependency. I will wait for that supplied list rather than reconstruct it independently. From it, I will produce a versioned deterministic inventory of all 27 tool names, HTTP methods and routes, input/output schemas, required headers and response statuses, with permission boundaries and relevant backend tests. We will review and freeze that mapping together before implementation. Any difference from the existing 27-tool design returns for agreement. The frozen inventory will be the source for binding tests and contract-drift checks.

Tool calls will use a configured API destination and fixed routes. Users will not be able to supply arbitrary destinations or authentication headers. Redirects will not carry credentials to another destination.

For the 14 mutations that require an operation key, the client must supply and preserve that key. The adapter will forward it unchanged. The self-profile PATCH is the one unkeyed mutation. Automatic mutation retry is forbidden, including retry with the same key. If a response is lost after dispatch, the adapter cannot know whether the write completed. It will report uncertain execution without claiming failure or rollback. A later client-initiated attempt preserves the original key and follows the API's replay rules.

Policy updates will preserve required version selectors such as `If-Match`. A stale selector must produce the API's conflict outcome. If the initial catalogue lacks an operation needed to recover the current selector, I will document that limitation for review instead of using a write to imitate a read.

Errors will distinguish invalid credentials, invalid input, API denial, conflicts, unavailable dependencies, and uncertain execution. The result will preserve useful API status and correlation information while excluding secrets and raw internal exceptions. A successful MCP transport response does not mean the Workstream operation succeeded.

### Exact request path

Every protected invocation follows this path:

1. Receive one request on the declared POST Streamable HTTP endpoint.
2. Validate protocol version, required transport metadata, Origin policy and bearer credential. `Mcp-Method` is required for every MCP request. In this tools-only release, `Mcp-Name` is required for `tools/call` and must match `params.name`; discovery and tool listing do not require it.
3. Establish caller context for this request only. Shared connection pools must not retain a caller's credentials or actor context.
4. Resolve the tool from a fixed typed registry. Unknown tools cause no API dispatch.
5. Validate arguments against the tool's closed input schema.
6. Select the registry's fixed public API method and route under the configured base URL.
7. Encode path and query selectors in their declared locations and serialize only the declared model under the typed `body` argument.
8. Add only adapter-controlled headers: approved downstream credentials, content type, required operation key and `If-Match`, and safe correlation identifiers. Arbitrary authorization, forwarding, host or destination headers are not tool inputs.
9. Send one bounded HTTP attempt.
10. Validate response status, content type, byte size, JSON shape and the declared success or error contract.
11. Return the structured MCP result, preserving the API's meaning and excluding credentials and internal exceptions.

Each tool has exactly one fixed method/path binding. Destination, route, method and authentication headers are never model-visible arguments. Authenticated redirects are disabled. Optional null query parameters are omitted, never serialized as the strings `None` or `null`. Partial updates preserve the difference between an omitted field and an explicit null, using JSON-safe, exclude-unset serialization rather than dropping every null.

UUIDs, timestamps, enums, cursor bounds, byte limits and cross-field rules must match the public API. Cursors remain opaque: no decoding, modification, fabrication or inferred totals. The adapter returns only data available to that caller through the API. It does not cache grants, authorization context, actor state, project policy or lifecycle eligibility.

## 7. Deployment and Operation

Authenticated MCP responses, including errors, must carry `Cache-Control: no-store`. The reverse proxy/CDN must preserve and respect this policy. Test headers and caller isolation through the deployed HTTP path, including error responses. v0.1 uses no identity-partitioned response cache; the prohibition on local authority and lifecycle caches remains in force.

The adapter will have its own container, configuration, and release instructions. Production HTTP connections will use TLS. Request sizes, response sizes, connection counts, timeouts and maximum in-flight calls will be configurable and tested. Backpressure must reject or limit excess work before an unbounded queue forms.

A liveness check will report whether the adapter process is running. Readiness and dependency reporting will make API unavailability visible without creating an actor or performing a business mutation as a health check.

Logs will record tool names, durations, safe outcomes, and correlation IDs. They will exclude credentials and sensitive request bodies. The separate Logfire feedback-loop work can be considered in its own PR; it is not a dependency for implementing this adapter.

## 8. How I Will Prove It Works

I will test the complete route from an MCP client, through the adapter, to a separately running Workstream API. Mocked HTTP tests will cover failures, but will not be presented as proof of live authorization.

| Test area | Evidence expected |
| --- | --- |
| Tool catalogue | Exactly the agreed tools and schemas; no unintended tools, resources, or prompts |
| HTTP mapping | Correct routes, bodies, query parameters, and required headers |
| Authentication | Invalid, expired, or wrong-audience credentials stop before tool dispatch |
| Flow token profile | ID tokens, wrong subject kinds, missing required claims, and excessive token lifetimes are rejected under the agreed profile |
| User isolation | Concurrent callers retain their own credentials and results |
| Product authorization | Allowed caller succeeds; missing, revoked, and cross-project authority is denied by the real API |
| Replay and conflict | Same-key retries follow backend behavior; changed payloads and stale policy selectors preserve conflicts |
| Dependency failures | Timeouts and malformed or oversized responses produce bounded, accurate failures |
| Privacy | Credentials never appear in results or telemetry; authorized API result fields remain distinct from prohibited diagnostic leakage, as confirmed in the response-data policy below |
| Key rotation | Trusted new and still-valid retiring keys work within the agreed cache policy; unknown keys or unavailable verification never trigger a fallback signer |
| Independent deployment | Adapter builds and starts separately and reports Workstream unavailability correctly |

The actual Flow Identity integration also needs an agreed test environment, preregistered clients, and credentials for representative callers. Tests using locally signed fixtures will be identified as fixture-based tests, not evidence that the deployed identity service works. Agent support will later need separate tests for missing delegation, human-grant removal, project restrictions, caller attribution, and revoked links that cannot be recreated by reconnecting.

### Required conformance suites

The following are acceptance requirements from the review addendum, not claims that tests have already run. Each implementation record will identify the concrete tests and commands for its portion of this matrix.

| Suite | Required proof |
| --- | --- |
| 1. Catalogue | Exactly 27 unique tools, 12 reads, 15 mutations, 14 keyed mutations and one fixed binding per tool. No resources, prompts, login tool, generic HTTP tool, hidden route or extra capability. Input and structured-output schemas are complete and self-contained; references resolve locally; closed schemas reject unknown fields. Read-only, destructive, idempotent and open-world annotations match actual behavior. |
| 2. MCP protocol | Explicit `2026-07-28` support on one POST Streamable HTTP endpoint. Test missing, unsupported and mismatched `MCP-Protocol-Version`; `Mcp-Method` required for every request and matching its method; `Mcp-Name` required for `tools/call` and matching `params.name`; positive `server/discover` and `tools/list` cases without `Mcp-Name`, and negative tool-call cases with missing or mismatched names; invalid present Origin; Accept and content-type rules. Test unknown methods/tools, malformed JSON-RPC, notifications, cancellation and bounded SSE according to the selected revision. No unapproved legacy GET event stream, session ID, DELETE session endpoint or resumable stream. `tools/list` is deterministic across clients and restarts. |
| 3. OAuth and Flow | Publish protected-resource metadata for the canonical MCP resource. Missing or invalid bearer gets the correct 401 challenge. Validate the full Flow profile. Distinguish safe failures for wrong issuer/audience, ID token, expired or premature token, malformed token, unknown key and verifier/JWKS unavailability. Prove current/retiring-key cache behavior, stable issuer/subject resolution and concurrent caller isolation across credentials, results, actor context and telemetry. Protected dispatch is incomplete until the downstream credential contract is approved and tested. |
| 4. All tool bindings | At least one positive wire-level case per tool proving exact method, encoded path, query omission/defaults, typed body, headers, successful status and structured response, with no extra API call. Cover both permitted project-response projections and every maximum-valid bounded input. Mock assertions support this proof but do not replace the release drill. |
| 5. Real authorization and lifecycle | Use the real API and PostgreSQL path. Prove first human profile/link provisioning grants no authority; self-edit remains self-only; missing authority, wrong administrative role, wrong scope and cross-project access are denied. Revoked grants and inactive actors/links stop subsequent actions. Preserve administrative self-grant/self-revoke guards and final effective Access Administrator protection. Contributor/admin projections must not leak into one another. Workstream guards and audit remain authoritative. |
| 6. Replay and concurrency | Same key and identical payload follows canonical replay; changed input conflicts. Concurrent duplicates match direct-API outcomes. Both policy writes preserve stale `If-Match` conflicts. Lost responses after possible commit report uncertainty without claiming rollback. No automatic mutation retry. Client restart preserves caller-retained keys, cursors, grant/resource IDs and policy selectors. |
| 7. Network failures | Bound connection refusal, DNS/TLS failures, connect/read/total/cancellation timeouts, applicable API 429/401/403/404/409/412/422/5xx responses, malformed JSON, wrong content type, schema-invalid success and oversized responses. Test API failure during a call and adapter shutdown with in-flight work. Never claim rollback of a possibly committed write. |
| 8. Privacy and observability | No credentials or authorization headers in results, logs, traces, exceptions, metric labels or URLs. Do not echo raw arguments or sensitive bodies into diagnostics. Profile data, guide content, reasons and cursor payloads must not enter telemetry. Allow only bounded tool name, fixed method/route template, duration, response size, safe status/error code and approved correlation IDs. Return the declared API fields the caller is authorized to receive, even when a field value also appeared in the request. Prove authorized profile/guide/cursor results are preserved while credentials and sensitive diagnostic content are excluded. Workstream remains audit authority. |
| 9. Independent deployment | Build, install and start without the backend package. Run in a separate process/container using only the configured public API. Invalid API URL or identity configuration fails startup safely. API unavailability affects readiness/calls without crashing catalogue discovery. No Garden-specific or client-name conditional behavior. Two MCP clients see the same catalogue and are independently authorized. Authenticated success and error responses carry `Cache-Control: no-store`; verify proxy/CDN preservation and no cross-caller reuse through the deployed HTTP path. |
| 10. Contract drift | After the maintainer supplies the public API list, map and jointly freeze the exact 27-tool inventory against a pinned current-main source commit, including routes, schemas, headers, statuses, authorization and API drill evidence. CI must fail on route, method, input/output, header, status, annotation or capability drift. Regeneration must not silently accept a changed contract. Changes require deliberate review and renewed proof. |

For annotations, a logical read is not automatically side-effect-free: first profile access may provision identity records. The annotation tests must reflect the actual API operation rather than its HTTP method alone. The implementation contract will trace the requested protocol assertions to the selected SDK and protocol sources; any mismatch must be raised for review before freezing behavior.

### Required release drill

```text
Real MCP client -> HTTP /mcp -> independently running adapter
  -> public Workstream HTTP API -> PostgreSQL
```

Use signed test tokens through normal verification, local bootstrap for the first Access Administrator and public grant APIs for subsequent authority. Do not disable guards or seed database authority to make a case pass. The harness may inspect database and audit state for proof; the adapter itself has no database access.

Exercise all 27 tools through HTTP MCP. For equivalent actors and intent, compare MCP execution with direct API execution for API outcome, response contract, database state, replay results, denial and audit provenance. Use equivalent isolated fixtures for the two paths so the first mutation does not change the second path's starting state.

Release requires 27/27 positive cases, corresponding negative and replay cases, zero unresolved schema drift, zero credential leakage, correct direct-API parity, independent package installation and a reviewed dependency lock. SDK tests, mock request counts, API-only drills and successful tool listing are supporting evidence, not substitutes for this gate. Fixture-token proof remains separate from proof of the deployed Flow service.

### Confirmed response-data policy

The maintainer's [clarification](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5654493551) confirms that tool results return the declared Workstream API fields the caller is authorized to receive, including profile data, guide content and pagination cursors. A declared response field is allowed even when its value also appeared in the request. Do not add an indiscriminate input-echo filter that removes valid response data. Credentials must never appear in results. Sensitive business content stays out of logs, traces and diagnostic errors; raw arguments are not copied into diagnostic output. These rules preserve authorized response data without adding fields unavailable through the API.

## 9. Proposed PR Order

Before runtime work, receive the maintainer's API list, produce and jointly freeze the exact tool mapping, and agree the MCP-to-API credential contract. The inventory handoff is a dependency, not a task to reconstruct the list independently. Then proceed through the following proposed implementation PRs:

1. **Runtime and identity foundation:** independent package and container, SDK setup, authentication boundary, HTTP client, and one profile-read tool proving the full request path. The final 27-tool catalogue is not claimed complete here.
2. **Profile and access tools:** complete the remaining profile, authorization, actor, and administrative-grant operations with focused authorization tests.
3. **Project setup and participation:** complete the agreed project, guide, policy, candidate, and project-grant tools, including replay and conflict tests.
4. **Release verification:** prove the complete agreed catalogue against the running API and identity environment, finish client/deployment instructions, and close remaining integration findings.

Each PR will include its relevant tests and documentation. PR 1 establishes protocol, credential, privacy and independent-package tests; PRs 2 and 3 add binding, authority, replay and drift tests for every tool they introduce. PR 4 closes the complete ten-suite matrix and the 27-tool direct-API parity drill. Security and deployment checks begin with the first PR and become broader as tools are added. Later lifecycle tools require their own agreed scope.

I will follow the current Commitrail process: one initiative overview for this multi-PR effort and one change record for each implementation PR. Each record will state the allowed files, non-goals, acceptance criteria, risks, and required review. Open PRs will be checked for overlapping changes before each boundary starts.

Review will follow the repository's risk routing, including security and architecture for the foundation. Relevant lint, type checks, tests, coverage requirements, and repository gates will be preserved. Roadmap impact will be assessed in the same PR. GitHub will hold current checks and approvals; the repository records will hold durable decisions. Merge remains a human decision.

## 10. Points for Your Review

The addendum confirms the human-only, 27-tool release and independently packaged deployment within this repository. The remaining questions are:

1. How should the separately deployed MCP adapter and Workstream API be registered as resources, and which credential should the adapter use for the API call? Which test environment and preregistered MCP clients should prove that contract?

The public API list will come from the maintainer. Mapping and joint catalogue review follow that handoff. Privacy, conditional MCP headers and `no-store` response caching are settled by the linked clarification.

The proposal follows the documents' human-only v0.1 baseline and keeps the future agent extension explicit. Once the API handoff, joint catalogue review and credential agreement are complete, I can turn the first PR boundary into its concrete Commitrail change record and begin implementation.

## References

- [Maintainer clarification: privacy, API handoff, headers and caching](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5654493551)
- [MCP standard request headers](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http#standard-request-headers)
- [Maintainer review addendum: dispatch and conformance requirements](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5653317895)
- [Workstream contribution guide](../../../CONTRIBUTING.md)
- [Commitrail guidance](../../README.md)
- [Workstream capability status](../../../docs/roadmap_status.md)
- Workstream MCP interactive design shared in the group, baseline `c69ff85`.
- `Flow-Identity-v0.1-Interactive.html`, approved architecture dated 10 September 2026. Used for issuer ownership, token validation, client registration, renewal, suspension, and key rotation.
- `Flow-Identity-Human-and-Agent-Experience.html`, future extension design dated 11 September 2026. Used for separate agent credentials, shared human accountability, identity links, local delegation, and the boundary between agreed direction and pending implementation.
- [Official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP authorization specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
