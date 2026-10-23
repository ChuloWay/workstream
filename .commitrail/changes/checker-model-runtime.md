# Shared budgeted model access for setup and POST checker agents

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Give setup inference and policy-bound POST agents one
  project-funded model-use boundary with authentic workload lineage, immutable
  evidence and recovery that cannot silently repeat a paid effect.

## Intent

The user resumed PILOT-05 for the real Terminal Systems project and then expanded
its intended outcome to the existing setup inference adapters. POST images own
their rubrics, bounded agent loops and interpretation; setup retains its existing
strict draft/review/correction SDK loops. Workstream owns one model-use authority,
project lifetime budget, provider effect and evidence boundary across both. No
project rule or generic agent framework belongs in the shared Rust runner.

## Intended merge behavior

One MODEL-USAGE owner supplies immutable project profiles, a non-resetting
project-lifetime account, bounded run envelopes, paid effects and private ART
evidence to both setup inference and approved POST images. Setup retains its
native OpenAI Agents SDK and OmniCoreAgent loops through the trusted proxy; POST
retains project-owned rubrics and invocation-local transport. Strong typed setup
and checker subjects share the meter without fabricating a CheckerRun for setup.
The linear `0061_model_usage` migration follows main's
`0060_audit_restore_path`; intermediate upgrades retain main data and leave one
head.

## Bounded change

### Allowed

- A provider-neutral MODEL-USAGE owner for project profiles, one project lifetime
  account, reservations, settlement, paid effects and protected evidence.
- Strong owner-specific setup and CHECKERS subject contracts. Setup binds the
  exact compilation attempt, setup generation and snapshotted runtime hash; POST
  binds exact Submission/requirement/registry/configuration and current run/lease.
- Existing pinned OpenAI Agents SDK and OmniCoreAgent request boundaries, without
  replacing either agent loop or forwarding arbitrary HTTP.
- CHECKERS selected POST integration and existing AUTH, PROJECTS and TASK ports
  for fresh owner currentness and Operator provisioning.
- Existing ART generated-output custody to retain bounded private model
  request/response evidence, with matching authority, read concealment and
  exact setup/checker lineage.
- Typed provider capability under `backend/app/interfaces/`, concrete adapter
  and explicit ADR-0014 composition; fixed settings outside images.
- One linear Alembic continuation with preflight, intermediate upgrade and
  retained-data proof; affected schema snapshots, permission catalogues and MCP
  contracts updated together where changed.
- Shared Rust runner and SDK: invocation-local socket transport only, preserving
  network denial, read-only submission material, cleanup and output budgets.
- Focused PostgreSQL/MinIO, transport, provider and public lifecycle tests;
  affected CI allocation, owner specifications, runbook and roadmap.
- Reconcile the existing CLI retry-source decoder and its process tests with
  the bounded model recovery candidates returned by that public read.

### Not allowed

No provider credential or global proxy socket in project images; no contributor
or project-owner billing, alternate checker implementation kind, project rules
in Rust, generic agent framework, arbitrary forwarding proxy, unrestricted
provider/model selection, automatic paid retry after ambiguous delivery, or
task/revision spending on infrastructure failures. Historical setup spend lacks
authenticated pricing/usage facts and must not be guessed as zero or backfilled;
paid work stays disabled until an Operator provisions an externally reconciled
remaining allowance within the already-approved US$10 total rehearsal ceiling.
No live paid call, merge or hosted deployment is authorized here.

## Design and decisions

An immutable project model-use profile binds provider/API/model snapshot,
generation parameters, per-call and whole-run dispatch/token/byte/deadline
ceilings, supported tool/request shape and immutable integer pricing. The common
profile is not registry-owned; the POST owner separately binds it to an exact
registry/image/configuration while setup snapshots the same selector into its
attempt runtime configuration. Reserve the complete selector triple
`model_profile_id`, `model_profile_version`, `model_profile_digest` in the flat
PM-approved image configuration. A typed exact profile reader checks project,
provider/API/model and profile identity during policy compilation, setup request,
readiness/activation and runtime. Partial selectors fail; existing owner hashes
retain custody without a new checker kind or TASK lineage column.
The user authorized US$10 total for the Terminal Systems rehearsal; configure
10,000,000,000 USD nanodollars and preserve all reservations and settled spend
across retries and configuration versions. No live call may precede enforcement.
An Operator sets a finite project budget; profiles do not
allow images to change that budget or choose a different model. Monetary amounts
use integer USD nanodollars with explicit immutable pricing provenance.

