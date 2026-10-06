# ARCH-04E1B-B3 — Retain verified ZIP metadata for initial dispatch

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: ART retains the canonical inspected submission manifest in immutable pre-submit evidence and returns exact detached file metadata through admission consumption, without another provider read.

## Intent

Allow the next initial-dispatch participant to build its checker request from
verified durable facts. File bytes remain in object storage; PostgreSQL retains
bounded metadata, not extracted file content.

## Current behavior

B2 prepares exact completed routing sources. Initial dispatch remains absent.
ART builds `SubmissionManifest` from inspected ZIP bytes, but persists only its
hash and identity. `PreSubmitExecutionAttempt.request_json` does not retain
members. CHECKERS requires those members and later compares them with the
materialized ZIP. Tests currently reconstruct that input independently.
A standalone routing-source writer is rejected: source publication belongs to
the first exact authorized atomic consequence at 04E2-B.

## Bounded change

### Allowed

ART `submission_archive.py`, `submission_manifest.py`, `pre_submit_evidence.py`, `pre_submit_attempts.py`,
`submission_materialization.py`, `submission_admission.py`, `submission_bindings.py`,
`post_submit_selection.py`, `models.py`, `api/submission_admission.py` and affected
exports/adapters; one Alembic migration after 0020, `backend/alembic/env.py` and
`backend/tests/test_alembic.py`, canonical schema fingerprint in `backend/tests/conftest.py`, and explicit predecessor fixture helpers in `backend/tests/migration_fixtures.py`; directly affected evidence,
admission, replay and migration tests/fixtures; exact lane/ownership registration;
this record, parent 04E contract and affected ARCH navigation, README, roadmap and ART/TASK specifications.

### Not allowed

No file-content persistence, provider read at consumption, new storage subsystem,
routing source INSERT, live handler registration, AUTH activation, TASK status
transition, REV/CON effect, public route, compatibility path, invented retained
metadata, data deletion, test skipping or CI gate weakening.

## Design and decisions

1. Carry the already inspected `SubmissionManifest` into evidence persistence.
   Reuse its canonical body and existing semantic hash; store the body exactly
   once on `PreSubmitEvidenceSet`, alongside the existing immutable commitment.
2. Validate closed entry shape, canonical ordering/uniqueness, typed file versus
   directory fields, counts and hash on persistence and recovery. Preserve all
   supported archive entries; do not truncate to CHECKERS' smaller request limit.
3. Make the new metadata mandatory for newly created evidence and independently
   enforce its hash binding and immutability in PostgreSQL. Migration retains existing rows unchanged, with null metadata representing
   missing historical evidence. Every new INSERT requires the body; current
   consumption/replay rejects missing metadata without a fallback read or
   invented backfill. This nullable retained-data fact is not an optional runtime
   path. Prove upgrade preservation and unavailable consumption for those rows.
4. Admission consumption validates this metadata together with existing ART
   lineage and returns a detached immutable file projection plus archive/hash
   facts. Only consumed success/replay includes material; the existing stale result
   includes none. Existing authorization and stale/consumed semantics remain intact;
   metadata does not confer admission eligibility or feature authority.
5. Exact replay uses the retained metadata and verifies its commitment. No
   fallback ZIP read, optional metadata path or second manifest implementation.

## Acceptance criteria

- A real ZIP preparation persists exactly its inspected canonical body; ready
  admission consumption and exact replay return the same file metadata/hash/size.
- Changed or missing metadata fails before binding/dispatch use; independent
  PostgreSQL tests reject mismatched body/hash and retained-row mutation.
- Failed persistence rolls back evidence/admission effects; root caller owns
  consumption transaction and rollback.
- Existing exact evidence/admission ownership checks remain intact. Substituted
  manifest bodies reject before binding, and database immutability prevents
  replacing the metadata of retained evidence.
- Upgrade preserves existing evidence without rewriting it; missing historical
  metadata fails closed on consumption/replay, while new null-body INSERTs deny.
- Provider-call proof shows consumption/replay adds no object reads.
- No live dispatch, routing, acceptance or public intake claim is introduced.

## Risk and review routing

Risk: L1. Focused architecture/reuse, security, QA/test-delta, CI integrity and
documentation/product-operations review. Human focus: exact bytes-to-metadata
custody, no private file content in PostgreSQL, immutable replay and safe migration.

## Evidence

Use existing real preparation/admission fixtures, PostgreSQL direct constraint
and upgrade-preservation tests, pure canonical-shape tests, affected owner
boundaries and lane inventory. Run Ruff, stale wording, links, Commitrail and
full hosted CI. New tests must isolate each named guard with a valid control;
retain existing required tests and distinguish mechanical custody from authority.

## Review findings

Plan discovery found a real production input gap, not a need for another
routing-source store. ART defaults to 2,000 ZIP entries while CHECKERS limits
its request manifest to 1,024 and its envelope to 1 MiB. This change preserves
all metadata. Initial dispatch must reconcile those existing limits before
claiming that every admitted ZIP can be scheduled; no silent truncation.

## Reconciliation

Current main `c7f91ac2` includes B2 and CLI-05. CLI-06 is independently open.
Next: initial submission/dispatch transaction using these facts and exact
creation/binding receipt custody, then remaining routing handlers, exact AUTH
and database/effect closure, live composition, remediation and public intake.

Plan review requires consumed-only material projection and explicit retention of
pre-change evidence without granting it current dispatch eligibility. Reuse the
existing immutable-row guard and SQL canonical JSON function; prove Unicode hash
parity. No retained row is rewritten or discarded. TASK forwarding of the new ART
metadata is explicitly deferred to initial dispatch; its existing adapter stays
binding/content-only in this change. Binding and attempt test doubles must gain
valid manifest facts so existing negative assertions still reach their guards.

The existing attempt request has a 32 KiB cap, so it cannot retain all supported
manifest metadata without widening reservation limits. Completed evidence remains
the single owner. Historical migration tests temporarily provide the new column
only while current ART seeds real rows, then restore and assert the predecessor
column set and retained IDs before testing any migration. Production has no
schema-detection branch.

Review refinement: recovered paths share ART's inspector rules, with SQL enforcing
the same canonical segment/NFC constraints and the supported 4,096-byte/256-depth
ceiling. New metadata is required by consumption and attempt replay. Existing
post-submit material selection continues to validate its original exact immutable
ART lineage and inspected bytes; it does not consume the new file projection and
has no schema-specific branch or fallback. No old admission can create a new
consumption result without the metadata.
