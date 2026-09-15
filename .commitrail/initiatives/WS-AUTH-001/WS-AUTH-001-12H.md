# AUTH-12H — Live manager authority for complete guide activation

- Initiative: WS-AUTH-001
- Durable disposition: Complete
- Risk: L1 (authorization and immutable activation evidence)
- Intended merge outcome: live exact-project manager authority for CP07; HTTP exposure remains pending.

## Intent

Connect the existing CP07 activation operation to live, exact-project
Project Manager authority. This adopts and reconciles the
[earlier contract](planning/chunks/WS-AUTH-001-12H-guide-activation.md) against
merged CP07. The existing operation owns readiness, product locks, selected
ContributionPolicy validation, activation, supersession and the caller's atomic
transaction. AUTH owns live principal/grant checks, one-use prepared authority
and the matching allow event. No public activation route is added here.

The earlier incomplete AUTH activation resource is superseded, not retained as
a compatibility constructor. Use CP07's public immutable locator/facts/receipt
and digest directly through its public API; do not duplicate that schema in AUTH.
Its runtime imports are dependency-safe public values. AUTH validates structure
and exact identity relationships; PROJECTS remains the policy readiness owner.

`human_review_required=false` remains unavailable under CP07's current guard.
The old plan's installed automated-acceptance scenarios require future runtime
work, not fabricated capabilities in this chunk. True needs no Task, Submission,
CheckerRun or PaymentPolicy. Downstream chronology remains a future contract;
guide-local generation is not a project-wide activation sequence.

## Bounded change

1. Replace the obsolete activation resource with a closed AUTH resource wrapping
   the existing public CP07 facts. Revalidate nested facts and bind locator to
   receipt operation, project and guide. Preserve the exact CP07/SQL digest.
2. Add the concrete AUTH implementation of CP07's nominal prepared port and
   explicit factory in the AUTH composition root. Extend shared PREP selectors,
   consume/replay and manager authorization to this one operation. Acquire AUTH
   control, actor/link and exact project grant before CP07's product/CON locks.
3. Activate only `project.guide.activate` in the catalogue; deny service actors,
   system-scoped managers and other administrative roles. Keep service allowlists
   unchanged. Preserve request-local, one-use, root-transaction handle custody.
4. Exercise the real composition with real PostgreSQL and update affected old
   catalogue/resource fixtures, current capability documentation and navigation.

Allowed files: AUTH catalogue/runtime/kernel/PREP, AUTH domain resource and
replay helpers, new activation authorization implementation, AUTH adapter root;
CP07 public contract documentation only if required; focused AUTH/CP07 tests and
their existing shared fixtures; affected current architecture/authorization/
operating documentation, roadmap and initiative navigation; exact new-module
registration in `backend/scripts/test_lane_catalogue.py`,
`backend/scripts/behavior_ownership.py`, `.ci/behavior-ownership/partition.v1.json`
and its negative inventory test; exact shrinking/unchanged measurements in
`.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json` (no threshold or exception expansion).
The manager scope action set and duplicate grant-denial branches are consolidated
so the touched kernel shrinks while retaining both query and returned-grant checks. A migration is
allowed only if inspection proves existing 0023 audit/custody parity insufficient.

Prohibited: new public routes, policy/compiler semantics, duplicate activation
or replay storage, new service permissions, CON redesign, provider calls,
TASK/Submission/REV execution or chronology changes, retained-data deletion,
compatibility paths, unrelated old-code cleanup, weakened CI or tests.

## Acceptance criteria

- An active exact-project manager activates a complete approved chain through
  real AUTH and CP07, with one matching decision, receipt and immutable binding.
- Wrong role/project, system scope, service identity, revoked/suspended actor,
  link or grant denies without activation or binding. Live database authority
  wins over stale authenticated context.
- Exact replay rechecks live authority and returns original evidence without a
  second activation/allow. Changed command, actor/link, operation or scope denies;
  replay does not revalidate mutable current CON state as a new activation.
- Real PostgreSQL concurrency proves authority locks precede product locks and
  revocation cannot interleave between allow and activation. Existing CP07 tests
  retain complete/partial/stale chain, false denial and supersession coverage;
  live-composition tests prove those guards remain reachable under real AUTH.
- Direct PREP tests reject changed locator/facts, malformed nested instances,
  wrong action, copied/closed/reused handles and changed session/root transaction.
  Positive controls reach consume/replay, rather than failing an earlier guard.
