# WS-MCP-002: Workstream MCP Adapter Approach

- Disposition: Planned
- Prepared by: OxVictor
- Purpose: Review and agreement before implementation
- Repository baseline reconciled: `a3e4c696`
- Pinned API handoff baseline: `6feef39834737eed106773fdaed6003561fd021a`
- Current change: [Combined planning and first-chunk contract](WS-MCP-002-01.md)

## 1. What I Understand We Are Building

I want to make Workstream available to MCP clients through a small service that calls the existing Workstream APIs. A user working from an MCP client should be able to perform supported Workstream actions under their own identity and permissions.

The adapter will be deployed separately. Updating or restarting it should not require redeploying Workstream. Workstream must still be running and reachable for its tools to complete API operations.

The wider experience includes creating projects, assigning contributors, working on tasks, submitting work, and reading contribution records. I propose delivering that experience in small stages, following the availability of the public backend contracts.

## 2. What I Have Checked

I have reviewed the current contribution guide, Commitrail guidance, architecture rules, roadmap, and the available Workstream MCP interactive design.

The MCP design is based on commit `c69ff85`. It describes 27 tools: 12 reads and 15 mutations, with operation keys required for 14 mutations. It exposes no resources or prompts and ends at project setup and access.

The maintainer has supplied the fixed public API list. Section 6 maps all 27 tool names to its operations and current route/schema owners at `6feef398`, with test references and differences from the original design. Source mapping does not replace running-server schema capture, joint agreement or MCP runtime proof.

The roadmap still distinguishes public capabilities from hidden implementations and planned work. A hidden backend service will not be treated as a public API available to the adapter.

I have also reviewed both complete Flow Identity designs. The architecture walkthrough, dated 10 September 2026, defines a human-only v0.1. The human and agent experience, dated 11 September 2026, defines an agreed future extension. Both are design records; neither claims that the integrations are deployed. I will keep that distinction clear in implementation and tests.

The planning PR is reconciled with main `6feef398`, including merged PR #400 and the updated API drill handoff. Public guide proposal review, pre-submission approval, correction and manual dispatch are exposed but outside the fixed 29-operation census and the proposed 27 tools. Guide creation itself has changed and is accounted for in the mapping. Recheck concurrent owner work before implementation; open work is not proof that an API is live.

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

The maintainer-owned API handoff is now received and mapped below. It covers all 27 original names without adding tools. The inventory records methods/routes, current body and result models, headers, success statuses and per-operation drill references. Schema differences and workflow limits are explicit for joint agreement before freezing the generated tool definitions. The agreed inventory will be the source for binding tests and contract-drift checks.

Tool calls will use a configured API destination and fixed routes. Users will not be able to supply arbitrary destinations or authentication headers. Redirects will not carry credentials to another destination.

For the 14 mutations that require an operation key, the client must supply and preserve that key. The adapter will forward it unchanged. The self-profile PATCH is the one unkeyed mutation. Automatic mutation retry is forbidden, including retry with the same key. If a response is lost after dispatch, the adapter cannot know whether the write completed. It will report uncertain execution without claiming failure or rollback. A later client-initiated attempt preserves the original key and follows the API's replay rules.

Policy updates will preserve required version selectors such as `If-Match`. A stale selector must produce the API's conflict outcome. If the initial catalogue lacks an operation needed to recover the current selector, I will document that limitation for review instead of using a write to imitate a read.

Errors will distinguish invalid credentials, invalid input, API denial, conflicts, unavailable dependencies, and uncertain execution. The result will preserve useful API status and correlation information while excluding secrets and raw internal exceptions. A successful MCP transport response does not mean the Workstream operation succeeded.

### API handoff mapping at `6feef398`

The maintainer supplied the [29-operation handoff](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5654783507). The table below maps all 27 original tool names to that fixed list and the reconciled backend source at `6feef398`. It is a proposed mapping for joint review, not a claim of MCP runtime execution or an approved catalogue freeze.

