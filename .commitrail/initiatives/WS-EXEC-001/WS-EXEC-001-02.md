# WS-EXEC-001-02 — Trusted intake, deployment and public microVM journey

- Initiative: WS-EXEC-001
- Durable disposition: Complete
- Intended merge outcome: prepare one bounded trusted intake microVM during the authorized ZIP upload, inspect/extract and run the Workstream default inside it, and feed the existing PRE/POST owners verified material without host ZIP/default execution; require coherent hosted intake configuration and prove both governed outcomes through public APIs and durable workers.

## Intent

Deliver authorized upload preparation, trusted intake, hosted configuration and
public durable-worker proof as one bounded change. The deployment/public proof
formerly described by WS-EXEC-001-03 is consolidated here; its original evidence
is retained below rather than maintained as a second change record.

Reduce contributor and agent waiting by preparing one clean, bounded VM during
the authorized upload. Both PRE and POST must use the same trusted isolation
boundary for ZIP handling so submitted bytes never select a host parsing path.

## Original starting behavior

Boundary 1 supplied real Smol execution and recovery through CHECKERS' existing
adapter. Public upload invoked ART's host `SubmissionArchiveInspector`,
then CHECKERS directly projected the archive and evaluates the default on the
host. Durable POST also projected on the host. Those call paths missed both the
requested overlap and the fresh-VM custody for all ZIP processing.

The user authorized continuing through this boundary and the separate full
public API/durable-worker drill. A node probe is not completion.

## Bounded change

### Allowed

- `backend/app/interfaces/`: narrow typed trusted-intake capability and session;
  shared external adapter convention remains unchanged.
- `backend/app/adapters/artifacts/`, `backend/app/adapters/checkers/__init__.py`,
  `backend/app/core/config.py`: explicit typed factory/constructor registration,
  required ART node configuration and scoped PRE/POST composition.
- ART `api/`, `submission_archive.py`, `submission_admission.py`,
  `submission_materialization.py`, `post_submit_materialization.py` and affected
  imports: canonical structural types, verified raw-file materialization and
  existing request-scoped preparation. `preparation.py` and `sources.py` for the explicit inspection cancellation hook;
  `trusted_intake.py` for the shared PRE/POST preparation lifetime and retained-reader binding.
- CHECKERS `api/default_checker.py`, `api/materialization.py`,
  `selected_pre_submit_execution.py`: typed default execution/material-view
  consumption; ordered project PRE execution and existing result semantics.
- `external_checkers/`: private prepared-intake protocol sharing the existing
  Smol machine/guardian engine, trusted intake image using canonical Python
  inspection/default code, controlled guest scratch/streaming and proof fixtures.
- Focused owner/adapter/conformance tests, their exact architecture inventories, explicit CI catalogue membership, and the four new production modules in `backend/scripts/behavior_ownership.py` and `.ci/behavior-ownership/partition.v1.json`; affected runtime documentation,
  configuration examples, roadmap and initiative records.

- `deploy/hosted/compose.yml`, `release.env.example`, `preflight.py`, `compose.py` and their
  existing `scripts/test_hosted_release_config.py` tests: require pinned intake
  identities and mount its private Unix socket into API/Celery processes;
  retain existing artifact-store, secrets and project execution boundaries.
- `external_checkers/deploy/`, `external_checkers/README.md`: concrete Smol
  provisioning/startup/recovery instructions and exact source/cache custody.
- `experiments/pilot04_external_checker_runtime/run_public_journey_probe.py`,
  `guide_runtime.py`, `guide_inputs.py`, its existing shared probe helpers,
  Dockerfile/checker proof fixture and README:
  accept a provisioned node/config rather than inventing a hard-coded Docker
  runtime; verify both typed health identities and use the existing public flow.
  Add only focused proof helpers needed for upload overlap/cancel and exact
  runtime/cleanup observations.
