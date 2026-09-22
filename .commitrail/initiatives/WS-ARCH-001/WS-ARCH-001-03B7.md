# ARCH-03B7 — Explicit task submission requirements

- Initiative: `WS-ARCH-001`
- Durable disposition: Complete
- Intended merge outcome: distinct immutable contributor and management
  requirements projections reuse the task's historical policy resolver.

## Intent

After merged 03B6, TASK still translates the locked effective submission policy
into one mutable `SubmissionRequirementsResponse`. The retained public read
uses token-role/creator visibility, does not lock TASK before PROJECTS, and has
no separately callable management projection. Replace that response within the
existing owner. Do not create a policy compiler or another authorization path.
The parent 03B/03C manifest requires contributor and management requirements
reads; live exact AUTH and separate public activation remain 03C.

## Bounded change

### Allowed

- `backend/app/modules/tasks/schemas.py`, `service.py`, `router.py`: explicit
  requirements models and hidden reads; one shared policy-to-requirements
  translation; retained route replacement. Existing repository/detail facts may
  be consumed without changing their public contracts.
- `backend/tests/tasks/test_submission_requirements.py`, affected
  `tests/test_tasks.py`, `tests/tasks/test_project_display.py` and the archive-limit
  projection cases in `tests/test_project_guide_compilation_contracts.py`; new module
  registration in existing lane catalogue and its exact-set test.
- Current ARCH parent, overview, plan/chunk map, AUTH/CON/POL navigation, INDEX,
  README, roadmap, task specification, glossary/data model and operating manual.
  Update local roadmap exports only if present.

### Not allowed

No AUTH permission/action changes, new routes, policy writers/compilers,
PROJECTS/CHECKERS/ART changes, migrations, assignment invalidation or audit-event
reads. No TASK public API dependency changes or weakened boundary guard. No
compatibility alias, old response path, audience switch or data deletion.

## Design and decisions

Keep composites in existing TASK schemas. Replace `SubmissionRequirementsResponse`
with `ContributorTaskSubmissionRequirements` and
`ManagementTaskSubmissionRequirements`. Both have the same fixed safe fields;
the separate types identify future caller authority, not invented extra content.
Keep wire field names: task_id, project_id, guide_version, policy_schema_version,
merge_algorithm_version, required_packet_fields, required_artifacts,
required_evidence, forbidden_artifacts, attestation_terms, manifest_required,
artifact_hash_required, artifact_hash_algorithm, allowed_storage_schemes,
storage_reference_rules, maximum_file_size_bytes, maximum_package_size_bytes,
maximum_archive_entries, maximum_archive_size_bytes, packaging.

Models are frozen, strict and extra-forbidden. IDs are UUIDs, guide version is
nonblank, collections tuples, nested artifact/evidence/forbidden/storage rules
frozen. Packaging has only package_required and optional allowed_package_formats
(the latter can be absent under the canonical PROJECTS merge contract). It is
an immutable typed value, never arbitrary policy JSON. Preserve canonical
optional policy limits and JSON array serialization; do not change business
policy defaults or claim formats/checkers are live because they are described.
No source metadata, actor identity, payment, full policy body or storage object
reference is projected. Existing whitelist translation and validation helpers
remain when used; remove only superseded response/builders and unused helpers.

Extract one private `_lock_scoped_task` helper from 03B6 `_read_locked_context`: UUID project/task validation, exact `lock_project_task` lookup under no_autoflush, refreshed TASK lock and TaskNotFound. `_read_locked_context` calls this helper and then the unchanged historical PROJECTS resolver. Hidden management requirements reuse that operation. Hidden contributor requirements validate all three UUID selectors through the existing `ContributorTaskDetailRequest` before SQL and call the same TASK-only helper,
then reuses `read_contributor_task_detail(ContributorTaskDetailRequest(...))`
for current visibility before entering PROJECTS. Its extra bounded detail query
is intentional: it reuses the existing ready/unassigned-or-own-active-assignment
predicate and sees committed assignment state after any TASK-lock wait, instead
of duplicating SQL visibility rules. Foreign/missing/invisible tasks all raise
`TaskNotFound` before policy resolution. Malformed selectors reject before SQL.
Callers supply authority and own transactions; no flush, commit, rollback or
nested transaction. Surround the complete reads with `no_autoflush`.

The retained `/tasks/{task_id}/submission-requirements` route keeps its existing
role/creator visibility wrapper and safe contributor-shaped payload. Load and
lock TASK exactly once, then check existing visibility, resolve the historical
context and use the shared contributor constructor. Preserve manager access and
current denials; do not silently replace authority ahead of 03C. The hidden
manager type must not appear in OpenAPI. There is no token-role-driven projection
selector. Required-packet API fields and locked policy rules remain composed by
the same translator; no current guide/policy lookup.

## Acceptance criteria

