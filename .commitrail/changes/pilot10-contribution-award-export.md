# PILOT-10A — Read and export immutable contribution and award evidence

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: Current authorized humans read their own contribution evidence, and covered Project Managers or exact-project Finance Authorities export one project's complete contribution and award facts in one bounded repeatable-read JSON/CSV response without implying payment.

## Intent

Issue [497](https://github.com/Flow-Research/workstream/issues/497) lets people
inspect recognized work and use its exact awards for payment outside Workstream.
This backend boundary reads existing canonical facts; it does not create
acceptance, awards or fulfillment. CLI consumption is a later bounded change.

## Current behavior

`contributions/records/participant.py` and `compensation/awards/participant.py`
create or exactly replay one accepted-submission contribution and the complete
frozen award set inside the caller's fenced root transaction. The existing
authorized TASK outcome composes those owners with REV FinalAcceptance and
durable source authority. `tests/contributions/records/support.py` supplies
`authorized_submitter_source`, which invokes that actual hidden outcome rather
than inserting a standalone contribution. Zero, one and two awards already have
PostgreSQL participant proof. Public intake and production false-policy activation
remain unavailable; export proof must not claim they are live.

No public contribution/award read owner exists. The two exact identifiers
`contribution.read_self` and `contribution.read_project` exist as PermissionId
values and canonical planned surface mappings, but have no ActionId,
ActionDefinition or evaluator on the inspected main. PM and Finance permission
candidates already include project contribution and award reads; Operator and
Audit candidates do too. The new surface must enforce the explicitly agreed
PM/Finance role set, not treat every candidate permission as disclosure authority.

Existing task cursors are signed live timestamp/UUID keysets, not frozen
snapshots. A timestamp ceiling alone can admit a transaction that inserted
before the first page and committed afterward. PostgreSQL exported snapshots
require their exporter transaction to remain open; tuple xmin with snapshot
visibility is not a general solution for subtransactions or xid epochs.
See PostgreSQL 16's [snapshot visibility contract](https://www.postgresql.org/docs/16/functions-info.html)
and [exported snapshot lifetime](https://www.postgresql.org/docs/16/functions-admin.html).

## Bounded change

### Allowed

- New `backend/app/modules/contributions/api/{records,source_reads}.py` and
  `backend/app/modules/contributions/records/{read_facts,read_repository,read_service,csv}.py`
  for exact scoped contribution projections and one shared JSON/CSV projection.
- Existing CON `api/__init__.py` and `backend/app/adapters/contributions/__init__.py`
  for the actual read caller's typed owner composition.
- Narrow read-only public owner ports and implementations under
  `compensation/api/` and `compensation/awards/`, `reviews/api/` and the existing
  REV acceptance source owner, `tasks/api/` and TASK repository, and `actors/api/` and its
  existing repository, only for exact selected award, source-time, task-source
  and display-label facts that the projection actually requires. No private
  cross-owner imports or broad owner refactors.
- A new read-only owner factory in `backend/app/adapters/actors/__init__.py`
  and one appended read factory in each existing
  `backend/app/adapters/{compensation,reviews,tasks}/__init__.py`, used by the
  actual CON export-service factory on one caller-owned session. Existing
  sibling factory bodies remain untouched. Only those owner roots instantiate
  private owner repositories, preserving the canonical composition boundary.
  Isolated public-port translations live in
  `backend/app/adapters/{reviews,tasks}/contribution_reads.py`.
  TASK and REV already consume CON, so CON consumes its own minimal source-read
  facts; the isolated owner adapters translate readonly TASK/REV facts into that
  contract. Direct CON imports of TASK/REV API would create forbidden owner
  dependency cycles and are excluded.
- New `backend/app/api/{deps/contribution_exports,routes/contributions}.py` and
  one scoped include in `backend/app/api/router.py` for project and actor-self
  read/export routes following current namespaces.
- New exact contribution-read AUTH resource/evaluator/adapter files plus the
  coordinated sections of `authorization/catalogue.py`, `runtime.py`,
  `kernel.py`, `domain/audit.py`, `domain/audit_targets.py`, and the existing AUTH
  composition root. Register only the two approved identifier strings against
  their existing permissions; no duplicate actions or generic award endpoint.
- New `authorization/domain/read_dispatch.py` extracts only the existing
  queue/history/project-read selection and the two new contribution-read
  actions from `kernel.require`. It retains each existing evaluator and its
  exact revalidation callback; kernel retains decisions/audit. The kernel must
  shrink rather than add structural debt. No generic registry or prepared
  mutation change is allowed. `domain/action_groups.py` adds only these two
  explicit audit-digest memberships. The catalogue groups the same two exact
  actions in one closed frozenset, preserving the existing action-index function
  size. Runtime's resource union retains its existing file size. Refresh only
  kernel's reduced structural debt and unchanged-symbol line relocations in
  `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`; no debt or thresholds grow.
- Focused new contribution export and AUTH read tests, using real PostgreSQL
  for authority custody, canonical facts and concurrent-acceptance claims.
  Existing `tests/authorization/setup_finalization/test_catalogue.py` and
  `tests/test_api_controls.py` retain their closed inventories, adding only
  the two exact contribution actions/routes and excluding those routes from
  unchanged-route fingerprints. The audit allowed-action fixture remains part
  of the sole migration author's schema handoff. Export fixtures use distinct
  human readers; snapshot proof follows the actual separate actor/link locks.
- `docs/spec_contribution_compensation.md`, `docs/spec_authorization_service.md`,
  ADR 0016, and coordinated contribution-specific README/roadmap sections.
  The agreed PM/Finance read scope and v0.1 fulfillment deferral replace only
  affected obsolete D11/read-release clauses.
- Required additive test-lane/behavior ownership metadata and the selected MCP
  authorization-context enum snapshot only after shared-file coordination.
  Root authorizes the exact eight new test modules in existing
  `backend/scripts/test_lane_catalogue.py`'s `PROJECT_MODULES`; no lane, cap or
  workflow reduction. Update only the corresponding exact inventory set in
  `backend/tests/test_ci_lane_catalogue.py`; keep its equality assertions.
  `backend/scripts/behavior_ownership.py` admits only the
  21 new eligible source paths in a closed PILOT-10 frozenset. Regenerate
  `.ci/behavior-ownership/partition.v1.json` preserving its protected base and
  all existing target assignments. Capture only
  `mcp_server/contracts/authorization_context_get.json`, whose ActionId enum
  gains the two exact contribution reads; other selected contracts must stay
  byte-equivalent. P02 owns its separate source-module additions and later
  enum/metadata union after source migration merge.
- Any necessary audit-constraint or snapshot DDL only by the existing sole
  migration author, after an exact schema handoff and linear-head allocation.

### Not allowed

- Acceptance, Review, ContributionRecord, award, policy or economic mutations;
  fake acceptance evidence; new paid/payout/settlement status or payment adapter.
- Fulfillment, reconciliation, reputation, optional ART evidence, provider I/O,
  contributor intake or false-guide activation.
- Broad all-project administrative lists, cross-contributor disclosure,
  provider references/credentials, Finance binding internals or role expansion.
- CLI implementation in this backend PR; PILOT-02/PILOT-04 owner changes;
  paginated lists, business snapshot storage or transactions retained across
  requests;
  migration authorship; workflow/CI reductions, new private-import debt,
  skips or weakened assertions.
- Merge, deployment, whole-issue closure or starting the CLI follow-on.

## Design and decisions

The backend projection has one JSON item per actual ContributionRecord with
`awards: []` for unpaid work and every immutable award ID/instrument/unit/exact
decimal quantity for compensated work. It retains contribution, contributor,
project, task, external source/task, Submission, source and policy-version
identities. `recorded_at` is the immutable ContributionRecord creation time for
both types. Actual FinalAcceptance source references use separate
`acceptance_review_id` or `acceptance_routing_manifest_id` fields; they never
replace the ContributionRecord's own exclusive source fields.
Optional `recorded_from` is inclusive and `recorded_before` exclusive;
both require timezone-aware values, normalize to UTC and apply to recorded time.
An optional exact contribution-type filter applies before counting and loading.
`accepted_at` comes from FinalAcceptance for accepted-submission rows and is null
for completed-review rows. It is never inferred from contribution creation or
used as a fabricated reviewer acceptance time.

CSV flattens `(contribution_id, award_id)`, retaining one row with an empty award
identity for zero awards. CSV row count is not a contribution count. Decimal
quantities use exact strings with no binary float, rounding or conversion.
UTF-8 quoting and formula neutralization apply to untrusted task, contributor,
source and unit text before output. Every CSV cell is quoted and formula-like
text receives an apostrophe prefix, including full-width and whitespace-prefixed
triggers. Quoting preserves embedded delimiters as one cell. JSON preserves
canonical values. The mitigation applies to Workstream's generated CSV; external
spreadsheet save/re-export behavior does not preserve a universal sanitization
guarantee, as described by [OWASP's CSV injection guidance](https://community.owasp.org/attacks/CSV_Injection).

Every request freshly authorizes the exact self or project scope before loading.
Actor-self routes accept no other actor selector. Project reads always select
one explicit project. A system-scoped or exact-project Project Manager grant
covers that project under canonical PM coverage. Finance Authority must have an
active grant scoped to that exact project; a system-only Finance grant does not
qualify. Operator, Audit, Access Administrator and contributor project roles do
not qualify for project contribution disclosure. Denied/foreign projects are
concealed. CSV format changes cannot expand the authorized data set.
Audit commit follows complete response
validation; read failures cannot mutate canonical facts.

The new AUTH evaluator locks and refreshes the exact current human profile and
identity link before testing lifecycle. Self authority binds the resource to
that actor, with no grant prerequisite and no other actor selector. Project
authority first loads only a covering Project Manager grant, then only an
exact-project Finance Authority grant, through existing deterministic owner
lookups with `for_update=True`. It locks the selected Project only after a
grant match. These locks remain held through response serialization and audit
commit. Project status does not erase immutable historical contribution facts.
The request digest binds caller, audience, exact project/date/type filters and
format, with no raw exported facts or display labels in authority evidence.
Both actions use existing `actor_profile`/`project` resource and target tokens.
Audit digest admission must select these two actions explicitly; it must not
widen the digest classification of every existing actor or project read.
The evaluator and transaction composition require lead/peer scope review before
public route composition; pure projection proof is not live authority proof.

Fixed-membership pagination remains a later implementation boundary. A multi-request
list must fix the initially visible contribution set and bind action, caller,
project, filters, ordering and continuation without holding a transaction across
HTTP requests. That paginated surface is deferred to a separately scoped change.
This first PR uses one PostgreSQL REPEATABLE READ transaction per response and
returns at most 1,000 contributions ordered by `(recorded_at, contribution_id)`.
Request composition projects the resolved identity into detached authority facts
and releases its earlier read-only admission transaction before beginning the
export transaction. It selects REPEATABLE READ on that transaction's connection
before the first AUTH SQL statement; reusing an already-open admission snapshot
does not meet this contract. No provider call occurs while read-authority locks
are held. The complete JSON/CSV body must serialize before the ALLOW audit commit;
an evidenced denial may commit its canonical audit only, while selection,
projection, serialization and SQL failures roll back the response transaction.
It probes for the 1,001st row before owner projections; exceeding the fixed
maximum returns a documented 422 refusal with no partial body. Callers can narrow
the recorded-time/type filters. Each contribution retains zero, one or two awards;
CSV has at most 2,000 data rows. Empty exports are successful. Both formats use
the same transaction, selection and projection. No business snapshot table or
cursor approximation is introduced.

Even without new business tables, registering the two exact actions requires a
small migration extending AUTH's closed SQL action/permission evidence pairs.
Retained clauses and facts must remain unchanged. The migration is not authored
in this lane.

## Acceptance criteria

- [ ] Public export reads a real hidden authorized acceptance and preserves its
  exact source, artifact, policy and complete zero/multiple award set.
- [ ] Covered PM and exact-project Finance obtain the same project facts;
  system-only Finance, Operator and Audit do not qualify; revoked/inactive,
  ungranted, foreign-project and service callers cannot obtain them.
- [ ] Self-read returns only the current caller's contribution/award facts;
  actor/project/cursor substitution is concealed or rejected before disclosure.
- [ ] The response's repeatable-read view excludes concurrent later commits even
  between owner projections; exactly 1,000 selected contributions succeed and
  1,001 refuse without silent truncation or a partial export body.
- [ ] CSV preserves exact Decimal quantities, UTF-8, complete flattening identity,
  zero-award visibility and formula-safe untrusted text.
- [ ] Reads leave all source/economic identities unchanged and append only the
  canonical exact read authority evidence; serialization failures roll back it.
- [ ] The real kernel reaches both new evaluators, and existing queue/history/
  project-read authority paths retain their exact callbacks and decisions.
  Authorized Project audit selectors are exact; missing/ungranted selectors
  remain absent. Structural/private-edge debt cannot grow.
- [ ] Current docs distinguish public reads from hidden acceptance and deferred
  fulfillment; no exported field or sentence asserts payment occurred.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: architecture, security, QA/test delta, documentation and
  product/operations; shared checks and reviewer scheduling belong to the lead.
- Human review focus: PM/Finance disclosure, actor-self isolation, the 1,000-row
  single-response snapshot/refusal boundary, exact awards and fulfillment deferral.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Main and overlapping work | Fetch current main and inspect open PRs | New clean worktree on `a51cf06ccb5ab85f2c41528855f537d4362ec26b`; PRs 520/527/528/529/518/433 remain separate | Shared AUTH/router/docs/metadata hunks require coordination |
| Canonical facts and real outcome proof source | Owned isolated PostgreSQL runner; `tests/contributions/exports/test_source_reads.py` | Real authorized hidden outcomes with zero, one and two awards project exact CON/FA/COMP/TASK facts; source/economic rows unchanged; database/role cleanup complete | Public audit/snapshot proof awaits sole-author migration; no public acceptance claim |
| AUTH registration gap | Inspect permission/action catalogues, kernel and role candidates; controlled actual-kernel tests | Exact two actions, evaluator dispatch, request digests and authorized target binding implemented with existing permissions | SQL audit pairs still require sole-author migration; no live retained-audit claim |
| Snapshot boundary | Inspect existing signed cursor and PostgreSQL 16 snapshot contracts | First response uses repeatable-read and a fixed 1,000-contribution refusal ceiling; fixed-membership pagination remains separate | Real concurrent response proof not yet executed |
| Projection and CSV contracts | Focused pure and controlled owner-port tests | Exact decimals, complete awards, zero-award visibility, delimiter/formula neutralization and explicit bounds exercised | No HTTP, database snapshot or retained audit proof |
| Read evaluator scope | Controlled AUTH owner repository inputs and actual canonical kernel | PM system/project coverage and Finance exact-project-only selection are distinct; self uses refreshed human ownership; exact action/target/digest reachability exercised | Real grant locks, revocation, denial audit and transaction composition remain unproved |
| Owner boundaries | `PYTHONPATH=backend python -m scripts.module_boundaries validate --protected-base HEAD` | Current AUTH/public composition passes public API isolation, acyclic owner dependencies and unchanged private-edge ledgers against the main-derived HEAD | Rerun at final tested head after main reconciliation |

## Review findings

Discovery identified obsolete all-CON joint-read/fulfillment gates and unresolved
D11 wording despite issue 497's explicit covered PM/Finance read decision. The
implementation must reconcile those affected canonical clauses together with
the new surface; it must not infer delivery authority or activate other D11 work.

## Reconciliation

- Current-source reconciliation: Current main includes hidden complete authorized
  routing outcomes and completion delivery through PR 526. Public intake,
  production false-policy activation and reviewer participation remain distinct
  unavailable capabilities.
- Next usable boundary: CLI self-read/export consumes the merged backend surface
  under current namespaces in a later separately authorized bounded change.
- Remaining risks: fixed-membership pagination remains undelivered; migration
  allocation remains with the sole migration author. Full issue 497 remains open.

## Reproduced revocation-first serialization repair

At clean `487488ebf6493906ad88ca99af102f5e197f422c`, the real PostgreSQL
revocation-first regression returns 503 instead of concealed 404. The reader's
repeatable-read snapshot precedes the committed grant update; locking the changed
grant produces a serialization conflict. The failed root rolls back and exposes
no contribution facts, but it does not yet retain the required fresh DENY.

Bounded repair: move the existing response transaction into the existing
`contribution_export_response` owner, leaving its dependency single-yield and
responsible for identity capture, public error mapping and cleanup. Permit one
retry only for driver SQLSTATE 40001, after the whole failed root rolls back.
Reuse canonical AUTH and projection operations with the identical request;
re-evaluate current actor, link and grant in a new repeatable-read root. Serialize
and commit only that attempt's response, and commit a fresh denial before raising
concealed 404. Do not retry durable product mutations, denials, arbitrary storage
errors or serializer errors; a second serialization conflict remains 503.

Allowed repair files: existing contribution-export dependency and transaction
regressions, exact schema-lane expectation, this record and affected current
read-contract documentation. No new service/factory, alternate authorization,
isolation downgrade, global retry middleware or weakened revocation assertion.
Verify both real lock interleavings, first-snapshot visibility, serialization
rollback, exact DENY custody, retry exhaustion and non-serialization refusal.
