# ARCH-04B2 — Verified checker output custody

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: Hidden ART storage and flush-only verified binding of exact checker-run output, with production access unavailable until CHECKERS reservations and AUTH activation exist.

## Intent

Complete the next storage boundary on the path to a usable contributor journey:
claim -> upload ZIP -> pre-submit feedback or immutable Submission -> automatic
post-submit evaluation -> outcome. The first complete no-human-review journey must
include shared FinalAcceptance, the submitter ContributionRecord and applicable
policy awards before live human review/revision becomes a dependency. Human review
packet foundations may proceed independently in another worktree; shared acceptance
is one operation used by both triggers, never a second automated acceptance engine.
Contributor skip and assignment expiry remain deferred.

## Current behavior

Main `9c292100` includes merged ARCH-04B exact verified input and bounded scratch.
The output-store and output-binding capabilities begin as unused declarations;
this change gives them CHECKERS-owned consumer contracts and ART implementations. Generic ART preparation, quota admission, durable put,
unknown-outcome recovery and independent verification already exist. Checker
output admission still reads private CheckerRun rows from ART's repository.
Existing CHECKERS rows do not persist 04A request/generation/worker reservation
facts. Current structural checker definitions permit zero generated output bytes
and no required output roles. This change must not invent evaluator outputs or
claim the current structural catalogue supports them.

## Design and decisions

1. Replace the unused output/binding declarations with CHECKERS-owned consumer
   requests, results and ports in its public API; ART implements them through
   composition injection. The input-materialization port uses the same dependency
   direction. Delete the replaced declaration paths; no compatibility alias or
   second storage engine. A CHECKERS-owned
   public reservation-facts port supplies exact run/request/Submission/policy, worker-lease generation and
   owner-declared output-slot/budget facts. Each slot has a globally unique bounded
   key within its run, media type and byte limit. Its production implementation is explicitly
   unavailable until ARCH-04C; hidden proof uses a controlled owner fixture,
   clearly distinguished from live reservation/currentness proof.
2. The public store request contains selector plus byte source, never PREP or raw
   AuthorizationContext. ART action-specific preflight denies before protected reads, byte-source iteration, scratch or
   provider access. Exact reservation facts must match the complete validated
   evaluation request and output selector. Role/budget comes from CHECKERS's
   reservation, never arbitrary contributor input. No production log/output role is introduced. The current structural plan has
   zero slots; 04C must accept that exact empty output set. Controlled nonempty
   test slots prove storage mechanics only, not a live evaluator capability.
3. Reuse canonical bounded scratch to commit exact output bytes. Add a per-call
   byte ceiling bounded by the existing manager maximum; over-cap input stops
   before writing excess bytes and cleans the reservation. Re-resolve owner
   facts and authority in a short transaction before generic quota admission and
   durable intent. Charge deployment/project/task/fixed producer, not contributor.
   Bind exact evaluation/run/output identity into the existing put request digest;
   persist Submission identity/version and a narrow checker-request digest on that
   attempt, and verified receipt/put
   ancestry on the immutable checker binding. Do not copy the evaluation envelope
   or add a competing CHECKERS reservation store. This receipt is material lineage, never
   independent CHECKERS currentness or authorization.
   Operation identity remains (run, globally unique slot). The request digest
   binds evaluation request ID/hash/generation, run, immutable owner lineage,
   slot key/media/ceiling, commitment, namespace and quota scopes. It excludes
   volatile worker lease ID/generation: every store/replay/bind separately resolves
   and authorizes the active lease. A replacement worker recovers the same logical
   output/put; an old lease cannot publish. Changed immutable facts or bytes conflict.
4. Release transaction/locks/PREP before provider I/O. Reuse existing committed
   put, observation and verification operations. Unknown outcomes retain the
   original attempt; absent unreproducible bytes cannot be fabricated or
   regenerated. Always clean private scratch. A verified reference is returned
   only for the exact attempt/replica/independent verification receipt.
   `recover(selector)` retrieves the stable operation after a lost response without
   a byte source. It reuses observation and verification, never provider put or
   regeneration. `store` still commits supplied bytes and rejects changed replay
   content. The narrow checker-request digest permits recovery/binding comparisons
   without reconstructing historical quota configuration inside the full digest.
