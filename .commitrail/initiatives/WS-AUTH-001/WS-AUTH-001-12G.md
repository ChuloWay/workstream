# WS-AUTH-001-12G — Live post-policy authorization

- Initiative: WS-AUTH-001
- Durable disposition: Complete
- Risk: L1
- Intended merge outcome: activate exact setup-service derivation and project-manager review, approval and correction authority for POL-06A; public composition remains POL-06B.

## Intent

POL-06A already owns canonical post-policy derivation from a finalized saved
unified result, complete draft read, separate approval and shared correction.
Those operations currently require a test/unavailable nominal AUTH port. This
chunk supplies live authority without changing policy compilation or lifecycle.
Only `workstream.project.setup` can derive; only a current human Project Manager
with an exact project grant can inspect the complete draft, approve or correct.
Approval never follows implicitly from successful derivation.

## Current owners and reconciliation

`PostPolicyService` prepares `PostPolicyAuthorizationLocator` before product
locks and supplies immutable `PostPolicyAuthorizationFacts` afterward. The
public facts bind every saved source/result/component, upstream approval,
policy/output digest and business operation; transport request is intentionally
excluded from the durable digest. Correction also prepares the existing unified
proposal authority before product locks and persists both operations atomically.
The migration already validates exact authority events and grants/matrix custody.

The older child contract's separate diagnostic-read action and manual correction
alternative are superseded by merged POL-06A. Reuse the existing PM-only
`project.guide_compilation.review_package.read` action and the unified successor;
no diagnostic reader gains complete proposal or mutation access. Preserve the
independent diagnostic-read actions elsewhere. The unconsumed flat
`ProjectPostSubmitCheckerPolicyMutationResourceContext` is referenced only by
AUTH runtime/kernel mappings and contract fixtures. Replace that shape and its
obsolete tests together; retain the public locator/facts/receipt port and exact
behavioral invariants. There is no compatibility resource or alias.

## Bounded change

Allowed production owners:

- `backend/app/modules/authorization/api/post_policy.py`: keep nominal public
  port/facts/receipt, remove the unused flat resource shape and stale availability
  wording. Existing public facts may only gain validation needed for exact AUTH.
- `authorization/domain/post_policy.py` and `post_policy_authorization.py`:
  strict exact facts/resource and explicit adapter over shared kernel/PREP.
- Existing `authorization/catalogue.py`, `runtime.py`, `kernel.py`, `prepared.py`,
  `prepared_proposal_replay.py`, `prepared_projection_replay.py`, and domain
  `action_groups.py`, `prepared_service.py`, `guide_proposals.py`,
  `guide_manager_resources.py::guide_manager_resource_denial`,
  `resource_digest.py`, `audit_targets.py`: bounded action/resource/selector,
  service/human, digest and replay integration. Extract a shared exact operation
  helper only where both existing consumers actually reuse it; no second kernel
  or independent handle/session/grant-lock implementation.
- `backend/app/adapters/auth/__init__.py`: one typed explicit construction
  function. No routes, dependency-driven product dispatcher or automatic derive.
- Existing AUTH/POL contract tests and fixtures plus focused
  `backend/tests/authorization/post_policy/` contract, PREP, PostgreSQL and
  concurrency tests. Existing guide-proposal tests retain all required behavior.
- Exact test-lane registration and expectations, behavior ownership partition
  and its closed approved additions/tests, structural debt inventory reductions
  required by touched oversized owners. No threshold/selection weakening.
- Current AUTH/POL/ARCH navigation, adopted child contract, README, relevant
  authorization/checker/operating documentation, roadmap and this record.
  Assess local roadmap exports; update them if present. No new export files.

No product compiler/body writes, new schema migration (existing audit resources
already suffice), source/document/provider access, agent runtime, checker
execution, public route, guide activation, task/review/acceptance behavior,
service-matrix widening, retained-data deletion, compatibility path, dependency
or CI workflow change. An unforeseen custody gap requires revisiting this
record and its plan review before implementation expands.

## Design

