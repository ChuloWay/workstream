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
  service with one two-phase operation: prepare and retain current authority,
  lock registry operation/logical identity, recover or select the durable
  UUIDv7, then finalize exact authority before insert or replay; keep the same
  repository, immutable row and digest contract.
- `backend/app/modules/checkers/router.py`,
  `backend/app/api/deps/checker_registry.py`, and
  `backend/app/api/router.py`: one authenticated Operator registration route,
  one exact-entry read route, caller-root transaction composition and stable
  HTTP error mapping.
- `backend/app/api/deps/api_controls.py`: describe the existing administrative
  mutation limiter now attached to the registration route without changing its
  policy or adding a new rate-control path.
- `backend/alembic/versions/0051_operational_read_audit.py` and
  `backend/alembic/env.py`: extend the existing closed AUTH audit vocabulary
  with exactly the current registry-read and retry-source-read action pairs.
  The registry's signed PostgreSQL readback exposed this concrete prerequisite;
  the adjacent recovery chunk consumes the same canonical migration rather
  than creating a sibling schema head.
- `backend/app/adapters/auth/__init__.py`: compose the existing AUTH kernel and
  opaque prepared-authority service for the request-scoped registry adapter;
  no second factory or fallback composition is allowed.
- `backend/app/adapters/checkers/__init__.py`: compose the existing private
  registry service through CHECKERS' established adapter root without adding a
  delivery-to-private-module dependency.
- `backend/app/modules/authorization/catalogue.py`,
  `backend/app/modules/authorization/domain/checker_registry.py`,
  `backend/app/modules/authorization/domain/action_groups.py`,
  `backend/app/modules/authorization/checker_registry_authorization.py`, and
  `backend/app/modules/authorization/{kernel.py,prepared.py,prepared_admin_authority.py}`:
  reuse the existing opaque prepared-authority protocol for registration and
  activate an exact registry read action using the existing system Operator
  `operations.status.read` permission. Registration continues to use
  `operations.reconcile.run`; both actions bind the registry resource and
  ordinary AUTH audit evidence. No general AUTH lock-order redesign is allowed.
  The existing prepared-denial classifier admits only the exact registry
  mutation resource, and the kernel reuses the existing project-scoped admin
  mutation classification without changing its action set.
- `backend/tests/checkers/external/{support.py,test_contracts.py,test_registry.py,test_postgresql.py,test_public_api.py,test_migration.py}`:
  focused service and signed public-API/PostgreSQL proof.
- `backend/tests/conftest.py`: refresh the exact canonical public-schema
  fingerprint measured from a fresh real PostgreSQL graph through revision
  `0051_operational_read_audit`; the graph delta after main's contributor-read revision is limited to the existing
  audit constraint's two allowed operational-read pairs.
- `backend/tests/test_alembic.py`: retain the exact single-root migration graph
  through main revision `0050_contributor_reads` and this change's
  `0051_operational_read_audit` head.
- `backend/tests/authorization/catalogue_fixtures.py`,
  `backend/tests/authorization/test_catalogue.py`, and
  `backend/tests/authorization/setup_finalization/test_catalogue.py`, plus
  `backend/tests/test_api_controls.py`: closed AUTH catalogue and active-action
  parity for the read action.
- `backend/tests/test_api_rate_controls.py`: retain the global dependency guard
  while admitting only the registry POST/admin-mutation and exact-entry
  GET/authorization-read limiter bindings.
- `backend/tests/projects/guide_activation/source_fixtures.py`: update the one
  existing direct registration caller to the server-selected registry-ID
  contract without an optional-ID or compatibility path.
- `backend/scripts/test_lane_catalogue.py` and
  `backend/tests/test_ci_lane_catalogue.py`: assign the new public registry test
  module to the existing checker-delivery family and update only its exact
  membership fingerprints.
- `backend/scripts/behavior_ownership.py` and
  `.ci/behavior-ownership/partition.v1.json`: assign the new request dependency
  to the existing registry/artifact behavior owner and update only the exact
  partition membership and authority digest.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: refresh only the exact
  whole-file fingerprint for the existing oversized AUTH kernel after its
  closed action sets change and reuse of the existing shared project-scoped
  mutation classification reduces that file by two lines; no limit or
  exception changes are allowed.
