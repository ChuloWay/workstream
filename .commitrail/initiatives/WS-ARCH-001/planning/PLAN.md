# WS-ARCH-001 — Current delivery plan through allow_review

## Current dependency contract

This section and the corrected pending child contracts are the current
cross-initiative delivery order. Completed records and review notes preserve
their original evidence; they do not restart superseded work. The stop point
of this reconciliation is canonical `allow_review`; downstream REV execution
is not redesigned here. 04F is documented only to preserve the required later
checker-remediation boundary before public Submission cutover.

| Boundary | Hard predecessors | Sole output owner |
|---|---|---|
| POL-04B | Merged POL-04A/04A3/04A2, AUTH-12I/12J/12B2 | PROJECTS live unified setup wiring, no new compiler/finalizer |
| CP05 | Merged CP04A/CP04B | AUTH exact policy-action activation |
| CP06 | CP05 | CON selected-version validation facts |
| CP07 | CP06 | PROJECTS hidden activation/binding command and replacement readiness guard |
| ARCH-04A | Merged canonical CHECKER catalogue and unified compilation contracts | CHECKERS post-phase public facts and registered evaluator conformance, no live run |
| POL-05A | POL-04B | PROJECTS hidden effective/pre approval and separate immutable operation provenance |
| AUTH-12F4 | POL-05A | AUTH approval adapter |
| POL-05B | POL-05A, AUTH-12F4 | PROJECTS live pre-policy approval |
| POL-06A | POL-05B | PROJECTS hidden post-policy projection/approval/correction provenance |
| AUTH-12G | POL-06A | AUTH exact post-policy action adapters |
| POL-06B | POL-06A, AUTH-12G | PROJECTS live post-policy configuration, zero evaluator calls |
| POL-07 | POL-06B, ARCH-04A, merged ART pre executor | One facade over ART pre and CHECKERS post contracts; no new persistence |
| AUTH-12H | POL-07, CP07, merged AUTH-12B2 | Exact authority and live composition for the CP07 guide activation command |
| CP08 | CP07 | TASK-owned policy-lineage fields and public facts, no readiness commands |
| ARCH-03A | AUTH-12H, CP08 | PROJECTS current active-generation public facts |
| ARCH-03B | ARCH-03A, CP08 | TASK readiness/claim/assignment/Submission command lineage |
| ARCH-03C | ARCH-03B | AUTH exact task/assignment activation and integrated readiness proof |
| CP09 (later cleanup coordination) | All legacy consumers replaced, including CHECKER and public 02I path | Physical economic deletion; not on the allow_review critical path |
| ARCH-04B | ARCH-04A, POL-07, ARCH-03C, merged ARCH-02H | ART exact stored Submission materialization |
| ARCH-04C | ARCH-04A, ARCH-04B, POL-07 | CHECKERS durable execution/result/currentness and worker recovery |
| ARCH-04D | ARCH-04B, ARCH-04C | AUTH post-submit materialization/result activation |
| ARCH-04E | ARCH-04D | TASK dispatch and canonical current routing manifest |
| ARCH-04F (later public-cutover prerequisite) | ARCH-04E | CHECKER failure facts and TASK/ART remediation resubmission, not REV |

POL-04B, CP05 and ARCH-04A have independent prerequisites. Their owners may
work concurrently if allowed paths do not overlap; shared catalogue/schema
changes must be serialized or rebased, not implemented twice. CP08 can proceed
after CP07 while policy setup finishes; it does not activate claims. Subsequent
PR-sized contracts name exact files, public types, current migration head and
runnable proof before implementation; they refine this design, not create a
new permission requirement.

Required capability support is a real prerequisite, not an optimistic label.
The current structural post-submit catalogue is not proof of substantive work
evaluation. ARCH-04A owns the missing registered capability/conformance work
for the bounded release use case. If a new capability changes the catalogue,
an old setup generation cannot adopt it in place: compile and approve a new
generation from that exact snapshot. Unknown required checks block the affected
guide; they never become permissive fallback checks.

### One mutation owner per boundary

- ART compiles/executes intake and owns admission/materialization/binding.
  POL consumes its default-plus-project compiler; it does not fork it.
- PROJECTS owns proposal/approval/activation and separate downstream operation
  records. A finalized setup row/receipt is immutable; approval is not another
  finalization or an in-place continuation of its closed row.
- CHECKERS owns registered work evaluation, durable attempts/results and
  currentness. POL-07 owns only facade composition. TASK projects the current
  recommendation, not a second checker decision.