- `.github/workflows/release-images.yml` and `scripts/test_public_smol_proof.py`:
  execute the fault-control safety regressions in required CI and trigger on their
  proof owners. Preserve all existing checks, pins and permissions.
- Focused existing release/probe tests, docs describing deployment prerequisites,
  roadmap, initiative records and index reconciliation.
- Disposable EC2 resources in a uniquely owned directory/unit/container/database/
  port namespace; no shared service restart, prune, volume deletion or edits to
  `/etc/workstream/` or the other agent's protected services.

### Not allowed

No policy, authorization, database schema, persistent workflow, submission,
review, acceptance, award or artifact-store semantic changes. No project image
may assert ART inspection or Workstream default authority. No host ZIP/default
production fallback, generic command API, project VM handle, new scheduler,
managed service or edits to the independently owned model gateway work.

## Design and decisions

1. Add `trusted_submission_intake/unix_socket` through
   `ExternalServiceAdapterFactory[TrustedSubmissionIntakeAdapter]`, registered
   only in the ART composition root. Its health requires Smol and the node-owned
   pinned intake image/config plus the exact default behavior digest. CHECKERS'
   existing health cannot satisfy ART readiness. A deployment can point both
   typed capabilities to one Smol node; retaining a Docker/runsc project node
   requires a separate Smol intake socket. There is no runtime fallback.
2. Publish canonical structural data types through an ART API leaf and update
   affected callers. Keep one implementation of ZIP validation and default
   rules, packaged into the trusted intake image from this source. Wire encoding
   validates those same contracts; do not fork normalization or checker rules.
3. Start one process-local preparation immediately after the first successful
   TASK/project authorization transaction and before consuming upload bytes.
   Upload and VM preparation run concurrently. The original artifact deadline
   bounds the whole intake session; preparation failure, upload failure,
   cancellation or disconnect aborts and drains its transport/VM cleanup.
4. After sealed upload, preserve the existing relock and materialization AUTH
   transaction ordering. Send the sealed bytes through `PreparedArtifact.inspect`
   with a trusted-session inspector and explicit cancellation hook. Do not call
   `committed_source.stream()`: its one-shot `stream_claimed` flag would prohibit
   the later workspace callback and external grants. Invoke only inspect/extract,
   not default evaluation,
   under that authorization. Return the exact archive identity and canonical
   inventory. Bind the existing manifest, selected PRE reservation and authority
   exactly as today. No early VM action creates a Submission or CHECKERS result.
5. Under the committed selected lease, ART opens its existing
   `_process_prepared_submission` quota-owned scratch callback
   and exports bounded raw files from the sealed intake session. ART independently
   checks normalized containment, inventory, size, executable mode and every hash;
   it alone creates scratch paths and issues existing external material grants.
   CHECKERS receives only a callback-scoped material view and the typed default
   result after ART has invoked its trusted-intake port and confirmed cleanup,
   removing its current direct `_projected_tree` private call. This keeps the
   same required default-before-project order with fewer cross-owner callbacks.
6. The typed default operation binds the exact committed reservation, policy,
   archive, manifest and existing default input. The trusted guest runs the
   canonical evaluator once. After verified export/default, close the intake VM
   before executing any project PRE image, so waiting intake VMs cannot hold
   every node slot while requesting project execution. Preserve locked order,
   stop-on-failure and distinct infrastructure outcomes.
7. POST starts the same ART intake during its authorized artifact download,
   inspects/exports under the existing current CHECKERS lease, then closes the
   intake before invoking the project consumer. Preserve the later authority,
   material identity and lease revalidation before accepting its result.

## Private session and guest mechanics

