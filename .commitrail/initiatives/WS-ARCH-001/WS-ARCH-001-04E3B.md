# WS-ARCH-001-04E3B — First-layer automatic acceptance activation

- Initiative: `WS-ARCH-001`
- Durable disposition: Planned
- Intended merge outcome: A manager can activate a complete guide with locked `human_review_required=false` and supported exact checks, while the existing production completion route can create the authorized FinalAcceptance and submitter ContributionRecord after REV is live.

## Intent

Open the existing first backend journey from approved guide through the governed false-policy outcome. A complete false-policy guide is currently blocked even though TASK already routes successful selected POST completion through REV's shared acceptance participant and CON's submitter record. Preserve the default-true human-review branch, exact checker capability custody, and contributor-correctable versus infrastructure failure distinction.

## Current behavior

`ProjectService.validate_activation_ready` rejects every false ReviewPolicy. `GuideActivationService._readiness` already verifies the approved PRE/POST policies, every exact registry entry and its digest, and the absence of capability suggestions before calling that guard. The saved compilation result can separately contain a `human_review` requirement with no capability suggestion, so false-policy admission needs an explicit disposition check.

The canonical `require_guide_activation_custody(operation, true)` PostgreSQL function in `backend/alembic/baseline/v01_schema.sql` also requires `review_policies.human_review_required=true`. The immutable approved requirement inventory is in `project_guide_compilations.canonical_result`, selected by the activation command's `target.proposal.compilation_id`, `result_hash` and `component_hashes`; SQL must enforce the same false-mode `human_review` denial as Python. Current false-policy test setup patches Python readiness and disables three database triggers, then re-enables them; it cannot prove real activation. The selected production OUTBOX registry already installs request and completion handlers. Completion delivery uses TASK's authorized routing manifest; false/pass takes a live REV generation and the shared FinalAcceptance/TASK/CON transaction, with no Review. REV's `FIRST_CONTRIBUTION_MANIFEST_DIGEST` still declares production routing unavailable even though selected production composition and PostgreSQL tests exist. `complete_context` validates locked lineage but explicitly does not rerun eligibility; the required acceptance-time disposition check is therefore still absent.

## Bounded change

### Allowed

- `backend/app/modules/projects/service.py` and `backend/app/modules/projects/guide_activation/service.py`: replace the false-policy blanket refusal with exact false-only denial of approved `human_review` dispositions; retain all other source, policy, selected registry, approval, authority and capability checks.
- `backend/app/modules/projects/locked_policy_projection.py`: recheck that the same immutable approved result contains no `human_review` disposition when resolving a false-policy locked context for TASK execution; fail closed through the existing PROJECTS context port without adding another policy or TASK-owned project query.
- `backend/alembic/versions/0037_false_guide_activation.py` (or the next available exact revision after source reconciliation): change only `public.require_guide_activation_custody(uuid, boolean)`'s new-binding ReviewPolicy predicate and persist a protected function search path. Use a counted known-clause replacement of the installed definition, qualify the new compilation lookup, preserve all other clauses and existing receipts, and admit a false policy only when its exact approved compilation is bound and has zero `human_review` dispositions. Replace exactly two old reviewed-manifest digest references in `public.joint_lifecycle_transition_valid(public.joint_lifecycle_transitions)` so PostgreSQL agrees with the corrected fixed REV manifest; retain the function's other custody clauses. Do not edit historical migrations or rewrite retained rows.
- `backend/app/modules/reviews/lifecycle/service.py`: correct the fixed reviewed manifest inventory for the already registered selected production routing writer, keeping human review, fulfillment and payment unavailable. The existing Operator-authorized adjacent transitions and current-generation fence remain the sole runtime enablement.
- `backend/app/modules/reviews/api/acceptance.py`, `backend/app/modules/reviews/acceptance/participant.py`, `backend/app/adapters/tasks/routing_acceptance.py`, `backend/app/modules/tasks/api/routing_outcome.py`, and `backend/app/modules/tasks/evaluation_completion_delivery.py`: carry one typed pre-effect non-live refusal from the held REV fence through TASK. After the routing root transaction rolls back, return shared OUTBOX `RETRY` only for that known no-effect refusal. All other handler exceptions remain UNKNOWN; do not change OUTBOX policy or invent redrive.
- `backend/tests/conftest.py`: update the expected PostgreSQL public-schema fingerprint for the changed canonical function; keep the reset integrity guard in force.
- `backend/tests/projects/guide_activation/pg_support.py`, `backend/tests/projects/guide_activation/test_rejections.py`, `backend/tests/projects/guide_activation/test_postgresql.py`, and `backend/tests/projects/guide_activation/test_contracts.py`: prove real authorized false activation/replay through the existing public operation, missing exact coverage, approved `human_review` denial in Python and SQL, temporary namespace shadowing, registry substitution, and default-true preservation against PostgreSQL with every trigger enabled.
- `backend/tests/projects/test_locked_policy_context.py` or `backend/tests/projects/test_locked_policy_contract.py`: focus one locked-context regression on the acceptance-time false disposition guard without editing unrelated context tests.
- `backend/tests/tasks/post_submit_routing/false_policy_fixture.py` and `backend/tests/projects/unified_policy_fixtures.py`: replace the patch/disabled-trigger activation prestate with the real owner path without weakening downstream outcome assertions.
- `backend/tests/reviews/lifecycle/test_transitions.py` and `backend/tests/tasks/evaluation_delivery/test_completion.py`: prove Operator live activation and selected production completion under the reviewed manifest, false/pass atomic acceptance and replay, true/pass handoff, and disabled/shadow/draining known-no-effect retry within the existing OUTBOX attempt budget.
- `experiments/pilot04_external_checker_runtime/checker.py`, `run_public_journey_probe.py`, and that experiment's `README.md`: companion proof for the integrated public activation, task, ZIP intake and Submission path through real broker/worker PRE/POST delivery, including a phase-aware POST failure fixture. The runtime owner edits these files; include them in this bounded activation PR after the clean entry stack is assembled.
- `docs/spec_review_lifecycle.md`, `docs/operations_project_operating_manual.md`, `docs/roadmap_status.md`, and this record: update only affected current claims after implementation evidence. The lead owns shared roadmap reconciliation and any required local sheet exports.

