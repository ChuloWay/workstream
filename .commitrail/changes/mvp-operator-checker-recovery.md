# Supported Operator terminal checker recovery

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: An authenticated system Operator can discover exact finalized post-submit infrastructure failures and invoke the existing reason-bound retry through the public API without repeating unresolved work.

## Intent

`CheckerRetryService` already creates one immutable, freshly authorized successor
for an exact finalized `infrastructure_failed` checker run, but deployments have
no supported way to find such sources or invoke that owner. This bounded part of
GitHub issue #581 exposes only the known-terminal recovery path needed by the
first automated backend MVP. Uncertain-delivery reconciliation remains separate
because its source-specific observations and safe closed outcomes are not yet
specified or implemented.

## Current behavior

`backend/app/modules/checkers/checker_retry.py` owns terminal-source validation,
TASK currentness locking, fresh Operator authority, stable actor/key replay,
successor reservation, immutable retry receipt, audit and outbox creation in one
transaction. Migration `0035_checker_retry` and the PostgreSQL tests under
`backend/tests/checkers/execution/` protect the exact source/successor closure,
concurrency, rollback and response-loss replay. `backend/app/adapters/checkers`
composes that service, but `backend/app/modules/checkers/router.py` exposes only
contributor and Project Manager history. Operators cannot discover the exact
eligible source or call the retry through a bearer-authenticated public route.

## Bounded change

### Allowed

- `.commitrail/changes/mvp-operator-checker-recovery.md`: this bounded contract
  and durable evidence.
- `backend/app/modules/checkers/api/execution.py`: privacy-bounded Operator
  discovery/request/response values, a typed discovery authority port, and a
  required project selector on the existing retry command.
- `backend/app/modules/checkers/checker_retry.py`: extend the existing owner
  with a bounded project page of retained finalized infrastructure failures and
  their exact current/retried state; leave retry mutation semantics intact.
- `backend/app/adapters/checkers/__init__.py`: compose the existing retry owner
  and its discovery authority through canonical adapters.
- `backend/app/modules/checkers/router.py` and a narrowly scoped dependency under
  `backend/app/api/deps/`: authenticated project-scoped discovery and exact-run
  retry routes, caller-root transaction handling, stable concealment/error
  mapping and UUID `Idempotency-Key` parsing.
- `backend/app/modules/authorization/catalogue.py`, the existing checker-retry
  authorization adapter, a focused CHECKERS recovery read domain/adapter,
  the prepared-denial action registry and prepared-scope owner,
  `backend/app/modules/authorization/kernel.py`,
  its closed audit-target mapper, `backend/app/modules/audit/schemas.py`, and only the minimum AUTH
  composition exports: activate an exact recovery-source read action backed by
  the existing system Operator `operations.status.read` permission and retain
  read/mutation denials through canonical restage/commit. The public read uses
  the existing authorization-read rate gate before AUTH or CHECKERS lookup.
  Mutation continues to use `operations.checker.retry` unchanged.
- `backend/scripts/behavior_ownership.py`,
  `backend/tests/test_behavior_ownership.py` and
  `.ci/behavior-ownership/partition.v1.json`: register only the three new
  public recovery modules with the existing ARCH-04F4 ownership group, retain
  its closed no-parallel-runner inventory and regenerate the additive
  partition snapshot.
- `backend/alembic/versions/0051_operational_read_audit.py`, the canonical
  head in `backend/alembic/env.py`, the existing external-checker migration
  proof, the real PostgreSQL schema fingerprint in `backend/tests/conftest.py`,
  and issue #580's bounded record: consume the byte-identical shared
  prerequisite commits from #589 that admit exactly its registry-read pair and
  this change's recovery-read pair. These files remain owned and merged by
  #589 before this PR; this branch adds no second migration variant. The
  revision identifier remains within Alembic's persisted 32-character bound.
- `mcp_server/contracts/authorization_context_get.json`: regenerate only the
  selected authorization-context fragment and digest changed by the additive
  recovery-source action.
- `backend/tests/test_api_controls.py` and
  `backend/tests/test_api_rate_controls.py`: preserve the closed public
  route/action inventory and bind only the existing read and mutation rate
  controls to their exact recovery routes.
- `backend/tests/checkers/execution/test_checker_retry*.py` and only directly
  affected AUTH catalogue fixtures/tests: update existing callers for the
  required project selector and add signed bearer-token, real AUTH and
  PostgreSQL proof for discovery, retry, denial, revocation, replay,
  currentness, rollback, cross-project locking and nonterminal refusal.
