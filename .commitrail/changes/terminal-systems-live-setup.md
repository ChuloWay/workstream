# Terminal Systems — live setup qualification

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Produce a useful, typed and reviewable guide-setup specification from the original guide, including correct checker classification and platform-limit inheritance; qualify it with the real provider before engineering images.

## Intent

Exercise the real guide upload and provider-backed setup before implementing
project checkers. Use the actual proposed requirements and capability gaps as
engineering input. Do not replace inference with a prepared response.

The user expanded PR #651 to include classification, structured engineering
specifications and invalid-output diagnosis. Keep these related repairs in this
PR, committing and reviewing each completed stage before advancing. The setup
agent must reduce PM interpretation work and produce a concrete implementation
handoff, not merely label requirements or return schema-valid prose.

## Current behavior

Main `91df16e76` includes the original guide/example/briefs and generic ECR image
publisher. Real setup of the original guide finalized a proposal blocked on
missing file/package limits despite ART already enforcing platform limits. The
corrected nullable contract produced a retained v5 draft from unchanged original
bytes, with all four project limits null. This proves that size-limit omission
need not block setup; it does not qualify the draft's checker classifications.
Other test containers on the workstation are separate retained environments.

## Bounded change

### Allowed

- Existing project-agent contract, instructions, SDK adapter and affected
  validation/finalization/public proposal owners; narrowly scoped adjacent
  interface modules if needed to keep the typed specification cohesive.
- Existing CLI proposal decoder and text renderer, affected API/process tests,
  manager-authored rules consumers, current setup specifications and runbooks.
- Focused pure, SDK-parser, PostgreSQL custody/hash/approval and CLI regressions,
  plus isolated live provider runs using unchanged guide bytes.

- Ignored local Compose configuration and operator scripts for a uniquely named
  PostgreSQL/Redis/MinIO/API/Celery environment, public API/CLI calls and private
  redacted evidence.
- This record and factual input/runbook corrections supported by observed
  results. Any runtime repair requires its own explicit allowed paths and
  reproducer before editing.
- `pilots/terminal_systems/guide.md`, `guide-request.json` and `README.md`:
  keep the original guide free of duplicated platform limits, use a new guide
  version and record the actual setup boundary.

- `backend/app/interfaces/project_agents.py`,
  `backend/app/core/project_guide_instructions.py`,
  `backend/tests/test_agent_runtime.py`,
  `backend/tests/projects/guide_compilation/test_projection_policy.py`, and
  focused existing PostgreSQL proposal tests: permit null file/package project
  overrides and prove exact projection without inventing platform values.
- `cli/internal/api/guide_proposal.go`, its process tests and `cli/README.md`:
  preserve nullable project limits through the strict public proposal reader.
- `docs/roadmap_status.md` and the setup configuration/operator documentation:
  reconcile default-limit ownership and the actual qualification boundary.

### Not allowed

- No private reference content, credentials or provider tokens in Git or logs.
- No direct product-row writes, prewritten inference results, fabricated
  checker coverage, automatic approval or destructive cleanup of other stacks.
- No claimed guide activation or contribution outcome before real evidence.

## Design and decisions

### Remaining stages in this PR

1. Define a bounded typed checker specification linked to each atomic
   requirement: evaluation method/stage, input materials, checks, pass criteria,
   failure findings, positive/negative examples and execution/infrastructure
   needs. Explain human-review and lifecycle classifications explicitly.
   Infer suitable verification from required outcomes; lack of a registered
   checker must yield an engineering gap, not a human-review fallback.
2. Preserve retained immutable result hashes and exact public reads when
   evolving the contract. Require complete specifications from newly compiled
   results, without rewriting earlier evidence or inventing implementation IDs.
   Keep all policy approval, registration and activation authority unchanged.
3. Render a concise PM overview followed by readable per-check specifications
   through the existing CLI command; retain complete structured JSON output.
4. Diagnose invalid structured results with bounded, non-content diagnostics;
   reproduce and fix actual contract/prompt gaps. Never weaken validation or
   silently retry terminal attempts until a result passes.
5. Replay the original guide, inspect semantic completeness of the resulting
   PRE/POST handoff, verify stored/public exactness and cleanup, then perform
   independent final review and required CI. No project-specific logic enters
   the shared runner. Building project images remains the next product step.

### Reviewed specification and stage boundary

The user clarified stage selection: static and other reliably bounded checks
within 60 seconds belong before Submission creation; longer-running execution
and model evaluation belong in the background after Submission. PRE may still
use durable asynchronous execution and polling. This is not a synchronous HTTP
completion guarantee. Proposals must explain stage and execution budget; new
supported PRE proposals cannot select a registry deadline exceeding 60 seconds.
Retained approved evidence keeps its exact original semantics.

