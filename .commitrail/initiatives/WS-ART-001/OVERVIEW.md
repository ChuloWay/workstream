# WS-ART-001 — Immutable artifact storage

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Intent: preserve exact artifact identity, verified bytes, provider-neutral
  storage, and bounded private processing scratch.
- Current boundary: ready-admission publication and hidden preparation,
  consumption, and binding dependencies are merged through ARCH-02H.
- Next usable boundary: exact post-submit materialization after executable
  unified guide/checker contracts; live cutover remains later.
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

1. Implement the ARCH-04 checker/post-submit materialization chain against the
   canonical checker contracts.
2. ARCH-04F owns checker-remediation resubmission using existing ART ports;
   later reviewer-requested revision remains a separate REV boundary. Add those dependencies before public Submission
   cutover.
3. Perform ARCH-02I only after those replacement paths exist; historical
   ART-05/06 and XINT-05 designs remain non-executable.
