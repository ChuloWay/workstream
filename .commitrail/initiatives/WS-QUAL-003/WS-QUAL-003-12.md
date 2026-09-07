# WS-QUAL-003-12 — Staged AUTH test audit and decomposition

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: complete the selected projection, actor-resolution and AUTH test-family audit and decomposition through reviewed commit checkpoints, without changing product authority or blocking product implementation.

## Intent

Continue the human-authorized behavior-first test audit. A missing decision is
not evidence that an existing but mismatched decision is rejected. Preserve
valuable protection, justify each retained case, and avoid a count-driven purge.

## Human-authorized staged expansion

The human rejected ending this change at the projection-only slice and asked
for one larger AUTH cleanup PR with reviewable commit checkpoints. Preserve the
projection work below as stage A; do not create another PR for each fixture,
test family or correction. Completion now means finishing the broader selected
AUTH cleanup, not merely the original replay proof.

The stage sequence is:

1. Preserve the implemented projection replay proof and its retained-case map.
2. Inventory the actor-resolution and related AUTH monolith families, their
   shared helpers and consumers. Record every selected case's disposition and
   exact extraction destinations before changing it. Inspect product overlap.
3. Repair the deterministic first-access race proof: both requests must pass
   the initial miss, the contender must wait for the identity lock, and both
   must resolve the same persisted winner. This is hosted PostgreSQL proof,
   not two coroutines or a mocked lock presented as concurrency evidence.
4. Audit and decompose the selected oversized AUTH families into owner-scoped
   test/support modules. Remove genuinely redundant or obsolete proof only
   with named surviving protection; split mixed behaviors and correct real
   defects rather than making expectations accept them.
5. Reconcile the accumulated diff, case dispositions, structural-debt changes,
   selection and current main; run final hosted coverage and affected reviews.

Stages 2–4 are the discovery/implementation sequence, not an assertion that
their executable file/test maps already exist. The allowed files and acceptance
table below currently describe stage A only. Extend this same record with the
specific stage maps after discovery and plan review, before backend edits;
do not silently treat all AUTH files as allowed. This is scope refinement under
the human's expansion, not a new permission system or another planning PR.

Each stage ends in a coherent commit or small commit series, focused checks,
and impact-routed internal review against a frozen checkpoint. The human can
inspect each checkpoint independently. Do not edit a target while it is being
reviewed; batch valid fixes and replay affected findings before progressing.
Routine checkpoint review does not require a separate human merge or PR.
Commits are review boundaries, not a reason to trigger full CI for every tiny
edit: run focused local checks and use hosted runs for PostgreSQL stages and
the final combined head. Preserve checkpoint history while it is under review.

Final approval covers the complete PR, including cross-stage interactions;
earlier checkpoint results cannot be relabeled as final-head approval. Product
work remains independent. No forced test-count reduction, weakened CI, altered
authorization semantics or blanket repository-wide cleanup is authorized here.

## Baseline behavior

Before this change, `test_policy_and_replay.py` named a mismatched-decision test but supplied only a
random absent ID. `projection_replay_event_matches` validates eleven independent
stored facts; the old absent-row test could not detect removing any of those checks.
The old exact-replay test exercised only the sufficiency adapter and repeated a
two-service setup also present in authority-retirement and custody-guard tests.
The real kernel/PREP runs against controlled session, owner-lock and audit ports;
these tests do not execute SQL or establish real transaction isolation.

## Bounded change

### Allowed

- This record and `OVERVIEW.md`.
- Under `backend/tests/authorization/guide_compilation_projections/`:
  `support.py`, `test_policy_and_replay.py`, `test_replay_guards.py`, new
  `replay_support.py` and `test_replay_evidence.py`.
- `backend/scripts/test_lane_catalogue.py` and
  `backend/tests/test_ci_lane_catalogue.py`: exact new-module registration only.
  These are also touched by product PR377; preserve both registrations if its
  merge changes main. Do not edit the product worktree.

