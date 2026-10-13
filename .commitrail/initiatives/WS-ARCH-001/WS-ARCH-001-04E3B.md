# WS-ARCH-001-04E3B — First-layer automatic acceptance activation

- Initiative: `WS-ARCH-001`
- Durable disposition: Planned
- Intended merge outcome: A manager can activate a complete guide with locked `human_review_required=false` and supported exact checks, while the existing production completion route can create the authorized FinalAcceptance and submitter ContributionRecord after REV is live.

## Intent

Open the existing first backend journey from approved guide through the governed false-policy outcome. At the planning base, a complete false-policy guide was blocked even though TASK already routed successful selected POST completion through REV's shared acceptance participant and CON's submitter record. Preserve the default-true human-review branch, exact checker capability custody, and contributor-correctable versus infrastructure failure distinction.

## Planning-base behavior

At `cdfdebd74`, `ProjectService.validate_activation_ready` rejected every false ReviewPolicy. `GuideActivationService._readiness` already verified the approved PRE/POST policies, every exact registry entry and its digest, and the absence of capability suggestions before calling that guard. The saved compilation result could separately contain a `human_review` requirement with no capability suggestion, so false-policy admission needed an explicit disposition check.

The canonical `require_guide_activation_custody(operation, true)` PostgreSQL function in `backend/alembic/baseline/v01_schema.sql` also required `review_policies.human_review_required=true`. The immutable approved requirement inventory is in `project_guide_compilations.canonical_result`, selected by the activation command's `target.proposal.compilation_id`, `result_hash` and `component_hashes`; SQL needed to enforce the same false-mode `human_review` denial as Python. The then-current false-policy test setup patched Python readiness and disabled three database triggers, then re-enabled them; it could not prove real activation. The selected production OUTBOX registry already installed request and completion handlers. Completion delivery used TASK's authorized routing manifest; false/pass took a live REV generation and the shared FinalAcceptance/TASK/CON transaction, with no Review. REV's `FIRST_CONTRIBUTION_MANIFEST_DIGEST` still declared production routing unavailable even though selected production composition and PostgreSQL tests existed. `complete_context` validated locked lineage but explicitly did not rerun eligibility; the required acceptance-time disposition check was therefore still absent.

## Bounded change

### Allowed