### Not allowed

- PILOT-08 caps, rebases, deadlines or claim expiry; changes to locked checker remediation; setup-fault hold; payment/fulfillment; human review/revision runtime; CLI or frontend; another policy, controller, acceptance path, permission, worker or subsystem.
- Bypassing activation authority or PostgreSQL custody; disabling triggers, patching readiness or inserting a false active guide directly in the success fixture; changing old policy hashes or retained evidence.
- A claim that guide activation itself starts REV. Static guide approval can complete while REV is disabled; a new false/pass acceptance still requires the existing Operator-authorized live controller generation at execution time.

## Design and decisions

Use the existing activation transaction and selected production completion operation. The migration changes the canonical SQL new-binding true-only predicate to allow the locked false setting only if the exact approved compilation row matches the command's compilation ID, result hash and component hashes, its requirement inventory is an array, and no member has disposition `human_review`. This retains the same semantics-version rule already enforced by the ReviewPolicy row and Python. It does not add a route or state. The Python owner checks the approved result's exact requirement dispositions and rejects false if any is `human_review`. PROJECTS rechecks that immutable result when resolving the locked context for execution, as required by the current review contract; TASK continues to consume its existing public context port. This does not relabel a human disposition as executable or infer success from setup-agent prose. Existing source/registry/binding checks reject unsupported or substituted executors. A guide can be prepared while REV is disabled because guide approval establishes immutable task policy, whereas REV's live fence authorizes a later economic mutation. A pre-effect non-live REV refusal currently escapes the completion handler and OUTBOX dead-letters it as invocation UNKNOWN. The bounded repair maps only the typed refusal from `require_new`, before TASK/AUTH/economic effects, to OUTBOX `RETRY` after routing transaction rollback. Normal backoff can deliver after authorized live enablement if the existing attempt budget remains; exhaustion still dead-letters with no redrive in this chunk. Operators should enable REV before allowing false-policy production work. All other exceptions and uncertain effects remain UNKNOWN. The true branch has no REV prerequisite.

The lifecycle manifest must describe the selected production writer that now exists. Its digest is part of new Operator transition commands; prior retained transition facts remain immutable and replay under their original command. This records reviewed runtime scope rather than broadening human or payment availability.

## Acceptance criteria

