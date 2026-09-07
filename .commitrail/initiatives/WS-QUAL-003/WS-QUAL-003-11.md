# WS-QUAL-003-11 — Replay proof consistency

- Initiative: WS-QUAL-003
- Durable disposition: Complete
- Intended merge outcome: realistic replay lookup proof and explicit retained-case rationale, without pausing independent product implementation.

## Intent

Correct permissive fixtures found by the follow-up audit. Test quantity and green
coverage are not evidence that each case earns its maintenance cost.

## Current behavior

Submission-policy repository fixtures return an existing operation from namespace
fallback while reporting that same operation missing. Five cases therefore pass
even if operation lookup is removed. Sufficiency tests manufacture disappearance
after an insert or conflict without a supported deletion/transaction boundary.

## Bounded change

### Allowed

- This record, `OVERVIEW.md`, and records `WS-QUAL-003-09.md` and `WS-QUAL-003-10.md`.
- `backend/tests/projects/submission_policy_mutations/test_repository.py`.
- A rationale table in this record covering the existing submission-policy family.
- `backend/tests/projects/sufficiency_mutations/test_replay_repository.py`.

### Not allowed

Production, schema, migration, CI, coverage-floor, public-interface, real
PostgreSQL-test or product implementation changes. No AUTH race repair here.
Do not edit the product worktree or make this cleanup its prerequisite.

## Design and decisions

Exact-operation fixtures resolve that operation and prohibit namespace fallback.
A separate different-operation/same-human-key conflict proves legitimate fallback
and exact selectors. Preserve existing SQL predicate proofs independently.
Remove the two unsupported disappearance simulations, not production guards.
Replace them with realistic same-actor/key pending and committed conflict
classification and changed-request rejection. The merged hosted coverage has
never entered this repository's conflict classifier (lines 94, 105, 106), while
covering the two impossible disappearance simulations. This is a distinct missing
behavior boundary, not a request to recover coverage through arbitrary faults.
Retain create/update identity and reservation-disposition matrices: these public
entry points have separate orchestration and error propagation, so each must
reject every listed substitution/state. Shared helpers alone do not establish
entry-point equivalence. Retain system/project scope crossed with both commands
because persisted action and grant provenance differ. Reject count-driven pruning.

## Acceptance criteria

- Exact pending/committed operation tests fail if operation lookup is bypassed.
- Changed operation facts deny without namespace fallback.
- A different operation in the same human namespace denies; fallback selectors
  and lookup order are exact, and insertion lookup is unused.
- Removing fallback is detected by that conflict test, not by fixture setup.
- Unsupported disappearance cases are removed with their proof limits recorded;
  real contention, rollback and completion guards remain tested and unchanged.
- Sufficiency conflict controls resolve the exact actor/action/key request and
  distinguish pending, committed and changed request digest without row insertion.
- Each retained submission-policy test has a rationale; parameter matrices name
  their distinct branches or deliberate interactions, without claiming all guards.
- Changed modules remain below 500 lines and tests below 120 lines.

## Risk and review routing

- Risk class: L1, bounded authorization-adjacent test evidence.
- Required reviewers: combined QA/test-delta; security for retained substitution
  rationale; documentation and CI-integrity for removal/coverage custody.
- Human review focus: meaningful proof, honest limits, no product pause.

## Evidence

Local: focused submission-policy and sufficiency repository tests, joint family
collection, Ruff, Commitrail validation, Markdown links, stale wording and diff
checks. Out-of-tree targeted mutations must distinguish missing operation lookup
and missing fallback. Hosted Backend owns full-suite PostgreSQL execution,
canonical node inventory, global coverage and unchanged per-file 90% floors.
Exact-head results belong in the PR, not as transient status in this record.

## Review findings

The prior audit exposed fixture inconsistency, not a demonstrated runtime defect.
Controlled SQL ports establish query composition and classification only; they
do not establish database isolation or exhaustive rejection of every custody field.

## Retained-case rationale

The submission-policy family has 35 named tests / 86 expanded cases after this
correction. This table is a bounded audit disposition, not a claim that the whole
repository or every production predicate has been tested. Names are exact;
paths are under `backend/tests/projects/submission_policy_mutations/`.
All existing cases are retained; repository fixtures are strengthened and one
legitimate namespace-only conflict is added. Pure schema/hash, service-port and
SQL-composition proof must not be relabeled as database/transaction proof.