Each owner allocates a finite phase/call slot before provider I/O; transport
arrival order and in-memory counters cannot mint durable identities. POST grants
bind current execution and exact Submission/requirement/registry/configuration.
Setup grants bind the exact compilation attempt/generation/runtime hash without a
fabricated CheckerRun. Rust exposes only invocation-local capabilities. Native
setup wrappers intercept each real pinned-SDK request; project images receive a
restricted model session. Credentials, global endpoints and opaque backend grants
never enter image input or logs.

Whole-run reservation is sized for every possible actual provider dispatch,
including correction and supported retries. Hidden SDK retries are disabled or
metered individually; ambiguity prohibits the next dispatch. Restart replays
cached exact provider responses only when canonical request hashes match, so SDK
state and tool-call identities reconstruct without another paid create. Known
provider IDs may be retrieved; unknown effects retain reservation and cannot be
recreated. New children remain limited to proven no-effect or fully settled
eligible failures.

The common effect row has exactly one SQL-enforced strong owner binding. Checker
lineage retains composite submission/registry/configuration custody; setup lineage
uses composite compilation-attempt/project/setup-generation/runtime-hash custody.
No owner-kind/owner-ID pair or JSON-only lineage is sufficient. AUTH plus the
affected PROJECTS/TASK owner locks precede MODEL locks; narrow late completion can
finish an already-paid exact effect without re-entering those owners, while a new
dispatch always requires fresh owner currentness first.

The paid slot identity is `(project, assignment, submission, submission_version,
requirement, registry_digest, configuration_hash, profile_version, slot_index)`.
Neither worker lease nor checker retry generation belongs in this key. The first
provider request hash is immutable: a later changed prompt conflicts. Successor
checker runs reuse the same cached or recoverable call. An authorized child
attempt is possible only after a proven no-effect outcome or an authenticated
terminal provider failure with no usable output and fully settled usage. It
requires explicit Operator recovery authority and a new atomic reservation;
the image cannot select its attempt number.

Create or attach the stable slot and verify its request evidence first. Reserve
the worst-case allowed input/output charge just before first dispatch, after
fresh authority/currentness, committing reservation and dispatch intent together
before provider I/O. Preserve
AUTH/TASK-before-CHECKERS custody; budget locks must never lead back to TASK.
Concurrent callers serialize the same slot and project budget. Persist dispatch
intent before create, persist provider identity immediately when returned, and
settle measured usage exactly once. Lost create responses remain uncertain and
retain their reservation; absence of a provider ID is not proof of no effect.
Known provider IDs may be retrieved without another create. Cached completion
is immutable and survives process, lease and Operator retries.

Keep the existing CheckerRun lifecycle. A run may finish `infrastructure_failed`
when its model response is unavailable, while the independent paid call remains
`dispatching` or `uncertain`. Operator retry attaches the same slot; it may only
recover that effect, never create again because a generation changed. A late
response may complete the original call after its run terminalized, allowing the
next current run to consume its cached evidence. Only an explicitly authorized
child of a proven no-effect or fully settled terminal failure receives fresh
dispatch authority. An uncertain effect or terminal failure with missing usage
remains ineligible.

Extend the existing ART generated-output custody with a paid-call-stable
reservation for two bounded canonical JSON slots: request before dispatch and
response/usage on known completion. Do not write transcript bytes to PostgreSQL,
Redis or outbox payloads. Ledger rows contain exact content identities and hashes.
Once dispatch intent is committed, the call-effect owner retains narrowly scoped
authority to finish/recover those exact evidence slots independently of the
original worker lease. It cannot start a new effect under that authority. Fresh
current-run authority links verified call evidence to each consuming run; stale
images cannot spend or gain read access to another invocation. This extends the
same ART put/verify/bind lifecycle, not a parallel artifact store. The unused
run-only write selector and deny-only producer composition are replaced; retained
historical rows keep their immutable ancestry. Private call bindings remain
retained independently of the original checker run.