Use one typed `check_specification` on each atomic checker requirement, with a
`classification_rationale` for every new requirement. Both additions are omitted
from serialized retained records when absent, preserving immutable canonical
result and component hashes. New-generation completeness is enforced before
acceptance, in the central orchestrator and adapter validation; historical read,
approval and recovery do not manufacture fields or reclassify evidence.

The bounded specification contains evaluation method, stage rationale, execution
mode and proposed duration, input materials, ordered checks, pass conditions,
coded failure findings, positive and negative test cases, runtime dependencies
and infrastructure-failure handling. Input paths are canonical relative machine
fields, not prose. Missing task context or model-service custody is an explicit
engineering dependency, never invented runtime capability. The ordinary image
runner is offline. A supported claim must fit its actual material/service port.

Fix the two reviewed instruction contradictions: capability gaps alone produce
warning-ready proposals and continue blocking activation; only guide blockers
or blocking findings require `guide_blocked`. Both PRE and POST bindings may
carry configuration accepted by their exact immutable registry schema. The
four platform defaults do not implement project required-file/layout rules;
those require project checks even when also recorded in artifact-policy metadata.

Update the existing CLI decoder and readable proposal output for this same
contract, including current PRE parameters. Keep the complete JSON response and
terminal-safe display. Prove old retained hashes and new malformed specs,
stage/time conflicts, exact registry parameters and public read/approval paths.
The existing nullable-limit repair and its evidence remain intact below.

The user clarified that platform limits already govern every upload. Silence
in the project guide must not block setup. Remove the attempted guide-level
duplication; retain uploaded versions and their outcomes unchanged. The canonical downstream project policy already represents absent overrides
as null. Align the inference result with that contract instead of copying
platform numbers into an immutable project restriction. Explicit project limits
may tighten, never lift, platform limits. ART remains the enforcing owner, including admission quotas;
setup does not own or bypass archive safety. No new configuration knob, schema
migration or parallel inference path is needed.

## Acceptance criteria

- [x] Isolated API, durable worker, scheduler and storage are healthy at a recorded source head.
- [x] Distinct local actors and service identities receive authority through existing supported operations.
- [x] The exact merged guide/example is uploaded through public routes, with verified document custody.
- [x] Real provider setup produces a retained proposal; no result is substituted.
- [x] A guide without numeric intake limits is not blocked for their absence; null project overrides leave ART platform limits in control.
- [x] The public proposal reader accepts null overrides while rejecting invalid positive limits.
- [x] Complete the isolated PostgreSQL explicit/null approval, replay and revoked-authority regression; a timed-out run is not a pass.
- [x] New setup results include typed, evidence-linked specifications sufficient
  to implement and test each proposed check; malformed or contradictory specs
  are rejected without policy writes.
- [x] Classification distinguishes mechanical checks, agent evaluation,
  explicitly human decisions and Workstream-owned lifecycle rules. Missing
  implementations remain visible engineering gaps.
- [x] Prior retained result hashes/readability remain exact; new specifications
  survive projection, public read, approval/correction and CLI display.
- [x] Invalid-output diagnosis identifies reproduced failure boundaries without
  exposing guide/model text, credentials or provider state.
- [x] Real setup of the unchanged guide yields a useful reviewed engineering
  handoff; no activation/image/contribution claim substitutes for that proof.

## Risk and review routing

- Risk class: L1 for live authority/storage/model integration.
- Required reviewers: architecture, QA/test delta, and documentation/product operations for the nullable public contract and live qualification claims.
- Human review focus: actual setup findings, project policy choices and the next image implementation scope.

## Evidence

The focused regression `test_absent_project_size_limits_remain_null_through_projection`
exercises all three nullable combinations; the nullable projection
cases reject None on the original schema and preserve None after the repair.
`test_public_approval_read_replay_and_current_authority` exercises both explicit
and null limits through real PostgreSQL, public approval, exact replay and grant
revocation, including an assertion on the retained policy body. CLI process proof
covers individual and combined null/omitted limits and existing invalid numeric
bounds. The SDK strict-output schema still requires nullable properties in its
wire shape. ART archive/configuration regressions independently protect platform
enforcement; no ART implementation changes are part of this repair.

Verification completed: 98 focused backend cases, nine CLI process tests,
229 clean-environment configuration tests, and both isolated PostgreSQL public
approval/replay/revocation cases passed. The final PostgreSQL run used source
`f7304e328`, whose runtime and test tree matches the final documentation-only
successors, and confirmed database/role cleanup. It replaced an earlier
incomplete timeout; that timeout is not counted as passing evidence. Go build
and vet, Ruff/CLI formatting, Markdown links, Commitrail and the three applicable
stale wording/authorization/artifact checks passed. Hosted full CI remains an
external merge check, not a claim established by these local results.