### Not allowed

Production code, public interfaces, action activation, migrations, database
reset changes, structural-debt exceptions, workflows, timeouts, thresholds,
skips, or other test families. No imports from the AUTH test monolith. No
mutation of immutable database evidence or bypassing triggers to fabricate
corruption. If the audit reveals a product defect, first document and review
the precise required scope correction; never rewrite expectations to hide it.

## Design and decisions

Extract only the duplicated two-preparation fixture into small same-owner test
support. Both preparations use fresh real PreparedAuthorizationService objects
with the same session/root transaction, actor and identity link. Honor the
fixed-service factory's request/correlation inputs rather than silently ignoring
them. Keep actual kernel/PREP matching; the fixture must not implement policy.
All modules stay below 500 lines, tests below 120 and helpers below 100.

Separate replay tests from the policy/matrix tests. Keep the absent-decision
negative under an honest missing-decision name. Parameterize the exact-replay
positive across the two adapters, with exact original decision lookup, no new
evidence and closure proof. Preserve both consumed-handle retirement cases.

For existing-decision substitution, first produce an actual allowed decision
through the real kernel/PREP. At the controlled audit-read port, return its
stored-shaped representation with exactly one field substituted, retaining the
original requested decision ID. Prove the lookup resolved an existing event
and returned the substituted representation, not None. This is a service-boundary
adversarial proof, not a claim that PostgreSQL permits immutable-event tampering.

The twelve cases exercise event type, actor, action, permission, project,
resource type, resource ID, request, correlation, allowed=False, allowed=1,
and resource digest. The two allowed cases distinguish denied outcome from
truthy non-boolean coercion. Use otherwise well-formed alternate values.
Do not cross all twelve cases with both adapters: the predicate is shared;
both adapter paths receive independent positive wiring proof instead.
No new database test is needed for that bounded service claim. Existing hosted
projection atomicity/concurrency tests remain unchanged and must still pass.

## Acceptance criteria

| Behavior | Named proof | Custody |
| --- | --- | --- |
| Exact original evidence authorizes replay for each component, without new evidence | `test_projection_exact_replay_uses_original_decision` (two components) | Real kernel/PREP, controlled ports |
| Missing decision denies without new evidence and closes | `test_projection_replay_rejects_missing_decision_without_new_evidence` | Controlled audit lookup returns None |
| Each of twelve existing-event substitutions independently denies; exact existing ID lookup occurs | `test_projection_replay_rejects_substituted_existing_decision` (named cases) | Existing kernel-produced event, one changed returned fact, real matcher |
| Denied replay retires its authority and cannot subsequently consume | Same substitution test: coupled fail-closed outcome | Real handle registry/sealed authority; no new event |
| Successful replay cannot consume either identical or changed next facts | Existing `test_projection_replay_retires_mutation_authority` | Both existing cases retained |
| Listed action/binding/transaction/scope mismatches and owner resource guard deny | Existing `test_replay_guards.py` tests | Existing cases retained; rename “every” to “listed” |
| Policy action/identity/matrix/output guards remain | Existing four non-replay policy tests | Assertions and parameters preserved |
| Missing matcher operand is actually detected | Process-local operand-removal probes | Each event predicate mutant must fail its named negative, not setup |
| Selected tests and full safety baseline remain | Catalogue tests; hosted Backend | Exact inventory, no skips/deselection, unchanged coverage floors |

## Risk and review routing

- Risk class: L1, bounded authorization test evidence.
- Required reviewers: plan review before implementation; QA/test-delta,
  security/reuse for exact evidence and shared setup, CI-integrity/documentation
  for selection, custody and honest claims. Related tracks may share an agent.
- Human review focus: substitutions hit real guards; fixture coherence; every
  retained case earns its cost; no product pause or blanket audit-complete claim.

## Evidence

