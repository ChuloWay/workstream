# ARCH-04E1A — Immutable post-submit routing source foundation

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Risk: L1 (retained lineage and schema).
- Intended merge outcome: one TASK source schema and detached internal contracts support the later shared acceptance source FK; routing, acceptance and public intake remain unavailable.

## Intent

Continue claim -> ZIP intake -> immutable Submission -> automatic checking ->
policy-governed outcome. Establish the source identity needed by REV without
making that identity an authorization token or adding a second acceptance path.

## Current behavior

Main `d5bf3460` includes ARCH-04D2. CHECKERS owns immutable completed results,
material custody, completion events, execute/finalize receipts and currentness.
TASK owns Submission/assignment/policy lineage and `SubmittedBundleFacts`.
There is no routing manifest or routing service/action. The zero-output
catalogue has no output-file authority requirement.

The old 04E skeleton promises complete routing authority before AUTH registration.
It also promises original Submission/binding/materialization decision IDs which
current owner contracts discard. Do not fabricate them or find substitute allows
by reverse audit-log search. The later 04E1B/04E2 publication work must propagate
those exact receipt IDs from their owning operations and retain them before
claiming a complete authorized manifest. CHECKERS execute/finalize receipts
remain distinct and cannot authorize routing.

## Bounded change

### Allowed implementation and proof files

- `backend/app/modules/tasks/routing_models.py`
- `backend/app/modules/tasks/api/post_submit_routing.py`
- `backend/app/modules/tasks/api/accepted_effects.py`
- `backend/app/modules/tasks/api/__init__.py`
- `backend/app/db/models.py`
- `backend/alembic/versions/0011_task_routing_source.py`
- `backend/tests/tasks/post_submit_routing/__init__.py`
- `backend/tests/tasks/post_submit_routing/support.py`
- `backend/tests/tasks/post_submit_routing/test_contracts.py`
- `backend/tests/tasks/post_submit_routing/test_storage.py`
- `backend/tests/tasks/post_submit_routing/test_migration.py`
- `backend/tests/conftest.py` (exact table/trigger inventory and generated schema fingerprint)
- `backend/tests/test_alembic.py` (exact revision graph)
- `backend/tests/test_coverage_contract.py` (current-head fixture only)
- `backend/tests/checkers/execution/test_migration.py` (current-head assertion)
- `backend/tests/authorization/post_submit/test_migration.py` (pin 0009 -> 0010 proof to its actual target)
- `backend/scripts/test_lane_catalogue.py`
- `backend/tests/test_ci_lane_catalogue.py` (exact inventory only if required)
- `.ci/behavior-ownership/partition.v1.json` (three additive TASK module registrations and digest)

Reuse `tests/post_submit_materialization_helpers.py`, the real live executor and
existing guide/policy fixtures without changing their behavior. No false-policy
fixture extension is allowed; current activation forbids that graph.

### Allowed documentation and navigation files

- This record; `.commitrail/INDEX.md`.
- `.commitrail/initiatives/WS-ARCH-001/OVERVIEW.md`, `planning/PLAN.md`,
  `planning/CHUNK_MAP.md`, `planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md`.
- `.commitrail/initiatives/WS-AUTH-001/OVERVIEW.md`, `planning/PLAN.md`, `planning/CHUNK_MAP.md`.
- `.commitrail/initiatives/WS-POL-003/OVERVIEW.md`, `planning/PLAN.md`, `planning/CHUNK_MAP.md`.
- `.commitrail/initiatives/WS-ART-001/OVERVIEW.md`.
- `.commitrail/initiatives/WS-CON-001/OVERVIEW.md`.
- `.commitrail/initiatives/WS-AUTH-003/OVERVIEW.md`.
- `.commitrail/initiatives/WS-REV-001/OVERVIEW.md`.
- `README.md`, `docs/roadmap_status.md`, `docs/architecture_data_model.md`,
  `docs/spec_chunk_4_task_queue_assignment.md`, `docs/spec_review_lifecycle.md`,
  `docs/spec_contribution_compensation.md`, `docs/spec_authorization_service.md`,
  `docs/engineering/authorization_activation_custody.md`.