| Module / test | Cases | Why retained / assertion boundary |
| --- | ---: | --- |
| public_routes / `test_public_mutation_conceals_service_before_owner_lookup` | 2 | POST and PATCH are separate routes; exact concealed error and owner non-call |
| public_routes / `test_invalid_key_precedes_actor_resolution` | 4 | Each route rejects absent and malformed keys before actor resolution; missing header and parsing are distinct failures |
| public_routes / `test_create_schema_rejects_malformed_snapshot` | 1 | Reject malformed snapshot UUID at schema boundary |
| public_routes / `test_create_schema_rejects_empty_policy_version` | 1 | Regression for repaired nonempty creation identity, not a second UUID case |
| public_routes / `test_update_schema_rejects_invalid_precondition` | 4 | Missing/invalid CAS digest and missing/empty successor version are four independent schema constraints |
| authority / `test_human_authority_requires_covered_grant` | 3 | Fixed-service decision, missing grant and foreign project each reject at human-authority guard |
| authority / `test_unsupported_prepare_forwards_exact_denial` | 1 | Unsupported action delegates exact denial and propagates its exception |
| authority / `test_replay_delegates_exact_custody_without_transaction_ownership` | 2 | Reserve and complete have different argument contracts; both remain caller-transaction owned |
| authority / `test_replay_requires_active_root_transaction` | 3 | Missing, inactive and nested transactions violate distinct root requirements |
| authority / `test_invalid_human_replay_facts_never_reach_repository` | 3 | Invalid action, request/resource mismatch and absent human key sample three validation stages; not every operand |
| authority / `test_fixed_service_replay_preserves_exact_custody` | 1 | Positive service path forwards run/task/correlation without human key |
| authority / `test_fixed_service_replay_rejects_changed_custody` | 3 | Run, task and correlation substitutions reject independently; not exhaustive service-fact validation |
| commands / `test_mutation_stages_exact_policy_provenance` | 4 | Intentional create/update × system/project grant interaction; persisted action/scope and predecessor provenance differ |
| commands / `test_mutation_binds_exact_prepared_facts` | 2 | Create and update use different routes, derived identities, CAS and successor facts; full fixture-owned equality |
| commands / `test_consume_failure_precedes_product_and_replay_effects` | 2 | Each command must reach consume with no staged product or replay calls; exception has no subsequent effects |
| commands / `test_changed_locked_lineage_denies_before_consume` | 2 | Each command revalidates locked generation; asserts prepare occurred and consume did not |
| commands / `test_unclaimed_replay_prevents_product_mutation` | 4 | Both entry points propagate pending/mismatch and forbid successor/supersession/completion; intentional action/error interaction |
| replay / `test_committed_replay_returns_original_without_mutation` | 2 | Both commands return exact stored response; update independently requires predecessor lookup |
| replay / `test_replay_requires_current_pm_admission` | 2 | Both entry points reauthorize exact covered PM before replay/product lookup |
| replay / `test_replay_rejects_substituted_identity` | 8 | Both commands must reject each actor/link/project/guide substitution; action/identity interaction retained deliberately |
| replay / `test_replay_rejects_changed_resource_digest` | 2 | Both commands reject changed canonical context, separate from scalar identity substitution |
| replay / `test_pending_replay_never_returns_success` | 2 | Pending records have no committed payload; both commands deny without reserving or consuming |
| lineage / `test_lineage_loads_exact_owner_context` | 2 | Read and locked paths use different owner selectors; exact facts/order, not physical row-lock proof |
| lineage / `test_missing_lineage_denies` | 4 | Missing project, guide, setup and report are distinct owner stages with precise errors |
| lineage / `test_incompatible_lineage_denies` | 6 | Foreign guide, active guide, changed snapshot, changed setup hash, report generation and immutable predecessor sample distinct guard stages |
| lineage / `test_warning_acknowledgement_digest_binds_exact_provenance` | 2 | System/project acknowledgement scope changes exact hashed provenance |
| lineage / `test_unacknowledged_warning_blocks_policy_mutation` | 1 | Complete material provenance with null acknowledgement cannot authorize warnings |
| lineage / `test_warning_acknowledgement_rejects_foreign_project` | 1 | Otherwise valid acknowledgement cannot authorize another project |
| repository / `test_reservation_classifies_existing_exact_row` | 2 | Pending/committed rows resolve through exact operation; no namespace fallback or inserted-row reload |
| repository / `test_reservation_rejects_changed_operation_facts` | 3 | Same operation with changed request/key/action conflicts even when a namespace could differ; exact-operation precedence |
| repository / `test_reservation_rejects_different_operation_in_human_namespace` | 1 | Missing exact operation falls back to the same human key and rejects different operation; exact lookup order/selectors |
| repository / `test_reservation_insert_binds_exact_values` | 1 | Exact INSERT values/conflict clause and returned-ID reload, with neither conflict lookup |
| repository / `test_namespace_query_binds_exact_selectors` | 2 | Human and fixed-service namespaces require different exact SQL predicates/null semantics |
| repository / `test_operation_lookup_uses_exact_operation_predicate` | 1 | Real query construction selects operation ID, not row PK or namespace |
| repository / `test_completion_requires_exact_pending_row` | 2 | Exact pending UPDATE selectors distinguish matched completion from failed completion |

The sufficiency repository module removes two disappearance fault simulations
and adds three real-shaped conflict classifications (pending, committed,
changed request). Its claimed-row and completion success/failure controls stay.
The new controls test repository code through a controlled SQL port, not actual
uniqueness or transaction recovery. Production guards are preserved but those
unsupported fault branches intentionally lose incidental statement coverage.
Hosted coverage must still satisfy the unchanged floors; no exclusion is added.

These tables justify current retained behaviors, not exhaustive guard coverage:
`_replay_values` has additional independent context operands; aggregate lineage
conditions and stored transaction evidence still have audit work remaining.

## Reconciliation

- Current-source reconciliation: based on merged PR375; product POL-04A2 owns
  separate files. Coordinate the shared overview wording only.
- Next usable boundary: separate AUTH race diagnosis; no automatic start.
- Remaining risks: most repository tests still require semantic audit. Existing
  transaction proof limitations in record 10 remain open.
