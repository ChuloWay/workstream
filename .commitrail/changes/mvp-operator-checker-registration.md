# Supported Operator external-checker registration

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: An authenticated system Operator can register one exact digest-pinned external checker through the public API, recover an exact lost-response replay, and read the immutable entry back under fresh authority.

## Intent

Fresh deployments currently need test helpers or direct service composition to
populate the external-checker registry. This bounded part of GitHub issue #580
exposes the existing immutable CHECKERS registration operation and exact
readback through the canonical bearer-token, actor-resolution and AUTH path.
It closes the registry-startup gap needed by the first automated backend MVP;
REV lifecycle exposure remains a separate later change.

## Current behavior

`ExternalCheckerRegistryService.register` in
`backend/app/modules/checkers/external_registry.py` already owns caller-root
atomic publication, fresh system-Operator authorization, immutable logical
identity, exact replay and conflict behavior. `ExternalCheckerRegistryReader`
already reconstructs the complete validated row for trusted internal
consumers. PostgreSQL migration `0029_external_checker_registry.py` enforces
the request/specification digests, authorization receipt and append-only row.

No route in `backend/app/api/router.py` exposes registration or registry
readback. Tests therefore call the service directly with fixture-built actor
contexts and registry IDs. A deployment cannot use an ordinary verified Flow
identity and system Operator grant to perform startup registration.

## Bounded change

### Allowed

- `.commitrail/changes/mvp-operator-checker-registration.md`: this bounded
  contract and durable evidence.
- `backend/app/modules/checkers/api/external.py` and
  `backend/app/modules/checkers/api/__init__.py`: the closed HTTP command/read
  values and exact read authority facts needed by the existing CHECKERS owner.
- `backend/app/modules/checkers/external_registry.py`: extend the existing
  service so it selects a UUIDv7 row ID on a new operation and recovers that
  stored ID by the exact operation key before fresh replay authorization; keep
  the same repository, immutable row and digest contract.
- `backend/app/modules/checkers/registry_router.py`,
  `backend/app/api/deps/checker_registry.py`, and
  `backend/app/api/router.py`: one authenticated Operator registration route,
  one exact-entry read route, caller-root transaction composition and stable
  HTTP error mapping.
- `backend/app/modules/authorization/catalogue.py`,
  `backend/app/modules/authorization/domain/checker_registry.py`,
  `backend/app/modules/authorization/checker_registry_authorization.py`, and
  `backend/app/modules/authorization/kernel.py`: activate an exact registry
  read action using the existing system Operator `operations.status.read`
  permission, while registration continues to use
  `operations.reconcile.run`; bind both to the registry resource and ordinary
  AUTH audit evidence.
- `backend/tests/checkers/external/{support.py,test_contracts.py,test_registry.py,test_postgresql.py,test_public_api.py}`:
  focused service and signed public-API/PostgreSQL proof.
- `backend/tests/authorization/catalogue_fixtures.py`,
  `backend/tests/authorization/test_catalogue.py`, and
  `backend/tests/authorization/setup_finalization/test_catalogue.py`: closed
  AUTH catalogue and active-action parity for the read action.
- `docs/architecture_checker_framework.md` and `docs/roadmap_status.md`: state
  only the supported registration/readback capability delivered by this PR
  and retain the remaining REV/hosted-runtime boundary.

### Not allowed

- REV controller routes, lifecycle transitions, reviewed-manifest or generation
  behavior, automatic enablement, checker execution, policy approval, routing,
  acceptance, model judges or human-review activation.
- A second registry, generic administrative bypass, direct product-row writes,
  fixture/test-package imports in production, CLI behavior, migrations, schema
  changes, retained-row update/deletion, compatibility aliases or fallback
  constructors.
- Changes owned by pull requests #575 or #577, CI work owned by #585, README
  work owned by #586, private project inputs, credentials, deployment, push,
  merge or cloud configuration.

## Design and decisions

The public mutation accepts only the existing canonical
`ExternalCheckerRegistrySpec`; the verified actor and `Idempotency-Key` supply
actor and operation identity. The existing registry service remains the sole
writer and selects `new_record_id()` only after locking the operation and
logical identity. A committed replay first recovers the stored UUID through
that operation key, reconstructs the same complete request digest, performs
fresh AUTH, and returns the original entry. Changed payload/key reuse remains a
conflict, and a revoked caller cannot recover the old result.

