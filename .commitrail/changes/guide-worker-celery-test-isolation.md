# Guide worker Celery test isolation

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Guide worker tests restore shared Celery settings so the prefork timeout proof is independent of earlier eager-mode tests.

## Intent

Keep the hosted guide-worker lane trustworthy when it runs the full selected test order. The timeout test must execute the stubborn provider and prove hard-limit acknowledgement and durable uncertainty.

Complete backend checks also exposed a merged catalogue fingerprint mismatch: `test_setup_checker_scope.py` is correctly registered in the shared family, but its independent test still expects the prior membership. Reconcile that assertion without changing lane membership.

## Current behavior

`backend/tests/projects/guide_compilation/test_live_worker.py` enables eager mode before importing the cached shared Celery app. Its fixture clears `get_settings` but leaves the app configuration eager after teardown. The later `test_prefork_hard_timeout_acknowledges_without_reinvocation` in `test_worker_topology.py` can reject before invoking its provider, while that test passes alone.

## Bounded change

### Allowed

- Guide compilation test fixtures and focused assertions in `backend/tests/projects/guide_compilation/`.
- The independent shared-family fingerprint assertion in `backend/tests/test_ci_lane_catalogue.py`.
- This change record and a current documentation correction only if the repair changes a capability claim.

### Not allowed

- Production Celery, topology, worker or provider changes; timeout or guard weakening; CI selection, catalogue membership or workflow changes; remote service changes.

## Design and decisions

Synchronize the cached task app with each fixture's selected settings using the existing `sync_task_settings` owner. Restore the app after the eager fixture and assert the topology fixture begins in broker mode. Keep the timeout and provider-invocation assertions intact.

Refresh only the independent shared-family count and digest for the already merged `test_setup_checker_scope.py` member. The old digest matches the current membership with that one member removed; project and task fingerprints remain exact.

## Acceptance criteria

- [x] Ordered pair reproduces failure on current `origin/main` with PostgreSQL.
- [x] Ordered pair passes after the repair and reaches the stubborn provider once.
- [x] Affected guide-worker lane passes with its existing guards and assertions.
- [x] The shared-family fingerprint rejects a missing member and passes with the merged catalogue.

## Risk and review routing

- Risk class: L1 (test custody for a worker timeout boundary).
- Required reviewers: `ci_integrity`, `test_delta`.
- Human review focus: Fixture restoration of cached Celery app settings, fidelity of the ordered regression, and the independently verified catalogue fingerprint.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Ordered baseline failure | PostgreSQL isolated runner with named ordered pair at `7f6a71a69` | First node passed; timeout node failed `DID NOT RAISE ExceptionWithTraceback` | Reproduces the reported order only |
| Ordered repair | Same runner and named pair with fixture changes | Both passed; existing provider marker and durable status assertions remained | Full hosted lane is still required |
| Affected modules | Isolated PostgreSQL runner on both changed modules, excluding the separate Redis transport test | 25 passed; Redis test remains for full lane | Full lane must run with its own Redis and MinIO services |
| Full affected lane | `project_lifecycle_c` on `da52741c84` with isolated PostgreSQL, Redis and MinIO; both changed test files are AST-identical to the final pushed source | 436 passed, 0 skipped, 0 deselected; exit 0 in 1426.17 seconds under the 1500-second cap | Hosted aggregate remains a separate required check |
| Merged catalogue drift | #666 `schema_contracts` artifact at `f9a5f5954` plus independent inspection of merged `origin/main` | The fingerprint test failed `259 == 258`; removing only merged `test_setup_checker_scope.py` reconstructs the old count and digest exactly | Complete aggregate still required |
| Fingerprint repair | Complete catalogue test module with the shared dependency lock; in-memory missing-member mutant | 58 passed; the missing-member mutant failed the same independent assertion; Ruff lint and format passed | Combined branch and hosted aggregate remain required |

## Review findings

Exact-head `ci_integrity` and `test_delta` review is required before PR readiness.

## Reconciliation

- Current-source reconciliation: Based on `origin/main` at `7f6a71a69`; no production or capability behavior changes.
- Next usable boundary: None.
- Remaining risks: Hosted full backend aggregate remains a required PR check.
