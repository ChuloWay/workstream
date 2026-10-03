# ARCH-04E1B-A — Routing request and source identity reservation

- Initiative: WS-ARCH-001
- Durable disposition: Complete
- Risk: L1 (immutable coordination custody, owner boundaries).
- Intended merge outcome: caller-owned preparation reserves one distinct TASK routing operation and future source identity for an exact completed current evaluation. Routing remains unavailable.

## Intent

Main `2134c7be` delivers AUTH-19A's inert acceptance-source commitments. TASK has
an immutable source table but no routing request record. CHECKERS' evaluation
request cannot also identify the routing operation. Add the missing TASK request
custody, not a second source table or an early source publication.

Reserve identities first; later AUTH preparation can bind that exact request.
Full source projection, immutable AUTH-event/actor verification, receipt issuance
and publication with the governed consequence remain later composition work.
Receipt-shaped values alone grant no authority. Both human-review policy branches
remain supported by the existing source contract; this preparation does not
choose or activate either branch. Submitter lease/skip remains deferred.

## Bounded change

Add an immutable TASK routing request with generated operation and future manifest
UUIDv7 IDs, project/task/submission/version, checker run, evaluation request/digest/
generation, result ID/digest, completion event, route request digest and database
creation time. Logical uniqueness is submission/checker run/result digest. Hash
the action/domain and all source selectors, excluding generated IDs and timestamp,
so concurrent identical preparations recover the same stored identities. Use domain
`workstream.task_post_submit_route_request.v0.1` and action `task.post_submit.route`.
Operation, future manifest and completion event identities are individually unique. Reject
reuse of the checker request identity/digest. Exact replay returns stored IDs.

Extend the existing CHECKERS EvaluationCoordinationPort with verification of an
exact completion event and EvaluationCompletion. Qualify project/task/submission
before locking the current fence and run; verify stored current completed result,
recommendation, event, phase receipts and material. Return the verified stored submission version for comparison with TASK; return no private provider
coordinates or policy bodies. Reuse existing result parsing/classification.

TASK locks its exact project-qualified Task, then Submission before invoking that owner port,
then inserts or recovers the request in the caller transaction and flushes only.
Use strict frozen flattened `TaskRoutingSelection` and extending
`TaskRoutingRequestFacts` (route_operation_id, routing_manifest_id, created_at,
route_request_digest). One canonical hash accepts selection facts. TASK public
API imports no CHECKERS contract and adds no unused Protocol; the private stager
accepts CHECKERS public EvaluationCompletion. Later 04E2-B must bind manifest.id
exactly to request.routing_manifest_id. Request facts cannot construct an AUTH
source commitment or receipt.

The database guard uses the same Task -> Submission -> CHECKERS fence -> run lock order
and independently enforces exact ownership/current completion and the
canonical digest; UPDATE/DELETE/TRUNCATE are forbidden. Protected SQL names are
schema-qualified with safe function search_path. No early manifest row is inserted:
its database timestamp and eventual authorization receipt belong to publication.

## Allowed files

- This record; current ARCH/AUTH/POL initiative overviews, plans and chunk maps;
  the ARCH-04E coordination contract; `.commitrail/INDEX.md`.
- `README.md`, `docs/roadmap_status.md`, `docs/spec_chunk_4_task_queue_assignment.md`,
  `docs/architecture_data_model.md`, `docs/engineering/authorization_activation_custody.md`.
- `backend/app/modules/tasks/api/post_submit_routing.py` and `api/__init__.py`;
  `backend/app/modules/tasks/post_submit_routing/{models,requests}.py`.
- `backend/app/modules/checkers/api/execution.py`;
  `backend/app/modules/checkers/{execution_coordination,execution_repository}.py`.
- `backend/alembic/versions/0018_task_routing_request.py`;
  `backend/alembic/env.py`; `backend/app/db/models.py` if registration requires it.
- `backend/tests/tasks/post_submit_routing/{support,test_contracts,test_requests,test_request_storage,test_request_contracts,test_migration}.py`;
  `backend/tests/checkers/execution/test_coordination.py` if existing proof belongs there.
- `backend/tests/{conftest,test_alembic,test_coverage_contract,test_behavior_ownership,test_ci_lane_catalogue}.py`
  and existing migration tests only for exact current-head inventory.