Version 2, the first real provider run, finalized a blocked proposal with 11 requirements
and five POST capability suggestions. Its blocking finding was missing finite
file/package size limits. The user clarified that platform defaults must not
be duplicated in the guide. The local 64 MiB task admission quota is an aggregate
storage limit, distinct from the configured per-source byte ceiling; do not turn
that quota into a project archive rule. Version 3 was already uploaded and produced terminal
`schema_invalid`; retain it unchanged. Version 4 used the original guide with the
nullable repair but also ended `compilation_invalid_terminal` / `schema_invalid`.
Neither result is repaired or retried in place, and their invalid-output cause
has not been diagnosed. A manually initiated fresh version 5 returned
`policy_draft_ready` from the same 12,110 original bytes (SHA-256
`13d789d4b8df5d6b310d844c622336f265d53d2ddc38e8aa101b67765f9f7183`).
The exact public proposal reports all four project limits null and nine
requirements: eight human-review dispositions and one lifecycle disposition,
with no bindings or capability suggestions. This proves nullable handling on
one real provider run, not repeatable model correctness or a complete checker
handoff. Review those classifications before approving anything.

Version 5 ran through the real durable worker and provider with local diagnostic
wrappers that retained normal validation and only attempted to report validator
locations/types on failure. No model output was substituted or repaired. The
ordinary worker command is restored after that run. Local retained evidence is
under the ignored `.local-agent-loop/terminal-systems-live/` directory: v4/v5
setup statuses, the exact v5 public proposal, original-byte proofs, and test
logs. No PRE/POST approval, guide activation, project checker/image, released
task or contribution outcome is claimed. All uploaded attempts remain retained.

The public original-document download matched all 12,110 uploaded bytes and
SHA-256. Deliberate unchanged-key upload replay returned the original receipt
without creating a successor setup generation. An unassigned actor's setup
read returned concealed 404. After version 5, all 12 provider resources recorded
across versions 2 through 5 were confirmed deleted.

The PM proposal read initially returned concealed 404 because the local actor
had only system-level PM authority. Issuing the required exact-project grant
through the public admin operation enabled the complete proposal read. This
was a test-provisioning omission, not a product defect.

Docker named-volume operations hung on this workstation. The same application
services started with dedicated persistent bind directories and exact image
identities recorded locally. Other stacks and retained volumes were untouched.

## Review findings

Architecture review rejected copying platform settings into proposed project
limits: doing so would freeze a platform default as a separate project
restriction. The smaller repair is nullable project overrides, already supported
by canonical policy and intake consumers. No new runtime configuration field is
needed.

## Reconciliation

- Current-source reconciliation: merged #647 and #649 on main `91df16e76`, then incorporated main `a82f0d45` including #633 and its linear 0057 migration.
- Next usable boundary: qualify a repaired fresh provider handoff against the
  unchanged guide before engineering images or approving policy. The v8 result
  is schema-valid but its semantic review found incomplete and misclassified checks.
- Remaining risks: earlier schema-invalid model outcomes remain unexplained;
  requirement classification, model/tool reliability, offline builds and the
  contribution journey still need qualification. A successful nullable proposal
  is not end-to-end project readiness.

### Expanded diagnostic run

A separate, unchanged-guide version 6 reproduced the classification problem:
nine human-review requirements, one POST
capability gap and one lifecycle requirement. It finalized a blocked result
solely because a required external evaluator was not registered. The model did
not fail schema validation in this run. This supports the source diagnosis that
the instructions conflate missing engineering with guide insufficiency, but
does not establish why the earlier v3/v4 outputs were invalid. The original
results remain immutable. All 15 recorded provider resources through v6 were
confirmed deleted. The isolated local database upgraded from 0056 to main's
0057 without recreation; no product records were rewritten.

### Typed contract checkpoint

New-generation admission requires a nonempty inventory for ready proposals,
source evidence and classification rationales, and complete typed specifications
for checker requirements. Supported proposals must fit the selected image's
registered deadline, with PRE capped at 60 seconds. Runtime gaps cannot masquerade
as available implementations. The single existing proposal command renders the
structured handoff as readable sections and preserves exact JSON output.

The SDK and manager-authored runtime suite passed 72 cases. The built CLI proposal
suite passed ten cases, with two affected cases replayed after the final display
and completeness changes; Go build, test and vet passed. The first PostgreSQL run
passed the new typed-specification public read, approval, replay, retained-body
and hash assertions; two previous positive fixtures correctly failed new admission
because they supplied an empty inventory. Those current-generation fixtures are
corrected; the clean-head rerun passed all three cases in 166.23 seconds,
including exact stored/public specifications, approval, replay and concealed
revoked-authority reads. Database and MinIO cleanup completed for both runs.

