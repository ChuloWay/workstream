# ARCH-04F3 — Exact-cause checker-remediation replacement intake

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Intended merge outcome: one hidden contributor replacement ZIP passes the
  canonical pre-submit intake again and creates a new immutable Submission and
  generation-one evaluation request only when its immediate predecessor has the
  exact current authorized checker-remediation outcome.
- Base: merged main `735cf2659` (PR 534); current migration head
  `0032_checker_remediation`. This record is group 1 of the first complete
  contributor milestone in the [current plan](planning/PLAN.md).

## Intent and observed gap

The current TASK context accepts `needs_revision` with only the latest
Submission ID/version and labels every such predecessor `revision`. ART retains
that predecessor across preparation, passing pre-submit evidence, verified
admission and binding. The canonical TASK writer creates version 2 and its
evaluation dispatch from that admission. [04F2](WS-ARCH-001-04F2.md) now makes
`needs_revision` possible from a completed, authorized, contributor-correctable
checker result, but none of those intake facts prove which result caused it.
The existing ART predecessor-change check proves the ZIP changed, not that
the contributor is allowed to replace this particular failed evaluation.

The target is a hidden, usable replacement path through the existing ART
preparation/verifier, TASK context and single `TaskSubmissionCreationService`.
TASK selects the immutable `TaskPostSubmitRoutingManifest` for the latest
Submission under its task/assignment locks and checks the current CHECKERS
result through the existing public evaluation port. The source must be
`needs_revision`, exact for that task, assignment, contributor, Submission,
run and result, and have its completed AUTH-backed routing consequence. The
context exposes one server-selected `checker_remediation_manifest_id`; no
caller-selected checker route or new endpoint is introduced. A source mismatch
or absence denies before contributor ZIP bytes are read, and a late change
denies before evidence, admission consumption or a new Submission commits.

Carry that single cause ID from the TASK context through ART passing evidence,
verified admission and final binding, then into the TASK creation dispatch.
The existing predecessor ID/version, locked policy context, archive and
semantic manifest remain the other lineage facts. Bind the cause in the final
prepared AUTH resources for bundle preparation, artifact binding and Submission
creation; preliminary actor/assignment preflight remains before byte access.
The database closes the same cause relationship across immutable rows and the
three retained AUTH receipts. No second findings store or duplicated checker
result body is needed. An ART durable intent already references its immutable
evidence set, and a Submission already references its one admission/dispatch;
extra cause columns on those rows would repeat an existing exact link.

The existing `revision` kind currently conflates checker remediation with
human revision. The new TASK context and committed creation kind will name
`checker_remediation` explicitly for new replacement creation. Historical
immutable creation evidence is retained; new human-review revision admission
remains unavailable until its own exact Review cause exists. This is not a
generic revision permission or a compatibility route. Review of the migration
must confirm retained initial/old rows remain valid without accepting an
unproven new revision.

Alternatives considered: predecessor-only checks are insufficient because a
synthetic or human-review `needs_revision` state could reach ART; copying
findings/result JSON into ART would duplicate CHECKERS evidence; a separate
replacement writer or route would fork the atomic creation operation.

## Bounded implementation plan

1. TASK context: extend `TaskSubmissionContextFacts` and its repository owner
   to resolve one exact current 04F2 manifest after locking TASK, assignment
   and latest Submission. Use the existing `EvaluationCoordinationPort` for
   CHECKERS currentness, injected at the existing adapter/composition root;
   do not import CHECKERS storage models into TASK. Revalidate the same source
   at each TASK context relock. Initial intake keeps no cause. A missing,
   foreign, stale, setup-fault or non-remediation manifest denies.
2. ART intake: compare the source selected before ZIP reading with each later
   relock. Include its ID in the existing passing evidence operation identity,
   passing capability, durable final preparation resource, verified admission,
   consumption and binding resource. Run the full original ZIP intake and
   canonical change gate; the predecessor's archive and immutable evidence are
   read only.
3. TASK creation: consume only an admission with the same exact cause, append
   the source ID to the existing dispatch and creation AUTH resource, then
   reserve the successor evaluation and outbox event inside the same root
   transaction. Fresh-authorized replay checks the committed source/receipts
   by the same admission key and does not require the old run still be current.
4. A linear migration after `0032_checker_remediation` adds the minimal cause
   columns/checks/FKs and replaces the existing admission, AUTH-resource and
   dispatch SQL closure as necessary. Preserve retained evidence and deny SQL
   substitution of cause, predecessor, recommendation or receipt. The migration
   must not add a sibling Alembic head.

### Allowed files

- TASK: `backend/app/modules/tasks/api/submission_context.py`,
  `api/submission_command.py`, `api/__init__.py`, `repository.py`, `submission_composition.py`,
  `submission_replay.py`, `submission_dispatch.py`, `submission_participants.py`,
  `models.py`, and `backend/app/adapters/tasks/__init__.py`.
- ART: `backend/app/modules/artifacts/api/submission_preparation.py`,
  `pre_submit_evidence.py`, `submission_materialization.py`,
  `submission_admission.py`, `submission_bindings.py`, `schemas.py`,
  `models.py`, `service.py`, `authorization.py`, and
  `backend/app/adapters/artifacts/__init__.py`.
- AUTH: `backend/app/modules/authorization/submission_preparation.py`,
  `submission_consumption.py`, `submission_creation_authorization.py`,
  `prepared_submission_replay.py` only if its exact replay comparison needs
  the cause, and `backend/app/modules/authorization/artifact_project_authority.py`
  only if its typed guard needs the new closed kind. Existing action and grant
  identities stay unchanged.
