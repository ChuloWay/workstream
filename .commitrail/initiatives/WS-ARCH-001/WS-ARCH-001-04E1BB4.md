# ARCH-04E1B-B4 — Bind Submission text to its checked packet

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: admission consumption and persisted Submission text must match the exact packet retained by pre-submission checking.

## Intent and discovery

Initial dispatch must use exactly the input that passed preparation. Plan review
found that TASK forwards no packet commitment to ART consumption: prepared summary
and attestation A can be replaced with B when creating a Submission. The existing
pre-submit evidence already stores their canonical packet hash. Enforce that
existing commitment before building dispatch on this boundary.

## Bounded design

- Forward the canonical hash of the actual creation request's summary and
  contributor attestation through existing TASK and ART consumption requests.
  Share the existing packet hash construction; no second packet format.
- ART compares it with locked immutable pre-submit evidence before consumed
  replay or new binding/consumption. Mismatch gives the existing concealed
  unavailable error and no mutation or final binding authorization.
- A deferred PostgreSQL guard reads the final Submission row and compares its
  summary/worker_attestation with its admission's retained evidence packet hash.
  Support existing insert-unbound then bind in the same transaction. Once bound,
  retain the existing guard against clearing or replacing the admission/binding/content triple. Reuse the
  existing canonical SQL JSON function and qualify every protected reference with
  a pinned safe search_path. Existing upstream hash/link immutability remains.
- Preserve retained data unchanged at upgrade. Unbound stored rows gain no
  admission or dispatch eligibility. Newly bound/changed rows must satisfy the
  guard; no optional current path, fabricated hash, compatibility API or backfill.

## Allowed files

TASK submission command contract/composition and adapters/tasks; ART consumption
contract/service, packet hashing caller and directly affected exports; CHECKERS public packet value helper; one migration after 0021, test_alembic and schema
fingerprint; focused binding/composition and real PostgreSQL submission tests plus
their affected canonical fixtures; exact lane/ownership registration; this record,
parent 04E contract and affected ARCH/AUTH/POL current navigation, README,
TASK/ART specifications and roadmap.

## Prohibited changes

No dispatch reservation/event/handler, capacity-limit changes, new receipt store,
AUTH replay activation, routing/acceptance/review effects, public route, claim
expiry, provider read, retained data rewrite/delete, compatibility path, weakened
CI or skipped tests. Preserve unrelated CLI work.

## Acceptance and proof

1. Exact prepared packet creates a Submission through real hidden TASK/ART/AUTH.
   Changing only summary or only attestation rejects and rolls back Submission,
   admission consumption, binding and staged AUTH evidence. No provider reread.
2. Exact ART consumption replay remains valid; a changed packet digest on a
   consumed admission rejects before binding authorization or mutation.
3. PostgreSQL permits valid insert-unbound/update-bind in one transaction; rejects
   changed packet fields, wrong packet on first binding and clearing/substituting
   bound lineage. Verify persisted state after rollback. Existing upstream
   evidence-hash/admission-link immutability tests remain valid.
4. Upgrade preserves existing rows unchanged. Canonical hash parity includes
   quotes, backslashes and supported packet text. Tests target each independent
   field; remove the service/SQL predicate and prove the intended assertions fail.
5. Run focused pure/PostgreSQL tests, Ruff, boundaries, lane/ownership inventory,
   stale wording/link/Commitrail checks and full hosted completeness. Coverage is
   diagnostic. Tests protect outcomes; no mirrored implementation-only cases.

## Risk and reviewers

L1. Architecture/security/reuse and QA/test-delta plan review before code.
Implementation reviews additionally include CI-integrity and docs/product ops.
Human focus: exact pre-check-to-Submission input custody, rejection before effects,
immutable bound lineage, caller rollback, retained-data preservation.

## Next dependency

Initial Submission/dispatch remains next after capacity and replay reconciliation.
Discovery established three explicit obligations for that transaction: retain
exact creation/binding AUTH receipts; validate the same bounded checker request
before ready admission and at dispatch; resolve same-admission replay under fresh
AUTH after TASK reaches evaluation_pending without replacing original identities.
The current creation-context validator intentionally permits only in_progress or
needs_revision, so broadening it is not a replay design. Both true review admission
and false shared acceptance remain in the parent plan. Worker activation,
remediation and public intake follow; contributor claim expiry remains deferred.

## Plan review outcome

Architecture/security and QA found the original atomic dispatch proposal too early:
packet substitution is currently possible, creation replay rejects post-creation
TASK state, and ready ZIP capacities exceed CHECKERS inputs. This chunk repairs
only the first concrete boundary. Both plan reviews found it feasible. Reuse
`protect_submission_contribution_stamp` for once-bound identity and existing ART
immutable evidence/admission guards; do not duplicate them. The real test keeps
preparation artifacts/evidence intact while proving creation-side rollback.
