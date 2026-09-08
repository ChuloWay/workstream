# Chunk Contract: WS-ARCH-001-04B ART Post-Submit Materialization

Disposition: Planned. Dependencies: 04A, POL-07, ARCH-03C and merged 02H. Risk: L1.
Outcome: ART can internally
materialize the exact verified bytes bound to one immutable Submission for the
fixed post-submit checker service.

Allowed: ART public API and owner-local materialization/binding code, fixed
adapter composition, focused ART tests, boundary ledgers and evidence/status.
Not allowed: checker policy/result ownership, TASK mutation, REV packet access,
generic download authority, Celery handle serialization or public routes.

This is the sole replacement for historical ART-06A materialization; do not
run both plans. Preparation may use public fixture facts before activation,
but production remains deny-only until 04D. The capability opens bounded
scratch through ArtifactScratchManager, re-verifies exact stored bytes and
returns typed material facts, never raw credentials or provider handles.

Acceptance: authority and materialization bind project/task/Submission,
admission, binding/content/replica, digest/size and approved generation;
denial precedes provider/scratch access; stale/replaced/cross-resource/replayed
requests fail closed. Verify Local/MinIO protocol tests, scratch cleanup,
PostgreSQL races, boundary validators, Ruff and hosted coverage. Required
reviews: architecture, security, ART/product ops, QA, senior and CI.

## ARCH-04B2 — Separate ART output-custody child

Input materialization does not implement output persistence. Keep a separate
ART-owned bounded change for `CheckerArtifactOutputPort.store` and
`ArtifactBindingPort.bind_checker_output`, using 04A's exact immutable request,
attempt/run and policy facts. Reuse the generic admission, put-intent,
verification, quota and binding infrastructure. Replace the current ART
repository's private CheckerRun lookup with the canonical public-fact boundary;
do not import CHECKERS models in ART behavior. Existing relational run foreign
keys may remain and use controlled foreign-row fixtures for hidden proof.

Runtime CHECKERS reserves its run before output I/O. ART admits bounded output
and logs against project/task/fixed-service/deployment quotas, never contributor
quota, independently rereads/verifies bytes, then supplies a flush-only binding
participant. No row lock or PREP survives storage I/O. 04C later composes final
binding publication with final CHECKER result and completion outbox in one
transaction, after fresh exact action authority supplied by 04D.

The output child proves Local/MinIO parity, non-reproducible/unknown outcome
handling without fabricated bytes, crash cleanup, deadline/quota races,
foreign-request denial and fixed-service attribution. 04C/04D separately prove
the integrated run/binding/result transaction. Neither child owns TASK routing,
REV records or contributor-blame decisions. Expand each owner-local child into
its exact implementation record rather than combining ART and CHECKERS writes
in one implementation PR.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

## Merge state

- Outcome on merge: `planned`
