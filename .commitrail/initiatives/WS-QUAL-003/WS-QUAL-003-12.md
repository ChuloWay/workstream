# WS-QUAL-003-12 — Staged AUTH test audit and decomposition

- Initiative: WS-QUAL-003
- Durable disposition: Complete
- Intended merge outcome: complete the selected projection, actor-resolution and AUTH test-family audit and decomposition through reviewed commit checkpoints, without changing product authority or blocking product implementation.

Disposition records the intended merged outcome, not transient PR readiness.
Exact-head checks, reviewer freshness and human approval remain in the PR.

## Intent

Continue the human-authorized behavior-first test audit. A missing decision is
not evidence that an existing but mismatched decision is rejected. Preserve
valuable protection, justify each retained case, and avoid a count-driven purge.

## Human-authorized staged expansion

The human rejected ending this change at the projection-only slice and asked
for one larger AUTH cleanup PR with reviewable commit checkpoints. Preserve the
projection work below as stage A; do not create another PR for each fixture,
test family or correction. Completion now means finishing the broader selected
AUTH cleanup, not merely the original replay proof.

The stage sequence is:

1. Preserve the implemented projection replay proof and its retained-case map.
2. Inventory the actor-resolution and related AUTH monolith families, their
   shared helpers and consumers. Record every selected case's disposition and
   exact extraction destinations before changing it. Inspect product overlap.
3. Repair the deterministic first-access race proof: both requests must pass
   the initial miss, the contender must wait for the identity lock, and both
   must resolve the same persisted winner. This is hosted PostgreSQL proof,
   not two coroutines or a mocked lock presented as concurrency evidence.
4. Audit and decompose the selected oversized AUTH families into owner-scoped
   test/support modules. Remove genuinely redundant or obsolete proof only
   with named surviving protection; split mixed behaviors and correct real
   defects rather than making expectations accept them.
5. Reconcile the accumulated diff, case dispositions, structural-debt changes,
   selection and current main; run final hosted coverage and affected reviews.

The first allowed-files and acceptance tables describe stage A. The concrete
stages B–D section below adds the discovered file/test map for stages 2–4;
backend edits require its plan review first. Neither section silently permits
all AUTH files. This is scope refinement under the human's expansion, not a new
permission system or another planning PR.

Each stage ends in a coherent commit or small commit series, focused checks,
and impact-routed internal review against a frozen checkpoint. The human can
inspect each checkpoint independently. Do not edit a target while it is being
reviewed; batch valid fixes and replay affected findings before progressing.
Routine checkpoint review does not require a separate human merge or PR.
Commits are review boundaries, not a reason to trigger full CI for every tiny
edit: run focused local checks and use hosted runs for PostgreSQL stages and
the final combined head. Preserve checkpoint history while it is under review.

Final approval covers the complete PR, including cross-stage interactions;
earlier checkpoint results cannot be relabeled as final-head approval. Product
work remains independent. No forced test-count reduction, weakened CI, altered
authorization semantics or blanket repository-wide cleanup is authorized here.

## Baseline behavior

Before this change, `test_policy_and_replay.py` named a mismatched-decision test but supplied only a
random absent ID. `projection_replay_event_matches` validates eleven independent
stored facts; the old absent-row test could not detect removing any of those checks.
The old exact-replay test exercised only the sufficiency adapter and repeated a
two-service setup also present in authority-retirement and custody-guard tests.
The real kernel/PREP runs against controlled session, owner-lock and audit ports;
these tests do not execute SQL or establish real transaction isolation.

## Bounded change

### Allowed

- This record and `OVERVIEW.md`.
- Under `backend/tests/authorization/guide_compilation_projections/`:
  `support.py`, `test_policy_and_replay.py`, `test_replay_guards.py`, new
  `replay_support.py` and `test_replay_evidence.py`.
- `backend/scripts/test_lane_catalogue.py` and
  `backend/tests/test_ci_lane_catalogue.py`: exact new-module registration only.
  These are also touched by product PR377; preserve both registrations if its
  merge changes main. Do not edit the product worktree.

### Not allowed (stage A; later additions are bounded below)

Production code, public interfaces, action activation, migrations, database
reset changes, structural-debt exceptions, workflows, timeouts, thresholds,
skips, or other test families. No imports from the AUTH test monolith. No
mutation of immutable database evidence or bypassing triggers to fabricate
corruption. If the audit reveals a product defect, first document and review
the precise required scope correction; never rewrite expectations to hide it.