Execution-trial reservation, engine behavior and trial-evidence ownership remain
in issue #493. This change exposes the bounded multi-call/model-evidence session
used by that project runtime, but does not claim execution-tool custody or add a
trial table to the independent #492 migration.

The local relay root must be mounted at the same Docker-daemon-visible path,
with private same-UID socket custody. gVisor requires the administrator-provided
`host-uds=open` configuration for this mounted socket; Docker development proof
does not qualify gVisor behavior.

Explicit service actions separate `checker.model_call.dispatch`,
`checker.model_call.recover` and `checker.model_call.complete` under existing
AUTH grants. Dispatch takes exact current execution facts; recover can only
inspect the existing effect; complete takes immutable call-attempt/effect facts
and may retain late evidence. Operator project budget/profile provisioning and
return exact configuration and lifetime budget counters. Broader PM cost-read
surfaces remain in PILOT-05; this bounded runtime exposes Operator controls.

A dedicated singleton backend process owns the private model listener, rather
than binding it in every API lifespan. Local compose opts into the `model-proxy`
profile. Its graceful drain includes margin beyond the maximum provider deadline;
abrupt termination still retains the original dispatch intent and reservation.

Implementation order: provider-free profile/slot/budget contracts and PostgreSQL
proof; AUTH and profile approval/readiness; ART evidence custody with MinIO crash
proof; typed fake provider/proxy; invocation-local Rust socket; selected POST
finalization/retry integration; offline project proof; capped live rehearsal.

Provider output and usage must satisfy the locked bounds. Budget exhaustion,
provider outage, invalid provider response and uncertain delivery are
infrastructure outcomes, never contributor-fixable failures. Private evidence
does not appear in contributor findings or exported provider coordinates.

## Acceptance criteria

- One digest-pinned image uses its invocation socket to obtain a bounded model
  response while provider credentials and the global endpoint remain unavailable.
- Two concurrent distinct calls cannot exceed the project budget; duplicate
  requests yield one provider create and one settlement.
- Provider acceptance followed by response loss, process/lease restart and
  Operator checker retry cannot create a second paid call. A generation-keyed
  mutant must fail this regression.
- A changed prompt, substituted project/Submission/profile, stale lease, expired
  grant, PRE invocation or unentitled image cannot spend.
- Request/response evidence, exact pricing and usage survive restart and replay;
  raw content remains under existing private ART custody.
- Budget/provider failure produces infrastructure recovery and no revision
  consumption. The existing non-model image path retains its behavior.
- Real PostgreSQL proves locking, rollback, settlement and linear upgrades;
  MinIO proves evidence custody. Offline provider tests precede capped live calls.

## Risk and review routing

Risk class: L0. Required architecture/plan, authorization/security, database and
QA review, plus CI/docs for affected changes. Human focus: spend authorization,
ambiguous provider effects, immutable policy identity, owner boundaries and
honest separation of local proof from deployed operation.

## Evidence

Initial source inspection and architecture review identified the stable paid
slot and the need to preserve image ownership. No live provider spend or project
completion is established. The candidate has focused controlled-provider,
proxy crash/replay, private Unix transport, setup/checker shared-account and
hosted Compose contract proof. The retained-data upgrade through
`0060_audit_restore_path` to `0061_model_usage`, PostgreSQL ledger, public
provisioning and actual authorization catalogue adapter require final exact-head
evidence before readiness.
All six composed public profile-to-checker cases pass with real PostgreSQL,
local/MinIO ART and a controlled provider/image boundary: completion, retained
paid results after a lost image reply, concurrent callbacks, and explicit child
recovery after proven no-effect or fully settled provider failure. Database and
MinIO cleanup completed. Final independent reviews and full CI remain required
before readiness. These checks do not establish live provider or gVisor operation.

Implementation review caught and repaired two runtime defects: inherited Compose
profiles unintentionally started the optional listener, and an empty prompt could
reserve budget before local validation rejected it. Profile publication now also
requires the exact registered POST image digest, with independent SQL checks of
canonical profile/budget specification hashes. Regressions cover each boundary;
the final frozen review must assess their composed behavior and current head.

