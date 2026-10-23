# Setup checker scope — PRE/POST proposals with strict correction

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: Setup derives only submission-check specifications, with strict JSON rejection and bounded error-guided correction.

## Intent

The PM owns review, revision, timing and other project-management decisions. Setup reads the assigned guide and examples to specify PRE and POST checks, not to advise on task management. Instructions, schemas, examples and runtime validation must agree.

## Current behavior

The instructions explicitly invite lifecycle and human-review classifications; generated requirements can carry those classifications. Private draft parsing rejects malformed JSON, but parser errors terminate rather than returning safe correction feedback. Accepted historical proposals must retain their exact hashes and read behavior.

## Bounded change

### Allowed

- `backend/app/core/project_guide_instructions.py`, setup contracts in `backend/app/interfaces/`, and `backend/app/adapters/project_agents/`: scope, provider schemas, bounded validation/correction and examples.
- Affected setup tests, shared fixture callers, current setup documentation and roadmap; this record.
- `cli/tests/integration/test_guide_approval_public_api.py`: keep its newly inferred proposal fixture within the same removed-field boundary; preserve real approval/replay/authority assertions.
- `backend/scripts/test_lane_catalogue.py`: register the new setup regression module in the existing complete CI inventory; no execution or gate changes.
- Existing PROJECTS admission call sites only if needed to enforce the same generation boundary.

### Not allowed

- Changes to PM policy authority, revision counts/deadlines, human-review behavior, acceptance, payments, retained proposal bytes, migrations or project checker logic.
- Live model spending, deployment or merging.
- Parallel provider implementations or bypasses of source access, cleanup, overall timeout and turn budgets.

## Design and decisions

Use the existing inference generation-admission boundary to narrow new proposals without rewriting immutable history. A guide with no project-check obligations may have an empty requirement inventory, but still needs source-backed sufficiency and complete document coverage; do not fabricate a management requirement to fill the list. PRE/POST check specifications and their supporting guide sufficiency, source attribution and capability-gap facts remain typed. Exclude task-management advice and remove the free-form notes field from the inference schema. Preserve the explicit manager-authored input path and retained custody component hashes. Keep default coverage separate from selectable project images. Supply a complete schema-valid example inside the hash-bound instruction snapshot and explicit input-field meanings. Retry known invalid completed output with bounded schema diagnostics, never raw invalid values, within the original attempt budget. Preserve fresh source review before publication.

## Acceptance criteria

- [x] Instructions and schema reject newly generated task-management/human-review/informational requirements; PM policies remain independent.
- [x] PRE/POST specifications, missing-capability handling and examples are coherent and schema validated.
- [x] Malformed JSON, extra fields, invalid classifications and canonical/context violations receive bounded correction feedback; exhausted correction never publishes a proposal.
- [x] Retry shares timeout, turn/tool budgets and cleanup; ambiguous provider failures are not replayed.
- [x] Retained proposals preserve exact read/hash behavior and existing authority.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `architecture`, `security`, `qa`, `documentation`, `product_ops`, `test_delta`, `ci_integrity`
- Human review focus: Only PRE/POST work requirements may be generated; historical evidence remains immutable; corrections cannot expand access or runtime budgets.

## Evidence

Focused setup/runtime/parser/source-review/specification suite: 178 passed.
Additional scope, provider-resilience, workspace, capability-growth and correction
contracts: 157 passed (overlaps the scope tests; counts are not additive).
Backend lint passed. Current docstring check: 80.2%; documentation link check passed.
New assertions reject the old broad provider enum, forbid the removed notes field,
and prove error-guided correction, exhaustion, shared budgets and retained hashes.
Repair suite: 184 passed; a further native SDK Runner probe passed using scripted
model responses and real SDK tool dispatch/parsing, with no network. It confirms
invalid-output exception propagation, value-free correction and a fresh review.
No live provider or deployment qualification claimed. Full CI and independent
review remain required before readiness.

## Reconciliation