Use the existing Smol `Machine` and exact guardian cleanup, extracting only a
small private resource tuple where both consumers require it. A random boot epoch,
lease nonce, trusted image/platform/config/default behavior identities, phase,
policy hash, resources and one absolute deadline bind the prepared session. Later
operations add sealed archive hash/size and manifest/reservation identity. The
opaque Python handle cannot be serialized, replayed, substituted or used after
close. The node connection owns it; EOF expires it. Preparation permits at most three attempts, with fixed 100 ms then 200 ms
backoff charged to the original deadline. Only an explicit `runtime_unavailable`
control-process launch/nonzero failure in VM create/start or trusted bootstrap
installation is retryable, and only after confirmed cleanup. Image/config/digest,
peer/custody, resource enforcement, protocol, capacity, cancellation and deadline
failures are final. Guest readiness identity mismatch is final. There is no
in-session retry after any archive byte is accepted, nor after inspect, export
or default invocation. Unknown execution status is final.

The static bootstrap gains a closed trusted-intake mode selected only by node
configuration. The pinned Python worker has bounded writable private VM-disk
scratch and persistent framed control I/O; project-image confinement is unchanged.
It receives bounded raw ZIP bytes, runs canonical inspect/project, exports raw
files, and accepts default input only in the correct later phase. Control frames,
raw byte counts, output and stderr are bounded. No credentials, host socket,
arbitrary host path or public network is exposed. ART host scratch remains under
`ArtifactScratchManager`; VM state is transient processing, not artifact storage.

Transport cancellation explicitly shuts down sockets and drains blocking work;
cancelling an `asyncio.to_thread` await alone is insufficient. A failed or unknown
inspection/default execution does not cause an unsafe in-session retry. Existing
request/retry and durable-worker owners decide the next business attempt.

## Acceptance criteria

| Atomic behavior | Owner and required proof |
|---|---|
| Upload overlaps preparation | Public preparation command fixture blocks upload and observes adapter prepare before upload release; no reservation/default yet |
| Unauthorized upload allocates no VM | AUTH denial fixture observes zero intake prepare calls and unchanged product rows |
| Failed upload/cancel/expiry releases capacity | Real-node session plus upload failure fixture; exact lease, VM disk and cgroup absence; original deadline not reset |
| Work ZIP failures remain bounded intake feedback | Canonical malformed/encrypted/collision/traversal/expansion corpus through guest; no Submission or project check |
| Guest inspection preserves prepared custody | Real `PreparedArtifact.inspect` followed by `_process_prepared_submission` and an external grant on the same artifact; no one-shot committed-source read |
| Smol-only ART readiness | Default-only PRE and POST fail on absent configuration, Docker/runsc runtime or mismatched image/config/default digest; valid split Smol-intake/Docker-project configuration works; poisoned host parser/default is never invoked |
| Inventory and raw export stay authoritative | Alter receipt/archive/hash/path/length/epoch/phase/policy; host rejects before grant/consumer and removes quota scratch |
| Default follows committed reservation | Separate observe-before/after-commit proof; replay/foreign reservation and second default rejected |
| Default failure skips project execution | Exact default findings, no external grant execution and no Submission |
| Successful default releases intake before ordered project PRE | Same Smol socket with `maximum_parallel=1`, default-only and two ordered bindings: observe intake cleanup confirmed, then capacity released, then first project connection; cancellation/uncertain cleanup never reports release |
| POST uses the same guest intake | Real immutable input/lease fixture, exact manifest and late revalidation, no host ZIP invocation |
| Canonical rules have one implementation | Existing corpus remains; source/composition negative checks reject production host inspector/default calls |
| Existing policy branches remain | Required checks still feed existing true-policy review routing and false-policy shared acceptance; full public durable proof is recorded in the consolidated deployment/public section below |

## Live-drill repair: sequential material grants