A read-only check against the real retained v5 row preserved its complete canonical
body, all component hashes and result hash
`sha256:639809ae02445e6b0dd87ebfc63d1818b882a168204e66e7af1c6bbb07be566f`.
A public CLI read also preserved the original result, target and target digest.
No prior proposal was rewritten or approved. Fresh provider inference using the
typed contract, independent review and full CI remain pending.


### Typed handoff review repairs

Independent architecture and QA review identified two contract gaps at `c2ef6ad`:
model evaluation could claim PRE with a short proposed duration, and the prompt
omitted the isolated-execution dependency required by schema validation. The real
unchanged-guide v7 attempt reproduced the latter: two specifications failed that
validator, yielding terminal `schema_invalid` with no proposal or policy. Bounded
local diagnostics retained field locations only, not rejected model text. All
18 provider resources through v7 were confirmed deleted.

The repair explicitly declares the method/dependency and failure-code linkage in
instructions and schema descriptions, rejects model PRE in new-generation and
CLI validation, and reconciles the canonical guide template. The actual SDK
parser regression admits the complete isolated specification and rejects the
missing dependency. The short model regression first passes existing semantic
validation, then proves PRE rejection and POST admission. The affected backend
suite passed 99 cases. No validator was weakened and no terminal attempt was
retried automatically. A fresh guide version will qualify the repaired handoff.

The clean c2ef security review found no security defect; architecture and QA
require repair replay. The shared architecture boundary suite passed 92 cases;
Markdown links, stale-contract checks and Commitrail validation passed before
this repair. These checks do not establish a live checker or activation outcome.


### Live semantic handoff repair

The unchanged-guide v8 run finalized a warning-ready draft with six checker gaps,
four null project limits and no registered bindings. All 21 provider resources
were deleted. Independent review rejected it as an engineering handoff: semantic
free-form checks were labeled static PRE, required violations became warnings,
inputs omitted material needed to observe a negative case, nested task execution
was confused with ordinary checker isolation, and requirements were omitted or
bundled without complete assertions. One work finding also conflated unavailable
tooling with a contributor failure. Preserve this result as evidence, not approved
policy.

The aggregate POST budget owner also disproved the assumption that every registry
maximum is usable in a complete policy: materialization and per-entry cleanup
must fit the existing durable worker deadline. Extend only the setup specification
dependency enum and existing CLI decoder with `execution_capacity` as an explicit
runtime gap, using `capacity_exceeded` as its infrastructure outcome. Supply current
PRE and POST budget facts from CHECKERS' public constants through hashed
instructions. Require a visible capacity gap exactly when a stage cannot fit,
and reject invented shortfalls when it does fit. Supported bindings must remain
within the actual registry and aggregate deadlines.
No runtime limit, worker lease, registry schema or product execution is changed.

Reconcile generic generation guidance and schema descriptions for atomic inventory
coverage, observable inputs, deterministic grammar versus semantic judgment,
required versus warning findings, nested execution and infrastructure failures.
Add discriminating capacity tests, mirror the closed enum in CLI, retain the
existing parser and stage regressions, then run a fresh original-guide version.
Do not add named-project logic, prewritten model results or invented guide rules.


The v9 run finalized a warning-ready draft with two structural PRE checks and
seven background checks. It correctly moved free-form author-note judgment to
POST and declared nested environment dependencies. It remained unqualified:
coverage still omitted guide obligations and it claimed a 260-second shortfall
although its proposed POST durations plus overhead totaled 3,000 seconds, below
the 3,400-second budget. All 24 provider resources through v9 were deleted.

Review tightened capacity validation in both directions and both stages. A stage
that fits must not claim execution_capacity; over-budget PRE includes the default
and per-entry cleanup just as POST includes materialization and cleanup. Pure
regressions cover both supported and proposed PRE/POST, exact POST thresholds,
PRE's 59-versus-60 full-budget entries, and false capacity claims. Forty affected
cases passed. Instructions require an explicit private obligation ledger and
computed capacity totals before finalization. The next fresh run must establish
semantic coverage; prior ready status is not an engineering readiness claim.


V9 also exposed absent prepared-material custody: an offline build specification
must distinguish supplied package bytes from externally prepared images or cache
inputs, and missing cache material from defective contributor work. Add only the
`prepared_material` input/dependency kind to the typed handoff and CLI, requiring
`runtime_gap/material_unavailable` and a matching infrastructure condition. This
describes an unresolved engineering prerequisite; it grants no material access.

