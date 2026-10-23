# WS-EXEC-001-03 — Deployment and public microVM journey

- Initiative: WS-EXEC-001
- Durable disposition: Planned
- Intended merge outcome: deploy the typed intake/execution capabilities coherently and prove public upload through durable governed outcome on an isolated self-hosted Smol node.

## Intent

Complete the user's authorized end-to-end goal. Boundaries 1 and 2 provide node
lifecycle and ART integration; neither synthetic node grants nor isolated ART
callbacks establish the public contributor journey. Preparation must overlap the
same authorized upload, clean up under failure, and preserve exact immutable
submission and ContributionRecord evidence through durable workers.

## Current owners and concrete gap

Merged main remains `733c752f7c1ecbb74615d42b747dfbda8ff72df5` (verified remotely).
The stacked intake candidate is `2c9c6685fd3de12d2976504fe0f9e0b1bc4bf3e5`.
Its API and POST composition require the new typed intake configuration, while
hosted Compose/preflight and the opt-in public journey probe still construct a
Docker-only node. The existing public probe already exercises public project/guide
setup, upload feedback, immutable Submission, prefork Celery/Beat, infrastructure
retry, true-policy review routing and false-policy shared acceptance/awards. Extend
that probe and deployment owners; do not create another lifecycle or business writer.

## Bounded change

### Allowed files and responsibilities

- `deploy/hosted/compose.yml`, `release.env.example`, `preflight.py` and their
  existing `scripts/test_hosted_release_config.py` tests: require pinned intake
  identities and mount its private Unix socket into API/Celery processes;
  retain existing artifact-store, secrets and project execution boundaries.
- `external_checkers/deploy/`, `external_checkers/README.md`: concrete Smol
  provisioning/startup/recovery instructions and exact source/cache custody.
- `experiments/pilot04_external_checker_runtime/run_public_journey_probe.py`,
  its existing shared probe helpers, Dockerfile/checker proof fixture and README:
  accept a provisioned node/config rather than inventing a hard-coded Docker
  runtime; verify both typed health identities and use the existing public flow.
  Add only focused proof helpers needed for upload overlap/cancel and exact
  runtime/cleanup observations.
- Focused existing release/probe tests, docs describing deployment prerequisites,
  roadmap, initiative records and index reconciliation.
- Disposable EC2 resources in a uniquely owned directory/unit/container/database/
  port namespace; no shared service restart, prune, volume deletion or edits to
  `/etc/workstream/` or the other agent's protected services.

### Prohibited changes

No policy, authorization, database schema, review/acceptance/award semantics or
artifact provider changes. No product row injection to manufacture submissions,
checks or acceptance. Existing documented infrastructure identity/bootstrap
fixtures are permitted and must be labeled. No host ZIP/default fallback,
checker network escape, ad hoc adapter factory, model gateway replacement or
claims of live external model invocation from recorded guide inference. Defects
in boundary 2 return to that owner/PR for a focused regression and review.

## Plan

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

## Acceptance criteria

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

## Risk and review routing

Risk L1. Required plan review before implementation, then architecture/reuse,
security, QA/test-delta, product/operations, documentation and CI integrity for
release/proof gates. Human focus: deployment authority, one-slot ordering,
public-to-durable custody, retry safety and exact contribution evidence.

## Evidence

Future proof: existing hosted-release tests extended with missing-intake mutants;
existing public journey probe extended with explicit node/intake and bounded
upload/cancel observations; real EC2 KVM/PG/MinIO/Redis execution, exact durable
readback and source/image custody. No proof is claimed by this plan. Boundary 2
reviews/integration are still active; this is planning for the already-authorized
final boundary, not a completed capability or merge permission.
