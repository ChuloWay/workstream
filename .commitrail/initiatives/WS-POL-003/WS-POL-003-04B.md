# POL-04B — Live unified setup cutover

- Durable disposition: Planned

Dependencies: complete 04A/04A3/04A2 and AUTH-12I/12J/12B2,
plus POL-04B1 automatic request custody and [ARCH-04A consolidation](../WS-ARCH-001/WS-ARCH-001-04A.md). Risk: L1.

## Current runtime intent — agent-led document investigation

The creator's clarified intent supersedes this record's earlier tool-free,
single-prompt, single-model-turn execution assumptions. Those assumptions do
not satisfy project guides comprising many documents larger than model context.
The existing implementation requires reconciliation before this boundary is
complete; successful single-request inference alone is not its acceptance proof.

One authorized setup attempt owns an agent run with multiple model/tool turns.
Worker replay must not start a duplicate agent run. That fence must not prohibit
legitimate calls within the original run. Unknown execution outcomes remain
explicitly unresolved until recovery of that same run is proven.

The agent receives a reference to the immutable, authorized guide snapshot and
a bounded inventory, then chooses which documents/ranges to read or search.
Tools must resolve through Workstream-owned artifact/material ports: S3 remains
behind ArtifactStore, and any physical ephemeral workspace uses
ArtifactScratchManager. Credentials and unrestricted bucket/host access are not
model inputs. Required document coverage, exact citations, extracted-content
omissions and unread material must be visible; a search hit or summary is not
proof that the guide was completely understood.

The runtime needs working notes and bounded context management so gradual reads
do not merely accumulate into another oversized prompt. Runtime harness,
model/provider, trusted instructions, tool permissions and execution budgets
remain separate configuration concerns. Study OmniCoreAgent and LangChain Deep
Agents as concrete harness references; this clarification does not select a
replacement library merely by naming it. Replace superseded affected paths and
tests together rather than retaining a one-shot fallback.

The output remains sufficiency findings plus distinct pre/post policy proposals,
followed by the existing deterministic validation and authorized persistence.
Insufficiency ends with findings; a ready proposal still waits for manager
review/correction/approval. No approval or checker execution authority moves into
the agent. The amended bounded file list, tool contracts, context/recovery
semantics, tests and focused architecture/security review must be settled before
implementing this replacement.

Read-only discovery establishes that originals already reside behind
ArtifactStore, while ART stores canonical extracted content in one PostgreSQL
row per source item. Current preparation reads whole items (32 MiB input and
4 MiB canonical output limits), then PROJECTS loads the entire guide into a
12 MiB aggregate snapshot. A tool wrapper over that aggregate would preserve
the wrong memory boundary. The revised corpus must load individual items or
segments and avoid assembling the whole guide. Existing canonical rows are a
possible initial backing; moving them into S3 is a separate storage decision,
not a prerequisite merely to expose document tools. Image extraction currently
provides structural facts without OCR or visual understanding.

Define actual segment/range semantics before relying on evidence ordinals, and
validate final citations against the exact content returned to the run. Tools
must return server-minted references so the model need not invent hashes or
lineage. The installed OpenAI SDK supports tool loops and Responses context
compaction; its default tool-output trimmer counts user-message turns, which
alone does not bound one long autonomous run. Context reduction must be tested
inside a single run. OpenAI remains the first candidate adapter; a Deep Agents
adapter is optional and must not duplicate Workstream's tool or policy owners.

