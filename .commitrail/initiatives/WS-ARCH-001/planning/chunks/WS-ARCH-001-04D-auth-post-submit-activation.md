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
