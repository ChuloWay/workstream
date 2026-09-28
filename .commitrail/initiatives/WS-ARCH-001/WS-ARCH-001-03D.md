# ARCH-03D — Approved-guide lineage through durable intake

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: Hidden contributor preparation carries the exact activated historical guide through its final durable handoff using canonical owner ports.

## Intent and current behavior

AUTH-18 delivers public manager activation. ART preparation already obtains TASK
assignment facts and PROJECTS activated, hash-validated historical context through
public ports. Its final `ArtifactAdmissionService._submission_bundle_facts`
revalidation instead imports TASK's `pre_submit_context` helper, which reads
PROJECTS rows directly and requires a currently compiled pre-policy. This omits the canonical active-project and
activation-receipt validation; a distinct successor supersedes the guide, not
necessarily its pre-policy. That is the concrete integration gap; no new
preparation service or public endpoint is needed.

## Bounded change

Allowed product paths: `backend/app/modules/artifacts/service.py`,
`backend/app/modules/artifacts/submission_admission.py`,
`backend/app/adapters/artifacts/__init__.py`, and removal of
`backend/app/modules/tasks/pre_submit_context.py`.
Allowed proof: `backend/tests/test_approved_guide_intake.py`,
`backend/tests/test_default_pre_submit_execution.py`,
`backend/tests/test_submission_bundle_admission.py`,
`backend/tests/test_effective_pre_submit_execution.py`,
`backend/tests/test_ci_lane_catalogue.py`, `backend/scripts/test_lane_catalogue.py`,
`backend/scripts/behavior_ownership.py` and `backend/tests/test_behavior_ownership.py`
for the exact deleted-target allowlist, and `backend/tests/architecture/`.
Allowed records: `.ci/module-boundaries/private-edge-debt.v1.json`,
`.ci/behavior-ownership/partition.v1.json`, this record, current ARCH/POL/AUTH/CON
`OVERVIEW.md`, ARCH planning `PLAN.md`/`CHUNK_MAP.md` and linked completed 03B contract, `.commitrail/INDEX.md`,
`docs/roadmap_status.md`, `README.md`, `docs/architecture_checker_framework.md`,
and related local roadmap exports when present.
Prohibited: new public routes, authority actions, migrations, post-submit execution,
review/revision or lease implementation, retained-data deletion, fallback paths,
and changes to authorization or transaction ownership.

## Design

Replace the private final-handoff lookup with the existing TASK submission-context
and PROJECTS locked-policy ports, explicitly injected through composition. Require
both on `SubmissionBundleDurablePutService`, passing submission-specific arguments
to generic admission; guide-only admission needs neither. The final preparation
transaction first calls its existing `_lock_authorized_context` to establish
TASK -> actor -> PROJECT -> grant ordering before reentrant handoff validation.
Require assignment ContributionPolicyVersion equality with the activation receipt.
Resolve exact assignment/predecessor facts and then the exact historical PROJECTS
context, retaining comparison of every persisted pre-submit evidence selector.
Use the same locked-guide hash semantics as evidence persistence. Preserve existing
AUTH final prepare/consume and custody consumption before durable intent publication.
Remove the old helper after tracing every consumer, including unused compile/version
functions. No compatibility alias. Remove its mock-query-order tests; retain their
required identity/assignment denial proof through existing AUTH/TASK tests and new
real database handoff regressions.

## Acceptance criteria

- A valid checked bundle reaches durable intent using its exact activated guide.
- A successor activation does not redirect or reject an existing assignment's
  frozen intake policy. A separately labeled owner-contract fixture may exercise
  superseded pre-policy rows; do not attribute that transition to guide activation.
- Wrong assignment, predecessor or policy facts reject before a durable intent;
  authorization revocation and caller rollback retain existing guarantees.
- A valid control reaches the final handoff; the regression detects the old
  lookup by reaching the differing behavior, not by fixture setup failure.
- The private helper and its ART import are removed, boundary checks pass, and
  public preparation/Submission cutover remains explicitly deferred.

## Risk and verification

Risk class: L1. Required reviewers: architecture/reuse, security, QA/test delta,
documentation/product operations, and CI integrity for exact target deletion and test-lane registration. Human focus: exact historical lineage,
no bypass of authority or byte custody, and honest hidden/public scope.
Plan review precedes implementation. Run focused real PostgreSQL intake tests,
authorization/rollback tests, module-boundary and documentation checks, then full
hosted tests. Record exact-target review and CI evidence in the PR. No percentage
gates or test weakening.

## Reconciliation

Based on main `540b5ec4` with AUTH-18 merged. Full public admission cutover remains
ARCH-02I after evaluation/remediation prerequisites. Following this bounded intake
repair, advance to exact post-submit materialization (ARCH-04B), then durable
execution and routing. Review that dependency contract before implementation.

## Plan review

Corrected the original plan following focused review: ports belong to the
submission-specific service; the final transaction must reacquire the existing
authority lock order; distinct successor activation does not imply pre-policy
supersession; negative proof must reach final validation after valid checking.

## Proof and removed tests

`test_final_intake_keeps_original_guide_after_successor` composes a real successor
activation with a distinct ContributionPolicyVersion, then resolves final intake
facts against the original assignment. `test_final_intake_rejects_invalid_owner_context`
uses real checked ZIP custody and PostgreSQL for an archived project; its separate
ContributionPolicy substitution case changes only typed TASK facts. Both have valid
controls before/after the rejected operation. They prove owner revalidation, not
provider execution or public HTTP.

`test_command_holds_actor_and_project_before_final_handoff` runs the real command,
materializer, AUTH and durable-intent owners. Independent PostgreSQL sessions must
time out taking the actor/project locks at final handoff. Provider execution is
explicitly stopped after committed intent. Existing
`test_effective_evidence_workflow_persists_once_and_replays_exactly` retains full
intent/replay, inactive-assignment, denial and admission custody coverage.

Removed two mock-query-order tests of the deleted helper. Exact TASK assignment
and predecessor projection remains covered by `tests/test_tasks.py`; live identity
revocation remains covered by
`test_revoked_contributor_cannot_execute_or_replay_after_reservation` in
`tests/test_pre_submit_attempt_recovery.py`. The replacement tests protect the
canonical final lookup and handoff rather than the helper's SQL query count.

Temporary pre-change-lookup substitution makes both negative owner-context cases
fail their expected rejection assertions. Temporary final-lock removal is a
separate lock-custody probe. Exact commands, results and frozen review targets
belong to the PR evidence; no mutation instrumentation ships with the product.
Public API, provider transport and full lifecycle release proof remain separate.