References inspected:
- [OmniCoreAgent](https://github.com/omnirexflora-labs/omnicoreagent)
- [Deep Agents context management](https://docs.langchain.com/oss/python/deepagents/context-engineering)
- [Deep Agents storage backends](https://docs.langchain.com/oss/python/deepagents/backends)
- [OpenAI SDK agent loop](https://openai.github.io/openai-agents-python/running_agents/)

## Intent

Make the unified setup service the sole live inference path and persist the
complete compilation plus canonical sufficiency/artifact-policy projections.

## Bounded change

### Allowed files

Project setup-service/queue/composition, existing projection/finalization
public ports and explicit AUTH-12I/12J/12B2 adapters, focused tests,
specifications, and WS-POL-003 docs. Do not rebuild completed projections.

### Not allowed

Approval/pre effective mutation, post canonical projection, checker execution,
compatibility routing, or a second provider attempt/key.

## Acceptance criteria

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

## Risk and review routing

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

Pre-change base `fa49529b` includes POL-04B1. `guide_mutation_service.py` still conditionally
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
fixture guide's diagnostic report through the real manual API. Within the guarded
isolated fixture only, create a separate fixture-owned verified report with exact
prepared ART material hash/byte count, generation and complete extraction usages.
Preserve the original human diagnostic; neither report impersonates an agent.
This fixture has no compilation, projection operation or finalization. Create,
update and approve its manual artifact policy through the API, compile the post
policy with its canonical compiler, and seed exact setup/activation prerequisites
within `seed_active_guide_for_pre_12h_e2e`. Require no compilation ownership before
seeding and assert downstream reads and task locks refer to the fixture guide.
The live guide independently proves immutable compilation and finalization.
No setup trigger is disabled to prepare the downstream guide.

### Review-driven recovery and admission safeguards

The same source-state predicate governs automatic admission, request material
resolution and deterministic projection. Nonempty outputs, errors or timing, or
an inconsistent ART continuation pair, reject before request or provider work.
After existing-finalization replay, an attempt without its owned runtime snapshot
is unavailable even if its compilation was already persisted.

The existing Beat continuation reclaims stale queued deterministic deliveries
when bounded Celery retries exhaust. It republishes the same task and generation,
retaining attempt/provider custody; invalid or uncertain provider outcomes,
existing attempts without runtime configuration, and finalized work are excluded.
The shared eligibility predicate belongs to the queue owner; continuation consumes
it without a reverse dependency. Every recovery publication rechecks eligibility
under the setup lock, including pending claims and absent task pointers. Only a
fresh explicit initial claim uses its already-owned publication authority.
Configuration repair can then start the still
uninvoked attempt, while accepted/persisted recovery never reinvokes the provider.
Typed runtime registration reuses the project-agent capability adapter root.
The delivery port's JSON result shape remains an explicitly bounded low-risk
review observation; existing frozen finalization and diagnostic owners determine
its contents, and Celery serializes the result without granting authority.

The uncalled role-only `ProjectService` report-creation and warning-acknowledgement
implementations and their unused validation wrapper are removed; the
prepared-authority mutation service owns both operations and reuses the canonical
sufficiency payload validator.
Warning acknowledgement records covered human provenance without resetting or
requeueing setup. Its own mutation no longer changes the stale-output identity,
so an identical request can replay under fresh authority; setup/report lineage
and late-conflict rollback checks remain intact. Shared task fixtures consume
the setup created by the source API instead of inserting a duplicate generation.

Retired sufficiency and submission-policy inference execution fences and
fixed-service inference replay tests are removed with their owners. The remaining
submission-policy fence had no product consumers; its isolated fence-test modules
and fixture are removed, with exact lane catalogue updates. Required one-attempt/concurrency protection
is proved by `test_concurrent_live_deliveries_share_one_provider_and_finalization`,
`test_concurrent_automatic_callbacks_share_one_attempt`, and the authorized
execution/concurrency tests. AUTH-12J projection tests retain exact service,
source, task and component custody; human policy replay tests remain unchanged.
Current submission-policy service/repository replay accepts human create/update
only; the unused service namespace, reserved execution binding and claim option
are removed. Existing nullable stored fields are retained, and current human
reservation/completion explicitly exclude non-null service custody. AUTH-12J
projection contracts and persisted evidence are unchanged. Alias-aware shared
AST proofs detect imported factory aliases, direct concrete runtime calls and
aliased finalization calls in the exact worker context. Finalized receipt recovery
exclusion is tested across all queue shapes using isolated adversarial setup
fixtures, restoring production guards before dispatch and preserving the receipt.
The shared project repository removes four zero-consumer methods from superseded
inference: agent-policy lookup, post-policy upsert, latest rejected-policy lookup
and the unlocked policy list replaced by the authorized locked list. Current
by-ID reads and retained correction-history listing stay intact. Consumer tracing
covers all backend source/tests before removal; no stored rows are deleted.
The two older migration guards are invoked directly in real PostgreSQL Alembic
operation contexts, so the newer runtime-custody guard cannot mask their proof.
Hosted installations include the configured agent runtime extra.

### Superseded executable consumers

Trace the old setup helper through the June `backend/scripts/week2_api_e2e.py`
drill and `examples/terminal_benchmark/terminal_benchmark_api_e2e.py`. Neither
is current CI or canonical runtime proof; both still call removed setup paths,
and the week2 caller was already incompatible with the current helper signature.
Remove these obsolete executables and their current command claims. Retain the
canonical API drill's database/environment guard tests once. Required checker
and task behaviors remain in `tests/test_checkers.py`, `tests/test_tasks.py` and
the hosted canonical API drill: intake non-durability, packet/integrity guards,
warning routing, blocked task setup, retry supersession, revision/resubmission,
worker concealment, immutable locks and audit evidence. Remove only the obsolete
file selectors in stale-wording guards; preserve the same rules on active files.
Historical validation notes remain explicitly historical, not runnable proof.

### Existing AUTH composition root

Reuse `app/adapters/auth/__init__.py`, which already composes both projection
authorities and setup finalization. Add only the fixed-service request/execution
context composition there; the worker imports this existing composition root
instead of AUTH private implementations. Remove its superseded private prepared
edge from the AUTH ledger. This decreases inbound debt and introduces no new
factory, permission, fallback or product-service dependency. The CHECKERS public
pre-submit projection types remain dependency-safe; its existing private catalogue
owner builds the snapshot at composition, without a public-to-private import.

The protected module boundary also forbids new worker private PROJECTS/CHECKERS
edges. Use existing `app/adapters/projects/__init__.py` to construct the same
coordinator/executor/projections from injected ports, exposed through a public
delivery protocol and bounded stale-delivery error. Existing CHECKERS adapter
composition builds the pre capability snapshot; use the already-public current
post catalogue directly and remove the redundant PROJECTS wrapper. No second
orchestrator, new registry, validator relaxation or private-edge allowance is
introduced. Remove retired worker edges from both durable debt inventories.

## Test replacement and retained safeguards

This cutover deletes tests whose only subject was a removed inference method,
its prompt, queue continuation, mutable setup-service custody or removed HTTP
dispatch route. It retains the shared manual CRUD/approval, warning
acknowledgement, lifecycle and immutable evidence tests. Replacement proof:

| Removed implementation-specific proof | Required behavior retained by current proof |
|---|---|
| Three runtime methods, prompts and hard-coded model factory | `test_agent_runtime.py`: closed unified output, separate configuration, SDK single call/retries disabled, timeout/error sanitization and both caller/internal cancellation |
| Separate pre/post dispatch and mutable worker progress | `test_live_worker.py`, `test_live_cutover_postgresql.py`: actual task ID, every stale selector, one invocation, ready/warning/blocked endings and safe invalid/uncertain diagnostics |
| Old service report/policy adoption and continuation replay | Existing AUTH-12J projection PostgreSQL tests plus live crash-boundary/revocation tests preserve exact source usage, transaction rollback and one-attempt recovery |
| Approval/correction-triggered inference | Live unified approval rejects with zero effective/pre-policy/audit writes; retained correction tests preserve supersession/audit without enqueuing |
| Hidden-only worker reachability assertions | Syntax-aware tests require the sole PROJECTS coordinator to call both projection ports; finalizer remains free of provider/projection/approval calls |
| Week 2 and terminal example executables | Current checker/task suites retain their required lifecycle and authorization cases; the canonical HTTP drill separately proves live draft finalization and fixture-owned downstream task lineage |

The lane catalogue includes every new test module and removes only the deleted
dispatch module. The supplemental sufficiency coverage command drops its three
removed setup-service selections; the remaining mutation family and both
90-percent file floors remain enforced. The seven-lane complete inventory,
zero-skip/deselection checks and global/subsystem coverage gates remain intact.

Runtime configuration migration adds no invented configuration to retained
attempts. They remain immutable evidence and cannot execute with missing
configuration. Business policy versions, semantic result identifiers and
retained deterministic task IDs remain required lineage, not parallel code.
Remaining shared AUTH action IDs are consumed by the current deterministic
projection owners and therefore are retained.

## Evidence

The required proof is one provider invocation across PostgreSQL replay and
concurrent delivery, fresh authority at each phase, exact projection/finalization
custody, strict runtime configuration guards and physically absent superseded
paths. The named tests and replacement mapping above identify those boundaries.
The PR owns executed command results, exact-head reviewer freshness, hosted
coverage and remaining verification; this record does not duplicate transient
CI or approval state.


### SDK parser outcome correction

The adapter translates `ModelBehaviorError` raised by the SDK output parser
into sanitized `schema_invalid` output, including unsafe text rejected there.
A per-run parser rejection flag preserves the native SDK error boundary; a
private result marker lets the public adapter construct the domain error only
after payload-bearing SDK frames and exception chains have been discarded.
Tests inspect traceback locals and exception chains with redaction enabled and
disabled. Classification does not depend on exception causes removed by redaction. Other SDK/provider failures remain unresolved. The tested SDK is pinned
to 0.22.2 in package metadata and the lockfile so local and hosted installs agree. Tests must exercise the installed structured-output parser,
then prove committed invalid-terminal custody and replay without another call.
The affected adapter/tests, dependency metadata/lockfile, native environment
example/README instructions and removed obsolete Compose setting remain within this repair;
authorization, lineage, retry limits and evidence retention do not change.
The environment example uses the current independent runtime/model/instruction
settings and documents loading credentials into both API and Celery worker processes, with Beat enabled for local recovery.
Focused security, QA/test-delta and architecture/docs review cover the repair.