Local: `backend/.venv/bin/pytest -q` for this AUTH projection directory and lane
catalogue, focused Ruff, root Commitrail, Markdown-link, stale-wording and diff
checks. Collect the changed family and compare named/expanded cases before and
after. Use out-of-tree process-local mutants; do not commit a mutation framework.
GitHub Backend exclusively owns full coverage and existing real PostgreSQL
projection concurrency/rollback execution. SQL-port proof remains separate.

## Review findings

Discovery confirms a missing proof, not a demonstrated production bypass.
Deleting the random-ID test would also lose missing-row coverage, so rename and
retain it while adding the distinct existing-row substitution boundary.
Plan review confirmed fixture feasibility and required the canonical acceptance
heading (PLAN-12-001); that mechanical correction is applied.

## Retained-case rationale and replacement map

The changed family has 21 expanded cases before this change and 34 afterward.
No behavior is deleted or skipped. Thirteen additions are twelve independently
failing stored-fact substitutions and one second-adapter positive; the shared
predicate does not receive a redundant Cartesian product with both adapters.

| Existing test suffix / cases | Disposition and distinct purpose |
| --- | --- |
| `artifact_policy_projection_uses_only_its_existing_action` / 1 | Keep exact action, permission and authority digest separation |
| `projection_requires_exact_project_setup_authority` / 6 | Keep wrong service, suspended actor and revoked link for each adapter; these are distinct identity guards |
| `projection_requires_active_action_matrix` / 4 | Keep absent matrix row and unavailable action for each adapter; neither implies the other |
| `policy_projection_rejects_wrong_deterministic_output` / 1 | Keep the caller's wrong output identity rejection |
| `projection_exact_replay_uses_original_decision` / 1 | Move to `test_replay_evidence.py`; retain digest parity and add artifact-policy wiring, exact lookup and evidence fields |
| `projection_replay_retires_mutation_authority` / 2 | Move; keep both unchanged and changed next-fact attempts after successful replay |
| `projection_replay_rejects_mismatched_decision_without_new_evidence` / 1 | Rename to `projection_replay_rejects_missing_decision_without_new_evidence`; an absent ID proves absence, not substitution |
| `projection_replay_rejects_every_prepared_custody_mismatch` / 4 | Rename `every` to `listed`; retain action, caller binding, replaced transaction and scope guards |
| `projection_replay_rejects_project_setup_resource_guard` / 1 | Keep owner-resource rejection, separately from handle custody |

All suffixes above have the `test_` prefix. The four non-replay policy tests
retain AST-identical bodies and parameter sets. Repeated original/replay
preparation is replaced by `ReplayCase`, not a second authorization evaluator.
The historical AUTH-12J pre-cutover contract's old `every` and `mismatched`
references resolve through this map; the historical snapshot is not rewritten.
The two old test modules shrink from 480 to 257 lines; with the new 84-line
support, 174-line evidence module and two net support lines, this family grows by
37 lines (685 to 722) to cover the missing behavior. This is proof repair, not a claimed
test-count or source-volume reduction.

The new negative cases each substitute only one returned fact of the exact
existing decision. They assert denial, spent authority, no new event and an
unchanged deep snapshot of the original evidence; a mutable alias cannot stand
in for an immutable comparison. Successful replay checks each adapter's
explicit action/permission/resource shape, rather than deriving all expected
values from the implementation under test.

## Reconciliation

- Source reconciliation: discovery used main `369903ae`, including merged
  observer repair PR378. Integrated base `8c00fb3d` also includes PR376's
  Commitrail contribution-path simplification. Product PR377 owns finalization,
  not this AUTH replay family.
- Next usable boundary within this change: map the actor-resolution and AUTH
  monolith stages above. The projection slice does not complete those
  large-file obligations and is no longer the whole intended merge outcome.
- Remaining risks: PostgreSQL integrity and owner-query isolation are separate
  proof boundaries; most repository tests remain unaudited.
