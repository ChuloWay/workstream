# WS-QUAL-003-12 — Exact historical projection decision proof

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: meaningful projection replay evidence and smaller shared test setup, without changing product authority or blocking product implementation.

## Intent

Continue the human-authorized behavior-first test audit. A missing decision is
not evidence that an existing but mismatched decision is rejected. Preserve
valuable protection, justify each retained case, and avoid a count-driven purge.

## Current behavior

`test_policy_and_replay.py` names a mismatched-decision test but supplies only a
random absent ID. `projection_replay_event_matches` validates eleven independent
stored facts; the absent-row test cannot detect removing any of those checks.
The exact-replay test exercises only the sufficiency adapter and repeats a
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

## Acceptance criteria and proof mapping

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

## Reconciliation

- Current-source reconciliation: main `369903ae` includes merged observer
  repair PR378. Product PR377 owns finalization, not this AUTH replay family.
- Next usable boundary: remaining AUTH monolith/actor-resolution audit and
  decomposition. This change does not complete those large-file obligations.
- Remaining risks: PostgreSQL integrity and owner-query isolation are separate
  proof boundaries; most repository tests remain unaudited.
