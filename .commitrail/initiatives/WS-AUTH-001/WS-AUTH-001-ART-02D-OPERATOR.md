# WS-AUTH-001-ART-02D-OPERATOR — Activate exact artifact Operator authority

- Initiative: WS-AUTH-001
- Durable disposition: Planned
- Intended merge outcome: authenticated system Operators can use the existing bounded artifact diagnosis routes and an independently authorized verification retry through canonical AUTH decisions.

## Intent

The human explicitly approved this backend prerequisite to client-only issue #611. The mounted `/api/v1/operator/artifacts` routes currently compose deny authorities, so no real caller can complete that issue. Activate only the already specified `WS-AUTH-001-ART-02D-OPERATOR` actions, leaving the subsequent CLI work in its own PR. This provides diagnosis and reasoned recovery without broad role-only reads or provider access.

## Current behavior

`app.modules.artifacts.router` supplies `DenyArtifactOperatorAuthority` and `DenyArtifactRecoveryAuthority`. `app.modules.authorization.catalogue` keeps all eight Operator actions planned. The existing positive route tests override both dependencies, so they prove response shape and ART owner behavior, not production authority. `docs/spec_authorization_service.md` reserves exact system-Operator actions and independent retry activation; ADR 0012 makes Workstream AUTH decisions, not token roles or feature-owned checks, authoritative.

## Bounded change

### Allowed

