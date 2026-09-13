# WS-AUTH-001-12G — Live post-policy authorization

- Initiative: WS-AUTH-001
- Durable disposition: Planned
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

Planned new tests are `backend/tests/authorization/post_policy/test_context.py`,
`test_prepared.py`, `test_postgresql.py`, and `test_concurrency.py` (names are
future test owners, not existing proof). Reuse `proposal_case`, canonical
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
coverage must be at least90%; preserve all current global and per-file floors.
Use hosted full-suite coverage instead of duplicating the full suite locally.
Frozen clean-head review and latest pushed-head hosted evidence precede PR
readiness. Live model smoke testing is irrelevant: this boundary invokes none.