1. Activate only the three existing post-policy mutation actions. Add their
   exact human/service groups to current kernel/PREP dispatch. The existing
   setup-service singleton matrix row remains the only derive authority.
   Current exact-project PM grant filtering governs read/approve/correct;
   system-scope or other-project PM grants do not suffice.
2. Replace the unused resource model with a strict AUTH resource wrapping the
   canonical public facts, with resource identity derived from action and
   policy ID. Complete read keeps the existing review-package resource name;
   mutation keeps `project_post_submit_checker_policy_mutation`. Preserve
   `facts.digest` exactly in AUTH events; transport request/correlation are
   independently checked by PREP against authenticated context.
3. The existing review action serves both proposal and post-policy ports.
   Bind a closed post-policy operation-family selector in private PREP input,
   so identical locator fields cannot substitute a proposal handle/resource.
   Both parsing paths must reject missing/unknown/crossed family or selectors;
   retain one catalogue action and one permission. No public compatibility input.
4. A nominal `PreparedPostPolicyOperation` view delegates consumption, replay,
   issuer/session/root-transaction/one-use enforcement and closure to shared
   PREP. It validates exact locator/facts types and authenticated actor/link/
   request before access. The adapter binds business correlation to the operation
   ID supplied by POL, without recomputing policy or operation identities.
5. Replay uses current locked authority and checks the original exact audit
   event, actor, action, permission, project/resource, business correlation and
   resource digest. Human evidence requires a valid retained grant; service
   evidence requires no grant and the fixed setup identity/matrix. Reuse existing
   replay infrastructure without allowing a service replay on a human operation
   or a human replay on derive. Different transport requests may replay the same
   operation; no new allowed event or product write is emitted.
6. Keep both correction PREPs before product locks and close before owner writes.
   Tests compose both concrete adapters in the same session/root transaction.
   Existing correction allocation, rollback, finalization and immutable custody
   remain untouched.

The cohesive adapter/PREP integration and real denial/replay/concurrency proof
may exceed the 500-line L1 guideline. It is one authority boundary over an
existing product owner, not a product feature expansion. No new framework is
justified; the canonical PREP controls already solve the lifecycle problem.

## Acceptance criteria

- All three mutation actions have exact activation; unrelated planned actions
  remain unavailable and the fixed service matrix gains no pair.
- Current setup service alone derives; covered PM alone reads/approves/corrects.
  Operator, Audit, system manager, unrelated human/service, wrong/expired/revoked
  grant, inactive actor/link and foreign project deny without protected effects.
- Raw kernel calls cannot bypass PREP. Wrong action/family, actor/link/request,
  project/guide/compilation/operation, resource, handle, session, transaction or
  post-close/double-use rejects. Strict UUID/hash/generation/lifecycle parsing
  rejects forged shapes and partial commitments, including Boolean generation.
- Positive controls use real finalized result and approved upstream chain;
  real derive/read/approve/replay and both correction origins commit through
  the concrete AUTH adapter and PostgreSQL migration guards.
- Revocation and independent-session races serialize current authority. Replay
  checks current authority and exact retained evidence; stale upstream decisions
  still reject through the existing product owner, retaining previous evidence.
- Real correction composes both live authorities atomically; deny/close failures
  leave no policy/successor/operation or allowed event. No model, document or
  runtime evaluator invocation occurs in positive/replay/recovery/denial paths.
- Audit contains bounded identifiers/hashes only, and uses the existing exact
  resource/action/permission pairing. No public endpoint or broader reader scope
  becomes available.

## Risk and review routing

L1 authorization and workflow integration. Required plan review precedes code.
Implementation review: security; architecture/reuse; QA/test delta; docs/product
operations; CI integrity for exact inventories, unchanged gates and hosted proof.
Lead runs shared checks once per frozen candidate; reviewers receive bounded
context and independently test their risk. Human focus: service versus PM duty,
exact project grant, sibling read isolation, replay and dual-PREP correction.
User authorized this chunk; no additional product decision is currently missing.
Human approval of the eventual specific PR remains required for merge.

## Evidence