## Design and decisions

Extract only the duplicated two-preparation fixture into small same-owner test
support. Both preparations use fresh real PreparedAuthorizationService objects
with the same session/root transaction, actor and identity link. Honor the
fixed-service factory's request/correlation inputs rather than silently ignoring
them. Keep actual kernel/PREP matching; the fixture must not implement policy.
All modules stay below 500 lines, tests below 120 and helpers below 100.

Separate replay tests from the policy/matrix tests. Keep the absent-decision
negative under an honest missing-decision name. Parameterize the exact-replay
positive across the two adapters, with exact original decision lookup, no new
evidence and closure proof. Preserve both consumed-handle retirement cases.

For existing-decision substitution, first produce an actual allowed decision
through the real kernel/PREP. At the controlled audit-read port, return its
stored-shaped representation with exactly one field substituted, retaining the
original requested decision ID. Prove the lookup resolved an existing event
and returned the substituted representation, not None. This is a service-boundary
adversarial proof, not a claim that PostgreSQL permits immutable-event tampering.

The twelve cases exercise event type, actor, action, permission, project,
resource type, resource ID, request, correlation, allowed=False, allowed=1,
and resource digest. The two allowed cases distinguish denied outcome from
truthy non-boolean coercion. Use otherwise well-formed alternate values.
Do not cross all twelve cases with both adapters: the predicate is shared;
both adapter paths receive independent positive wiring proof instead.
No new database test is needed for that bounded service claim. Existing hosted
projection atomicity/concurrency tests remain unchanged and must still pass.

## Acceptance criteria

| Behavior | Named proof | Custody |
| --- | --- | --- |
| Exact original evidence authorizes replay for each component, without new evidence | `test_projection_exact_replay_uses_original_decision` (two components) | Real kernel/PREP, controlled ports |
| Missing decision denies without new evidence and closes | `test_projection_replay_rejects_missing_decision_without_new_evidence` | Controlled audit lookup returns None |
| Each of twelve existing-event substitutions independently denies; exact existing ID lookup occurs | `test_projection_replay_rejects_substituted_existing_decision` (named cases) | Existing kernel-produced event, one changed returned fact, real matcher |
| Denied replay retires its authority and cannot subsequently consume | Same substitution test: coupled fail-closed outcome | Real handle registry/sealed authority; no new event |
| Successful replay cannot consume either identical or changed next facts | Existing `test_projection_replay_retires_mutation_authority` | Both existing cases retained |
| Listed action/binding/transaction/scope mismatches and owner resource guard deny | Existing `test_replay_guards.py` tests | Existing cases retained; rename “every” to “listed” |
| Policy action/identity/matrix/output guards remain | Existing four non-replay policy tests | Assertions and parameters preserved |
| Missing matcher operand is actually detected | Process-local operand-removal probes | Each event predicate mutant must fail its named negative, not setup |
| Selected tests and full safety baseline remain | Catalogue tests; hosted Backend | Exact inventory, no skips/deselection, unchanged coverage floors |

## Risk and review routing

- Risk class: L1, bounded authorization test evidence.
- Required reviewers: plan review before implementation; QA/test-delta,
  security/reuse for exact evidence and shared setup, CI-integrity/documentation
  for selection, custody and honest claims. Related tracks may share an agent.
- Human review focus: substitutions hit real guards; fixture coherence; every
  retained case earns its cost; no product pause or blanket audit-complete claim.

## Evidence

Local: `backend/.venv/bin/pytest -q` for this AUTH projection directory and lane
catalogue, focused Ruff, root Commitrail, Markdown-link, stale-wording and diff
checks. Collect the changed family and compare named/expanded cases before and
after. Use out-of-tree process-local mutants; do not commit a mutation framework.
GitHub Backend exclusively owns full coverage and existing real PostgreSQL
projection concurrency/rollback execution. SQL-port proof remains separate.

## Review findings

Discovery confirms a missing proof, not a demonstrated production bypass.
Deleting the random-ID test would also lose missing-row coverage, so rename and
retain it while adding the distinct existing-row substitution boundary.
Plan review confirmed fixture feasibility and required the canonical acceptance
heading (PLAN-12-001); that mechanical correction is applied.

## Retained-case rationale and replacement map