Readback is an exact entry-ID GET. It uses a new action ID rather than recording
a mutation-shaped decision, but maps to the Operator's existing
`operations.status.read` permission and existing registry resource boundary.
The service loads and validates the immutable row before authorization without
returning it; AUTH then locks/revalidates the actor/link/grant and records the
exact entry/request/spec facts before the route discloses the value. Missing or
unauthorized entries are concealed consistently. The registration response and
read response are the existing complete `ExternalCheckerRegistryEntry`, so no
second projection or lossy schema is introduced.

No migration is expected: the persisted registry and audit-event action field
already support the exact facts. If implementation reveals a required schema
change or an inability to keep fresh read authority and exact replay in one
caller-owned transaction, stop for a new bounded decision instead of widening
this record.

## Acceptance criteria

- [ ] A genuine bearer-authenticated human with an active system Operator grant
  can POST one valid pre-submit or post-submit digest-pinned specification and
  receives the complete persisted immutable entry; the server selects its
  UUIDv7 record ID.
- [ ] Repeating the same `Idempotency-Key` and specification after a committed
  response or simulated lost response freshly authorizes and returns the exact
  original ID, timestamps, specification/digests and registration authority
  receipt without a second registry row.
- [ ] Reusing the key with any changed specification, or registering an already
  occupied capability/version/phase with another key, returns a stable conflict
  with no registry or allow-audit partial write.
- [ ] The same Operator can GET the exact entry and receives every canonical
  registered fact. A missing ID, wrong admin role, project-scoped grant,
  service identity, revoked identity link or revoked Operator grant discloses no
  registry facts and produces no registry mutation.
- [ ] Registration and read decisions use their exact action/permission,
  actor, system scope, operation/resource ID and immutable digests. Registration
  rollback removes both the row and staged allow evidence; replay after
  revocation fails before returning the stored result.
- [ ] Real PostgreSQL and signed canonical AUTH fixtures prove success,
  denial/scope isolation, revocation, replay, payload mismatch and forced
  rollback through `/api/v1`; existing service/registry tests remain green.
- [ ] Current checker architecture and roadmap text distinguish supported
  registry preparation from still-unexposed REV lifecycle controls and from
  checker policy approval/execution.

## Risk and review routing

- Risk class: L1
- Required reviewers: `architecture`, `security`, `qa`, `test_delta`,
  `product_ops`, `reuse_dedup`, and `documentation`; the lead owns shared
  deterministic checks and final reviewer coordination.
- Human review focus: server-owned UUIDv7 replay recovery, lock/AUTH ordering,
  exact read concealment and audit facts, existing-service reuse, and avoiding
  any implication that registration activates a checker or completes issue
  #580's REV lifecycle portion.
- Human gate: lead plan acceptance before implementation; an eligible human
  separately reviews the final PR and explicitly authorizes any merge.
- Budget posture: bounded Sol-high implementation and focused PostgreSQL/API
  evidence; no urgency or token SLA was supplied.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing owner and public gap | Inspect registry service, AUTH adapter/domain, router composition, issue #580 and direct PostgreSQL tests at base `34501cd64` | Existing hidden operation and absent route confirmed | Implementation and runtime proof await accepted plan |
| Commitrail validity | `python3 scripts/check_commitrail_records.py --base-ref origin/main` | Pending | Exact-head rerun required after implementation |
| Public and PostgreSQL behavior | Focused `pytest` for checker external contracts, registry, PostgreSQL and public API using the repository isolated PostgreSQL runner | Pending | Hosted full-suite evidence remains with the lead |
| AUTH catalogue parity | Focused authorization catalogue/setup-finalization tests and stale authorization-document check | Pending | Exact-head reviewer replay remains |
| Documentation integrity | Markdown links, stale wording scan and affected roadmap reconciliation | Pending | Deployment and complete issue #580 remain outside this PR |

## Review findings

Plan review is pending before implementation. Material findings and their
disposition will be recorded here after a clean candidate exists.

## Reconciliation

- Current-source reconciliation: base `34501cd64`; open PRs #575 and #577 own
  result/read surfaces and are excluded. #585 owns CI work and #586 owns README
  work. Neither is needed to expose this existing registry owner.
- Next usable boundary: issue #580's separate authenticated REV lifecycle
  state/readback and guarded `disabled -> shadow -> live` controls, followed by
  the parent #555 real-project drill combining actual checker images.
- Remaining risks: exact-head PostgreSQL/public API proof and routed internal
  review remain pending; no registry migration or REV behavior is authorized.
