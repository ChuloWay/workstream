# WS-ART-001 — Immutable artifact storage

Current pre-review work follows the [cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
and the [capability ledger](../../../docs/roadmap_status.md).

- Disposition: Planned
- Intent: preserve exact artifact identity, verified bytes, provider-neutral
  storage, and bounded private processing scratch.
- Current boundary: ready-admission publication and hidden preparation,
  consumption, and binding dependencies are merged through ARCH-02H.
- Completed boundary: ARCH-04B hidden input materialization and hidden
  [ARCH-04B2 checker-output custody](../WS-ARCH-001/WS-ARCH-001-04B2.md).
  The CHECKERS zero-slot reservation reader is implemented; checker-output
  write/bind authority remains deny-only.
- Delivered dependent boundary: ARCH-04E1A route-neutral source facts retain the
  exact canonical material lineage supplied after
  [ARCH-04D2](../WS-ARCH-001/WS-ARCH-001-04D2.md), without a runtime reader,
  writer or published route. Output-file authority remains unavailable for the
  zero-output catalogue.
- Delivered contract: [ART-07A1](WS-ART-001-07A1.md) defines exact, metadata-only
  reviewer packet membership. REV-03B corrects its original `guide_binding_id`
  to live upload `ingest_id`; the completed ART record preserves the original
  delivery history. No alias, revived extraction writer or byte authority.
- Delivered storage: [REV-03B](../WS-REV-001/WS-REV-001-03B.md) freezes exact
  lease packets with normalized live guide ingests; no resolver or byte authority.
  [REV-04A](../WS-REV-001/WS-REV-001-04A.md) adds complete immutable Review, findings, resolutions and completed request storage; no decision runtime.
  [REV-04B](../WS-REV-001/WS-REV-001-04B.md) adds shared FinalAcceptance source
  storage, without AUTH receipt custody or runtime consumers.
- Next usable boundary: CON-07, the REV-12A/CON fence foundation and mandatory
  acceptance authority hardening. ARCH-04F remediation and public intake follow
  acceptance and routing composition.
- Governing sources: artifact specifications, `ArtifactStore`,
  `ArtifactScratchManager`, code, migrations, and artifact tests.
- Preserve: SHA-256/byte-count identity, reread verification, isolation,
  idempotency, and no local-filesystem provider coupling.

## Delivered

- Provider-neutral admission, put attempts, verification/publication,
  recovery, immutable guide binding/read, bounded extraction for supported
  formats, canonical manifests, and same-generation sufficiency are merged.
- Pre-submit planning/execution, project-policy continuation, durable put
  intent, ready-admission publication, contributor preparation, admission
  consumption, Submission creation, and final binding exist behind the current
  hidden route.

## Remaining v0.1 sequence

Follow the [current cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract).
ART retains the merged default-plus-project intake compiler/executor; POL-07
is a facade, not a replacement or second precheck run. New unified generations
must prove exact approved lineage at preparation, consumption and binding.

1. ARCH-04B hidden exact Submission materialization, ARCH-04B2 hidden output
   custody, ARCH-04C hidden durable execution, ARCH-04D2 fixed-service authority
   and ARCH-04E1A source-only material lineage are delivered.
2. ART-07A1 metadata-only membership types are delivered. REV-03B packet
   storage, REV-04A Review sources and REV-04B shared FinalAcceptance storage are
   delivered. CON-03C contribution/award storage is delivered. CON-07 participation, the shared fence and mandatory
   acceptance authority hardening precede acceptance/routing composition.
3. ARCH-04F owns checker-remediation resubmission using existing ART ports;
   later reviewer-requested revision remains a separate REV boundary. Add those dependencies before public Submission
   cutover.
4. Perform ARCH-02I only after those replacement paths exist; historical
   ART-05/06 and XINT-05 designs remain non-executable.

## Preserved history

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).
These verbatim records preserve completed work and original proposals; where
pending sequencing conflicts, the current dependency contract above governs.