The retained-data upgrade into the model-usage migration exposed a PL/pgSQL parsing failure that
fresh baseline installation did not expose. A discriminating PostgreSQL probe
isolated the unparenthesized CASE expression in the ART binding guard; the
corrected upgrade passes with retained data and owned-database cleanup. Public
HTTP qualification also exposed strict JSON UUID decoding and a prepared
system-Operator scope mismatch. These require the real adapter/API proofs; the
ledger's controlled-authority tests alone cannot establish public usability.

Composed execution also exposed strict Python decoding of the JSON prepared
ART authorization packet. The parser now validates that packet as JSON while
retaining strict integer validation. Both write and binding regressions reject
the original decoder. The composed fixture explicitly declares model evaluation
and supplies the canonical profile reader instead of attaching a model profile
to a static requirement; production policy validation remains unchanged.

That composed path also exposed an inherited ART receipt trigger that required
a checker-run producer even for a paid-call receipt. The migration now admits
only the exact model-call attempt and request/response role while retaining the
existing producer guards. Fresh schema installation, the canonical ART custody
case and retained intermediate upgrade pass with the corrected trigger.

Canonical storage regressions also require malformed or substituted commitment
facts to leave AUTH through its concealed unavailable outcome. Resource
validation now discards the prepared handle before returning that outcome;
changed bytes cannot reach provider I/O. The remaining ART cases cover mixed
binding lineage, rollback/concurrent replay, uncertain puts, revocation,
cancellation and size limits. The adapter composition uses existing owner ports
and passes the protected-base boundary check without adding private-edge debt.

Operator recovery uses the existing authorized checker retry-source read to
discover bounded eligible paid-call candidates. Child preparation retains exact
current Task/Submission custody without requiring a live worker lease; actual
dispatch still requires a fresh current invocation. This closes the otherwise
unusable repair path after a terminal infrastructure failure.

Current owner documentation replaces deny-only generated-output wording with
active paid-call ART custody, lists all nine model permission/action mappings and
describes stable effect records. Existing normalized checker outcomes and
true/false review-policy routing remain unchanged.

Plan review found that existing ART output slots are empty and run/lease-bound;
the stable call evidence reservation above is required. It also required exact
profile selection/readiness checks rather than merely hashing opaque config.
The proposed new CheckerRun state was rejected as unnecessary: call-effect
recovery belongs to the durable slot while existing infrastructure outcomes stay
unchanged.

## Reconciliation

The earlier PILOT-05 hold is lifted only for this required runtime scope. The
user approved a hard US$10 aggregate rehearsal cap; enforce it before live calls.
Review current main and open migrations before allocating a
revision number. Required execution trials and authenticated prior-work context
must still be supplied before final guide activation.

### Active setup-output custody ownership

The setup ART continuation is limited to public setup selector/reservation
types and a MODEL-USAGE-owned resolver, the existing ART generated-output
admission/storage/verification/binding path, its prepared AUTH resource, the
`0061_model_usage` ART constraints/guards, adapter composition, and focused
AUTH/PostgreSQL/MinIO regressions. Its owned paths are
`backend/app/modules/model_usage/api.py`, a new cohesive resolver under
`backend/app/modules/model_usage/`,
`backend/app/modules/checkers/api/output_custody.py`, the existing
`backend/app/modules/artifacts/` checker-output API, custody, binding, service,
schema, model and adapter-composition files,
`backend/app/adapters/model_usage/__init__.py`,
`backend/app/modules/authorization/checker_output_authorization.py`,
`backend/app/modules/authorization/domain/checker_outputs.py`,
`backend/app/modules/authorization/domain/audit.py`,
`backend/alembic/versions/0061_model_usage.py`, and only their focused tests and
schema inventory/fingerprint updates. This continuation does not edit
`backend/app/modules/model_usage/setup.py`, SDK/transport/provider dispatch,
PROJECTS owners, or CHECKERS ORM. It adds only the closed setup-model-output
case; independent trial-evidence types remain outside this branch.

### Exact effect inspection

The shared owner exposes one bounded System Operator read at
`GET /api/v1/operations/projects/{project_id}/model-usage/effects/{effect_id}`.
Fresh `project.model_usage.read` authority reuses the existing
`project.model_budget.manage` permission and binds the request, actor, project
and exact effect before MODEL-USAGE is read. Missing and foreign effects are
concealed. The response contains only the typed stable setup/checker owner,
profile selector, state, reservations/settlement, usage and ART evidence
identities; it never returns provider response coordinates, request/response
bytes, credentials, list access or mutation authority. The action/permission
pair is added to the same linear `0061_model_usage` audit allowlist and the MCP
authorization-context snapshot.

