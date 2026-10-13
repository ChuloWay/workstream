# WS-ART-001 — Immutable artifact storage

Current pre-review work follows the [cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
and the [capability ledger](../../../docs/roadmap_status.md).

- Disposition: Planned
- Intent: preserve exact artifact identity, verified bytes, provider-neutral
  storage, and bounded private processing scratch.
- Current boundary: ready-admission publication, public ZIP preparation and
  admission-backed Submission creation are delivered through ARCH-02I-B; the
  underlying ART consumption and binding dependencies remain the single writer.
- Completed boundary: ARCH-04B hidden input materialization and hidden
  [ARCH-04B2 checker-output custody](../WS-ARCH-001/WS-ARCH-001-04B2.md).
  The CHECKERS zero-slot reservation reader is implemented; checker-output
  write/bind authority remains deny-only.
- Delivered dependent boundary: ARCH-04E1A route-neutral source facts retain the
  exact canonical material lineage supplied after
  [ARCH-04D2](../WS-ARCH-001/WS-ARCH-001-04D2.md), without a runtime reader,
  writer or published route. Output-file authority remains unavailable for the
  zero-output catalogue.
- Delivered routing dependency: [ARCH-04F2](../WS-ARCH-001/WS-ARCH-001-04F2.md)
  routes the exact current contributor-correctable result through existing
  TASK/AUTH owners under either policy mode, with no new ART write or REV/CON
  effect.
- Delivered replacement dependency: [ARCH-04F3](../WS-ARCH-001/WS-ARCH-001-04F3.md)
  reuses full ART intake, verification and admission for a changed ZIP with the
  exact current authorized checker-remediation cause. TASK creates the successor
  Submission and dispatch through its canonical atomic writer; prior evidence
  remains immutable.
- Delivered contract: [ART-07A1](WS-ART-001-07A1.md) defines exact, metadata-only
  reviewer packet membership. REV-03B corrects its original `guide_binding_id`
  to live upload `ingest_id`; the completed ART record preserves the original
  delivery history. No alias, revived extraction writer or byte authority.
- Delivered storage: [REV-03B](../WS-REV-001/WS-REV-001-03B.md) freezes exact
  lease packets with normalized live guide ingests; no resolver or byte authority.
  [REV-04A](../WS-REV-001/WS-REV-001-04A.md) adds complete immutable Review, findings, resolutions and completed request storage; no decision runtime.
  [REV-04B](../WS-REV-001/WS-REV-001-04B.md) adds shared FinalAcceptance source
  storage, without AUTH receipt custody or runtime consumers.
- Delivered public boundary: ARCH-02I-B exposes the canonical admission-backed
  initial and exact checker-remediation Submission entry. ARCH-04E3-B admits
  supported false guides without changing ART custody.
- Next usable boundary: first-layer public/worker drill with exact ART bytes and
  contribution evidence. A setup-fault hold is later safety work.
- Governing sources: artifact specifications, `ArtifactStore`,
  `ArtifactScratchManager`, code, migrations, and artifact tests.
- Preserve: SHA-256/byte-count identity, reread verification, isolation,
  idempotency, and no local-filesystem provider coupling.

REV-12A1 supplies the original disabled controller/fence foundation. REV-12A4A,
04E2-B and CON-07 now supply hidden scoped lifecycle control, exact acceptance
source custody and CON participation. ARCH-04E3-B supports false-guide activation; new false/pass effects still
require an Operator-authorized LIVE REV generation.

This is delivery priority, not a prerequisite of true human admission. Both
hidden success branches have 04E1B request/source custody, exact AUTH 04E2
outcomes and B8 completion delivery; 04F2 adds the policy-independent failure
handoff. PILOT-04 selected production registration is delivered. True routing has no CON-07/shared-acceptance
prerequisite; false routing does. Human final acceptance later uses the same
authorized shared acceptance/CON operation.

## Delivered

- Provider-neutral admission, put attempts, verification/publication,
  recovery, immutable guide binding/read, bounded extraction for supported
  formats, canonical manifests, and same-generation sufficiency are merged.
- Pre-submit planning/execution, project-policy continuation, durable put
  intent, ready-admission publication, contributor preparation, admission
  consumption, Submission creation, and final binding are exposed through the
  public ARCH-02I-B entry for initial work and checker remediation.

## Remaining v0.1 sequence

Follow the [current cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract).
ART retains the merged default-plus-project intake compiler/executor; POL-07
is a facade, not a replacement or second precheck run. New unified generations
must prove exact approved lineage at preparation, consumption and binding.

1. ARCH-04B hidden exact Submission materialization, ARCH-04B2 hidden output
   custody, ARCH-04C hidden durable execution, ARCH-04D2 fixed-service authority
   and ARCH-04E1A source-only material lineage are delivered.
2. ART-07A1 metadata-only membership types, REV packet/Review/FinalAcceptance
   storage, CON contribution/award storage and participation, exact routing AUTH,
   B8 completion delivery and the 04F2 hidden remediation handoff are delivered.
3. ARCH-04F3 supplies exact-cause checker-remediation resubmission using
   existing ART ports. 04F4 adds hidden Operator retry through existing CHECKERS custody without changing ART bindings. A manager-visible setup-fault hold is later safety work because no current
   production result classifies to `task_setup_blocked`. Later reviewer-requested
   revision is a separate REV boundary. Submitted-task rule changes remain deferred.
4. ARCH-02I-B public admission-backed entry is delivered; prove the complete
   public/worker journey next. Historical ART-05/06 and XINT-05 designs remain
   non-executable.

## Preserved history

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).
These verbatim records preserve completed work and original proposals; where
pending sequencing conflicts, the current dependency contract above governs.
