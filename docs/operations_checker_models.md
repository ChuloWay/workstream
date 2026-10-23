# Project checker model calls

Model review is part of a project's external POST image. The image owns its
prompt, rubric and interpretation. Workstream controls which model it can call,
the maximum spend, private evidence and recovery. The shared Rust runner only
provides the invocation's private socket; it contains no project rubric or
provider SDK. PRE images have no model capability.

## Configure a project

Register the project's digest-pinned POST image through the existing checker
registry. An Operator provisions an immutable model profile for that exact
project and registry entry, and a finite lifetime project budget. The profile
contains the provider/API pair, exact model snapshot, reasoning and verbosity,
byte/token/deadline bounds, and integer pricing with an immutable pricing
reference. The supported pair is `openai_responses` / `responses.v1`. The adapter
explicitly requests the provider's standard pricing tier. Verify the selected
snapshot's current standard rates before authorizing live spend.

Include the complete selector in the existing policy proposal's image
configuration:

```json
{
  "model_profile_id": "<published profile UUID>",
  "model_profile_version": 1,
  "model_profile_digest": "sha256:<published digest>"
}
```

Project-specific configuration may accompany it when the registered image schema
allows those fields. The PM approves this configuration through the existing
policy path. A partial selector, a profile from another project/image, or a PRE
binding is invalid. The setup specification identifies `model_service` with
`model_proxy` provisioning; this does not waive registration, approval or
activation checks. Required unbound capabilities still block activation.

Budget amounts use integer USD nanodollars: US$10 is `10000000000`. A later budget
configuration changes the ceiling without resetting settled spend or outstanding
reservations. A project cannot lower its ceiling below the sum already committed.
The budget belongs to Workstream-paid evaluation, not contributor compensation.

## Runtime and credentials

For the local agent-loop compose overlay, enable the `model-proxy` profile and
start its singleton `model-proxy` service. It runs
`python -m app.workers.checker_model_proxy` with
`WORKSTREAM_CHECKER_MODEL_PROXY_SOCKET=/run/ws-model-proxy/model-proxy.sock`.
Ordinary API workers do not own this listener. The backend's existing
`OPENAI_API_KEY` supplies credentials; never put that key in an image, policy,
checker input or command output. Configure the Rust service's `model_proxy_socket`
to the same path and `model_relay_root` to its private daemon-visible relay root.
The local configuration generator supports `--enable-model-proxy` for those Rust
settings. See the [external checker protocol](../external_checkers/README.md).

Run exactly one model-proxy process owning a given socket. The listener
requires an existing private directory owned by its process user, refuses an
occupied socket path, and drains admitted handlers during graceful shutdown.
After a forced process kill, confirm the old owner has stopped before removing
its stale socket and restarting. Restart does not clear reservations or replay
provider creates. The proxy's durable tables and private ART objects remain the
recovery authority.

## What happens for each call

1. A current POST execution receives one short-lived invocation grant for its
   exact locked binding. The grant never enters the image. Rust exposes only
   `/work/model.sock` to that image, with ordinary networking still disabled.
2. The image sends one bounded prompt. Workstream authorizes it, binds the exact
   request hash to a stable paid-call slot and consumes the invocation grant.
   A successor checker run uses the same slot; a changed prompt is a conflict.
3. Workstream retains and verifies the request through ART. In one PostgreSQL
   transaction it reserves the profile's maximum possible charge and commits
   dispatch intent. Only the caller that first committed that intent may create
   the provider response. Network I/O occurs outside the database transaction.
4. The provider input-token count must fit the approved profile. The adapter
   disables automatic create retries and requests a stored background response.
   It persists a returned provider ID before polling or retaining terminal bytes.
5. Authenticated terminal output and complete usage are retained through ART.
   Settlement replaces the reservation once, using the locked integer rates.
   Cached input is priced separately; reasoning tokens are part of output tokens
   and are not charged twice. A current authorized invocation receives only
   bounded output and a receipt digest, never provider coordinates.
6. The image interprets that output and returns the ordinary normalized checker
   result. Workstream verifies the corresponding completed call before accepting
   a completed model-image result. Existing routing decides acceptance or
   contributor revision; the model proxy cannot do either.

## Failure and recovery

| Condition | Retained effect | Permitted next action |
| --- | --- | --- |
| Budget unavailable | No provider dispatch | Configure sufficient budget, then use existing checker recovery |
| Input counting proves no create occurred | `known_no_effect`; reservation released | Explicit Operator-authorized child attempt, then checker recovery |
| Create response lost, no provider ID | Uncertain; full reservation retained | Investigate; no automatic or Operator child create without proof of no effect |
| Known provider ID still pending/unavailable | Original effect and reservation retained | Retrieve that ID through a fresh authorized execution |
| Terminal failure without complete usage | Uncertain; reservation retained | Recover complete usage for the original ID; no paid child yet |
| Terminal failure with complete settled usage | `known_failed`, immutable evidence | Explicit Operator-authorized child attempt, then checker recovery |
| Completed call but worker/image response lost | Completed effect, original ART bytes and settled cost | Fresh current execution attaches the same cached completion |

Infrastructure and budget failures never consume a contributor revision. A late
provider response may finish the original paid call after its checker lease has
ended, but cannot deliver output to a stale invocation or create another effect.
Recovery requires current authorization; knowing a row ID is not authority.

Request/response evidence is private ART content. Ledger rows contain identities,
hashes, pricing and usage, not transcript bytes. Do not put transcripts or provider
coordinates in contributor findings, logs, exports or outbox payloads.

## Verification boundaries

Provider transport tests use the real SDK with a recorded HTTP transport; they
make no live calls. PostgreSQL tests cover budget serialization, immutable
receipts and invocation consumption. ART tests exercise storage/verification and
failure recovery. Unix socket tests prove framing and lifecycle locally.
Docker development isolation does not qualify gVisor: the mounted Unix socket
requires administrator-enabled `host-uds=open` and a separate real gVisor run.
Record the exact image digest, profile, budget, tested revision, provider usage
and retained effect identities for a live rehearsal; passing unit counts do not
establish the project's complete activation-to-contribution journey.