- Ignored local `sheets/workstream_roadmap.xlsx` and `sheets/workstream_roadmap.csv`
  only if already present; preserve one `WorkStream RoadMap` sheet.

### Prohibited

No AUTH registration, public route, writer, reader, application composition,
handler, current pointer, TASK transition, REV/CON record, output-file authority,
controller, data deletion, compatibility code or second manifest table. The
accepted-effects port is type-only, without an adapter/default/no-op implementation.

## Design and decisions

### One route-neutral source

Create one `task_post_submit_routing_manifests` table. It is source evidence,
not current routing, human admission or acceptance. No deployable product path
can populate or consume it in this step. Tests insert real source facts directly
only to prove storage. Later publication must harden this SAME table with
mandatory exact routing/other required receipt custody before installing a writer
or reader. That migration must refuse any retained pre-authority rows rather
than backfill, mutate or delete them. No pending state or nullable future receipt.

### Exact field ownership

Every persisted column below is non-null. `id` uses UUIDv7; creation time is
PostgreSQL time. All record keys/references are native UUID.

| Persisted fields | Canonical equality |
|---|---|
| `id`, `created_at` | TASK source identity and database timestamp |
| `project_id`, `task_id`, `submission_id`, `submission_version` | Exact Submission joined to its TASK project |
| `assignment_id`, `contributor_id`, `contribution_policy_version_id` | Submission's exact assignment/submitter; Task, Assignment and Submission frozen policy IDs agree at insertion |
| `checker_run_id`, `evaluation_request_id`, `request_digest`, `evaluation_generation`, `result_id`, `result_digest` | Same-Submission immutable completed CheckerRun; run ID is the attempt ID, not a second identity |
| `completion_event_id`, `execute_evidence_id`, `finalize_evidence_id` | Exact distinct receipt IDs and completion event retained on that run; no audit search |
| `human_review_required` | Exact Submission-locked ReviewPolicy ID/generation/hash and its persisted boolean; no default |
| `replica_id`, `content_sha256`, `byte_count`, `semantic_manifest_sha256` | Run's validated `material_custody`, backed by existing `public.art_submission_material_matches`; never caller `Submission.package_hash` |

Public `TaskPostSubmitManifestFacts` contains these same scalar fields plus the
following immutable join-only facts (not extra stored copies):

- `predecessor_submission_id`, `predecessor_submission_version`: Submission's
  exact same-task predecessor; both null for the initial Submission.
- `admission_id`, `binding_id`, `content_id`: immutable Submission ART anchors,
  equal to validated run material. No private provider coordinates.
- `locked_policy: TaskPolicyLineage`: reuse TASK's existing strict frozen public
  value in `api/transition_audit.py`, populated from Submission's locked guide,
  source snapshot, effective/pre/post/review/revision identities and hashes;
  its contribution-policy field equals the stored source policy ID. The existing
  locked post-policy hash is the compiled policy's sole `policy_hash`, not another
  computed plan hash. Review/revision generations and guide version remain exact.
- `routing_recommendation`: closed literal `allow_review`; this is CHECKERS'
  success evidence, not permission to admit a human or accept the work.

No packet, policy body, member results or arbitrary metadata is copied. There
is no runtime projection builder in this step. Future composition supplies these
same detached fields only after owner-qualified reads and live currentness checks.

### Database custody

Composite FKs anchor source project/task/Submission/version, exact assignment/
contributor, CHECKERS ownership and frozen contribution-policy project. Other
retained record refs use restrictive FKs. A schema-qualified insert guard validates
all equality above using `IS DISTINCT FROM` or explicitly coalesced predicates;
NULL must deny, never bypass a three-valued condition. Require completed
`allow_review`, non-null material, exact phase receipts and completion event.
Reuse the canonical ART material predicate rather than another material parser.