- `backend/app/modules/projects/service.py` and `backend/app/modules/projects/guide_activation/service.py`: replace the false-policy blanket refusal with exact false-only denial of approved `human_review` dispositions; retain all other source, policy, selected registry, approval, authority and capability checks.
- `backend/app/modules/projects/locked_policy_projection.py`: recheck that the same immutable approved result contains no `human_review` disposition when resolving a false-policy locked context for TASK execution; fail closed through the existing PROJECTS context port without adding another policy or TASK-owned project query.
- `backend/alembic/versions/0039_false_guide_activation.py`: follow merged `0038_task_batch_transitions` without editing that main migration. Change `public.require_guide_activation_custody(uuid, boolean)`'s new-binding ReviewPolicy predicate and persist a protected function search path. Use a counted known-clause replacement of the installed definition, qualify the new compilation lookup, preserve all other clauses and existing receipts, and admit a false policy only when its exact approved compilation is bound and has zero `human_review` dispositions. Replace exactly two old reviewed-manifest digest references in `public.joint_lifecycle_transition_valid(public.joint_lifecycle_transitions)` so PostgreSQL agrees with the corrected fixed REV manifest; retain the function's other custody clauses. Add the canonical `public.joint_lifecycle_new_effects_enabled` predicate and bind it into `public.task_routing_acceptance_matches` only for new effects and `public.guard_task_routing_authority` for new false-policy routing inserts. Preserve historical select-only replay. Do not edit historical migrations or rewrite retained rows.
- `backend/alembic/env.py` and `backend/tests/test_alembic.py`: admit installed 0039 as the current migration head while retaining 0036, merged 0037 and merged 0038 as authorized upgrade predecessors and preserving fail-closed rejection of unknown revisions; keep exact graph, direct 0038→0039 upgrade, repeated-upgrade and downgrade-no-mutation proof aligned with the new head.
- `backend/app/modules/reviews/lifecycle/service.py`: correct the fixed reviewed manifest inventory for the already registered selected production routing writer, keeping human review, fulfillment and payment unavailable. The existing Operator-authorized adjacent transitions and current-generation fence remain the sole runtime enablement.
- `backend/app/modules/reviews/api/acceptance.py`, `backend/app/modules/reviews/acceptance/participant.py`, `backend/app/adapters/tasks/routing_acceptance.py`, `backend/app/modules/tasks/api/routing_outcome.py`, and `backend/app/modules/tasks/evaluation_completion_delivery.py`: carry one typed pre-effect non-live refusal from the held REV fence through TASK. After the routing root transaction rolls back, return shared OUTBOX `RETRY` only for that known no-effect refusal. All other handler exceptions remain UNKNOWN; do not change OUTBOX policy or invent redrive.
- `backend/tests/conftest.py`: update the expected PostgreSQL 16 public-schema fingerprint for the combined import, batch-transition and activation schema; preserve merged import and batch-transition table reset coverage and the reset integrity guard.
- `backend/tests/projects/guide_activation/pg_support.py`, `backend/tests/projects/guide_activation/test_rejections.py`, `backend/tests/projects/guide_activation/test_postgresql.py`, and `backend/tests/projects/guide_activation/test_contracts.py`: prove real authorized false activation/replay through the existing public operation, missing exact coverage, approved `human_review` denial in Python and SQL, temporary namespace shadowing, registry substitution, and default-true preservation against PostgreSQL with every trigger enabled.
- `backend/tests/projects/test_locked_policy_context.py` or `backend/tests/projects/test_locked_policy_contract.py`: focus one locked-context regression on the acceptance-time false disposition guard without editing unrelated context tests.
- `backend/tests/tasks/post_submit_routing/false_policy_fixture.py` and `backend/tests/projects/unified_policy_fixtures.py`: replace the patch/disabled-trigger activation prestate with the real owner path without weakening downstream outcome assertions.
- `backend/tests/reviews/lifecycle/test_transitions.py` and `backend/tests/tasks/evaluation_delivery/test_completion.py`: prove Operator live activation and selected production completion under the reviewed manifest, false/pass atomic acceptance and replay, true/pass handoff, and disabled/shadow/draining known-no-effect retry within the existing OUTBOX attempt budget.
- `backend/tests/authorization/guide_activation/test_postgresql.py` and `backend/tests/reviews/lifecycle/test_participant_control.py`: reconcile affected caller expectations with real false activation and the typed pre-effect non-live TASK signal; retain approved human-only denial, original authority/custody checks, owner-level REV denial and no-effect snapshots.
- `backend/app/adapters/artifacts/internal_workers.py`, `backend/app/modules/artifacts/service.py`, and `backend/app/main.py`: separate the Celery invocation's SQLAlchemy async engine/factory lifetime from the API pool. Compose and dispose the private worker engine/factory within each invocation's async context; require an explicit factory in the artifact namespace helper, passing the API pool at the API call site and the worker-owned factory at the worker call site. Keep the existing process-level provider lease.
- `backend/tests/test_artifact_verification.py`, `backend/tests/test_task_import_sources.py`, `backend/tests/tasks/evaluation_delivery/test_worker_materialization.py`, and `backend/tests/projects/guide_compilation/test_live_cutover_postgresql.py`: prove worker factory custody and disposal on success, failure and cancellation, plus sequential synchronous initialization → real pending-work scan → scan against PostgreSQL with canonical scheduler authority and no pool reset or disposal between boundaries. A separate no-global-getter unit/source guard protects the explicit factory requirement; the integration regression must not patch the global getter because that would miss the observed failure cause. The artifact worker owner edits these files after separate plan review.
- `experiments/pilot04_external_checker_runtime/checker.py`, `run_public_journey_probe.py`, and that experiment's `README.md`: companion proof for the integrated public activation, task, ZIP intake and Submission path through real broker/worker PRE/POST delivery, including a phase-aware POST failure fixture. The runtime owner edits these files; include them in this bounded activation PR after the clean entry stack is assembled.
- `README.md`, `docs/operations_project_operating_manual.md`, `docs/operations_revision_replay.md`, `docs/operations_queue_policy.md`, `docs/glossary.md`, `docs/architecture_lockdown.md`, `docs/architecture_checker_framework.md`, `docs/architecture_system_architecture.md`, `docs/architecture_lifecycle_state_machine.md`, `docs/architecture_data_model.md`, `docs/current_system_data_flow.html`, `docs/product_brief.md`, `docs/product_first_user_flows.md`, `docs/decision_0011_submission_artifact_policy_drives_pre_submit.md`, `docs/engineering/authorization_activation_custody.md`, `docs/engineering/review_authorization_action_custody.md`, `docs/operations_authorization_service.md`, `docs/spec_week2_checker_framework.md`, `docs/spec_chunk_3_project_guide_foundation.md`, `docs/spec_chunk_5_submission_packet_foundation.md`, `docs/spec_chunk_6_checker_contract_records.md`, `docs/spec_chunk_7_checker_runner_registry.md`, `docs/template_submission_packet.md`, `docs/template_submission_artifact_policy.md`, `docs/template_checker_policy.md`, `docs/spec_authorization_service.md`, `docs/spec_contribution_compensation.md`, `docs/architecture_brief/workstream_architecture_brief.md`, `docs/architecture_brief/README.md`, its generated `docs/architecture_brief/workstream_architecture_brief.pdf`, `docs/spec_artifact_storage_service.md`, `docs/spec_chunk_4_task_queue_assignment.md`, `docs/spec_review_lifecycle.md`, `docs/roadmap_status.md`, and this record: update only affected current claims after implementation evidence. The lead owns shared roadmap reconciliation and any required local sheet exports.