- [ ] A real manager-authorized complete false guide activates and replays with the same receipt through the current public activation operation; PostgreSQL commits with all custody triggers enabled.
- [ ] False activation refuses an approved `human_review` disposition, unbound/unsupported required capability, substituted registry identity or digest, incomplete policy and unavailable authority; failed attempts leave guide, replay and AUTH/audit facts unchanged.
- [ ] Omitted review mode continues to mean true; a supported true guide activates and successful completion reaches `review_pending` without REV/CON effects.
- [ ] Under an authorized live REV generation, false/pass production request/completion delivery commits one routing manifest, one FinalAcceptance and exact submitter ContributionRecord with applicable frozen awards, no Review or reviewer record; redelivery is exact and no duplicate effect occurs.
- [ ] False/pass new effects are denied while REV is disabled, shadow or draining; a known pre-effect non-live refusal rolls back, returns OUTBOX `RETRY`, and completes after authorized live transition within the existing bounded attempt budget. Exhaustion still dead-letters; all other uncertain handler effects remain UNKNOWN. Correctable failures and infrastructure failures retain their existing distinct outcomes.
- [ ] Migration from the preceding revision changes only the canonical function predicate and its stored search path, retains existing activation receipts and true-policy behavior, and rejects direct SQL without exact same-transaction authority or through a shadowed temporary relation. A negative test bypasses only Python's new disposition check while retaining real activation authority and enabled triggers; PostgreSQL independently rejects an approved false `human_review` inventory at commit.

## Risk and review routing

- Risk class: L1 (bounded policy, authorization, database custody and economic workflow).
- Required reviewers: security, architecture, QA, product operations, and test delta for removal of bypass setup; docs review for capability claims and lifecycle manifest wording.
- Human review focus: Python/SQL admission parity; complete approved requirement inventory; exact registry binding; no trigger bypass; distinction between guide activation and live REV economic permission; true/default branch and retained evidence; exact false/pass contribution with no synthetic Review.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing gate and SQL custody | Read `ProjectService.validate_activation_ready`, `GuideActivationService._readiness`, baseline function and false fixture | Identified two independent false-only blocks and three disabled triggers in the fixture | Implementation and real PostgreSQL proof pending |
| Existing governed outcome | Read production OUTBOX registry, TASK completion/routing, REV participant and PostgreSQL tests | Selected request/completion handler and shared authorized false/pass participant are present | Public activation-to-intake drill pending integration with the public intake owner |
| Migration and behavior | Isolated PostgreSQL 16 migration through 0037; focused public/owner activation, SQL custody sensitivity and lifecycle cases | Final migration applied; seven focused activation/security/lifecycle cases passed: real false activation, human-only and unsupported checker denial, nominal and unpinned temporary-shadow cases, old-command replay and fresh new-manifest Operator transition | Integrated public broker/worker drill and full-suite stack remain pending |
| Bounded non-live recovery | Three isolated PostgreSQL cases for disabled, shadow and draining, followed by authorized live redelivery | 3 passed; each first delivery was `retryable` with no routing/economic effects, then the same event acknowledged with one FinalAcceptance/submitter record/award after live transition | OUTBOX max-attempt exhaustion still dead-letters; no redrive in scope |
| End-to-end journey | Real public manager activation, claim/start, ZIP intake, durable PRE/POST, OUTBOX retry, exact contribution SQL evidence with PostgreSQL and MinIO | Planned jointly with public-intake owner | Requires that owner's independently merged surface; do not claim from hidden fixtures alone |

## Review findings

The bounded plan on `cdfdebd74` passed architecture, security, QA and product-operations review before implementation. Code and evidence review remain pending.

## Reconciliation

- Current-source reconciliation: Fast-forwarded to `cdfdebd74` after CLI-only PR #547. It changed no backend owner or migration in this plan; the single migration head remains `0036_selected_checker_flow`, so the proposed next revision is 0037. It did update CLI public activation coverage and shared roadmap/index wording, which the lead will reconcile. The existing ARCH-04E3A child delivered runtime materialization; this 04E3B child owns readiness on the same initiative without adding an initiative.
- Next usable boundary: Public claim/ZIP end-to-end drill with the separately owned intake route and durable workers after activation lands; human review/revision remains separate.
- Remaining risks: None accepted yet; tests and focused review are pending.