- `backend/app/modules/authorization/catalogue.py`, `runtime.py`, `kernel.py`, the existing read dispatcher and audit-domain types, and one cohesive AUTH domain/adapter module for exact typed Operator ART resources, action dispatch, system-Operator grant/lifecycle evaluation and decision evidence.
- One public `backend/app/modules/artifacts/api/operator_authority.py` contract for ART-owned authority facts/ports/evidence; `backend/app/adapters/auth/__init__.py` is the sole new AUTH factory registration. AUTH may import only the public ART contract, not `artifacts.schemas` or another private ART owner.
- `backend/app/modules/artifacts/authorization.py`, `router.py`, `schemas.py`, `operator.py`, `service.py`, and only their directly affected callers for exact owner-local lineage, public-port migration, actor-read-root cleanup, request-local factory composition, read commit/concealment and recovery transaction ownership.
- Focused `backend/tests/authorization/` and `backend/tests/test_artifact_operator_api.py`, `test_artifact_authorization.py`, `test_artifact_recovery.py` tests using real PostgreSQL and non-overridden production AUTH; update current expected catalogue availability only with matching proof. Include exact module-boundary/negative-structure checks.
- `.ci/auth-boundaries/IMPORT_LEDGER.md` only to remove the superseded `artifacts.schemas` → private AUTH runtime import; frozen edge growth remains prohibited.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json` only to record the actual reduction of pre-existing oversized AUTH kernel and ART route-test entries; no new structural debt, policy change or exception is allowed.
- `docs/spec_authorization_service.md`, `docs/engineering/authorization_activation_custody.md`, `docs/operations_authorization_service.md`, `docs/operations_artifact_storage.md`, `docs/roadmap_status.md`, and the current WS-AUTH overview/record only for affected intended-merge claims.

### Not allowed

- CLI commands, new routes, new permissions/action IDs, arbitrary Operator or cross-tenant read shortcuts, token-role authority, compatibility paths, direct SQL or object-store access from the CLI, provider activation, or retry automation.
- New business eligibility, acceptance, review, payment or artifact-retention rules; weakened tests, CI or proof gates; fabricated positive responses from denial-only authority.

## Design and decisions

Move the existing ART `ArtifactOperatorAuthorityFacts` and `ArtifactRecoveryAuthorityFacts` contracts into a public ART API module, replacing the private definitions and updating callers, not retaining aliases. ART composes canonical resource identity and the complete sorted associated project-ID set from locked owner rows before calling AUTH; AUTH imports only that public contract. Its strict typed resource context binds action, resource selector, actor identity, canonical project IDs and exact retry CAS/lineage as applicable. Only the matching existing action and current system-scoped human Operator grant can allow. The AUTH adapter stages the real action/permission/decision ID in the caller's session; it never commits. `app.adapters.auth` constructs it, and ART's dependencies consume only that factory. Readiness and admission usage use the exact `operations.artifact_storage_admission.read` action, not a generic status alias. A read resource cannot satisfy retry, nor the reverse.

This L1 change deliberately crosses AUTH catalogue/evaluator/audit, the public ART port, and ART route transaction custody in one backend PR: activating any one layer alone leaves the mounted production API deny-only or unable to retain its exact decisions. It does not include the CLI or alter an ART provider. The existing positive mock route tests masked an admission-usage response mismatch: the service already returns `int | None` for a deployment without configured limits, while its unreachable production response schema declared `int`. The route schema and OpenAPI now expose `null` for that real unconfigured state, with signed PostgreSQL and schema regressions; no client of a previously successful production surface is changed.

ART's context dependency projects the resolved actor, then rolls back the actor-resolution read root before entering its owner transaction. Each GET keeps canonical lookup, AUTH decision, response projection/validation and one success commit in a single request-owned session. Missing resources produce the same concealed 404 as AUTH denials. An AUTH denial is rolled back and the issuing AUTH kernel's *same* decision is restaged and committed in a clean AUTH-only transaction before the concealed response; a late read/response/evidence failure rolls back any allow decision and returns bounded unavailability, not 200. No adapter commits before ART's response is complete. Malformed UUID/body/query remains a bounded transport 422, not an AUTH concealment claim.

The Operator router checks the verified subject kind before actor resolution: nonhuman tokens receive the same artifact 404 as a missing resource, rather than leaking whether a fixed service actor is provisioned. This is only an ineligible-subject concealment gate; human Operator permission still requires the real persisted AUTH decision.

The existing guide-upload route directly calls that shared context dependency, rather than asking FastAPI to inject it. Its call must pass the same request-owned session so the actor-read-root rollback is real; the public guide upload regression uses production dependencies and migrated PostgreSQL/MinIO. This is an affected direct consumer, not a new guide permission.

Retry remains a separate action and evaluator path. ART keeps source, put-attempt, task and replay locks in its one recovery transaction; AUTH revalidates the current human actor/link and grant and stages exact decisions *inside* that transaction. The current ART service makes a preliminary and a terminal AUTH check for new work; both decisions commit with the chain, and only the terminal decision ID is linked by `ArtifactRecoveryInitiated`. Replay stages one fresh decision before returning the original IDs, then commits it without a duplicate chain/audit. A failed operation rolls back every staged allow decision, recovery, job and initiation audit; a denied decision is restaged by the issuing kernel only after rollback. Evidence-persistence failure is bounded unavailability, never successful retry. Reuse the existing AUTH kernel and audit event custody; do not add an ART-owned grant evaluator or alternate factory.

The old ART recovery actor pre-lock inverted the lifecycle mutation order: ART locked actor/link before AUTH could lock `AuthorityControl`, while lifecycle transitions lock control before actor/link. It is redundant once both production AUTH evaluations freshly validate actor and link. Remove only that pre-lock and keep canonical AUTH control → actor/link → grant order, with signed PostgreSQL directional retry-versus-suspend/link-revoke/grant-revoke proof. ART source, CAS and recovery effects remain ART-owned.

The old dependency-overridden HTTP test asserted that ART itself rejected a forged stale actor/link context while its fake authority always allowed. Those two assertions no longer describe the owner boundary after removing ART's redundant pre-lock; retain the surrounding ART response/CAS/replay checks and replace the lifecycle protection with signed public-API PostgreSQL tests of real AUTH, both transition orders, durable decisions, and no orphan recovery chain. Do not emulate production AUTH inside the fake.

The existing audit constraint already reserves all eight exact action/permission pairs, as confirmed against migrated PostgreSQL. No migration is needed; test durable denials and allows against that existing gate, plus direct-SQL mismatched-permission rejection for each ART action. No product data, arbitrary action string or privacy-registry change is authorized.

Rejected alternatives: composing `operations.status.read` for admission/readiness, using only the pre-existing Operator permission tuple, or copying allow-authority test fakes into production. Each bypasses the reserved action/resource decision and planned-action gate.

## Acceptance criteria

- [ ] The eight reserved actions alone become active with exact typed resource matching; no unrelated availability or permission changes.
- [ ] The existing migrated audit constraint admits only the exact action/permission pairs and still rejects mismatched evidence; without durable audit, no route reports success.
- [ ] A real system-scoped human Operator can read each of the eight existing GET routes through production AUTH composition, with the exact durable decision after a successful response. A token role without a persisted grant, non-Operator human, service actor, suspended actor, revoked link/grant, well-formed missing resource and wrong canonical lineage remain denied with the same concealed 404 envelope; malformed transport input is bounded 422 without internals. Provider fields remain redacted.
- [ ] Shared content/replica lineage cannot expose another project's custody through an incomplete or caller-invented project tuple; resource facts are canonical and decision evidence is exact.
- [ ] Retry remains independently gated: only exhausted eligible source work with matching project/task/submission/CAS, reason and key can create one recovery attempt, retry job and initiation audit. A read context never grants retry and vice versa. Current actor/link/grant revocation, stale CAS, changed replay and post-decision failure roll back success effects; exact replay returns the original IDs only after fresh authority.
- [ ] Signed-token PostgreSQL public-API tests use no override of database session, actor/context or either authority dependency for positive and negative calls. They inspect persisted decision/effect evidence in an independent session. Existing Local/MinIO and ART response tests remain intact.
- [ ] Current AUTH/ART docs and roadmap distinguish executable backend routes from later CLI and hosted AWS proof; no deployment or live S3 claim is inferred.

## Risk and review routing

- Risk class: L1 (authorization, tenant isolation, retry/audit atomicity).
- Required reviewers: pre-implementation security, QA and architecture plan review; exact-head implementation security, QA/test delta, architecture/reuse and documentation review. CI integrity only if CI/test workflow changes.
- Human review focus: exact system-Operator scope, multi-project resource lineage, independent retry activation and transaction-time revocation/rollback; client-only #611 remains separate.

## Evidence

The following are named future tests, not executed evidence. The shared fixture signs a real bearer, provisions a human through `/actors/me`, bootstraps an Access Administrator and issues a persisted system Operator grant through public administration. It uses the migrated PostgreSQL schema, real FastAPI dependencies and an independent observer session. ART seeds only canonical artifact rows needed to reach the route; no authority port or context is overridden.

| Existing surface | Exact action | ART-owned resource selector | AUTH and transaction owner |
|---|---|---|---|
| `GET /bindings` | `artifact.binding.read` | canonical product resource kind/UUID and project | typed system-Operator read; ART GET commits |
| `GET /contents/{id}/replicas` | `artifact.replica.read` | content UUID and complete associated projects | typed system-Operator read; ART GET commits |
| `GET /replicas/{id}/receipts` | `artifact.receipt.read` | replica UUID and complete associated projects | typed system-Operator read; ART GET commits |
| `GET /verification-jobs/{id}` | `artifact.verification_job.read` | job UUID and complete associated projects | typed system-Operator read; ART GET commits |
| `GET /recovery-attempts/{id}` | `artifact.recovery_attempt.read` | attempt UUID and canonical project | typed system-Operator read; ART GET commits |
| `GET /audit-events` | `artifact.audit.read` | audit resource kind/UUID and complete associated projects | typed system-Operator read; ART GET commits |
| `GET /admission-usage` | `operations.artifact_storage_admission.read` | exact project and optional task/deployment scope | typed system-Operator read; ART GET commits |
| `GET /readiness` | `operations.artifact_storage_admission.read` | deployment artifact-storage readiness selector | typed system-Operator read; ART GET commits |
| `POST /verification-jobs/{id}/retry` | `artifact.verification_job.retry` | locked source job, project/task/submission and CAS | separate typed system-Operator evaluator; ART recovery service owns commit |

| Behavior atom / owner | Future discriminating proof | Required observation |
|---|---|---|
| Exact eight-action availability and no unrelated growth / AUTH catalogue | `test_artifact_operator_action_activation_is_exact` | Before/after action/permission set; wrong typed resource/action pair denied |
| Binding, replica, receipt, job, recovery, audit GETs / ART router + AUTH read evaluator | `test_signed_operator_artifact_resource_reads_record_exact_decisions` | Six route/action pairs succeed and persist action, permission, matched grant, actor/link, resource digest and request/correlation IDs after response |
| Admission usage and readiness GETs / ART router + exact operations action | `test_signed_operator_artifact_operations_reads_record_exact_decisions` | Both operations use their shared exact action and distinct canonical resource digests; no inferred AWS activation |
| All read negative identities / AUTH evaluator and ART concealment | `test_signed_artifact_read_denial_matrix` | No grant, wrong role, token role only, service actor, suspended actor, revoked link/grant each conceal with durable matching denial; malformed input separately 422 |
| Missing, foreign and multi-project lineage / ART resolvers + AUTH digest | `test_signed_artifact_shared_content_lineage_is_complete` | Two-project content/replica, sorted complete project tuple in exact decision digest, missing/foreign 404 equivalence; dropping one project makes assertion fail |
| Read commit and late failure / ART route transaction owner | `test_artifact_read_response_failure_rolls_back_allow_decision` | Independent observer sees decision only after 200; injected post-decision response fault yields bounded error and no committed allow |
| Retry new result and typed action isolation / ART recovery + AUTH | `test_signed_artifact_retry_records_exact_atomic_authority` | 202 with exact source, attempt/job and initiation audit; two fresh allow decisions in the same commit, audit links the terminal one, no read-context substitution |
| Retry negative eligibility and rollback / ART recovery transaction | `test_signed_artifact_retry_denial_and_fault_matrix` | Mismatched lineage, stale CAS, non-exhausted source, revoked actor/link/grant, and failures after decision/job/audit/attempt staging leave zero new success facts or allow decisions; 404/409/422 remain bounded |
| Exact/changed/revoked replay / ART recovery + AUTH | `test_signed_artifact_retry_replay_rechecks_authority` | Exact replay original IDs plus one fresh decision and no duplicate chain; changed replay 409; revoked replay concealed without returning IDs |
| Revocation and same-key races / independent PostgreSQL sessions | `test_artifact_retry_revocation_and_replay_serialization` | Revocation-first: no chain/effect/allow decision. Retry-first: revocation blocks until one chain commits, later replay denies. Concurrent exact keys: one new/one replay, identical IDs, one attempt/job/initiation audit, fresh decision per call |
| Public boundary and source checks | `cd backend && .venv/bin/python -m scripts.module_boundaries validate` plus `tests/architecture/test_authorization_boundary.py`; focused pytest, Ruff, stale/link checks, hosted complete suite | No AUTH→private ART or ART→private AUTH edge, no role-only bypass, no test/CI weakening; hosted evidence remains future |

## Review findings

The first L1 plan review found that the original contract omitted production actor-root cleanup, GET decision commit/denial restaging, public ART port and AUTH composition-root ownership, and reachable negative/race fixtures. The revised bounded change and evidence matrix incorporate those blocking findings. Exact-head implementation findings remain future evidence.

## Reconciliation

- Current-source reconciliation: #598 merged AWS activation timing/source corrections; #582 remains an open live-AWS proof boundary. Neither activates these Operator actions. Open #633 (AWS Roles Anywhere) and #647 (checker image publication) have no ART Operator AUTH ownership.
- Next usable boundary: separate #611 CLI client implementation against this merged, usable public API; hosted AWS proof remains separately owned by #582.
- Remaining risks: exact production AUTH/API and PostgreSQL evidence is not yet available; do not claim this record's intended outcome delivered before those proofs pass.
- Human decision: backend prerequisite scope is explicitly approved; no new role, entitlement, provider or product-lifecycle decision is inferred. A later eligible human must approve this specific PR for merge.
