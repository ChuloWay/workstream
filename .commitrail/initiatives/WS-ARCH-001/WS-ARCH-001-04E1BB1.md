# ARCH-04E1B-B1 — TASK-before-CHECKERS reservation custody

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Risk class: L1 — cross-owner concurrency and immutable evaluation lineage.
- Intended merge outcome: the existing evaluation reservation operation requires
  TASK-owned locking before CHECKERS custody and cannot advance an accepted task.
  Routing handlers, publication and authority remain unavailable.

## Intent and current-main discovery

Main `a77e8bdc` delivers REV-04C's hidden shared acceptance participant.
It locks TASK before staging acceptance and contribution effects. CHECKERS'
`EvaluationCoordinator.reserve_current_evaluation` currently takes its own
advisory/fence locks without first locking TASK. A later generation can therefore
race with terminal acceptance. The parent 04E1B-B contract already requires
closing this gap before routing handlers consume current results.

Implement that shared prerequisite first within 04E1B-B. Handler construction
and source publication remain the subsequent bounded portion; this is not a
second dispatcher, acceptance operation or new authorization action. Do not
claim live routing, automated acceptance or complete receipt custody.

## Allowed files and design

- `backend/app/modules/checkers/api/execution.py` and
  `checkers/execution_coordination.py`: required typed consumer-owned TASK lock
  port on the existing coordinator, invoked before CHECKERS reservation locks.
- `backend/app/modules/tasks/post_submit_routing/evaluation_guard.py`:
  TASK-owned project-qualified locking and exact immutable Submission selection.
  Narrow existing repository methods only if the owner query needs them.
- `backend/app/adapters/{checkers,tasks}/__init__.py`: explicit composition of the same
  coordinator and TASK guard. No optional guard or unguarded fallback constructor.
- Existing coordinator callers in CHECKERS execution tests, TASK routing tests,
  AUTH routing support and review queue persistence tests; add focused
  `backend/tests/tasks/post_submit_routing/test_evaluation_guard.py` and
  `test_evaluation_currentness.py`, with a cohesive helper if needed.
- Exact ownership/lane registrations and their expectation tests. Preserve caps,
  complete collection, isolation, negative assertions and failure propagation.
- This record, the parent 04E contract, affected current ARCH/AUTH/POL/REV/CON
  navigation, index, roadmap, README and canonical checker/TASK/review specs.
  Update local roadmap exports together only if present.

The owner graph remains TASK -> CHECKERS. CHECKERS receives its own structural
port through composition and never imports TASK implementation or contracts.
Lock the exact project/task before CHECKERS advisory key, fence and run. Check
fresh scalar state under the task lock, not an identity-map value read earlier.
Keep the caller transaction; reject root/savepoint misuse before locks can be
released independently. The required CHECKERS-owned guard returns a strict boolean indicating whether
new reservation is eligible after locking and verifying exact TASK custody.
`False` permits only a SELECT-only exact stored reservation replay; a missing or
changed request denies before the CHECKERS advisory/fence locks. There is no
optional guard. Even terminal replay requires the latest exact submitted
Submission and matching immutable owner lineage. Earlier evaluation-generation
replay for that same Submission retains its original identity and never restores
the current fence.

TASK locks Task -> exact project/task Assignment -> latest Submission. Verify
Submission status `submitted`, ID/version, assignment, contributor/assignment
ownership, binding/content IDs, and every guide/source/effective/pre/post/review/
revision field in request.expected_context against the existing immutable
SubmittedBundleReader projection. Compare the frozen Submission, not today's
project policy. ART continues to own digest/size and byte verification; this
new guard does not read ART or claim those checks.

Eligible TASK states are `in_progress`, `submitted`, `evaluation_pending`,
`review_pending`, and `needs_revision`, with the same active assignment.
`accepted`/`rejected` allow exact read-only replay only; all other states deny.
Expose one concealed `CheckerExecutionUnavailable` scope error for absent,
foreign, stale or inconsistent facts. Keep existing request-conflict errors
for changed envelopes that have valid owner custody. This prerequisite does not
activate execution or add TASK status transitions.

## Prohibited changes

No migration, public route, worker registration, AUTH allow/permission change,
false guide activation, source publication/current pointer, outbox event,
contribution/award mutation, artifact I/O, generic accepted transition or
compatibility path. Do not turn historical policy hashes into current-policy
selection. Do not fabricate false-policy activation or AUTH receipts in tests.
Contributor leases/skip remain deferred.

## Acceptance and verification

1. Valid initial reservation, exact replay, later generation and rollback retain
   their existing identities and caller-owned transaction behavior.
2. Independent PostgreSQL sessions prove acceptance winning first prevents a
   successor reservation; the winner uses the merged shared acceptance owner
   and a genuine retained human Review storage fixture, not a hand-written
   terminal status. This remains mechanical storage proof, not live authority.
3. Successor first causes the old completion's routing preparation to reject;
   observe the real task-lock wait before releasing the winner. No stale request
   or new acceptance facts may commit. Full authorized routing races remain a
   later handler/activation proof.
4. Valid foreign project/task/Submission substitutions deny before foreign
   checker locks or mutations. Wrong-project requests must not wait on a foreign
   task lock. Exact lineage, latest Submission and stale identity-map cases have
   meaningful controls and unchanged-state assertions.
5. Remove the TASK lock or terminal guard independently and show the intended
   PostgreSQL regression detects the defect rather than failing fixture setup.
6. Managed and raw savepoints cannot undermine reservation lock lifetime.
7. Preserve existing review queue supersession and replay proof. All callers
   use the required owner seam; there is no executable old constructor path.
8. Run focused PostgreSQL tests through the canonical isolated runner; Ruff,
   dependency/ownership/test-structure checks, stale wording, Markdown links and
   Commitrail checks; full hosted suite with zero skips/deselections.

## Review and human focus

Required plan and final tracks: architecture/reuse, security, QA/test-delta,
CI integrity for registrations, documentation/product operations. Review the
actual lock order and both race controls, exact replay semantics, root transaction
lifetime and the distinction between this prerequisite and activated routing.
Plan review required explicit exact-lineage predicates and terminal replay
semantics before implementation. Both were resolved in this record. The
architecture check required the CHECKERS adapter to consume the TASK adapter,
not import TASK private implementation. The guard-removal lock probe uses
`FOR NO KEY UPDATE NOWAIT` so a foreign-key KEY SHARE lock cannot mask a missing
TASK lock. Terminal replay is exercised while CHECKERS advisory/fence/run locks
are independently held, proving it neither locks nor rewrites those rows.

## Next boundary

Complete hidden request/completion handlers in the remaining 04E1B-B scope,
then exact authority/evidence closure at 04E2-B and live composition at 04E3.
True human admission remains independent of shared acceptance. False activation
still requires receipt/database/audit closure, lifecycle control and 04F
remediation. This change does not claim those prerequisites delivered.
