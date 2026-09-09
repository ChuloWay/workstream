# Chunk Contract: WS-POL-003-04B - Live Unified Setup Cutover

Disposition: Planned. Dependencies: complete 04A/04A3/04A2 and AUTH-12I/12J/12B2,
plus POL-04B1 automatic request custody and [ARCH-04A consolidation](../../../WS-ARCH-001/WS-ARCH-001-04A.md). Risk: L1.

## Goal

Make the unified setup service the sole live inference path and persist the
complete compilation plus canonical sufficiency/artifact-policy projections.

## Allowed files

Project setup-service/queue/composition, existing projection/finalization
public ports and explicit AUTH-12I/12J/12B2 adapters, focused tests,
specifications, and WS-POL-003 docs. Do not rebuild completed projections.

## Not allowed

Approval/pre effective mutation, post canonical projection, checker execution,
compatibility routing, or a second provider attempt/key.

## Acceptance

- Live orchestration invokes only `compile_project_guide`.
- Sufficiency and artifact-policy projections each consume fresh action-bound
  PREP in their own atomic transaction. Each PREP binds the immutable
  compilation and accepted-result hashes plus its exact sufficiency or
  artifact-policy component hash.
- Delete all three superseded model methods/prompts and their consumers/tests;
  no disabled retained implementation or fallback exists.
- Complete replay returns canonical outputs with zero provider calls.
- Verified source readiness automatically requests the first run. Bind one immutable attempt,
  use AUTH-12J for the two projections and AUTH-12B2 for finalization. Reuse
  the exact finalizer; do not mutate its closed setup row or mint a parallel
  completion receipt. Manager correction/rerun uses a new generation through POL-05; no arbitrary same-generation rerun is exposed.
- Remove superseded model calls physically in this PR; no deferred deletion.
- Consume the CHECKERS-owned public catalogue snapshot, not PROJECTS private
  registry imports or copied constants. Existing sparse-catalogue results are
  never enriched in place to make them approval-eligible.
- Update the PROJECTS input projection/validation adapter to consume that
  single current public contract, including supported typed binding parameters;
  do not keep the old blanket parameter rejection while advertising new
  capability schemas. Reuse canonical validators and prove parity without
  rebuilding the completed attempt/finalization state machine.
- A database `provider_idempotency_key` alone does not prove provider recovery:
  the current adapter does not accept that key or expose retrieval/resume.
  Unknown provider outcomes remain blocked and cannot trigger another call
  under a fresh key. Claim recovery only after a typed ADR-0014 capability
  demonstrably recovers that same provider operation. This cutover must expose
  the blocked outcome honestly and never promise automatic recovery that the
  provider contract cannot supply.

## Verification and review

Real PostgreSQL/Celery/API cutover, static reachability, one-attempt replay,
projection/finalization atomicity, hosted coverage, and impact-routed reviews
(architecture, security, QA, product/operations). Human focus: clean
one-call cutover with reusable, not borrowed, projection authority.

## Runtime configuration and terminal behavior

Use ADR 0014: `ProjectGuideAgentRuntime` extends the shared external adapter
contract and is constructed by `ExternalServiceAdapterFactory[ProjectGuideAgentRuntime]`
with explicit composition-root registration. OpenAI Agents SDK is the installed
runtime adapter, not the domain architecture. Runtime selection, model/provider
configuration and instructions are separate validated configuration concerns.
Switching runtime must not rewrite PROJECTS, Celery or policy behavior. Remove the
old hard-coded factory and affected callers/tests; do not retain an alias or
install speculative alternative runtimes. Instructions must be independently
configurable and their exact content/configuration must be bound to each immutable
attempt together with runtime/model identity. A changed deployment configuration
cannot silently alter an in-flight attempt. No credentials enter evidence.

Automatic compilation persists findings and draft pre/post policy proposals;
the worker returns their bounded completion receipt. Authorized PM proposal
visibility remains POL-05; this chunk does not claim that read surface delivered.
Compilation stops there;
insufficient guide results also terminate with findings. It never approves or
activates a guide. Manager correction/manual rerun is POL-05's new-generation
operation, using this same runtime and executor. No mode setting is introduced.
The superseded operator autostart flag must not leave manual-mode or parallel
pipeline code in the affected source-generation/continuation modules.