- `.commitrail/INDEX.md`, the ARCH overview and `planning/PLAN.md`/`planning/CHUNK_MAP.md`, and the ART, AUTH-001, AUTH-003, CON, POL and REV initiative overviews: reconcile only affected current readiness and next-boundary claims with the bounded local proof and its remaining release limits.

### Reviewed verification and drill repair

The integrated drill exposed an intermittent verifier failure after a job was
claimed. A diagnostic run subsequently completed both policy branches, but did
not capture that earlier exception; its cause remains unassigned. Source review
separately identified an admission-publication lock-order risk: implicit foreign
key checks can lock the contributor before the assignment, while public
preparation locks TASK/assignment before the contributor. Correct that ordering
without attributing the observed failure to it without evidence.

Additional allowed files are `backend/app/modules/tasks/api/submission_context.py`,
`backend/app/modules/tasks/api/__init__.py`,
`backend/app/modules/tasks/submission_context.py`,
`backend/app/modules/artifacts/submission_admission.py`,
`backend/tests/test_submission_bundle_admission.py`,
`backend/tests/tasks/test_submission_lineage.py`,
`backend/tests/tasks/submission_lineage_support.py`,
`backend/tests/checkers/external/test_selected_pre_submit.py`,
`backend/tests/retained_material_fixtures.py`, and
`experiments/pilot04_external_checker_runtime/run_selected_end_to_end_probe.py`
for its existing direct submission verifier call; the already listed ART
service, worker composition, verification tests and TASK lineage fixture may
change for the same bounded repair. Extend the existing TASK context port with
retained-parent locking, using immutable project/task/assignment/contributor
identities. Acquire those locks before terminal ART row locks, then reparse and
compare the locked intent to the identity used for the owner lock. Do not add
fresh contributor lifecycle authorization to retained byte verification, weaken
foreign keys, change stored evidence, or introduce a second context lookup.
Submission-bundle verification must require its composed owner port; other
artifact producers retain their existing behavior. Keep the focused regression
in the existing relevant verification/admission tests unless a separately
registered test module is explicitly added to scope.

The companion drill also exercises an owned worker restart after a committed
known no-effect retry, and public routing-identity revocation after retained
external checker output. Reuse the existing Operator lifecycle transitions to
hold the latter completion safely; do not add a runtime barrier or manually
publish ordinary delivery. Preserve prior accepted facts, prove the revoked
second task creates no routing/economic effects, and distinguish its closed
unknown delivery from the retryable non-live refusal. These are proof extensions,
not activation of human review, fulfillment, or deployment.