The changed family has 21 expanded cases before this change and 34 afterward.
No behavior is deleted or skipped. Thirteen additions are twelve independently
failing stored-fact substitutions and one second-adapter positive; the shared
predicate does not receive a redundant Cartesian product with both adapters.

| Existing test suffix / cases | Disposition and distinct purpose |
| --- | --- |
| `artifact_policy_projection_uses_only_its_existing_action` / 1 | Keep exact action, permission and authority digest separation |
| `projection_requires_exact_project_setup_authority` / 6 | Keep wrong service, suspended actor and revoked link for each adapter; these are distinct identity guards |
| `projection_requires_active_action_matrix` / 4 | Keep absent matrix row and unavailable action for each adapter; neither implies the other |
| `policy_projection_rejects_wrong_deterministic_output` / 1 | Keep the caller's wrong output identity rejection |
| `projection_exact_replay_uses_original_decision` / 1 | Move to `test_replay_evidence.py`; retain digest parity and add artifact-policy wiring, exact lookup and evidence fields |
| `projection_replay_retires_mutation_authority` / 2 | Move; keep both unchanged and changed next-fact attempts after successful replay |
| `projection_replay_rejects_mismatched_decision_without_new_evidence` / 1 | Rename to `projection_replay_rejects_missing_decision_without_new_evidence`; an absent ID proves absence, not substitution |
| `projection_replay_rejects_every_prepared_custody_mismatch` / 4 | Rename `every` to `listed`; retain action, caller binding, replaced transaction and scope guards |
| `projection_replay_rejects_project_setup_resource_guard` / 1 | Keep owner-resource rejection, separately from handle custody |

All suffixes above have the `test_` prefix. The four non-replay policy tests
retain AST-identical bodies and parameter sets. Repeated original/replay
preparation is replaced by `ReplayCase`, not a second authorization evaluator.
The historical AUTH-12J pre-cutover contract's old `every` and `mismatched`
references resolve through this map; the historical snapshot is not rewritten.
The two old test modules shrink from 480 to 257 lines; with the new 84-line
support, 174-line evidence module and two net support lines, this family grows by
37 lines (685 to 722) to cover the missing behavior. This is proof repair, not a claimed
test-count or source-volume reduction.

The new negative cases each substitute only one returned fact of the exact
existing decision. They assert denial, spent authority, no new event and an
unchanged deep snapshot of the original evidence; a mutable alias cannot stand
in for an immutable comparison. Successful replay checks each adapter's
explicit action/permission/resource shape, rather than deriving all expected
values from the implementation under test.

## Concrete stages B–D: authentication and actor-resolution proof

This extension makes stages 2–4 concrete under the existing human-authorized
single-PR expansion. The implementation checkpoint below records the selected repairs;
its review and hosted execution remain distinct from the plan's feasibility proof.
The reviewed starting source is `ca86fb38e8d9d4fb4dafc9cd0256fa0aa6ed6de6`.

### Selected boundary and additional allowed files

Audit all 34 named tests in `backend/tests/test_actors.py`, the 51 selected
authentication tests listed below from `backend/tests/test_auth.py`, and the
shared controlled AUTH runtime helpers currently housed in
`backend/tests/test_authorization.py`. Do not audit or rewrite the unrelated
grant/bootstrap/admin lifecycle tests remaining in either AUTH monolith.

Additional allowed files:

- `backend/tests/test_actors.py` (remove after all selected proof is mapped).
- `backend/tests/test_auth.py` (selected cases and shared helper imports only).
- `backend/tests/test_authorization.py` (helper extraction/imports only).
- `backend/tests/test_artifact_authorization.py` and
  `backend/tests/test_submission_preparation_authorization.py` (replace their
  imports of test-bearing AUTH monolith helpers; test bodies unchanged).
- `backend/tests/authorization/runtime_support.py` for the five existing
  controlled runtime helpers; retain sentinel/default behavior, do not build
  another evaluator or imply real SQL/session custody.
- The exact new test modules in the two destination tables below; additionally
  `backend/tests/authentication/__init__.py`, `support.py`, `fixtures.py`,
  `conftest.py`, `concurrency_support.py`, and
  `backend/tests/actors/support.py`, `fixtures.py`, `conftest.py`,
  `first_access_support.py`, and `__init__.py`. The actor package marker is a
  reviewed fixture-scope correction: without it, pytest loads its `conftest.py`
  as the root module and breaks existing database-reset collection. Do not
  change database-reset behavior to accommodate the extraction.
  Support modules contain setup or coordination,
  not hidden product assertions that replace the test's primary behavior.
