# POL-04B — One live unified guide setup attempt

- Initiative: WS-POL-003
- Durable disposition: Planned
- Intended merge outcome: explicit Project Manager setup requests use one unified
  compilation attempt and the existing authorized projections and finalizer.

## Current baseline and scoped replacement

PR #390 consolidated the initial v0.1 post-submit contract. Consume its single
public CHECKERS catalogue and canonical configuration validator. No parallel
schemas, compatibility readers, or old inference methods remain in this scope.
Preserve business policy versions, locked lineage and retained evidence/data.
Remove obsolete tests only when their behavior is superseded; retain or replace
authorization, atomicity, material-custody and lifecycle regression protection.
Repository-wide cleanup is parked, not a prerequisite.

## Intent and current behavior

One guide setup proposes both the pre-submission intake policy and the separate
post-submission evaluation policy. Their approvals remain separate later work.
ARCH-04A supplies the canonical post-submission catalogue. The existing
`guide_compilation` services already own attempt fencing, accepted-result
persistence, component projection, and atomic finalization. HTTP and Celery
still reach the earlier separate inference methods.

## Bounded change

Allowed: PROJECTS guide setup request/orchestration/queue and route composition;
composition-root wiring of existing AUTH request/execute, projection, and
finalization ports; canonical CHECKERS capability projection wiring; existing
ART verified preparation continuation where needed to finish verified preparation without
automatic inference dispatch; focused backend tests and additive test/ownership catalogues;
related specifications, roadmap, and current initiative navigation.

Prohibited: new authorization permissions, rewritten compilation/projection or
finalization state machines, new completion receipts, effective-policy mutation,
approval activation, canonical post-policy projection, checker execution,
automatic unified inference after ingestion, additional provider attempts or
compatibility fallbacks. Historical sparse catalogues are never enriched.

## Implementation plan

1. Reconcile live request/generation custody and queued source shape with the
   existing finalizer. Preserve verified ART preparation; require explicit PM
   authority before unified inference. Remove superseded task registrations and inference deliveries.
   Existing source-snapshot creation supplies the setup generation when setup
   preparation is configured on. ART preparation stops before inference dispatch.
   An explicit request selects that exact prepared generation; absent or incomplete
   material is a bounded not-ready result. Do not mint preparation authority or
   another generation from a compilation request.
2. Add a bounded request/recovery entry using canonical source and capability
   snapshots. Pin immutable attempt facts; replay the same operation and expose
   provider uncertainty without another invocation.
   Publish only after request custody commits, using the existing deterministic
   setup task identity and dispatch claim. Keep setup queued/queued throughout
   execution; attempt custody owns progress. A current PM authorization check
   precedes every request/recovery response, including completed replay.
3. Compose the existing executor, separate fresh projection authority for each
   component, and existing finalizer. Recovery after partial persistence resumes
   only those deterministic operations. Completed replay returns canonical output.
4. Verify public API/worker reachability, real PostgreSQL authority and atomicity,
   catalogue parity, one-attempt concurrency, and invalid/uncertain outcomes.
5. Update current capability/navigation and prepare one PR with final-head hosted
   evidence and focused internal reviews.

Request replay revalidates current PM authority inside the existing request
service transaction, including concurrency recovery, while AUTH actor/link/grant
locks remain held through receipt classification. Extend the existing typed
AUTH request port with replay validation that closes its fresh handle without
creating another request event. Remove the draft out-of-transaction precheck.
Execution facts, hashes, and predecessor selectors come from server-owned rows;
the HTTP caller supplies only exact lineage selectors and an idempotency key.

Primary implementation paths: `backend/app/modules/projects/guide_compilation/context.py`,
`request.py`, `live.py`, and `live_contracts.py`; `backend/app/api/routes/project_guide_setup.py`,
`backend/app/api/deps/project_guide_setup.py`, `backend/app/api/router.py`;
`backend/app/workers/project_guide_setup.py`, existing
`backend/app/workers/project_setup.py`; PROJECTS `setup_queue.py`,
`guide_setup_continuation.py`, and `router.py`; `backend/app/workers/celery_app.py`
only for explicit task registration. Canonical
capability construction belongs in composition, not PROJECTS registry imports.

Focused tests belong under `backend/tests/projects/guide_compilation/live/`:
`test_request.py`, `test_orchestration.py`, `test_queue.py`, `test_reachability.py`,
`test_postgresql.py`, and `support.py`. Adjust only affected existing setup-route,
worker, hidden-boundary, lane, and ownership assertions in `test_projects.py`,
`test_guide_setup.py`, guide compilation call-graph tests,
`backend/scripts/test_lane_catalogue.py`, its ownership tests,
`backend/scripts/behavior_ownership.py`, and
`.ci/behavior-ownership/partition.v1.json`. Documentation: this record, adopted
04B contract, POL/ARCH overview and dependency plan, `.commitrail/INDEX.md`,
`docs/roadmap_status.md`, and `docs/spec_chunk_3_project_guide_foundation.md`.

Operation and durable request IDs use distinct UUID5 domains bound to the
canonical actor ID and client idempotency key; middleware request IDs are only
transport correlation. Existing request custody is loaded first on recovery,
so its immutable catalogue/context facts are never rebuilt against a new
deployment catalogue. Different lineage with the same key conflicts. Responses
retain existing compilation classifications (`compilation_reserved`,
`provider_outcome_unresolved`, `provider_result_accepted_not_persisted`,
`compilation_persisted`, `compilation_invalid_terminal`) plus an optional existing
finalization receipt and bounded dispatch status (`queued`, `enqueue_failed`,
`not_required`). No raw provider result or authority handle crosses HTTP.