## Historical checker-only review

The following review is retained as evidence for the earlier checker-only
checkpoint. Its head, paths, migration names and verdict do not qualify the
current shared setup/POST candidate. Current exact-head recovery qualification,
full CI and independent security/authorization/database/QA review remain pending.

### Independent QA, test-delta and CI review

Review dimensions: `qa`, `test_delta`, and `ci_integrity`. Review target:
base and merge base `6fa9a9b557fa3ae22c16af67bca25dc868f67b38`, frozen head
`57b3619a22fb23995d663cb747a074e93af9225f`. The start snapshot and the
end-of-evidence snapshot both reported that exact head, `final_ready: true`, and
a clean worktree. This section is the only worktree mutation made after the end
snapshot. The final merge differs from runtime commit `63614e145` only in the
separate terminal-systems PRE change record and roadmap prose; this review did
not repeat the PRE review.

Verdict: **PASS WITH LOW RISKS** for the three review dimensions. No runtime,
test-selection, or required-job defect was confirmed. Finding `QA-CI-001` is a
non-blocking reliability risk in one Rust unit test. Publication remains
separately blocked on Commitrail branch reconciliation: comparison with main
includes the PRE record, while comparison with the PRE head includes the newer
main record. That gate must not be weakened.

### Finding

- **QA-CI-001 — severity Low; confidence high; non-blocking — timing-sensitive
  relay assertion.** Target `57b3619a2`; location
  `external_checkers/workstream-checker-service/src/model_relay.rs:891` and
  `:910`; failure pattern `FP-TIME-BOUNDARY-FLAKE`. The required exact-head
  Rust workspace invocation failed once because
  `distinct_invocations_and_frame_bounds_do_not_cross` did not observe
  `first.finish().failed`. The test gives the relay only 100 ms to accept and
  classify the oversized frame. The exact node passed immediately in
  isolation, passed 30 further isolated repetitions, and the whole 44-test
  workspace passed on rerun. This does not establish a relay runtime failure,
  but a loaded runner can produce a false required-check failure. Use a
  deterministic readiness handshake, or a materially larger deadline while
  retaining a separate elapsed-time bound. Verification should repeat the
  workspace under scheduler load and show the oversized-frame assertion still
  reaches the intended branch.

### Atomic traceability