- Existing `backend/tests/auth_concurrency_support.py`: only if the first-access
  proof needs a bounded extension of the real observer; otherwise reuse unchanged.
- `backend/tests/test_auth_concurrency_observer.py`: prove the optional exact
  waiter/blocker selectors on the existing observer, including wrong-blocker
  rejection. Preserve its original fresh-versus-cached snapshot regression.
- `backend/scripts/test_structure_boundary.py` and
  `backend/tests/architecture/test_test_structure_boundary.py`: explicitly
  include the authentication/actor test directories in existing structural and
  assertion-map enforcement. Extraction must not escape checks merely because
  a filename no longer contains "auth" or imports AUTH directly.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: reconcile shrinking/deleted
  selected entries and shifted unchanged spans from actual inventory only.
  No new debt, raised limits, or same-size rewritten exceptions.
- `.ci/auth-boundaries/assertion-maps/WS-QUAL-003-12.json`: exact ancestor,
  per-assertion hashes and final surviving node mapping through the existing
  validator. No new mapping engine or duplicate proof framework.
- The already-allowed lane catalogue and catalogue test: register all extracted
  test modules in their existing shared lanes; remove the deleted monolith
  registration only when all its cases have destinations.

All production code, routes, database reset behavior, migrations, timeouts,
coverage floors, workflow policy and product implementation remain prohibited.
This includes changing production AUTH merely to improve test coverage.
A demonstrated runtime defect requires a precise reviewed correction to this
record before a repair; the human has authorized defect repair, not arbitrary
scope expansion. No files in the product worktree are touched.

### Behavior decisions and proof requirements

Preserve real RSA signatures, issuer/audience/time validation, bounded network
clients and credential isolation. Fixtures remain owner-local: cache cleanup
applies to the same authentication families, database fixtures remain opt-in,
and existing actor eligibility tests do not acquire new autouse DB setup.
A moved helper must preserve module-scoped RSA fixture behavior. Explicitly
re-export shared RSA/cache fixtures into the remaining `test_auth.py`; keep its
opt-in database fixture unchanged. Delete the unused actor `alembic_config`
helper rather than carrying dead setup into a new module. Preserve path
resolution wherever paths are actually used.

Separately prove the 32-role cap and overlength-role filtering. Place the
overlength role before valid roles; the old final-position example was masked
by the count cap. Compatibility normalization remains a current boundary.

The old JWKS lock-wait test delays HTTP without holding the refresh lock. Keep
that useful behavior as `test_jwks_http_request_is_inside_total_deadline`; add
`test_jwks_lock_wait_is_inside_total_deadline` that holds the actual lock,
expects the typed key-resolution timeout and observes zero HTTP requests.
An outer safety timeout must not count as the expected application exception.

The same-kid and distinct-kid single-flight tests currently use gather with a
synchronous transport. Replace that incidental schedule with a held async
refresh and observed acquisition of the real refresh lock by the contender.
Both return the expected unknown-key denial and only one refresh occurs.
The distinct-kid case separately exercises generation reuse. Probe that removing
the outer resolution deadline and bypassing refresh exclusion respectively
break these named tests; use out-of-tree process-local probes, not production
edits or a committed mutation framework.

The actor first-access race must use two independent database sessions and
backend PIDs. Both initial lookups return real misses before either provisioning
transaction is released. The winner holds the actual identity advisory lock;
the contender is observed blocked on that exact backend (not merely any Lock
wait). Release the winner only after that observation. Assert the loser's
post-lock lookup returns the same stored profile/link and follows touch, with
exactly one profile, one link and one creation-event pair. Assert both complete
persisted events: request/correlation, actor/target references, entity/resource
IDs, event types and after_facts belong to the winner. The contender must not
create another pair. Cleanup awaits or cancels tasks on failure so no locks leak. The existing
`test_concurrent_first_access_leaves_one_profile_link_and_event_pair` becomes
this deterministic proof; PostgreSQL execution is hosted-only.