The public two-binding trial exposed that the canonical grant publisher moves
exported files below `workspace/`, but revocation removed only its manifest.
The second binding then inspected an extra directory level and failed before
execution. Restore the sealed exported tree when revoking each exact grant,
including submissions that themselves contain `workspace` or the manifest name.
Keep one bounded scratch reservation and preserve per-request revalidation.
Strengthen the existing ordered lifecycle test to use the real ART grant owner;
verify a restoration-disabled mutant fails. PRE and POST also verify sealed
directory/file permissions after each grant; a permission-restoration mutant is
rejected before a later grant can hide the defect. Retain reserved-name/cleanup tests and rerun
the real public two-binding case. This repair belongs to this boundary's existing
ART preparation scope; it adds no policy or runtime path.

## Evidence

Owner/adapter suites, the canonical archive/default corpus, real PostgreSQL
integration and live KVM intake/cleanup tests establish the component boundaries.
The historical public Celery journey and its custody are recorded below. Fresh
full-suite and live evidence for a changed candidate belong to the PR.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture/reuse, security, QA/test-delta, product/operations, documentation; CI integrity if workflow changes become necessary.
- Human review focus: preparation before bytes versus authority, two-phase default ordering, exact material export custody, cancellation/deadline cleanup, and explicit deployment prerequisites.
- Plan review: required before implementation; the plan replay and implementation proof are recorded below.

## Review findings

Plan corrections address WS-EXEC-001-02-PLAN-01..04: safe inspect-then-workspace
custody, distinct Smol readiness cases, discriminating single-slot ordering and
closed preparation retry policy. Plan replay passed on `4b86aa3054d4fe79e92c7253665b9394fd36bbf8` before implementation.

## Reconciliation

This combined delivery includes deployment composition and the isolated public
PRE -> immutable Submission -> durable POST -> governed outcome drill, including
failure/retry, both policy branches and exact contribution facts. The intended
hosted Flow/AWS deployment remains a separate qualification.

### Public setup prerequisite reconciliation

The current setup owner requires an operator-published model profile and a
configured typed model session. The recorded public drill must provision those
through the existing public profile endpoint and reuse the canonical scripted
session environment helper before guide upload. This repair is limited to the
existing public proof helpers and focused tests; it must not stub model-session
admission or change production model, authorization or setup rules. Profile
publication failure must stop before guide upload. Verify that boundary with a
focused regression and repeat the full public journey. Architecture/reuse and
QA/product reviewers assess the fixture reconciliation. Recorded inference is
still a fixture and does not qualify live model execution inside Smol. The opt-in
execution observer must also forward the current typed port's `model_grant`
argument unchanged, including `None`; observation cannot alter adapter admission
or drop model custody. A focused forwarding regression protects that seam.

### Deadline classification repair

A live sleeping guest exposed a race between independent guardian cleanup and
process collection: observing child exit before checking the elapsed deadline
can mislabel expiry as runtime unavailability. The shared bounded collector must
check its original deadline before accepting exit/output, preserving independent
cleanup, cancellation and output limits. A focused already-reaped-child control
covers successful and failed exits before and after expiry; real KVM sleep and
the full public deadline/recovery journey must still pass. This remains within
the existing runtime scope and does not extend budgets or relax fault assertions.

## Intake implementation and historical owner-level proof

The typed adapter, closed guest worker and Rust prepared session connect PRE and
POST to canonical guest ZIP/default processing. Confirmed intake cleanup precedes
ordered project checks. An ART deadline after confirmed cleanup finalizes the
selected run as `deadline_exceeded`; an unconfirmed close retains unresolved lease
recovery. Caller cancellation drains both upload and preparation, and exact
committed reservation fields bind default evaluation before any project grant.

The maintained real-node intake matrix passes PRE/POST retained-reader export,
PRE default and ART grant issuance with host ZIP/default execution poisoned.
Abandoned upload, cancellation, idle deadline and malformed ZIP recover the
one-slot node. The streaming probe exposed and repaired misuse of the one-shot
project trailing-byte guard; its socket-pair regression now protects legitimate
pending ZIP input. The ART exporter accepts the retained directory-FD path while
preserving descriptor-relative child containment.