### Not allowed

- PILOT-08 caps, rebases, deadlines or claim expiry; changes to locked checker remediation; setup-fault hold; payment/fulfillment; human review/revision runtime; CLI or frontend; another policy, controller, acceptance path, permission, worker or subsystem.
- Bypassing activation authority or PostgreSQL custody; disabling triggers, patching readiness or inserting a false active guide directly in the success fixture; changing old policy hashes or retained evidence.
- A claim that guide activation itself starts REV. Static guide approval can complete while REV is disabled; a new false/pass acceptance still requires the existing Operator-authorized live controller generation at execution time.
- A new async runner, global API pool reuse by Celery, provider lease change, authorization/permission change, logger change or migration for worker pool lifetime.

## Design and decisions

Use the existing activation transaction and selected production completion operation. The migration changes the canonical SQL new-binding true-only predicate to allow the locked false setting only if the exact approved compilation row matches the command's compilation ID, result hash and component hashes, its requirement inventory is an array, and no member has disposition `human_review`. This retains the same semantics-version rule already enforced by the ReviewPolicy row and Python. It does not add a route or state. The Python owner checks the approved result's exact requirement dispositions and rejects false if any is `human_review`. PROJECTS rechecks that immutable result when resolving the locked context for execution, as required by the current review contract; TASK continues to consume its existing public context port. This does not relabel a human disposition as executable or infer success from setup-agent prose. Existing source/registry/binding checks reject unsupported or substituted executors. A guide can be prepared while REV is disabled because guide approval establishes immutable task policy, whereas REV's live fence authorizes a later economic mutation. A pre-effect non-live REV refusal currently escapes the completion handler and OUTBOX dead-letters it as invocation UNKNOWN. The bounded repair maps only the typed refusal from `require_new`, before TASK/AUTH/economic effects, to OUTBOX `RETRY` after routing transaction rollback. Normal backoff can deliver after authorized live enablement if the existing attempt budget remains; exhaustion still dead-letters with no redrive in this chunk. Operators should enable REV before allowing false-policy production work. All other exceptions and uncertain effects remain UNKNOWN. The true branch has no REV prerequisite.

The lifecycle manifest must describe the selected production writer that now exists. Its digest is part of new Operator transition commands; prior retained transition facts remain immutable and replay under their original command. This records reviewed runtime scope rather than broadening human or payment availability.

The integrated broker drill exposed a separate worker lifetime defect: synchronous Celery initialization and successive scans each use a fresh `asyncio.run` loop, while the cached global API async pool could retain connections bound to a closed prior loop. The implemented bounded repair composes a private async engine/factory for each worker invocation and disposes it before that invocation's loop closes. The existing process-level artifact provider lease remains unchanged. API namespace creation receives the API factory explicitly, and worker namespace creation receives its invocation factory; no fallback to the global accessor is permitted. Real PostgreSQL initialization followed by two empty pending-work scans proves the engine/event-loop boundary and authority sensitivity; it does not prove a nonempty verifier execution or the complete public worker chain.

## Acceptance criteria