Keep revocation/update and legacy-activation concurrency proofs with real
transactions, adding exact waiter/blocker observation before releasing either
holder. Extend the existing AUTOCOMMIT observer with expected waiter/blocker PIDs
rather than duplicating its polling loop. Prove a wrong blocker cannot satisfy
the observation. Seed deliberately old persisted timestamps for repeated-access
advancement; do not depend on a timing sleep. Rate-limit denial forbids profiles,
links and provisioning/decision evidence, matching unavailable-rate-control proof.
The controlled authorization-lock test gains one-fact-at-a-time
profile/link owner, issuer, subject and kind substitution with exact selector
arguments and lock flags. Keep missing-profile and missing-link cases separate
from the drift matrix and valid control; do not call this direct-SQL or database locking proof.
Split the mixed existing-actor/legacy negative bucket. Only its duplicate
`resolve_verified_actor(service_token)` rejection may map to
`test_unknown_service_creates_nothing`; suspended,
revoked, malformed stored profile and unknown-legacy cases retain distinct
survivors. Historical compatibility behavior is not obsolete just because its
name says legacy: it remains protected while current runtime consumers exist.

Every selected test keeps its parameters and assertions unless the concrete
disposition below specifies a split/strengthening or a stronger named survivor.
Final assertion maps must explain each old assertion, including redundant
assertions, and point to actual final test nodes. A pure move is intermediate
decomposition evidence, not a completed semantic audit. New modules stay below
500 lines, tests at most 120, helpers at most 100. Remaining untouched debt is
reported honestly, not hidden by moving it.

### Authentication case destinations

Sources are `backend/tests/test_auth.py`; destinations are relative to
`backend/tests/authentication/`. An unchanged name means preserve the existing
named behavior and its parameter matrix; split cases get final node-level
assertion mappings before the checkpoint is accepted.

| Source test | Destination | Disposition |
| --- | --- | --- |
| `test_local_hmac_fixture_uses_final_claim_shape` | `test_local_verifiers.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_flow_auth_rejects_subject_above_persisted_identity_bound` | `test_local_verifiers.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_flow_auth_rejects_subject_whitespace_before_persistence` | `test_local_verifiers.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_local_hmac_fixture_is_impossible_in_production` | `test_local_verifiers.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_asymmetric_token_returns_minimal_canonical_contract` | `test_token_contract.py` | Split canonical output from token-free JWKS transport proof. |
| `test_untrusted_or_remote_key_headers_fail_before_jwks` | `test_token_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_missing_kid_fails_before_jwks` | `test_token_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_jwks_cache_hit_avoids_second_network_request` | `test_jwks_cache.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_verifier_metrics_enforce_closed_labels_without_identity_values` | `test_jwks_cache.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_unknown_kid_refreshes_once_then_uses_bounded_negative_cache` | `test_jwks_cache.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_unknown_kid_refresh_is_single_flight` | `test_jwks_concurrency.py` | Strengthen: hold real refresh and observe actual contending lock acquisition. |
| `test_distinct_unknown_kids_share_one_refresh_generation` | `test_jwks_concurrency.py` | Strengthen: distinct-kid overlap must reuse the winner generation. |
| `test_jwks_lock_wait_is_inside_total_deadline` | `test_jwks_concurrency.py` | Rename existing HTTP timeout honestly; add actual held-lock deadline proof. |
| `test_rotation_clears_matching_negative_kid` | `test_jwks_cache.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_negative_kid_cache_is_ttl_and_size_bounded` | `test_jwks_cache.py` | Split eviction and expiry into separately failing behaviors. |
| `test_expired_jwks_cache_refreshes_during_longer_unknown_kid_cooldown` | `test_jwks_cache.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_refresh_failure_cooldown_preserves_valid_cached_key_hits` | `test_jwks_cache.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_verified_token_claim_failures_are_closed` | `test_token_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_missing_mandatory_claims_fail_closed` | `test_token_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_malformed_tokens_fail_without_network` | `test_token_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_flow_verifier_rejects_ambiguous_clients_and_malformed_claim_collections` | `test_input_contracts.py` | Split client ambiguity, audience, scopes and key strength; replace UUID truthiness with identity relation proof. |
| `test_token_size_limits_fail_before_network` | `test_token_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_temporal_claims_honor_configured_skew` | `test_token_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_service_and_agent_tokens_receive_no_legacy_authority` | `test_subject_authority.py` | Split canonical token shape, agent route denial and service-scope denial; redundant direct denial requires named route survivor. |
| `test_jwks_unavailability_is_typed_and_redacted` | `test_jwks_boundaries.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_invalid_jwks_documents_fail_closed` | `test_jwks_boundaries.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_weak_rsa_signing_key_is_rejected` | `test_jwks_boundaries.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_incompatible_jwk_metadata_is_rejected` | `test_jwks_boundaries.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_malformed_and_excessive_jwks_fail_closed` | `test_jwks_boundaries.py` | Separate invalid JSON from excessive key count. |
| `test_jwks_redirect_does_not_receive_or_forward_bearer` | `test_jwks_boundaries.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_oversized_jwks_response_fails_before_json_buffering` | `test_jwks_boundaries.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_required_introspection_is_separate_bound_and_no_redirect` | `test_introspection.py` | Split successful credential isolation from redirect rejection. |
| `test_jwks_and_introspection_use_distinct_owned_client_factories` | `test_introspection.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_required_introspection_fails_closed_on_inactive_or_mismatch` | `test_introspection.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_required_introspection_rejects_missing_identity_fields` | `test_introspection.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_introspection_response_failures_are_redacted` | `test_introspection.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_introspection_transport_error_drops_credential_bearing_exception` | `test_introspection.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_introspection_total_timeout_fails_closed` | `test_introspection.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_missing_bearer_token_is_rejected` | `test_admission.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_invalid_bearer_token_is_rejected` | `test_admission.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_invalid_production_verifier_configuration_is_service_unavailable` | `test_admission.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_actor_id_uses_subject_and_issuer_not_email` | `test_development_contract.py` | Strengthen issuer and subject distinctions; retain email invariance. |
| `test_dev_auth_requires_explicit_development_environment` | `test_development_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_dev_auth_allows_only_development_environments` | `test_development_contract.py` | Replace object truthiness with successful configured verification. |
| `test_dev_auth_requires_explicit_identity_fields` | `test_development_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_dev_auth_rejects_whitespace_only_identity_anchors` | `test_development_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_dev_auth_rejects_surrounding_identity_anchor_whitespace` | `test_development_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_dev_auth_rejects_issuer_above_persisted_utf8_bound` | `test_development_contract.py` | Separate dev, local-HMAC and production-Flow configuration rejection. |
| `test_flow_auth_verifier_boundary_rejects_unconfigured_verification` | `test_development_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_flow_role_normalization_ignores_non_string_values` | `test_development_contract.py` | Retain and audit the named invariant; preserve independent parameters. |
| `test_dev_role_normalization_uses_bounded_compatibility_contract` | `test_development_contract.py` | Retain and audit the named invariant; preserve independent parameters. |