## Current-source implementation plan

- Initiative: WS-POL-003
- Intended merge outcome: one automatic, authorized unified guide compilation
  replaces the three separately invoked setup agents and stops at draft output.

Current main includes POL-04B1. `guide_mutation_service.py` still conditionally
creates setup rows, `guide_setup_continuation.py` dispatches the separate
sufficiency worker, and `workers/project_setup.py` runs sufficiency followed by
artifact-policy inference. `ProjectService` retains another sufficiency method
and post-submit inference/continuation. The runtime exposes all four methods.
The unified orchestrator, component projections and finalizer already exist.

Implementation order:

1. Trace and remove each inference-only consumer, route, prompt and test. Retain
   policy CRUD, diagnostic reads, canonical validation, authorization and
   immutable historical evidence wherever shared. Remove the old manual
   sufficiency-dispatch route; POL-05 owns authorized correction/new generation.
   Remove approval-triggered post-submit inference without replacing it with
   premature post-policy approval or projection.
2. Extend the existing runtime port with ADR 0014 adapter identity and compose
   it through the shared typed factory. Define one validated, credential-free
   configuration for runtime selection, model/provider, instructions and bounded
   run limits. Persist its exact immutable snapshot on the existing attempt in the request
   transaction. Include it in canonical input identity, but exclude it from the
   provider user prompt; use its instructions as instructions. Preserve semantic
   agent/instruction versions. Existing retained rows receive no invented
   backfill and cannot execute without configuration. Require configuration on
   new inserts and forbid later changes in PostgreSQL and application guards.
   Reconstruct from that snapshot, never from changed deployment settings.
3. Make source setup creation unconditional. Preserve verified-source readiness,
   deterministic queue claims and retry handling. Replace the existing worker
   with request_automatic -> existing executor -> two existing projection ports
   -> existing finalizer. Each authority belongs to its own existing transaction.
   Worker arguments must match the persisted project/guide/source/generation
   before request authority or any provider invocation. A fast worker may
   normalize its exact persisted dispatch_pending claim to queued/queued before
   projection; match the full tuple and deterministic task ID, preserve all other
   setup fields, and prove publisher acknowledgement cannot overwrite terminal
   work. Rename the existing queue/task symbols for unified compilation without
   an alias, preserving retained task identity values where custody requires it.
4. Return bounded terminal output for sufficient, insufficient, invalid and
   uncertain results. Replay completed work without constructing/calling a
   provider. Never rewrite finalized setup rows or schedule another model call.
5. Replace obsolete test coverage with behavior proof for the unified flow,
   then run focused checks, hosted PostgreSQL/Celery/API/coverage evidence and
   impact-routed review. Update roadmap/navigation in this same implementation.

Additional affected paths: `backend/app/interfaces/project_agents.py`,
`backend/app/core/{config,project_agents}.py`,
`backend/app/adapters/project_agents/`, affected PROJECTS router/source/sufficiency/
submission-policy/service modules, queue task identity and Celery registration,
AUTH action dispatch registrations for removed entry points, and exact affected
schemas/migrations if configuration custody requires them. Existing audit facts
and retained output rows must remain interpretable and immutable. Test fixtures,
API/route inventories, lane/ownership inventories and structural-debt snapshots
may change only to match the actual replacement, never to weaken gates.

Required reviews: architecture/reuse (shared consumers and typed composition),
security (source/service authority, replay and immutable configuration), QA/test
delta (behavior replacement and discriminating failure tests), product/docs
(terminal outputs and remaining manual workflow), CI integrity (test removals,
registrations and full hosted custody). Human focus: old inference is physically
removed; one run proposes both phase policies; no approval or extra model call.

Planned proof, not yet execution evidence: configuration changes independently
alter attempt identity; unsupported runtime/provider fails before dispatch;
wrong worker tuple and revoked service perform zero provider calls; duplicate
callbacks race to one attempt; sufficient/insufficient outputs finalize exact
persisted pointers; interrupted projections replay without inference; unknown
provider outcome remains blocked; removed routes/methods cannot execute; shared
policy mutation, locked lineage and retained-data protections still hold.