5. A separate flush-only binding participant runs inside the caller's transaction.
   Caller supplies fresh CHECKERS reservation/fence facts and exact authority
   before ART locks. Match persisted intent and full verified chain, then create
   or replay one immutable run/role binding. Changed bytes, foreign intent,
   incomplete verification, stale owner facts or late revoked authority deny.
   Authority custody is prepared before CHECKERS reservation/currentness locks,
   followed by ART scope/row locks. ART never locks CHECKERS/TASK privately.
   Verify using immutable terminal receipt ancestry or the verifier's compatible
   job -> replica -> attempt -> content lock order; do not introduce the inverse.
   Generic bindings receive checker-only put_attempt_id and verification_receipt_id.
   An INSERT guard verifies exact receipt -> job -> attempt -> replica/content
   ancestry, verified state and project/run/slot ownership. Seal terminal
   attempt/job facts and replica identity atomically with that binding; preserve
   mutable replica health. Reuse the existing binding immutability trigger; do not invent a common receipt FK across distinct
   direct-put and observation receipt tables. ARCH-04C later composes this participant
   with its final result and outbox; ARCH-04D owns live service activation.
6. Replace the raw-AuthorizationContext checker admission path with a mandatory
   action-specific authority participant and owner reservation facts. Default
   admission without that participant denies before mutation. Replace the affected
   private checker admission/recovery lookup with owner facts.
   Trace remaining consumers explicitly; preserve retained records. Do not rewrite
   unrelated owner behavior or add compatibility constructors.

## Bounded change

### Allowed

- `backend/app/interfaces/artifact_operations.py` output requests/results and ports.
- `backend/app/modules/artifacts/checker_outputs.py`,
  `backend/app/modules/artifacts/checker_output_custody.py` and
  `backend/app/modules/artifacts/checker_output_bindings.py` (new ART owners).
- `backend/app/modules/artifacts/preparation.py` for the bounded per-call cap.
- `backend/app/modules/artifacts/models.py`, `schemas.py`, `service.py`,
  `repository.py` only for affected output custody and traced lookup consumers.
  The separate Operator resource-to-project CHECKERS lookup remains explicitly
  outside this mutation boundary; it is not a second output admission path.
- `backend/app/modules/checkers/api/output_custody.py` (new closed owner facts),
  `backend/app/modules/checkers/api/__init__.py`; composition in existing
  `backend/app/adapters/artifacts/__init__.py`, `backend/app/adapters/checkers/`.
- One ART-owned migration `backend/alembic/versions/0007_checker_output_custody.py` after `0006_history_read_authority` for immutable exact
  output intent/binding custody; no CHECKERS run writer or retained-data deletion.
- New `backend/tests/test_checker_output_custody.py`,
  `backend/tests/test_checker_output_storage.py`,
  `backend/tests/test_artifact_admission_digest.py` for unaffected guide replay,
  `backend/tests/checker_output_custody_helpers.py`,
  `backend/tests/checker_output_admission_helpers.py`, and
  existing `test_artifact_admission.py`, `test_artifact_recovery.py`,
  `test_artifact_architecture.py`, `test_artifact_preparation.py`,
  `test_artifact_authorization.py`, `backend/tests/conftest.py` (exact migrated
  fingerprint and protected-table reset inventory), `backend/alembic/env.py`,
  `test_alembic.py`, `test_coverage_contract.py` for exact migration-head registration, module boundary
  tests and migration tests, including
  `backend/tests/authorization/submission_history/test_migration.py` for exact
  predecessor-schema restoration across the new dependent foreign key.
- Existing lane/ownership/module/test-structure inventories and their tests only
  to register changed owners and keep existing gates intact.
- This record, linked ARCH output skeleton, current ARCH/ART/AUTH/POL/CON navigation,
  `.commitrail/INDEX.md`, `README.md`, `docs/roadmap_status.md`, artifact/checker/data
  model specifications, authorization specification, operating manual and
  authorization custody page for affected claims.

### Not allowed