- `mcp_server/contracts/authorization_context_get.json`: refresh the captured
  authorization-context schema for the newly active registry-read ActionId.
- `docs/architecture_checker_framework.md` and `docs/roadmap_status.md`: state
  only the supported registration/readback capability delivered by this PR
  and retain the remaining REV/hosted-runtime boundary.

### Not allowed

- REV controller routes, lifecycle transitions, reviewed-manifest or generation
  behavior, automatic enablement, checker execution, policy approval, routing,
  acceptance, model judges or human-review activation.
- A second registry, generic administrative bypass, direct product-row writes,
  fixture/test-package imports in production, CLI behavior, schema changes
  beyond the exact two current operational-read audit pairs, retained-row
  update/deletion, compatibility aliases or fallback constructors.
- Changes owned by pull requests #575 or #577, CI behavior owned by #585 beyond
  the required exact registration of this new test module, README work owned by
  #586, private project inputs, credentials, deployment, push, merge or cloud
  configuration.

## Design and decisions

The public mutation accepts only the existing canonical
`ExternalCheckerRegistrySpec`; the verified actor and `Idempotency-Key` supply
actor and operation identity. Registration uses AUTH's existing opaque
prepared-authority machinery in one root transaction:

1. Prepare `checker.registry.register` by locking and revalidating the exact
   actor, identity link and active system Operator grant.
2. While retaining those AUTH locks, take the registry operation and logical
   capability/version/phase locks.
3. Reread the operation winner and either recover its stored UUID or select
   exactly one `new_record_id()` UUIDv7 for a new row.
4. Construct the complete current registration request plus request/spec
   digests using that durable UUID.
5. Consume the opaque prepared handle to finalize and stage exact AUTH evidence.
6. Insert or return only the UUID and digests named by that decision.

This AUTH-first ordering extends the current operation through the existing
`PreparedAuthorizationService`; it does not expose an AUTH lock primitive to
CHECKERS or add another permission evaluator. A committed replay recovers the
stored UUID before final exact AUTH and returns the original entry. Changed
payload/key reuse remains a conflict, and a revoked caller cannot recover the
old result. Independent same-key sessions must serialize to one stored UUID;
every committed allow event must name that same UUID, operation, request digest
and entry digest. The direct guide-activation fixture adopts this command
contract and no caller-selected-ID constructor remains.

Readback is an exact entry-ID GET. It uses a new action ID rather than recording
a mutation-shaped decision, but maps to the Operator's existing
`operations.status.read` permission and existing registry resource boundary.
The service loads and validates the immutable row before authorization without
returning it; AUTH then locks/revalidates the actor/link/grant and records the
exact entry/request/spec facts before the route discloses the value. Missing or
unauthorized entries are concealed consistently. The registration response and
read response are the existing complete `ExternalCheckerRegistryEntry`, so no
second projection or lossy schema is introduced.

The public dependency owns distinct transaction outcomes. A canonical AUTH
denial is concealed and committed only through a typed registration/read
denial path so its staged denial evidence survives; no CHECKERS effect is
retained. Payload/key or logical-identity conflicts roll back any staged allow
evidence. Storage, audit or prepared-authority failure rolls back everything
and returns retryable unavailability. On success, the dependency first
round-trips the response through its declared Pydantic type to detach and
validate it, then commits the registry row and allow evidence together before
returning. Read success likewise commits its allow evidence only after the
detached response is valid.

Runtime proof revealed one concrete closed-vocabulary gap: PostgreSQL accepted
the existing registry mutation audit pair but rejected the active registry
read pair before its allowed decision could commit. The same constraint also
omitted the adjacent retry-source read action that recovery proved through its
public API. One forward migration therefore admits exactly
`checker.registry.read` and `operations.checker_retry_source.list`, both with
the existing `operations.status.read` permission. Direct SQL regression proof
accepts those two pairs and rejects each crossed to
`operations.reconcile.run`; no table, column, retained row or permission is
added or rewritten.

## Acceptance criteria

- [ ] A genuine bearer-authenticated human with an active system Operator grant
  can POST one valid pre-submit or post-submit digest-pinned specification and
  receives the complete persisted immutable entry; the server selects its
  UUIDv7 record ID.
