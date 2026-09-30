# Chunk Contract: WS-ARCH-001-04D AUTH Post-Submit Activation

Status: non-executable planning skeleton after exact 04B/04C manifests.
Risk: L1. Outcome: ARCH-04D activates exact fixed-service materialization,
checker-output, evaluator execution and finalization boundaries, replacing
the historical XINT-06B/broad AUTH-14 design.

ARCH-04D is the sole current activation contract; XINT-06B and broad AUTH-14
are historical custody references, not parallel work. Materialization PREP
precedes storage access; final-result PREP binds the accepted output after
I/O. Fixed-service registrations and resource facts must come from the exact
04B/04C manifest, not a generic checker or artifact permission.

Allowed: AUTH catalogue/matrix/evaluator/PREP adapters, delivery composition,
focused AUTH/XINT tests, boundary ledgers and evidence/status. Not allowed:
new authorization protocol, human checker authority, generic artifact reads,
REV actions, TASK transition ownership or serialized prepared handles.

## Canonical ART lineage activation prerequisite

ARCH-04C persists material facts from ART's authorized selection, but migration
0008 does not independently compare the stored `admission_id`, `replica_id` and
`semantic_manifest_sha256` with canonical ART records. Its normal-path
Local/MinIO proof does not establish rejection of false persisted lineage.

Live post-submit materialization, execution and finalization authority must not
be registered or composed until durable finalization enforces one exact canonical
ART lineage tuple. All three stored fields must belong to the same exact
Submission/binding/content lineage under ART's canonical selection rules.
Independent existence, request-copy equality, runtime preflight or a positive
execution test is insufficient. Require an owner-approved persisted-boundary
design using existing ART selection semantics; do not add ad hoc CHECKERS runtime
queries into private ART tables, a parallel validation path or a generic framework.
The executable 04D contract must enumerate the affected owner/database files.

Required proof before activation:

- Real PostgreSQL substitutes each of the three fields independently using valid
  foreign, same-shaped ART lineage and rejects at the durable boundary.
- Each rejection rolls back the terminal result, members, completion event,
  finalization authority evidence and material custody.
- The exact canonical tuple commits as the valid control.
- Removing each comparison makes its corresponding regression fail at the
  intended rejection assertion, after valid setup.
- Production AUTH composition remains denied until all three comparisons and
  the live authorization tests pass. Retain exact replay and immutable history.

## Proposed CHECKERS service manifest

ART's three existing actions cover materialization, output ingestion and
binding only; none authorizes a CHECKERS run/result write. Propose one exact
fixed identity `workstream.checker.post_submit` with two action/permission
pairs: `checker.post_submit.execute` for attempt execution/pre-I/O admission
and `checker.post_submit.finalize` for final-result persistence. Register their
typed contexts, static matrix, admission and unavailable seams explicitly;
activate only after the hidden 04C behavior manifest. No human or outbox
dispatcher receives these service-only permissions. The existing ART
materializer/output identities retain their separate actions; do not collapse
them into this evaluator identity.

Finalization requires fresh authority after I/O, exact current request/fence,
accepted-result digest and verified declared output bindings. The preflight
allow does not authorize final persistence. Operator terminal retry retains
its separately governed recovery action and cannot impersonate ordinary
execution. Negative proof covers each service attempting the other's actions,
request substitution, revocation between calls and complete final rollback.

Acceptance: service, action, resource digest, session, transaction, approved
generation, Submission/binding and checker identities are exact. Resource
facts also bind 04A/04C evaluation-request identity, server-owned
generation, post-plan hash, phase and attempt identity, and the final result
digest where available. Execution/finalization also bind CHECKERS worker-lease
generation separately from outbox claim and evaluation generation. They cannot
authorize a different request or expired worker on the same
Submission. Stale,
cross-resource, mismatched replay, copied-handle or revoked requests detected
before I/O deny before protected side effects. Fresh validation after I/O
suppresses final-current result and routing writes if authority or lineage
changed; it cannot undo earlier authorized reads/evaluator calls. Exact valid
replay returns the same stored identity with no duplicate effects; it never
borrows an earlier allow in place of current authority. Evidence commits
atomically with its protected write. Verify catalogue/database parity,
PostgreSQL races, boundary validators, Ruff and hosted coverage. Required
reviews: authorization architecture, security, product/ops, QA, senior, CI and
test delta.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

## Merge state

- Outcome on merge: `planned`