Real PostgreSQL/MinIO proof covers verified original material, immutable
Submission/lease custody, late authority and content drift, cancellation and
scratch revocation, durable worker materialization and public intake outcomes.
The combined 140-case EC2 run passes with database and MinIO cleanup confirmed.
These transaction fixtures explicitly inject an in-process intake fake; the
separate KVM matrix establishes the real adapter/guest boundary. Neither proof
is mislabeled as a public API -> Smol -> durable worker -> governed outcome drill.
The distinct combined public proof and deployment composition are recorded in
this change's deployment/public section below.

Implementation review findings repaired the exact default-binding assertion,
combined upload/preparation cancellation, and recoverable deadline finalization.
Hosted checks also exposed collection-time ZIP timestamps and an oversized test
module. Deterministic ZIP metadata/stable case IDs and a focused intake lifecycle
test module repair those defects without loosening the structural guard or test
selection. Exact architecture and CI inventories retain all prior assignments.
Required full hosted-suite evidence and reviewer receipts belong to the PR's
current candidate. The isolated public journey below does not establish the
intended hosted Flow/AWS deployment.

## Creation-failure classification

The trusted-intake caller preserves the runtime's typed cleanup classification.
A failure before lease creation or after confirmed cleanup returns the existing
recoverable `runtime_unavailable` response and releases admission. Uncertain
lease/guardian custody still retains admission until controller reconciliation.

## Deployment and public journey proof


Complete the user's authorized end-to-end goal. Boundaries 1 and 2 provide node
lifecycle and ART integration; neither synthetic node grants nor isolated ART
callbacks establish the public contributor journey. Preparation must overlap the
same authorized upload, clean up under failure, and preserve exact immutable
submission and ContributionRecord evidence through durable workers.

### Original public-proof starting point (historical)

At the original public-proof planning point, API and POST composition required the new typed intake configuration, while
hosted Compose/preflight and the opt-in public journey probe still construct a
Docker-only node. The existing public probe already exercises public project/guide
setup, upload feedback, immutable Submission, prefork Celery/Beat, known pre-effect routing
retry, true-policy review routing and false-policy shared acceptance/awards. Extend
that probe and deployment owners; do not create another lifecycle or business writer.

#### Prohibited changes

No policy, authorization, database schema, review/acceptance/award semantics or
artifact provider changes. No product row injection to manufacture submissions,
checks or acceptance. Existing documented infrastructure identity/bootstrap
fixtures are permitted and must be labeled. No host ZIP/default fallback,
checker network escape, ad hoc adapter factory, model gateway replacement or
claims of live external model invocation from recorded guide inference. Defects
in intake return to that ART owner for a focused regression and review.

### Plan

1. Reconcile boundary 2 repairs before using its candidate for final proof.
   Preserve its exact source/image/binary custody; build the project proof image
   from the same tree and provision its canonical cache entry.
2. Extend hosted composition with the three required intake settings and private
   socket mount. Preflight validates deployment-owned socket metadata, pinned
   image/config and Smol identity without widening credentials or permissions.
   Project Docker/runsc and Smol intake may be separate nodes; the live drill uses
   one Smol node for both, with one execution slot to expose ordering deadlocks.
3. Replace the public probe's hard-coded Docker construction with explicit
   provisioned-node input and typed capability readiness. Retain its existing
   settings parity, public guide/policy flow, immutable evidence and durable
   workers. Failure injection targets only the probe's exact owned resources.
4. Run on EC2 with isolated real PostgreSQL, MinIO (S3 protocol) and Redis plus
   API, Celery prefork and Beat. Use documented local Flow verifier fixtures and
   recorded guide inference; label these limits. This proves the self-hosted
   execution path, not native AWS S3 activation or production Flow certification.
5. Record public response IDs, ZIP and manifest hashes, selected PRE/POST attempt
   IDs, exact locked policy hashes, durable outbox retries and final facts. Read
   durable rows only to independently verify the public outcomes; create business
   state through existing public APIs/authorized durable owners.