- [x] A real manager-authorized complete false guide activates and replays with the same receipt through the current public activation operation; PostgreSQL commits with all custody triggers enabled.
- [x] False activation refuses an approved `human_review` disposition, unbound/unsupported required capability, substituted registry identity or digest, incomplete policy and unavailable authority; failed attempts leave guide, replay and AUTH/audit facts unchanged.
- [x] Omitted review mode continues to mean true; a supported true guide activates and successful completion reaches `review_pending` without REV/CON effects.
- [x] Under an authorized live REV generation, false/pass production request/completion delivery commits one routing manifest, one FinalAcceptance and exact submitter ContributionRecord with applicable frozen awards, no Review or reviewer record; redelivery is exact and no duplicate effect occurs.
- [x] False/pass new effects are denied while REV is disabled, shadow or draining; a known pre-effect non-live refusal rolls back, returns OUTBOX `RETRY`, and completes after authorized live transition within the existing bounded attempt budget. Exhaustion still dead-letters; all other uncertain handler effects remain UNKNOWN. Correctable failures and infrastructure failures retain their existing distinct outcomes.
- [ ] Migration from the preceding revision changes the canonical activation-custody predicate and its stored search path plus exactly two fixed REV manifest digest references in the canonical lifecycle transition validator. The upgrade repair additionally installs the shared manifest-bound new-effect predicate and uses it in the new-effect branches of both routing SQL guards; replay-only validation remains unchanged. It retains existing activation receipts, true-policy behavior and prior Operator transition facts with exact original-command replay; fresh transitions require the corrected digest and reject the old digest. Direct SQL without exact same-transaction authority or through a shadowed temporary relation is denied. A negative test bypasses only Python's new disposition check while retaining real activation authority and enabled triggers; PostgreSQL independently rejects an approved false `human_review` inventory at commit.
- [x] Real PostgreSQL sequential synchronous initialization followed by two empty pending-work scans completes with canonical scheduler authority and without resetting or disposing a global pool between boundaries. Each worker invocation disposes its private factory on success, failure and cancellation; a separate no-global-getter guard proves the namespace helper requires an explicit factory.
- [x] The actual broker/worker public drill passes through nonempty artifact verification, PRE/POST delivery and exact contribution evidence with the same provider lease and authority boundaries.

- [ ] An upgraded old-manifest live generation denies new acceptance and routing effects until renewed Operator authorization binds the current manifest; original transition and acceptance replay remain select-only and unchanged.

### Upgrade authorization repair

An existing live generation can retain an immutable transition reviewed against
an earlier manifest that excluded production routing. Changing the digest for
future transitions must not expand that retained authorization. New effects
must additionally match the current reviewed manifest through the controller's
exact immutable transition identity, singleton, generation and phase. Historical
select-only replay and existing evidence remain valid; the migration must not
fabricate an Operator transition or relabel an old receipt.

Use the existing REV fence and canonical database routing guards, not a second
controller. A single REV-owned SQL predicate will bind that exact current
transition and manifest for new effects. The predicate uses a protected `pg_catalog,public,pg_temp` search path and
fully qualified references, fails closed on any missing exact binding, and
acquires no locks. Evaluate it under the existing advisory/controller custody;
the controller-before-TASK lock order stays unchanged. The locked fence reports
the strict mechanical `new_effects_enabled` boolean to existing REV/TASK/CON
new-effect checks; stopped and historical replay
reads remain available. Do not re-run the transition validator as a runtime
permission check: it contains live Operator authority and observation checks
that belong to transition issuance, not continued operation. Renewal follows
the existing authorized live → draining → disabled → shadow → live edges with
the current manifest; no new transition or implicit activation is introduced.

Additional affected files: `backend/app/modules/reviews/api/lifecycle.py`,
`backend/app/modules/reviews/lifecycle/fence.py`,
`backend/app/modules/tasks/api/accepted_effects.py`,
`backend/app/modules/tasks/accepted_effects.py`,
`backend/app/modules/contributions/api/participation.py`,
`backend/app/modules/contributions/records/participant.py`, existing REV
lifecycle/acceptance and TASK/CON fixture/tests that construct fence facts,
`backend/tests/reviews/lifecycle/test_transitions.py`, and existing migration
upgrade tests. Extend this PR's unmerged migration 0039 to enforce the same
predicate in new routing/acceptance SQL guards; preserve earlier migrations.
Measure and update the schema fingerprint in the existing test fixture.
Update the existing operating runbook and affected roadmap limitation together.

Required proof: legitimate old-manifest shadow/live transitions survive the
actual upgrade unchanged; a new-effect gate denies without effect writes;
old transition replay still returns its original receipt; renewed current-
manifest Operator transitions permit new effects. Add discriminating Python
and direct-SQL checks, with a guard-removal probe failing at the intended
assertion. Preserve current-manifest success, stopped states, true-policy
independence and select-only historical acceptance replay. Run focused real
PostgreSQL tests, schema verification, boundaries and fresh hosted CI; obtain
focused architecture/security and QA/test-delta review of the repaired head.