Final contract review required the material pair in both directions: task context,
guide context and prepared material cannot appear as dependencies without declared
inputs, or as inputs without matching dependencies. Backend and CLI now enforce
that relationship. This validation repair does not change the v10 inference
instructions or add any material permission. The actual retained v10 result must
also pass this stricter validation before qualification.


### Method and evidence qualification

The retained v10 result passes current strict parsing, public read and immutable
hash checks, but remains unqualified as an engineering handoff. Independent QA
found a free-form directory explanation inside a static check, built-environment
visibility claims judged only from source, executed demonstrations represented as
documentary review, revision quality hidden under lifecycle, and displayed stage
totals missing fixed overhead. All 27 provider resources were deleted.

Repair generic inference instructions and typed field descriptions: split methods
by the evidence they can establish, require executed observations for runtime
claims, separate revised-work quality from eligibility and timing, and compute
complete totals. Add these rules to the existing contextual contract regression.
No task identifiers or project-specific predicates enter shared code. A fresh
provider run, independently checked against the unchanged guide, is the semantic
regression; presence of instruction text alone does not prove inference quality.


Source review narrowed that guidance to the actual guide obligation: other exact
Workstream-owned lifecycle behavior remains classifiable by its owner; prior
context is a gap only when needed and unavailable from existing inputs; a guide
requiring documentary or attested evidence does not acquire an invented rerun
obligation. Runtime outcomes still require observable execution proof.


The final affected SDK/specification suite passed 119 cases; the subsequent
wording-only replay passed both instruction/configuration cases. Architecture,
QA and security source reviews passed, with their bounded head/delta scopes
retained locally. Source review is separate from semantic live qualification.

The v11 rehearsal was interrupted by a local worker restart after automatic
upload-triggered setup had already started. Its retained configuration used the
preceding instruction snapshot; it remains an uncertain attempt and supplies no
semantic success evidence. No automatic provider retry or row rewrite was used.
A fresh v12 upload uses the final instruction hash, verified against the retained
runtime configuration before inspecting the outcome. The normal lease-bound
cleanup owns v11's remaining provider resources; do not report cleanup before it
is observed.


### Bounded source-to-proposal coverage review

V12 used the exact final instruction hash and produced a strictly valid retained
proposal, but independent semantic review still found missing source obligations,
unsupported provenance certainty, absent comparison inputs and false prose budget
arithmetic. Correct trial and revision classification did not qualify the whole
handoff. Repeating instructions in one generation did not resolve the failure.

Extend the existing SDK adapter with exactly two phases inside one attempt:
produce a typed candidate, then inspect the original sources in a fresh model
context and return a corrected complete proposal. The review receives only the
existing credential-free prompt projection and the untrusted typed candidate.
Keep the same workspace, client, admission, overall timeout and aggregate model
and hosted-tool budgets. Reserve half the turn allowance for review; unused draft
turns remain available to it. Budget exhaustion or review failure cannot publish
the unchecked draft. Do not loop until green or reinvoke terminal attempts.
Only the final reviewed output reaches existing validation and finalization.

The affected scope includes the existing SDK runtime/workspace regression tests,
configuration instructions and current setup docs. Regressions must prove that
only the reviewed result is returned, review errors never fall back, aggregate
turn/tool budgets do not reset, and parser redaction, timeout, cancellation and
owned resource cleanup still hold. Capacity admission already computes exact
stage totals in trusted code; generated notes must not restate arithmetic.
Run a fresh unchanged-guide inference and independent source-to-output review
before claiming a useful handoff. PM approval remains required; a model audit is
not proof of universal model correctness or authority to activate anything.


Independent review found two boundary gaps in the two-phase implementation.
Known local review-input overflow now records terminal invalid output rather
than provider uncertainty. Successful document opens are tracked separately for
the review phase: it must open every cited source, and every assigned original
for a ready proposal. Draft access cannot satisfy review access. The existing
source-evidence validator is shared between this phase check and final validation;
no additional grant, workspace or model call is introduced. Regressions cover
zero, partial and complete review access after the draft opened all originals,
and distinguish local size rejection from unresolved provider failures.
All 33 provider resources from the previous live attempts are confirmed deleted.

V13 used the exact reviewed c39d5fa instruction hash and unchanged original bytes.
It ended as terminal `schema_invalid`: bounded parser diagnostics identified a
material dependency without its required matching input. All 36 allocations
through this attempt are deleted. No result was accepted or semantic success
claimed. The contract already rejects this mismatch; instructions and schema
field descriptions now state the pairing in both directions instead of only
requiring a dependency for an input. The existing three-kind pairing regressions
remain authoritative; a new instruction assertion exposes the previously omitted
reverse rule. Fresh inference, not that wording assertion, must qualify the repair.

### Private draft correction before canonical acceptance