- `backend/scripts/test_lane_catalogue.py` and
  `backend/tests/test_ci_lane_catalogue.py`: keep the focused recovery HTTP
  proof in exactly one canonical project lane after splitting it from the
  oversized integration module; refresh only the affected family fingerprints.
- `docs/operations_roles_permissions.md`, `docs/operations_operator_workflow.md`
  and `docs/roadmap_status.md`: describe the newly supported terminal-failure
  path and retain uncertain delivery as a visible remaining boundary.

### Not allowed

- Request/completion/acceptance `UNKNOWN` replay, generic redrive, broker
  invocation, dead-letter mutation, acceptance/contribution/award recovery or
  any claim that issue #581 is complete.
- Retry of queued, running, completed business outcomes, unresolved invocation
  effects, stale/non-current runs, PRE checks or contributor resubmission.
- New retry tables, alternate retry services, compatibility paths,
  direct product-row repair, mutable source evidence or changes to locked policy
  lineage.
- Checker registration or REV lifecycle work owned by issue #580; CLI/CI,
  credentials, cloud/deployment changes, frontend behavior, merge or
  unrelated cleanup.

## Design and decisions

The discovery route is a project-scoped, cursor-bounded projection owned by
CHECKERS. It includes only identifiers, generation, terminal failure code and
timestamps needed to select the exact source, plus whether its immutable retry
receipt already exists and the exact successor identities when present. It does
not return request/result payloads, artifact data, credentials or provider
coordinates. AUTH revalidates an active human identity and system Operator grant
for each page before disclosure, binds the project and query digest in audit,
and conceals missing or unauthorized projects. Pagination reuses the canonical
signed authorization-read cursor codec, binds the exact project/query, and uses
stable `(created_at, run_id)` keyset ordering.

The retry route accepts a required project and source run in the path, a bounded
reason in the body, and one UUID `Idempotency-Key`. The command requires that
project selector for every caller. The existing owner first resolves the source
by the exact `(project_id, run_id, post_submission)` tuple, before loading its
request or taking any TASK lock, so a wrong-project request cannot lock a foreign
task. The dependency builds the existing retry context with the key as its
request/correlation identity, then calls `CheckerRetryService.retry` inside the
request transaction. The service remains the only writer and still locks TASK
currentness before AUTH, revalidates fresh authority before any successor
commits, and returns the retained receipt on an exact lost-response replay. The
route maps absent, foreign, stale, nonterminal and unauthorized sources to one
concealed response; key/payload reuse maps to a stable conflict. AUTH denials
roll back product effects, then restage and commit their exact canonical denial
evidence. Conflict, storage, audit and outbox errors roll back any staged allow
decision and the whole successor. Required-authority evidence failure returns
retryable unavailability.

Discovery explicitly reports only known finalized infrastructure failures. A
queued/running run, a dead-letter `UNKNOWN`, or any unresolved invocation effect
is never converted into retry eligibility. Source-specific UNKNOWN observation
and reconciliation will require a separate bounded contract before code.

The new read action and the parallel issue #580 registry-read action both touch
the closed AUTH catalogue/kernel. Their branches must be reconciled once in a
known order before final proof; neither change may overwrite the other's active
action or tests.

## Acceptance criteria

- [ ] A bearer-authenticated human with a live system Operator grant can list a
  project's retained finalized post-submit infrastructure failures and receives
  exact source run/request/result/finalization identity, generation, failure
  code, timestamps and eligible/retried current state without private payloads.
- [ ] Missing project, wrong role, project-scoped grant, service identity,
  revoked identity link or revoked Operator grant returns the same concealed
  discovery response and discloses no failed-work facts; service identity also
  reaches no CHECKERS or TASK lookup through the mutation route. Read AUTH
  evidence is exact and denial evidence follows the canonical read path.
- [ ] POST of an eligible source, reason and UUID key calls the existing owner
  and returns its immutable source, successor, receipt and authorization IDs;
  the original Submission/run/result/finalization remain unchanged and no
  contributor revision, Review, acceptance, contribution or award is created.
- [ ] Exact committed replay, including simulated response loss, performs fresh
  authority and returns the same receipt/successor without another run, event or
  retry-initiation audit effect; it validates the retained original allow and
  may retain only canonical fresh-request AUTH evidence if AUTH requires it.
  Changed reason or source under the key in the same URL project conflicts;
  reuse under another URL project stays concealed with `404` before any foreign
  TASK lock.
- [ ] Wrong/foreign/stale sources and queued, running or completed outcomes
  refuse before a successor effect. Revocation, concurrent retry, forced audit
  or typed outbox failure and caller rollback retain the service's existing
  atomic guarantees through the public request path; internal outbox conflicts,
  invalid input and persistence failures return bounded retryable unavailability.