### Actor case destinations

Sources are `backend/tests/test_actors.py`; destinations are relative to
`backend/tests/actors/`. Existing candidate-query pagination, status filters,
API denial side effects and PostgreSQL event/rollback assertions remain
required; a smaller file does not itself justify removing any of them.

| Source test | Destination | Disposition |
| --- | --- | --- |
| `test_candidate_exists_query_is_backed_by_one_link_per_profile_constraint` | `test_repository_contract.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_contributor_candidate_query_filters_and_paginates_without_gaps` | `test_repository_contract.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_actor_admin_response_requires_exact_service_identity_pair` | `test_admin_views.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_service_admission_rejects_malformed_stored_identity_without_writes` | `test_resolution_service.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_actor_admin_reads_are_bounded_and_reuse_exact_repository_lookups` | `test_admin_views.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_service_identity_lock_has_a_distinct_domain_without_changing_external_keys` | `test_repository_contract.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_actor_resolution_fails_closed_on_profile_or_subject_kind_drift` | `test_resolution_service.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_actor_authorization_lock_rejects_disappearance_and_identity_drift` | `test_authorization_locks.py` | Strengthen exact selectors and one-field identity-drift matrix. |
| `test_active_human_write_actor_revalidates_exact_profile_then_link` | `test_authorization_locks.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_actor_timestamp_touch_fails_closed_before_writes_on_missing_rows` | `test_repository_contract.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_first_human_access_atomically_creates_profile_link_and_events` | `test_first_access_postgresql.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_concurrent_first_access_leaves_one_profile_link_and_event_pair` | `test_first_access_postgresql.py` | Strengthen actual dual-miss, exact-lock-wait and winner-reuse proof. |
| `test_repeated_verified_access_reuses_actor_and_advances_database_timestamps` | `test_first_access_postgresql.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_first_access_rolls_back_profile_link_and_first_audit_on_second_audit_failure` | `test_first_access_postgresql.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_unsupported_subject_kinds_create_nothing` | `test_resolution_service.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_unknown_service_creates_nothing` | `test_resolution_service.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_actors_me_returns_contributor_without_token_role_authority` | `test_self_api.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_patch_actors_me_updates_only_display_fields` | `test_self_api.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_patch_actors_me_maps_database_failure_to_retryable_unavailable` | `test_self_api.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_actor_self_evidence_failure_is_retryable_and_rolls_back_touch` | `test_self_api.py` | Rename to `test_actor_self_evidence_failure_is_retryable_before_touch`; prove no touch occurs when earlier AUTH evidence fails. |
| `test_missing_bearer_has_no_actor_self_decision_evidence` | `test_self_api.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_suspended_profile_is_readable_but_not_mutable` | `test_self_api_lifecycle.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_revoked_identity_link_is_denied_by_actor_api` | `test_self_api_lifecycle.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_deactivated_actor_is_denied_by_actor_self_api` | `test_self_api_lifecycle.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_nonhuman_actor_self_api_denials_create_nothing` | `test_self_api_lifecycle.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_revocation_wins_synchronized_actor_update_recheck` | `test_self_api_lifecycle.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_actor_api_accepts_verifier_identity_bounds` | `test_identity_bounds_and_rate_controls.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_verified_identity_rejects_values_above_persisted_provenance_bound` | `test_identity_bounds_and_rate_controls.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_first_access_rate_limit_denies_without_actor_write` | `test_identity_bounds_and_rate_controls.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_first_access_rate_control_unavailable_fails_closed` | `test_identity_bounds_and_rate_controls.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_legacy_activation_writes_only_compatibility_metadata` | `test_legacy_eligibility_postgresql.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_repeated_legacy_activation_updates_one_row_and_audits_only_changes` | `test_legacy_eligibility_postgresql.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_concurrent_legacy_activation_serializes_payloads_and_actual_audits` | `test_legacy_eligibility_postgresql.py` | Retain and audit named behavior; preserve existing real/controlled custody. |
| `test_existing_actor_and_legacy_negative_states_fail_closed` | `test_legacy_eligibility_postgresql.py` | Split resolution negatives into test_resolution_service.py and legacy negatives here; remove duplicate service rejection only with named survivor. |