Public routes, live grants, checker reservation/result/currentness writers,
TASK transitions, policy/catalogue expansion, inference, reviewer workflows,
acceptance implementation, alternate scratch/store/factory, data deletion,
compatibility paths, CI weakening or contributor quota charges for system outputs.

## Acceptance criteria

- Default composition fails before any protected or external access.
- Controlled exact reservation plus real PostgreSQL/Local and MinIO storage proves
  preparation, exact byte commitment, independent verification and immutable binding.
- Valid foreign stored lineages and mixed reservation/intent/binding selectors deny;
  positive controls succeed. Requests cannot select a role or budget outside the
  owner-issued reservation. Invalid requests never invoke the byte source/provider.
- Same run/role/bytes replay produces the same intent and binding; changed request
  or bytes reject. Concurrent publication and caller rollback preserve one binding
  and no partially committed effect.
- Database rejects intent/binding identity mutation, mismatched stored ancestry,
  and subsequent changes to sealed verified ancestry, including concurrent writes
  under READ COMMITTED and REPEATABLE READ.
  Migration refuses retained checker attempts lacking provable evaluation custody;
  it never invents the missing checker-request digest or deletes retained data.
- Unknown put outcome resumes observation of the same intent without regenerating
  output; missing unreproducible bytes remain unavailable. Existing generic recovery
  proof is reused rather than copied.
- Quota/deadline/cancellation cleanup and fresh authority after I/O are demonstrated;
  independent sessions prove no row lock spans provider I/O.
- No claim of live CHECKERS request/lease custody: that remains ARCH-04C proof.

## Risk and review routing

- Risk class: L1 (untrusted bytes, immutable evidence, storage/schema boundary).
- Required reviewers: architecture/reuse, security, QA/test delta, docs/product;
  CI integrity for affected lane/inventory registrations.
- Human review focus: exact run/request/role binding, unavailable production boundary,
  shared storage reuse, retained evidence and automated acceptance sequencing.
- Plan review resolved the missing producer with an unavailable owner seam, not
  a new runtime fixture; current structural outputs remain empty. Replay binds
  immutable attempt facts while fresh authority fences the changing worker lease.

## Evidence

The focused proof lives in `test_checker_output_custody.py` and
`test_checker_output_storage.py`:

- Default composition denies before protected access; valid stored foreign and
  mixed selectors reject before source/provider use after two valid controls.
- Local/MinIO store -> independent verify -> binding preserves exact persisted
  identities; binding rollback and concurrent replay preserve one result.
- Lost acknowledgement uses typed observation and byte-free recovery;
  worker takeover preserves logical output identity and denies the old lease.
- Slot caps stop iteration and clean scratch; revocation during provider I/O
  denies the returned reference, with independent-session lock checks.
- Direct SQL rejects mixed binding ancestry and immutable intent changes;
  migration refuses retained output lacking provable request custody.

Affected admission/recovery tests retain quota, service-identity, relationship,
namespace precedence and transaction guarantees under the new closed request.
Existing preparation tests cover deadline, cancellation and aggregate quotas;
new per-slot cases extend that same canonical path.

Verification uses the existing isolated PostgreSQL/MinIO runner, Ruff,
structure/module-boundary validators, markdown links, stale wording,
Commitrail checks and complete hosted lanes. Exact command results and
review targets belong in the PR. Guard-removal probes must reach the behavioral
assertion after valid controls, not fail during fixture setup. Hidden controlled
reservation/action-authority fixtures prove ART mechanics only; actual CHECKERS
lease custody and AUTH activation remain subsequent work.

## Plan review disposition

The focused plan review found the original store PREP lifetime,
per-slot scratch ceiling, missing reservation producer, and binding ancestry
underspecified. The design above incorporates those repairs. The reviewed stable/volatile split keeps worker leases out of logical output
identity while authorizing the caller's exact claimed active lease on every phase.
Existing binding
immutability is reused; no generated-output catalogue expansion or duplicate
custody aggregate is authorized.

## Review findings

- Immutable binding custody must cover statement-level deletion as well as row
  mutation. Reuse the existing ART fact-mutation rejection function for a binding
  no-TRUNCATE trigger; prove direct and cascading truncation rejects and preserves
  a real verified binding. The canonical isolated test reset disables/restores
  this guard and pins the resulting schema fingerprint.