Worker ordering: existing exact finalization -> authorized finalizer replay;
otherwise require queued/queued and exact deterministic task identity -> existing
executor -> for persisted results, sufficiency projection -> artifact projection
only for ready outcomes -> finalizer. Unknown/invalid outcomes never project.
An early dispatch-pending delivery raises a typed transient result and the Celery task retries with bounded delay; it is never acknowledged as successful lost work. Permanent stale states fail closed without retries or model I/O. Queue payload is attempt ID only.
Remove automatic and acknowledgement inference redispatch. Physically remove the
old pre/post setup task functions, their queue functions and the three runtime
methods/prompts. Trace PROJECTS sufficiency/submission-policy mutation services,
post-policy derivation and their routes: remove superseded inference operations
and consumers while retaining independent manual correction/approval operations
and their authorization/lineage guards. Later approval chunks own the integration
of finalized unified proposals; do not manufacture a second setup generation or
reopen a finalized row to keep an obsolete route alive.

Composition obtains the installed post catalogue through the CHECKERS public
`build_post_submit_catalogue` API. PROJECTS uses the single
`PostSubmissionCapabilityProjection` and canonical configuration validator.
Pre-submission intake capabilities keep their separate CHECKERS-owned catalogue;
trace their projection and active processor before removing any shared code.
Extend affected allowed paths to `interfaces/project_agents.py`, the project-agent
adapter, PROJECTS sufficiency/submission-policy mutation services and routers,
old setup worker/queue, and affected consumer tests/scripts. Remove dead result
schemas only after checking deterministic projections and manual policy owners.
No retained database rows or required evidence columns are deleted.

## Acceptance criteria

- Only `compile_project_guide` is reachable for live inference; both policy
  proposal sections are validated and persisted in its complete result.
- Canonical CHECKERS-owned metadata and configuration validation are reused;
  unavailable, altered, or stale capabilities fail closed.
- Each component consumes its own fresh action-bound PREP; ready outcomes project
  sufficiency and artifact policy, blocked outcomes project sufficiency only.
- Existing finalization closes the exact generation atomically. No downstream
  continuation reopens a finalized setup row.
- Exact complete replay invokes no provider; duplicate delivery cannot create a
  second attempt. Unknown provider outcomes remain explicitly unresolved.
- Complete blocked replay reaches the existing finalizer before the executor's
  active-lineage loader; a finalized blocked row cannot be treated as queued work.
- A delivery racing the dispatch-pending/queued transition cannot call the provider
  before the required queued source state is established.
- Unauthorized/foreign/stale requests cannot disclose compilation material or
  enqueue inference; queue publication follows committed request custody.

## Risk, verification, and review

Risk: L1, bounded workflow and authorization composition. Required tracks:
architecture/reuse, security, QA/test delta, product/operations/documentation;
CI integrity for additive hosted test ownership changes. Human focus: one-call
cutover, current PM authority on recovery, immutable finalization, and distinct
pre/post approval boundaries.

Focused deterministic tests and lint run locally. Full backend, real PostgreSQL,
Celery/API integration, concurrency, and coverage run hosted on the constrained
workstation's established verification path. Negative cases must supply valid
preceding fields and prove the intended guard; mutation probes test critical
one-attempt/replay assertions. Check links and stale current wording.

Planned discriminating integration cases: ready and blocked complete setup with
real request/projection/finalization authority; revoked PM exact replay; foreign
project/guide/setup substitution; ART material not ready; stale catalogue and
malformed or obsolete context; broker failure followed by same-key dispatch; delivery
before queued state; concurrent duplicate deliveries; provider timeout followed by
recovery with zero additional calls; failure after accepted persistence or either
projection followed by deterministic completion; finalized ready and blocked
replay preserving row/output identities; static absence of superseded runtime methods and task registrations, plus
HTTP, ingestion callback, and current worker reachability. These are
future tests, not executed evidence.

## Reconciliation

Base includes merged ARCH-04A catalogue/conformance and AUTH-12B2 finalization.
The selected next boundary after this chunk remains POL-05A, AUTH-12F4, POL-05B,
then POL-06A, AUTH-12G, POL-06B, and POL-07. CP06/CP07 follow that selected sequence.
Implementation feasibility review must resolve request/generation custody before
the live wiring is written; this is review evidence, not another permission gate.

## Plan-review refinements

Explicit additional allowed files: PROJECTS `service.py`, `repository.py` for
dead inference queries, `schemas.py` only for obsolete inference-only schemas;
`authorization/api/project_guide_compilation.py` and
`authorization/guide_compilation.py` for same-transaction replay admission;
existing guide-compilation `service.py` and direct AUTH/request tests. No new
permission, action, fixed-service grant or audit bypass is introduced.

Remove the old post-policy correction route/service, whose sole outcome is
another model call. Retain independent policy read/approval operations and their
guards; existing submission-policy approval and activation must reject unified
compilation projections until POL-05 provides exact downstream custody.
Remove obsolete agent-only provenance branches without permitting other unknown
policy provenance. Preserve required current manual policy paths and canonical
policy validation consumed by unified projections. AUTH's existing closed
sufficiency/derivation action identifiers and persisted audit/resource schemas
remain shared consumers pending their owner reconciliation; no callable old
inference route or runtime implementation is retained for them.

The existing active CHECKERS pre-submission processor and catalogue remain the
intake owner. Setup reads that catalogue's immutable capability projection, not
a second checker implementation. Material schemas remain shared ART/PROJECTS
inputs. All superseded runtime methods, prompts, service inference operations,
queue functions, registered tasks and their preservation-only tests are removed.
Test replacements must cover current material custody, manager revocation,
replay, one-attempt dispatch, no-write denials and immutable finalization.