- [ ] The existing authorization-read and mutation rate controls refuse their
  exact recovery routes before AUTH or CHECKERS access. Absent, foreign, stale
  and ineligible sources stay concealed, while retained authority, reservation,
  replay or delivery inconsistency returns retryable unavailability and rolls
  back every staged effect.
- [ ] A request whose URL project differs from the source project is rejected
  before loading source payloads or taking the foreign TASK row lock; a real
  PostgreSQL held-lock probe distinguishes that ordering from a coincidental
  denial.
- [ ] Discovery never treats dead-letter or `UNKNOWN` delivery as eligible and
  the supported operations documentation names that remaining hold explicitly.
- [ ] Focused signed public-API tests use real PostgreSQL and canonical AUTH;
  existing checker retry, history, delivery and AUTH catalogue proof remains
  green.

## Risk and review routing

- Risk class: L1
- Required reviewers: `architecture`, `security`, `qa`, `test_delta`,
  `product_ops`, `reuse_dedup`, and `documentation`; the lead owns shared checks
  and reviewer scheduling.
- Human review focus: exact read scope/concealment, source/currentness proof,
  request-key-to-AUTH binding, denial evidence, lock order, response-loss replay,
  rollback and the hard exclusion of unresolved-effect retry.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing owner and public gap | Inspect `CheckerRetryService`, adapter composition, routes, issue #581 and ARCH-04F4 tests at base `a201d7432` | Hidden exact terminal retry and absent Operator read/command confirmed; implementation extends that owner | Public PostgreSQL proof remains pending |
| UNKNOWN separation | Inspect OUTBOX dead-letter contracts and issue #581 | Unresolved invocation effects have no safe generic replay owner; excluded from this PR | Source-specific reconciliation remains a later bounded change |
| Public PostgreSQL behavior | Focused signed `/api/v1` recovery tests plus existing checker retry suites | Exact clean head `667e5a053` passed 4/4 in 143.68 seconds: real prepared-denial binding, complete public discovery/retry/replay/revocation, real OUTBOX-conflict rollback, and stale-source refusal after auto-acceptance; isolated database, role and MinIO cleanup all completed | Exact-head hosted full-suite evidence remains pending |
| Closed AUTH and lane ownership | Exact catalogue, OpenAPI route/action, recovery HTTP transaction, ownership validation and running OpenAPI snapshot checks | `3 passed` in 162.42 seconds; ownership validation and exact snapshot comparison exited `0`; recovery HTTP proof remains in exactly one canonical project lane | Exact-head hosted boundary and lane execution remain pending |
| Static implementation checks | Changed-file Ruff; conflict/stale-wording/Markdown-link/authorization-doc scans; `git diff --check` | Passed on clean stacked head `020d3d55d` | Affected review must replay after any source change |
| Commitrail validity | `python3 scripts/check_commitrail_records.py --base-ref 2aa661bb9bb19e0970b12f05527454de77d30163` | Passed | None for the current stacked diff |

## Review findings

Pre-implementation plan review required the URL project selector to constrain
the canonical CHECKERS source lookup before any TASK or foreign product-row
lock; a real held-lock wrong-project probe; a project/query-bound stable signed
cursor; explicit caller-root rollback and canonical denial restaging; and clear
separation between fresh AUTH evidence on replay and duplicate retry business
effects. The implementation and focused tests incorporate those corrections.
Security, architecture, QA, test-delta, product-operations, reuse and
documentation source review passed through the repaired public projection at
clean head `1be238145`. QA/test-delta replay then passed on clean head
`667e5a053`, confirming that replay retains the exact original allow decision
while freshly revalidating current Operator authority without adding a second
allow event. The focused PostgreSQL proof passed at that exact head; hosted
full-suite evidence remains pending.

## Reconciliation

- Current-source reconciliation: main `d5bac1313` is an ancestor through the
  published PR #589 head `2aa661bb9`; issue #580 owns supported checker
  registration and a separate registry read action. This change owns only
  terminal checker recovery and preserves both catalogue additions. PR #589
  owns the canonical `0051_operational_read_audit` migration before #588 and
  #592; this branch consumes its proved migration and schema fingerprint
  byte-for-byte and introduces no sibling revision.
- Next usable boundary: source-specific observation and reconciliation for
  request execution, checker completion and acceptance commit/acknowledgement
  loss, followed by parent issue #555's real-project worker drill.
- Remaining risks: exact-head PostgreSQL/public API evidence and routed internal
  review remain pending. UNKNOWN effects stay held.