V14 failed its first canonical SDK parse on required artifact path syntax before
the review phase could run. All 39 provider resources through that attempt are
deleted. Repeated independent draft-constraint failures show that requiring a
canonical candidate prevents the intended review from correcting it; further
prompt-only retries do not address that design assumption.

Keep exactly two bounded phases, with the identical provider-facing strict JSON
Schema. Add a private parser under `backend/app/adapters/project_agents/` that
checks draft byte size, strict JSON syntax, duplicate keys and schema structure,
including a local-reference-only schema boundary. A structurally valid draft is
transient untrusted data, never a retained or accepted compilation. A bounded
field-path diagnostic can identify canonical validation failures without source
values, exception messages or contexts. The same provider reviews this candidate
against the original documents; only its final output uses the canonical SDK
parser and unchanged owner, evidence, storage and finalization validators.

The same agent/model, workspace, client, admission, overall deadline and work
counters remain shared. Drop the draft run result before review. Malformed,
structurally invalid or oversized drafts terminate without another invocation;
there is no third phase, fallback, acceptance bypass or retry loop. Unsafe draft
prose may be corrected inside this private boundary but can never bypass final
text safety. Architecture and security design reviews support this boundary.
Extend the focused adapter tests and add a private-parser test module covering
both repaired drafts and still-invalid final outputs, structural rejection,
local schema references, redaction, shared budgets and exact parser selection.

The structural-draft regression set completed with 182 passing cases across the
SDK runtime, workspace, two-phase work budget, private parser and typed spec
validation. The first run identified five fixtures missing explicit nullable
input paths required by the strict provider schema; fixture serialization was
corrected without relaxing production validation. The passing run covers draft
correction versus unchanged invalid final output, no extra invocation, shared
budgets, source reopening, structural rejection and error redaction. The rendered
instructions remain within their 16,000-character limit (15,994). Ruff and diff
checks passed. These are adapter proofs, not fresh live semantic qualification.

### Production schema-validator dependency

Independent review identified that `jsonschema==4.26.0` was declared only in the
development extra although the existing checker contract already imports it.
The new private parser adds another production consumer. The current agents
release works through a transitive dependency; this is not a newly reproduced
live import failure. Extend this repair's allowed scope to `backend/pyproject.toml`,
`backend/uv.lock` and the existing configuration dependency regression. Move the
single unchanged pin into base dependencies, preserve every resolved version and
hash, and prove a no-dev/no-agents installation can import both guide runtime
composition and the new parser. No runtime policy or authority changes.

The locked base-only installation passed imports for guide runtime composition,
private draft parsing and checker schema validation with neither `agents` nor
`pytest` installed. The dependency regression passed. Every third-party lock entry,
resolved version and artifact hash is unchanged; only the root dependency edge
moves. Ruff and diff checks passed. The parser's 182-case evidence is unchanged.

### Real proposal review and public correction

V15 completed on `aa77a9b10` with 13 typed requirements (two static PRE, ten POST,
one lifecycle), 12 missing-capability suggestions, four null limits and no
approval. Exact canonical/result/component hashes and public CLI rendering passed;
all 42 accumulated provider resources are deleted. Source-to-proposal review still
found missing mandatory predicates, evidence inputs and execution dependencies;
one coverage condition incorrectly accepted disclosure instead of compliance.
This proposal is retained unapproved, not qualified as an engineering handoff.

Strengthen the generic instructions within existing scope: each source clause
needs an enforceable pass/error condition; disclosure is not compliance unless
expressly permitted; apply PM correction feedback without dropping other source
obligations. Do not encode this project's rules in shared code. Exercise the
existing public correction and explicit dispatch using the exact reviewed target,
retain its immutable predecessor and feedback, and independently review the real
successor before qualifying a handoff. No direct result edits or fabricated output.

The generic correction/coverage wording passed the three focused instruction and
configuration checks; rendered instructions are 15,928 characters. Ruff and diff
checks passed. This proves visibility and bounds of the instruction contract,
not that every future model output is semantically correct. Qualification depends
on the actual PM-correction successor and independent source review.

### Exact predecessor input for corrections

The real generation-2 correction completed, but regressed previously useful
requirements. Both model phases receive only the previous result's identity/hash
and feedback, not its content. Add the exact retained predecessor as bounded,
untrusted input; never ask the model to reconstruct it from an identifier.

Extend allowed paths to the existing compilation context, request-input and
correction-feedback loaders, their contract and PostgreSQL tests, SDK correction
input tests, and affected setup documentation. Preserve the public correction
command and immutable feedback hash. Reuse `AcceptedCompilationResult` to verify
canonical/result/component hashes, and match the exact correction target and
successor project/guide/source/generation. Read immutable records without new
locks or permission paths. Require feedback and predecessor together.

