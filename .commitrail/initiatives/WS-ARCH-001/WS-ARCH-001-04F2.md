# ARCH-04F2 — Authorized checker remediation handoff

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Intended merge outcome: the existing hidden completion operation atomically
  routes an exact current contributor-correctable result to TASK `needs_revision`,
  retaining its source and actual AUTH receipt without Review or acceptance effects.

## Intent and current behavior

Group 1 of the first contributor milestone requires failed post-submit work to
reach its contributor without being mistaken for a human review or acceptance.
04F1 already supplies current verified failure results; 02I-A supplies pre-submit
feedback. Neither performs this post-submit handoff. Current TASK request, source,
outcome, completion handler and SQL closure accept only `allow_review`.

This child makes the hidden lifecycle handoff representable and authorized. It
does not add a public route or response body: contributors continue to use the
existing bounded Submission/checker-history projections when public intake is
connected later.

Extend those owners rather than add another dispatcher, checker command or
findings store. Existing immutable checker results and authorized history reads
retain bounded findings. Preserve success behavior and default human review.

## Bounded change

### Allowed

- `backend/app/modules/tasks/api/post_submit_routing.py`, `routing_outcome.py`
  and `backend/app/modules/tasks/post_submit_routing/{requests,source,outcome,models}.py`:
  exact `needs_revision` request/source and one existing outcome operation.
- `backend/app/modules/tasks/evaluation_completion_delivery.py`: same invocation
  and commit-before-ACK boundary for contributor remediation.
- `backend/app/modules/authorization/domain/post_submit_routing.py`, existing
  `backend/app/modules/authorization/post_submit_routing_authorization.py`,
  `backend/app/modules/authorization/acceptance_source_contracts.py` and
  `backend/app/adapters/{auth,audit}/__init__.py`:
  bind the exact checker-remediation consequence through the same AUTH action;
  explicitly reject failure sources at acceptance-only consumers.
- `backend/app/modules/audit/schemas.py`,
  `backend/app/modules/tasks/accepted_effects.py` and
  `backend/app/adapters/tasks/routing_acceptance.py`: admit the precise audit
  transition and reject failure sources at acceptance-only consumers.
- `backend/alembic/versions/0031_checker_remediation.py`, corresponding model,
  migration fingerprint and test registrations: extend source/receipt/consequence
  database closure, preserving prior rows and evidence.
- Focused routing/AUTH contract, PostgreSQL, delivery and migration tests under
  existing owner suites; existing ART replacement integration tests may be added
  in parallel without implying a completed remediation replacement workflow.
- Current roadmap, ARCH overview/index/plan/chunk map, TASK/CHECKERS and AUTH
  canonical documentation, and this record for the affected delivered boundary.

### Not allowed

No production handler registration, public intake, new permission, human Review,
review decision, contribution/award from failure, external evaluator, payment,
claim lease, replacement Submission activation or Operator retry. No parallel
compatibility path. Setup faults remain distinct and unavailable to this
contributor handoff; infrastructure failures never become contributor blame.

## Design and decisions

Reuse TaskRoutingRequest and TaskPostSubmitRoutingManifest; add one immutable
manifest recommendation column, initializing retained success rows to
`allow_review`. Bind request, run, result, completion event, manifest and AUTH
consequence to the same recommendation. The closed new consequence is
`checker_remediation`, `evaluation_pending -> needs_revision`, with no lifecycle
generation or FinalAcceptance for either locked ReviewPolicy mode. Preserve
success-only checks at shared acceptance consumers. No duplicate result body: retain result identity/digest; CHECKERS owns its body.
`TaskRoutingOutcome` carries the closed recommendation and the handler compares
it to the completion before commit/ACK. Keep `TaskPostSubmitRouted` unchanged as
an exact reference notice: its manifest ID resolves the immutable recommendation,
and SQL binds that reference to the actual receipt. Audit binds the target state.
Do not rewrite retained events or introduce event-format fallback.

