# Chunk Contract: WS-ARCH-001-04E Canonical Allow-Review Manifest

Status: non-executable planning skeleton after 04D. Risk: L1. Outcome: the hidden admission-backed
Submission automatically dispatches post-submit checking and exposes one
durable current routing fact; an exact `allow_review` manifest becomes the REV
entry dependency.

Allowed: TASK owner-local dispatch/projection code and public API, delivery
composition, focused cross-module integration tests, boundary ledgers,
capability/status docs and exact evidence. Not allowed: REV queue writes,
reviewer behavior, CON behavior, public 02I route cutover, legacy-path claims,
or TASK-owned checker decisions.

TASKS owns one dispatch/outbox record and a current routing projection; CHECKERS
owns the result and recommendation. The success manifest references the exact
persisted AUTH allow events for admission consumption/binding, post-submit
materialization and final-result persistence, including their action/resource
and operation/correlation identities. Do not reuse one action's receipt for
another or treat a routing projection as authorization. Final emission
rechecks run/currentness and locked lineage in the TASK-owned transaction.

## Distinct idempotency and uniqueness custody

Define the canonical input envelope from the locked project/task/assignment,
immutable Submission version, admission/binding/content identity, digest/size,
guide/policy/catalogue lineage and compiled post-plan hash below. Hash it using
the existing canonical hashing convention; matching a key with a different
envelope is a conflict, never a replay. No caller supplies trusted hashes.

| Identity | Deterministic key and database uniqueness owner |
|---|---|
| Dispatch | TASKS owns a unique `(project_id, submission_id, post_plan_hash, evaluation_request_generation)` reservation. Initial submission uses the initial server-owned generation; retry never increments it. A genuinely new authorized evaluation requires a new generation allocated under the TASK lock, not a timeout fallback. No new public reevaluation command is introduced here. |
| Outbox delivery | TASKS owns one domain event identity derived from the dispatch reservation plus event kind; use the existing shared outbox unique-event contract. Delivery retries retain that identity and dispatch reference. |
| Checker attempt | CHECKERS/04C owns one unique `(dispatch_id, phase)` attempt bound to the exact envelope. Its canonical attempt ID is derived from that key; provider/member retry identities derive from this same attempt, never from a delivery timestamp. |
| Routing manifest | TASKS owns one immutable manifest per `(submission_id, checker_run_id, final_result_hash)` and one current routing pointer per Submission. Replays reuse the manifest; replacement changes only the current pointer after CHECKERS currentness and locked-lineage validation in the caller transaction. |

The initial dispatch reservation and outbox event commit atomically. Unique
conflict losers roll back the failed statement/savepoint, lock/read the winning
row and compare its envelope; an exact match reuses it, otherwise deny. Never
publish a message before commit or duplicate the CHECKERS attempt in TASKS.
Final routing locks the Submission/current pointer and consumes CHECKERS public
current-result facts under the same transaction/serialization contract, so a
concurrent supersession cannot publish an obsolete result as current. The
implementation must prove independent-session winners/losers and crash recovery
at each of these four uniqueness boundaries, including outbox redelivery.

Acceptance: one end-to-end test proves approved guide -> authorized assignment
-> verified admission -> immutable Submission/binding -> final current checker
result -> `allow_review`. The manifest explicitly binds the task in its exact
pre-review/evaluation state; immutable Submission id/version; assignment,
contributor and predecessor; admission id; ART binding, content, replica,
digest and byte count; final completed current CheckerRun; no unresolved
blocking failure under the locked post-submit policy; and
`routing_recommendation = allow_review`. It also carries the exact
`WorkstreamTask.locked_contribution_policy_version_id`, the exactly equal
`TaskAssignment.submitter_contribution_policy_version_id`, immutable
`Submission.contribution_policy_version_id`, and locked review/revision policy
lineage needed by later REV and CON consumers. The Submission version was
stamped before any later revision rebase. The initial version was the
same-project, published, complete, binding-valid immutable
version selected at guide activation and locked before task claimability; the
manifest never reselects it and later policy publication cannot alter this
Submission attempt or its downstream lease. Here stale policy means a mismatch
with the attempt's exact locked lineage, not a newer global publication or
later retirement; do not reselect policy or invalidate the stamped version.

Mismatched replay, revocation, stale guide/policy generation, stale assignment, replaced
binding, non-current run, cross-project/resource, wrong service, wrong session,
wrong transaction all deny. Exact replay and concurrent duplicate dispatch
converge on the same stored identity without duplicate effects. Every denial
proves zero unauthorized provider reads, checker mutations, TASK routing transitions, REV
admissions, and duplicate Submission, binding, dispatch, run, or routing rows.
Failures discovered before I/O prove zero provider reads. A late revocation or
stale result after authorized I/O instead proves no final-current result or
routing write; prior authorized I/O cannot be retroactively undone. Reuse the
canonical AUTH error/audit and owner outbox contracts, not a new denial-only
schema. A denied operation emits no allowed-decision fact or product mutation. No
REV admission occurs in this chunk. Verify real
API/database/Celery/MinIO integration, recovery
and concurrency tests, all boundary validators, Ruff and hosted coverage.
Required reviews: architecture, authorization security, product/ops, QA,
senior, reuse, CI, docs and test delta. Human focus: whether this exact merged
manifest is sufficient to let REV-05A begin.

Final checker outcomes other than `allow_review` remain hidden and fail closed
for routing in 04E. Before public 02I, a separate executable child must install
contributor-readable checker-remediation lineage for final needs-revision
checker results without creating Review, ReviewFinding, or
RevisionContextPreparation records.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

## Merge state

- Outcome on merge: `planned`