- One linear `backend/alembic/versions/0033_checker_remediation_replacement.py`
  migration after 0032; matching model/schema registration and
  `backend/tests/test_alembic.py` migration graph assertion.
- Focused existing owner tests under
  `backend/tests/test_submission_predecessor_custody.py`,
  `backend/tests/tasks/submission_dispatch/`,
  `backend/tests/tasks/post_submit_routing/`,
  `backend/tests/test_submission_bundle_admission.py`,
  `backend/tests/test_submission_preparation_authorization.py`,
  `backend/tests/authorization/task_authority/test_submission_authority.py`,
  `backend/tests/test_tasks.py`, and one new focused integration test file under
  `backend/tests/tasks/submission_dispatch/` if needed for the joined journey.
- This record and affected current capability claims in `docs/roadmap_status.md`,
  `docs/spec_chunk_4_task_queue_assignment.md`,
  `docs/spec_artifact_storage_service.md`,
  `docs/spec_authorization_service.md`, `README.md`, ARCH plan/chunk map/overview
  and `.commitrail/INDEX.md` only where the merged outcome changes a claim.
  Verify exact documentation filenames and links before editing.

Shared migration environment/fingerprint files, AUTH catalogue/action lists,
and any overlapping current docs are **coordination-owned by the lead** unless
explicitly allocated. A newly observed required file outside this list is a
plan-review delta before editing, not an invitation to widen implementation.

### Prohibited changes

No public 02I route, production handler registration, new checker command or
result writer, human Review/revision decision, acceptance/contribution/award,
Operator retry, claim lease, payment fulfillment, frontend, policy relaxation,
compatibility/fallback writer, or modification to the recovery worker's
terminal retry/setup-fault scope. Do not change existing committed Submission,
checker result, AUTH decision, outbox event or ART bytes. An infrastructure or
setup fault never becomes contributor remediation.

## Acceptance and proof

- From a real routed 04F2 `needs_revision` result, the same submitter's changed
  full ZIP passes pre-submit checks, reaches a verified ready ART admission,
  and creates exactly one version-2 Submission, binding, creation/binding
  receipts, generation-one CHECKERS reservation and request event atomically.
  It retains the exact predecessor and remediation manifest, locked policy and
  verified new bytes. The prior Submission, failure result and manifest remain
  byte-for-byte immutable; no Review or failure economics appear. Exercise both
  locked human-review-required values because remediation is policy independent.
- The unchanged archive and same semantic manifest fail the existing change
  gate before provider put, with actionable intake feedback. A blocked new
  pre-submit check creates no Submission or replacement dispatch. Valid new
  content is the control proving the cause gate is reachable.
- Foreign task/assignment/contributor/predecessor, a valid foreign remediation
  manifest, non-remediation success, task/setup failure, stale current run,
  later generation, missing or substituted AUTH receipt, and source changed
  between first context lock, byte read, verification and consumption all deny
  without a new Submission. Valid controls for each substitution are two
  independently routed failure fixtures, not random IDs or synthetic task
  status updates. Denial before byte access is checked with a source that fails
  if read.
- Concurrent replacement requests serialize on TASK and one succeeds; an
  independent-session current-run/generation race proves TASK-before-CHECKERS
  lock order and stale-cause denial. Replay after response loss returns the
  exact committed identities under fresh actor authority with no repeated
  binding, evaluation or outbox effect. Rollback and actual later participant
  insertion failure leave no partial replacement effects.
- Direct PostgreSQL probes reject evidence/admission/dispatch cause
  substitution and mismatched final AUTH contexts. Upgrade from 0032 preserves
  previously committed initial and remediation rows and validates their
  original receipts. Function search paths and FKs do not trust caller text.

The valid integration control starts from
`tests.tasks.post_submit_routing.remediation_support.remediation_source`,
which uses `completed_evidence` for real initial ART admission/Submission,
CHECKERS finalization and a routed AUTH outcome. Use
`revision_archive(h.data)` from the existing ART replacement test to create a
changed governed ZIP, then `_verified_admission` and
`compose_hidden_submission_creation_command` for the sole writer. The current
`test_submission_predecessor_custody.py` fixture merely updates TASK status;
replace it with the routed control before claiming exact-cause proof. Keep
initial-submission and existing success-path regressions as controls.

Run focused pure contract tests, then bounded isolated PostgreSQL/Local and
MinIO tests through the repository's test runner, migration upgrade/replay,
the current boundary/inventory/docs/link checks and the required hosted suite.
Discriminating probes must remove the cause/currentness guard and show the
specific negative assertion fails after a valid control passes. Do not claim
runtime proof from this inspected plan.

## Risk, review and human focus

- Risk class: L1: contributor authorization, immutable evidence and atomic
  ART/TASK/AUTH/SQL lineage cross owner boundaries.
- Plan review before implementation: architecture, security and QA, including
  a reachable positive control and each negative's earliest expected denial.
- Frozen implementation review: architecture, security, QA, test delta,
  reuse/dedup, product operations and documentation. Add CI integrity if
  migration/test registration or required checks change. The lead runs shared
  checks once and coordinates review target freshness.
- Human focus: the replacement must be caused by the exact current checker
  failure, use the original assignment and locked policies, pass full intake
  again, and atomically dispatch a new evaluation. The failure path creates no
  acceptance or economic facts; public activation remains later work.

No human product decision is needed for this bounded hidden path. The lead's
internal plan review is the implementation sequencing point; it is not a
new user permission gate.