- Current-source reconciliation: Main `bb39ac10a` includes the project PRE image (#656), ART CLI completion (#662), neutral document runtime (#659) and MCP policy drafts (#657). Reconciliation preserves the provider-neutral bounded read/search tools and model profiles while enforcing the restricted output schema, correction budget and fresh source access in each inference phase. The roadmap retains the original runtime qualification and distinguishes it from the fresh PRE/POST-only proposal still required.
- Next usable boundary: Real project proposal regeneration after human merge; model runtime work remains separate.
- Remaining risks: Generated prose still requires PM review; schemas cannot prove every statement is semantically within scope.

## Review findings

Plan review identified the shared manager-authored boundary and immutable example
identity. Inference scope is conditioned on the recorded runtime; direct manager
rules remain explicit PM input. The entire example is included in snapshotted
instructions. Regression testing also caught the SDK inline enum copy; both the
provider field and referenced enum are now restricted.

Frozen review found that blocked results could omit assigned originals, that the
example wrapper was not itself valid output JSON, and that the pilot runbook needed
a historical-scope qualifier. Repairs require all assigned handles in every phase
and status, append only the valid result JSON after explanatory example context,
and qualify the retained handoff. Regressions cover blocked drafting/review and
correction, exact displayed JSON, both enum sites and the absent notes field.
Hosted preflight also found the added example module outside the tracked behavior
partition. The static example now lives with its existing instruction owner; no
partition rule or CI gate changed.

Independent architecture, product/operations, security, QA and test-delta replays
confirmed those repairs. Discriminating regressions reject incomplete source
access, a widened enum, the invalid example wrapper, missing correction handling
and retained source-open evidence across phases. The remaining documentation
finding was a stale helper docstring; it now states the implemented all-originals
requirement. These reviews qualify offline service and SDK composition, not live
provider or deployment behavior. Hosted full-suite verification remains required.

External review also found a stale roadmap scoreboard and parser tests whose
faults used the removed notes field. The scoreboard now requires fresh proposal
correction before implementation. Length, Unicode and unsafe-prose faults use a
supported finding message and assert their intended validation layer, preserving
the distinct boundaries instead of merely testing unknown-field rejection.

The retained PostgreSQL parser-rejection test also expected immediate termination.
Its pre-fix run reproduced three bounded calls against that one-call expectation.
The corrected proof checks both corrections, terminal persistence without a
proposal, sanitized feedback and zero further calls on exact replay. Its malformed,
schema-invalid and unsafe-prose cases retain distinct invalid-output causes. All
three passed against isolated PostgreSQL; database and role cleanup was confirmed.
Independent replay caught that ordinary model serialization omitted a nullable
provider-required member and masked the unsafe-prose case. The fixture now uses
the existing strict provider-payload helper and asserts exact per-case diagnostic
paths and codes, so a wrong validation layer cannot satisfy the database proof.

Merge review also reconciled the compilation scoreboard inherited from main: it
now requires fresh correction and PRE-image reconciliation before implementing
and binding the resulting POST checks, matching the pilot row and runbook.

Hosted completeness validation found the new setup test module absent from the
lane catalogue. It is now assigned to the same shared-foundation partition as
the other setup runtime tests. No runner, selection rule or completeness gate
changed; the existing recursive inventory test detects the omitted registration.

The real CLI approval regression copied a generated proposal through retained
serialization, inadvertently making the removed empty notes field explicit. Its
inference fixture now omits that field; production rejection and all existing
public approval, replay and fresh-authority assertions remain unchanged.

Main reconciliation retained neutral read/search tools, provider profiles and shared
result validation. Source evidence is reset for each draft, review and correction.
Failed hosted fixtures were still emitting removed notes or generating human-policy
requirements. Growth proposals now use the strict inference fixture. Human-review
activation proofs explicitly select the manager-authored runtime, preserving real
request identity, persisted configuration, activation refusal and SQL backstops.

Merge security review found that a no-match search could satisfy fresh-source
coverage. Per-phase observation now requires a first-page read returning text or
a verified genuinely empty original. Search and offset-only access remain audited
and budgeted but do not establish source observation. Regressions exercise both
phases, correction success/exhaustion, no-match searches and empty/partial reads.
Current setup and roadmap documentation now describes neutral tools and bounded
correction before terminal failure.

The final current-spec scan also reconciled the operating manual, developer setup,
roadmap history and ART guide-binding specification: every phase receives strict
validation and fresh source observation; neutral inference creates no provider
file/workspace resources. Historical exact-ID cleanup remains separately owned.
