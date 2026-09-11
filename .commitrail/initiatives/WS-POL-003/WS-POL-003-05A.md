# WS-POL-003-05A — Complete proposal review and pre-submission approval custody

- Initiative: WS-POL-003
- Durable disposition: Planned
- Intended merge outcome: One hidden PROJECTS operation family reviews an exact finalized unified proposal, records pre-submission approval, and requests a setup-wide correction without changing prior evidence.

## Intent

The project manager must see the complete agent result before deciding what to
approve or correct. Pre-submission intake policy and post-submission evaluation
proposals stay distinct. Approval runs the existing policy compiler and makes no
model call. Correction requests another generation through the unified setup
machinery; it does not edit or retry an uncertain provider result.

This implements the adopted [05A contract](planning/chunks/WS-POL-003-05A-hidden-pre-submit-approval.md).
Public authorization and exposure follow in AUTH-12F4 and POL-05B.

## Current behavior

`guide_compilation/` already owns immutable attempts, results, component
projections and setup finalization. `ProjectService.approve_submission_artifact_policy`
instead accepts manual lineage and rejects unified proposals. Its policy merge
helpers and CHECKERS compilers have shared activation consumers. Existing test
fixtures call the manual HTTP approval route and must be reconciled with its
replacement rather than preserving that obsolete route for fixtures.

## Bounded change

### Allowed

- `backend/app/modules/projects/`: complete review contracts, policy merge and
  approval owner, correction operation, canonical request/context integration,
  removal of superseded manual approval route/schema/implementation, and
  shared active-guide-read readiness custody for the replacement approval.
- `backend/app/modules/authorization/api/`: narrow unavailable-by-default typed
  review/approval/correction port; no activated evaluator or composition.
- AUTH catalogue and audit vocabulary may declare the two proposal actions as
  `planned` and register bounded evidence identifiers. Hidden PostgreSQL custody
  needs these identifiers; neither action becomes active or receives an evaluator.
- `backend/app/modules/checkers/api/policy_compilation.py`: public typed bundle-and-plan
  contract implemented by the canonical catalogue; the private compiler remains
  the sole implementation. The catalogue supplies both operations through the
  existing injected planner, without widening planning-only consumers. The dependency-free
  `checkers/api/artifact_paths.py` owns shared machine-field grammar; replace
  its private compiler/runtime consumers and PROJECTS path validation together.
- `backend/app/interfaces/project_agents.py` and affected runtime input shaping:
  bounded correction feedback bound into the existing canonical input hash,
  plus field-specific artifact-proposal path/pattern validation matching the
  existing compiler contract (nested relative paths are machine fields, not prose).
- PROJECTS database models and one successor Alembic migration for append-only
  operation custody, composite ownership and immutable evidence constraints.
- Affected tests and shared fixtures, API/schema inventories, ownership records,
  structural inventory, current specifications and POL navigation/roadmap.

### Not allowed

- Public action activation, public live approval/correction, provider invocation,
  post-policy approval/projection, checker execution, public guide activation operations/routes/state transitions,
  unrelated AUTH/ART audit cleanup, alternate compilers or compatibility routes.
- Changing finalized setup rows or receipts, weakening tests/gates, deleting
  retained data or embedding private guide material in repository evidence.

## Design and decisions

1. Expose a bounded exact-compilation package containing validated findings,
   artifact policy, requirements, separate pre/post bindings, suggestions and
   safe notes, with all component/source/catalogue/finalization identities.
2. Reuse the existing PROJECTS policy merge, CHECKERS canonical bundle compiler,
   and CHECKERS `EffectivePreSubmissionPlanningPort` for the ordered effective
   execution plan. Bind both compiled outputs and the exact catalogue to the
   approval operation. ART owns original-document custody, not either compiler.
   Extract shared merge behavior if needed; remove the superseded manual
   approval operation.
3. Record approval separately from setup finalization, atomically with canonical
   artifact/effective/pre-policy lifecycle writes and authorization evidence.
   Bind operation replay to the exact displayed target and fresh authority.
   `SubmissionPolicyMutationIdempotencyRecord` remains the existing reservation
   and replay owner; the immutable approval operation is its committed product
   provenance, not a second idempotency protocol. Effective/pre-policy custody
   must require both that reservation and the exact immutable approval operation.
   Retain manual draft creation custody only for still-supported create/update.
   Approval-aware finalization replay must prove the original draft projection
   digest and the exact authorized lifecycle transition using this provenance;
   coercing arbitrary policy state to draft is not sufficient evidence.