0031 replaces `guard_task_post_submit_routing_source` (0011), the request check
and `guard_task_routing_request` including completion payload (0018), and 0030's
`task_routing_context_valid`, `guard_task_routing_authority`,
`task_routing_acceptance_matches`, `task_routing_outcome_complete`, and
`guard_task_accepted_routing_state`. Both acceptance matching and accepted-state
immutability must select only `allow_review`; failure cannot freeze the task at
`needs_revision`. Application acceptance adapters explicitly reject failures.
Existing success source hashes, receipt contexts and notice payloads stay exact.

Failure takes TASK -> Assignment -> latest Submission -> locked PROJECTS facts
-> CHECKERS custody, then existing AUTH/invocation custody; no REV fence. False
success continues to acquire its REV fence first. Exact current replay returns
stored identities without repeating effects. A successor invalidates stale
completion delivery. Existing root-transaction, clock, live authority, SQL
search-path protections and immutable evidence remain intact.

Replacement ingestion remains a successor change: its canonical TASK context
must distinguish checker remediation from human revision and bind the exact
predecessor cause before public intake. Existing ART predecessor comparison is
reused; its committed admission scope is already checked by dispatch SQL.
Parallel ART proof must not invent a defect or duplicate those safeguards.

## Acceptance and verification

- Real PostgreSQL current contributor failure routes once under true and false
  review policies, retaining exact source/receipt/result/assignment/Submission.
- Both modes produce zero Review, acceptance, contribution and award effects;
  false failure does not acquire REV custody or require LIVE.
- Duplicate delivery and response loss recover identical outcomes; stale or
  foreign identifiers, substituted recommendations/results and setup faults
  cannot route. Existing success branches retain their checks.
- Caller rollback and actual audit/outbox write failure retain no partial
  transition, manifest, AUTH evidence or event. Independent sessions prove
  TASK-before-CHECKERS custody and currentness under a competing generation.
- Direct SQL rejects inconsistent request/run/manifest recommendation, incomplete
  closure and failure-to-acceptance substitution. Retained success evidence
  survives the migration; function search paths and table references are safe.
- Discriminating guard-removal probes must fail at their intended assertions,
  not fixture setup or unrelated digest errors. Reuse existing valid fixtures.
Named future regression groups (not executed proof):
`test_remediation_outcome_and_replay` (true/false and all zero-effect tables),
`test_false_remediation_does_not_wait_for_rev` (independent held REV row),
`test_remediation_rejects_crossed_source` (valid foreign controls),
`test_remediation_outcome_substitution_rolls_back`,
`test_failure_cannot_authorize_acceptance`,
`test_remediation_does_not_freeze_successor`,
`test_routing_upgrade_preserves_success_evidence` (retained 0030 true/false), and
`test_remediation_partial_effects_roll_back` (real audit/outbox insertion failure).
Direct SQL also rejects a notice referencing a different manifest/receipt.
Existing fixtures supply real authority and completion; forbidden REV method
spies and held-row tests independently prove no observation/lock for false failure.

- Run focused owner contracts, real PostgreSQL tests, migration fingerprint,
  boundaries, inventory, docs/links/Commitrail and complete hosted checks.

## Risk and review routing

- Risk class: L1.
- Reviewers: architecture/reuse, security, QA/test delta, CI integrity and
  documentation/product operations for their affected boundaries.
- Human focus: failure is contributor remediation, never acceptance or human
  revision; no premature production activation or new delivery subsystem.

## Evidence and reconciliation

Planning is based on merged main `8f5fe6e0a`, including 04F1, 04E3A and 02I-A.
Current migration head is 0030; coordinate any newly merged migration before
implementation is published. PRs 528 (external runtime), 532 (CLI correction)
and 533 (CI lanes) are separate; preserve their owners on integration.

Remaining: exact-cause replacement intake, setup-fault/Operator recovery,
production composition/false readiness, public intake and the first-layer drill.
No new capability is claimed by this plan or by parallel ART-only proof.

## Plan review dispositions

Architecture identified success-only SQL predicates that would wrongly treat a
false-policy failure as acceptance and freeze later replacement. Explicit
recommendation guards and the successor test are required above. Security/QA
added exact audit/acceptance files and discriminating tests. Outcome recommendation
is explicit; the existing reference-notice format is retained to preserve immutable
success evidence without compatibility branches. Parallel ART proof is test-only
and does not establish checker-remediation causality.
