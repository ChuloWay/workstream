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

- `backend/app/modules/authorization/catalogue.py`, `runtime.py`, `kernel.py`, and one cohesive AUTH domain/adapter module for exact typed Operator ART resources, action dispatch, system-Operator grant/lifecycle evaluation and decision evidence.
- `backend/app/modules/artifacts/authorization.py`, `router.py`, and only necessary ART owner/port code for canonical resource-fact translation and request-local production composition; preserve owner-local lineage lookup and recovery transaction ownership.
- Focused `backend/tests/authorization/` and `backend/tests/test_artifact_operator_api.py`, `test_artifact_authorization.py`, `test_artifact_recovery.py` tests using real PostgreSQL and non-overridden production AUTH; update current expected catalogue availability only with matching proof.
- `docs/spec_authorization_service.md`, `docs/engineering/authorization_activation_custody.md`, `docs/operations_artifact_storage.md`, `docs/roadmap_status.md`, and the current WS-AUTH overview/record only for affected intended-merge claims.

### Not allowed

- CLI commands, new routes, new permissions/action IDs, arbitrary Operator or cross-tenant read shortcuts, token-role authority, compatibility paths, direct SQL or object-store access from the CLI, provider activation, or retry automation.
- New business eligibility, acceptance, review, payment or artifact-retention rules; weakened tests, CI or proof gates; fabricated positive responses from denial-only authority.

## Design and decisions

Reuse the existing ART `ArtifactOperatorAuthorityFacts` and `ArtifactRecoveryAuthorityFacts` ports. ART composes canonical resource identity and all associated project IDs before calling AUTH; AUTH receives a strict typed resource context and requires the exact existing action and system-scoped human Operator grant. The authority adapter returns only the actual action, permission and persisted decision ID. Operator reads use fresh request-local decisions and preserve concealed not-found behavior. Readiness and admission usage use the existing exact `operations.artifact_storage_admission.read` action, not an alias to a generic status route.

Retry remains a separate action and evaluator path. ART keeps source, put-attempt, task and replay locks in its one recovery transaction; AUTH revalidates the current human actor/link and grant and records an exact decision within that transaction before any recovery/job/audit success can commit. Exact replay gets fresh current authority, never authority from an old read or response. Reuse the existing AUTH kernel and audit event custody; do not add an ART-owned grant evaluator or alternate factory.

Rejected alternatives: composing `operations.status.read` for admission/readiness, using only the pre-existing Operator permission tuple, or copying allow-authority test fakes into production. Each bypasses the reserved action/resource decision and planned-action gate.

## Acceptance criteria

- [ ] The eight reserved actions alone become active with exact typed resource matching; no unrelated availability or permission changes.
- [ ] A real system-scoped human Operator can read each of the eight existing GET routes through production AUTH composition. Non-Operators, inactive actors/links, malformed or missing resources, and wrong canonical lineage stay denied/concealed without provider details.
- [ ] Shared content/replica lineage cannot expose another project's custody through an incomplete or caller-invented project tuple; resource facts are canonical and decision evidence is exact.
- [ ] Retry remains independently gated: only exhausted eligible source work with matching project/task/submission/CAS, reason and key can create one recovery attempt, retry job and initiation audit. Current actor/link/grant revocation, stale CAS, changed replay and failure roll back success effects; exact replay returns the original IDs only after fresh authority.
- [ ] PostgreSQL-backed public-API tests use no authority dependency overrides for positive and negative calls. They inspect persisted decision/effect evidence where the claim requires it. Existing Local/MinIO and ART response tests remain intact.
- [ ] Current AUTH/ART docs and roadmap distinguish executable backend routes from later CLI and hosted AWS proof; no deployment or live S3 claim is inferred.

## Risk and review routing

- Risk class: L1 (authorization, tenant isolation, retry/audit atomicity).
- Required reviewers: pre-implementation security, QA and architecture plan review; exact-head implementation security, QA/test delta, architecture/reuse and documentation review. CI integrity only if CI/test workflow changes.
- Human review focus: exact system-Operator scope, multi-project resource lineage, independent retry activation and transaction-time revocation/rollback; client-only #611 remains separate.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing production deny and planned actions | source inspection of ART router, AUTH catalogue/kernel, current route tests | Confirmed on origin/main 8f65c9d74 | None for current source |
| Exact HTTP authority and concealed reads | future isolated PostgreSQL `test_artifact_operator_api.py` production-dependency cases | Planned | Must execute after implementation |
| Retry current authority, replay and rollback | future isolated PostgreSQL `test_artifact_recovery.py`/route cases and independent-session revocation race | Planned | Must execute after implementation |
| Source integrity | focused pytest, Ruff, boundary/stale/link checks and hosted complete suite | Planned | Hosted evidence pending |

## Review findings

Pre-implementation and exact-head findings will be recorded here only when material to the durable design.

## Reconciliation

- Current-source reconciliation: #598 merged AWS activation timing/source corrections; #582 remains an open live-AWS proof boundary. Neither activates these Operator actions. Open #633 (AWS Roles Anywhere) and #647 (checker image publication) have no ART Operator AUTH ownership.
- Next usable boundary: separate #611 CLI client implementation against this merged, usable public API; hosted AWS proof remains separately owned by #582.
- Remaining risks: exact production AUTH/API and PostgreSQL evidence is not yet available; do not claim this record's intended outcome delivered before those proofs pass.