- Existing audit migration admits the exact new allow and rejects altered
  commitments. No expanded audit payload or private guide/policy contents.
- AUTH all-pairs, affected tests, module/AUTH boundary checks, stale-wording and
  Markdown-link checks, and hosted full CI remain green. New/materially changed
  subsystem coverage remains at least 90 percent.

## Risk and review routing

L1 authorization and immutable-evidence impact requires focused security,
architecture/reuse, QA/test-delta, documentation/product-operations and CI-integrity
review. Human focus is exact-project manager authority through the existing CP07
transaction, with no public HTTP activation or automated-acceptance expansion.

## Evidence

### Owner and proof map

Paths below are relative to `backend/`. The named tests provide implementation
proof; exact-head execution and review results remain in the PR. PostgreSQL tests use `clean_postgres_database`
and the existing complete CP07 `activation_case`; no authority guards are mocked
in that integration layer. Unit custody tests retain the real kernel/PREP while
substituting only principal storage and audit persistence.

| Owner / exact implementation | Proof |
| --- | --- |
| `app/modules/authorization/domain/guide_activation.py`: `ProjectGuideActivationResourceContext`, `activation_resource`, `activation_selectors`, `parse_activation_prepare`, `activation_matches` | `tests/authorization/guide_activation/test_context.py`: exact digest parity, independently mismatched resource/locator/receipt, nested invalid model instances |
| `app/modules/authorization/guide_activation_authorization.py`: `GuideActivationAuthorizationAdapter.lock_activation_scope`, nominal `_PreparedGuideActivation.consume_new/validate_replay` | `tests/authorization/guide_activation/test_prepared.py`: positive consume/replay, invalid caller/locator, sibling action/resource, copied/closed/reused handle, foreign session/root, evidence failure |
| `runtime.py`: remove old resource class and import replacement in existing union/mapping; `domain/action_groups.py`: `GUIDE_BOUND_PROJECT_MANAGER_ACTIONS`; `kernel.py`: `_prepare_project_manager` | Same PREP tests: wrong role, exact versus system/foreign project scope, suspended actor and revoked link/grant; direct kernel cannot authorize |
| `prepared.py`: `_PreparedAuthorizationBinding`, `_binding`, `consume`, `validate_replay`; `prepared_proposal_replay.py`: `parse_review_bindings`, `review_context_matches`, `validate_review_replay` | Same PREP tests: selector substitution, one-use replay, original decision substitution, refreshed request and live grant |
| `domain/resource_digest.py`: `authorization_resource_digest`; `domain/audit_targets.py`: `project_authority_audit_target` | Context tests and existing `tests/projects/guide_activation/test_audit_contract.py`: exact receipt digest and closed, privacy-bounded audit target |
| `app/adapters/auth/__init__.py`: `guide_activation_authorization`; existing `app/adapters/projects/__init__.py`: `project_guide_activation_port` (consumer, no second operation) | `tests/authorization/guide_activation/test_postgresql.py`: `test_complete_activation_and_live_replay`, `test_live_authority_denial_preserves_draft`, `test_live_activation_keeps_product_readiness_guards`, `test_caller_rollback_removes_activation_evidence` |
| `catalogue.py`: `_index_actions`; no service allowlist additions | Existing exact active inventory in `tests/authorization/setup_finalization/test_catalogue.py`, all-pairs resource fixture in `tests/test_authorization.py`, new service-denial controls |
| CP07 service / SQL 0023 unchanged owners | `tests/authorization/guide_activation/test_concurrency.py`: `test_activation_and_revocation_serialize` (both orders, two real DB sessions, observed PostgreSQL waiter/blocker); `test_concurrent_activation_replays_once`; existing CP07 negative chain and supersession tests retained |

Inspection of SQL 0023 confirms action, resource, bounded audit facts and exact
activation custody already agree with this design. **No migration is expected**;
real live-composition commit and audit-contract tests must prove that parity.

Before implementation: architecture/reuse and security plan review, including
import direction, digest parity, lock order and reachable positive/negative
fixtures. After deterministic checks: focused security, architecture/reuse,
QA/test-delta, documentation/product-operations and CI-integrity reviews over a
clean candidate. Lead owns implementation and shared verification.

Human focus: only exact project-manager authority becomes live; the sole CP07
transaction, separate pre/post approvals and false-branch denial remain intact.
Public activation exposure and downstream task lineage remain subsequent work.
