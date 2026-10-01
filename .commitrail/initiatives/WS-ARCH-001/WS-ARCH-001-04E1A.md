# ARCH-04E1A — Immutable post-submit routing source foundation

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Risk: L1 (cross-owner retained lineage and schema).
- Intended merge outcome: TASK owns one immutable routing-source schema and detached internal facts for the later shared acceptance source FK; routing, acceptance and public intake remain unavailable.

## Intent and current behavior

Continue claim -> ZIP intake -> immutable Submission -> automatic checking ->
policy-governed outcome. Main `d5bf3460` includes ARCH-04D2's exact CHECKERS
execute/finalize receipts and ART materialization authority. CHECKERS already
owns immutable completed results, their material custody, completion events and
currentness fences. TASK owns Submission/assignment/policy lineage and its
`SubmittedBundleFacts` projection. There is no TASK routing manifest, routing
service identity/action, or shared acceptance operation.

The adopted 04E coordination contract predates these concrete interfaces. It
must not imply that a routing allow can already be minted, that an execution
receipt substitutes for one, or that the zero-output catalogue needs output
write/bind authority. Original Submission/binding and materialization AUTH
receipt identities are also not retained by the existing public facts. Those
receipt-retention requirements must be reconciled in the later publication
contract before routing can become live; this foundation does not invent them.

## Bounded change

### Allowed files and behavior

- `backend/app/modules/tasks/routing_models.py`: one immutable
  `task_post_submit_routing_manifests` source table, registered in `backend/app/db/models.py`.
- `backend/app/modules/tasks/api/post_submit_routing.py`: detached TASK-owned
  scalar source facts and a narrow accepted-effects protocol.
  Reuse `SubmittedBundleFacts`/`SubmittedPolicyContext`; no CHECKERS, REV, CON or
  PROJECTS imports in TASK's public API.
- `backend/alembic/versions/0011_task_routing_source.py`: additive schema,
  immutable custody and exact canonical source validation; safe schema-qualified
  references and function search paths. Preserve all existing rows.
- Focused `backend/tests/tasks/post_submit_routing/` contracts/storage/migration tests;
  existing real `material_fixture` and live CHECKERS executor; only necessary
  fixture extension for a reachable locked-policy branch.
- Schema/head fixtures, model registration, exact lane/ownership inventories
  and their parity tests as required; no relaxed checks or percentage gates.
- This record, the 04E coordination contract, affected current ARCH/AUTH/ART/POL/
  CON navigation and index, README, roadmap, TASK/data-model/review/checker
  specifications where they describe this source/authority boundary. Local
  roadmap exports only if present.

### Prohibited

No new AUTH actions/identities or permissive authority participants, public
routes, production writer/reader/composition, dispatch/request handlers, current routing pointer, `review_pending`,
accepted/completed transitions, REV/CON records, output-file authority, recovery
controller, data deletion, compatibility code or second manifest table. The
accepted-effects protocol has no implementation or default/no-op adapter.

## Design

Use one `task_post_submit_routing_manifests` identity throughout the planned sequence.
This step stores source facts, not an authorization decision, current routing
claim, human admission or acceptance. It has no runtime publisher. The later
routing-authority step must extend the same schema with non-null exact routing
receipt custody before any publication; it must refuse pre-authority retained
rows that cannot be proven rather than rewrite or delete them. No nullable
receipt later filled in, second source/manifest table or artificial pending state.

Store the exact project/task/Submission version, assignment/contributor and
ContributionPolicyVersion, CHECKERS run/request/generation/result identities and
digests, completion event, distinct execute/finalize receipt IDs, server-derived
content SHA-256, locked `human_review_required` and creation time. Preserve
immutable Submission policy context through the existing TASK projection; do
not duplicate policy bodies, member results, private packets or storage locators.