### Checkpoint acceptance and execution custody

| Independent outcome | Named proof or comparison | Custody |
| --- | --- | --- |
| Original tests have no unmapped lost assertions | Existing `validate_assertion_maps` plus QA old/new source review | Static exact-ancestor mapping; semantic reviewer checks survival |
| Moved files remain enforced | New `test_actor_and_authentication_tests_remain_in_structure_scope` | Negative-structure fixture for both directories without AUTH imports |
| No new debt is accepted | Existing `test_repository_structural_debt_equals_the_frozen_ledger` and trusted-ledger validation | Actual current source inventory |
| No helper consumer imports a test-bearing monolith | AST inspection of the three consumers and support imports | Negative structure; unchanged consumer test bodies |
| Each selected authentication behavior survives or improves | Named table cases and their final mapped split nodes | Focused real verifier tests locally; no live network |
| Key-resolution deadline includes lock wait | `test_jwks_lock_wait_is_inside_total_deadline` | Real asyncio lock with no HTTP access; deadline-removal probe |
| Refresh single-flight is genuine | `test_unknown_kid_refresh_is_single_flight`, same-kid and distinct-kid-after-cooldown cases | Observed real lock contention and held async transport; exclusion- and generation-removal probes |
| First-access race produces one persisted identity | Existing first-access race name, strengthened | Hosted PostgreSQL, independent PIDs, both misses, exact blocker |
| Revocation and legacy concurrent mutation protections survive | Existing named actor race tests in destination table | Hosted PostgreSQL; no mock downgrade |
| Lane discovery includes all moved proof | Existing lane catalogue/discovery tests and hosted final manifest | Exact source/destination node reconciliation, no skips/deselections |
| Coverage protection remains | Hosted Backend global gate and changed-subsystem gates | Full hosted suite only; no local full coverage |

Local focused commands from `backend/`: `.venv/bin/pytest -q
tests/authentication/`, the controlled actor nodes explicitly identified during
implementation, `tests/test_ci_lane_catalogue.py`, and
`tests/architecture/test_test_structure_boundary.py`. Root Markdown links,
stale wording, Commitrail and diff checks remain required. Run Ruff only on
changed Python files. Collect-only can inventory PostgreSQL families but is
never reported as their execution. GitHub owns all actor persistence/race,
unchanged helper-consumer integration and full coverage evidence.