Plan review decisions: configuration custody belongs to the existing attempt,
not an additional table or registry; hash-only configuration would lose exact
reconstruction evidence. Shared mutation services remain for non-inference
operations. Post-submit binding validation already delegates to the canonical CHECKERS
validator; preserve it. Pre-submit binding validation currently checks only
parameter names; reconcile its typed ownership and proposal-value validation
against the canonical policy contract, with no duplicate rule schema.

The existing `approve_submission_artifact_policy` boundary must reject a
`unified_compilation` draft before any effective/pre-policy writes or enqueue,
until POL-05 provides the complete approved workflow. Preserve shared AUTH-12J
actions `project.guide_sufficiency.run` and
`project.submission_artifact_policy.derive`; these authorize deterministic
projections even after their separate inference callers are removed.

Verified readiness stays with ART verification callbacks and the existing
guide continuation scanner through `GuideSetupPreparationService`; missing
material stays eligible for continuation, without reserving a provider attempt.

The runtime snapshot is a closed typed value, never a Settings dump: adapter
capability/provider identity, model ID and safe behavior settings, instruction
identity/version/exact content/SHA-256, and bounded run limits. Credentials,
secret references, headers and signed endpoints are excluded. PostgreSQL checks
its shape/hash and immutability. The canonical input hash (already present in
AUTH facts and provider-key derivation) binds its full canonical value. Provider
user-prompt serialization excludes the snapshot. Only a RESERVED attempt may
construct/validate its selected runtime, before the one-shot dispatch fence;
accepted, persisted, invalid and uncertain replay construct no runtime.

The worker normalizes only dispatch_pending/current_step=dispatch with its exact
persisted task/tuple to queued/queued; all other data stays unchanged. Terminal
replay follows existing authority/custody paths and does not normalize or reopen
setup rows. Test early delivery with a barrier around publisher acknowledgement.

The worker must compare its actual bound Celery delivery ID, not merely a
payload or recomputed ID. Before request/executor/configuration/projection work,
the coordinator looks up exact existing finalization custody and invokes the
existing finalizer replay with fresh AUTH; this includes sufficiency_blocked
redelivery, which cannot enter the executor source-state guard.

The existing authorized latest-setup diagnostic read projects current immutable
attempt custody onto its response without changing setup rows: reserved, accepted
but not persisted, invalid-terminal and provider-outcome-unresolved are explicit
compilation statuses. Invalid output exposes the bounded failure code and terminal
timestamp; uncertainty exposes a stable unresolved code with no invented finished
timestamp. Finalized generations retain the exact finalization outcome and
pointers. Worker results use the same bounded classification. Neither a read nor
redelivery may reopen a finalized row, fabricate an outcome, or enqueue another
provider call. Read authorization remains the existing diagnostic-read action.

## Discriminating verification cases

- A real verified-source control and each wrong worker selector (including actual
  bound delivery ID) prove denial before request/audit/attempt/provider effects.
- Pause publisher acknowledgement while an eager worker completes the exact
  claim; resume acknowledgement and compare all terminal pointers/timestamps.
  Two concurrent deliveries still admit at most one provider invocation.
- Replay finalized blocked and ready generations through fresh finalizer AUTH
  before any runtime/configuration construction; no new audit or product writes.
- Inject failure after persistence, after sufficiency, and after both projections;
  restoration completes the missing effects under current phase authority with
  one total provider invocation. Revoke service authority separately at each phase.
- Invalid schema/unsafe output and provider uncertainty retain truthful bounded
  diagnostics; reads and redeliveries neither rewrite setup nor reinvoke runtime.
- New missing/malformed/oversized/hash-mismatched snapshots fail direct SQL;
  configuration mutation fails; retained missing configuration remains unchanged
  and unavailable for live execution. Deployment changes cannot replace snapshot.
- A valid unified projected draft hits the named approval denial before writes;
  an otherwise valid manual-policy control retains its required behavior.