- `backend/scripts/{behavior_ownership,test_lane_catalogue}.py`;
  `.ci/behavior-ownership/partition.v1.json`; test-structure canonical inventory and
  an exact assertion map only if an affected frozen test requires extraction.
- Existing ignored local roadmap XLSX/CSV exports only if present.

### Exact request inventory

Primary key `route_operation_id`; unique `routing_manifest_id` and
`completion_event_id`; unique replay tuple `(submission_id, checker_run_id,
result_digest)`. `result_id` means CheckerRun.result_id, not a CheckerResult row.
Digest input is `{domain, action, selection}` where selection contains exactly
project_id, task_id, submission_id, submission_version, checker_run_id,
evaluation_request_id, evaluation_request_digest, evaluation_generation,
result_id, result_digest, completion_event_id, routing_recommendation. The latter
is the stored literal `allow_review`; both application and SQL reject
`needs_revision` and `task_setup_blocked`. UUID values are canonical strings.
Generated route_operation_id/routing_manifest_id, created_at and the digest itself
are excluded. Future publication must enforce request-to-manifest identity equality.

Replay rechecks currentness before returning stored IDs; a changed selector under
the same logical key is rejected. All independent selector substitutions must be
covered without stale digest or unrelated invalid facts masking the boundary.
The direct-SQL insert guard must serialize against fence advancement: prove both
insert-first (advancement waits) and advance-first (old completion rejected).

CHECKERS compares the strict incoming completion in full against its locked
stored request/result/run, exact event ID, phase receipts and retained material.
It relies on existing immutable terminal-event custody, without importing OUTBOX
private models. The new SQL guard independently joins the event and verifies
type/version, project, aggregate run, exact payload, correlation and idempotency.
The latter are database event-custody checks, not TASK request authority. Test
valid foreign completion events and altered payload/aggregate independently.

The request guard stamps created_at unconditionally from clock_timestamp, including
past/future/NULL caller timestamps. Both generated IDs are distinct UUIDv7 values
and cannot reuse checker request/result/event identities. Replay requires the
same submitted latest Submission under the project-qualified Task lock; successor
creation already takes that Task lock before assignment/latest Submission. This
preparation does not replace later live lifecycle/AUTH validation. Prove retained
Task lock independently; do not fabricate a live revision workflow to test it.

## Prohibited changes

No public route, AUTH allow/action activation, service provisioning, receipt
consumer, source-manifest insert, routing current pointer, handler, automatic
dispatch, TASK lifecycle transition, Review/FinalAcceptance/ContributionRecord/
award, outbox publication, commit ownership, second source table, compatibility
path, retained-data deletion or unrelated cleanup. No CI gate weakening.

## Acceptance criteria

1. Real completed evaluation reserves stable distinct operation/manifest IDs and
   exact selectors; committed replay recovers them without extra rows/effects.
2. Caller rollback removes the request; independent concurrent identical callers
   converge on one request. No source, lifecycle, AUTH or outbox effects appear.
3. Noncurrent, noncompleted, wrong-event and mixed identifiers from a second valid
   project/submission deny. A stale completion cannot reserve a request.
4. Direct SQL rejects coherent foreign selectors, wrong digest, invalid identity
   reuse and mutation/deletion/truncation. Negatives retain all unrelated valid
   inputs and assert the intended guard, not any database error. At least one
   owner-predicate removal makes its named regression fail at the assertion.
5. Currentness locks remain held through preparation; an independent session
   cannot advance the same fence before caller completion. No claimed authority
   or transaction-fence guarantee beyond the actual tested preparation boundary.
6. Current navigation names AUTH-04E2-A preparation next, without describing
   source projection, actual receipt validation or live routing as delivered.

## Evidence

Use existing real PostgreSQL/MinIO completed-source fixtures and isolated runner;
new tests above are implementation targets, not existing proof. Run focused new
contracts/storage, retained source and CHECKERS coordination tests, migration and
identifier checks, module/authorization/test-structure/behavior ownership checks,
ruff, Commitrail records, markdown links and stale wording scans. Require hosted
full-suite completeness without skips/deselections; coverage remains diagnostic.