Database checks join the exact existing Submission/Task/Assignment/ReviewPolicy
and CHECKERS source chain. Require completed `allow_review`, matching request,
result, material hash, completion event and phase receipts; exact locked review
policy determines the boolean. Match the three locked contribution-policy
identities at source creation. FKs and semantic guards reject coherent foreign
or crossed same-project sources, not merely missing UUIDs. Uniqueness is the
existing planned `(submission_id, checker_run_id, result_digest)` identity.
Updates, deletes and truncation deny; no mutable current pointer is introduced.
Source validity is historical, not proof that its CHECKERS generation remains
current. Routing's caller-transaction TASK -> CHECKERS currentness check remains
in 04E1B; historical source reads do not acquire that authority.

No read port, application composition or consumer is introduced before route
receipt custody is implemented. The detached facts are an owner contract for
source evidence only. The accepted-effects protocol describes the future exact task/assignment/
Submission/policy input and accepted/completed result under the initiating
transaction. It performs no effects in this step and imports no REV owner.

## Acceptance criteria and proof feasibility

1. A real admitted Submission and real successful CHECKERS execution can support
   a valid source row. Direct SQL proves exact retained fields and immutable
   custody, duplicate rejection and caller rollback. No fabricated routing
   receipt is used or claimed.
2. Source storage rejects mismatched project/task/Submission, same-project sibling
   run, request/result/generation/digest, phase receipt, content hash,
   assignment/contributor/contribution-policy identity and locked policy boolean.
   Negative cases supply all unrelated valid fields and target their named guard.
3. Non-completed/non-successful checker evidence cannot be a success source.
   Retained valid sources remain readable after a later checker generation;
   they never claim currentness or cause effects.
4. Public scalar contracts support both policy branches. Current PROJECTS service
   and database activation guards reject false, so a real false Submission is
   unreachable. Prove strict false DTO shape only; do not bypass guide activation
   or fabricate a live false-policy graph. Retain existing false-activation denial.
5. Contracts contain no private policy bodies, packets or storage coordinates.
   No HTTP/OpenAPI surface, production writer/reader/composition, AUTH registration
   or accepted-effects implementation appears. REV runtime cannot consume this
   source until exact routing authority is implemented and independently proven.
6. Controlled removal/substitution of each material guard must make its targeted
   test fail at the intended assertion. Mutation setup failures do not count.
7. Upgrade preserves the prior schema's retained Submission/checker facts and
   creates no routing/admission/acceptance rows. Schema inventory stays exact.

## Risk and review routing

Focused plan and candidate reviewers: architecture/reuse (one schema, dependency
order and no premature effects), security (crossed source and immutable custody),
QA/test delta (reachable real controls and discriminating negatives), docs/product
operations (source versus authority, both branches and next dependency), CI
integrity (migration, exact inventory and complete execution). Lead runs shared
checks once. Human focus: whether the retained source is sufficient for the
REV source FK without being misrepresented as permission to accept.

## Evidence strategy

Run the focused contracts and real PostgreSQL storage/migration tests through
`backend/scripts/run_isolated_tests.py`, reusing the Local/MinIO-backed source
fixture rather than another fake checker runtime. Run Ruff, module boundaries,
behavior ownership, structure, schema/head parity, Commitrail and markdown-link
checks. Full hosted lanes and aggregate must reconcile every collected test with
zero skips/deselections. Coverage is diagnostic. Proof names/commands become
exact when the plan's fixture feasibility is reviewed.

## Plan-review reconciliation

The earlier coordination skeleton cannot provide a genuine routing allow in
04E1A: AUTH registration is later. Keep this same-table source foundation
explicitly unexposed and add no reader/writer that could make it an admission
token. A complete authorized row is a later publication obligation, not a
fictional positive fixture now. The current false-policy activation guard is a
real prerequisite, so false is contract-only proof in this step.

## Reconciliation

The next dependency is the existing shared REV/CON source/acceptance foundation
before false-branch handler composition, followed by 04E1B/04E2/04E3 and 04F.
This record does not make live human queues or review leases a dependency of
automated acceptance. Public intake remains behind the complete outcome and
remediation path. Current navigation must distinguish delivered source schema
from later authoritative publication.
