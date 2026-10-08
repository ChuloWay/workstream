# ARCH-04E1B-B6 — Atomic Submission and initial evaluation dispatch

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: the existing hidden Submission command commits
  verified admission consumption, immutable Submission/binding, their exact AUTH
  receipts, the initial CHECKERS reservation, TASK evaluation-pending state and
  one shared outbox request together. Exact replay revalidates authority without
  another allow, generation, binding or event.

## Intent

Complete step 3 of the [first contributor milestone](planning/PLAN.md#first-complete-contributor-milestone).
The existing creator allocates a new Submission on every call, discards creation
and binding decision IDs, and neither reserves evaluation nor appends dispatch.
Its ART replay path consumes authority again. CHECKERS reservation and outbox
append can create missing rows, so they cannot establish complete stored replay.
B3/B4/B5 already supply exact files, checked packet custody and representable
content. Reuse them rather than adding another intake or checker implementation.

## Bounded change

1. Extend `TaskSubmissionCreationService` and its existing transactional adapter;
   do not retain a second creator. The command uses admission identity as
   its exact replay key, qualified by task, assignment and contributor. Allocate
   UUIDv7 record identities only on the first successful transaction. Reject
   changed packet/selectors, foreign ownership and incomplete stored custody.
2. Keep one root transaction and TASK-before-actor/PROJECT/ART/CHECKERS custody.
   The first call locks the current submission context, obtains fresh human and
   fixed-binding authority, validates historical policy facts, creates the
   Submission and consumes its verified admission. Reuse the B5 projection with
   actual consumed files and checked packet, and use real Submission identities.
   Reuse the already-locked PROJECTS facts returned by
   `TaskService._load_locked_task_context`; never acquire PROJECTS after ART.
   CHECKERS' existing TASK guard verifies the stored Submission before reservation.
   The same creator supports existing hidden predecessor-linked submissions:
   generation one is per new Submission, not per task. This adds no live revision
   workflow and leaves no alternate successor path without dispatch.
3. Preserve owner boundaries: the ART-to-TASK composition adapter translates
   consumed material through the existing CHECKERS content projection. TASK's
   public contracts do not import ART contracts or PROJECTS composite contracts.
   Move composition-only admission participant contracts out of TASK's public
   API into a private TASK composition port. That port may combine PROJECTS and
   CHECKERS public values; TASK public facts keep their existing dependency guard.
   CHECKERS public values remain owner-independent. No private cross-owner SQL
   or imports in product services; cross-owner SQL is confined to migrations.
4. Retain one immutable TASK dispatch receipt for each new Submission operation. Its
   concrete purpose is recovering original Submission/request/attempt/result/event
   IDs and both exact AUTH decisions after a lost response, not another job queue.
   Bind request digest, owner scope, admission/binding/content, generation one,
   reservation and shared event, plus original version/predecessor and creation
   kind/status facts. Existing CHECKERS owns attempt state; existing
   outbox owns delivery state. The receipt is complete at commit and immutable.
5. Extend the existing AUTH consumption adapters to return their decision IDs
   and use canonical PREP for select-only validation of the original immutable
   events under fresh authority. Verify actor/service identity, exact resource,
   action/permission, project and canonical resource digest. No fabricated allow,
   receipt-shaped value as authority, or duplicate authorization on replay.
   ART persists one immutable binding receipt (admission, binding and decision)
   with consumption and returns it through its existing port. A separate owner
   receipt keeps historical admission row shapes unchanged; every current
   consumption requires it, without a nullable receipt fallback. Its consumed replay validates that receipt instead of consuming
   again. Add explicit PREP replay branches for `submission.create` and
   `artifact.submission.binding.create`. Reconstruct the original resource from
   immutable owner facts; never treat audit JSON as the source of product truth.
   Fresh transport request/correlation IDs may differ: validate the retained
   event's original request binding under current authority, rather than compare
   it to the retry's transport IDs. Missing receipt means unavailable, never a
   fallback.
6. Add narrow select-only existing-reservation/event verification to CHECKERS
   coordination and shared outbox, reusing their canonical matching rules. A
   stored replay may not call reserve-or-create or append-or-create. It cannot
   reset a successor fence, repeat provider I/O or recreate missing evidence.
   Recorded original creation facts are distinct from current lifecycle state;
   replay requires live authority and exact retained ownership, not fabrication
   of a currently in-progress task. Use separate TASK/ART select-only historical
   reads after commit; do not feed a synthetic pre-submission context into consume.
   The CHECKERS read returns the canonical stored request and its reservation so
   existing execution fixtures and later handlers use the committed request.
7. Advance TASK through its existing submitted/evaluation-pending
   transitions in that same transaction. Append a bounded evaluation-request
   event containing only exact IDs/digests and receipt references, never packet,
   policy bodies, file bytes or provider coordinates. No broker send before commit.
8. Add an additive migration with native UUID keys, exact composite ownership,
   immutable receipt/binding-decision custody and deferred canonical receipt/run/
   event validation. Use qualified protected references and safe search paths.
   Preserve retained data without inventing historical receipts. Existing records
   without the new proof cannot replay through the new command. No data deletion,
   compatibility writer or baseline rewrite. Freeze the retained parent facts
   on which a committed dispatch depends; test direct-SQL substitutions.
   Deferred completeness checks apply to each newly bound Submission, not merely
   dispatch-receipt insertions; require the binding decision on each new ART
   ready-to-consumed transition. Historical records stay untouched and are not
   made replayable by backfill.

## Allowed files

- TASK `api/submission_command.py`, exports, existing `submission_composition.py`,
  private composition participant contracts, bounded dispatch/replay persistence helpers, `repository.py`, `models.py`, and
  affected owner fixtures. Existing lifecycle constants/guards are reused.
- Existing `adapters/tasks`, `adapters/checkers`, `adapters/artifacts`, and hidden
  composition in `api/deps/authorization.py`; no new route.
- ART admission-consumption contracts, `submission_bindings.py`, binding
  authorization and admission model; affected consumed-material callers/tests.
- AUTH submission creation/resource contracts, canonical PREP replay dispatch
  and a focused submission receipt validator; exact affected adapter tests.
  Shared AUDIT resource-name validation gains the two exact submission resource
  kinds so retained receipts carry their real project/resource identities.
- CHECKERS `api/execution.py`, coordination/repository reservation verification;
  shared outbox API/service/repository select-only exact-event verification.
- One additive Alembic migration and actual PostgreSQL schema fingerprint/reset
  metadata, Alembic head/allowlist and exact migration-chain tests; model registration and identifier/ownership inventories if required. Reconcile unchanged AUTH structural-debt line spans without changing content hashes or limits.
- Focused TASK/ART/AUTH/CHECKERS/outbox tests and real PostgreSQL composition,
  replay, concurrency, rollback and direct-SQL tests; new-test lane registration.
  Update current materialization/review/routing fixtures to use the stored request
  instead of independently reserving generation one. Historical migration tests
  use an explicit test-only predecessor-schema seeder preserving their original
  retained-data assertions; no production schema detection or fallback creator.
- This record, affected current ARCH/AUTH/POL/CON/REV navigation, README,
  submission/checker/artifact specifications, current system-flow/architecture brief (including its regenerated PDF) and operating manual, and roadmap; local exports if present.

## Prohibited changes

No public intake exposure, worker/handler registration, post-check execution,
routing/acceptance activation, human review/revision implementation, compensation
change, claim expiry/skip, provider I/O during commit, catalogue change, alternate
intake path, compatibility alias, retained-data rewrite or weakened test/CI gate.
Required existing successor lineage proofs remain and use this same creator;
this chunk does not authorize live human revision.

## Acceptance criteria

1. Real PostgreSQL and a genuinely prepared/verified ZIP produce exactly one
   Submission, consumed admission, binding, human/binding allow, initial request/
   attempt/result reservation and request event, with TASK evaluation_pending.
   Compare every returned ID and stored policy/file/packet fact to actual owners.
2. Inject failure after each owner stage (including actual receipt persistence,
   reservation and event append). Observe staged rows then caller rollback: no
   partial Submission, consumed admission, status change, allow or dispatch remains.
   No external provider or broker is called by this transaction.
3. Lost-response retry returns the same IDs and counts after fresh authority.
   Independently alter request text, admission, task, assignment and contributor;
   include a second valid foreign lineage. Revocation and suspended service deny.
   Missing/wrong creation or binding receipt, reservation or event rejects without
   recreating anything. A later evaluation generation is not reset by replay.
4. Independent sessions submitting the same admission serialize into one committed
   result. Different admissions for the same initial task cannot create two initial
   Submissions. Exercise current project-role revocation/issuance and TASK-before-
   CHECKERS lock order using real AUTH, with bounded waits and cleanup.
5. Direct SQL independently substitutes each receipt/owner/run/event reference,
   omits a required component, and mutates frozen parent facts. Assert the intended
   constraint, rollback and valid control. Removing a key receipt or owner guard
   makes its exact regression fail for that defect rather than an earlier guard.
6. Existing public surfaces remain unchanged; hidden composition uses canonical
   owner operations and retained B5 content/request digest rules. New events remain
   undeliverable until the later handler/activation steps. Full hosted suite runs
   without skipped/deselected cases or gate changes.
7. Existing hidden successor creation also commits its own generation-one request
   and event with exact predecessor/version lineage. Historical migration proofs
   still seed genuine predecessor storage and exercise the actual migration; they
   do not call a current writer against an incompatible earlier schema.

## Risk and review routing

L1: bounded multi-owner transaction, authorization receipts, replay and storage.
Plan review: architecture/security and QA feasibility. Implementation: security,
architecture/reuse, QA/test-delta, CI integrity, docs/product operations. Shared
checks: focused pure contracts; isolated real PostgreSQL composition and mutation
probes; module/AUTH/test boundaries, ownership/lane inventory, Ruff, schema parity,
links, stale wording, Commitrail and complete hosted CI. Human focus: one operation,
no partial commit or replay repair, exact original receipt verification, concurrent
revocation/creation, and no premature exposure or delivery.

## Next dependency

Step 4 consumes these committed exact request IDs through hidden request/completion
handlers. It must use current CHECKERS/ART/AUTH custody and shared outbox delivery;
this record alone does not claim automatic evaluation, outcomes or a public journey.

## Retained test behavior

The former mock-only command-order and predecessor tests are replaced by the real
atomic creation/participant rollback tests and the existing real Review predecessor
chain test, now consuming each successor's committed request. The mini-schema
hidden-concurrency/service tests previously mocked TASK locks and AUTH admission;
their required behavior moves to real-AUTH concurrent creation and revoked-binding
identity tests. ART-only binding serialization/rollback tests remain. Early human
lifecycle, foreign actor, policy failure/handle cleanup and malformed ART-result
unit tests remain. Historical migration seeders are test-only, refuse current
schema writes and retain predecessor constraints; they do not provide a product
compatibility path.

## Evidence

- `tests/tasks/submission_dispatch/` covers real prepared ZIP creation, exact
  original replay, valid foreign lineage, missing-owner read faults, current
  authority, five staged participant failures, unmanaged savepoint denial,
  independent-session same/different-admission contention and real project-role
  issuance/revocation. SQL tests bind individual receipt members, reject an
  unrelated stored allow and freeze retained receipt/Submission fields.
- The additive upgrade test snapshots actual predecessor rows and proves no
  invented dispatch or binding-receipt backfill. Existing older migration tests
  keep their retained-data refusal/preservation requirements.
- A local isolated predicate-removal probe makes the unrelated-allow commit
  regression fail on acceptance of that allow; setup and cleanup both complete.
  This distinguishes receipt validation from an earlier missing-field/FK guard.
- Existing Local/MinIO execution, historical-owner reads and predecessor Review
  composition use the committed request. Unit, module/AUTH/test-boundary,
  identifier, behavior-ownership and test-lane checks remain required. Exact-head
  hosted completeness, current review conclusions and their provenance belong in
  the PR trust summary rather than durable navigation.

Downstream fixture reconciliation retains the routing status and accepted-assignment
preconditions as explicit negative cases with no-effects assertions and valid
controls. CHECKERS tests compare exact committed initial run/request-event IDs
instead of obsolete empty totals. Sibling and successor fixtures read their actual
committed requests; only genuine later-generation cases allocate a new request.
Predecessor migration callers explicitly select the revision-gated historical
seeder, including Review/Contribution fixture chains. Receipt columns retain their
referenced owners' canonical-string Python identities and convert at typed UUID
API boundaries; the native UUID and identity-family tests remain enforced.