6. Test cancellation/deadline and controller death with a separate in-flight
   attempt; confirm cleanup and recovery before a fresh request. Do not retry an
   unknown guest execution in-session or reuse a dirty VM. Preserve foreign
   resource controls.
7. Extend `RecordedGuideRuntime` explicitly for zero, one and two project PRE
   requirements. Select the recorded project variant from its exact public guide
   source, not by mutating approved policy rows. Preserve the existing one-image
   capability registration and one-binding journey. The two-binding compilation
   assigns distinct requirement IDs to the same registered PRE image; its check
   specification and fixture image distinguish those IDs. Public compilation,
   manager approvals and activation lock the resulting canonical order. The
   zero-binding variant compiles no project PRE requirement and retains default
   intake plus its required POST requirement. Extend the guide document/examples
   assertions per variant rather than disabling evidence checks.
8. Add named proof helpers `_assert_default_only_pre`,
   `_assert_ordered_pre_and_stop`, and `_assert_no_submission_after_intake_failure`.
   Read selected PRE evidence to verify zero/two binding counts and canonical
   order; a first-binding rejection marker makes the first fail while the second
   would pass if incorrectly invoked. Assert there is no second member/execution
   and no admission/Submission. A passing two-binding fixture must show both
   exact request identities after confirmed intake cleanup.

### Distinct failure and retry trials

Do not describe the existing `_wait_known_retry` as a runtime outage: it proves
known pre-effect completion-routing refusal while the lifecycle is non-live,
followed by the authorized live transition. Retain that proof separately.

- `_assert_prepare_retry_bound`: use the owned Smol executable shim/control
  launch injection before any guest input to fail known VM create/start launch
  attempts. The node retries only after exact lease cleanup, at most three
  attempts with the existing 100/200 ms backoff charged to the same deadline.
  Record launch counts, original deadline and absence of residual disks/cgroups;
  exhausted failure creates no selected completion, admission or Submission.
- `_assert_public_intake_recovery`: stop only the owned intake node before an
  authenticated upload, or inject a known project PRE execution outage after
  reservation. Assert public 503, exact selected terminal infrastructure code
  when execution is known (otherwise unresolved lease), and no admission or
  Submission. Same-key replay must preserve the owner's existing recovery
  contract; it must not silently rerun a terminal failure. Restart the node and
  use a fresh authorized request/key to repeat upload and checks successfully.
- `_assert_post_runtime_failure`: keep intake available and inject an outage in
  the owned project execution node after immutable Submission creation. Await
  the terminal `CheckerRun.infrastructure_failed` directly, not `_complete_post`
  (which requires completed work and a completion event). Assert no fabricated
  completion event, acceptance or contribution. Restore the node, then invoke
  the existing public Operator discovery/retry routes backed by `checker_retry.py`,
  with fresh authorization and a new request key; assert its exact next evaluation
  generation, durable dispatch, real worker success and single governed result.
  Discovery confirmed the public routes already exist in `checkers/router.py`;
  use that entry instead of calling the hidden owner directly. No new route is needed.
- `_assert_unknown_execution_cleanup`: kill only the owned controller after
  guest invocation begins, observe connection loss/unresolved status and no
  in-session retry. Verify guardian cleanup and startup reconciliation before a
  fresh request. Retain exact attempt/lease IDs and assert no duplicate business
  facts. Controller recovery must not reset the original attempt deadline.

Each trial uses uniquely owned unit/socket/cache/VM/DB resources. Evidence records
whether entry was public API, durable worker, or the existing public Operator
retry route; no direct SQL writes manufacture lifecycle outcomes.

### Acceptance criteria

- API and Celery resolve identical required intake identity/socket settings;
  missing/wrong runtime or image fails before unsafe processing. Release tests
  reject missing settings/mounts and preserve unrelated secrets/provider checks.
