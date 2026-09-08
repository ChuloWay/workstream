# Chunk Contract: WS-ARCH-001-04A CHECKER Post-Submit API

Disposition: Planned. Dependencies: merged CHECKER catalogue and unified
compilation contracts; no POL-07, AUTH-12H, task activation or live run prerequisite.
Risk: L1.
Outcome: CHECKERS owns the single post-submit API and phase-command contract
for consuming and publishing immutable execution facts. Chunk 04C owns durable
final-result/currentness persistence; 04E owns the durable `allow_review`
routing manifest.

Allowed: `backend/app/modules/checkers/api/**`, focused CHECKER-owned
implementation/tests, the shared typed catalogue/compilation input contract
where its versioned shape changes, boundary ledgers and initiative evidence/status. Not
allowed: ART provider access, TASK transitions, AUTH activation, REV admission,
ORM leakage, generic checker payloads or a second checker catalogue.

This supplies the CHECKER-owned post phase contract consumed by POL-07's
single facade. It must not add another
dispatcher, phase API, catalogue, caller-selectable checker path, or execution
surface. POL owns facade composition, not a second definition of these facts.

## Catalogue and compiled policy identity

The current PROJECTS post-catalogue projection exposes only ID/version/stage
and selection/default flags and rejects post-binding parameters. It is not
already the richer capability contract below. CHECKERS owns the single public
catalogue and registered implementation definitions: execution method, typed
configuration/result schema, failure categories, dependency ordering and
resource budgets, provider recovery capability and required output/log roles.
Only declared generated outputs require ART binding; do not fabricate an empty
artifact to satisfy a run that declares none. Extend the shared unified-compilation input/binding contract
alongside that catalogue; do not advertise unsupported fields to the agent.
PROJECTS/POL later consumes the frozen public snapshot instead of importing
the private CHECKERS registry or copying its default constants.

Use the existing `PostSubmitCheckerPolicy.policy_hash` as the post-plan hash.
It hashes the complete canonical compiled policy body, including ordered
mandatory defaults, approved project entries/configuration and pinned compiler/
catalogue/implementation identities. Extend/version that body where necessary;
do not add a second task-level plan or hash algorithm. TASK stamps its existing
locked post-policy identity/hash/body, and the evaluation envelope separately
binds the immutable task/submission facts. Execution validates that frozen
policy and never recompiles against the newest catalogue.

This catalogue/schema foundation precedes POL-04B generations intended for
approval. Sparse-catalogue generations remain immutable evidence and cannot be
upgraded in place; changed capability input requires a new generation. Actual
registered evaluator conformance is required before activation, not a claim
that the current presence-only implementation is substantive evaluation.

## Required capability proof before guide activation

04A also defines the immutable typed evaluation-request envelope consumed by
04C and later persisted/delivered by TASK in 04E. Its opaque
`evaluation_request_id` is not an outbox delivery ID. It binds project, task,
assignment, immutable Submission/version, ART content/binding/digest/size,
locked guide/policies/catalogues, post-plan hash and server-owned evaluation
generation. CHECKERS validates the fields and recomputes the canonical digest;
a caller hash is never trusted. This value contract has no foreign key or
existence dependency on a future TASK dispatch table. Controlled owner fixtures
can supply it before live dispatch exists; they do not activate production.

The public currentness contract distinguishes recovery of an unfinished
request from a new authorized evaluation after terminal failure. 04C owns its
fence participant and persistence; 04E coordinates TASK routing with it in one
caller transaction. No consumer invents an alternative attempt identity.

CHECKERS owns the versioned post-submit catalogue, mandatory defaults and
registered project evaluator implementations. Existing structural checks such
as `check_acceptance_criteria_present` do not prove that submitted work meets
those criteria. Requirements classified for automated post-submit evaluation
must select an actually implemented evaluator matching that claim; unsupported requirements stay
explicit capability gaps, never fabricated bindings or hidden acceptance.

The existing `human_review` disposition remains legitimate when explicitly
proposed and approved for that requirement. Do not impose universal automated
semantic judgment on every source-agnostic project, and do not silently move
an unsupported automated requirement to human review. A substantive-invalid
artifact fixture is mandatory for an evaluator claiming substantive coverage,
not for a structural checker that claims only package or lineage integrity.

Extend existing canonical catalogue/compilation types only where required for
the selected capability; do not introduce another registry. Deterministic
rules and model-based judges are distinct execution methods, not different
phases. A model judge requires a typed ADR-0014 adapter, locked requirements,
model/instruction/schema identity, bounded verified input, strict output and
safe evidence, provider idempotency/recovery requirements, budget/time limits,
and no project-supplied code, arbitrary tools, secrets or unrestricted network.
No model evaluator is claimed implemented by this plan or implied by setup's
guide agent. Concrete capability IDs and fixtures must be fixed in the bounded
implementation contract from the actual supported v0.1 use case; absent that
support, the affected guide stays blocked, not silently weakened.

Before POL-07/AUTH-12H, prove each selected implementation with real evaluator
fixtures: valid work, a failure of the behavior the evaluator actually claims
(including structurally valid but substantively invalid work for substantive evaluation),
malformed output, unsupported config, wrong stage/version and required gaps.
For a model adapter, fake-provider tests prove contract handling only; record
separate controlled adapter/evaluation evidence and never promise deterministic
judgments. ARCH-04C alone adds durable execution/currentness/worker custody.
If implementing a capability exceeds this contract-sized boundary, split its
implementation before starting; do not combine it with task routing or AUTH.

Acceptance: facts can represent the approved unified generation and closed checker
catalogue; only one final current result can authorize routing; stale,
superseded or partial results deny. Verify contract/unit tests, property tests
for canonical hashes and real registered capability conformance (no completed
product run prerequisite), boundary validators, Ruff and hosted coverage. Required
reviews: architecture, security, product/ops, QA, senior and reuse.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

## Merge state

- Outcome on merge: `planned`