- Replace inference-only tests, keeping mixed CRUD, lineage, source-usage,
  warning-acknowledgement, correction-audit and immutable-policy protections.
  AST/route/registry checks prove the three methods/prompts and old tasks/routes
  are absent, rather than monkeypatching symbols that should have been deleted.

Pre-submission projection ownership moves to CHECKERS public API, replacing the
current CHECKERS-to-agent-interface import. The unified result validator keeps
cross-component equality: proposal-backed parameter names are the intersection
of the selected definition's policy_fields and SubmissionArtifactPolicyProposal
fields. Empty parameters select the capability against that separately hashed
proposal. Nonempty parameters require the complete relevant field set and exact
canonical JSON/type equality with the validated proposal; platform-owned fields,
extra/missing fields and conflicting values fail. Parameters never form another
executable policy or feed the compiler independently. This reuses the existing
proposal schema without a parallel checker configuration model. Test int/float,
tuple/list normalization, packaging/storage, unsupported fields and conflicts.

One PROJECTS-owned coordinator reads its own exact persisted attempt/result and
finalization to branch blocked versus draft-ready. The worker only composes and
calls it. No private ORM/result read is added to Celery and no new public receipt
field exists solely for the branch.

### Live provisioning guard reconciliation

The first real automatic-worker test exposes a pre-cutover SQL assumption:
`guard_project_guide_compilation_insert` requires the literal issuer
`workstream-internal` and subject `workstream.project.setup`. The controlled
service-provisioning API instead binds the configured verifier issuer and an
operator-supplied opaque subject. AUTH resolves that exact stored active link;
its fixture-only issuer must not become another provisioning implementation.

Within this cutover migration, replace those two literal checks with the existing
exact provisioned actor/link custody: keep the compilation's exact actor and
identity-link IDs, their relationship, active service kind/status, fixed
`workstream.project.setup` profile identity, and exact consumed execution event,
action, permission, resource and digest. Do not add an alternative issuer list,
change provisioning, rewrite retained evidence, or broaden service membership.
Prove a controlled-provisioning link can persist; wrong actor/link, revocation,
wrong service and forged/mismatched authorization evidence still reject.
This repair requires focused security/architecture review in addition to the
cutover's implementation reviews.

The same repair includes `guard_project_guide_setup_finalization`, which also
requires the literal external subject. Replace that subject predicate with
active actor and active link checks while retaining exact actor/link IDs,
relationship, service kinds, fixed service identity and every existing finalization
event/action/permission/resource/request/correlation/digest predicate. Both guards
must follow controlled provisioning; fixing compilation alone leaves finalization
unusable. Test ready and blocked finalization using an opaque provisioned subject,
and direct rejection for inactive actors/links or wrong actor/link custody.

### E2E proof boundary after immutable draft finalization

The existing API drill interleaves live guide setup with a test-only post-policy
bridge that rewrites the same setup row. Replace that arrangement with two
distinct guides in the existing isolated project. The live guide proves the real
unified worker, complete draft stop, read/CRUD authority, denied unified approval
and immutable finalization/replay. It never feeds task activation. The second
guide belongs to one explicitly isolated locked-contract fixture for downstream
active-guide/task/submission/review HTTP proof. Consolidate the existing activation
seed and post-policy fixture under that boundary; use current canonical owners,
never old inference methods or a product alternative path. Fixture construction
must refuse finalized input and must not mutate the live guide or any finalization
receipt. Preserve all downstream lifecycle and authorization assertions. Fixture
seeding does not prove POL-05 approval or AUTH-12H public guide activation.

Use version `unified-draft-proof-v1` for the live guide and retain `v1` for the
fixture guide so task-lock assertions identify the latter explicitly. Build the
fixture guide's report and ART source usages through the canonical request,
execution and projection owners with the same deterministic typed-factory runtime;
omit only finalization in fixture composition, without adding a worker mode.
Create and approve a separate manual artifact policy through the real API, compile
the post policy with its canonical compiler, and seed exact setup/activation
prerequisites within `seed_active_guide_for_pre_12h_e2e`. Require no finalization
row before that fixture transition and assert downstream reads and task locks
refer to the fixture guide.