The predecessor body is derived material already committed by the feedback's
result hash. Exclude that redundant body from canonical attempt identity, and
include it explicitly in provider input with size checks before dispatch and
again when constructing coverage review. Preserve terminal replay hashes;
provider-uncertain attempts must not be reissued. No migration, retained-data
rewrite, compatibility branch or additional model call is permitted.

Acceptance: exact predecessor visible in both model phases; substitution,
missing custody and oversize input rejected before provider execution; request
and execution reconstruct identical identity; public correction/replay preserves
the original proposal. Run focused pure/SDK and isolated PostgreSQL proofs, then
architecture, QA/product and security reviews on a frozen candidate. Re-run the
real public correction and review source-to-proposal semantics before qualifying
the engineering handoff. Existing source and runtime authority remain unchanged.

The focused contract/SDK suite passes 190 cases. The initial isolated PostgreSQL
run passes correction request/replay, exact predecessor delivery to execution,
uncertain-call recovery without a second runtime, and the hosted fence's refusal
to reopen (three cases); temporary database cleanup is confirmed. Additional
bad-storage and substituted-authority assertions are being qualified separately.
The unchanged owner state machine fences hosted dispatch before provider I/O;
only provider-free executions may reopen. Thus a reserved attempt has never
contacted the hosted provider, and authenticated predecessor materialization
needs no new version branch or deployment fence. Instructions remain bounded at
15,966 characters. Ruff, Markdown links, Commitrail and diff checks pass.

Independent architecture review caught the new hosted prompt bound also applying
to provider-free manager-authored compilation. Scope it to hosted runtimes, as
the existing orchestrator already does; add a shared-builder regression for both
branches and replay the existing real PostgreSQL provider-free case. QA requested
a missing-finalization negative, now added to the storage-substitution proof.
These repairs preserve the same bounded outcome and runtime authority.

The clean repair `1e8dc833f` passed all five isolated PostgreSQL correction,
authority, hosted-fence and provider-free cases, with cleanup confirmed, plus
92 repository module/authorization boundary tests. Real generation 3 completed
from the unchanged guide, with exact stored/public hashes and CLI rendering,
two PRE and eight POST specifications, two lifecycle requirements, ten gaps and
four null limits. All 48 accumulated provider resources were deleted.

Independent semantic review closed the earlier method/evidence defects but found
remaining incomplete predicates, directory entries in a file-artifact list,
missing mandatory documentation/pinning obligations, and unresolved qualitative
selection of revision checks. Keep this result unapproved. Within the existing
instruction/specification scope, clarify self-contained predicates, typed path
inputs, file-only artifact metadata, presence before accuracy, and resolved
mapping or conservative complete reruns. Update generic schema descriptions and
their existing focused assertions, preserving the 16,000-character instruction
limit and all trust, stage and authority rules. Submit source-grounded PM feedback
through another exact correction, then qualify its actual output. No source guide
changes, project-specific shared code or fabricated result are permitted.


### Qualified setup handoff and remaining boundary

The final source candidate `e4ac7599e42cf6186e507ff5e77cbe0e0797ae0d`
passed architecture, QA/test-delta and security review. Its last specification
refinement passed 72 focused cases. The complete correction work additionally
passed 190 contract/SDK cases, nine focused context-boundary cases, five isolated
PostgreSQL custody/replay/authority cases on clean `1e8dc833f` with database and
role cleanup, 92 module/authorization boundary cases, and the unchanged CLI's
11 integration cases plus Go build/vet. Full backend Ruff and the existing
80-percent docstring gate passed (80.1%); documentation and Commitrail checks
passed. These are scoped suites with overlap, not a unique full-suite count.
Full hosted CI remains the independent merge check for the final PR head.

Real generation 4 repaired the earlier handoff but retained metadata root/table,
visible-example failure mapping and reference-before-verifier ambiguities.
Generation 5 closed those, but weakened command-specific obligations into
broader prose. Both remained unapproved. Exact-target public PM corrections,
without changing the guide or replacing model output, produced generation 6:

- Compilation: `01a165a2-7cde-7277-b789-7013d7a2088d`.
- Result hash: `sha256:523356e72f2f4ac2541f3eb74b5939b67fd2e24af421458ac966ed2aef5f65a3`.
- Original guide SHA-256 remains
  `13d789d4b8df5d6b310d844c622336f265d53d2ddc38e8aa101b67765f9f7183`.
- Two PRE specifications (20/30 seconds), eight POST specifications and two
  lifecycle requirements; ten capability suggestions and zero image bindings.
- POST execution plus declared cleanup/materialization is 2,880 seconds within
  the 3,400-second bound. Four project size/entry limits remain null; required
  artifact metadata contains only the three regular files, not directories.