1. Exact fields, UUIDs, strict/frozen nested contracts and no private/extra fields.
   Lists cannot mutate stored projections; JSON arrays and optional packaging
   format omission remain valid. Manager and contributor types are distinct.
2. Malformed project/task/contributor selectors fail before repository/resolver
   calls. Real ready task succeeds for both hidden reads; stored wrong-project,
   missing, draft/unassigned and another contributor's assigned task conceal
   appropriately before PROJECTS. Management of a locked non-ready task works.
   Assert the stored status/assignee and assignment contributor/status for each
   case before reading: wrong assignment contributor, wrong task assignee, active
   assignment alone on unassigned READY, assignee without assignment, claimed
   without assignment and released claimed assignment all conceal. Own active
   assignment succeeds; READY with released history remains visible. Reuse the
   proven fixture pattern in `test_task_detail_visibility`.
3. Every requirement equals the original effective policy projection. Reuse the
   existing successor integration test: original `answer.md`, activated successor
   `v2-answer.md`; prove the successor differs, then both hidden reads and public
   read keep all original fields. No historical CURRENT-policy substitution.
4. Valid control precedes permitted TASK post-policy-body mismatch. Both hidden
   reads reject through the existing coded custody error. Draft manager read
   rejects incomplete locks rather than fabricating requirements.
5. Both reads leave invalid pending sentinel unflushed and a flushed marker
   uncommitted; independent observer after caller rollback sees neither. Reuse
   03B6's exact-PID two-session TASK-lock pattern for contributor read: preload
   reader row and observe exact writer blocker. Wrap both real detail visibility
   and real PROJECTS reads; neither is entered before TASK release. After release,
   detail runs exactly once before PROJECTS, which rejects the refreshed changed
   body. No fake successful policy resolver.
6. Retained service test asserts exactly one TASK load with `for_update=True`
   before visibility/resolution; existing HTTP manager/worker/foreign/error tests
   remain. OpenAPI exposes only contributor-safe schema. Old response/builder
   symbols disappear; behavior tests protecting current requirements remain.

## Evidence

New named tests: `test_requirement_contracts`,
`test_requirement_selectors_reject_before_sql`,
`test_requirement_scope_and_assignment_visibility`,
`test_requirement_custody_and_caller_transaction`,
`test_requirement_waits_for_task_before_projects`,
`test_requirement_public_surface_and_removed_symbols`.
Extend `test_task_display_survives_guide_successor_for_contributor_and_manager`
in `tests/tasks/test_project_display.py` and
`test_task_service_read_contexts_preserve_visibility_and_operator_scope` in
`tests/test_tasks.py`; update its exact await list so both requirements and
locked-context reads request `for_update=True`, with one TASK load each. A focused pure
translation test `test_requirement_packaging_projection` independently proves
canonical package_required-only policy with absent formats, valid format-to-tuple
conversion and JSON arrays, unexpected keys, and malformed package_required or
formats rejected with sanitized `TaskLockedContextInvalid`. It uses otherwise
valid policy facts and does not claim to prove persisted custody.

Discriminating runtime probes: omit contributor visibility and require foreign
assignment rejection to fail; drop task-assignee equality from the existing
visibility predicate and require the wrong-assignee case to fail; move the real
detail read before TASK locking and require its non-entry assertion to fail;
substitute the genuinely different successor
requirements and require full historical equality to fail; remove retained-route
TASK lock and require the exact await assertion to fail. Contract tests reject
mutable nested collections and private packaging keys independently.

Use `backend/scripts/run_isolated_tests.py` for real PostgreSQL at migration
`0025_task_command_replay`, owned resources and cleanup. Run new nodes, affected
HTTP/retained-service/history nodes, original module boundary tests, Ruff,
lane parity, links, stale wording and Commitrail. Lead owns full hosted suite
and final exact-head artifacts: zero skips/deselections, unchanged gates and
TASK coverage above 90%. No duplicate full local backend run.

## Risk and review routing

Risk L1: policy projection, privacy, visibility and locking. Before code:
architecture/security/reuse and QA/product-operations plan review. After common
proof: those tracks, test delta, senior engineering for simplicity and lock
reuse, documentation, and CI integrity for test registration. Human focus:
complete historical requirements, exact contributor visibility, immutable safe
payload and explicit deferred authority boundary.

## Reconciliation

Plan review tightened the complete assignment matrix, required detail-before-
PROJECTS and TASK-before-detail concurrency proof, extracted the shared TASK-only
lock helper, and named packaging projection proofs. These are adopted before
implementation; no future runtime proof is claimed by plan review.

Base is merged #424, `b5e52529`. Only open #410 concerns CI impact reporting;
this change does not touch workflows or impact selection. No local spreadsheet
exports found during discovery. Remaining after this child: task audit-evidence
projections, dependency-gated invalidation and ARCH-03C authority/public cutover.