**Result:** 27 distinct tools match 27 distinct handed-off method/path pairs. Keep 12 logical reads, 15 mutations and 14 keyed mutations. The two unused operations are row 1, `GET /api/v1/health` (operational liveness, not a user tool), and row 18, `POST /api/v1/service-actors` (not part of this human-only catalogue). A human administrator reading or managing an existing service actor does not enable service actors to authenticate as MCP callers.

All paths below have the fixed prefix `/api/v1`. `K` means required UUID `Idempotency-Key`; `K+M` also requires `If-Match`; `-` means neither mutation header. Authentication is request context, never a tool argument. Request/correlation IDs remain transport metadata. Success codes below are backend HTTP codes, not MCP transport success. Body and response names refer to current backend models, not the stale embedded HTML schemas.

The **Drill** column names the exact row in the [fixed acceptance matrix](../../../docs/engineering/external-api-drill.md#fixed-29-operation-acceptance-matrix), including its named E/A cases, invalid inputs, authority, readback and replay controls. Linked response names point to the current route declaration for that binding; schemas are linked below. These references define the tests to reuse, not newly executed results.

| Tool | Method and path | Body model | Success data model | HTTP / headers | Drill |
| --- | --- | --- | --- | --- | --- |
| `workstream_profile_get` | `GET /actors/me` | None | [ActorProfileSelfResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/api/routes/auth.py#L43) | 200 / - | 2 |
| `workstream_profile_update` | `PATCH /actors/me` | `ActorProfileUpdateRequest` | [ActorProfileSelfResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/api/routes/auth.py#L113) | 200 / - | 3 |
| `workstream_authorization_context_get` | `GET /actors/me/authorization-context` | None | [ActorAuthorizationContextResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/api/routes/auth.py#L77) | 200 / - | 4 |
| `workstream_permissions_list` | `GET /authorization/permissions` | None | [PermissionDefinitionsResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L857) | 200 / - | 12 |
| `workstream_admin_roles_list` | `GET /authorization/admin-role-definitions` | None | [AdminRoleDefinitionsResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L885) | 200 / - | 13 |
| `workstream_admin_grants_list` | `GET /admin-role-grants` | None | [AdminRoleGrantCollectionResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L960) | 200 / - | 15 |
| `workstream_admin_grants_issue` | `POST /admin-role-grants` | `AdminRoleGrantIssueBody` | [AuthorityMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1021) | 201 / K | 14 |
| `workstream_admin_grants_revoke` | `POST /admin-role-grants/{grant_id}/revoke` | `AdminRoleGrantRevokeBody` | [AuthorityMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1125) | 200 / K | 17 |
| `workstream_actor_admin_grants_list` | `GET /actors/{actor_profile_id}/admin-role-grants` | None | [AdminRoleGrantCollectionResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L989) | 200 / - | 16 |
| `workstream_actor_get` | `GET /actors/{actor_profile_id}` | None | [ActorProfileAdminResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L775) | 200 / - | 5 |
| `workstream_actor_identity_link_get` | `GET /actors/{actor_profile_id}/identity-links` | None | [ActorIdentityLinkAdminResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L817) | 200 / - | 6 |
| `workstream_actor_suspend` | `POST /actors/{actor_profile_id}/suspend` | `ActorLifecycleBody` | [ActorLifecycleMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L636) | 200 / K | 7 |
| `workstream_actor_reactivate` | `POST /actors/{actor_profile_id}/reactivate` | `ActorLifecycleBody` | [ActorLifecycleMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L664) | 200 / K | 8 |
| `workstream_actor_deactivate` | `POST /actors/{actor_profile_id}/deactivate` | `ActorLifecycleBody` | [ActorLifecycleMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L692) | 200 / K | 9 |
| `workstream_identity_link_revoke` | `POST /actor-identity-links/{identity_link_id}/revoke` | `ActorLifecycleBody` | [IdentityLinkLifecycleMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L720) | 200 / K | 10 |
| `workstream_identity_link_reactivate` | `POST /actor-identity-links/{identity_link_id}/reactivate` | `ActorLifecycleBody` | [IdentityLinkLifecycleMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L748) | 200 / K | 11 |
| `workstream_projects_create` | `POST /projects` | `ProjectCreate` | [ProjectResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/create_router.py#L83) | 201 / K | 19 |
| `workstream_projects_get` | `GET /projects/{project_id}` | None | [ProjectResponse or ContributorProjectResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/router.py#L193) | 200 / - | 20 |
| `workstream_guides_create` | `POST /projects/{project_id}/guides` | `ProjectGuideCreate` | [ProjectGuideCreateResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/guide_mutation_router.py#L161) | 201 / K | 26 |
| `workstream_guides_update` | `PATCH /projects/{project_id}/guides/{guide_id}` | `ProjectGuideUpdate` | [ProjectGuideResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/guide_mutation_router.py#L184) | 200 / K | 27 |
| `workstream_review_policy_put` | `PUT /projects/{project_id}/guides/{guide_id}/review-policy` | `ReviewPolicyInput` | [ReviewPolicyResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/policy_mutation_router.py#L112) | 200 / K+M | 28 |
| `workstream_revision_policy_put` | `PUT /projects/{project_id}/guides/{guide_id}/revision-policy` | `RevisionPolicyInput` | [RevisionPolicyResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/projects/policy_mutation_router.py#L140) | 200 / K+M | 29 |
| `workstream_contributor_candidates_list` | `GET /projects/{project_id}/contributor-candidates` | None | [ContributorCandidateListResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1563) | 200 / - | 21 |
| `workstream_project_grants_issue` | `POST /projects/{project_id}/role-grants` | `ProjectRoleGrantIssueBody` | [ProjectRoleGrantMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1233) | 201 / K | 22 |
| `workstream_project_grants_list` | `GET /projects/{project_id}/role-grants` | None | [ProjectRoleGrantListResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1592) | 200 / - | 23 |
| `workstream_project_grants_get` | `GET /projects/{project_id}/role-grants/{grant_id}` | None | [ProjectRoleGrantRead](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1626) | 200 / - | 24 |
| `workstream_project_grants_revoke` | `POST /projects/{project_id}/role-grants/{grant_id}/revoke` | `ProjectRoleGrantRevokeBody` | [ProjectRoleGrantMutationResponse](https://github.com/Flow-Research/workstream/blob/6feef398/backend/app/modules/authorization/router.py#L1420) | 200 / K | 25 |

### Input and output details

Path selectors are supplied only where shown above. The authenticated actor is never replaced by a target selector. Preserve backend selector types: authorization target IDs are UUIDs; project/guide selectors follow their route and tool schemas. Query parameters are:

- Authorization context: required `project_id`.
- Both administrative-grant lists: required `scope_type`; optional `scope_project_id`, `status` (default `active`), `limit` (default 50, 1-100) and `cursor` (at most 512 characters). A project scope must satisfy the backend's project selector rules.
- Contributor candidates: `limit` (default 50, 1-100) and `cursor` (at most 512 characters).
- Project-grant list: optional `status` (`active` or `revoked`, omitted means unfiltered), `role` (`submitter` or `reviewer`), `limit` (default 50, 1-100) and `cursor` (at most 512 characters).
- All other bindings: no query parameters. Omit absent/null optional query values; do not decode or manufacture cursors.

Use these current model owners for the full field types, requiredness, enum values, nested schemas and validation. The field summaries below are navigation, not replacement validators:

| Model owner | Mapped fields and output boundaries |
| --- | --- |
| [Actor schemas](../../../backend/app/modules/actors/schemas.py) | Profile PATCH accepts only optional nullable `display_name` (200 characters) and `contact_email` (320). Preserve omission versus explicit null and normalization/NUL rules. Self responses contain the caller's declared profile fields; administrative actor/link responses are separate projections without raw subject or contact email. The plural identity-links route returns one object, not a list. |
| [Administrative schemas](../../../backend/app/modules/authorization/admin_schemas.py) | Grant issue uses `target_actor_profile_id`, `role`, `scope_type`, optional `scope_project_id`, and `reason`; revoke uses `reason`. Collection responses include `items`, `total`, `next_cursor`. Mutation responses are receipts, not full grant objects. |
| [Authorization router](../../../backend/app/modules/authorization/router.py) | Actor/link lifecycle bodies contain `reason`. Keep the existing lifecycle response models, catalogue projections and exact action binding; lifecycle operations do not provision a new identity or grant. |
| [Project-role request schemas](../../../backend/app/modules/authorization/project_role_schemas.py) and [nested qualification/read schemas](../../../backend/app/modules/authorization/schemas.py) | Grant issue uses `target_actor_profile_id`, `role` (`submitter` or `reviewer`), `qualification`, `reason`. Qualification contains skills/reputation availability snapshots, prior-project work UUIDs and external expertise references. Preserve nested availability consistency and collection/token bounds. Revoke accepts `reason`. Candidate and project-grant pages have `items` and `next_cursor`, no `total`. |
| [Project and guide schemas](../../../backend/app/modules/projects/schemas.py) | Project create: `name`, `slug`, optional nullable `description`. Project read preserves the API-selected administrative projection or the exact contributor `id/name/status` projection. Guide create: required `version`, `task_examples`, `documents`, optional nullable `change_summary`. Documents are 1-100 declarations with `label` and `media_type`; IDs/order are returned by the API. Guide PATCH accepts only optional nullable `change_summary`. |
| [Policy schemas](../../../backend/app/modules/projects/schemas.py) | Review input requires positive preference-window and lease-duration seconds; optional fields include strict boolean `human_review_required`, one active lease, no self-review, reject policy, finding evidence requirement, second-review flag, allowed decisions and minimum finding fields. Revision requires positive `max_revision_rounds` and `revision_deadline_hours`; optional state list is exactly one `needs_revision`, and reassignment rule is nullable. Preserve full version/hash/predecessor responses. |

### Authority and failure mapping

Guide task examples use the [nested task-example schema](../../../backend/app/modules/projects/api/task_examples.py): 1-100 examples, each with required nonblank `content`, optional nullable `title` and optional `labels`. Preserve its per-field and aggregate 128 KiB serialized UTF-8 bound; OpenAPI field types alone do not capture every custom validator.

Each tool uses its linked route's existing action and authorization path; the adapter does not recreate role evaluation. Self-profile/context operations act on the authenticated caller. Catalogue, actor, identity-link and administrative-grant operations retain their administrative/audit boundaries. Project creation requires the backend's system-scoped project-manager authority. Project reads may use exact contributor access; project management, candidate discovery and grant/policy mutations retain their exact-project and current-role checks. An administrative tool being listed is not permission to invoke it.

Run the named tests for each matrix row under the same caller categories, including ordinary users, applicable administrators/auditors, project managers, foreign-project managers, revoked/suspended/deactivated actors and revoked links. Preserve concealed 404 responses where the API uses them; do not convert every denial to 403 or expose target existence. Retain self-grant/self-removal and final-effective-administrator safeguards in the API, never a parallel adapter implementation.

For all rows, preserve actual API status, safe error code and correlation metadata. Applicable cases include 401 token rejection, 403 authority refusal, concealed 404, 422 input/header rejection, 409 state/precondition/idempotency conflicts, and 429/503 rate/dependency failures. This is not a claim that every row produces every code. The per-row drill cases and [findings and fixes](../../../docs/engineering/external-api-drill-findings.md) are the observed error oracle; OpenAPI's declared success/validation responses alone are insufficient. In particular, key mismatch and state-changed replay conflicts are not interchangeable. Do not retry a mutation automatically, even on a retryable API error.

Candidate and project-grant lists also return `400 invalid_cursor` for invalid cursors; preserve that instead of relabeling it as schema validation. Policy selector errors distinguish `policy_precondition_invalid` from `policy_precondition_failed`, both HTTP 409.

For the 14 keyed mutations, retain the original key, normalized request semantics and API replay outcome. Recheck current authority on replay through the API. Do not promise that an earlier receipt can always be replayed after target state or authority changes. The unkeyed profile PATCH remains unkeyed. Reads may update admission timestamps, so read-only means no requested product mutation, not absolutely no database writes.

### Differences and decisions to freeze

1. **Guide contract has changed.** Remove `content_markdown` from guide input/output. Add required task examples and document declarations; create success is now `ProjectGuideCreateResponse`, including `documents` and `setup`. PATCH still returns `ProjectGuideResponse`. Preserve task-example content/hash and all declared metadata. Do not silently keep the old embedded schemas.
2. **This catalogue does not complete guide setup.** Creating a guide returns `awaiting_documents`; there is no upload tool among the 27. Upload/setup/findings and the four proposal APIs from PR #400 are outside the handed-off 29-operation census. Confirm that the first release deliberately stops at declarations and draft policy configuration, with uploads handled outside MCP. Adding that workflow requires an explicitly agreed scope change.
3. **Policy omission and selector behavior matter.** Review input/output now includes `human_review_required` and response semantics metadata. Omission of the mode preserves a selected predecessor's setting; ordinary omitted optional fields use backend defaults. Do not fill defaults in the adapter. First creation uses the quoted `"no-current-policy"` selector. A later selector is the quoted policy ID, generation and hash without its `sha256:` prefix, joined by dots, as specified by the [policy owner](../../../backend/app/modules/projects/policy_mutation_service.py). Forward a caller-supplied selector unchanged. The 27 tools have no policy-read operation for recovering a lost/stale selector; confirm an outside-MCP recovery path or separately agree a read tool. Never use a write as discovery.
4. **Refresh all schemas, not just guide names.** Current validation also includes NUL rejection, qualification limits and revision-policy constraints. Before freezing generated tool JSON, compare the selected operations and their transitive schemas against `/openapi.json` from the exact pinned backend build. The source mapping here is complete; running-server schema capture and MCP conformance execution have not been performed in this planning change. Do not describe the old HTML JSON as the approved current schema.
5. **Credential handoff remains an owner decision.** The API list does not resolve MCP resource registration, audience or the credential presented to Workstream. Keep the caller's authority intact without inventing token exchange, accepting a wrong-audience token or substituting an administrator identity.

For implementation evidence, reuse [the drill setup](../../../docs/engineering/external-api-drill.md#run) and per-row assertions through an actual MCP client and independently running adapter. Keep health, local bootstrap and service-actor fixture provisioning outside the 27-tool count. Setup may need backend-only calls, but tools must dispatch only their agreed endpoint. Retain direct-API parity checks, state/audit checks, rejection-before-write assertions and same-key recovery. Existing historical backend runs are useful evidence, not proof that the new MCP path or live Flow deployment passes.


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
| 10. Contract drift | Use the source mapping in section 6 and jointly freeze the exact 27-tool definitions against the pinned running backend schemas, including routes, schemas, headers, statuses, authorization and API drill evidence. CI must fail on route, method, input/output, header, status, annotation or capability drift. Regeneration must not silently accept a changed contract. Changes require deliberate review and renewed proof. |

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

## 9. Chunk Map and PR Boundaries

Before runtime work, jointly review the completed source mapping and its schema/workflow differences, capture the pinned running backend schemas, freeze the tool definitions, and agree the MCP-to-API credential contract. The API-list handoff is complete; the mapping does not itself settle those remaining decisions. Then proceed through the following proposed implementation PRs:

The following stable IDs replace the four broad headings. Each row is one intended implementation PR and one observable outcome. Paths are proposed ownership under the new `mcp_server/` package, not claims that those files exist. Tool names below omit only the common `workstream_` prefix. Every one of the 27 names in section 6 appears exactly once. All chunks also own their matching combined change record and directly affected tests/docs; they do not own backend product behavior.

| Change ID and outcome | Depends on | Owned modules and exact new tools | PR acceptance evidence and next usable boundary |
| --- | --- | --- | --- |
| WS-MCP-002-01: one authenticated self-profile read through an independently installed adapter | Catalogue/schema agreement and credential decision below; [first contract](WS-MCP-002-01.md) | Package/container/configuration, `workstream_mcp/{server,auth,http_gateway,errors,schemas}.py`, `tools/profile.py`; `profile_get` only | Package-only install/container, protocol/credential isolation/privacy tests, real profile API parity and rejected-token no-dispatch proof. Leaves one protected path and test harness for later bindings, not 27 working tools. |
| WS-MCP-002-02: own profile editing and project authorization context | 01 | `tools/profile.py`, `tools/context.py`, their schemas/registry entries; `profile_update`, `authorization_context_get` | Profile omission/null/normalization/atomic rejection, unkeyed PATCH and no automatic retry; exact-project context, revoked/foreign access and safe data tests. Leaves complete self-service surface. |
| WS-MCP-002-03: inspect authorization definitions and administrative projections | 01 | `tools/access_reads.py`; `permissions_list`, `admin_roles_list`, `admin_grants_list`, `actor_admin_grants_list`, `actor_get`, `actor_identity_link_get` | Frozen catalogue/projection fields, pagination/cursor behavior, admin/audit/ordinary denial matrix and no contact/subject leakage. Leaves administrative readback for mutation proofs. |
| WS-MCP-002-04: issue and revoke administrative grants | 03 | `tools/admin_grants.py`; `admin_grants_issue`, `admin_grants_revoke` | Exact receipts/history, scope and self-grant checks, last-admin protection, key mismatch/replay/current-authority checks and lost-response handling. Leaves HTTP-owned administrative authority changes. |
| WS-MCP-002-05: manage actor and identity-link admission | 03, 04 | `tools/actor_lifecycle.py`; `actor_suspend`, `actor_reactivate`, `actor_deactivate`, `identity_link_revoke`, `identity_link_reactivate` | Each reason/key boundary, self/final-admin guards, terminal deactivation, revoked-link admission and replay/current-state tests. Leaves bounded lifecycle administration, no new identity registration. |
| WS-MCP-002-06: create and read project shells | 01, 04 | `tools/projects.py`; `projects_create`, `projects_get` | System-manager create, duplicate slug/replay/conflict and administrative versus three-field contributor read projections. Leaves exact project selectors for project-scoped chunks. |
| WS-MCP-002-07: manage project participation | 03, 06 | `tools/project_grants.py`; `contributor_candidates_list`, `project_grants_issue`, `project_grants_list`, `project_grants_get`, `project_grants_revoke` | Populated bounded cursors, qualification fields, both roles, cross-project/target substitution, revoked access, replay/concurrency and unchanged-state denials. Leaves project access management, not task eligibility logic in MCP. |
| WS-MCP-002-08: declare guide documents and edit draft metadata | 06; agreement on upload exclusion | `tools/guides.py`; `guides_create`, `guides_update` | Current examples/documents schema, waiting-setup response, summary-only PATCH, immutable-field rejection, UTF-8/aggregate limits and replay. Leaves document declarations; actual uploads/setup completion stay outside MCP. |
| WS-MCP-002-09: configure draft review and revision policies | 08; agreement on selector recovery limitation | `tools/policies.py`; `review_policy_put`, `revision_policy_put` | Correct initial/current `If-Match`, omission versus defaults, human-review mode, stale/malformed selectors, lineage, exact-project denial and replay. Leaves draft policy configuration without approval/activation tools. |
| WS-MCP-002-10: prove the assembled 27-tool release | 02, 05, 07, 09 and their ancestors; agreed live identity/client environment | `tests/integration/`, release drill, deployment/client docs and contract snapshot validation; no new tools | Complete ten-suite matrix, 27/27 positives plus per-tool negatives and mutation replay, actual client-to-adapter-to-API/PostgreSQL parity, deployed proxy no-store/caller isolation and independent container. Leaves a release candidate for human decision, not an automatic merge/deploy. |

The dependency column describes technical prerequisites, not permission to start another chunk automatically. Default delivery follows row order. Independent branches may be proposed only after checking shared registry/schema ownership. One chunk finishes with its checks, focused review and human review/merge direction before beginning the next. If a chunk grows beyond its coherent behavior, revise its contract/map before adding unrelated implementation; do not silently combine rows into one PR.

Every binding chunk includes its route/body/query/header/status tests, public API authorization and error parity, snapshot drift checks, privacy checks, and relevant mutation replay/failure tests from its first PR. Tests may use public-API-only fixtures for prerequisite state that has no MCP tool; fixture setup must not masquerade as catalogue coverage. The final drill assembles existing proofs and adds deployed/live integration coverage; it is not the first test of any tool. Each partial catalogue is asserted exactly, with zero prompts/resources and no placeholder tools.

### Decisions before dependent code

- **Catalogue and schemas:** jointly agree the 27-name mapping and its corrected guide/policy schemas. Capture selected operations and transitive schemas from `/openapi.json` of the pinned backend, with source SHA and explicit differences if a newer runtime target is selected. Main reconciliation alone does not silently replace the handoff baseline or approve drift.
- **Credential contract:** record MCP resource/audience, downstream Workstream resource/audience, the owner-supported credential mechanism, preservation of human caller identity, issuer/JWKS/client configuration and the test environment. Do not assume forwarding, exchange or shared audience. This must be settled before 01 implements protected dispatch.
- **Workflow limits:** agree that document upload/setup completion and recovery of lost/stale policy selectors remain outside this catalogue. No automatic extra endpoint, hidden route or write-as-read workaround.

The first record is authored here as a proposed contract, with runtime acceptance still unchecked. Its implementation PR will update that same `WS-MCP-002-01.md` record, not introduce a second intent/plan/risk bundle. Before each later chunk starts, create its own combined record from the current template. The earlier planning record is consolidated into this first contract so this planning PR and each future implementation PR contain exactly one change record.

I will follow the current Commitrail process: one initiative overview for this multi-PR effort and one change record for each implementation PR. Each record will state the allowed files, non-goals, acceptance criteria, risks, and required review. Open PRs will be checked for overlapping changes before each boundary starts.

Review will follow the repository's risk routing, including security and architecture for the foundation. Relevant lint, type checks, tests, coverage requirements, and repository gates will be preserved. Roadmap impact will be assessed in the same PR. GitHub will hold current checks and approvals; the repository records will hold durable decisions. Merge remains a human decision.

## 10. Points for Your Review

The addendum confirms the human-only, 27-tool release and independently packaged deployment within this repository. The remaining questions are:

1. How should the separately deployed MCP adapter and Workstream API be registered as resources, and which credential should the adapter use for the API call? Which test environment and preregistered MCP clients should prove that contract?

2. Can we freeze the mapped 27 names with the corrected guide/policy schemas, leaving document uploads and lost-policy-selector recovery outside MCP for this release? These workflow limits are detailed in section 6; adding tools needs explicit agreement.

The public API list is received and the source mapping is complete. Joint catalogue review remains. Privacy, conditional MCP headers and `no-store` response caching are settled by the linked clarification.

The proposal follows the documents' human-only v0.1 baseline and keeps the future agent extension explicit. The chunk map and first contract are ready for review. Runtime work starts only after the relevant catalogue, schema and credential decisions are recorded; this proposal is not merge approval.

## References

- [Maintainer API handoff](https://github.com/Flow-Research/workstream/pull/401#issuecomment-5654783507)
- [Fixed public API drill and cases](../../../docs/engineering/external-api-drill.md)
- [API drill findings and fixes](../../../docs/engineering/external-api-drill-findings.md)
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