- Exact stored canonical/result/component hashes and public specifications match;
  the public CLI renders the complete handoff. Public correction replay retained
  the original operation and immutable predecessor. All 57 accumulated provider
  resources are deleted; the diagnostic worker override was removed after the
  last attempt finished.

Independent architecture and QA/product source-to-proposal reviews both pass
this actual generation. Exact reproduction commands, each documented command,
metadata root/table semantics, visible-example findings, author-only isolation,
and revision reference-then-verifier execution are explicit and testable. The
remaining material/runtime dependencies are stated as gaps, not delivered
capabilities. The model output required human review and several corrections;
this proves one useful reviewed handoff and the correction mechanism, not
universal or unattended semantic accuracy.

The intended setup/specification repair is complete. The proposal remains
`draft_ready_with_warnings`, without PM approval, POST policy or activation.
Project-owned checker implementations, unresolved runtime/material services,
image publication/registration, corrected policy binding/approval and the real
contributor journey are separate remaining work. This record does not claim
submission-intake enforcement, deployment, or a contribution outcome from setup
proof. No private reference content or prewritten inference response was used.

### Hosted structural-gate repair

Hosted preflight at `f16fa6cc2` passed the 92 boundary tests but rejected new
structural debt: the extended correction test is 171 lines, its file is 1,204
lines, and `growth_report` is 101 lines. The structural validator itself had
not been run locally. Keep the existing limits and frozen ledger unchanged.

Within the existing focused test scope, move only the newly added altered-storage
rejection proof into a separate correction-input test, retain every original
canonical request/replay/execution assertion in its current test node, and move
its imports to module scope. Remove the fixture's duplicated capability lookup
without changing the generated result. No product source, provider prompt,
proposal, skip or test assertion may be weakened. Qualify the actual structural
validator, focused fixture tests and both PostgreSQL invariants, then replay
QA/test-delta and architecture review. Existing live Gen6 qualification remains
applicable because runtime source and instructions are unchanged.

The same hosted run also refused every lane before collection because four new
test modules had not been registered in the explicit lane catalogue. Add those
modules and the newly split PostgreSQL module to their existing shared/project
families. Extend allowed paths to `backend/scripts/test_lane_catalogue.py` and
its existing inventory/ownership checks; preserve all lane counts, owners,
timeouts, completeness rules and required checks. Verify recursive module
inventory and a complete collect-only run before another push.

CodeRabbit separately found a real CLI/backend path mismatch: the CLI rejected
literal braces which canonical backend relative paths permit. Remove only that
extra restriction in the existing proposal decoder; add a process regression
using the backend-validated public response and keep invalid path rejection
coverage. This is within the existing CLI contract scope; no backend path rule,
execution boundary or guide instruction changes. Batch these repairs with the
structural fix and replay the affected independent reviews.

The split PostgreSQL cases passed on `f9a581d5c` with database/role cleanup; all
17 original journey assertions are AST-identical, all seven substituted-read
variants remain, and an intact-read control is added. The growth suite passed
51 cases and the actual structural validator passed without ledger changes.
Formatter-only cleanup does not change those assertions. The old CLI binary
rejects the new backend-validated brace-path case with `invalid_api_response`.

Catalogue reconciliation adds exactly two shared modules and three project
modules, preserving every existing module's lane owners and the 16-lane topology.
Update only the corresponding independent family/ownership snapshot constants;
no existing test is moved or excluded. The first local inventory run correctly
rejected stale snapshot constants before their explicit reconciliation.

Architecture review also reproduced Unicode control/format characters accepted
by the CLI and rejected by the backend. Enforce valid UTF-8, the 500-rune bound
and Cc/Cs/Cf rejection while preserving canonical Unicode filenames and braces.
Keep NFC validation with the backend owner: this display-only reader neither
resolves nor executes paths. Go's stream-safe normalization rejects some valid
Python NFC strings and uses a different Unicode version; do not introduce a
second normalization implementation or dependency just to mirror that semantic
guard. Backend-validated positive cases include long combining sequences;
backend-rejected process cases cover controls, format characters and length.
The old binary accepts the invalid response, so the new negative test fails
against it. Replay the affected architecture and QA reviews.

Hosted real-API CLI cases also exposed callers still feeding the empty retained
compilation fixture into new execution. The new generation guard correctly
refuses these before persistence. Update current-generation source/committed-guide
fixtures and explicit runtime callers to supply the existing generated fixture
and complete typed PRE/POST specifications. Preserve retained-result fixtures and
deliberately invalid-output tests; never auto-enrich supplied outcomes or bypass
generation validation. Extend test scope to their existing backend and CLI
consumers. Reproduce the failing public approval journey, rerun affected real-API
journeys on isolated PostgreSQL, and retain cleanup evidence.