## Risk and review routing

- Risk class: L1 (bounded policy, authorization, database custody and economic workflow).
- Required reviewers: security, architecture, QA, product operations, and test delta for removal of bypass setup; docs review for capability claims and lifecycle manifest wording. The bounded worker lifetime repair needs architecture, security, QA and test-delta review of factory ownership, disposal and changed tests.
- Human review focus: Python/SQL admission parity; complete approved requirement inventory; exact registry binding; no trigger bypass; distinction between guide activation and live REV economic permission; true/default branch and retained evidence; exact false/pass contribution with no synthetic Review.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Planning-base gate and SQL custody | Read `ProjectService.validate_activation_ready`, `GuideActivationService._readiness`, baseline function and false fixture at `cdfdebd74` | Identified two independent false-only blocks and three disabled triggers in the fixture; the implemented path removes that fixture bypass | Full public drill remains pending |
| Existing governed outcome | Read production OUTBOX registry, TASK completion/routing, REV participant and PostgreSQL tests | Selected request/completion handler and shared authorized false/pass participant are present | Complete public durable-runtime drill pending |
| Migration and behavior | Focused isolated PostgreSQL 16 run at pre-stack activation commit `1c64abca4`, then six combined-0038 import/activation PostgreSQL cases and the strict installed-schema fingerprint at `fe7cf9981` | Real false activation, human-only and unsupported checker denial, namespace sensitivity, retained old-command replay, fresh corrected-manifest Operator transition and the then-current import/activation schema passed | This predates batch-transition migration 0038 and activation resequencing to 0039; complete public durable-runtime drill pending |
| Migration resequencing | Four focused PostgreSQL cases against staged reconciliation files later captured by `3b13bfad2`; those migration/env/test/fingerprint files are unchanged at `be3638e84` | Direct 0038→0039 upgrade, head repeat, downgrade refusal/no mutation and reset/fingerprint checks passed | The runner recorded pre-reconciliation `fba26a21c`, so this is supporting staged-tree evidence, not exact-target execution proof. Fresh clean-head CI remains required |
| Bounded non-live recovery | Focused isolated PostgreSQL run at the pre-stack activation implementation for disabled, shadow and draining, followed by authorized live redelivery | Three cases passed; each first delivery was `retryable` with no routing/economic effects, then the same event acknowledged with one FinalAcceptance/submitter record/award after live transition | OUTBOX max-attempt exhaustion still dead-letters; no redrive in scope |
| Default-true and replay preservation | Focused isolated PostgreSQL run at the pre-stack activation implementation | Five true-policy and replay cases passed | Full public drill remains independent proof |
| Integrated main fixture repair | Exact-head PostgreSQL rerun at `4f342bf56` after repairing the missed main fixture call | Two affected fixture/worker cases passed on the exact head | The complete public drill remains independent proof |
| Worker engine lifetime | Real PostgreSQL synchronous initialization followed by two empty pending-work scans and authority sensitivity at `f30c858c2`; focused explicit-factory guard and disposal cases at `5992ab59a` | The per-invocation engine/factory repair passed its bounded ownership, sensitivity and disposal proof | Empty scans do not prove nonempty verification or the complete worker chain |
| Exact-head backend CI | Hosted merge target `f11b3564e04eefd5679d7c555c7162971ac374b0` for source head `4f342bf56` | All ten lanes exited zero; 8,831 unique nodes completed with each lane's collected count equal to completed and zero skipped or deselected; aggregate passed | Hosted CI does not replace the public durable-runtime drill; a later source head requires fresh CI |
| Verifier retained-parent custody | Repair candidate `7d67e0c9668cb2734f5b4a90fcd8b30be5b0eb3b`, integrated without source changes | Seven PostgreSQL behavior cases passed; exact-head terminal-order and independent-session TASK/assignment `NOWAIT` checks passed. Removing either owner lock fails its named regression; removing final identity equality fails its regression. Owned resources cleaned | Proves actual row custody and order, not attribution of the earlier intermittent exception or a full deadlock reproduction |
| Supporting runtime diagnostic | Product tree `489df6c9632d213f95992e29e9fb1620b8627583` with a private worker failure observer | True-policy initial POST failure, public remediation and v2 `review_pending`; false-policy non-live retry then one acceptance, submitter record and conditional award; duplicate delivery preserved effects. Cleanup confirmed | Diagnostic run predates the verifier repair and restart/revocation extension; it is not final integrated journey proof |
| Integrated backend evidence | Hosted source `d5703d9c67a61b7192505fdced5a7e1157f54107`, synthetic merge `4cb047d43d0cdaed1c29c49f317d1930b3f99f68` | Independently verified 8,888 unique completed nodes across ten lanes; exact collected/completed multisets, zero skips/deselections, all 33 artifact hashes valid and all owned database/MinIO probes and cleanup complete; all required checks passed | Slowest lane was 1,175.535 seconds, close to the unchanged 1,200-second limit. Later documentation reconciliation requires fresh head checks; no timing gate was weakened |
| Final integrated journey | Clean `d5703d9c67a61b7192505fdced5a7e1157f54107`, isolated PostgreSQL/MinIO/Redis, public API, real prefork worker and Beat, selected external images | Passed: initial POST failure → public replacement → human `review_pending`; false-policy safe retry survived worker restart → one FinalAcceptance, submitter ContributionRecord and project-points award, no Review; after-I/O public router-link revocation closed delivery with no second-task governed effects. Exit zero and complete owned-resource cleanup | Uses scripted approved-guide preconditions and a Flow-compatible local signer, development container isolation and configured 10-second ART scans; OUTBOX uses its normal 60-second schedule. Does not prove hosted Flow, live model setup, deployment, live human review or payment fulfillment |
| Retained-live authorization upgrade | Real isolated PostgreSQL 16, genuine Alembic 0038 schema and Operator shadow/live transitions, followed by actual 0038→0039 upgrade; staged repair source captured by `eb9a5ddb4` | One focused upgrade test passed: original transition replay unchanged, new-effect gate denied without effects, forged Python enablement rejected by the routing trigger, authorized current-manifest renewal permitted acceptance, and stopped terminal replay remained valid. The SQL acceptance predicate discriminated new effects from replay when the canonical gate was forced false. Owned database and role cleanup completed | Runner recorded the earlier plan commit while the repair files were staged; this is supporting source-matched proof, not exact-head hosted evidence. The clean focused batch and guard-removal probes remain required |