The locked guide must carry its retained activation operation/receipt and may
be active or superseded. Never consult the project's latest guide/policy. Existing
PROJECTS custody guards protect that immutable activation; draft/unactivated
sources deny. Match the exact locked ReviewPolicy tuple, not an arbitrary sibling
policy with the same boolean. Do not lock foreign TASK/ART/PROJECTS rows or query
private runtime owners; this is a database constraint over immutable source refs.

Uniqueness: `(submission_id, checker_run_id, result_digest)`. Updates, deletes
and truncation deny. Retained source validity does not claim currentness; a later
checker generation does not rewrite or invalidate this historical row. The later
routing transaction must acquire TASK Submission/current pointer then CHECKERS
currentness through the owner port. No currentness pointer or new lock protocol
is implemented here. All SQL protected refs are schema-qualified, with safe
function search paths and `pg_temp` last.

### Shared accepted-effects contract

Put the source-neutral contract in `tasks/api/accepted_effects.py`, so neither
human acceptance nor routing owns the shared TASK participant.
`TaskAcceptedEffectsRequest` is strict/frozen and contains `project_id`, `task_id`,
`assignment_id`, `submission_id`, positive `submission_version`, `contributor_id`,
`contribution_policy_version_id`, `content_id`, `content_sha256`,
`final_acceptance_id`, and `expected_task_status` limited to `evaluation_pending`
or `review_pending`. IDs are UUIDs and hashes use the existing SHA-256 syntax.
`TaskAcceptedEffectsResult` retains that request identity, reports only task
`accepted` and assignment `completed`; it does not reuse Assignment.accepted_at,
which currently records claim acceptance, as a completion timestamp.

`TaskAcceptedEffectsPort.apply_accepted_effects(request)` returns that result or
`TaskAcceptedEffectsUnavailable`. Its future participant requires the caller's
one root transaction, validates exact state/lineage, flushes only, and never
commits, authorizes, creates REV/CON facts or calls back into routing. The shared
REV acceptance command owns composition and authorization. No implementation or
claim of terminal state support is included in 04E1A.

## Acceptance criteria

Future tests are named now; none is claimed executed by this plan.

| Exact future test | Boundary and discriminating proof |
|---|---|
| `test_source_matches_real_completed_run` | Real `material_fixture` + live execution + stored true-policy source; compare every source scalar and join-only public fact with its canonical parent |
| `test_source_rejects_null_scalar[field]` | Each required stored column independently NULL; non-null constraint denies while otherwise valid row rolls back |
| `test_source_rejects_scalar_substitution[field]` | Separate well-shaped request ID/digest/generation/result ID/digest, content hash/bytes/semantic hash, replica and review-boolean substitutions reach the named semantic guard |
| `test_source_rejects_foreign_lineage[field]` | Two real stored graphs: independent project/task/Submission/version/assignment/contributor/contribution-policy swaps reject, including coherent same-project sibling ownership |
| `test_source_rejects_sibling_completion_event` | Real same-project sibling completion event, all other facts valid, rejects at source guard |
| `test_source_rejects_phase_receipt[substitution]` | Separate execute substitution, finalize substitution and execute/finalize swap using existing real stored allow IDs; no invented/missing event |
| `test_source_rejects_ineligible_checker_source[state]` | Real queued/running/infrastructure-failed or blocking completed evidence cannot become successful source; select a registered failing-check fixture for the blocking case |
| `test_source_rejects_unactivated_guide` | Deliberately inconsistent storage fixture isolates source activation guard, not a claim of a valid false-policy product graph; restoring real activation permits the same source |
| `test_source_retains_historical_guide_and_generation` | Real successor activation/generation leaves original source IDs and policy tuple intact; no currentness claim or effects |
| `test_source_is_immutable[update/delete/truncate]` | Each direct-SQL mutation denied with exact row preserved |
| `test_source_uniqueness_and_caller_rollback` | Duplicate exact source rejected; failed enclosing transaction leaves source/effect counts unchanged and valid insertion remains possible |
| `test_source_contract_is_strict_and_detached` | Strict UUID/hash/version/boolean, unknown/private fields, nested lineage mismatch, predecessor shape; exact frozen value |
| `test_false_source_value_is_transport_only` | False scalar transports without coercion; no claim of activated false storage/routing. Real false proof remains 04E2/04E3 after activation becomes reachable |
| `test_accepted_effects_contract_is_source_neutral` | Exact input/result identity and closed prestates/poststates; imports no REV or routing API |
| `test_source_foundation_has_no_runtime_entry` | No registration, route, composition, reader/writer, current pointer or effects implementation; proposed AUTH identifiers remain absent |
| `test_upgrade_preserves_existing_sources_without_publishing` | Actual 0010 -> 0011 upgrade retains prior Submission/checker/AUTH bytes and adds an empty source table; no routing/review/acceptance effects |

