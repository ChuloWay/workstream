# ART post-submit input and output boundaries

ARCH-04B implementation follows the [current bounded change record](../../WS-ARCH-001-04B.md).
It replaces this input skeleton with exact files, predicates and verification.
The output child below remains separate and Planned.

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