- CON validates the explicitly chosen immutable policy; PROJECTS binds it on
  activation. CP08 owns TASK lineage schema, ARCH-03B writes it. Neither CON
  nor AUTH calls back into PROJECTS activation.
- ARCH-04B/04D/04F replace historical ART-06A, XINT-06B/AUTH-14 and XINT-05C
  respectively; those old plans do not open parallel implementation lanes.

### Feasibility and falsification proof for future implementations

For each row, prove its output using only predecessor outputs and controlled
owner fixtures; do not seed future live authority to make a fixture pass.
In particular: activate a guide without a Task/CheckerRun/legacy PaymentPolicy;
deny missing review/revision configuration and required checker gaps; keep
finalization byte-for-byte unchanged across approval/correction/replay; reject
a structurally valid but substantively failing artifact through the selected
work evaluator; preserve mandatory defaults; reject cross-generation intake
evidence reused as post-submit evidence. AUTH denial before I/O means no read;
late revocation after I/O means no final current result/routing, not impossible
retroactive removal of an already-authorized read. Prove crash/retry identity,
atomic outbox/result/manifest custody and independent-session races in the
owning implementation, not with planning prose or fake database claims.


## Historical continuity and implementation scope

### Named proof targets for the remaining design

These are required future implementation tests, not tests claimed present or
executed by this planning PR. Each owner's bounded record fixes the final
module path alongside implementation; the symbols preserve the behavioral
obligation. Run them through `cd backend && uv run pytest <owner-test-file>`
and the unchanged hosted suite/coverage gates. Database, I/O and concurrency
claims require their real custody, not unit substitutes.

| Owner boundary | Future proof symbol(s) | Required custody / counterexample |
|---|---|---|
| POL-04B | `test_live_setup_uses_only_unified_attempt`, `test_finalization_replay_makes_zero_provider_calls` | Real API/worker composition and PostgreSQL; legacy call injection must fail |
| POL-05A/05B | `test_approval_preserves_finalized_setup`, `test_effective_intake_keeps_platform_defaults` | PostgreSQL rollback/race plus canonical ART compiler; attempted default removal and mixed hash deny |
| POL-06A/06B | `test_post_policy_operation_preserves_finalization`, `test_post_projection_never_invokes_evaluator` | PostgreSQL provenance and provider-call spy; stale upstream approval denies |
| ARCH-04A/POL-07 | `test_registered_evaluator_rejects_invalid_work`, `test_checker_facade_delegates_once` | Actual registered evaluator fixtures and typed composition; presence-only mutant must fail |
| CP06/CP07/AUTH-12H | `test_activate_without_legacy_payment_or_task`, `test_activation_requires_exact_selected_policy`, `test_activation_rejects_missing_review_revision_config` | PostgreSQL atomic command plus full response serialization; foreign/retired/incomplete new binding denies |
| CP08/ARCH-03A/03B/03C | `test_ready_preserves_screening_policy_lock`, `test_claim_copies_policy_without_current_lookup` | PostgreSQL and actual AUTH/owner composition; later publication leaves existing attempt unchanged |
| ARCH-04B/04C/04D | `test_exact_post_materialization_denies_before_io`, `test_late_revocation_cannot_publish_result`, `test_checker_retry_reuses_attempt` | Local/MinIO, real worker/provider contract, PostgreSQL races; independent sessions and staged/final state |
| ARCH-04E | `test_submission_to_current_allow_review`, `test_superseded_run_cannot_route`, `test_duplicate_dispatch_has_one_manifest` | Real DB/worker/storage path, exact authority-event references; no REV row or product accept decision |

Owner-local schema names and migrations are chosen from the then-current
baseline in the same implementation PR. No migration numbers or future
runtime success are invented here.

The [preserved plan](../pre-cutover/PLAN.md) retains the complete original
architecture/debt and downstream REV/CON history. It is not the current
dependency order. Current [chunk map](CHUNK_MAP.md) and the corrected child
contracts in this directory supersede conflicting pending sequencing there.
Unchanged predecessor evidence remains in the preserved records; no completed
work is repeated. No backend capability, route or authorization is activated
by this planning update.

Each implementation uses one bounded change record in its existing initiative,
expanded from these current contracts with exact files, current schema head,
proof commands and affected reviewers in the same implementation PR. No
additional planning-only PR or administrator permission is implied by that
expansion. Human approval and merge remain GitHub responsibilities.