- A deliberately delayed authenticated ZIP request observes ready intake before
  upload ends; unauthorized upload observes no new lease. Disconnect releases
  exact owned VM/disk/cgroup within the original bound and creates no Submission.
- Invalid ZIP/default/project work returns actionable bounded intake feedback and
  creates no Submission; infrastructure outage is distinct and recoverable.
- Default-only and two canonically ordered project PRE bindings run on a one-slot
  node. Intake cleanup precedes the first project connection; failure stops the
  remaining bindings. A subsequent fresh upload repeats the whole authorized flow.
- A valid public request creates one immutable Submission with exact ZIP/manifest
  and locked-policy lineage, then real Celery performs POST through guest intake
  and the selected external execution adapter. No host ZIP/default execution.
- `human_review_required=true` retains review-pending routing without a fabricated
  Review/acceptance/contribution. `false` reaches the existing shared authorized
  FinalAcceptance and exact submitter ContributionRecord and conditional awards
  atomically, with no reviewer contribution. Duplicate delivery creates no new facts.
- Known infrastructure failure/retry, caller cancellation, deadline and controller
  restart preserve durable outcome distinctions and settle only owned resources.
- Final proof binds a clean source candidate, packaged image and runtime binaries;
  full required suite/checks and focused internal reviews pass before readiness.

### Risk and review routing

Risk L1. Required plan review before implementation, then architecture/reuse,
security, QA/test-delta, product/operations, documentation and CI integrity for
release/proof gates. Human focus: deployment authority, one-slot ordering,
public-to-durable custody, retry safety and exact contribution evidence.

### Evidence

The isolated EC2 public journey passes on real KVM, PostgreSQL, MinIO and Redis,
with the API, Celery prefork worker and Beat. It exercises original public guide
setup/approvals, authorized upload overlap and cancellation, zero/two project PRE
bindings, first-failure stop, immutable Submission, revision, launch retry/exhaustion,
controller death/epoch recovery and durable POST failure followed by public Operator
retry generation 2. Every recovery checks owned cleanup and preserved foreign
controls. Human review remains pending with no final facts; automatic acceptance
creates one FinalAcceptance, one submitter ContributionRecord and one 7 PTS award,
with no Review. Duplicate delivery and late authority revocation preserve those facts.
Database and MinIO cleanup complete. Source/image/binary identities and exact run
receipts remain in the PR evidence; no production deployment is inferred.

The public two-binding trial exposed ART's sequential grant-layout defect; its
repair and discriminating PRE/POST regressions belong to boundary 2. Review also
strengthened the proof itself: independently supplied node/binary custody, exact
controller kill and disk cleanup, explicit idle-node checks under optimized Python,
CI ownership of safety tests, one-slot enforcement, fixture-derived artifact hashes,
request-correlated execution counts, cancellation resource readback and per-machine
original retry leases. Retry wall-clock projections permit only the observed
one-millisecond flooring difference while remaining lifetimes must shrink; the
Rust operation retains one monotonic deadline. The timeout trial requires `deadline_exceeded` at the original
lease expiry, with no in-session retry. Required hosted checks and reviewer freshness
are reported against the final PR candidate, not stored as durable workflow state.

The 33 hosted configuration tests and focused negative fault-control tests preserve
existing release gates. The drill intentionally uses recorded guide inference and
a local Flow verifier fixture; MinIO establishes the S3 protocol, not native AWS
activation. Intended hosted deployment and actual external-model invocation remain
separate. No shared EC2 service or product business owner was changed.

## Interrupted export and cleanup precedence

An export failure immediately aborts its mixed framed/raw transport; later cleanup
cannot parse unread file bytes as a response. A selected-attempt deadline keeps
its unresolved outcome if cleanup also fails. Cleanup failure still supersedes
ordinary archive rejection, and caller cancellation retains its existing behavior.
The hosted intake health command uses only its cached pinned backend image.