Before backend edits, plan review checks this concrete map and fixture
feasibility. Checkpoints then route QA/test-delta for preservation and behavior
quality, security/reuse for verifier and lock custody, and CI-integrity/docs for
selection, debt and honest remaining-scope reporting. Architecture review is
needed only if inspection finds a changed runtime/public boundary; none is
planned. Reuse existing focused reviewers; no blanket nine-agent fanout.

### Implementation checkpoint: what changed and why

The 85 selected original functions contained 141 expanded cases: 104
authentication and 37 actor cases. Their replacements collect 198: 127 and 71.
That increase is primarily independently named failures formerly hidden inside
loops and mixed tests, not 57 new product behaviors. The exact 331 original
assertion spans are mapped to surviving nodes in the required machine-readable
assertion map. A map verifies custody; semantic review must still verify meaning.

The 1,594-line actor monolith is removed. The remaining authentication monolith
shrinks from 7,304 to 5,822 lines; extracting AUTH runtime helpers reduces its
consumer monolith from 13,384 to 13,318. These files are not yet fully decomposed.
All new actor/authentication files remain below 500 lines. The remaining
23 authentication tests, 163 AUTH tests, and 16 external helper-consumer tests
retain identical AST bodies. Their broader lifecycle audit is not claimed here.

| Repair | Why the retained proof earns its cost |
| --- | --- |
| Real JWKS lock deadline, single-flight and generation reuse | Old delayed-HTTP/gather tests survived deadline/exclusion removal. New tests detect a held-lock timeout and duplicate HTTP; cooldown is expired independently for generation reuse. |
| Duplicate JWK and overlength role fixtures | Otherwise-valid duplicate keys and a long role before valid roles prevent unrelated validation/count guards from masking the intended defect. |
| Rotation clears a still-live negative entry | A short positive-key TTL forces refresh while the longer negative TTL remains live. Assert that rotation removes the matching entry; positive-key verification alone bypasses the negative cache and cannot prove cleanup. |
| Actor identity substitutions and bounded candidate query | Exact controlled selectors reject one changed identity field at a time; ordered real rows place ineligible candidates before eligible rows so pagination cannot conceal a missing filter. |
| Three PostgreSQL races | First-access, revocation and legacy activation observe the actual waiter blocked on the exact holder before release; tasks are awaited/cancelled on failure. |
| Staged rollback versus early denial | First-access audit failure observes stored transaction-local rows/event before failing. Self-update failure observes staged timestamps/evidence; earlier evidence failure proves touch never ran. |
| Event provenance, timestamp and no-effect checks | Winner request/correlation and both event shapes are exact; timestamps are seeded instead of sleeping; rate/admission denial forbids links and events as well as profiles. |

Only redundant proof is pruned: the malformed wrong-use JWKS parameter is
replaced by the existing valid-key `test_incompatible_jwk_metadata_is_rejected`
use case; direct agent-admission rejection survives through the actual agent
route; duplicate service-token rejection survives in
`test_unknown_service_creates_nothing`. The distinct known-service human-entry
denial remains separately named. UUID/object truthiness is replaced with actual
identity relations and successful verification. No legacy product path is
removed merely because its name says legacy.

The exact-PID observer regression first establishes a real blocked connection,
then uses one actual observer query for each selector. Its test-only poll
override checks that the unchanged default is 5,000; it does not spend thousands
of queries proving the same deliberately wrong PID remains wrong. The original
late-waiter/fresh-snapshot regression retains its normal polling behavior.

## Source reconciliation

- Source reconciliation: discovery used main `369903ae`, including merged
  observer repair PR378. Integrated base `8c00fb3d` also includes PR376's
  Commitrail contribution-path simplification. Product PR377 owns finalization,
  not this AUTH replay family.
- Next audit boundary after this change: the remaining AUTH lifecycle families
  in the monoliths need their own behavior inventory and bounded plan. Do not
  repeat this selected actor/authentication audit or infer that all AUTH tests
  are repaired. Product work continues independently.
- Remaining risks: PostgreSQL integrity and owner-query isolation are separate
  proof boundaries; most repository tests remain unaudited.
