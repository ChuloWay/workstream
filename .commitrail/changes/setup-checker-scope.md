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
- Required reviewers: `architecture`, `security`, `qa`, `documentation`, `product_ops`, `test_delta`
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

- Current-source reconciliation: Main `6fa9a9b55`; open #659 replaces the hosted document runtime and overlaps the adapter. Keep this change focused and reconcile the adapter before readiness if that PR lands.
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