## Risk and review routing

Plan review: architecture/reuse and security before implementation. Frozen clean
candidate: architecture/reuse, security, QA/test-delta, documentation/product-ops
and CI-integrity, selected from the canonical reviewer matrix. Record actual
head-specific evidence in the PR. Human focus: request custody is not source
publication or authority; exact replay/ownership, caller rollback and lock order.

## Planned test nodes and commands

New tests: `test_reserve_replay_and_rollback`,
`test_concurrent_reservations_recover_winner`,
`test_stale_completion_cannot_reserve`, `test_mixed_valid_lineage_is_denied`,
`test_request_storage_rejects_substituted_owner`,
`test_request_storage_rejects_wrong_digest`,
`test_request_is_immutable`, `test_reservation_holds_currentness_lock`,
`test_non_allow_completion_cannot_reserve`,
`test_database_owns_request_timestamp`, `test_request_ids_are_distinct_uuid7`,
`test_sql_insert_blocks_fence_advancement`,
`test_sql_advance_first_rejects_old_completion`,
`test_sql_rejects_crossed_completion_event`,
`test_replay_requires_latest_submitted_submission`,
`test_reservation_blocks_successor_parent_lock`.
These are implementation targets, not claims of existing proof. From backend:

```sh
.venv/bin/python scripts/run_isolated_tests.py --metadata-json /tmp/arch04e1ba-tests.json --timeout-seconds 1200 -- .venv/bin/python -m pytest tests/tasks/post_submit_routing -q --tb=short
.venv/bin/ruff check app/modules/tasks/post_submit_routing app/modules/tasks/api/post_submit_routing.py app/modules/checkers/api/execution.py app/modules/checkers/execution_coordination.py app/modules/checkers/execution_repository.py alembic/versions/0018_task_routing_request.py tests/tasks/post_submit_routing
.venv/bin/python -m scripts.module_boundaries validate --protected-base 2134c7be
.venv/bin/python -m scripts.behavior_ownership validate
```

Use locally configured PostgreSQL/MinIO credentials without printing them.
From repository root:

```sh
.venv/bin/python scripts/check_commitrail_records.py --base-ref 2134c7be
.venv/bin/python scripts/check_markdown_links.py
.venv/bin/python scripts/check_stale_workstream_wording.py
git diff --check
```

## Verification scheduling

Keep the three new request-test modules on existing `task_lifecycle_c`, without
changing other node assignments, services, the nine-lane inventory, completeness
checks or 1,200-second limit. Merged-base hosted run 37083930861 completed TASK C
in approximately 12m27s including job setup, while TASK B took approximately
20m59s including setup. Randomly adding the new expensive owner-graph fixtures
to B has insufficient measured headroom. This is explicit scheduling of new
proof only; exact-head hosted completion must still establish the actual budget.
Ordinary transaction tests use canonical reset and schema verification; only
migration tests rebuild schema. No test or assertion is skipped to fit the lane.

## Implementation and proof boundaries

The request table, strict facts and caller-session stager implement the bounded
outcome. CHECKERS extends its existing coordination interface; TASK imports no
private CHECKERS implementation. The source manifest remains unchanged.

Focused proofs cover exact replay/rollback, concurrent winner recovery, every
committed selector, both fence race orders, phase/event custody, timestamp and
identity ownership, no lifecycle/economic/audit/outbox effects, and migration
preservation. A real successor Submission is created through the existing hidden
intake writer after explicitly seeding its future revision precondition; this
proves ordering rejection, not a live review/revision workflow. Existing source
proof remains retained. No obsolete product implementation is replaced here:
there was no prior TASK routing-request path to remove.

A local test-of-test probe removes only the completion-event aggregate predicate
from the request guard. The crossed-event regression then fails at its expected
rejection assertion, while the function is restored before teardown. This does
not rely on a digest error or fixture failure. Exact clean-head execution and
review freshness belong in the PR trust summary.

Current roadmap, TASK/data-model specs and AUTH/ARCH/POL navigation advance to
hidden AUTH preparation. No local spreadsheet exports are present. Public intake,
source publication, complete authority, routing, acceptance and remediation
remain separate prerequisites to the first complete contributor journey.