| Behavior atom | Production owner and changed boundary | Discriminating evidence | Result and custody |
| --- | --- | --- | --- |
| A published POST profile fixes provider, API, model snapshot, token ceiling, pricing and maximum reservation before spend. | `backend/app/modules/checkers/model_calls/profiles.py`, `backend/app/modules/checkers/model_calls/service.py:550`, `backend/app/adapters/checkers/model_provider.py:113` | Exact-head contract, provider-adapter, proxy-orchestration and AUTH selection; source inspection of stored background response creation and strict usage normalization. | Pass in the reviewer-run 76-test selection. This is controlled-provider contract evidence, not a live-provider claim. |
| One stable paid slot survives checker retry; ambiguous provider effects are not recreated; lifetime reserved plus settled spend cannot exceed the project ceiling. | `backend/app/modules/checkers/model_calls/service.py:683`, `:911`, `:1186`; migration `0059_checker_model_runtime.py` | Exact-head owned PostgreSQL/MinIO nodes `minio-retry-retains-paid-effect` and `test_concurrent_dispatch_reserves_one_lifetime_budget`. | Pass. Metadata binds schema `0059`, head `57b3619a2`, owned PG and MinIO namespaces, and successful cleanup. |
| Request and response evidence stays in private ART custody and completion consumes the retained paid effect. | `backend/app/adapters/checkers/model_proxy.py:142`, `:231`, `:276`; ART model-call evidence and binding modules | The exact MinIO composed node exercises real local PostgreSQL and MinIO with the controlled proxy/provider/image boundary; canonical ART, lineage, rollback, currentness and old-tail cases were also inspected in the supplied artifacts. | Exact composed boundary passes. The broader supplied artifacts were produced on the same runtime tree before commit/final-doc merge and are producer-attested rather than self-authenticating exact-head proof. |
| Operator recovery creates a bounded authorized child only after proven no-effect or fully settled failure. | `backend/app/modules/checkers/model_calls/service.py:607`, `:1045`, `:1102`; checker retry source | Exact-head composed `operator-recovers-no-effect`; supplied six-case composed artifact additionally covers settled-failure recovery. | No-effect recovery passes at exact head. Settled-failure coverage is inspected producer-attested evidence and is not promoted to exact-head execution. |
| Prepared checker-output AUTH accepts its JSON packet while still rejecting string-coerced integers. | `backend/app/modules/authorization/domain/checker_outputs.py:213`; `backend/tests/authorization/checker_models/test_contracts.py:141` | Exact-head positive tests plus an in-memory old strict-Python-decoder mutant. | Pass; both WRITE and BIND tests fail at the intended validation assertion under the mutant, before no unrelated setup. |
| A checker image receives one invocation-local relay socket, with no network, a read-only root and a closed response contract. | `external_checkers/workstream-checker-service/src/model_relay.rs:1`, service container arguments, `docker-compose.agent-loop.yml:59` and `:103` | Exact-head Python transport tests, exact-head Rust workspace rerun, exact Compose render, and inspected real-Docker relay proof. | Controlled boundaries pass, subject to `QA-CI-001`. The Docker artifact proves Docker only; it is not gVisor qualification. |
| CLI and MCP surfaces preserve the public model-operation and authorization vocabulary. | `cli/internal/api/checker_models.go`, `cli/internal/api/checker_operations.go`, MCP contracts and access-read tests | Inspected CLI operation artifact (including Go build/vet) and corrected MCP contract artifact, plus actual-backend permission/role evidence supplied by the producer. | Pass within artifact custody. GitHub authentication was invalid, so no hosted check result was available to independently bind these runs to the PR. |
| The changed cross-cutting surface selects all required backend, external checker, MinIO, CLI, MCP and semantic-lane jobs. | `backend/scripts/select_ci_scope.py:121`, `backend/scripts/test_lane_catalogue.py:485`, `.github/workflows/backend.yml` | Reviewer executed the selector on the exact base/head pair; it returned `unknown_or_cross_cutting_path` with every required boolean true and the full lane matrix. Catalogue ownership and the final required-job aggregator were inspected. | Pass. No hosted workflow was run during this review. |

### Evidence executed by this reviewer

- `/dev/shm/model-qa-exact-head-minio-v5.log` and `.json`: three selected
  tests passed against a fresh owned PostgreSQL database and MinIO namespace;
  tree, migration head, provisioning, probe and cleanup fields are present.
- `/dev/shm/model-qa-exact-head-pure.log`: 76 selected contract, runtime,
  proxy, provider, transport and authorization tests passed.
- `/dev/shm/model-qa-parser-mutant-exact.log`: the old decoder produced both
  expected failures, killing the targeted regression mutant.
- `/dev/shm/model-qa-exact-head-rust.log`: the first workspace run exposed
  `QA-CI-001`; `/dev/shm/model-qa-exact-head-rust-retry.log` passed the isolated
  node, 30 additional repetitions passed, and
  `/dev/shm/model-qa-exact-head-rust-rerun.log` passed the workspace rerun.
- Exact-head Compose rendering passed the proxy/socket/network/read-only mount
  assertions. Exact base/head CI selection produced
  `/dev/shm/model-qa-ci-scope-*.out` with full scope.
- `/dev/shm/model-qa-end-target.json` records the clean final evidence
  snapshot before this required review-record write.

### Inspected evidence and remaining limits

The review also inspected the supplied composed, ledger/recovery, signed-public,
canonical ART, old-tail, retained-upgrade, provider/proxy, output-contract,
CLI, MCP, Rust and real-Docker artifacts. The original old-tail artifact was
excluded because its database was cleaned too early; only `tail-v2` was used.
Test names and counts were not treated as runtime proof: assertions, setup
completion, metadata custody and owner code were inspected. No live provider
call, hosted CI run, gVisor run, or complete real-project execution occurred,
so this verdict makes none of those claims.