- Service-level binding proof must substitute valid foreign put/receipt identities
  after both valid controls, independently of the database insert guard. The
  requested-attempt filter removal must make the negative service test fail.
- Current authorization specifications must show delivered input/output custody,
  then ARCH-04C execution/results, then ARCH-04D activation. ARCH-04F gates
  remediation/public intake and enabling false, not the earlier true routing branch.
- Retained-data migration probes must remove the exact new dependent ART foreign
  key when reconstructing the predecessor checker schema and restore it after
  committed concurrency probes; no CASCADE shortcut or weakened assertion. The
  existing guide quota-reconciliation fixture supplies explicit null checker
  custody fields under the expanded internal admission facts; its rollback and
  configured-limit assertions remain intact.

## Reconciliation

- Current-source reconciliation: merged ARCH-04B on main; no overlapping open
  product PR. AUTH provisioning proof and deferred lease planning are separate.
- Next usable boundary: ARCH-04C durable execution/results, then exact AUTH and
  automatic routing; shared acceptance and compensation participants precede
  no-human-review activation; remediation and public intake complete the first
  contributor milestone before live human review/revision.
- Remaining risks: CHECKERS reservation producer and live authority deliberately
  absent; only controlled hidden storage proof is claimed by this child.

## External review repair scope

The output capability must have a typed acyclic consumer/implementation seam;
placing its declarations in shared `app.interfaces` does not remove the
ART-to-CHECKERS dependency. CHECKERS owns the consumed output and materialization
ports in its public API; ART implements them and composition injects them. Move
the existing ART materialization contract to that consumer API and delete its
old path. ARCH-04C imports its own consumer ports, never ART API/private owners.
The existing pre-submit archive-execution private ART dependency remains a
separately tracked consumer; it is not a new post-submit dependency or fallback. Replace that affected declaration path, update all
callers and boundary proof, and make ARCH-04C consume the declared seam without
importing ART implementation. No compatibility re-export is allowed.

Verified binding custody must survive subsequent SQL mutations, not merely pass
an insertion check. Protect the ancestry facts used by the inserted binding,
including put execution state and references, while preserving legitimate
unbound put/observation recovery. Prove post-bind mutations fail and leave the
binding and its exact chain unchanged; include the competing-transaction case.

Add focused service proofs for identical `store()` replay without another put
and cancellation while provider I/O is paused with scratch cleanup. Share the
canonical run/slot operation identity instead of rebuilding its hash. Reconcile
the current ARCH plan's stale missing-storage sentence. These are repairs within
the existing L1 boundary and require fresh architecture/reuse, security,
QA/test-delta, documentation/product and CI-integrity review. Existing prohibited
changes and human review focus remain unchanged. The affected owner API,
architecture boundary tests and ARCH-04C contract are included in allowed scope.

The ancestry repair seals the terminal attempt and verification job plus replica
identity in the successful binding transaction. A monotonic row-local seal is
needed because a transaction using an older PostgreSQL snapshot could miss a
newly inserted binding if protection relied only on cross-table existence checks.
Binding takes the existing job -> replica -> attempt -> content order with update
locks on the sealed ancestors, validates the exact chain, and sets seals atomically.
The attempt/job terminal facts and replica identity cannot change afterward;
replica health and availability remain operational facts that may change. Failed
or rolled-back publication must not leave seals behind. Real PostgreSQL proof
covers both READ COMMITTED and REPEATABLE READ interleavings, not only sequential
mutation. No separate custody aggregate or public capability is introduced.

Follow-up review identified two additional bounded repairs. The binding guard
must reject a null terminal verification result explicitly: SQL's nullable
comparison cannot establish verified ancestry. Direct-SQL proof supplies an
otherwise valid chain and checks rejection without a binding or seals. Checker
lineage fields belong only in the checker-output admission digest; unrelated
guide and submission producers retain their canonical digest inputs. Guide
replay must recover its existing attempt without a conflicting digest. Submission
bundle replay already returns through its owner replay port before this digest;
no submission replay failure is claimed. These changes add no compatibility
path and do not rewrite retained attempts.
