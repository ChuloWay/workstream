# WS-QUAL-003-08 — Deterministic mutation execution-fence proof

- Initiative: WS-QUAL-003
- Durable disposition: Complete
- Intended merge outcome: Isolate and strengthen execution-fence delegation and
  cleanup proof without changing production or claiming mocked database locks.

## Intent

Continue the PROJECT mutation audit after PR #372. The mixed
`test_sufficiency_mutation_fail_closed_internal_guards` in `test_projects.py`
contains only invalid-engine and false-acquisition fence checks. Its remaining
authority, lineage and replay assertions are outside this slice and preserved.
The sufficiency and submission-policy `_execution_fence` methods both derive a
signed advisory key, acquire on a dedicated connection, yield only on literal
True, and release in finally. No focused test currently proves that sequence.
PR #372 coverage also exposed incidental coverage of submission policy's signed
key conversion; deterministic boundary inputs must replace that uncertainty.

## Bounded change

Allowed files:

- This record and `OVERVIEW.md`: outcome and next audit boundary.
- `backend/tests/test_projects.py`: remove only the two execution-fence checks
  and their dedicated fake classes; preserve the rest of the mixed test.
- `backend/tests/projects/execution_fence_fixtures.py`: small explicit service
  variants and standard mock connection harness, no copied fence algorithm.
- `backend/tests/projects/test_execution_fence_binding.py`: engine, exact digest
  input, signed key and acquisition SQL delegation proof.
- `backend/tests/projects/test_execution_fence_lifetime.py`: denied acquisition,
  successful body, exception/cancellation and release ordering proof.
- `backend/scripts/test_lane_catalogue.py` and
  `backend/tests/test_ci_lane_catalogue.py`: register both complete modules in
  the existing PROJECT owner pair and its exact membership test.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: canonical changed spans/hashes,
  no new or enlarged debt.

Not allowed: production, migrations, workflow/coverage changes, grants, routes,
dependencies, conftest, real database tests, AUTH race repairs or other monolith
assertion removal. No helpers imported from collected test modules.

## Design and acceptance criteria

Use explicit standard mock ports, with the real service context manager invoked.
Both service variants must execute each applicable proof independently.
Each new test has one primary behavior and each module stays below 500 lines.

| Behavior | Named future proof |
| --- | --- |
| Invalid engine cannot enter work | `test_fence_rejects_non_async_engine` |
| Digest binds exact domain, actor, action, operation key | `test_fence_hashes_exact_identity` |
| 0, signed maximum, signed minimum, and -1 key conversion | `test_fence_delegates_exact_signed_key` |
| False, None, and truthy non-True acquisition cannot enter work or unlock | `test_unacquired_fence_never_enters_work` |
| Acquisition exception propagates unchanged without work or unlock | `test_acquisition_failure_propagates` |
| Successful work runs after acquire, before same-connection unlock/exit | `test_fence_releases_after_success` |
| Body exception propagates unchanged after unlock | `test_fence_releases_after_body_failure` |
| Body cancellation propagates after unlock attempt | `test_fence_releases_after_body_cancellation` |
| Unlock error propagates; connection exit is still attempted | `test_unlock_failure_propagates` |

Exact expected SQL/key arguments and event order are independent assertions,
not a fake that enforces the desired behavior itself. Digest-input and signed
conversion tests are separate: inject explicit hash prefixes for conversion,
capture exact canonical payload separately. Do not use random inputs to claim
the signed branch is covered. Mocks do not prove PostgreSQL contention, rollback,
crash release, physical connection closure or cancellation during unlock itself.
Existing hosted real-database protection is retained, not replaced by these tests.

## Risk and review routing

- L1: mutation fence proof and full-suite selection.
- Plan: feasibility and honest mock/database boundary review.
- Final: QA/test-delta, security/CI-integrity, architecture/reuse (fixture boundary).
- Human focus: exact key/ordering oracles; no deleted real concurrency protection.

## Evidence

Run the old mixed test before extraction; then new modules, retained mixed test,
and catalogue tests locally. Run Ruff, canonical ledger inventory/validation,
Commitrail, links, stale scans and diff checks. Hosted CI owns full PostgreSQL,
all-node manifest reconciliation and coverage floors. No full local suite.
Independent controls must pass; temporary omitted unlock, truthy-acquisition,
wrong signed-key and wrong digest-field mutants must fail at assertions, not
setup errors. Unrelated definitions and retained mixed-test statements must
remain AST-identical except the named removed checks and unused parameter.

## Review findings and measured proof

Plan review traced both real service implementations and confirmed feasible
independent controls for every proposed case. The standard mock harness only
records calls/events and returns configured values; test assertions define the
expected identity, SQL arguments and cleanup order.

The original mixed test passes. The two new modules, retained mixed test and
catalogue tests pass 55 cases. The 28 new expanded cases add deterministic proof;
no whole test node or real database case is removed. The monolith shrinks by 35
lines; remaining mixed-test statements and all unrelated monolith definitions
are AST-identical. New modules are 76 and 113 lines with a 64-line support file.

Out-of-tree probes start from passing controls and inject wrong signed-key
conversion, substituted actor identity, truthy acquisition acceptance and missing
unlock delegation. Each defect fails a named assertion for both service variants.
No mutant is committed. Actual task cancellation inside the protected body
proves unlock/connection-exit attempts before the same cancellation escapes;
this is not proof of physical database cleanup or cancellation during unlock.

## Reconciliation

- Current source: main `5e27af60`, merged diagnostic proof slice 07.
- Next usable boundary: remaining mixed PROJECT mutation guard/replay tests,
  then AUTH's recorded race diagnosis before routine AUTH decomposition.
- Remaining risks: most test bodies remain unaudited; no full cleanup claim.
