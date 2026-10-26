# Shared setup and POST model access

Workstream pays for supported model calls through one project-lifetime account.
The same account serves guide setup inference and approved POST checker agents,
but each call keeps a strong workload-specific owner:

- setup calls bind the exact compilation attempt, setup generation, runtime
  configuration hash and phase/call index;
- POST calls bind the exact Submission, requirement, locked registry image and
  configuration, current checker execution and stable paid slot.

The model proxy owns credentials, request bounds, reservations, provider effects,
private evidence and settlement. It does not own setup tools, checker rubrics,
submitted-code execution, policy approval, acceptance or revision routing.

## Provision a project

A system Operator publishes immutable project model profiles and configures one
finite lifetime budget. These are separate authorized operations; approving a
guide or POST policy never grants budget authority.

| Operation | Route |
| --- | --- |
| Publish an immutable profile | `POST /api/v1/operations/projects/{project_id}/model-profiles` |
| Configure the project lifetime ceiling | `POST /api/v1/operations/projects/{project_id}/model-budget-configurations` |
| Inspect one exact paid effect | `GET /api/v1/operations/projects/{project_id}/model-usage/effects/{effect_id}` |
| Authorize an eligible checker recovery child | `POST /api/v1/operations/projects/{project_id}/model-call-attempts/{parent_attempt_id}/recovery-children` |

Mutations require their documented idempotency key and fresh system-Operator
authority. The exact-effect read uses `project.model_usage.read` under the
existing model-budget management permission. It conceals missing and foreign
effects and returns only bounded identities, usage, cost and ART custody facts;
it never returns provider IDs, credentials or transcript bytes.

Amounts are integer USD nanodollars. US$10 is `10000000000`. A new explicitly
authorized budget version may raise the ceiling, but it never resets settled or
reserved spend. `externally_reconciled_prior_spend_nanodollars` records only
spend reconciled outside this ledger and cannot decrease. Historical setup spend
must not be guessed as zero. Until the Operator has reconciled the remaining
allowance, paid calls fail closed.

Profiles are project-owned, not checker-image-owned. Each immutable version fixes
the provider/API/model snapshot, reasoning and verbosity, per-call and aggregate
call/token/byte/deadline limits, allowed tools and their aggregate limits, integer
pricing ceilings and pricing provenance. Multiple provider/model identities may
coexist for one project.

Setup selects the newest published version matching the already configured exact
provider/API/model when a compilation attempt is created, then snapshots the
profile ID/version/digest into that attempt. A later publication cannot redirect
an existing attempt. POST policy configuration carries the same selector triple:

```json
{
  "model_profile_id": "<profile UUID>",
  "model_profile_version": 1,
  "model_profile_digest": "sha256:<digest>"
}
```

The POST owner separately validates the exact approved registry image and locked
configuration. A partial selector, another project's profile, a same-project
profile with a different provider/model, a PRE binding or a stale policy is
unavailable before spend.

## Supported provider boundaries

POST model sessions currently use the closed `openai_responses` / `responses.v1`
adapter. Setup preserves both native agent runtimes through a credential-free
local transport:

- OpenAI Agents SDK uses the approved `openai` / `responses` request shape;
- OmniCoreAgent uses the approved `openrouter` / `chat_completions` shape.

The setup proxy accepts only the exact selected model, two neutral document tools,
locked reasoning/verbosity, finite completion output and strict structured output.
Remote prompt references, provider routing/fallback controls, hidden retries,
unapproved service tiers and provider-side storage are rejected. OpenAI input is
counted with the provider's input-count endpoint before dispatch. OpenRouter uses
the exact non-alias model metadata endpoint before dispatch and requires current
context, completion, parameter and pricing metadata to fit the immutable profile;
unknown or unsupported non-token fees fail before spend. Metadata-to-dispatch
consistency remains an external provider assumption that must be requalified for
the selected account and model.

Setup's fixed `read_document` and `search_document` capability retains its own
owner-side actual call/output counters. A model session opens only when those
runtime ceilings fit inside the selected profile's tool-call and tool-output
ceilings. The profile's aggregate paid-call/token/byte envelope spans the complete
setup attempt across draft, review and correction phases.

## Runtime and credentials

Run exactly one trusted model-proxy process for a private socket. Project images
receive only an invocation-local relay socket. A hosted setup worker receives the
global socket directory read-only; it does not own the socket and receives no
provider key. API and Beat receive neither socket nor provider credential.

