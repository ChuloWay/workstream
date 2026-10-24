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
The linear `0062_model_usage` migration follows main's
`0061_project_catalogue_read` (which follows `0060_audit_restore_path`);
intermediate upgrades retain main data and leave one head.

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

Setup requests disable provider-side storage. A known provider ID is therefore a
durable observation, not by itself a recovery source: if the process is lost before
response ART custody, the exact effect remains uncertain and keeps its reservation.
Only retained verified response evidence or an authenticated provider/no-effect
proof may settle or release it; an Operator read cannot manufacture certainty.

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

The canonical parent schema installs linearly through
`0060_audit_restore_path`, `0061_project_catalogue_read`, and
`0062_model_usage`; its measured public-schema digest is
`d14a06c088aae0e8876bebb637a7b3fb0c19344f8cc4fdfd31aa2c1a47348593`.
The migration and owner guard retain immutable prepare/dispatch/terminal
authority facts instead of reconstructing them from a later worker lease. A
real PostgreSQL selection passed 20/20 checker and setup authority cases,
including every foreign digest branch, a renewed legitimate checker grant,
successor-run attachment to one paid effect, known-failed settlement, and stale
or reused authorization rejection. Independent QA reran seven discriminating
authority/renewal cases and killed a mutant that restored latest-grant lookup.

The controlled composed boundary has separate current evidence for its ordinary
and recovery paths. Four ordinary completion, retained-result and concurrent
callback cases passed with real PostgreSQL and MinIO. The concurrent callback
is held before first response publication so the second caller must recover the
known provider identifier; both replies use one effect, response receipt and
settlement. Proven no-effect and fully settled failure each passed their public
Operator recovery journey with exactly one additional pre-authorized dispatch,
while the original effect and evidence remain immutable. Database and MinIO
cleanup completed for each owned run. The setup handler separately proves that
two simultaneous resumptions share one durable paid effect and provider create;
the scripted setup coordinator convergence test is intentionally not represented
as paid-effect deduplication.

Private request/response evidence uses the existing generated-output ART path.
Manual setup correction dispatch passed five public HTTP/PostgreSQL profile
selection, replay and denial cases: a created attempt remains pinned to profile
version 1 even after version 2 is published. Actual MinIO tests passed 11/11
transport-timeout, outer-cancellation, precondition and malformed-observation
cases after the S3 adapter was made to join its single SDK body consumer before
returning; no source reads continue after timeout cleanup.

The current hosted configuration passes 38/38 focused tests after reconciling
main's cached proof-image policy with the private model-proxy image identity.
An actual parent Rust relay image previously passed a controlled Docker smoke
with no network, read-only input/root filesystem, only the invocation socket
exposed, the global grant concealed, and owned image/container cleanup
confirmed. Static API/lane, CLI, MCP, Ruff, behavior ownership and structural
debt checks pass their affected selections. These are controlled local proofs,
not hosted deployment or composed gVisor qualification.

Independent QA issued a PASS for the reviewed MODEL runtime atoms and the
discriminating PostgreSQL/composed callback tests. Attempts to obtain the
separate security-review verdict ended in platform review errors, so no security
sign-off is claimed. Current hosted CI, retained-data qualification on the
stacked migration, and remaining independent review gates must complete before
the draft is marked ready. No live provider call or paid spend occurred. The
historical setup spend remains unreconciled; deployment and any paid rehearsal
remain disabled until the Operator supplies the externally reconciled remaining
allowance within the existing US$10 aggregate ceiling.

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
`0062_model_usage` ART constraints/guards, adapter composition, and focused
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
`backend/alembic/versions/0062_model_usage.py`, and only their focused tests and
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
pair is added to the same linear `0062_model_usage` audit allowlist and the MCP
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


Manual guide correction dispatch must select the same immutable project model
profile as automatic setup before request facts and runtime hashes are locked.
The real public correction regression exposed a missing selection: the worker
correctly refused the already-created attempt because its configuration had no
profile. The repair shares selection in the existing PROJECTS request-input
module, supplies the MODEL-USAGE read port at composition, and preserves an
existing attempt's exact configuration on replay. A later Operator profile
publication must not change that attempt. This owns the affected correction
dispatch, live coordinator, request-input and composition files plus their
existing public and boundary tests; it adds no new route or model call.

An S3 write timeout may cancel the pinned aiohttp request while its separately
scheduled body-writer task is still advancing the single committed scratch
stream. Recovery must own that task to quiescence before it validates, observes,
or releases the sealed source. This bounded repair owns only the S3-compatible
adapter and its focused tests: it must reproduce the actual asynchronous-writer
race, prevent concurrent advancement and post-return source access, preserve
the source's finite scratch deadline, and never accept an incomplete source as
a replay. A canceled partial write is unavailable/uncertain and remains
recoverable only through the existing complete provider-object observation;
increasing transport timeouts is not a correctness fix.

The pre-repair probe used the pinned aiohttp 3.14.3 writer against a local
stalled HTTP endpoint and deterministically produced the qualification failure:
request timeout followed by `anext(): asynchronous generator is already
running`. With explicit consumer ownership, the same probe joins the writer and
classifies the still-incomplete body unavailable. Eleven focused S3 cases pass
against MinIO, covering transport timeout, outer caller cancellation, no source
access after return, early 412 replay, missing replay, malformed sealed bytes,
unconsumed success, and independent uncertain-write observation.
