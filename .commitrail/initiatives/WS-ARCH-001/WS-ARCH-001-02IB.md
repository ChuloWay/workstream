# ARCH-02I-B — Public admission-backed Submission entry

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: an authorized contributor can upload one ZIP through the existing preparation operation, recover a retained ready admission through exact same-key replay after a lost response, consume that admission through the canonical `POST /api/v1/tasks/{task_id}/submissions`, and read the resulting immutable Submission and checker history for initial work or exact checker remediation.

## Intent

Connect the delivered preparation and atomic Submission writer at their existing
HTTP boundary so the first contribution path can be exercised through public
backend APIs. This is the entry portion of the current
[first complete contributor milestone](planning/PLAN.md#first-complete-contributor-milestone),
within its ARCH-02I public intake group. It does not claim the complete journey
or production readiness before live worker composition and the realistic drill.

## Planning baseline at `cdfdebd74`

The following describes the source state before this bounded public-entry change.

- `POST /api/v1/tasks/{task_id}/submission-bundle-preparations` is mounted in
  `backend/app/api/routes/artifact_submissions.py`. It streams an outer ZIP to
  `PreparedSubmissionBundlePreparationCommand`, which runs selected PRE and
  returns a ready `admission_id` only after durable ART verification. A blocked
  attempt returns bounded same-request `pre_submission_checker_failed` feedback.
  `include_in_schema=False` keeps this callable route out of OpenAPI.
- `compose_hidden_submission_creation_command()` in
  `backend/app/api/deps/authorization.py` already binds TASK's
  `TransactionalSubmissionCreationCommand` to canonical human AUTH and ART
  admission consumption. Its sole transaction commits the immutable Submission,
  artifact binding, initial checker reservation, and outbox request. Hidden
  PostgreSQL proof in `backend/tests/tasks/test_submission_lineage.py` and
  `backend/tests/tasks/submission_dispatch/` covers exact packet custody,
  concurrency, rollback, and replay. No mounted HTTP POST invokes this command.
- `SelectedPreSubmitRun` retains the actor/idempotency key, task/assignment,
  exact reservation and terminal PRE facts. `SubmissionBundleDurableIntent`
  links that run to the put attempt; `SubmissionBundleAdmission` links the
  intent to ready/consumed/stale status. The existing POST replay reads those
  facts only after preparing the ZIP stream again. No authorized metadata-only
  contributor status operation can recover a ready admission after a lost HTTP
  response. A rejection before selected reservation creates no durable run.
- Public claim/start and contributor work-context routes are in
  `backend/app/modules/tasks/router.py`. The same router exposes
  `GET /tasks/{task_id}/submissions` and `GET /submissions/{submission_id}`;
  checker history has existing authorized reads. These reads do not create work.
- The adopted [intake contract](../../../docs/architecture_data_model.md)
  names `POST /api/v1/tasks/{id}/submissions` for ready-admission consumption.
  The historical pre-cutover 02I contract also names that operation, while the
  current initiative plan limits first public intake to initial submissions and
  checker remediation. `TaskSubmissionContextFacts` permits only `initial` or
  exact `checker_remediation` with a routed cause and predecessor; human-review
  revision waits for its own live authority.

## Bounded change

### Allowed

- `backend/app/api/routes/artifact_submissions.py`: publish the existing ZIP
  preparation route in OpenAPI only after its required headers, raw ZIP request
  body, success statuses and bounded error responses are accurately declared;
  retain the same handler, AUTH dependency, selected PRE, and admission writer.
- `backend/app/api/deps/authorization.py`: compose a request-scoped dependency
  for the existing Submission command from the resolved actor's canonical AUTH
  context, and clear the actor-resolution read transaction before the command
  opens its one root transaction. Reuse current request/correlation identity.
- `backend/app/modules/tasks/router.py` and, only if a focused request/response
  type is needed, `backend/app/modules/tasks/schemas.py`: bind canonical
  `POST /tasks/{task_id}/submissions` to the existing command. Accept a ready
  admission ID, assignment ID, summary, attestation and optional exact
  predecessor. Derive contributor ID from the verified actor. Return bounded
  Workstream IDs/status with no provider location or unchecked client manifest.
  Preserve concealed denial and distinct retryable infrastructure errors.
- `backend/app/adapters/tasks/__init__.py` and
  `backend/app/modules/tasks/api/{submission_command.py,__init__.py}`: translate
  ART's closed admission rejection codes into a TASK-owned error at the
  existing command composition boundary. This is required because importing
  ART's public error into the TASK router creates a forbidden cyclic public
  dependency; the existing command and transaction remain singular.
- Focused HTTP and PostgreSQL behavior proof under
  `backend/tests/test_submission_bundle_admission.py` and a new
  `backend/tests/tasks/test_public_submission_intake.py`, reusing existing real
  ART/TASK fixtures. The fixture in
  `backend/tests/tasks/test_submission_lineage.py` may expose its exact ZIP and
  request for HTTP replay proof without changing owner behavior.
  `backend/tests/test_submission_bundle_preparation_recovery.py` may supply its
  direct-call session stub after the handler gains an owned read-transaction
  cleanup dependency. `backend/tests/submission_fixtures.py` may adapt retained
  history fixture inputs after removal of the superseded public
  `SubmissionCreate` transport type; those tests still exercise ART admission,
  immutable lineage, checker evaluation and history with retained private
  evidence fields, rather than accepting a client package URI through HTTP.
  `backend/tests/tasks/submission_dispatch/{test_rollback.py,test_replay.py}`
  may assert the TASK-facing typed error while retaining exact ART owner cause
  and rollback proof.
  `backend/tests/authorization/task_authority/{test_task_commands.py,test_public_surface.py}`
  `backend/tests/test_api_controls.py` and
  `backend/tests/test_artifact_architecture.py` may replace assertions that the
  canonical POST is absent with old client-packet denial, exact protected
  public route declarations and the expanded API inventory. The architecture
  test retains obsolete upload-route denial and admits only the canonical
  preparation/Submission operations. Existing authority gates and retained-route
  inventory checks remain enforced.
  Register the
  new test module in `backend/scripts/test_lane_catalogue.py` and
  `backend/tests/test_ci_lane_catalogue.py` if required to register the new
  test module.
- Companion real public drill under
  `experiments/pilot04_external_checker_runtime/` is owned by the runtime
  worker and uses these canonical entry routes with PostgreSQL and MinIO
  without editing product modules in this change.
- This change record and current-capability reconciliation in `README.md`,
  `docs/roadmap_status.md`, `.commitrail/INDEX.md`,
  `.commitrail/initiatives/WS-ARCH-001/{OVERVIEW.md,planning/PLAN.md,planning/CHUNK_MAP.md}`,
  and the affected `WS-ART-001`, `WS-AUTH-001`, `WS-AUTH-003`, `WS-CON-001`, `WS-POL-003`
  and `WS-REV-001` initiative overviews. These describe public entry as the
  intended merge outcome while preserving planned false-guide activation and
  complete public API/Celery service drill. The lead coordinates final PR and
  integrated-branch reconciliation; no local sheet export is present.

### Not allowed

- No upload-intent subsystem, additional ZIP writer, alternate Submission
  endpoint, old JSON packet route, compatibility alias, client URI/hash/manifest,
  provider coordinate, migration, or new policy/checker implementation.
- No changes to PRE eligibility, durable admission, TASK/ART atomicity, locked
  lineage, authorization rules, routing/acceptance, durable worker registration,
  CLI, human-review revision, or contribution/payment effects. No new status
  table, upload-intent authority, provider poller or alternate admission writer.
- No metadata-only status GET in this chunk. No claim that a missing
  pre-reservation row represents a successful upload, or that a completed
  passing PRE run without durable intent has a ready admission. Preserve
  recoverable uncertainty and explicit replay guidance.

## Design and decisions

The public mutation uses the already composed admission-backed command. It
passes only the same checked packet text and exact admission selectors into
`SubmissionCreationRequest`; it never independently reads ART rows or creates a
Submission. The command checks current actor, project grant, task/assignment,
predecessor, packet commitment and admission under its existing transaction.
The canonical route name avoids a second finalize operation and preserves the
retired `/submissions/{submission_id}/finalize` boundary.

Preparation should become discoverable with a truthful binary ZIP OpenAPI
contract. Its 202 status vocabulary includes non-ready custody states; only
`ready` plus a non-null admission permits the creation POST. Existing same-key
POST replay can observe a retained result but needs the ZIP stream again. The
same-key replay re-prepares and inspects the ZIP, checks the current actor and
task, and calls `SelectedPreSubmitCoordinator.read_current()` before checker
execution or durable put. When the stored run completed and its admission is
ready, `_selected_replay_result()` returns the same admission ID without
re-running selected PRE or PUT. A replay with changed bytes, packet, actor,
task, assignment or predecessor conflicts under existing request custody.
This is sufficient for a contributor who retains the ZIP and exact request key
after a lost ready response, though it retransmits and re-inspects the ZIP.
Passing PRE without a durable intent currently returns 503 on same-key replay;
queued/running or infrastructure-failed runs also return 503. Do not claim those
cases are recovered by this chunk or present them as ready admissions.

If the first-layer drill shows a requirement to recover a ready admission
without the ZIP, a later metadata-only ART read can use
`GET /tasks/{task_id}/submission-bundle-preparations/{idempotency_key}`.
That would require typed status contracts in
`backend/app/modules/artifacts/api/submission_preparation.py`, ART-owned
projection in `backend/app/modules/artifacts/submission_admission.py`, canonical
composition in `backend/app/adapters/artifacts/__init__.py`, route binding in
`backend/app/api/routes/artifact_submissions.py`, and a key-scoped
validated CHECKERS read port in
`backend/app/modules/checkers/api/selected_pre_submit.py` with implementation
in `backend/app/modules/checkers/selected_pre_submit_coordination.py`.
It must lock TASK before CHECKERS/ART, freshly validate the human's exact
project Submitter authority, and distinguish absent pre-reservation work,
queued/running PRE, completed failed PRE, completed passing PRE without intent,
durable PUT status, ready, consumed and stale admission. This is a candidate
owner-port extension for review, not an approved or implemented part of 02I-B.

## Acceptance criteria

- [x] OpenAPI describes the real mounted ZIP preparation operation, exact
      required headers and binary body, 202 response and bounded failed-intake
      feedback. The route remains backed by the current ART command.
- [x] A normal contributor bearer with an exact active Submitter grant can
      claim/start, upload a passing ZIP, receive a ready admission, then call
      `POST /tasks/{task_id}/submissions` and read its immutable Submission and
      checker reservation/history through public APIs.
- [x] After an exact current checker result routes the task to
      `needs_revision`, the same preparation and creation operations accept
      only the immediate predecessor and the existing checker-remediation
      cause. They produce version two under the same locked lineage. An
      uncaused predecessor and a human-review revision context are denied;
      neither gains a permissive public path.
- [x] The POST derives the contributor identity from AUTH and accepts no
      caller-owned contributor, package URI/hash/manifest, checker outcome,
      locked policy or reviewer decision. Server-generated result IDs are stable.
- [x] Exact creation replay after lost response returns the same Submission,
      binding and evaluation request without duplicate effects. Concurrent
      requests preserve one winner. A changed packet, foreign actor, crossed
      task/assignment, wrong predecessor, non-ready/stale admission, an
      admission consumed without the matching retained request/receipt,
      revoked grant and malformed selectors fail closed with no new product
      effects. Exact historical replay of the matching consumed admission
      returns the retained result under fresh authority.
- [x] A failed PRE returns actionable bounded feedback and creates no ready
      admission or Submission; infrastructure failure remains distinct and
      recoverable. A non-ready preparation response cannot be submitted.
- [x] Exact same-key POST replay after a lost ready response returns the same
      admission without a second selected checker run, provider PUT, ready
      admission or product effect. Replay requires the original ZIP and packet;
      changed bytes/packet/selectors fail closed. A missing durable intent or
      unresolved run returns the existing 503 and cannot be finalized.

The coordinated first-layer integration drill remains separate proof. It must
exercise real public HTTP, PostgreSQL, MinIO and durable workers through
first-pass correction, immutable creation, post-submit result and governed
outcome before the complete first journey is claimed. This chunk's focused
proof establishes the HTTP entry, not that combined outcome.

## Risk and review routing

- Risk class: `L1` — new public AUTH/TASK/ART mutation binding and OpenAPI
  exposure across immutable evidence and atomic dispatch.
- Required plan and implementation reviewers: architecture, security,
  product/operations, QA, test delta, documentation, and reuse/dedup.
- Human review focus: exact public request shape, server-selected identity,
  checker-remediation cause custody, denial/replay behavior, truthful
  preparation states and the limit of same-key replay after an uncertain result.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing operation and gap | Inspect `artifact_submissions.py`, `compose_hidden_submission_creation_command`, `TransactionalSubmissionCreationCommand`, `TaskSubmissionCreationService`, and mounted routes | Confirmed at `cdfdebd74`: preparation was mounted but hidden from OpenAPI; no creation POST was mounted. This change closes that public boundary. | Complete worker/outcome drill remains separate |
| Public HTTP entry and recovery | Earlier focused run passed 53 public-route, owner replay/rollback and history tests; its metadata identified the pre-edit base and is supporting diagnostic evidence only. The corrected public initial/history case passed at `9bfc5b589` after validated-settings/rate-control preflight. At clean merged head `b932bf3c4`, `/tmp/ws-entry-b932-qa-pg.json` records four focused PostgreSQL tests, including exact foreign-assignment concealment and all old client-packet denials. | Passed; exact-head runner records Alembic 0036, MinIO probe, and PostgreSQL/MinIO cleanup | Focused route fixture uses local artifact bytes; the companion public drill owns live MinIO transport |
| Closed authority and packet | The initial case proves a second active same-project Submitter without the assignment cannot consume the original actor's valid admission; uncaused predecessor, changed packet and caller `package_uri` are denied. Checker-remediation version two/replay and owner rollback pass | Passed | Existing owner tests retain concurrency and consumed-admission matching receipt proof |
| Published contracts and boundaries | Full `create_app().openapi()` check verified binary ZIP prep and the five-field extra-forbid canonical POST; `scripts.module_boundaries validate --protected-base cdfdebd74` | Passed | Full CI and implementation review remain pending |
| Protected route inventory | Published route/action inventory counts both new secured POST operations and preserves the hash of all other retained routes; old client-owned packet returns `422 invalid_request` without a Submission. `test_public_surface` and `test_openapi_documents_request_error_and_response_context` passed locally. | Passed | Hosted CI must run against the final PR head |
| Full journey | Real API plus broker/worker drain through current checker/outcome and contribution reads | Coordinated companion first-layer drill pending | Local route proof uses real PostgreSQL and local artifact bytes; companion public drill establishes MinIO transport |

## Review findings

Architecture/security and QA/product operations plan tracks passed at
`cdfdebd74` after reconciling checker-remediation scope, exact consumed
creation replay, and the absence of a selectable setup-fault hold. The lead's
pre-implementation spot check identified an obsolete public packet DTO used
only by retained-history fixtures and ambiguous repeated custody headers; this
change removes that DTO and rejects repeated preparation selectors before
product SQL. The module-boundary validator found a TASK→ART cyclic public edge
from the draft router's direct ART error import; the existing composition
adapter now translates only the four closed ART admission codes to a TASK-owned
error. No parallel composer or new metadata read is introduced.
Implementation QA found stale tests that assumed the canonical Submission POST
was absent and a foreign-actor assertion that allowed either 403 or concealed
404. The affected tests now require old client-packet denial, both protected
action declarations and exact 404 `submission_unavailable` for a second active
same-project Submitter without the assignment.
External PR review at `9e49f4057` found that the new POST also mapped command
composition `RuntimeError` to retryable infrastructure failure. The route now
reserves retryable 503 for SQLAlchemy failures, while focused proof requires
composition errors to propagate. Public denial tests now require exact
predecessor, packet and suspended-actor codes; the planning baseline and ART
next-boundary prose are reconciled with delivered entry.

## Reconciliation

- Current-source reconciliation: `cdfdebd74` had hidden ART preparation,
  atomic TASK/ART creation and public history reads, but no public creation
  POST or OpenAPI exposure for ZIP preparation. This change exposes those
  existing owners. Main through `42fd31b8f` adds CLI Finance policy management
  and PILOT-02B atomic JSON-to-DRAFT import with migration 0037. The reconciled
  public task router retains both batch commands and canonical Submission entry;
  CLI submit/status is still separate. False-guide
  activation and the realistic Celery service drill remain necessary before
  claiming a complete public false-policy journey.
- Next usable boundary: false-guide activation/readiness, outcome access and the
  complete real public API and Celery service
  drill; metadata-only preparation status only if the actual drill requires it.
- Remaining risks: a crash before selected PRE reservation leaves no durable
  lookup target, and a passing PRE run without durable intent may need a
  narrower retryable recovery path. Neither can be represented as `ready`.