Hosted inference uses a dedicated digest-pinned `agents` backend image for the
proxy even when the setup worker uses the mutually exclusive `omnicore` image.
The proxy image contains the pinned OpenAI input-count/Responses dependencies and
the OpenRouter HTTP adapter. Its entrypoint validates the root-owned SDK marker
before reading the two closed proxy-only provider secrets. Proxy enablement is
independent of setup runtime selection, so `manager_authored` setup can coexist
with model-backed POST checks and OpenRouter setup can coexist with OpenAI POST.
See
[`deploy/hosted/README.md`](../deploy/hosted/README.md).

The local agent-loop overlay uses
`WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET=/run/ws-model-proxy/model-proxy.sock` and
the existing `model-proxy` profile. Configure the Rust checker service with the
same global socket and its private relay root. The image never sees that global
socket, a provider key, model coordinates or arbitrary network egress. See the
[external checker protocol](../external_checkers/README.md).

Socket roots are canonical mode-`0700` directories and sockets are mode `0600`
under one non-root identity. Stop producers first, drain active executions, then drain the
proxy before removing any stale socket. Restarting a process does not clear a
reservation or authorize another provider create.

## Paid-call lifecycle

1. The workload owner proves current authority and exact locked lineage before
   taking MODEL-USAGE locks.
2. MODEL-USAGE selects the immutable profile/account/run envelope and stable
   phase/call slot, verifies the canonical request hash and retains request ART.
3. It reserves that dispatch's worst-case charge and conservative token/response
   capacity against both the project lifetime account and immutable run envelope,
   then commits dispatch intent before provider I/O.
4. The trusted adapter performs exactly one bounded provider dispatch with hidden
   retries disabled. Provider acceptance, when known, is checkpointed with the
   provider ID and response digest before response ART work.
5. Canonical response and usage bytes are stored, independently verified and
   immutably bound through ART. Settlement replaces the reservation once using
   the locked pricing version. Cached input is priced separately and reasoning
   tokens are not charged twice.
6. A retry with the same stable owner and request reconstructs the exact retained
   response. Request drift conflicts; lease renewal or checker retry does not mint
   a new paid effect.

Each setup phase may consume several finite call slots; POST profiles likewise
bound the complete image session. A conditional image path may leave an unused
capability untouched, but every started call must reach a replay-safe terminal or
remain held as uncertain. No profile, image, correction or retry creates a second
project budget.

## Failure and recovery

| Condition | Durable result | Safe next action |
| --- | --- | --- |
| Missing or exhausted funding | No provider dispatch | Operator configures reconciled funding; retry the same owner workflow |
| Input/metadata/profile refusal | Proven no provider effect | Correct authorized configuration; do not charge a revision |
| Delivery ambiguous without usable provider evidence | `uncertain`, full reservation retained | Inspect the exact effect; never create again without authenticated no-effect proof |
| Provider ID/response known, ART or callback interrupted | Exact effect and response identity retained | Recover and verify original ART/provider evidence, then complete without another create |
| Complete provider failure with authenticated usage | `known_failed`, usage settled | Checker-only authorized child may be prepared when eligibility is proven |
| Completion delivered but runtime/image reply lost | Completed effect, ART response and settled cost | Fresh authorized owner consumes the cached completion |

Setup recovery never fabricates checker lineage. The setup handler reads retained
verified response ART and completes the original setup effect. Provider storage is
disabled: if delivery succeeds but the process is lost before response ART is
retained, a provider ID alone does not make that response retrievable. That effect,
like an ID-less genuinely ambiguous response, remains uncertain with its reservation
held until authenticated evidence can establish a safe terminal outcome. The exact
Operator read provides visibility but cannot assert no effect, release money or
create a replacement.

For POST, budget exhaustion, provider outage, unavailable runtime and invalid
provider output remain infrastructure failure on the original Submission. They do
not prepare a revision, start a revision deadline or spend a revision round.
Eligible checker children still require the existing fresh Operator recovery
authorization and a current checker execution.

## Verification boundaries

Repository tests use controlled HTTP/provider transports; they perform no live
paid calls. PostgreSQL tests cover setup/checker concurrency on one account,
canonical lock waits, rollback, profile/budget versioning, replay and settlement.
MinIO tests cover setup request/response custody and crash recovery. Unix-socket,
Rust relay and networkless-container tests cover the restricted transport.
Release composition tests prove that only the proxy receives provider secrets and
that setup workers mount only the socket read-only.

These checks do not establish the external provider account state, current live
pricing, model quality, deployed gVisor/AWS operation or the Terminal Systems
activation-to-contribution journey. The existing US$10 authorization is one
aggregate rehearsal ceiling, not an allowance per SDK, image, retry or call.