Focused tests are `backend/tests/authorization/post_policy/test_context.py`,
`test_prepared.py`, `test_postgresql.py`, and `test_concurrency.py`. Reuse `proposal_case`, canonical
`prepare_upstream`, POL06A operation fixtures and public nominal ports; replace
only AUTH port construction with the real adapter for integration. A service
seed must carry a real active setup identity/link; a PM control carries a real
exact project grant. Assertions about PostgreSQL/locks use independent actual
sessions, not the in-memory PREP fixture.

Prove a valid control before each denial family. Fault injection must show that
removing exact-project/operation-family/read/replay guards makes the named
regression fail; do not label ordinary parameterization a mutation probe.
Schema/authority event constraints remain real and preconditions complete.

Run affected AUTH/catalogue/resource/PREP/POL suites using the isolated
PostgreSQL/MinIO runner and locked clean venv, Ruff, structural/ownership and
boundary checks, stale wording and Markdown links. New/changed AUTH subsystem
coverage must be at least 90%; preserve all current global and per-file floors.
Use hosted full-suite coverage instead of duplicating the full suite locally.
Frozen clean-head review and latest pushed-head hosted evidence precede PR
readiness. Live model smoke testing is irrelevant: this boundary invokes none.

### Proof map

This map identifies the committed proof owners; execution results belong in the
PR and its exact-head evidence. Test paths are relative
to `backend/tests/authorization/post_policy/` unless an existing owner is named.
Each parametrized row varies only its named invariant. Contract fixtures use the
real kernel/PREP with explicit principal/evidence ports; transactional rows use
`proposal_case`/`prepare_upstream`, real concrete adapters and PostgreSQL.

| Acceptance atom | Owner/source | Named proof and assertion | Required custody |
|---|---|---|---|
| Only three reserved actions activate; service matrix unchanged | `authorization/catalogue.py` | `test_context.py::test_exact_action_activation_and_matrix`: exact active delta and unchanged singleton pair | pure catalogue |
| Fixed setup service derives | `PostPolicyAuthorizationAdapter`, shared service PREP | `test_postgresql.py::test_setup_service_derives_with_exact_evidence`: one policy/operation and matching service event/digest commit | PostgreSQL transaction |
| Other services or humans cannot derive | adapter, `kernel._prepare_prelocked` | `test_prepared.py::test_derive_rejects_other_principals`: each service identity/human denies with no allow | service; valid setup control |
| Covered PM reads complete exact draft | `guide_manager_resource_denial`, `PostPolicyService.review_package` | `test_postgresql.py::test_manager_reads_exact_post_policy`: displayed target/body and bounded PM event match stored policy | PostgreSQL transaction |
| Covered PM approves separately | adapter and `PostPolicyService.approve` | `test_postgresql.py::test_manager_approves_exact_post_policy`: compiled control becomes approved with exact human receipt | PostgreSQL transaction |
| Covered PM corrects compiled or approved policy | both AUTH adapters, `request_post_policy_correction` | `test_postgresql.py::test_manager_correction_has_one_shared_successor`: parameterized initial lifecycle; one successor and both exact decisions commit | PostgreSQL transaction |
| Wrong role, system/foreign scope, revoked grant cannot read/approve/correct | `_prepare_project_manager`, repository grant lookup | `test_postgresql.py::test_manager_operations_reject_wrong_authority`: valid upstream/policy and real alternative principal/grant, unchanged protected rows and no new allow | stored foreign resource and PostgreSQL transaction |
| Inactive/revoked identity fails | shared kernel request-actor lock | `test_prepared.py::test_inactive_identity_denies`: parameterized actor/link lifecycle with same valid final facts, no allow | service |
| Missing, malformed or crossed commitments reject | `domain/post_policy.py` exact locator/facts validator | `test_context.py::test_each_commitment_is_required_and_strict`: each UUID/hash/generation/lifecycle and selector fails independently; valid tuple passes | pure |
| Proposal handle cannot consume post-policy read | both domain family matchers and `prepared.consume` | `test_prepared.py::test_proposal_handle_rejects_post_policy_read`: otherwise identical locator fails with no allow | service PREP |
| Post-policy handle cannot consume proposal read | same owners | `test_prepared.py::test_post_policy_handle_rejects_proposal_read`: reverse substitution fails with no allow | service PREP |
| Bound action/principal/request/operation or scope cannot be substituted | adapter and `prepared._binding` | `test_prepared.py::test_prepared_selector_substitution_rejects`: change each independent selector after valid preparation, no allow | service PREP |
| Raw kernel cannot authorize these operations | kernel public versus private PREP boundary | `test_prepared.py::test_raw_kernel_cannot_authorize_post_policy`: read/approve/correct/derive valid resources deny without preparation | service |
| Handle cannot cross issuer/session/root transaction, repeat or survive close | shared PREP and nominal adapter | `test_prepared.py::test_handle_lifetime_is_exact`: parameterized misuse after valid preparation, no allow | service PREP |
| Replay uses original exact decision and fresh authority with new transport request | shared prepared replay and post-policy adapter | `test_postgresql.py::test_exact_replay_adds_no_effects`: derive/approve/correct original receipt returned, rows/events unchanged; revoked caller replay denies | PostgreSQL transaction |
| Forged replay decision fields reject | shared prepared replay | `test_prepared.py::test_replay_evidence_substitution_rejects`: each actor/action/permission/project/resource/correlation/digest/grant-kind mismatch rejects | service evidence port |
| Post-policy or unified authority deny/close failure rolls back correction | both real adapters and caller root transaction | `test_postgresql.py::test_correction_authority_failure_rolls_back`: inject failure only at chosen authority boundary after complete prerequisites; no successor/policy/operation/allow changes | PostgreSQL transaction |
| Stale upstream remains rejected after replacement | existing POL owner and new live adapter | `test_postgresql.py::test_stale_upstream_denies_through_live_authority`: new approved generation, fresh old target cannot mutate; retained rows unchanged | PostgreSQL transaction |
| Manager operation and revocation serialize in either order | repository locks, shared PREP | `test_concurrency.py::test_manager_operation_and_revocation_serialize`: independent sessions, observed blocker/waiter; grant-first denies, operation-first commits then revoke | PostgreSQL concurrency |
| Concurrent exact replay commits one operation | shared authority/product locks | `test_concurrency.py::test_concurrent_derive_commits_once`: independent sessions return same receipt, one operation/event | PostgreSQL concurrency |
| No document/model/evaluator calls on operation/replay/denial | unchanged POL owner and AUTH composition | shared `forbid_runtime_calls` fixture on all new PostgreSQL/concurrency tests: actual runtime/document/checker entrypoints raise if invoked | composition spy with real transaction |
| Audit stays bounded; public boundary unchanged | digest/audit targets, adapter root, existing routers | `test_context.py::test_post_policy_digest_preserves_public_facts`; exact stored event assertions above; existing public OpenAPI contract test retains route set | pure digest, PostgreSQL audit and composition |