- [ ] Repeating the same `Idempotency-Key` and specification after a committed
  response or simulated lost response freshly authorizes and returns the exact
  original ID, timestamps, specification/digests and registration authority
  receipt without a second registry row. Independent same-key sessions produce
  one row and only allow events whose resource ID, operation, request digest and
  entry digest equal the stored/returned facts.
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
- [ ] The closed PostgreSQL audit vocabulary accepts only the exact registry
  and retry-source read actions with `operations.status.read`; crossed
  permissions still fail the existing action-evidence constraint.
- [ ] Crossed real-session Operator-grant and identity-link revocation races
  prove both legal serial orders: registration holding prepared authority
  completes with exact evidence before revocation, while revocation winning
  first denies registration with no row or allow; no stale allow crosses either
  locked boundary.
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
  prepared-handle binding/denial custody, exact concurrent audit facts, exact
  read concealment, existing-service reuse, and avoiding any implication that
  registration activates a checker or completes issue #580's REV lifecycle
  portion.
- Human gate: lead plan acceptance before implementation; an eligible human
  separately reviews the final PR and explicitly authorizes any merge.
- Budget posture: bounded Sol-high implementation and focused PostgreSQL/API
  evidence; no urgency or token SLA was supplied.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing owner and public gap | Inspect registry service, AUTH adapter/domain, router composition, issue #580 and direct PostgreSQL tests at base `34501cd64` | Existing hidden operation and absent route confirmed; the public surface extends that owner | No parallel registry or administrative bypass was introduced |
| Commitrail validity | `python3 scripts/check_commitrail_records.py --base-ref origin/main` | Pass with the record-only finding correction applied | Exact-head hosted checks remain with the lead |
| Public and PostgreSQL behavior | `backend/tests/checkers/external/test_public_api.py`, `test_postgresql.py`, and `test_migration.py` through the isolated PostgreSQL runner | Nine registration/readback/replay/revocation/migration cases passed at `802a22260`; the public commit-boundary database-failure rollback and same-key retry case passed at `f620eab2c` | Hosted full-suite evidence remains with the lead |
| AUTH catalogue parity | Focused authorization catalogue/setup-finalization tests and stale authorization-document check | 157 focused registry/catalogue/API/lane tests passed before the final rollback case; the changed route-rate inventory and rollback cases passed separately at `f620eab2c` | Hosted full-suite evidence remains with the lead |
| Documentation integrity | Markdown links, stale wording scan and affected roadmap reconciliation | Affected architecture/roadmap claims, bounded change links and stale wording passed with the record-only correction applied | Deployment and complete issue #580 remain outside this PR |

## Review findings

Security plan review at plan-only head `bca361570` found three blocking design
gaps. `SEC-580-PLAN-001` identified the speculative-loser UUID risk in a
single-phase AUTH-before-registry-lock flow; the design now uses AUTH's existing
opaque prepare/consume protocol and requires exact independent-session audit
assertions plus crossed revocation races. `SEC-580-PLAN-002` found the existing
guide-activation fixture caller outside scope; it is now allowed and must adopt
the replacement server-ID contract without compatibility behavior.
`SEC-580-PLAN-003` found denial custody underspecified; the transaction outcomes
now distinguish committed canonical denials, rolled-back conflicts, retryable
storage/audit failures and detached-response success commits. A bounded replay
of this corrected clean plan is required before implementation.

## Reconciliation

- Current-source reconciliation: implementation started from `34501cd64` and
  now follows merged main `d5bac1313`. Main's contributor reads own revision
  `0050_contributor_reads`; this change's exact operational-read audit pairs are
  the sole `0051_operational_read_audit` successor. The registry surface remains
  separate from contributor/result reads, CI and README ownership.
- Shared migration order: recovery and S3 consume this byte-identical `0051`
  prerequisite before adding their later revisions. Other open read work must
  rechain after the revisions that actually merge; this PR does not duplicate
  those migrations or depend on their unmerged product surfaces.
- Next usable boundary: issue #580's separate authenticated REV lifecycle
  state/readback and guarded `disabled -> shadow -> live` controls, followed by
  the parent #555 real-project drill combining actual checker images.
- Focused proof: signed public registration/readback and real PostgreSQL
  replay, revocation, concurrency, migration, commit-boundary database-failure
  rollback and same-key retry are covered by the external-checker tests named
  above. The shared read-pair migration must remain one linear prerequisite for
  recovery and S3, and no REV behavior is authorized.