## Review findings

The bounded plan on `cdfdebd74` passed architecture, security, QA and product-operations review before implementation. On the implemented source, architecture, security, reuse, QA and test-delta review passed. The focused and exact-head PostgreSQL evidence is recorded above. The verifier repair additionally passed focused architecture and security review at `7d67e0c`; architecture retains the explicit limitation that no full cycle or original exception attribution was established. Independent runtime evidence QA passed at `d5703d9c6`, verifying structured results against exact-tree assertions, source identity, custody and complete resource cleanup. The final integrated public drill passed at `d5703d9c6`; documentation reconciliation preserves its local fixture and deployment limits. Earlier table entries describe their original evidence boundary; the final row supplies the complete local runtime proof.

## Reconciliation

- Current-source reconciliation: The plan originally fast-forwarded to `cdfdebd74` after CLI-only PR #547, when `0036_selected_checker_flow` was the migration head. Main subsequently merged PILOT-02B atomic import as `0037_task_import_batches` and PILOT-02C batch transitions as `0038_task_batch_transitions`; this integrated activation change follows them as `0039_false_guide_activation`, preserving each owner and its retained evidence. The existing ARCH-04E3A child delivered runtime materialization; this 04E3B child owns readiness on the same initiative without adding an initiative.
- Next usable boundary: Reproduce and operate the first contribution path in the intended hosted environment using its real identity and infrastructure configuration. The local public claim/ZIP-to-contribution journey is proven; live human review/revision remains separate.
- Remaining risks: The local drill uses scripted approved-guide facts, a Flow-compatible signer and development container isolation; it does not establish hosted identity, model-based setup or deployment. Bounded OUTBOX retry still exhausts without automatic redrive. Live human review/revision, setup-fault hold and payment fulfillment remain separate work.
