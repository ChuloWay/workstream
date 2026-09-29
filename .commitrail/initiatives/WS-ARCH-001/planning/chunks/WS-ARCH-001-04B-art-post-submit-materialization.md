# ART post-submit input and output boundaries

ARCH-04B implementation follows the [current bounded change record](../../WS-ARCH-001-04B.md).
It replaces this input skeleton with exact files, predicates and verification.
The separate output child is delivered by the
[current ARCH-04B2 record](../../WS-ARCH-001-04B2.md).

## ARCH-04B2 — Separate ART output-custody child

Input materialization does not implement output persistence. ARCH-04B2 now
supplies typed `CheckerArtifactOutputPort.store`, byte-free
`recover(selector)`, and `CheckerOutputBindingPort.bind_checker_output` using 04A's
exact immutable request and owner reservation facts. It reuses generic
admission, put intent, observation, verification, quota and binding
infrastructure. ART behavior no longer reads CheckerRun through its private
repository; the separate Operator resource-to-project lookup remains explicit.

Runtime CHECKERS will reserve its run before output I/O. ART admits each
owner-declared slot against project/task/fixed-service/deployment quotas, never
contributor quota, independently rereads/verifies bytes, then supplies a
flush-only binding participant. Authority is fresh for each phase and no row
lock or PREP survives storage I/O. Production reservation and authority remain
unavailable. The current structural catalogue declares zero slots; controlled
nonempty fixtures prove ART mechanics only. 04C must support the empty set and
later composes any reserved bindings with final CHECKER result and completion
outbox in one transaction, after fresh exact action authority supplied by 04D.

The output child proves Local/MinIO parity, non-reproducible/unknown outcome
handling without fabricated bytes, crash cleanup, deadline/quota races,
foreign-request denial and fixed-service attribution. 04C/04D separately prove
the integrated run/binding/result transaction. Neither child owns TASK routing,
REV records or contributor-blame decisions. Expand each owner-local child into
its exact implementation record rather than combining ART and CHECKERS writes
in one implementation PR. The [ARCH-04B2 record](../../WS-ARCH-001-04B2.md) is
the delivered source; this skeleton no longer assigns the next change.