4. Record correction separately, with normalized bounded feedback and one
   successor setup generation. Integrate feedback into the canonical request
   context and hash. Preserve the previous finalized generation byte for byte.
   The successor starts in `correction_requested`, outside automatic upload
   recovery. This distinct state is necessary because every existing queued or
   awaiting-documents state can trigger automatic source consent, which belongs
   only to the initial upload. The existing human compilation-request operation
   later admits this successor, changes it to the canonical queued shape and
   reserves its attempt atomically. Hidden tests supply request authority; live
   dispatch composition remains POL-05B. No automatic-origin alias is added.
5. Default authorization is unavailable. Tests exercise supplied purpose-specific
   authority handles; this does not claim AUTH-12F4 or public GET is live.

## Acceptance criteria

- [ ] Complete result is reviewable by exact identity with no provider payload,
  raw guide, storage credentials or replayable document references disclosed.
- [ ] Stale/mixed source, generation, result, component, catalogue and policy
  identities fail; every capability gap blocks approval; warnings require exact
  acknowledgment where applicable.
- [ ] Mandatory platform checks cannot be weakened, repeated, selected or
  reordered; effective policy and pre-plan match the canonical compiler.
- [ ] Default authority denies reads and writes; authorized operation/replay
  remains inside the supplied session/root transaction with no hidden commit.
- [ ] PostgreSQL proves atomic approval/provenance, immutable finalization,
  composite ownership, rollback and exact replay.
  `test_unified_approval_postgresql_requires_reservation_and_operation` must
  independently remove each relation from an otherwise valid transaction and
  prove rejection, alongside a successful complete control.
- [ ] Correction produces one successor on replay, binds bounded feedback, and
  cannot restart uncertain provider work or mutate previous evidence.
- [ ] Removed manual approval callers/tests are replaced with required behavior
  coverage; current API inventory and docs describe the resulting exposure.

## Risk and review routing

- Risk class: L1 (policy lifecycle, authorization seam and immutable evidence).
- Required reviewers: architecture, security, QA, product_ops, reuse_dedup,
  test_delta, documentation; ci_integrity for affected evidence inventories.
- Human review focus: full proposal visibility, clear pre/post distinction,
  correction lineage, no inference during approval, no obsolete approval path.

## Evidence

Plan feasibility review precedes implementation. Focused tests will use real
PostgreSQL transactions and actual compiler controls; negative cases must reach
the intended guard and have a valid control. Run the affected API, migration,
project lifecycle and compilation tests, lint and repository contract gates
before the clean-candidate review wave. Hosted CI supplies the full test and
coverage result. No execution result is claimed yet.

## Reconciliation

- Current-source reconciliation: starts after merged #396 and preserves #397's
  canonical project-role task authorization; the unrelated submission denial
  audit gap remains outside this change.
- Next usable boundary: AUTH-12F4, then POL-05B.
- Remaining risks: manual approval test fixtures have downstream consumers;
  successor generation must retain exact original-document custody without a
  second artifact access path. Trace both before implementation.

## Plan review disposition

ARC-POL05A-001: retain the existing reservation/replay owner and require a
separate immutable product provenance relation on all approval outputs, as
specified above. This resolves the ambiguity without another replay subsystem.
The other reviewed corrections assign both compilation stages to CHECKERS,
require approval-aware finalization validation and isolate correction successors
from automatic source consent. Evidence references in the review package must
be display-only source labels/locations; runtime document handles are excluded.
Correction feedback is optional input data, not a new implementation version;
its canonical encoding omits an absent feedback field and binds a present one.
This keeps unchanged semantic inputs unchanged without an old/new runtime path.

## Affected-consumer reconciliation

Shared active-guide reads previously required manual-policy lineage. They now
reuse the exact unified approval and original finalization proof under the
existing guide lock, binding approval/reservation identity into their resource
digest. This changes no activation command, public action or lifecycle authority.
Warning acknowledgments live in the immutable approval receipt; finalized
sufficiency reports are never edited to acknowledge them.

The removed HTTP approval tests are replaced by actual hidden PostgreSQL
operation tests: exact approval/replay, each independently missing custody row,
immutable projected/approved content, same-content corrected-generation
supersession, required predecessor identity, concurrent approvals and current
manager authority. Packaging merge and identical-default deduplication retain
focused tests of their existing canonical owner. The removed route has an
absence assertion; unknown fields remain rejected by current public schemas
and the new strict commands. Invalid artifact fields are now rejected at result
validation with independent defensive projection checks, without old-version
fixtures or a permissive compatibility constructor.

The compilation input resolver is renamed to reflect its shared automatic and
human request responsibility. Its exact ownership partition replacement and
new bounded proposal targets are declared without widening eligibility or
limits. The catalogue contract moves intact to its focused test module and
adds the two planned actions; permission inventory and active actions do not
grow. Model metadata stays in the existing compilation model owner.

The coherent diff spans these shared callers and their tests because removing
manual approval while retaining its fixtures/read assumptions would leave a
broken product path. This is one approval/correction boundary, not an additional
authorization or post-policy implementation chunk.
