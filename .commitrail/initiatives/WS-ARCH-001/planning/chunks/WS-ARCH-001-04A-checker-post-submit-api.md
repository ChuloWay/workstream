# Chunk Contract: WS-ARCH-001-04A CHECKER Post-Submit API

Disposition: Planned. Dependencies: merged CHECKER catalogue and unified
compilation contracts; no POL-07, AUTH-12H, task activation or live run prerequisite.
Risk: L1.
Outcome: CHECKERS owns the single post-submit API and phase-command contract
for consuming and publishing immutable execution facts. Chunk 04C owns durable
final-result/currentness persistence; 04E owns the durable `allow_review`
routing manifest.

Allowed: `backend/app/modules/checkers/api/**`, focused CHECKER-owned
implementation/tests, boundary ledgers and initiative evidence/status. Not
allowed: ART provider access, TASK transitions, AUTH activation, REV admission,
ORM leakage, generic checker payloads or a second checker catalogue.

This supplies the CHECKER-owned post phase contract consumed by POL-07's
single facade. It must not add another
dispatcher, phase API, catalogue, caller-selectable checker path, or execution
surface. POL owns facade composition, not a second definition of these facts.

## Required capability proof before guide activation

CHECKERS owns the versioned post-submit catalogue, mandatory defaults and
registered project evaluator implementations. Existing structural checks such
as `check_acceptance_criteria_present` do not prove that submitted work meets
those criteria. The release path must select an actually implemented work
evaluator matching its declared requirements; unsupported requirements stay
explicit capability gaps, never fabricated bindings or hidden acceptance.

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
fixtures: valid work, structurally valid but substantively invalid work,
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