The plan review identified the human resource-owner omission and requested
this atom-level proof map; both are incorporated without changing the product
boundary. Local guard-removal probes target the named exact-project, sibling-family,
read and replay tests. Exact-project removal reaches the independent database
authority guard; its regression detects loss of early AUTH denial, not a committed
authorization bypass. Structural/source inspection is not runtime proof.

Discovery refinement: AdminRoleGrant has active/revoked lifecycle, with no expiry field.
The proof covers its actual lifecycle; this chunk adds no grant expiry model.

## Scope and cleanup reconciliation

The unused flat post-policy resource and its dedicated shape-only test file are
removed. Required commitment, crossed identity and obsolete-field rejection
coverage moves to `authorization/post_policy/test_context.py`; existing broad
resource assertions retain their behavior using the canonical facts fixture.
The shared kernel and PREP oversized owners shrink, with their relevant
post-policy resource and review-binding invariants in focused domain helpers.
No old post-policy execution path or alias remains. Other sufficiency and
submission-policy mutation consumers still use their own shared contexts;
this chunk neither deletes those consumers nor adds a compatibility path.

The footprint exceeds the preferred L1 size because it includes independent
contract, replay, PostgreSQL, concurrency and rollback proof plus required
current navigation and exact inventories. It remains one AUTH boundary over
unchanged POL operations: splitting its service/human/read/replay guards would
leave an incomplete executable authorization surface. There are no migration,
workflow, dependency or provider changes.