Guard-removal probes: remove only source scalar equality, phase-receipt equality,
historical activation check or immutable trigger in an isolated test database;
its corresponding named regression must fail at the intended assertion. Keep
valid controls enabled and exclude fixture/setup errors from proof. FK/NOT NULL
proof names their own boundary; it must not be mislabeled as semantic-trigger proof.

## Risk and review routing

Required focused plan/candidate tracks: architecture/reuse, security, QA/test
delta, docs/product operations and CI integrity. Lead owns shared checks and
exact clean candidates. Human focus: one durable source identity without
premature routing authority, exact receipt/material/locked-policy custody and
honest false-policy limits.

## Evidence

Use the existing isolated runner with locally configured test PostgreSQL/MinIO;
never commit credentials. From `backend/`:

```sh
.venv/bin/python scripts/run_isolated_tests.py --metadata-json /tmp/arch04e1a-tests.json --timeout-seconds 1200 -- .venv/bin/python -m pytest tests/tasks/post_submit_routing -q --tb=short
.venv/bin/ruff check app/modules/tasks/api/post_submit_routing.py app/modules/tasks/api/accepted_effects.py app/modules/tasks/routing_models.py tests/tasks/post_submit_routing alembic/versions/0011_task_routing_source.py
.venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main
.venv/bin/python -m scripts.behavior_ownership validate
.venv/bin/python -m scripts.test_structure_boundary validate --policy ../.ci/auth-boundaries/TEST_STRUCTURE_POLICY.md --ledger ../.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json
```

From repository root:

```sh
.venv/bin/python scripts/check_commitrail_records.py --base-ref origin/main
python3 scripts/check_markdown_links.py
git diff --check
```

Run affected schema/head, catalogue and retained activation-denial tests through
the same isolated runner. Full hosted semantic lanes and aggregate reconcile
all collected nodes with zero skips/deselections; coverage is diagnostic. Run
stale-wording scans against changed current records. No new percentage gate.

## Plan-review reconciliation

Architecture findings PLAN-001..005 and security findings SEC-04E1A-001..003
require exact headings, files, fields, source-neutral effect types, null-safe
custody and independent named proof. This record incorporates those requirements.
The parent 04E contract must describe this source-only boundary and explicitly
assign complete receipt propagation to 04E1B/04E2. No reviewer result is asserted
here; exact freshness and execution evidence remain in the eventual PR.

## Reconciliation

Next: existing shared REV/CON source/acceptance and fence foundations before
false-handler composition, then 04E1B/04E2/04E3 and remediation 04F. Live human
queues or leases are not prerequisites of automated acceptance. Public intake
remains behind complete outcomes and remediation. Navigation distinguishes
this source schema from authoritative publication and deployed behavior.
